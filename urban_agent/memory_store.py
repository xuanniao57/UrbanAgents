from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


PACKAGE_ROOT = Path(__file__).resolve().parent
BUILTIN_MEMORY_ROOT = PACKAGE_ROOT / "memory"
DEFAULT_MEMORY_ROOT = BUILTIN_MEMORY_ROOT


def _default_writable_memory_root() -> Path:
    env_root = os.getenv("URBAN_AGENT_MEMORY_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    try:
        from .constants import get_urban_home

        return get_urban_home() / "memory"
    except Exception:
        return BUILTIN_MEMORY_ROOT


@dataclass(frozen=True)
class MemoryRecord:
    """File-backed memory item shared by policy, workflow, and experience memory."""

    record_id: str
    memory_type: str
    summary: str
    triggers: tuple[str, ...] = field(default_factory=tuple)
    scope: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    source_path: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, memory_type: str, source_path: Path | None = None) -> "MemoryRecord":
        fallback_id = source_path.stem if source_path else str(uuid.uuid4())
        record_id = (
            data.get("record_id")
            or data.get("lesson_id")
            or data.get("policy_id")
            or data.get("workflow_id")
            or data.get("experience_id")
            or fallback_id
        )
        triggers = data.get("triggers", ())
        if isinstance(triggers, str):
            triggers = (triggers,)
        return cls(
            record_id=str(record_id),
            memory_type=memory_type,
            summary=str(data.get("summary") or data.get("description") or ""),
            triggers=tuple(str(item) for item in (triggers or ())),
            scope=str(data.get("scope") or ""),
            payload=dict(data),
            source_path=str(source_path) if source_path else None,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = dict(self.payload)
        payload.setdefault("record_id", self.record_id)
        payload.setdefault("memory_type", self.memory_type)
        payload.setdefault("summary", self.summary)
        payload.setdefault("triggers", list(self.triggers))
        if self.scope:
            payload.setdefault("scope", self.scope)
        if self.source_path:
            payload.setdefault("source_path", self.source_path)
        return payload


class FileMemoryStore:
    """Folder-tree memory store with simple metadata/keyword retrieval."""

    MEMORY_DIRS = {
        "policy": "policy_memory",
        "workflow": "workflow_memory",
        "experience": "experience_memory",
        "knowledge": "knowledge_memory",
        "research": "research_memory",
    }

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root).expanduser().resolve() if root is not None else _default_writable_memory_root()
        self.roots = [self.root]
        for raw_root in os.getenv("URBAN_AGENT_EXTRA_MEMORY_ROOTS", "").split(os.pathsep):
            if not raw_root.strip():
                continue
            extra_root = Path(raw_root.strip()).expanduser().resolve()
            if extra_root not in self.roots:
                self.roots.append(extra_root)
        if BUILTIN_MEMORY_ROOT not in self.roots:
            self.roots.append(BUILTIN_MEMORY_ROOT)

    @classmethod
    def default(cls) -> "FileMemoryStore":
        return cls()

    def records(self, memory_type: str | None = None) -> list[MemoryRecord]:
        types = [memory_type] if memory_type else list(self.MEMORY_DIRS)
        loaded: list[MemoryRecord] = []
        for item_type in types:
            rel = self.MEMORY_DIRS.get(str(item_type), str(item_type))
            for root in self.roots:
                folder = root / rel
                if not folder.exists():
                    continue
                for path in sorted(folder.rglob("*.json")):
                    loaded.extend(self._read_records(path, memory_type=str(item_type)))
                for path in sorted(folder.rglob("*.jsonl")):
                    loaded.extend(self._read_jsonl_records(path, memory_type=str(item_type)))
        return loaded

    def select(self, task: dict[str, Any] | str, *, memory_types: Iterable[str] | None = None, limit: int = 8) -> dict[str, Any]:
        text = task if isinstance(task, str) else json.dumps(task, ensure_ascii=False, default=str)
        lowered = text.lower()
        task_tokens = _tokens(text)
        candidates = [
            record
            for item_type in (memory_types or ("policy", "workflow", "experience"))
            for record in self.records(item_type)
        ]
        scored: list[tuple[float, MemoryRecord]] = []
        for record in candidates:
            trigger_hit = any(trigger.lower() in lowered for trigger in record.triggers if trigger)
            overlap = len(task_tokens & _tokens(record.to_dict())) / max(len(task_tokens), 1)
            score = (1.0 if trigger_hit else 0.0) + overlap
            if score > 0:
                scored.append((score, record))
        scored.sort(key=lambda item: (-item[0], item[1].memory_type, item[1].record_id))
        selected = [record for _, record in scored[:limit]]
        return {
            "source": "urbanagent_file_memory",
            "memory_root": str(self.root),
            "memory_roots": [str(root) for root in self.roots],
            "selected_count": len(selected),
            "records": [record.to_dict() for record in selected],
        }

    def append_experience(self, payload: dict[str, Any], *, namespace: str = "runtime") -> Path:
        folder = self.root / self.MEMORY_DIRS["experience"] / namespace
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{datetime.now().strftime('%Y%m%d')}.jsonl"
        record = {
            "experience_id": payload.get("experience_id") or f"exp_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
            "timestamp": datetime.now().isoformat(),
            **payload,
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return path

    @staticmethod
    def _read_records(path: Path, *, memory_type: str) -> list[MemoryRecord]:
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            return []
        if isinstance(data, list):
            return [MemoryRecord.from_dict(item, memory_type=memory_type, source_path=path) for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            if isinstance(data.get("records"), list):
                return [
                    MemoryRecord.from_dict(item, memory_type=memory_type, source_path=path)
                    for item in data["records"]
                    if isinstance(item, dict)
                ]
            return [MemoryRecord.from_dict(data, memory_type=memory_type, source_path=path)]
        return []

    @staticmethod
    def _read_jsonl_records(path: Path, *, memory_type: str) -> list[MemoryRecord]:
        records: list[MemoryRecord] = []
        try:
            lines = path.read_text(encoding="utf-8-sig").splitlines()
        except Exception:
            return records
        for line in lines:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except Exception:
                continue
            if isinstance(data, dict):
                records.append(MemoryRecord.from_dict(data, memory_type=memory_type, source_path=path))
        return records


def _tokens(value: Any) -> set[str]:
    import re

    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return set(re.findall(r"[a-z0-9_\-]+|[\u4e00-\u9fff]+", text.lower()))
