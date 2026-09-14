"""Regression checks for the Pi-to-Python UrbanAgents adapter."""

from __future__ import annotations

import json
import sys
from pathlib import Path


EXPERIMENT_ROOT = Path(__file__).resolve().parents[1] / "pi_urban_agent"
if str(EXPERIMENT_ROOT) not in sys.path:
    sys.path.insert(0, str(EXPERIMENT_ROOT))

from urban_pi_bridge import dispatch  # noqa: E402


def _payload(request: dict[str, object]) -> dict[str, object]:
    return json.loads(dispatch(request))


def test_bridge_rejects_route_initialization_without_task(tmp_path: Path) -> None:
    payload = _payload(
        {
            "tool_name": "urban_route_tree",
            "arguments": {"action": "init", "run_dir": str(tmp_path)},
        }
    )

    assert payload["success"] is False
    assert "requires a non-empty task" in str(payload["error"])


def test_bridge_initializes_typed_route_tree(tmp_path: Path) -> None:
    task = "Assess pedestrian accessibility in a station walk shed."
    payload = _payload(
        {
            "tool_name": "urban_route_tree",
            "arguments": {
                "action": "init",
                "run_dir": str(tmp_path),
                "task": task,
                "nodes": [
                    {
                        "node_id": "scope",
                        "node_type": "research_object",
                        "title": "Define accessibility question",
                        "required_inputs": ["study boundary"],
                        "expected_outputs": ["scope note"],
                        "time_space_people": {
                            "time": "cross-sectional",
                            "space": "station walk shed",
                            "people": "pedestrians",
                        },
                        "claim_boundary": "No causal claim",
                        "status": "selected",
                    }
                ],
            },
        }
    )

    assert payload["success"] is True
    state = json.loads((tmp_path / "route_tree_state.json").read_text(encoding="utf-8"))
    assert state["meta"]["task"] == task
    assert state["nodes"][0]["node_type"] == "research_object"
    assert state["nodes"][0]["time_space_people"]["space"] == "station walk shed"
