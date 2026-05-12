"""Runtime ledger for UrbanAgent execution.

The ledger is intentionally lightweight: it does not replace the existing
Planner/Manager/Worker architecture. It adds the operational substrate that
keeps long-running work auditable: an explicit todo list, checkpoint decisions,
tool-surface snapshots, and runtime events.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


APPROVED_CHECKPOINT_ACTIONS = {"approve", "accept", "continue", "ok", "pass"}
BLOCKING_CHECKPOINT_ACTIONS = {"reject", "revise", "stop", "cancel", "pause"}


@dataclass
class RuntimeTodoItem:
    id: str
    title: str
    agent: str
    status: str = "pending"
    dependencies: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RuntimeCheckpointRecord:
    checkpoint_id: str
    stage: str
    mode: str
    action: str
    reason: str = ""
    subtask_id: Optional[str] = None
    agent: Optional[str] = None
    payload_keys: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def approved(self) -> bool:
        if self.action in BLOCKING_CHECKPOINT_ACTIONS:
            return False
        return self.action in APPROVED_CHECKPOINT_ACTIONS or not self.action

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["approved"] = self.approved
        return payload


@dataclass
class RuntimeEventRecord:
    type: str
    payload: dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RuntimeLedger:
    """Per-run operational ledger for ManagerAgent."""

    def __init__(
        self,
        *,
        plan_id: str,
        workflow_profile: str,
        complexity: str,
        interaction_mode: str,
        tool_surface: Optional[dict[str, Any]] = None,
    ):
        self.plan_id = plan_id
        self.workflow_profile = workflow_profile
        self.complexity = complexity
        self.interaction_mode = interaction_mode
        self.tool_surface = tool_surface or {}
        self.todos: dict[str, RuntimeTodoItem] = {}
        self.checkpoints: list[RuntimeCheckpointRecord] = []
        self.events: list[RuntimeEventRecord] = []
        self.created_at = datetime.now().isoformat()

    @classmethod
    def from_plan(cls, plan_data: dict[str, Any], *, interaction_mode: str = "autonomous") -> "RuntimeLedger":
        capability_context = plan_data.get("capability_context", {}) if isinstance(plan_data, dict) else {}
        ledger = cls(
            plan_id=str(plan_data.get("plan_id") or "plan"),
            workflow_profile=str(plan_data.get("workflow_profile") or "adaptive_urban_analysis"),
            complexity=str(plan_data.get("complexity") or "unknown"),
            interaction_mode=interaction_mode,
            tool_surface={
                "selected_capabilities": list(capability_context.get("selected_names", [])),
                "disclosure_policy": capability_context.get("disclosure_policy"),
                "level0_index_size": capability_context.get("level0_index_size"),
                "runtime_policy": "isolated_subtasks_with_checkpointed_review",
            },
        )
        for item in plan_data.get("subtasks", []):
            todo = RuntimeTodoItem(
                id=str(item.get("subtask_id") or len(ledger.todos)),
                title=str(item.get("objective") or "subtask"),
                agent=str(item.get("assigned_role") or "unknown"),
                dependencies=[str(dep) for dep in item.get("dependencies", []) if dep],
            )
            ledger.todos[todo.id] = todo
        ledger.record_event("runtime_initialized", {"todo_count": len(ledger.todos)})
        return ledger

    def start_subtask(self, subtask_id: str, *, agent: str, objective: str) -> None:
        todo = self.todos.setdefault(
            subtask_id,
            RuntimeTodoItem(id=subtask_id, title=objective, agent=agent),
        )
        todo.status = "in_progress"
        todo.started_at = datetime.now().isoformat()
        self.record_event("subtask_started", {"subtask_id": subtask_id, "agent": agent})

    def complete_subtask(self, subtask_id: str, result: Any) -> None:
        todo = self.todos.get(subtask_id)
        if todo is None:
            return
        todo.status = "completed"
        todo.completed_at = datetime.now().isoformat()
        todo.artifacts = _artifact_markers(result)
        self.record_event(
            "subtask_completed",
            {"subtask_id": subtask_id, "artifact_count": len(todo.artifacts)},
        )

    def fail_subtask(self, subtask_id: str, error: str) -> None:
        todo = self.todos.get(subtask_id)
        if todo is None:
            return
        todo.status = "failed"
        todo.error = error
        todo.completed_at = datetime.now().isoformat()
        self.record_event("subtask_failed", {"subtask_id": subtask_id, "error": error})

    def cancel_pending(self, reason: str) -> None:
        for todo in self.todos.values():
            if todo.status == "pending":
                todo.status = "cancelled"
                todo.error = reason
                todo.completed_at = datetime.now().isoformat()
        self.record_event("pending_subtasks_cancelled", {"reason": reason})

    def record_checkpoint(
        self,
        *,
        checkpoint_id: str,
        stage: str,
        mode: str,
        decision: Optional[dict[str, Any]] = None,
        subtask_id: Optional[str] = None,
        agent: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
    ) -> RuntimeCheckpointRecord:
        decision = decision or {}
        record = RuntimeCheckpointRecord(
            checkpoint_id=checkpoint_id,
            stage=stage,
            mode=mode,
            action=str(decision.get("action") or "approve").lower(),
            reason=str(decision.get("reason") or ""),
            subtask_id=subtask_id,
            agent=agent,
            payload_keys=sorted(str(key) for key in (payload or {}).keys()),
        )
        self.checkpoints.append(record)
        self.record_event(
            "checkpoint_recorded",
            {
                "checkpoint_id": checkpoint_id,
                "stage": stage,
                "action": record.action,
                "approved": record.approved,
                "subtask_id": subtask_id,
            },
        )
        return record

    def record_event(self, event_type: str, payload: dict[str, Any]) -> None:
        self.events.append(RuntimeEventRecord(type=event_type, payload=dict(payload)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_profile": {
                "name": "urban_runtime_kernel",
                "inspired_by": "NousResearch/hermes-agent",
                "adapted_patterns": [
                    "session_scoped_todo_ledger",
                    "checkpointed_execution",
                    "isolated_subtask_context",
                    "progressive_tool_surface",
                    "auditable_runtime_events",
                ],
            },
            "plan_id": self.plan_id,
            "workflow_profile": self.workflow_profile,
            "complexity": self.complexity,
            "interaction_mode": self.interaction_mode,
            "created_at": self.created_at,
            "tool_surface": dict(self.tool_surface),
            "todos": [todo.to_dict() for todo in self.todos.values()],
            "checkpoints": [checkpoint.to_dict() for checkpoint in self.checkpoints],
            "events": [event.to_dict() for event in self.events],
        }


def checkpoint_for_agent(agent: str) -> Optional[tuple[str, str]]:
    return {
        "perception": ("DP-2", "data_source_validation"),
        "analyst": ("DP-3", "spatial_representation_review"),
        "cartographer": ("DP-4", "artifact_layer_review"),
        "reporter": ("DP-6", "result_interpretation_review"),
    }.get(agent)


def checkpoint_is_approved(decision: dict[str, Any]) -> bool:
    action = str((decision or {}).get("action") or "approve").lower()
    if action in BLOCKING_CHECKPOINT_ACTIONS:
        return False
    return action in APPROVED_CHECKPOINT_ACTIONS or not action


def _artifact_markers(result: Any) -> list[str]:
    if not isinstance(result, dict):
        return []
    markers: list[str] = []
    for key in ("report", "svg_overlay", "geojson", "geojson_features", "layer_stack", "map_preview"):
        if result.get(key):
            markers.append(key)
    outputs = result.get("outputs")
    if isinstance(outputs, Iterable) and not isinstance(outputs, (str, bytes, dict)):
        markers.extend(str(item) for item in outputs if item)
    return sorted(dict.fromkeys(markers))
