import asyncio

from urban_agent.agents.base import AgentMessage, AgentRole
from urban_agent.agents.workers import AnalystWorker
from urban_agent.core import MemoryModule


def test_memory_module_store_and_stats():
    memory = MemoryModule(config={"short_term_size": 3})

    asyncio.run(memory.store({"perception": {"type": "text"}, "reasoning": {}, "action": {}}))

    stats = memory.get_memory_stats()
    assert stats["short_term_size"] == 1
    assert stats["working_memory_size"] > 0


def test_memory_module_retrieve_relevant_short_term():
    memory = MemoryModule(config={"short_term_size": 3})
    asyncio.run(
        memory.store(
            {
                "perception": {"type": "text", "location": "Shanghai"},
                "reasoning": {"summary": "walkability near bund"},
                "action": {"answer": "done"},
            }
        )
    )

    result = asyncio.run(memory.retrieve({"location": "Shanghai", "type": "text"}))
    assert "relevant_short_term" in result
    assert len(result["relevant_short_term"]) >= 1


def test_memory_module_persists_runtime_experience_across_instances(tmp_path):
    config = {
        "short_term_size": 5,
        "persistent": True,
        "root": str(tmp_path / "memory"),
        "load_limit": 20,
    }

    async def _run():
        first = MemoryModule(config=config, enable_reflector=False)
        await first.store(
            {
                "task": {"task_type": "walkability", "city": "Shanghai"},
                "perception": {"type": "text", "location": "Shanghai"},
                "action": {"answer": "prior walkability pattern"},
            }
        )
        second = MemoryModule(config=config, enable_reflector=False)
        retrieved = await second.retrieve({"task_type": "walkability", "city": "Shanghai"})
        return first, second, retrieved

    first, second, retrieved = asyncio.run(_run())

    assert first.last_persisted_path
    assert second.get_memory_stats()["persistent_loaded_count"] == 1
    assert retrieved["persistent"]["enabled"] is True
    assert any(
        item.get("action", {}).get("answer") == "prior walkability pattern"
        for item in retrieved["relevant_short_term"]
    )


def test_memory_module_loads_review_feedback_as_experience(tmp_path):
    root = tmp_path / "memory"
    feedback_dir = root / "experience_memory" / "review_feedback"
    feedback_dir.mkdir(parents=True)
    (feedback_dir / "20260513.jsonl").write_text(
        '{"experience_id":"review-1","category":"review_feedback","summary":"Reviewer asked for authoritative walkability evidence.","triggers":["walkability"],"task":{"task_type":"walkability","city":"Shanghai"}}\n',
        encoding="utf-8",
    )

    memory = MemoryModule(config={"persistent": True, "root": str(root), "short_term_size": 5}, enable_reflector=False)
    retrieved = asyncio.run(memory.retrieve({"task_type": "walkability", "city": "Shanghai"}))

    assert memory.get_memory_stats()["persistent_loaded_count"] == 1
    assert any(item.get("category") == "review_feedback" for item in retrieved["relevant_short_term"])


def test_analyst_worker_passes_memory_context_to_reasoning_module():
    class CapturingReasoningModule:
        def __init__(self):
            self.memory_context = None

        async def infer(self, perception_data, memory_context, task):
            self.memory_context = memory_context
            return {
                "status": "analysis_complete",
                "answer": "used memory",
                "memory_context_used": bool(memory_context),
            }

    reasoning = CapturingReasoningModule()
    worker = AnalystWorker(reasoning_module=reasoning, disable_capabilities=True)
    memory_context = {"best_match": {"id": "memory-1", "action": {"answer": "prior route"}}}
    message = AgentMessage(
        sender=AgentRole.MANAGER,
        receiver=AgentRole.ANALYST,
        msg_type="subtask",
        payload={
            "input_data": {"question": "Analyze walkability", "memory_context": memory_context},
            "dependency_results": {},
        },
    )

    result = asyncio.run(worker.execute(message))

    assert reasoning.memory_context == memory_context
    assert result.payload["memory_context_used"] is True


def test_memory_module_cube_retrieval_supports_bbox_queries():
    memory = MemoryModule(
        config={
            "short_term_size": 3,
            "cube_retrieval_config": {
                "layer_steps": [1.0, 0.1, 0.01],
                "max_results": 3,
            },
        },
        enable_cube_retrieval=True,
    )

    asyncio.run(
        memory.store(
            {
                "task": {"task_type": "traffic_signal", "city": "Shanghai"},
                "perception": {
                    "bounds": {
                        "min_lon": 121.500,
                        "min_lat": 31.250,
                        "max_lon": 121.504,
                        "max_lat": 31.254,
                    }
                },
                "action": {"answer": "nearby-intersection"},
            }
        )
    )

    asyncio.run(
        memory.store(
            {
                "task": {"task_type": "traffic_signal", "city": "Shanghai"},
                "perception": {
                    "bounds": {
                        "min_lon": 118.000,
                        "min_lat": 24.000,
                        "max_lon": 118.010,
                        "max_lat": 24.010,
                    }
                },
                "action": {"answer": "far-intersection"},
            }
        )
    )

    result = asyncio.run(
        memory.retrieve(
            {
                "task_type": "traffic_signal",
                "bounds": {
                    "min_lon": 121.501,
                    "min_lat": 31.251,
                    "max_lon": 121.503,
                    "max_lat": 31.253,
                },
            }
        )
    )

    cube_hits = result["relevant_long_term"]["cube_rag"]
    assert cube_hits
    assert cube_hits[0]["experience"]["action"]["answer"] == "nearby-intersection"
    assert "cube_match" in cube_hits[0]