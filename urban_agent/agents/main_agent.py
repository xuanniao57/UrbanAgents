"""Conversation-facing MainAgent for intent, routing, and direct answers."""

from __future__ import annotations

from datetime import datetime
import json
import logging
from typing import Any, Dict

from .base import AgentMessage, AgentRole, BaseAgent

logger = logging.getLogger(__name__)


DIRECT_RESPONSE_MODES = {"chat_advice", "research_design", "clarify"}


class MainAgent(BaseAgent):
    """Owns task interpretation before workers, memories, or GIS policies run."""

    def __init__(self, llm_client: Any = None, **kwargs: Any):
        super().__init__(role=AgentRole.MAIN, llm_client=llm_client, **kwargs)

    @property
    def role_prompt(self) -> str:
        return (
            "You are the conversation-facing MainAgent for UrbanAgent. "
            "First understand the user's intent, then decide whether to answer directly "
            "or invoke execution workers. You know the available worker contracts, "
            "capability cards, research memories, review policies, and prior experience. "
            "Use that context as optional evidence for your decision, not as a fixed script. "
            "You may answer directly, ask for clarification, or launch worker execution. "
            "Do not let old case memories, GIS policies, or capability cards override the "
            "user's actual request."
        )

    async def execute(self, message: AgentMessage) -> AgentMessage:
        self.log_message(message)
        task = message.payload
        decision = await self.interpret(task)
        if not decision.get("should_execute"):
            answer = await self.answer_direct(task, decision)
            payload = {**decision, "answer": answer}
        else:
            payload = decision
        return AgentMessage(
            sender=self.role,
            receiver=AgentRole.MANAGER,
            msg_type="main_decision",
            payload=payload,
            trace_id=message.trace_id,
        )

    async def interpret(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Return an execution decision. Prefer LLM judgment, use rules as fallback."""
        main_context = _main_context(task)
        if self.llm_client is not None:
            task_for_prompt = _task_without_bulk_context(task)
            prompt = (
                f"{self.role_prompt}\n\n"
                f"Current task JSON:\n{json.dumps(task_for_prompt, ensure_ascii=False, default=str, indent=2)}\n\n"
                f"Available worker / ReAct contracts:\n{json.dumps(_worker_contracts(), ensure_ascii=False, indent=2)}\n\n"
                f"Capability index (level 0 only):\n{json.dumps(main_context.get('capability_index', {}), ensure_ascii=False, default=str, indent=2)}\n\n"
                f"Feedback/workflow memory index (summaries only):\n{json.dumps(main_context.get('feedback_index', {}), ensure_ascii=False, default=str, indent=2)}\n\n"
                f"Research-design memory index (summaries only):\n{json.dumps(main_context.get('research_index', {}), ensure_ascii=False, default=str, indent=2)}\n\n"
                f"Conversation/runtime memory index:\n{json.dumps(main_context.get('memory_index', {}), ensure_ascii=False, default=str, indent=2)}\n\n"
                "Classify the task. Return strict JSON only with keys:\n"
                '  "response_mode": "chat_advice" | "research_design" | "clarify" | "execute" | "mixed_execute",\n'
                '  "should_execute": true | false,\n'
                '  "reason": short explanation,\n'
                '  "selected_capabilities": list of capability names you would use if executing,\n'
                '  "memory_notes": list of relevant memories and whether they apply,\n'
                '  "missing_inputs": list of inputs that would be needed before execution,\n'
                '  "answer_strategy": short plan for how to respond.\n\n'
                "Reason from the progressively disclosed context. The WorkerAgent path follows a ReAct-style loop: "
                "plan a bounded subtask, act with allowed tools, observe artifacts/evidence, then "
                "return results for review and synthesis. Use it when it materially helps the user. "
                "For open-ended research questions, you can still use memories and capability cards "
                "to craft a better answer, but do not launch GIS execution unless execution is actually requested or feasible."
            )
            try:
                parsed = _parse_json_object(await self.call_llm(prompt))
                if parsed:
                    return _normalize_decision(parsed, task)
            except Exception as error:
                logger.warning("MainAgent LLM intent classification failed: %s", error)

        return _fallback_decision(task)

    async def answer_direct(self, task: Dict[str, Any], decision: Dict[str, Any]) -> str:
        """Generate a direct conversational answer without worker orchestration."""
        question = str(task.get("question") or task.get("description") or task.get("text") or task)
        main_context = _main_context(task)
        if self.llm_client is not None:
            prompt = (
                f"{self.role_prompt}\n\n"
                f"User request: {question}\n"
                f"Routing decision: {json.dumps(decision, ensure_ascii=False, default=str)}\n\n"
                f"Useful capability index:\n{json.dumps(main_context.get('capability_index', {}), ensure_ascii=False, default=str, indent=2)}\n\n"
                f"Relevant workflow/policy memory summaries to use only when applicable:\n{json.dumps(main_context.get('feedback_index', {}).get('lessons', []), ensure_ascii=False, default=str, indent=2)}\n\n"
                f"Relevant research-design memory summaries to use only when applicable:\n{json.dumps(main_context.get('research_index', {}).get('lessons', []), ensure_ascii=False, default=str, indent=2)}\n\n"
                "Answer as a helpful urban research assistant. Be concrete and useful. "
                "Do not claim that data was fetched, layers were generated, or metrics were computed "
                "unless they are present in the task input. If execution would be useful later, "
                "briefly name the inputs needed."
            )
            try:
                text = (await self.call_llm(prompt)).strip()
                if text:
                    return text
            except Exception as error:
                logger.warning("MainAgent direct answer failed: %s", error)

        return _fallback_direct_answer(question, decision)


def _parse_json_object(text: str) -> Dict[str, Any]:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}") + 1
    if start < 0 or end <= start:
        return {}
    data = json.loads(cleaned[start:end])
    return data if isinstance(data, dict) else {}


def _normalize_decision(decision: Dict[str, Any], task: Dict[str, Any]) -> Dict[str, Any]:
    mode = str(decision.get("response_mode") or "").strip().lower()
    if mode not in DIRECT_RESPONSE_MODES | {"execute", "mixed_execute"}:
        mode = "execute" if decision.get("should_execute") else _fallback_decision(task)["response_mode"]
    should_execute = bool(decision.get("should_execute"))
    if mode in DIRECT_RESPONSE_MODES:
        should_execute = False
    if _has_execution_inputs(task) and mode != "clarify":
        should_execute = bool(decision.get("should_execute", True))
    return {
        "response_mode": mode,
        "should_execute": should_execute,
        "reason": str(decision.get("reason") or ""),
        "selected_capabilities": _string_list(decision.get("selected_capabilities")),
        "memory_notes": _string_list(decision.get("memory_notes")),
        "missing_inputs": _string_list(decision.get("missing_inputs")),
        "answer_strategy": str(decision.get("answer_strategy") or ""),
        "decided_at": datetime.now().isoformat(),
        "source": "main_agent",
    }


def _fallback_decision(task: Dict[str, Any]) -> Dict[str, Any]:
    question = str(task.get("question") or task.get("description") or task.get("text") or task)
    text = question.lower()
    has_inputs = _has_execution_inputs(task)
    asks_for_execution = _looks_like_execution_request(text)
    asks_for_research_design = _looks_like_research_design(text)

    if asks_for_research_design and not has_inputs and not asks_for_execution:
        mode = "research_design"
        execute = False
        reason = "Open-ended research design request without declared AOI/data execution inputs."
    elif has_inputs or asks_for_execution:
        mode = "execute"
        execute = True
        reason = "The task includes execution inputs or asks for concrete data/GIS work."
    else:
        mode = "chat_advice"
        execute = False
        reason = "Conversational request; answer directly before considering tools."

    return {
        "response_mode": mode,
        "should_execute": execute,
        "reason": reason,
        "selected_capabilities": [],
        "memory_notes": [],
        "missing_inputs": [] if execute else ["AOI or place", "data sources", "target outcome variable"] if mode == "research_design" else [],
        "answer_strategy": "Answer directly with concepts, variables, data options, and next-step choices.",
        "decided_at": datetime.now().isoformat(),
        "source": "fallback_rules",
    }


def _has_execution_inputs(task: Dict[str, Any]) -> bool:
    meaningful_keys = (
        "bbox",
        "aoi",
        "aoi_path",
        "input_path",
        "data_resources",
        "dataset_cards",
        "city_data",
        "layers",
        "geojson",
        "shapefile",
    )
    for key in meaningful_keys:
        value = task.get(key)
        if value:
            return True
    return False


def _main_context(task: Dict[str, Any]) -> Dict[str, Any]:
    context = task.get("main_context")
    if isinstance(context, dict):
        return context
    return {
        "capability_index": task.get("capability_context", {}),
        "feedback_index": task.get("feedback_context", {}),
        "research_index": task.get("research_context", {}),
        "memory_index": task.get("memory_context", {}),
    }


def _task_without_bulk_context(task: Dict[str, Any]) -> Dict[str, Any]:
    bulky_keys = {
        "main_context",
        "memory_context",
        "feedback_context",
        "research_context",
        "capability_context",
        "city_data",
    }
    compact = {key: value for key, value in task.items() if key not in bulky_keys}
    for key in ("data_resources", "dataset_cards", "layers"):
        if key in compact:
            compact[key] = _truncate_value(compact[key], 4000)
    return compact


def _truncate_value(value: Any, limit: int) -> Any:
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= limit:
        return value
    return {"_truncated": True, "preview": text[:limit]}


def _worker_contracts() -> Dict[str, Any]:
    return {
        "main_agent": {
            "responsibility": "Interpret intent, choose direct answer vs execution, plan worker use, synthesize final answer.",
            "authority": "Owns task meaning and final user-facing response.",
        },
        "worker_agent_path": {
            "pattern": "ReAct-style bounded execution: plan subtask, act with allowed tools, observe evidence/artifacts, report limitations.",
            "current_compatible_roles": [
                {
                    "role": "perception",
                    "use_when": "Data acquisition, source inventory, AOI/layer ingestion, OSM/remote-sensing/street-view preparation.",
                },
                {
                    "role": "analyst",
                    "use_when": "Spatial reasoning, metrics, modeling, research variable construction, quantitative analysis.",
                },
                {
                    "role": "cartographer",
                    "use_when": "Map previews, GeoJSON/GeoPackage exports, layer styling, spatialized metric artifacts.",
                },
                {
                    "role": "reporter",
                    "use_when": "Synthesize worker outputs into a report after evidence exists.",
                },
            ],
        },
        "reviewer_agent": {
            "responsibility": "Review evidence, fit to user intent, missing inputs, policy violations, and whether worker results should be revised.",
            "note": "Review feedback returns to MainAgent; reflection/memory writing is a background concern.",
        },
    }


def _looks_like_research_design(text: str) -> bool:
    markers = (
        "which factors",
        "what factors",
        "influence",
        "how to study",
        "research design",
        "research framework",
        "variables",
        "hypothesis",
        "urban vitality",
        "historic district",
        "我希望研究",
        "想研究",
        "哪些",
        "什么因素",
        "影响因素",
        "研究框架",
        "变量",
        "假设",
        "怎么研究",
        "如何研究",
        "研究设计",
        "城市活力",
        "历史街区",
        "历史感",
        "主观感知",
    )
    return any(marker in text for marker in markers)


def _looks_like_execution_request(text: str) -> bool:
    execution_markers = (
        "compute",
        "calculate",
        "fetch",
        "download",
        "export",
        "generate map",
        "create geojson",
        "shapefile",
        "geopackage",
        "osm",
        "overpass",
        "run analysis",
        "可视化",
        "导出",
        "计算",
        "获取",
        "下载",
        "生成地图",
        "出图",
        "图层",
        "geojson",
        "gis",
    )
    return any(marker in text for marker in execution_markers)


def _fallback_direct_answer(question: str, decision: Dict[str, Any]) -> str:
    text = question.lower()
    if "城市活力" in question or ("urban vitality" in text and "built" in text):
        return (
            "可以先把这个问题作为研究设计来展开，而不是马上进入 GIS 执行。\n\n"
            "城市活力通常要先定义因变量，例如人流强度、消费/点评活跃度、POI 营业活跃度、夜间灯光、街道停留行为、手机信令或社交媒体活动。建成环境因素可以从几组变量入手：\n\n"
            "1. 功能混合：POI 多样性、土地利用混合度、居住-就业-消费平衡、主导功能占比。\n"
            "2. 开发强度：建筑密度、容积率、建筑覆盖率、街区紧凑度、人口或岗位密度。\n"
            "3. 路网与可达性：路网密度、交叉口密度、街区尺度、步行可达性、公交/地铁可达性。\n"
            "4. 街道空间品质：界面连续性、底层商业比例、绿视率、天空开敞度、街道宽高比、慢行友好度。\n"
            "5. 设施与公共空间：公共服务设施、商业设施、公园广场、开放空间的数量、距离和服务范围。\n"
            "6. 区位与邻近关系：距离中心区、轨道站点、就业中心、滨水空间、历史街区或大型商圈的距离。\n\n"
            "比较稳妥的路径是：先明确活力代理指标，再构建多尺度建成环境变量，之后用相关分析、OLS/空间回归、GWR/MGWR、随机森林或因果推断方法检验影响关系。"
            "如果后续要让 UrbanAgent 进入实证执行，需要补充研究区 AOI、时间范围、活力代理数据和可用的建成环境数据源。"
        )

    if "历史街区" in question or "历史感" in question or "historic district" in text:
        return (
            "这个问题更适合先作为研究框架来组织，而不是直接启动 GIS 执行。\n\n"
            "可以把“历史街区风貌”作为建成环境与景观感知变量，把“游客历史感认知”作为感知结果变量。一个可操作的框架是：\n\n"
            "1. 风貌物质要素：建筑年代、传统建筑比例、立面连续性、街巷尺度、材料色彩、屋顶/檐口/门窗等历史形态特征。\n"
            "2. 空间场景要素：街道围合度、步行连续性、视线通廊、节点空间、文化遗产点密度、商业更新强度。\n"
            "3. 符号与叙事要素：牌匾、导览系统、历史说明、地方故事、非遗展示、老字号与生活场景保留。\n"
            "4. 游客认知结果：历史真实性感知、地方依恋、文化理解、沉浸感、记忆点、游览满意度与再访意愿。\n"
            "5. 空间单元设计：如果只有少量历史街区样本，不宜直接做复杂机器学习；可以考虑 200m x 200m 网格、街段或街坊，把建成环境指标和小红书/社媒感知数据落到同一单元。\n"
            "6. 数据与模型：问卷/访谈可直接测认知，社媒文本与图像可构造历史感得分，街景图像、POI、历史建筑名录和空间句法可测风貌；模型上可用回归、空间回归、随机森林、SEM 或多层模型。\n\n"
            "后续如果进入实证，需要明确具体历史街区 AOI、可用社媒或游客样本、街景/建筑/POI 数据，以及你要检验的是相关关系、机制路径还是评价模型。"
        )

    missing = decision.get("missing_inputs") or []
    suffix = f"\n\n如果要进入实证执行，还需要：{', '.join(missing)}。" if missing else ""
    return (
        "我会先把它作为开放咨询问题处理：明确研究对象、可观测指标、可用数据、分析方法和可能的局限，"
        "而不是默认启动 GIS 数据抓取或制图流程。"
        + suffix
    )


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if value:
        return [str(value)]
    return []
