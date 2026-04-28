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