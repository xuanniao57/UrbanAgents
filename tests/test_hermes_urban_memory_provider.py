import json
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
ADAPTER_ROOT = ROOT / "hermes_urban_agent"
if str(ADAPTER_ROOT) not in sys.path:
    sys.path.insert(0, str(ADAPTER_ROOT))

from urban_hermes.memory_provider import UrbanMemoryProvider
from urban_hermes.paths import HERMES_ROOT


def _result(raw: str) -> dict:
    payload = json.loads(raw)
    assert payload["success"] is True
    return payload["result"]


def test_urban_hermes_defaults_to_vendored_runtime():
    if os.getenv("URBAN_HERMES_HERMES_ROOT"):
        pytest.skip("developer override uses an external Hermes checkout")
    assert HERMES_ROOT.name == "hermes_runtime"
    assert HERMES_ROOT.parent.name == "_vendor"
    assert (HERMES_ROOT / "cli.py").exists()
    assert (HERMES_ROOT / "hermes_cli" / "banner.py").exists()


def test_tool_artifact_memory_routes_to_research_store(tmp_path):
    provider = UrbanMemoryProvider(root=tmp_path)
    provider.initialize("test-session")

    recorded = _result(
        provider.handle_tool_call(
            "urban_memory_record",
            {
                "summary": "QGIS workbench packaging should validate qgz readability and layer styles.",
                "memory_type": "tool_artifact",
                "content_layer": "tool_artifact",
                "memory_scope": "reflective",
                "triggers": ["qgis", "workbench", "layer styles"],
            },
        )
    )

    assert recorded["feedback"] is None
    assert recorded["place"] is None
    assert recorded["research"]["content_layer"] == "tool_artifact"
    assert recorded["research"]["memory_scope"] == "reflective"

    search = _result(
        provider.handle_tool_call(
            "urban_memory_search",
            {
                "query": "qgis workbench layer styles",
                "memory_types": ["feedback", "research"],
                "content_layers": ["tool_artifact"],
                "limit": 3,
            },
        )
    )

    assert search.get("feedback_lessons") == []
    assert search["research_design_lessons"]
    assert search["research_design_lessons"][0]["content_layer"] == "tool_artifact"


def test_prefetch_keeps_tool_artifacts_deferred(tmp_path):
    provider = UrbanMemoryProvider(root=tmp_path)
    provider.initialize("test-session")

    _result(
        provider.handle_tool_call(
            "urban_research_memory",
            {
                "action": "record",
                "summary": "Vitality-grid studies should separate population observation windows from built-environment indicators.",
                "content_layer": "research_design",
                "memory_scope": "reflective",
                "triggers": ["vitality-grid", "observation window"],
            },
        )
    )
    _result(
        provider.handle_tool_call(
            "urban_research_memory",
            {
                "action": "record",
                "summary": "QGIS vitality workbench packaging procedure stores project files, style files, and a manifest.",
                "content_layer": "tool_artifact",
                "memory_scope": "reflective",
                "method_hint": "Create qgz, qgs, styles, README, and spatial_reasoning_manifest.json.",
                "triggers": ["vitality-grid", "qgis workbench"],
            },
        )
    )

    recall = provider.prefetch("vitality-grid qgis workbench", session_id="test-session")
    assert recall.startswith("[Urban memory recall]")
    payload = json.loads(recall.split("\n", 1)[1])

    assert payload["planning_memory_cards"]
    assert all(item["content_layer"] in {"research_design", "urban_method"} for item in payload["planning_memory_cards"])
    assert payload["deferred_tool_artifact_index"]
    assert all(item["content_layer"] == "tool_artifact" for item in payload["deferred_tool_artifact_index"])
    assert "method_hint" not in payload["deferred_tool_artifact_index"][0]