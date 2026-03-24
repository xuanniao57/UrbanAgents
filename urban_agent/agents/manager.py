"""
Manager Agent — Execution Layer Orchestrator
参考 GeoAgent 的 Manager：子任务调度 + Worker 分配 + 上下文隔离

职责：
1. 接收 ExecutionPlan，按依赖顺序调度子任务
2. 为每个 Worker 构造隔离的上下文（AutoBEE 信息隔离）
3. 收集结果，传递给 Review Layer
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .base import (
    AgentMessage,
    AgentRole,
    BaseAgent,
    SubTask,
)

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

        # 按序执行（尊重依赖关系）
        for st_id in execution_order:
            st = subtask_map.get(st_id)
            if st is None:
                continue
            await self._execute_subtask(st, trace_id)

        # 汇总结果
        aggregated = self._aggregate_results(subtasks)

        # 送审 Review Layer
        reviewed = await self._send_to_review(aggregated, trace_id)

        result_msg = AgentMessage(
            sender=AgentRole.MANAGER,
            receiver=AgentRole.PLANNER,  # 返回给调用者
            msg_type="result",
            payload={"results": reviewed, "plan_id": plan_data.get("plan_id")},
            trace_id=trace_id,
        )
        self.log_message(result_msg)
        return result_msg

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
            result_msg = await worker.execute(msg)
            subtask.result = result_msg.payload
            subtask.status = "completed"
            self._subtask_results[subtask.subtask_id] = result_msg.payload
        except Exception as e:
            logger.error(f"Subtask {subtask.subtask_id} failed: {e}")
            subtask.status = "failed"
            subtask.result = {"error": str(e)}

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

        # 注入依赖子任务的输出（且仅限依赖）
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
        return {
            "subtask_results": results,
            "completed": sum(1 for st in subtasks if st.status == "completed"),
            "total": len(subtasks),
        }

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
                    dependencies=st_data.get("dependencies", []),
                    expected_output=st_data.get("expected_output", ""),
                )
            )
        return subtasks
