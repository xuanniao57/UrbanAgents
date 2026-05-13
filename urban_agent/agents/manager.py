"""
Manager Agent — Execution Layer Orchestrator
参考 GeoAgent 的 Manager：子任务调度 + Worker 分配 + 上下文隔离

职责：
1. 接收 ExecutionPlan，按依赖顺序调度子任务
2. 为每个 Worker 构造隔离的上下文（AutoBEE 信息隔离）
3. 收集结果，传递给 Review Layer
"""

from __future__ import annotations

import json
import logging
import math
import time
from typing import Any, Dict, List, Optional

from .base import (
    AgentMessage,
    AgentRole,
    BaseAgent,
    SubTask,
)
from .runtime import RuntimeLedger, checkpoint_for_agent, checkpoint_is_approved

logger = logging.getLogger(__name__)


class ManagerAgent(BaseAgent):
    """
    执行层管理者

    核心设计（AutoBEE 信息隔离）：
    - Worker 只接收自己子任务的上下文
    - Worker 之间不直接通信
    - 结果由 Manager 统一收集和路由
    """

    def __init__(
        self,
        workers: Optional[Dict[AgentRole, BaseAgent]] = None,
        reviewers: Optional[Dict[AgentRole, BaseAgent]] = None,
        llm_client: Optional[Any] = None,
        **kwargs,
    ):
        super().__init__(role=AgentRole.MANAGER, llm_client=llm_client, **kwargs)
        self.workers = workers or {}
        self.reviewers = reviewers or {}
        self._subtask_results: Dict[str, Dict[str, Any]] = {}
        self._runtime_ledger: Optional[RuntimeLedger] = None

    @property
    def role_prompt(self) -> str:
        return (
            "You are the Manager Agent. You orchestrate task execution by:\n"
            "1. Dispatching subtasks to the correct Worker Agent\n"
            "2. Maintaining information isolation between workers\n"
            "3. Collecting results and routing to reviewers\n"
            "4. Handling failures with graceful fallbacks"
        )

    async def execute(self, message: AgentMessage) -> AgentMessage:
        """
        执行编排流程：
        1. 解析 ExecutionPlan
        2. 按依赖顺序执行子任务
        3. 送审 Review Layer
        4. 汇总最终结果
        """
        plan_data = message.payload.get("execution_plan", {})
        trace_id = message.trace_id
        self.log_message(message)

        subtasks = self._parse_subtasks(plan_data)
        execution_order = plan_data.get("execution_order", [st.subtask_id for st in subtasks])
        subtask_map = {st.subtask_id: st for st in subtasks}
        self._subtask_results = {}
        self._runtime_ledger = RuntimeLedger.from_plan(
            plan_data,
            interaction_mode=self._checkpoint_mode(),
        )

        scope_decision = await self._run_human_checkpoint(
            "DP-1",
            "task_interpretation_and_scoping",
            {"plan": plan_data, "subtask_count": len(subtasks)},
            trace_id,
        )
        if not checkpoint_is_approved(scope_decision):
            self._runtime_ledger.cancel_pending(scope_decision.get("reason", "checkpoint blocked execution"))
            aggregated = self._aggregate_results(subtasks)
            return AgentMessage(
                sender=AgentRole.MANAGER,
                receiver=AgentRole.PLANNER,
                msg_type="result",
                payload={"results": aggregated, "plan_id": plan_data.get("plan_id")},
                trace_id=trace_id,
            )

        # 按序执行（尊重依赖关系）
        for st_id in execution_order:
            st = subtask_map.get(st_id)
            if st is None:
                continue
            await self._execute_subtask(st, trace_id)

        # 汇总结果
        aggregated = self._aggregate_results(subtasks)

        # 送审 Review Layer
        review_input_snapshot = json.loads(json.dumps(aggregated, ensure_ascii=False, default=str))
        review_start = time.perf_counter()
        reviewed = await self._send_to_review(aggregated, trace_id)
        review_latency = round(time.perf_counter() - review_start, 4)
        reviewed.setdefault("_meta", {})["review"] = {
            "latency_s": review_latency,
            "input_tokens_est": self._estimate_tokens(review_input_snapshot),
            "output_tokens_est": self._estimate_tokens(reviewed.get("review", {})),
        }

        result_msg = AgentMessage(
            sender=AgentRole.MANAGER,
            receiver=AgentRole.PLANNER,  # 返回给调用者
            msg_type="result",
            payload={"results": reviewed, "plan_id": plan_data.get("plan_id")},
            trace_id=trace_id,
        )
        self.log_message(result_msg)
        return result_msg

    @staticmethod
    def _estimate_tokens(payload: Any) -> int:
        try:
            text = json.dumps(payload, ensure_ascii=False, default=str)
        except Exception:
            text = str(payload)
        if not text:
            return 0
        return max(1, math.ceil(len(text) / 4))

    # ------------------------------------------------------------------
    # 子任务执行
    # ------------------------------------------------------------------

    async def _execute_subtask(self, subtask: SubTask, trace_id: str):
        """执行单个子任务 — 信息隔离"""
        role = subtask.assigned_role
        worker = self.workers.get(role)

        if worker is None:
            logger.warning(f"No worker for role {role.value}, skipping {subtask.subtask_id}")
            subtask.status = "failed"
            subtask.result = {"error": f"No worker for {role.value}"}
            if self._runtime_ledger is not None:
                self._runtime_ledger.fail_subtask(subtask.subtask_id, subtask.result["error"])
            return

        # 构造隔离上下文 — Worker 只看到自己需要的数据
        isolated_context = self._build_isolated_context(subtask)

        msg = AgentMessage(
            sender=AgentRole.MANAGER,
            receiver=role,
            msg_type="subtask",
            payload=isolated_context,
            trace_id=trace_id,
        )

        try:
            subtask.status = "running"
            if self._runtime_ledger is not None:
                self._runtime_ledger.start_subtask(
                    subtask.subtask_id,
                    agent=role.value,
                    objective=subtask.objective,
                )
            result_msg = await worker.execute(msg)
            result_payload = result_msg.payload
            checkpoint = checkpoint_for_agent(role.value)
            if checkpoint:
                checkpoint_id, stage = checkpoint
                decision = await self._run_human_checkpoint(
                    checkpoint_id,
                    stage,
                    {
                        "subtask_id": subtask.subtask_id,
                        "agent": role.value,
                        "objective": subtask.objective,
                        "result": result_payload,
                    },
                    trace_id,
                    subtask_id=subtask.subtask_id,
                    agent=role.value,
                )
                if not checkpoint_is_approved(decision):
                    subtask.status = "failed"
                    subtask.result = {
                        "error": "blocked_by_human_checkpoint",
                        "checkpoint_decision": decision,
                        "draft_result": result_payload,
                    }
                    if self._runtime_ledger is not None:
                        self._runtime_ledger.fail_subtask(
                            subtask.subtask_id,
                            decision.get("reason", "checkpoint blocked result"),
                        )
                    return

            subtask.result = result_payload
            subtask.status = "completed"
            self._subtask_results[subtask.subtask_id] = result_payload
            if self._runtime_ledger is not None:
                self._runtime_ledger.complete_subtask(subtask.subtask_id, result_payload)
        except Exception as e:
            logger.error(f"Subtask {subtask.subtask_id} failed: {e}")
            subtask.status = "failed"
            subtask.result = {"error": str(e)}
            if self._runtime_ledger is not None:
                self._runtime_ledger.fail_subtask(subtask.subtask_id, str(e))

    def _build_isolated_context(self, subtask: SubTask) -> Dict[str, Any]:
        """
        信息隔离：只传递该子任务需要的上下文

        依赖子任务的输出 → 作为输入数据传入
        其他子任务的结果 → 不可见
        """
        context = {
            "subtask_id": subtask.subtask_id,
            "objective": subtask.objective,
            "input_data": dict(subtask.input_data),
        }

        if subtask.input_data.get("capability_context"):
            context["capability_context"] = subtask.input_data["capability_context"]
        if subtask.input_data.get("feedback_context"):
            context["feedback_context"] = subtask.input_data["feedback_context"]
        if subtask.input_data.get("memory_context"):
            context["memory_context"] = subtask.input_data["memory_context"]

        # Reporter is the synthesis role: it needs all completed upstream outputs.
        # Other workers keep dependency-only context isolation.
        if subtask.assigned_role == AgentRole.REPORTER:
            context["dependency_results"] = dict(self._subtask_results)
        else:
            for dep_id in subtask.dependencies:
                if dep_id in self._subtask_results:
                    context.setdefault("dependency_results", {})[dep_id] = self._subtask_results[dep_id]

        if subtask.review_feedback:
            context["review_feedback"] = subtask.review_feedback

        return context

    # ------------------------------------------------------------------
    # 审查与汇总
    # ------------------------------------------------------------------

    async def _send_to_review(self, aggregated: Dict, trace_id: str) -> Dict[str, Any]:
        """送审 Review Layer"""
        reviewer = self.reviewers.get(AgentRole.SPATIAL_REVIEWER)
        if reviewer is None:
            logger.info("No spatial reviewer configured, skipping review")
            return aggregated

        review_msg = AgentMessage(
            sender=AgentRole.MANAGER,
            receiver=AgentRole.SPATIAL_REVIEWER,
            msg_type="review",
            payload=aggregated,
            trace_id=trace_id,
        )
        try:
            feedback_msg = await reviewer.execute(review_msg)
            aggregated["review"] = feedback_msg.payload
        except Exception as e:
            logger.warning(f"Review failed: {e}")
            aggregated["review"] = {"status": "skipped", "reason": str(e)}

        return aggregated

    async def _run_human_checkpoint(
        self,
        checkpoint_id: str,
        stage: str,
        data: Dict[str, Any],
        trace_id: str,
        *,
        subtask_id: Optional[str] = None,
        agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        checkpoint_agent = self.reviewers.get(AgentRole.HUMAN_CHECKPOINT)
        mode = self._checkpoint_mode()
        decision: Dict[str, Any] = {"action": "approve", "reason": "human checkpoint not configured"}

        if checkpoint_agent is not None:
            checkpoint_msg = AgentMessage(
                sender=AgentRole.MANAGER,
                receiver=AgentRole.HUMAN_CHECKPOINT,
                msg_type="checkpoint",
                payload={"checkpoint_id": checkpoint_id, "stage": stage, "data": data},
                trace_id=trace_id,
            )
            try:
                feedback = await checkpoint_agent.execute(checkpoint_msg)
                decision = feedback.payload.get("decision", decision)
            except Exception as error:
                logger.warning("Human checkpoint %s failed: %s", checkpoint_id, error)
                decision = {"action": "approve", "reason": f"checkpoint failed open: {error}"}

        if self._runtime_ledger is not None:
            self._runtime_ledger.record_checkpoint(
                checkpoint_id=checkpoint_id,
                stage=stage,
                mode=mode,
                decision=decision,
                subtask_id=subtask_id,
                agent=agent,
                payload=data,
            )
        return decision

    def _checkpoint_mode(self) -> str:
        checkpoint_agent = self.reviewers.get(AgentRole.HUMAN_CHECKPOINT)
        return str(getattr(checkpoint_agent, "interaction_mode", "autonomous"))

    def _aggregate_results(self, subtasks: List[SubTask]) -> Dict[str, Any]:
        """汇总所有子任务结果"""
        results = {}
        for st in subtasks:
            results[st.subtask_id] = {
                "objective": st.objective,
                "role": st.assigned_role.value,
                "status": st.status,
                "result": st.result,
            }
        aggregated = {
            "subtask_results": results,
            "completed": sum(1 for st in subtasks if st.status == "completed"),
            "total": len(subtasks),
        }
        if self._runtime_ledger is not None:
            aggregated["runtime"] = self._runtime_ledger.to_dict()
        return aggregated

    @staticmethod
    def _parse_subtasks(plan_data: Dict) -> List[SubTask]:
        """从序列化的 plan 还原 SubTask 列表"""
        subtasks = []
        for st_data in plan_data.get("subtasks", []):
            subtasks.append(
                SubTask(
                    subtask_id=st_data["subtask_id"],
                    objective=st_data["objective"],
                    assigned_role=AgentRole(st_data["assigned_role"]),
                    input_data=st_data.get("input_data", {}),
                    dependencies=st_data.get("dependencies", []),
                    expected_output=st_data.get("expected_output", ""),
                )
            )
        return subtasks
