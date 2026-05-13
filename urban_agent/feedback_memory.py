from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .memory_store import FileMemoryStore, MemoryRecord


@dataclass(frozen=True)
class FeedbackLesson:
    lesson_id: str
    summary: str
    triggers: tuple[str, ...]
    validation_checks: tuple[str, ...] = field(default_factory=tuple)
    expected_outputs: tuple[str, ...] = field(default_factory=tuple)
    scope: str = ""
    checks: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    repair_actions: tuple[str, ...] = field(default_factory=tuple)
    memory_type: str = "policy"
    workflow_steps: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    review_policies: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_record(cls, record: MemoryRecord) -> "FeedbackLesson":
        data = record.to_dict()
        lesson_id = data.get("lesson_id") or data.get("policy_id") or data.get("workflow_id") or record.record_id
        triggers = data.get("triggers") or record.triggers
        checks = data.get("checks") or []
        repair_actions = []
        for check in checks:
            if isinstance(check, dict) and check.get("repair_action"):
                repair_actions.append(str(check["repair_action"]))
        return cls(
            lesson_id=str(lesson_id),
            summary=str(data.get("summary") or record.summary),
            triggers=tuple(str(item) for item in (triggers or ())),
            validation_checks=tuple(str(item) for item in data.get("validation_checks", ()) or ()),
            expected_outputs=tuple(str(item) for item in data.get("expected_outputs", ()) or ()),
            scope=str(data.get("scope") or record.scope or ""),
            checks=tuple(dict(item) for item in checks if isinstance(item, dict)),
            repair_actions=tuple(dict.fromkeys(repair_actions)),
            memory_type=str(record.memory_type),
            workflow_steps=tuple(dict(item) for item in data.get("steps", []) if isinstance(item, dict)),
            review_policies=tuple(str(item) for item in data.get("review_policies", []) if item),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "lesson_id": self.lesson_id,
            "summary": self.summary,
            "triggers": list(self.triggers),
            "validation_checks": list(self.validation_checks),
            "expected_outputs": list(self.expected_outputs),
            "scope": self.scope,
            "checks": [dict(item) for item in self.checks],
            "repair_actions": list(self.repair_actions),
            "memory_type": self.memory_type,
            "workflow_steps": [dict(item) for item in self.workflow_steps],
            "review_policies": list(self.review_policies),
        }


class FeedbackMemory:
    """Reusable policy/workflow view plus review-feedback writer."""

    def __init__(self, lessons: list[FeedbackLesson] | None = None, memory_store: FileMemoryStore | None = None):
        self.memory_store = memory_store or FileMemoryStore.default()
        if lessons is not None:
            self.lessons = lessons
        else:
            self.lessons = self._load_lessons(("policy", "workflow"))

    def _load_lessons(self, memory_types: tuple[str, ...]) -> list[FeedbackLesson]:
        lessons: list[FeedbackLesson] = []
        for memory_type in memory_types:
            for record in self.memory_store.records(memory_type):
                lessons.append(FeedbackLesson.from_record(record))
        return lessons

    def select_for_task(self, task: dict[str, Any] | str, *, limit: int = 8) -> dict[str, Any]:
        memory_pack = self.memory_store.select(task, memory_types=("policy", "workflow"), limit=limit)
        selected_lessons = [FeedbackLesson.from_record(MemoryRecord.from_dict(record, memory_type=record.get("memory_type", "policy"))) for record in memory_pack.get("records", [])]
        return {
            "source": "urbanagent_feedback_memory",
            "memory_root": str(self.memory_store.root),
            "memory_roots": [str(root) for root in getattr(self.memory_store, "roots", [self.memory_store.root])],
            "selected_count": len(selected_lessons),
            "lessons": [lesson.to_dict() for lesson in selected_lessons],
            "memory_pack": memory_pack,
        }

    def policy_criteria(self) -> dict[str, dict[str, Any]]:
        criteria: dict[str, dict[str, Any]] = {}
        for lesson in self.lessons:
            if lesson.memory_type != "policy":
                continue
            criteria[lesson.lesson_id] = {
                "summary": lesson.summary,
                "scope": lesson.scope,
                "validation_checks": list(lesson.validation_checks),
                "expected_outputs": list(lesson.expected_outputs),
                "checks": [dict(item) for item in lesson.checks],
                "repair_actions": list(lesson.repair_actions),
            }
        return criteria

    def store_experience(self, payload: dict[str, Any], *, namespace: str = "runtime") -> str:
        return str(self.memory_store.append_experience(payload, namespace=namespace))

    def store_review_feedback(self, *, task: dict[str, Any], review: dict[str, Any], trace_id: str = "") -> str | None:
        corrections = review.get("correction_memory") or []
        rerun_queue = review.get("rerun_queue") or []
        if not corrections and not rerun_queue:
            return None
        if trace_id:
            for record in self.memory_store.records("experience"):
                data = record.to_dict()
                if data.get("category") == "review_feedback" and data.get("trace_id") == trace_id:
                    return record.source_path

        payload = {
            "summary": "ReviewHub correction feedback captured for future workflow planning.",
            "triggers": _experience_triggers(task, review),
            "task": task,
            "review": {
                "recommendation": review.get("recommendation"),
                "issues": review.get("issues", []),
                "warnings": review.get("warnings", []),
                "correction_memory": corrections,
                "rerun_queue": rerun_queue,
            },
            "trace_id": trace_id,
            "category": "review_feedback",
        }
        return self.store_experience(payload, namespace="review_feedback")


def get_default_feedback_memory() -> FeedbackMemory:
    return FeedbackMemory()


def select_feedback_lessons(task: dict[str, Any] | str, *, limit: int = 8) -> dict[str, Any]:
    return get_default_feedback_memory().select_for_task(task, limit=limit)


def _experience_triggers(task: dict[str, Any], review: dict[str, Any]) -> list[str]:
    text = json.dumps({"task": task, "review": review}, ensure_ascii=False, default=str).lower()
    triggers = []
    for token in ("aoi", "buffer", "context", "osm", "gis", "pre-clipped", "预裁剪"):
        if token.lower() in text:
            triggers.append(token)
    return triggers or ["review", "correction"]



