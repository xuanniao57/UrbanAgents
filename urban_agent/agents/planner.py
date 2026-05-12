"""
Planner Agent — Planning Layer
参考 GeoAgent 的 Planner：两阶段工作流（任务解析 + 任务规划）

职责：
1. 解析用户任务 → 复杂度评级 + 数据需求 + 能力需求
2. 拆分子任务 → 依赖排序 + 分配角色
3. 输出结构化 ExecutionPlan
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from ..capabilities import CapabilityRegistry, get_default_capability_registry
from ..feedback_memory import get_default_feedback_memory

from .base import (
    AgentMessage,
    AgentRole,
    BaseAgent,
    ExecutionPlan,
    SubTask,
)

logger = logging.getLogger(__name__)

def _declared_data_names(task: Optional[Dict[str, Any]]) -> list[str]:
    if not task:
        return ["declared_data_sources"]
    resources = task.get("data_resources")
    if isinstance(resources, dict) and resources:
        return [str(key) for key in resources]
    if isinstance(resources, list) and resources:
        names = []
        for item in resources:
            if isinstance(item, dict):
                names.append(str(item.get("name") or item.get("id") or item.get("type") or "data_resource"))
            else:
                names.append(str(item))
        return names
    return ["declared_data_sources"]


class PlannerAgent(BaseAgent):
    """
    规划层 Agent

    GeoAgent 消融实验显示：去掉 Planning Layer → -35.38%
    因此本 Agent 是架构中最关键的组件之一。
    """

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        capability_registry: Optional[CapabilityRegistry] = None,
        feedback_memory: Optional[Any] = None,
        **kwargs,
    ):
        super().__init__(role=AgentRole.PLANNER, llm_client=llm_client, **kwargs)
        self.capability_registry = capability_registry or get_default_capability_registry()
        self.feedback_memory = feedback_memory or get_default_feedback_memory()

    @property
    def role_prompt(self) -> str:
        return (
            "You are the Planner Agent for UrbanAgent, an urban spatial analysis system.\n"
            "Your role:\n"
            "1. Parse user tasks into structured specifications\n"
            "2. Assess complexity (basic / intermediate / advanced)\n"
            "3. Decompose into subtasks with dependencies\n"
            "4. Assign each subtask to the appropriate worker role\n"
            "5. Select method-level capabilities before choosing software backends\n\n"
            "Available worker roles:\n"
            "- PERCEPTION: Multi-source data acquisition (OSM, remote sensing, street view, trajectory)\n"
            "- ANALYST: Spatial reasoning, pattern analysis, quantitative computation\n"
            "- CARTOGRAPHER: SVG overlay, GeoJSON generation, map visualization\n"
            "- REPORTER: Result integration, narrative generation, report formatting\n\n"
            "Capabilities are disclosed progressively: use the compact capability cards for planning, "
            "and request full invocation schemas only for selected methods. "
            "Output a structured JSON execution plan."
        )

    async def execute(self, message: AgentMessage) -> AgentMessage:
        """
        两阶段规划：
        Stage 1: 任务解析 — 复杂度 + 数据需求 + 能力选择
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
        task_description = task.get("description", task.get("question", str(task)))
        capability_context = self.capability_registry.select_for_task(task)
        feedback_context = self.feedback_memory.select_for_task(task)

        # 如果有 LLM，用 LLM 做智能解析
        if self.llm_client is not None:
            prompt = (
                f"{self.role_prompt}\n\n"
                f"--- TASK ---\n{json.dumps(task, ensure_ascii=False, default=str)}\n\n"
                f"--- CAPABILITY CARDS (LEVEL 1) ---\n{json.dumps(capability_context['level1_cards'], ensure_ascii=False, default=str)}\n\n"
                f"--- REUSABLE FEEDBACK LESSONS ---\n{json.dumps(feedback_context['lessons'], ensure_ascii=False, default=str)}\n\n"
                "Analyze this task and output JSON with keys:\n"
                '  "complexity": "basic"|"intermediate"|"advanced",\n'
                '  "workflow_profile": a short adaptive workflow label,\n'
                '  "required_data": list of data types needed,\n'
                '  "selected_capabilities": list of capability names needed,\n'
                '  "subtasks": list of objects, each with:\n'
                '    "objective": task description string,\n'
                '    "assigned_role": "perception"|"analyst"|"cartographer"|"reporter"\n'
                'Choose the number of subtasks and their roles based on task complexity.\n'
                'A typical urban analysis uses 3-5 subtasks: data perception → spatial analysis → cartographic output → report synthesis.\n'
            )
            try:
                response = await self.call_llm(prompt)
                parsed = json.loads(response)
                # Normalize: accept both "subtasks" (new) and "subtask_descriptions" (legacy)
                if "subtasks" not in parsed and "subtask_descriptions" in parsed:
                    raw = parsed.pop("subtask_descriptions")
                    parsed["subtasks"] = [
                        d if isinstance(d, dict) else {"objective": str(d), "assigned_role": None}
                        for d in raw
                    ]
                parsed.setdefault("subtasks", [])
                parsed.setdefault("selected_capabilities", capability_context["selected_names"])
                parsed["capability_context"] = capability_context
                parsed["feedback_context"] = feedback_context
                return parsed
            except Exception:
                logger.warning("LLM task parsing failed, falling back to rule-based")

        # 规则兜底
        analysis = self._rule_based_parse(task_description, task)
        analysis["capability_context"] = capability_context
        analysis["feedback_context"] = feedback_context
        analysis.setdefault("selected_capabilities", capability_context["selected_names"])
        return analysis

    def _rule_based_parse(self, description: str, task: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """规则兜底的任务解析"""
        task = task or {}
        stage = str(task.get("stage") or "").strip().lower()
        workflow_profile = "adaptive_urban_analysis"

        if stage == "single_district_single_indicator":
            return {
                "complexity": "basic",
                "workflow_profile": workflow_profile,
                "required_data": _declared_data_names(task),
                "subtasks": [
                    {"objective": "Inventory declared data sources and identify one analysis unit", "assigned_role": "perception"},
                    {"objective": "Select one feasible indicator after checking source authority and data support", "assigned_role": "analyst"},
                    {"objective": "Compute or proxy the selected indicator with traceable inputs", "assigned_role": "analyst"},
                    {"objective": "Package result, validation notes, and correction hooks", "assigned_role": "reporter"},
                ],
            }

        if stage == "single_district_multi_indicator":
            return {
                "complexity": "intermediate",
                "workflow_profile": workflow_profile,
                "required_data": _declared_data_names(task),
                "subtasks": [
                    {"objective": "Inventory declared data sources and select one analysis unit", "assigned_role": "perception"},
                    {"objective": "Classify candidate indicators by computable, proxy-only, or unsupported status", "assigned_role": "analyst"},
                    {"objective": "Compute available and proxy indicators with traceable evidence fields", "assigned_role": "analyst"},
                    {"objective": "Prepare inspectable GIS layers, charts, or tables for review", "assigned_role": "cartographer"},
                    {"objective": "Package limitations and structured correction hooks", "assigned_role": "reporter"},
                ],
            }

        if stage == "multi_district_multi_indicator":
            return {
                "complexity": "advanced",
                "workflow_profile": workflow_profile,
                "required_data": _declared_data_names(task),
                "subtasks": [
                    {"objective": "Inventory and validate declared data sources across analysis units", "assigned_role": "perception"},
                    {"objective": "Design comparable indicator computation rules across units", "assigned_role": "analyst"},
                    {"objective": "Batch-compute available and proxy indicators with exception handling", "assigned_role": "analyst"},
                    {"objective": "Prepare comparable GIS layers, tables, and diagnostics", "assigned_role": "cartographer"},
                    {"objective": "Package cross-unit limitations and correction hooks", "assigned_role": "reporter"},
                ],
            }

        # 复杂度启发式
        complexity = "basic"
        description_lower = description.lower()
        if any(kw in description_lower for kw in ["compare", "multi", "across", "temporal", "对比", "多", "跨", "时间", "趋势", "综合"]):
            complexity = "intermediate"
        if any(kw in description_lower for kw in ["optimize", "plan", "design", "simulate", "train", "model", "优化", "规划", "设计", "模拟", "训练", "模型", "建议", "方案"]):
            complexity = "advanced"

        # 默认子任务模板（complexity 自适应）
        subtasks = [
            {"objective": "Collect task-relevant city data and spatial context", "assigned_role": "perception"},
            {"objective": "Analyze spatial patterns, constraints, and task-specific indicators", "assigned_role": "analyst"},
            {"objective": "Prepare cartographic layers and visual outputs", "assigned_role": "cartographer"},
            {"objective": "Synthesize findings, caveats, and actionable recommendations", "assigned_role": "reporter"},
        ]
        if complexity == "basic":
            subtasks = subtasks[:2]  # perception + analyst only for simple tasks
        elif complexity == "intermediate":
            subtasks = subtasks[:3]  # + cartographer
        return {
            "complexity": complexity,
            "workflow_profile": workflow_profile,
            "required_data": ["osm"],
            "subtasks": subtasks,
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
        workflow_profile = analysis.get("workflow_profile", "adaptive_urban_analysis")
        # Support both new structured subtasks and legacy subtask_descriptions
        subtask_items = analysis.get("subtasks") or [
            {"objective": desc, "assigned_role": None}
            for desc in analysis.get("subtask_descriptions", ["analysis"])
        ]
        capability_context = analysis.get("capability_context", {})
        feedback_context = analysis.get("feedback_context", {})
        task_with_capabilities = dict(task)
        if capability_context:
            task_with_capabilities["capability_context"] = capability_context
        if feedback_context:
            task_with_capabilities["feedback_context"] = feedback_context

        subtasks: list[SubTask] = []
        prev_id: Optional[str] = None

        for i, item in enumerate(subtask_items):
            desc = item["objective"] if isinstance(item, dict) else str(item)
            role_str = (item.get("assigned_role") if isinstance(item, dict) else None) or ""
            role_lower = str(role_str).lower()
            if "perception" in role_lower:
                role = AgentRole.PERCEPTION
            elif "cartographer" in role_lower:
                role = AgentRole.CARTOGRAPHER
            elif "reporter" in role_lower:
                role = AgentRole.REPORTER
            elif "analyst" in role_lower:
                role = AgentRole.ANALYST
            else:
                role = self._assign_role(desc)
            st_id = f"{plan_id}_st{i}"
            subtasks.append(
                SubTask(
                    subtask_id=st_id,
                    objective=desc,
                    assigned_role=role,
                    input_data=dict(task_with_capabilities),
                    dependencies=[prev_id] if prev_id else [],
                    expected_output=f"Result of {desc}",
                )
            )
            prev_id = st_id

        return ExecutionPlan(
            plan_id=plan_id,
            original_task=task_with_capabilities,
            complexity=complexity,
            workflow_profile=workflow_profile,
            subtasks=subtasks,
            execution_order=[st.subtask_id for st in subtasks],
        )

    @staticmethod
    def _assign_role(description: str) -> AgentRole:
        """根据子任务描述分配 Worker 角色"""
        desc_lower = description.lower()
        perception_phrases = [
            "data acquisition",
            "acquire data",
            "collect data",
            "collect task-relevant city data",
            "fetch data",
            "ingest data",
            "perception",
            "openstreetmap",
            "osm",
            "remote sensing",
            "street view",
            "trajectory",
            "survey",
        ]
        if any(kw in desc_lower for kw in perception_phrases):
            return AgentRole.PERCEPTION
        if any(kw in desc_lower for kw in ["report", "summary", "narrative", "document", "synthesize", "finding", "recommendation", "报告", "总结"]):
            return AgentRole.REPORTER
        if any(kw in desc_lower for kw in ["visual", "svg", "map", "carto", "chart", "plot"]):
            return AgentRole.CARTOGRAPHER
        return AgentRole.ANALYST

    @staticmethod
    def _plan_to_dict(plan: ExecutionPlan) -> Dict[str, Any]:
        """序列化 ExecutionPlan"""
        return {
            "plan_id": plan.plan_id,
            "complexity": plan.complexity,
            "workflow_profile": plan.workflow_profile,
            "capability_context": plan.original_task.get("capability_context", {}),
            "feedback_context": plan.original_task.get("feedback_context", {}),
            "subtasks": [
                {
                    "subtask_id": st.subtask_id,
                    "objective": st.objective,
                    "assigned_role": st.assigned_role.value,
                    "input_data": dict(st.input_data),
                    "dependencies": st.dependencies,
                    "expected_output": st.expected_output,
                }
                for st in plan.subtasks
            ],
            "execution_order": plan.execution_order,
        }
