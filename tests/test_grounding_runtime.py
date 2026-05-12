import asyncio
from pathlib import Path

from urban_agent.agents.base import AgentMessage, AgentRole
from urban_agent.agents.reviewers import SpatialReviewerAgent
from urban_agent.grounding import (
    build_dataset_cards,
    build_grounding_policy,
    build_indicator_computability_matrix,
    build_input_grounding_package,
)


def test_grounding_runtime_builds_cards_policy_and_matrix(tmp_path: Path):
    task = {
        "artifact_dir": str(tmp_path),
        "input_grounding_policy": {
            "authoritative_aoi_required": True,
            "dataset_cards_required": True,
            "known_limits_required": True,
        },
        "indicator_requirements": [
            {
                "indicator": "building-road adherence",
                "required_data": "建筑轮廓、道路中心线",
            },
            {
                "indicator": "historical street skeleton similarity",
                "required_data": "历史街巷图、现状路网",
                "available_proxy": "current_road_density_km_per_km2",
            },
            {
                "indicator": "protected building value density",
                "required_data": "保护建筑名录、建筑轮廓",
            },
        ],
    }
    path_context = {
        "paths": {
            "boundary": str(tmp_path / "aoi.geojson"),
            "roads": str(tmp_path / "roads.geojson"),
            "buildings": str(tmp_path / "buildings.geojson"),
        }
    }

    cards = build_dataset_cards(task, path_context)
    policy = build_grounding_policy(task, cards)
    matrix = build_indicator_computability_matrix(task, cards, path_context)

    assert cards
    assert policy["dataset_card_count"] == len(cards)
    assert [row["status"] for row in matrix] == ["direct", "proxy", "missing"]

    package = build_input_grounding_package({"task_data": task, "path_context": path_context})
    artifact_types = {artifact["type"] for artifact in package["artifacts"]}
    assert "dataset_cards" in artifact_types
    assert "grounding_policy" in artifact_types
    assert "indicator_computability_csv" in artifact_types
    assert (tmp_path / "urbanagent_indicator_computability_matrix.csv").exists()


def test_reviewer_flags_undisclosed_missing_indicator():
    reviewer = SpatialReviewerAgent()
    result = {
        "evidence_manifest": {
            "spatial": {"bbox": [0, 0, 1, 1], "crs": "EPSG:4326"},
            "temporal": {"timestamp": "2026-05-12T00:00:00"},
            "population": {
                "target_group": "researchers",
                "observed_group": "researchers",
                "affected_group": "researchers",
                "stakeholder_source": "expert review",
            },
            "governance": {
                "provenance": "test",
                "license": "test",
                "collection_method": "test",
                "uncertainty": "test",
                "missing_layers": [],
            },
            "tags": ["grounding"],
        },
        "grounding_policy": {
            "dataset_cards_required": True,
            "known_limits_required": True,
            "require_missing_evidence_disclosure": True,
        },
        "dataset_cards": [
            {"resource_id": "roads", "known_limits": ["test limits"]},
        ],
        "indicator_computability_matrix": [
            {"indicator": "protected building value density", "status": "missing"},
        ],
        "limitations": [],
    }
    payload = {
        "subtask_results": {
            "st_1": {"status": "completed", "result": result},
        },
        "completed": 1,
        "total": 1,
    }
    message = AgentMessage(
        sender=AgentRole.MANAGER,
        receiver=AgentRole.SPATIAL_REVIEWER,
        msg_type="review",
        payload=payload,
    )

    reviewed = asyncio.run(reviewer.execute(message)).payload

    assert any("protected building value density is missing" in warning for warning in reviewed["warnings"])


def test_grounding_module_does_not_embed_case_dataset_descriptions():
    source = Path(__file__).resolve().parents[1] / "urban_agent" / "grounding.py"
    text = source.read_text(encoding="utf-8")

    forbidden = ["SinoBF", "sinobf", "OpenStreetMap", "Overpass", "Paper9", "heritage", "aoi_dir", "osm_cache_root"]
    assert not any(token in text for token in forbidden)
