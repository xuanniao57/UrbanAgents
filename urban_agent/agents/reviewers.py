"""
Review Layer Agents — 质量审查与人机协作
参考 GeoAgent 的 Review Layer（去掉审查层 → -25.17%）

两个 Reviewer：
1. SpatialReviewerAgent: 空间一致性校验 + 拓扑/矢量对齐审查
2. HumanCheckpointAgent: DP-1~DP-6 决策门控（Guided / Supervisory / Autonomous）
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from .base import AgentMessage, AgentRole, BaseAgent

logger = logging.getLogger(__name__)


class SpatialReviewerAgent(BaseAgent):
    """
    空间审查 Agent — 防止空间幻觉

    校验项：
    1. 拓扑一致性：节点关系是否与实际空间结构匹配
    2. 矢量精度：坐标、距离、面积是否在合理范围
    3. 语义合理性：分类标签是否与空间特征一致
    4. 完整性检查：必要的输出字段是否齐全
    """

    def __init__(self, llm_client: Optional[Any] = None, **kwargs):
        super().__init__(role=AgentRole.SPATIAL_REVIEWER, llm_client=llm_client, **kwargs)

    @property
    def role_prompt(self) -> str:
        return (
            "You are the Spatial Reviewer Agent. You verify spatial analysis quality:\n"
            "1. Topological consistency: node relationships match actual spatial structure\n"
            "2. Vector accuracy: coordinates, distances, areas within reasonable ranges\n"
            "3. Semantic validity: classification labels consistent with spatial features\n"
            "4. Completeness: all required output fields present\n\n"
            "Output a quality_score (0-1) and list of issues found."
        )

    async def execute(self, message: AgentMessage) -> AgentMessage:
        self.log_message(message)
        results = message.payload

        # 规则校验
        issues = self._rule_based_review(results)

        # LLM 辅助审查（可选）
        if self.llm_client is not None and not issues:
            llm_issues = await self._llm_review(results)
            issues.extend(llm_issues)

        quality_score = max(0.0, 1.0 - len(issues) * 0.15)
        passed = quality_score >= 0.6

        return AgentMessage(
            sender=self.role,
            receiver=AgentRole.MANAGER,
            msg_type="review",
            payload={
                "quality_score": quality_score,
                "passed": passed,
                "issues": issues,
                "recommendation": "accept" if passed else "revise",
            },
            trace_id=message.trace_id,
        )

    def _rule_based_review(self, results: Dict) -> list[str]:
        """规则校验"""
        issues = []
        subtask_results = results.get("subtask_results", {})

        for st_id, st_data in subtask_results.items():
            if st_data.get("status") == "failed":
                issues.append(f"Subtask {st_id} failed: {st_data.get('result', {}).get('error', 'unknown')}")

            result = st_data.get("result", {})
            if isinstance(result, dict):
                # 坐标范围检查
                for key in ("latitude", "lat"):
                    val = result.get(key)
                    if val is not None and not (-90 <= float(val) <= 90):
                        issues.append(f"{st_id}: latitude {val} out of range [-90, 90]")
                for key in ("longitude", "lon", "lng"):
                    val = result.get(key)
                    if val is not None and not (-180 <= float(val) <= 180):
                        issues.append(f"{st_id}: longitude {val} out of range [-180, 180]")

        completed = results.get("completed", 0)
        total = results.get("total", 1)
        if total > 0 and completed / total < 0.5:
            issues.append(f"Low completion rate: {completed}/{total}")

        return issues

    async def _llm_review(self, results: Dict) -> list[str]:
        """LLM 辅助审查"""
        import json

        prompt = (
            f"{self.role_prompt}\n\n"
            f"Review these results:\n{json.dumps(results, ensure_ascii=False, default=str)[:3000]}\n\n"
            "List any spatial inconsistencies as a JSON array of strings. "
            "Return [] if no issues."
        )
        try:
            response = await self.call_llm(prompt)
            return json.loads(response) if response.strip().startswith("[") else []
        except Exception:
            return []


class HumanCheckpointAgent(BaseAgent):
    """
    人机协作 Agent — 6个决策检查点

    DP-1: Task interpretation & scoping
    DP-2: Data source validation
    DP-3: Spatial representation review
    DP-4: Intervention proposal selection
    DP-5: Parameter tuning
    DP-6: Result interpretation & narrative

    三种交互模式：
    - guided:    每个 DP 都暂停等待人工确认
    - supervisory: 自动执行 + 事后检查点
    - autonomous:  完全自动（不暂停）
    """

    def __init__(
        self,
        interaction_mode: str = "autonomous",
        human_callback: Optional[Callable] = None,
        **kwargs,
    ):
        super().__init__(role=AgentRole.HUMAN_CHECKPOINT, **kwargs)
        self.interaction_mode = interaction_mode  # guided / supervisory / autonomous
        self.human_callback = human_callback
        self._checkpoint_log: list[Dict] = []

    @property
    def role_prompt(self) -> str:
        return (
            "You are the Human Checkpoint Agent. You manage decision points (DP-1 to DP-6) "
            "where human experts can review and adjust the analysis workflow."
        )

    async def execute(self, message: AgentMessage) -> AgentMessage:
        self.log_message(message)
        checkpoint_id = message.payload.get("checkpoint_id", "DP-0")
        data = message.payload.get("data", {})

        decision = await self._process_checkpoint(checkpoint_id, data)

        self._checkpoint_log.append({
            "checkpoint": checkpoint_id,
            "mode": self.interaction_mode,
            "decision": decision,
        })

        return AgentMessage(
            sender=self.role,
            receiver=AgentRole.MANAGER,
            msg_type="feedback",
            payload={"checkpoint_id": checkpoint_id, "decision": decision},
            trace_id=message.trace_id,
        )

    async def _process_checkpoint(self, checkpoint_id: str, data: Dict) -> Dict:
        """根据交互模式处理检查点"""
        if self.interaction_mode == "autonomous":
            return {"action": "approve", "reason": "autonomous mode"}

        if self.interaction_mode == "guided" and self.human_callback:
            return await self._ask_human(checkpoint_id, data)

        if self.interaction_mode == "supervisory":
            # 事后记录，不阻塞
            logger.info(f"Supervisory checkpoint {checkpoint_id}: auto-approved, logged for review")
            return {"action": "approve", "reason": "supervisory auto-approve"}

        return {"action": "approve", "reason": "no callback configured"}

    async def _ask_human(self, checkpoint_id: str, data: Dict) -> Dict:
        """请求人工输入"""
        if self.human_callback is None:
            return {"action": "approve", "reason": "no callback"}

        import asyncio

        if asyncio.iscoroutinefunction(self.human_callback):
            return await self.human_callback(checkpoint_id, data)
        return self.human_callback(checkpoint_id, data)
