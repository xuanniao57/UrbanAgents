import asyncio

from urban_agent.agents.base import AgentMessage, AgentRole, BaseAgent
from urban_agent.agents.manager import ManagerAgent
from urban_agent.agents.reviewers import HumanCheckpointAgent
from urban_agent.agents.runtime import RuntimeLedger
from urban_agent.cli import _summarize_runtime


class DummyWorker(BaseAgent):
    def __init__(self, role: AgentRole, payload: dict):
        super().__init__(role=role)
        self.payload = payload

    @property
    def role_prompt(self) -> str:
        return "Dummy worker"

    async def execute(self, message: AgentMessage) -> AgentMessage:
        return AgentMessage(
            sender=self.role,
            receiver=AgentRole.MANAGER,
            msg_type="result",
            payload=dict(self.payload),
            trace_id=message.trace_id,
        )


class CapturingWorker(DummyWorker):
    def __init__(self, role: AgentRole, payload: dict):
        super().__init__(role, payload)
        self.last_payload = None

    async def execute(self, message: AgentMessage) -> AgentMessage:
        self.last_payload = message.payload
        return await super().execute(message)


def _plan_for(role: str = "analyst") -> dict:
    return {
        "plan_id": "plan_runtime_test",
        "complexity": "intermediate",
        "workflow_profile": "adaptive_urban_analysis",
        "capability_context": {
            "disclosure_policy": "progressive",
            "level0_index_size": 12,
            "selected_names": ["network_accessibility", "layered_gis_export"],
        },
        "subtasks": [
            {
                "subtask_id": "st0",
                "objective": "Analyze walkability with traceable evidence",
                "assigned_role": role,
                "input_data": {"question": "Analyze walkability with traceable evidence"},
                "dependencies": [],
                "expected_output": "analysis result",
            }
        ],
        "execution_order": ["st0"],
    }


def test_runtime_ledger_builds_todos_and_tool_surface():
    ledger = RuntimeLedger.from_plan(_plan_for(), interaction_mode="supervisory")
    payload = ledger.to_dict()

    assert payload["runtime_profile"]["inspired_by"] == "NousResearch/hermes-agent"
    assert payload["todos"][0]["status"] == "pending"
    assert payload["tool_surface"]["selected_capabilities"] == [
        "network_accessibility",
        "layered_gis_export",
    ]


def test_cli_summarizes_runtime_ledger():
    ledger = RuntimeLedger.from_plan(_plan_for(), interaction_mode="supervisory")
    ledger.start_subtask("st0", agent="analyst", objective="Analyze walkability")
    ledger.complete_subtask("st0", {"answer": "ok"})
    ledger.record_checkpoint(
        checkpoint_id="DP-3",
        stage="spatial_representation_review",
        mode="supervisory",
        decision={"action": "approve"},
    )

    summary = _summarize_runtime(ledger.to_dict())

    assert summary["todo_completed"] == 1
    assert summary["todo_total"] == 1
    assert summary["checkpoint_count"] == 1
    assert summary["last_checkpoint"] == "DP-3"


def test_manager_records_runtime_checkpoints_and_todos():
    manager = ManagerAgent(
        workers={AgentRole.ANALYST: DummyWorker(AgentRole.ANALYST, {"answer": "walkability is constrained"})},
        reviewers={AgentRole.HUMAN_CHECKPOINT: HumanCheckpointAgent(interaction_mode="supervisory")},
    )
    message = AgentMessage(
        sender=AgentRole.PLANNER,
        receiver=AgentRole.MANAGER,
        msg_type="task_plan",
        payload={"execution_plan": _plan_for()},
        trace_id="trace_runtime",
    )

    result = asyncio.run(manager.execute(message))
    runtime = result.payload["results"]["runtime"]

    assert result.payload["results"]["completed"] == 1
    assert runtime["todos"][0]["status"] == "completed"
    checkpoint_ids = [item["checkpoint_id"] for item in runtime["checkpoints"]]
    assert checkpoint_ids == ["DP-1", "DP-3"]
    assert all(item["approved"] for item in runtime["checkpoints"])


def test_manager_exposes_memory_context_to_worker_payload():
    worker = CapturingWorker(AgentRole.ANALYST, {"answer": "ok"})
    plan = _plan_for()
    memory_context = {"best_match": {"id": "memory-1", "summary": "prior lesson"}}
    plan["subtasks"][0]["input_data"]["memory_context"] = memory_context
    manager = ManagerAgent(workers={AgentRole.ANALYST: worker}, reviewers={})
    message = AgentMessage(
        sender=AgentRole.PLANNER,
        receiver=AgentRole.MANAGER,
        msg_type="task_plan",
        payload={"execution_plan": plan},
        trace_id="trace_memory_context",
    )

    asyncio.run(manager.execute(message))

    assert worker.last_payload["memory_context"] == memory_context


def test_guided_checkpoint_can_block_subtask_result():
    async def callback(checkpoint_id: str, data: dict) -> dict:
        if checkpoint_id == "DP-3":
            return {"action": "reject", "reason": "needs authoritative data"}
        return {"action": "approve", "reason": "scope accepted"}

    manager = ManagerAgent(
        workers={AgentRole.ANALYST: DummyWorker(AgentRole.ANALYST, {"answer": "draft"})},
        reviewers={AgentRole.HUMAN_CHECKPOINT: HumanCheckpointAgent(interaction_mode="guided", human_callback=callback)},
    )
    message = AgentMessage(
        sender=AgentRole.PLANNER,
        receiver=AgentRole.MANAGER,
        msg_type="task_plan",
        payload={"execution_plan": _plan_for()},
        trace_id="trace_runtime_block",
    )

    result = asyncio.run(manager.execute(message))
    subtask = result.payload["results"]["subtask_results"]["st0"]
    runtime = result.payload["results"]["runtime"]

    assert result.payload["results"]["completed"] == 0
    assert subtask["status"] == "failed"
    assert subtask["result"]["error"] == "blocked_by_human_checkpoint"
    assert runtime["todos"][0]["status"] == "failed"
    assert runtime["checkpoints"][-1]["approved"] is False
