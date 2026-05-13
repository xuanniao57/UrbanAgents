from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .memory_store import FileMemoryStore, MemoryRecord


@dataclass(frozen=True)
class ResearchLesson:
    """Reusable research-design lesson exposed progressively to MainAgent/Planner."""

    lesson_id: str
    summary: str
    triggers: tuple[str, ...] = field(default_factory=tuple)
    domain: str = ""
    method_hint: str = ""
    caveats: tuple[str, ...] = field(default_factory=tuple)
    evidence_scope: str = ""
    memory_type: str = "research"

    @classmethod
    def from_record(cls, record: MemoryRecord) -> "ResearchLesson":
        data = record.to_dict()
        return cls(
            lesson_id=str(data.get("lesson_id") or data.get("record_id") or record.record_id),
            summary=str(data.get("summary") or record.summary),
            triggers=tuple(str(item) for item in (data.get("triggers") or record.triggers or ())),
            domain=str(data.get("domain") or data.get("scope") or record.scope or ""),
            method_hint=str(data.get("method_hint") or data.get("method") or ""),
            caveats=tuple(str(item) for item in (data.get("caveats") or ())),
            evidence_scope=str(data.get("evidence_scope") or ""),
            memory_type=str(record.memory_type),
        )

    def to_index_dict(self) -> dict[str, Any]:
        return {
            "lesson_id": self.lesson_id,
            "summary": self.summary,
            "triggers": list(self.triggers)[:8],
            "domain": self.domain,
            "method_hint": self.method_hint,
            "evidence_scope": self.evidence_scope,
            "memory_type": self.memory_type,
        }

    def to_planner_dict(self) -> dict[str, Any]:
        data = self.to_index_dict()
        data["caveats"] = list(self.caveats)
        return data


class ResearchMemory:
    """Thin read model for urban research-design memory."""

    def __init__(self, memory_store: FileMemoryStore | None = None):
        self.memory_store = memory_store or FileMemoryStore.default()

    def select_for_task(self, task: dict[str, Any] | str, *, limit: int = 6) -> dict[str, Any]:
        memory_pack = self.memory_store.select(task, memory_types=("research",), limit=limit)
        lessons = [
            ResearchLesson.from_record(
                MemoryRecord.from_dict(record, memory_type=record.get("memory_type", "research"))
            )
            for record in memory_pack.get("records", [])
            if isinstance(record, dict)
        ]
        return {
            "source": "urbanagent_research_memory",
            "memory_root": str(self.memory_store.root),
            "memory_roots": [str(root) for root in getattr(self.memory_store, "roots", [self.memory_store.root])],
            "selected_count": len(lessons),
            "lessons": [lesson.to_planner_dict() for lesson in lessons],
            "memory_pack": memory_pack,
        }


def get_default_research_memory() -> ResearchMemory:
    return ResearchMemory()


def select_research_lessons(task: dict[str, Any] | str, *, limit: int = 6) -> dict[str, Any]:
    return get_default_research_memory().select_for_task(task, limit=limit)
