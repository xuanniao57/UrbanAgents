import asyncio

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