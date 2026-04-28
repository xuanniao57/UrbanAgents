import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from urban_agent.agents.base import AgentMessage, AgentRole
from urban_agent.agents.reviewers import SpatialReviewerAgent


def _aggregated_result(evidence_manifest, report=None, outputs=None):
    return {
        "subtask_results": {
            "st_1": {
                "status": "completed",
                "result": {
                    "alignment_diagnostics": {
                        "preferred_scale": "street_block",
                        "maup_like_risk": "medium",
                    },
                    "distribution_preview": {},
                    "human_alignment": {
                        "stakeholder_feedback": [
                            {"group": "pedestrians", "concern": "unsafe crossing"}
                        ]
                    },
                    "correction_audit": [{"module": "scale_alignment"}],
                    "evidence_manifest": evidence_manifest,
                    "report": report,
                    "outputs": outputs or [],
                },
            }
        },
        "completed": 1,
        "total": 1,
    }


def test_review_hub_passes_with_complete_evidence_manifest():
    reviewer = SpatialReviewerAgent()
    evidence_manifest = {
        "spatial": {
            "bbox": [121.4, 31.2, 121.5, 31.3],
            "crs": "EPSG:4326",
            "admin_level": "district",
            "scale_band": "street_block",
            "spatial_relation_frame": "network_topology",
        },
        "temporal": {
            "timestamp": "2026-04-23T09:00:00",
            "time_window": "2026-04-23T08:00:00/2026-04-23T09:00:00",
            "granularity": "hourly",
            "forecast_horizon": "PT1H",
            "freshness": "current_day",
        },
        "population": {
            "target_group": "pedestrians",
            "observed_group": "pedestrians",
            "affected_group": "pedestrians_and_elderly",
            "sampling_bias": "low",
            "stakeholder_source": "street_intercept_survey",
        },
        "governance": {
            "provenance": "osm+survey",
            "license": "ODbL + consented survey",
            "collection_method": "api_and_field_survey",
            "uncertainty": "moderate",
            "missing_layers": [],
        },
        "tags": ["mobility", "walkability", "pedestrian"],
    }

    message = AgentMessage(
        sender=AgentRole.MANAGER,
        receiver=AgentRole.SPATIAL_REVIEWER,
        msg_type="review",
        payload=_aggregated_result(evidence_manifest, report="# Methods\nBased on evidence\n# Results", outputs=["svg_overlay"]),
    )
    result = asyncio.run(reviewer.execute(message))

    assert result.payload["passed"] is True
    assert "policy_scores" in result.payload
    assert result.payload["policy_scores"]["temporal_consistency_review"]["score"] >= 0.8


def test_review_hub_fails_without_population_and_governance_evidence():
    reviewer = SpatialReviewerAgent()
    evidence_manifest = {
        "spatial": {
            "bbox": [121.4, 31.2, 121.5, 31.3],
            "crs": "EPSG:4326",
        },
        "temporal": {
            "timestamp": "2026-04-23T09:00:00",
        },
        "tags": [],
    }

    message = AgentMessage(
        sender=AgentRole.MANAGER,
        receiver=AgentRole.SPATIAL_REVIEWER,
        msg_type="review",
        payload=_aggregated_result(evidence_manifest),
    )
    result = asyncio.run(reviewer.execute(message))

    assert result.payload["passed"] is False
    assert "population_and_stakeholder_review" in result.payload["hard_failures"]
    assert "evidence_and_governance_review" in result.payload["hard_failures"]