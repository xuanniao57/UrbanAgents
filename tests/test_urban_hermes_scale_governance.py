import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADAPTER_ROOT = ROOT / "hermes_urban_agent"
if str(ADAPTER_ROOT) not in sys.path:
    sys.path.insert(0, str(ADAPTER_ROOT))

from urban_hermes.scale_governance import audit_scale_branches


FEATURES = [
    "building_density",
    "building_coverage",
    "mean_height",
    "volume_proxy",
    "function_entropy",
    "poi_density",
    "poi_entropy",
    "road_density",
]


def _branch(branch_id: str, size_m: int):
    return {
        "branch_id": branch_id,
        "analysis_unit": {
            "size_m": size_m,
            "geometry": "square",
            "origin_id": "inner_ring_origin_v1",
            "aoi_id": "shanghai_inner_ring_v1",
        },
        "outcome_contract": {
            "definition": "log1p aggregate device stays",
            "temporal_scope": "2024-09-19/2024-09-25",
            "population_scope": "deterministic 10% device sample",
            "privacy_rule": "minimum 10 devices per released cell",
            "cohort_scheme": "all-age aggregate before release",
        },
        "feature_names": FEATURES,
        "validation_design": {
            "partition_id": "shared_macro_regions_v1",
            "fold_count": 5,
            "macro_region_artifact": "shared_folds.csv",
        },
        "model_protocol": {
            "candidate_families": ["OLS", "Ridge", "RF"],
            "tuning_protocol_id": "capacity_grid_v1",
            "metric_set": ["R2", "RMSE", "MAE", "Spearman"],
        },
        "empty_grid_policy": {
            "outside_aoi": "exclude",
            "true_zero": "retain only when observed before privacy suppression",
            "privacy_suppressed_or_unreleased": "unknown; never recode to zero",
            "covariate_missing": "report then impute within the training fold",
            "model_ready": "outcome and predictor keys aligned",
        },
    }


def test_harmonized_branches_admit_scale_component_claim():
    audit = audit_scale_branches([_branch("scale_500m", 500), _branch("scale_200m", 200)])
    assert audit["status"] == "pass"
    assert audit["pure_maup_scale_effect_admissible"] is True


def test_different_feature_set_qualifies_pure_scale_claim():
    fine = _branch("scale_200m", 200)
    fine["feature_names"] = [*FEATURES, "road_type_count"]
    audit = audit_scale_branches([_branch("scale_500m", 500), fine])
    assert audit["status"] == "qualify"
    assert audit["pure_maup_scale_effect_admissible"] is False
    assert any(issue["code"] == "feature_set_differs" for issue in audit["issues"])


def test_different_validation_geography_is_visible():
    fine = _branch("scale_200m", 200)
    fine["validation_design"]["partition_id"] = "scale_specific_kmeans"
    audit = audit_scale_branches([_branch("scale_500m", 500), fine])
    assert any(issue["code"] == "validation_partition_id_differs" for issue in audit["issues"])


def test_moran_cannot_directly_select_scale_or_model():
    diagnostics = [
        {
            "branch_id": "scale_500m",
            "residual_source": "out_of_fold repeat 1",
            "weight_kind": "knn",
            "k": 8,
            "decision_role": "select_scale",
        }
    ]
    audit = audit_scale_branches(
        [_branch("scale_500m", 500), _branch("scale_200m", 200)],
        diagnostics,
    )
    assert audit["status"] == "block"
    assert any(issue["code"] == "moran_used_as_selector" for issue in audit["issues"])


def test_string_nested_contract_is_blocked_without_crashing():
    malformed = _branch("scale_200m", 200)
    malformed["model_protocol"] = "OLS plus adaptive and fixed GWR"
    malformed["analysis_unit"] = "200 m square grid"
    audit = audit_scale_branches([_branch("scale_500m", 500), malformed])
    assert audit["status"] == "block"
    assert any(
        issue["code"] == "invalid_scale_contract_schema"
        for issue in audit["issues"]
    )
