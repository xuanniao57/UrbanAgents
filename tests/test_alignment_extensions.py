import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from urban_agent import CorrectionModuleRegistry
from urban_agent.core import MemoryModule
from legacy.urban_agent_legacy.cognition import SpatialCognition
from legacy.urban_agent_legacy.visualization import SpatialVisualizer
from plugins.rhino.connectors import BaseConnector, ConnectorRegistry


class _Context:
    def __init__(self, raw_features):
        self.raw_features = raw_features
        self.crs = "EPSG:3857"


class _DummyConnector(BaseConnector):
    def __init__(self):
        super().__init__(name="dummy_connector")

    def health_check(self):
        return {"status": "ok"}

    def execute(self, operation: str, payload=None):
        return {"operation": operation, "payload": payload or {}}


def test_connector_registry_exposes_open_specs():
    registry = ConnectorRegistry()
    registry.register(
        _DummyConnector(),
        capabilities=["distribution_preview", "fairness_review"],
        input_modalities=["geojson", "survey"],
        output_modalities=["json"],
        human_review_surfaces=["html_review"],
    )

    specs = registry.list_specs()
    assert specs["dummy_connector"]["protocol"] == "urban-agent-open-spec/v1"
    assert "fairness_review" in specs["dummy_connector"]["capabilities"]
    assert "html_review" in specs["dummy_connector"]["human_review_surfaces"]


def test_cognition_outputs_alignment_diagnostics_and_trace():
    cognition = SpatialCognition()
    result = cognition.understand(
        _Context(
            {
                "clusters": [{"id": 0, "count": 5, "density": 0.8, "centroid": (0.0, 0.0), "radius": 90.0}],
                "open_spaces": [{"type": "plaza", "area": 1000, "centroid": (40.0, 0.0), "shape_type": "square"}],
                "barriers": [{"type": "river", "description": "River", "coordinates": (20.0, 100.0)}],
                "junctions": [{"id": "j0", "degree": 4, "coordinates": (20.0, 80.0), "road_types": ["primary"]}],
                "landmarks": [{"name": "Tower", "type": "tower", "coordinates": (5.0, 5.0), "importance": 0.9}],
                "connectivity": {"average_degree": 2.5},
                "roads": {"dominant_orientation": 0, "orientation_entropy": 0.2},
                "spatial_patterns": {"grid_regularity": 0.5, "building_clustering": 0.6},
            }
        ),
        "inspect site-scale accessibility",
    )

    any_node = next(iter(result["topological_graph"]["nodes"].values()))
    assert any_node["trace"]
    assert result["alignment_diagnostics"]["preferred_scale"] in {"site", "street_block", "neighbourhood", "district_or_city"}
    assert result["inspection_payload"]["nodes"]
    assert "maup_like_risk" in result["alignment_diagnostics"]


def test_correction_registry_applies_structured_overrides():
    registry = CorrectionModuleRegistry()
    payload = {
        "nodes": [{"id": "p1", "type": "plaza", "label": "Old Plaza", "lat": 1.0, "lng": 2.0}],
        "edges": [{"from": "p1", "to": "b1", "type": "connected", "distance_m": 100}],
        "topological_graph": {
            "nodes": {"p1": {"id": "p1", "type": "plaza", "label": "Old Plaza", "properties": {}}},
            "relations": [{"source": "p1", "target": "b1", "type": "connected", "properties": {}}],
        },
        "alignment_diagnostics": {"preferred_scale": "street_block", "maup_like_risk": "medium"},
        "distribution_preview": {},
    }
    request = {
        "selected_modules": ["scale_alignment", "stakeholder_equity", "memory_priority"],
        "node_overrides": [{"id": "p1", "label": "Updated Plaza", "notes": "Survey says this is a community plaza."}],
        "relation_overrides": [{"source": "p1", "target": "b1", "action": "modify", "type": "separated", "notes": "Barrier is stronger than model assumed."}],
        "scale": {"preferred_scale": "site", "maup_like_risk": "high", "notes": "Need site-scale review first."},
        "stakeholder_feedback": [{"group": "elderly pedestrians", "concern": "crossing is unsafe after sunset"}],
        "memory_directives": {"promote": ["case-1"], "suppress": ["case-2"]},
    }

    result = registry.apply(payload, request)
    corrected = result["corrected_payload"]

    assert corrected["nodes"][0]["label"] == "Updated Plaza"
    assert corrected["edges"][0]["type"] == "separated"
    assert corrected["alignment_diagnostics"]["maup_like_risk"] == "high"
    assert corrected["human_alignment"]["memory_directives"]["promote"] == ["case-1"]
    assert any(item["module"] == "scale_alignment" for item in result["audit"])


def test_memory_module_retrieval_trace_and_feedback():
    async def _run():
        memory = MemoryModule(config={"short_term_size": 3})
        await memory.store(
            {
                "task": {"task_type": "outdoor_navigation", "start": "A", "end": "B"},
                "perception": {"type": "text", "location": "Shanghai"},
                "action": {"route_actions": ["forward", "left", "stop"]},
            }
        )
        retrieved = await memory.retrieve({"task_type": "outdoor_navigation", "location": "Shanghai"})
        memory_id = retrieved["relevant_short_term"][0]["id"]
        applied = memory.apply_feedback({"memory_id": memory_id, "importance_delta": 0.2, "note": "Validated by planner"})
        return retrieved, applied, memory.inspect_state()

    retrieved, applied, snapshot = asyncio.run(_run())
    assert retrieved["retrieval_trace"]["short_term"]
    assert applied is True
    assert snapshot["feedback_count"] == 1


def test_visualizer_creates_inspection_html():
    visualizer = SpatialVisualizer()
    html = visualizer.create_inspection_html(
        {
            "inspection_payload": {
                "nodes": [{"id": "n1", "label": "Node 1", "type": "junction", "lng": 2.0, "lat": 1.0, "trace": [{"explanation": "Test node"}]}],
                "edges": [{"from": "n1", "to": "n2", "type": "connected", "trace": [{"explanation": "Test edge"}]}],
            },
            "alignment_diagnostics": {"preferred_scale": "street_block", "maup_like_risk": "medium"},
            "distribution_preview": {"dominant_layer": "junctions", "missing_layers": []},
        }
    )

    assert "UrbanAgent Spatial Review" in html
    assert "MAUP-like risk" in html
    assert "Test node" in html