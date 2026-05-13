"""Hermes MemoryProvider for UrbanAgent feedback and place memory."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .paths import DEFAULT_MEMORY_ROOT, ensure_paths

ensure_paths()

from agent.memory_provider import MemoryProvider


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _tokens(value: Any) -> set[str]:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return set(re.findall(r"[a-z0-9_\-]+|[\u4e00-\u9fff]+", text.lower()))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            records.append(item)
    return records


def _append_jsonl(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "record_id": payload.get("record_id") or f"urban_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
        "timestamp": datetime.now().isoformat(),
        **payload,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    return path


@dataclass
class FeedbackMemoryProvider:
    """Local feedback lesson store used by UrbanMemoryProvider."""

    root: Path

    @property
    def path(self) -> Path:
        return self.root / "feedback_memory" / "feedback_lessons.jsonl"

    def record(self, payload: dict[str, Any]) -> dict[str, Any]:
        summary = str(payload.get("summary") or payload.get("correction") or "Urban feedback lesson")
        triggers = payload.get("triggers") or []
        if isinstance(triggers, str):
            triggers = [triggers]
        record = {
            "memory_type": "feedback",
            "summary": summary,
            "triggers": [str(item) for item in triggers],
            "place": payload.get("place"),
            "correction": payload.get("correction"),
            "review_policy": payload.get("review_policy"),
            "payload": payload,
        }
        _append_jsonl(self.path, record)
        return record

    def search(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        return _rank_records(_read_jsonl(self.path), query, limit=limit)


@dataclass
class PlaceMemoryProvider:
    """Local place-context store used by UrbanMemoryProvider."""

    root: Path

    @property
    def path(self) -> Path:
        return self.root / "place_memory" / "place_context.jsonl"

    def record(self, payload: dict[str, Any]) -> dict[str, Any]:
        place = str(payload.get("place") or payload.get("location") or "unknown-place")
        record = {
            "memory_type": "place",
            "place": place,
            "summary": str(payload.get("summary") or payload.get("correction") or f"Context for {place}"),
            "triggers": [place.lower()],
            "payload": payload,
        }
        _append_jsonl(self.path, record)
        return record

    def search(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        return _rank_records(_read_jsonl(self.path), query, limit=limit)

    def context_for_place(self, place: str, *, limit: int = 5) -> list[dict[str, Any]]:
        records = _read_jsonl(self.path)
        lowered = place.lower()
        matches = [record for record in records if lowered in str(record.get("place", "")).lower() or lowered in json.dumps(record, ensure_ascii=False).lower()]
        return matches[-limit:]


@dataclass
class ResearchMemoryProvider:
    """Reusable urban research-design lessons, not hard-coded workflow rules."""

    root: Path

    @property
    def path(self) -> Path:
        return self.root / "research_memory" / "research_lessons.jsonl"

    def record(self, payload: dict[str, Any]) -> dict[str, Any]:
        summary = str(payload.get("summary") or payload.get("lesson") or "Urban research design lesson")
        triggers = payload.get("triggers") or []
        if isinstance(triggers, str):
            triggers = [triggers]
        record = {
            "memory_type": "research_design",
            "summary": summary,
            "triggers": [str(item) for item in triggers],
            "domain": payload.get("domain") or "urban_analysis",
            "method_hint": payload.get("method_hint"),
            "evidence_scope": payload.get("evidence_scope"),
            "caveats": payload.get("caveats") or [],
            "payload": payload,
        }
        _append_jsonl(self.path, record)
        return record

    def search(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        records = [*_builtin_research_lessons(), *_read_jsonl(self.path)]
        return _rank_records(records, query, limit=limit)

    def list(self, *, limit: int = 20) -> list[dict[str, Any]]:
        records = [*_builtin_research_lessons(), *_read_jsonl(self.path)]
        return records[-limit:]


class UrbanMemoryProvider(MemoryProvider):
    """Single Hermes external provider that composes feedback and place memory."""

    def __init__(self, root: str | Path | None = None) -> None:
        raw_root = root or os.getenv("URBAN_HERMES_MEMORY_ROOT") or DEFAULT_MEMORY_ROOT
        self.root = Path(raw_root).expanduser().resolve()
        self.feedback = FeedbackMemoryProvider(self.root)
        self.place = PlaceMemoryProvider(self.root)
        self.research = ResearchMemoryProvider(self.root)
        self._session_id = ""
        self._platform = ""
        self._initialized = False

    @property
    def name(self) -> str:
        return "urban_memory"

    def is_available(self) -> bool:
        return True

    def initialize(self, session_id: str, **kwargs: Any) -> None:
        self._session_id = session_id
        self._platform = str(kwargs.get("platform") or "local")
        self.root.mkdir(parents=True, exist_ok=True)
        self._initialized = True

    def system_prompt_block(self) -> str:
        return (
            "Urban memory provider is active. Before urban analysis, recall task-relevant "
            "research-design lessons, place context, and previous human corrections. Treat "
            "recalled lessons as professional cues, not as automatic facts or hard-coded rules. "
            "Store new reusable lessons when the user changes a spatial unit, data source, "
            "scale, stakeholder caveat, variable operationalization, or rerun instruction."
        )

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        feedback = self.feedback.search(query, limit=4)
        places = self.place.search(query, limit=4)
        research = self.research.search(query, limit=4)
        if not feedback and not places and not research:
            return ""
        payload = {
            "provider": self.name,
            "session_id": session_id or self._session_id,
            "research_design_lessons": research,
            "feedback_lessons": feedback,
            "place_context": places,
        }
        return "[Urban memory recall]\n" + json.dumps(payload, ensure_ascii=False, default=str, indent=2)

    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:
        return None

    def sync_turn(self, user_content: str, assistant_content: str, *, session_id: str = "") -> None:
        text = f"{user_content}\n{assistant_content}"
        if _looks_like_feedback(text):
            self.feedback.record(
                {
                    "summary": _shorten(text, 300),
                    "triggers": sorted(_tokens(text))[:12],
                    "session_id": session_id or self._session_id,
                    "source": "sync_turn",
                }
            )

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        return [URBAN_MEMORY_SEARCH_SCHEMA, URBAN_MEMORY_RECORD_SCHEMA, URBAN_PLACE_CONTEXT_SCHEMA, URBAN_RESEARCH_MEMORY_SCHEMA]

    def handle_tool_call(self, tool_name: str, args: dict[str, Any], **kwargs: Any) -> str:
        if tool_name == "urban_memory_search":
            query = str(args.get("query") or "")
            limit = int(args.get("limit") or 5)
            memory_types = set(args.get("memory_types") or ["feedback", "place"])
            result: dict[str, Any] = {"query": query, "memory_root": str(self.root)}
            if "feedback" in memory_types:
                result["feedback_lessons"] = self.feedback.search(query, limit=limit)
            if "place" in memory_types:
                result["place_context"] = self.place.search(query, limit=limit)
            if "research" in memory_types or "research_design" in memory_types:
                result["research_design_lessons"] = self.research.search(query, limit=limit)
            return _json({"success": True, "result": result})
        if tool_name == "urban_memory_record":
            memory_type = str(args.get("memory_type") or "feedback")
            feedback_record = self.feedback.record(args)
            place_record = None
            research_record = None
            if args.get("place") or memory_type == "place":
                place_record = self.place.record(args)
            if memory_type in {"research", "research_design"}:
                research_record = self.research.record(args)
            return _json({"success": True, "result": {"feedback": feedback_record, "place": place_record, "research": research_record, "memory_root": str(self.root)}})
        if tool_name == "urban_place_context":
            place = str(args.get("place") or args.get("location") or "")
            limit = int(args.get("limit") or 5)
            return _json({"success": True, "result": {"place": place, "records": self.place.context_for_place(place, limit=limit), "memory_root": str(self.root)}})
        if tool_name == "urban_research_memory":
            action = str(args.get("action") or "search")
            limit = int(args.get("limit") or 5)
            if action == "record":
                return _json({"success": True, "result": {"record": self.research.record(args), "memory_root": str(self.root)}})
            if action == "list":
                return _json({"success": True, "result": {"records": self.research.list(limit=limit), "memory_root": str(self.root)}})
            query = str(args.get("query") or args.get("task") or "")
            return _json({"success": True, "result": {"query": query, "records": self.research.search(query, limit=limit), "memory_root": str(self.root)}})
        return _json({"success": False, "error": f"UrbanMemoryProvider does not handle {tool_name}"})

    def on_memory_write(self, action: str, target: str, content: str, metadata: dict[str, Any] | None = None) -> None:
        metadata = metadata or {}
        if _looks_like_feedback(content):
            self.feedback.record({"summary": content, "triggers": sorted(_tokens(content))[:12], "action": action, "target": target, "metadata": metadata, "source": "builtin_memory_mirror"})

    def on_delegation(self, task: str, result: str, *, child_session_id: str = "", **kwargs: Any) -> None:
        text = f"Delegated task: {task}\nResult: {result}"
        if _looks_like_feedback(text):
            self.feedback.record({"summary": _shorten(text, 300), "triggers": sorted(_tokens(text))[:12], "child_session_id": child_session_id, "source": "delegation"})

    def shutdown(self) -> None:
        self._initialized = False


def register(ctx: Any) -> None:
    """Hermes plugin entry point."""
    ctx.register_memory_provider(UrbanMemoryProvider())


def _rank_records(records: list[dict[str, Any]], query: str, *, limit: int) -> list[dict[str, Any]]:
    query_tokens = _tokens(query)
    lowered = query.lower()
    scored: list[tuple[float, dict[str, Any]]] = []
    for record in records:
        haystack = json.dumps(record, ensure_ascii=False, default=str).lower()
        triggers = [str(item).lower() for item in record.get("triggers", [])]
        trigger_score = 1.0 if any(trigger and trigger in lowered for trigger in triggers) else 0.0
        overlap = len(query_tokens & _tokens(record)) / max(len(query_tokens), 1)
        score = trigger_score + overlap
        if score > 0:
            scored.append((score, record))
    scored.sort(key=lambda item: (-item[0], str(item[1].get("timestamp", ""))))
    return [record for _, record in scored[:limit]]


def _builtin_research_lessons() -> list[dict[str, Any]]:
    """Built-in seed lessons used as recallable cues, not fixed policies."""
    seed_path = Path(__file__).with_name("research_memory_seed.json")
    if seed_path.exists():
        try:
            data = json.loads(seed_path.read_text(encoding="utf-8-sig"))
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict)]
        except Exception:
            pass
    return [
        {
            "record_id": "builtin_aoi_context_buffer_pattern",
            "timestamp": "builtin",
            "memory_type": "research_design",
            "domain": "spatial_scope",
            "summary": (
                "Many urban studies distinguish an authoritative AOI or study boundary from a larger "
                "context buffer used to collect surrounding roads, buildings, POIs, viewsheds, or spillover "
                "conditions. Treat AOI/context-buffer separation as a task-relevant research design cue, "
                "not as a universal hard rule."
            ),
            "triggers": ["aoi", "context buffer", "buffer", "研究范围", "历史街区", "空间范围"],
            "method_hint": "Ask or infer whether the user supplied an AOI, a context buffer, or both; label exploratory scope explicitly when the authoritative AOI is missing.",
            "caveats": ["Do not silently substitute a context buffer for the analytic AOI.", "Buffer size should be justified by research question and domain convention."],
        },
        {
            "record_id": "builtin_grid_units_for_perception_models",
            "timestamp": "builtin",
            "memory_type": "research_design",
            "domain": "spatial_unit_design",
            "summary": (
                "For studies linking historical-district built environment to subjective perception, uniform "
                "grid cells such as 200m x 200m can increase sample size and improve X/Y spatial alignment "
                "compared with one observation per district. Social-media perception signals can be aggregated "
                "to the same grid cells as built-environment indicators."
            ),
            "triggers": ["历史感", "主观感知", "social media", "小红书", "grid", "200m", "网格", "建成环境"],
            "method_hint": "Consider 200m grids, street segments, or blocks; compare sensitivity across spatial units and report MAUP risks.",
            "caveats": ["Grid size is a research design choice, not a law.", "Avoid machine learning on a few dozen district-level observations unless the design supports it."],
        },
        {
            "record_id": "builtin_social_media_y_alignment",
            "timestamp": "builtin",
            "memory_type": "research_design",
            "domain": "variable_operationalization",
            "summary": (
                "When using social-media posts to represent historical-sense perception, geocode posts, align "
                "them to the chosen spatial unit and observation window, and model posting bias, visitor bias, "
                "platform demographics, duplicate posts, and text/image sentiment uncertainty."
            ),
            "triggers": ["小红书", "社交媒体", "游客", "历史感", "perception", "Y变量", "subjective"],
            "method_hint": "Aggregate historical-sense labels/scores per grid or segment; keep the Y construction separate from X indicators before modeling.",
            "caveats": ["Social-media signals are not representative surveys.", "Do not overclaim causality without design or validation."],
        },
        {
            "record_id": "builtin_paper_gap_variable_verifiability",
            "timestamp": "builtin",
            "memory_type": "research_design",
            "domain": "paper_gap",
            "summary": (
                "A useful paper gap for urban-analysis agents is variable verifiability: the agent should map "
                "research questions to measurable variables, required data, spatial/temporal units, validation "
                "checks, and comparable literature choices, then flag variables that are only proxies or missing."
            ),
            "triggers": ["gap", "paper", "变量", "可验证", "研究设计", "literature", "method"],
            "method_hint": "Return a research design table with question, X/Y variables, data, unit, model family, validation, and risks.",
            "caveats": ["Literature memory should guide alternatives, not force a single template."],
        },
    ]


def _looks_like_feedback(text: str) -> bool:
    lowered = text.lower()
    markers = ["correction", "correct", "override", "feedback", "review", "rerun", "barrier", "stakeholder", "scale", "source", "license", "human"]
    return any(marker in lowered for marker in markers)


def _shorten(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


URBAN_MEMORY_SEARCH_SCHEMA = {
    "name": "urban_memory_search",
    "description": "Search UrbanAgent feedback lessons and place memory.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "memory_types": {"type": "array", "items": {"type": "string", "enum": ["feedback", "place", "research", "research_design"]}},
            "limit": {"type": "integer", "default": 5},
        },
        "required": ["query"],
    },
}

URBAN_MEMORY_RECORD_SCHEMA = {
    "name": "urban_memory_record",
    "description": "Record a reusable urban feedback lesson and optional place context.",
    "parameters": {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "correction": {"type": "string"},
            "place": {"type": "string"},
            "triggers": {"type": "array", "items": {"type": "string"}},
            "memory_type": {"type": "string", "enum": ["feedback", "place", "research", "research_design"], "default": "feedback"},
        },
        "required": ["summary"],
    },
}

URBAN_PLACE_CONTEXT_SCHEMA = {
    "name": "urban_place_context",
    "description": "Retrieve stored place context for a specific urban location.",
    "parameters": {"type": "object", "properties": {"place": {"type": "string"}, "limit": {"type": "integer", "default": 5}}, "required": ["place"]},
}

URBAN_RESEARCH_MEMORY_SCHEMA = {
    "name": "urban_research_memory",
    "description": "Search, list, or record reusable urban research-design lessons.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["search", "record", "list"], "default": "search"},
            "query": {"type": "string"},
            "task": {"type": "string"},
            "summary": {"type": "string"},
            "method_hint": {"type": "string"},
            "domain": {"type": "string"},
            "triggers": {"type": "array", "items": {"type": "string"}},
            "caveats": {"type": "array", "items": {"type": "string"}},
            "limit": {"type": "integer", "default": 5},
        },
        "required": [],
    },
}
