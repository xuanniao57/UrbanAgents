"""
Planner Agent — Planning Layer
参考 GeoAgent 的 Planner：两阶段工作流（任务解析 + 任务规划）

职责：
1. 解析用户任务 → 复杂度评级 + 任务类别
2. 拆分子任务 → 依赖排序 + 分配角色
3. 输出结构化 ExecutionPlan
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from .base import (
    AgentMessage,
    AgentRole,
    BaseAgent,
    ExecutionPlan,
    SubTask,
)

logger = logging.getLogger(__name__)

# 8 种城市分析任务类型 (与 CityBench 对齐)
TASK_CATEGORIES = {
    "population_prediction",
    "object_detection",
    "geolocation",
    "geoqa",
    "mobility_prediction",
    "traffic_signal",
    "outdoor_navigation",
    "urban_exploration",
}


class PlannerAgent(BaseAgent):
    """
    规划层 Agent

    GeoAgent 消融实验显示：去掉 Planning Layer → -35.38%
    因此本 Agent 是架构中最关键的组件之一。
    """

    def __init__(self, llm_client: Optional[Any] = None, **kwargs):
        super().__init__(role=AgentRole.PLANNER, llm_client=llm_client, **kwargs)

    @property
    def role_prompt(self) -> str:
        return (
            "You are the Planner Agent for UrbanAgent, an urban spatial analysis system.\n"
            "Your role:\n"
            "1. Parse user tasks into structured specifications\n"
            "2. Assess complexity (basic / intermediate / advanced)\n"
            "3. Decompose into subtasks with dependencies\n"
            "4. Assign each subtask to the appropriate worker role\n\n"
            "Available worker roles:\n"
            "- PERCEPTION: Multi-source data acquisition (OSM, remote sensing, street view, trajectory)\n"
            "- ANALYST: Spatial reasoning, pattern analysis, quantitative computation\n"
            "- CARTOGRAPHER: SVG overlay, GeoJSON generation, map visualization\n"
            "- REPORTER: Result integration, narrative generation, report formatting\n\n"
            "Output a structured JSON execution plan."
        )

    async def execute(self, message: AgentMessage) -> AgentMessage:
        """
        两阶段规划：
        Stage 1: 任务解析 — 复杂度 + 类别 + 数据需求
        Stage 2: 任务规划 — 子任务列表 + 依赖图 + 执行顺序
        """
        task = message.payload
        trace_id = message.trace_id
        self.log_message(message)

        # Stage 1: 任务解析
        task_analysis = await self._parse_task(task)

        # Stage 2: 子任务拆分与排序
        plan = await self._plan_subtasks(task, task_analysis, trace_id)

        result_msg = AgentMessage(
            sender=AgentRole.PLANNER,
            receiver=AgentRole.MANAGER,
            msg_type="task_plan",
            payload={"execution_plan": self._plan_to_dict(plan)},
            trace_id=trace_id,
        )
        self.log_message(result_msg)
        return result_msg

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    async def _parse_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Stage 1: 任务解析"""
        task_type = task.get("task_type", "")
        task_description = task.get("description", task.get("question", str(task)))

        # 如果有 LLM，用 LLM 做智能解析
        if self.llm_client is not None:
            prompt = (
                f"{self.role_prompt}\n\n"
                f"--- TASK ---\n{json.dumps(task, ensure_ascii=False, default=str)}\n\n"
                "Analyze this task and output JSON with keys:\n"
                '  "complexity": "basic"|"intermediate"|"advanced",\n'
                '  "category": one of the 8 CityBench task types,\n'
                '  "required_data": list of data types needed,\n'
                '  "subtask_descriptions": list of subtask objective strings\n'
            )
            try:
                response = await self.call_llm(prompt)
                return json.loads(response)
            except Exception:
                logger.warning("LLM task parsing failed, falling back to rule-based")

        # 规则兜底
        return self._rule_based_parse(task_type, task_description)

    def _rule_based_parse(self, task_type: str, description: str) -> Dict[str, Any]:
        """规则兜底的任务解析"""
        category = task_type if task_type in TASK_CATEGORIES else "geoqa"

        # 复杂度启发式
        complexity = "basic"
        if any(kw in description.lower() for kw in ["compare", "multi", "across", "temporal"]):
            complexity = "intermediate"
        if any(kw in description.lower() for kw in ["optimize", "plan", "design", "simulate"]):
            complexity = "advanced"

        # 默认子任务模板
        subtasks = ["data_acquisition", "analysis", "visualization", "report"]
        if complexity == "basic":
            subtasks = ["data_acquisition", "analysis"]

        return {
            "complexity": complexity,
            "category": category,
            "required_data": ["osm"],
            "subtask_descriptions": subtasks,
        }

    async def _plan_subtasks(
        self,
        task: Dict[str, Any],
        analysis: Dict[str, Any],
        trace_id: str,
    ) -> ExecutionPlan:
        """Stage 2: 生成子任务与执行计划"""
        from datetime import datetime

        plan_id = f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        complexity = analysis.get("complexity", "basic")
        category = analysis.get("category", "geoqa")
        subtask_descs = analysis.get("subtask_descriptions", ["analysis"])

        subtasks: list[SubTask] = []
        prev_id: Optional[str] = None

        for i, desc in enumerate(subtask_descs):
            role = self._assign_role(desc)
            st_id = f"{plan_id}_st{i}"
            subtasks.append(
                SubTask(
                    subtask_id=st_id,
                    objective=desc,
                    assigned_role=role,
                    input_data=task if i == 0 else {},
                    dependencies=[prev_id] if prev_id else [],
                    expected_output=f"Result of {desc}",
                )
            )
            prev_id = st_id

        return ExecutionPlan(
            plan_id=plan_id,
            original_task=task,
            complexity=complexity,
            task_category=category,
            subtasks=subtasks,
            execution_order=[st.subtask_id for st in subtasks],
        )

    @staticmethod
    def _assign_role(description: str) -> AgentRole:
        """根据子任务描述分配 Worker 角色"""
        desc_lower = description.lower()
        if any(kw in desc_lower for kw in ["data", "acquisition", "perception", "fetch", "collect"]):
            return AgentRole.PERCEPTION
        if any(kw in desc_lower for kw in ["visual", "svg", "map", "carto", "chart", "plot"]):
            return AgentRole.CARTOGRAPHER
        if any(kw in desc_lower for kw in ["report", "summary", "narrative", "document"]):
            return AgentRole.REPORTER
        return AgentRole.ANALYST

    @staticmethod
    def _plan_to_dict(plan: ExecutionPlan) -> Dict[str, Any]:
        """序列化 ExecutionPlan"""
        return {
            "plan_id": plan.plan_id,
            "complexity": plan.complexity,
            "task_category": plan.task_category,
            "subtasks": [
                {
                    "subtask_id": st.subtask_id,
                    "objective": st.objective,
                    "assigned_role": st.assigned_role.value,
                    "dependencies": st.dependencies,
                    "expected_output": st.expected_output,
                }
                for st in plan.subtasks
            ],
            "execution_order": plan.execution_order,
        }
