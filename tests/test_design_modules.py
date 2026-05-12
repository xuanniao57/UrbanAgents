import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from legacy.urban_agent_legacy.cognition import SpatialCognition
from urban_agent.core.memory import MemoryModule
from urban_agent.core.reasoning import ReasoningModule


class _Context:
    def __init__(self, raw_features):
        self.raw_features = raw_features
        self.crs = "EPSG:3857"


def test_dual_space_cognition_detects_extended_relations():
    cognition = SpatialCognition()
    result = cognition.understand(
        _Context(
            {
                "clusters": [{"id": 0, "count": 5, "density": 0.8, "centroid": (0.0, 0.0), "radius": 90.0}],
                "open_spaces": [{"type": "plaza", "area": 1000, "centroid": (40.0, 0.0), "shape_type": "square"}],
                "barriers": [{"type": "river", "description": "River", "coordinates": (20.0, 100.0)}],
                "junctions": [{"id": "j0", "degree": 4, "coordinates": (20.0, 80.0), "road_types": ["primary"]}],
                "connectivity": {"average_degree": 2.5},
                "roads": {"dominant_orientation": 0, "orientation_entropy": 0.2},
                "spatial_patterns": {"grid_regularity": 0.5, "building_clustering": 0.6},
            }
        ),
        "synthetic test",
    )

    relation_types = {relation["type"] for relation in result["topological_graph"]["relations"]}
    assert "contains" in relation_types
    assert "separated" in relation_types


def test_memory_retrieval_and_reasoning_transfer():
    async def _run():
        memory = MemoryModule(config={"short_term_size": 5})
        await memory.store(
            {
                "task": {"workflow_profile": "adaptive_urban_analysis", "start": "A", "end": "B"},
                "perception": {"type": "text", "city": "Beijing"},
                "action": {"route_actions": ["forward", "left", "stop"]},
            }
        )
        memory_context = await memory.retrieve({"workflow_profile": "adaptive_urban_analysis", "start": "A", "end": "B"})

        reasoning = ReasoningModule(config={"mode": "enhanced"})
        result = await reasoning.infer(
            {"road_network": {}, "topology": {}},
            memory_context,
            {"workflow_profile": "adaptive_urban_analysis", "start": "A", "end": "B", "steps": []},
        )
        return result

    result = asyncio.run(_run())
    assert result["workflow_profile"] == "adaptive_urban_analysis"
    assert result["reasoning_chain"]