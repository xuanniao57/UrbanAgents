import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from urban_agent.agents.base import AgentMessage, AgentRole
from urban_agent.agents.reviewers import SpatialReviewerAgent
from urban_agent.feedback_memory import FeedbackMemory


_feedback_mem = FeedbackMemory()


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
    reviewer = SpatialReviewerAgent(feedback_memory=_feedback_mem)
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
    reviewer = SpatialReviewerAgent(feedback_memory=_feedback_mem)
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


def test_review_hub_flags_unclipped_formal_gis_layers():
    reviewer = SpatialReviewerAgent(feedback_memory=_feedback_mem)
    evidence_manifest = {
        "spatial": {"bbox": [121.4, 31.2, 121.5, 31.3], "crs": "EPSG:4326"},
        "governance": {
            "provenance": "osm",
            "license": "ODbL",
            "collection_method": "local cache",
            "uncertainty": "cache extent may exceed AOI",
            "missing_layers": [],
        },
        "tags": ["gis"],
    }
    payload = _aggregated_result(
        evidence_manifest,
        outputs=["gis_layer_package"],
    )
    result_payload = payload["subtask_results"]["st_1"]["result"]
    result_payload.update({
        "artifact_role": "formal_gis",
        "layer_stack": {"roads": "run.gpkg|layername=roads"},
        "legend": {"roads": {"label": "Road centerlines"}},
        "alignment_diagnostics": {
            "status": "aligned_with_warnings",
            "issues": [],
            "layers": {
                "roads": {
                    "source_feature_count": 100,
                    "exported_feature_count": 100,
                    "source_outside_aoi_feature_ratio": 0.72,
                    "output_clipped_to_aoi": False,
                }
            },
        },
    })

    message = AgentMessage(
        sender=AgentRole.MANAGER,
        receiver=AgentRole.SPATIAL_REVIEWER,
        msg_type="review",
        payload=payload,
    )
    result = asyncio.run(reviewer.execute(message))

    assert any("without clipping" in warning for warning in result.payload["warnings"])


def test_review_hub_flags_metric_csv_without_spatial_result_layer():
    reviewer = SpatialReviewerAgent(feedback_memory=_feedback_mem)
    evidence_manifest = {
        "spatial": {"bbox": [121.4, 31.2, 121.5, 31.3], "crs": "EPSG:4326"},
        "temporal": {"time_window": "local cache", "granularity": "feature-level", "freshness": "local"},
        "population": {
            "target_group": "pedestrians",
            "observed_group": "pedestrians",
            "affected_group": "pedestrians",
            "stakeholder_source": "expert review",
        },
        "governance": {
            "provenance": "osm",
            "license": "ODbL",
            "collection_method": "local cache",
            "uncertainty": "cache extent may exceed AOI",
            "missing_layers": [],
        },
        "tags": ["gis"],
    }
    payload = _aggregated_result(
        evidence_manifest,
        outputs=["gis_layer_package", "metric_csv", "chart_png"],
    )
    result_payload = payload["subtask_results"]["st_1"]["result"]
    result_payload.update({
        "artifact_role": "formal_gis",
        "layer_stack": {"roads": "run.gpkg|layername=roads"},
        "legend": {"roads": {"label": "Road centerlines"}},
        "alignment_diagnostics": {
            "status": "aligned_with_context_buffer",
            "issues": [],
            "context_buffer": {
                "status": "generated",
                "width_factor": 3.0,
                "height_factor": 3.0,
                "area_ratio_to_aoi_bbox": 9.0,
                "centered_on_aoi": True,
            },
            "metric_spatialization": {"status": "failed"},
            "layers": {},
        },
    })

    message = AgentMessage(
        sender=AgentRole.MANAGER,
        receiver=AgentRole.SPATIAL_REVIEWER,
        msg_type="review",
        payload=payload,
    )
    result = asyncio.run(reviewer.execute(message))

    assert any("not spatialized" in warning for warning in result.payload["warnings"])