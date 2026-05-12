"""
Multi-Agent Orchestrator — 三层架构总调度器

将 Planning → Execution → Review 三层串联，
对外暴露与原 UrbanAgent.execute_task() 兼容的接口。
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..capabilities import CapabilityRegistry, get_default_capability_registry
from ..feedback_memory import get_default_feedback_memory
from ..core import CorrectionModuleRegistry, MemoryModule
from .efficiency import MODEL_PRICING
from .base import AgentMessage, AgentRole, ExecutionPlan
from .planner import PlannerAgent
from .manager import ManagerAgent
from .workers import (
    AnalystWorker,
    CartographerWorker,
    PerceptionWorker,
    ReporterWorker,
)
from .reviewers import HumanCheckpointAgent, SpatialReviewerAgent
from .quality_controller import QualityController

logger = logging.getLogger(__name__)


class MultiAgentOrchestrator:
    """
    四层多智能体编排器

    Architecture:
      Planning Layer     → PlannerAgent
      Execution Layer    → ManagerAgent + Workers
      Review Layer       → SpatialReviewer + HumanCheckpoint
      Quality Control    → QualityController (cross-cutting)

    Usage:
        orchestrator = MultiAgentOrchestrator(llm_client=my_llm)
        result = await orchestrator.run(task)
    """

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        vlm_client: Optional[Any] = None,
        mcp_client: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None,
        interaction_mode: str = "autonomous",
        human_callback: Optional[Callable] = None,
        # Feature flags for ablation experiments
        enable_planning: bool = True,
        enable_review: bool = True,
        enable_quality_control: bool = True,
        enable_dual_space: bool = True,
        enable_memory: bool = True,
        disable_capabilities: bool = False,
        # 可选注入已有模块 (向后兼容)
        perception_module: Optional[Any] = None,
        reasoning_module: Optional[Any] = None,
        visualization_module: Optional[Any] = None,
        memory_module: Optional[Any] = None,
        correction_registry: Optional[CorrectionModuleRegistry] = None,
        capability_registry: Optional[CapabilityRegistry] = None,
        # Multi-model: separate clients for planner vs execution
        planner_llm_client: Optional[Any] = None,
    ):
        self.config = config or {}
        self.capability_registry = capability_registry or get_default_capability_registry()
        self.correction_registry = correction_registry or CorrectionModuleRegistry()

        # Resolve clients: planner uses deep reasoning, others use fast
        _planner_client = planner_llm_client or llm_client
        _exec_client = llm_client
        self.feedback_memory = get_default_feedback_memory()
        self.memory_module = (
            memory_module
            if memory_module is not None
            else (MemoryModule(config=self.config.get("memory", {}), llm_client=_exec_client) if enable_memory else None)
        )

        # Feature flags
        self.enable_planning = enable_planning
        self.enable_review = enable_review
        self.enable_quality_control = enable_quality_control
        self.enable_dual_space = enable_dual_space
        self.enable_memory = enable_memory
        self.disable_capabilities = disable_capabilities
        self.model_name = getattr(llm_client, "model", "default") if llm_client is not None else "default"
        self.planner_model_name = getattr(_planner_client, "model", self.model_name) if _planner_client is not None else self.model_name

        # — Efficiency tracking —
        self._token_log: list[Dict[str, Any]] = []
        self._start_times: Dict[str, float] = {}

        # — Planning Layer (deep reasoning) —
        self.planner = PlannerAgent(
            llm_client=_planner_client,
            config=self.config,
            capability_registry=self.capability_registry,
            feedback_memory=self.feedback_memory,
        )

        # — Quality Controller (RMDA-style cross-cutting) —
        self.quality_controller = QualityController(llm_client=_exec_client) if enable_quality_control else None

        # — Execution Layer: Workers (fast) —
        workers = {
            AgentRole.PERCEPTION: PerceptionWorker(
                perception_module=perception_module,
                llm_client=_exec_client,
            ),
            AgentRole.ANALYST: AnalystWorker(
                reasoning_module=reasoning_module,
                llm_client=_exec_client,
                capability_registry=self.capability_registry,
                disable_capabilities=disable_capabilities,
            ),
            AgentRole.CARTOGRAPHER: CartographerWorker(
                visualization_module=visualization_module,
                llm_client=_exec_client,
                capability_registry=self.capability_registry,
                disable_capabilities=disable_capabilities,
            ),
            AgentRole.REPORTER: ReporterWorker(llm_client=_exec_client),
        }

        # — Review Layer (fast) —
        reviewers = {
            AgentRole.HUMAN_CHECKPOINT: HumanCheckpointAgent(
                interaction_mode=interaction_mode,
                human_callback=human_callback,
            ),
        }
        if enable_review:
            reviewers[AgentRole.SPATIAL_REVIEWER] = SpatialReviewerAgent(llm_client=_exec_client, feedback_memory=self.feedback_memory)

        # — Manager (fast) —
        self.manager = ManagerAgent(
            workers=workers,
            reviewers=reviewers,
            llm_client=_exec_client,
        )

    # ------------------------------------------------------------------
    # Efficiency helpers
    # ------------------------------------------------------------------

    def _tick(self, label: str) -> None:
        import time
        self._start_times[label] = time.perf_counter()

    def _tock(self, label: str) -> float:
        import time
        return time.perf_counter() - self._start_times.pop(label, time.perf_counter())

    def _estimate_tokens(self, payload: Any) -> int:
        try:
            text = json.dumps(payload, ensure_ascii=False, default=str)
        except Exception:
            text = str(payload)
        if not text:
            return 0
        return max(1, math.ceil(len(text) / 4))

    def _estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        pricing = MODEL_PRICING.get(self.model_name, MODEL_PRICING["default"])
        return round((input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1000, 6)

    def _record_efficiency(self, layer: str, latency_s: float, input_payload: Any = None, output_payload: Any = None) -> Dict[str, Any]:
        input_tokens = self._estimate_tokens(input_payload)
        output_tokens = self._estimate_tokens(output_payload)
        record = {
            "layer": layer,
            "latency_s": round(latency_s, 4),
            "input_tokens_est": input_tokens,
            "output_tokens_est": output_tokens,
            "est_cost_usd": self._estimate_cost(input_tokens, output_tokens),
        }
        self._token_log.append(record)
        return record

    def get_efficiency_summary(self) -> Dict[str, Dict[str, Any]]:
        summary: Dict[str, Dict[str, Any]] = {}
        layer_alias = {
            "quality_control_plan": "quality_control",
            "quality_control_exec": "quality_control",
        }
        for record in self._token_log:
            layer = layer_alias.get(record["layer"], record["layer"])
            stats = summary.setdefault(layer, {
                "count": 0,
                "input_tokens_est": 0,
                "output_tokens_est": 0,
                "latency_s": 0.0,
                "est_cost_usd": 0.0,
            })
            stats["count"] += 1
            stats["input_tokens_est"] += record.get("input_tokens_est", 0)
            stats["output_tokens_est"] += record.get("output_tokens_est", 0)
            stats["latency_s"] += record.get("latency_s", 0.0)
            stats["est_cost_usd"] += record.get("est_cost_usd", 0.0)

        for stats in summary.values():
            stats["latency_s"] = round(stats["latency_s"], 4)
            stats["est_cost_usd"] = round(stats["est_cost_usd"], 6)
        return summary

    def get_efficiency_report(self) -> List[Dict[str, Any]]:
        """Return per-layer latency log (for ablation / Table 4 data)."""
        return list(self._token_log)

    # ------------------------------------------------------------------
    # Quality-control helper
    # ------------------------------------------------------------------

    async def _qc_check(
        self,
        source_role: str,
        output: Dict[str, Any],
        task_context: Dict[str, Any],
        mode: str = "recommender",
        trace_id: str = "",
    ) -> Tuple[bool, Dict]:
        """Run QualityController and return (passed, report_payload)."""
        if self.quality_controller is None:
            return True, {}
        qc_msg = AgentMessage(
            sender=AgentRole.MANAGER,
            receiver=AgentRole.QUALITY_CONTROLLER,
            msg_type="quality_check",
            payload={
                "source_role": source_role,
                "output": output,
                "task_context": task_context,
                "qc_mode": mode,
            },
            trace_id=trace_id,
        )
        qc_result = await self.quality_controller.execute(qc_msg)
        report = qc_result.payload
        return report.get("passed", True), report

    # ------------------------------------------------------------------
    # Main pipeline
    # ------------------------------------------------------------------

    async def run(
        self,
        task: Dict[str, Any],
        city_data: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        执行四层多智能体协作流程

        Layers:
          1. Memory Retrieval  (skippable via enable_memory=False)
          2. Planning          (skippable via enable_planning=False)
          3. Execution + Review (review skippable via enable_review=False)
          4. Quality Control   (skippable via enable_quality_control=False)

        兼容原 UrbanAgent.execute_task() 参数签名
        """
        trace_id = f"trace_urban_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        task_payload = dict(task)
        if city_data:
            task_payload["city_data"] = city_data

        logger.info(f"[Orchestrator] Starting multi-agent pipeline: {trace_id}")
        self._token_log = []
        self._start_times = {}
        self._tick("total")

        # ── Step 1: Memory Retrieval ──
        memory_context: Dict = {}
        if self.enable_memory and self.memory_module is not None:
            self._tick("memory_retrieve")
            try:
                memory_context = await self.memory_module.retrieve(task_payload)
            except Exception as e:
                logger.warning(f"Memory retrieval failed: {e}")
            memory_retrieve_latency = self._tock("memory_retrieve")
            self._record_efficiency("memory_retrieve", memory_retrieve_latency, task_payload, memory_context)
        task_payload["memory_context"] = memory_context

        # ── Step 2: Planning Layer ──
        self._tick("planning")
        if self.enable_planning:
            plan_msg = AgentMessage(
                sender=AgentRole.MANAGER,
                receiver=AgentRole.PLANNER,
                msg_type="task_plan",
                payload=task_payload,
                trace_id=trace_id,
            )
            plan_result = await self.planner.execute(plan_msg)
        else:
            # Ablation: skip planner — pass task directly as a single-step plan
            direct_subtask = {
                "subtask_id": f"direct_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
                "objective": task_payload.get("question", str(task_payload))[:240],
                "assigned_role": "analyst",
                "input_data": task_payload,
                "dependencies": [],
                "expected_output": "Direct analyst output without planner decomposition",
            }
            plan_result = AgentMessage(
                sender=AgentRole.PLANNER,
                receiver=AgentRole.MANAGER,
                msg_type="plan_result",
                payload={
                    "execution_plan": {
                        "plan_id": f"direct_plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                        "original_task": task_payload,
                        "complexity": "direct",
                        "workflow_profile": "planner_ablation_direct_execution",
                        "subtasks": [direct_subtask],
                        "execution_order": [direct_subtask["subtask_id"]],
                    },
                },
                trace_id=trace_id,
            )
        plan_latency = self._tock("planning")
        self._record_efficiency("planning", plan_latency, task_payload, plan_result.payload)

        # QC gate: validate plan
        plan_qc_payload = {
            "source_role": "planner",
            "output": plan_result.payload,
            "task_context": task_payload,
            "qc_mode": "configurator",
        }
        self._tick("quality_control_plan")
        plan_passed, plan_qc = await self._qc_check(
            source_role="planner",
            output=plan_result.payload,
            task_context=task_payload,
            mode="configurator",
            trace_id=trace_id,
        )
        plan_qc_latency = self._tock("quality_control_plan")
        self._record_efficiency("quality_control_plan", plan_qc_latency, plan_qc_payload, plan_qc)
        if not plan_passed:
            logger.warning(f"[QC] Plan quality below threshold: {plan_qc}")

        # ── Step 3: Execution Layer (Manager → Workers → Review) ──
        self._tick("execution")
        exec_result = await self.manager.execute(plan_result)
        exec_total_latency = self._tock("execution")
        review_meta = exec_result.payload.get("results", {}).get("_meta", {}).get("review", {})
        review_latency = float(review_meta.get("latency_s", 0.0))
        exec_latency = max(exec_total_latency - review_latency, 0.0)
        self._record_efficiency("execution", exec_latency, plan_result.payload, exec_result.payload)
        if review_latency > 0 or review_meta:
            self._token_log.append({
                "layer": "review",
                "latency_s": round(review_latency, 4),
                "input_tokens_est": int(review_meta.get("input_tokens_est", 0)),
                "output_tokens_est": int(review_meta.get("output_tokens_est", 0)),
                "est_cost_usd": self._estimate_cost(
                    int(review_meta.get("input_tokens_est", 0)),
                    int(review_meta.get("output_tokens_est", 0)),
                ),
            })

        # QC gate: validate execution output (normalize for completeness check)
        raw_exec_output = exec_result.payload
        exec_output_for_qc = dict(raw_exec_output)
        results = raw_exec_output.get("results", {})
        # Inject top-level status/answer fields that QC completeness checker expects
        exec_output_for_qc.setdefault("status", "completed" if results.get("completed", 0) > 0 else "partial")
        exec_output_for_qc.setdefault("answer", self._extract_answer(results))
        exec_qc_payload = {
            "source_role": "execution",
            "output": exec_output_for_qc,
            "task_context": {"required_fields": ["status", "results", "answer"], **task_payload},
            "qc_mode": "recommender",
        }
        self._tick("quality_control_exec")
        exec_passed, exec_qc = await self._qc_check(
            source_role="execution",
            output=exec_output_for_qc,
            task_context=exec_qc_payload["task_context"],
            mode="recommender",
            trace_id=trace_id,
        )
        exec_qc_latency = self._tock("quality_control_exec")
        self._record_efficiency("quality_control_exec", exec_qc_latency, exec_qc_payload, exec_qc)
        if not exec_passed:
            logger.warning(f"[QC] Execution output confidence low: {exec_qc}")

        # ── Step 4: Memory Update ──
        if self.enable_memory and self.memory_module is not None:
            self._tick("memory_store")
            memory_store_payload = {
                "task": task_payload,
                "plan": plan_result.payload,
                "results": exec_result.payload,
                "timestamp": datetime.now().isoformat(),
            }
            try:
                await self.memory_module.store(memory_store_payload)
            except Exception as e:
                logger.warning(f"Memory update failed: {e}")
            memory_store_latency = self._tock("memory_store")
            self._record_efficiency("memory_store", memory_store_latency, memory_store_payload, {"stored": True})

        total_latency = self._tock("total")
        self._record_efficiency("total", total_latency, task_payload, exec_result.payload)

        # ── Step 5: Assemble output ──
        results = exec_result.payload.get("results", {})
        return {
            "trace_id": trace_id,
            "status": "success" if results.get("completed", 0) > 0 else "partial",
            "plan": plan_result.payload.get("execution_plan", {}),
            "results": results,
            "final_answer": self._extract_answer(results),
            "review": results.get("review", {}),
            # New: quality & efficiency metadata
            "quality_control": {
                "plan_qc": plan_qc,
                "exec_qc": exec_qc,
                "plan_passed": plan_passed,
                "exec_passed": exec_passed,
            },
            "alignment_support": {
                "correction_modules": self.correction_registry.list_modules(),
                "memory_snapshot": self.memory_module.inspect_state() if self.memory_module is not None and hasattr(self.memory_module, "inspect_state") else {},
                "feedback_memory_root": str(self.feedback_memory.memory_store.root),
                "review_feedback_memory_path": review_memory_path,
            },
            "efficiency": {
                "plan_latency_s": plan_latency,
                "exec_latency_s": exec_latency,
                "review_latency_s": round(review_latency, 4),
                "quality_control_latency_s": round(plan_qc_latency + exec_qc_latency, 4),
                "total_latency_s": total_latency,
                "detail": self.get_efficiency_report(),
                "summary": self.get_efficiency_summary(),
            },
            "ablation_config": {
                "planning": self.enable_planning,
                "review": self.enable_review,
                "quality_control": self.enable_quality_control,
                "dual_space": self.enable_dual_space,
                "memory": self.enable_memory,
            },
        }

    @staticmethod
    def _extract_answer(results: Dict) -> str:
        """从子任务结果中提取最终答案"""
        subtask_results = results.get("subtask_results", {})
        # 优先取 reporter 的完整报告。
        for st_data in subtask_results.values():
            if st_data.get("role") == "reporter":
                report = st_data.get("result", {})
                if isinstance(report, dict) and report.get("report"):
                    return report.get("report", "")

        for st_data in subtask_results.values():
            if st_data.get("status") != "completed":
                continue
            result = st_data.get("result", {})
            if isinstance(result, dict) and result.get("answer"):
                return str(result["answer"])

        for st_data in subtask_results.values():
            if st_data.get("status") != "completed":
                continue
            result = st_data.get("result", {})
            if isinstance(result, dict):
                for key in ("analysis", "findings", "summary", "llm_analysis"):
                    value = result.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
                    if value:
                        return json.dumps(value, ensure_ascii=False, default=str)

        for st_data in subtask_results.values():
            if st_data.get("status") != "completed":
                continue
            result = st_data.get("result", {})
            if isinstance(result, dict) and result.get("report"):
                return str(result["report"])

        for st_data in reversed(list(subtask_results.values())):
            if st_data.get("status") == "completed":
                result = st_data.get("result", {})
                if isinstance(result, str):
                    return result.strip()
                if isinstance(result, dict):
                    content = result.get("content")
                    if isinstance(content, str) and content.strip():
                        return content.strip()
                    if content:
                        return str(content)
        return ""
