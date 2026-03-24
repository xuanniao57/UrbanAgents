"""
Multi-Agent Orchestrator — 三层架构总调度器

将 Planning → Execution → Review 三层串联，
对外暴露与原 UrbanAgent.execute_task() 兼容的接口。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, Dict, Optional

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

logger = logging.getLogger(__name__)


class MultiAgentOrchestrator:
    """
    三层多智能体编排器

    Architecture:
      Planning Layer  → PlannerAgent
      Execution Layer → ManagerAgent + Workers
      Review Layer    → SpatialReviewer + HumanCheckpoint

    Usage:
        orchestrator = MultiAgentOrchestrator(llm_client=my_llm)
        result = await orchestrator.run(task, task_type)
    """

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        vlm_client: Optional[Any] = None,
        mcp_client: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None,
        interaction_mode: str = "autonomous",
        human_callback: Optional[Callable] = None,
        # 可选注入已有模块 (向后兼容)
        perception_module: Optional[Any] = None,
        reasoning_module: Optional[Any] = None,
        visualization_module: Optional[Any] = None,
        memory_module: Optional[Any] = None,
    ):
        self.config = config or {}
        self.memory_module = memory_module

        # — Planning Layer —
        self.planner = PlannerAgent(llm_client=llm_client, config=self.config)

        # — Execution Layer: Workers —
        workers = {
            AgentRole.PERCEPTION: PerceptionWorker(
                perception_module=perception_module,
                llm_client=llm_client,
            ),
            AgentRole.ANALYST: AnalystWorker(
                reasoning_module=reasoning_module,
                llm_client=llm_client,
            ),
            AgentRole.CARTOGRAPHER: CartographerWorker(
                visualization_module=visualization_module,
                llm_client=llm_client,
            ),
            AgentRole.REPORTER: ReporterWorker(llm_client=llm_client),
        }

        # — Review Layer —
        reviewers = {
            AgentRole.SPATIAL_REVIEWER: SpatialReviewerAgent(llm_client=llm_client),
            AgentRole.HUMAN_CHECKPOINT: HumanCheckpointAgent(
                interaction_mode=interaction_mode,
                human_callback=human_callback,
            ),
        }

        # — Manager —
        self.manager = ManagerAgent(
            workers=workers,
            reviewers=reviewers,
            llm_client=llm_client,
        )

    async def run(
        self,
        task: Dict[str, Any],
        task_type: str = "geoqa",
        city_data: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        执行完整的三层多智能体协作流程

        兼容原 UrbanAgent.execute_task() 参数签名
        """
        trace_id = f"trace_{task_type}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        task_payload = dict(task)
        task_payload["task_type"] = task_type
        if city_data:
            task_payload["city_data"] = city_data

        logger.info(f"[Orchestrator] Starting multi-agent pipeline: {trace_id}")

        # Step 1: Memory retrieval (if available)
        memory_context = {}
        if self.memory_module is not None:
            try:
                memory_context = await self.memory_module.retrieve(task_payload)
            except Exception as e:
                logger.warning(f"Memory retrieval failed: {e}")
        task_payload["memory_context"] = memory_context

        # Step 2: Planning Layer
        plan_msg = AgentMessage(
            sender=AgentRole.MANAGER,  # 外部触发
            receiver=AgentRole.PLANNER,
            msg_type="task_plan",
            payload=task_payload,
            trace_id=trace_id,
        )
        plan_result = await self.planner.execute(plan_msg)

        # Step 3: Execution Layer (Manager → Workers → Review)
        exec_result = await self.manager.execute(plan_result)

        # Step 4: Memory update (if available)
        if self.memory_module is not None:
            try:
                await self.memory_module.store({
                    "task": task_payload,
                    "plan": plan_result.payload,
                    "results": exec_result.payload,
                    "timestamp": datetime.now().isoformat(),
                })
            except Exception as e:
                logger.warning(f"Memory update failed: {e}")

        # Step 5: 组装最终输出 (兼容原接口)
        results = exec_result.payload.get("results", {})
        return {
            "trace_id": trace_id,
            "task_type": task_type,
            "status": "success" if results.get("completed", 0) > 0 else "partial",
            "plan": plan_result.payload.get("execution_plan", {}),
            "results": results,
            "final_answer": self._extract_answer(results),
            "review": results.get("review", {}),
        }

    @staticmethod
    def _extract_answer(results: Dict) -> str:
        """从子任务结果中提取最终答案"""
        subtask_results = results.get("subtask_results", {})
        # 优先取 reporter 的结果
        for st_data in subtask_results.values():
            if st_data.get("role") == "reporter":
                report = st_data.get("result", {})
                if isinstance(report, dict):
                    return report.get("report", "")
        # 否则取最后一个完成的子任务
        for st_data in reversed(list(subtask_results.values())):
            if st_data.get("status") == "completed":
                result = st_data.get("result", {})
                if isinstance(result, dict):
                    return result.get("answer", result.get("report", str(result)))
                return str(result)
        return ""
