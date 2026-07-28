"""Build the concise, evidence-backed Git-tree state used by the live frontend.

The full May execution state remains preserved.  This derived July state makes
the paper/competition decision logic readable without rewriting that history.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
RUN = ROOT / "experiments" / "case2_uuid10_multiroute_rerun_20260528_095026" / "outputs"
AUDIT = ROOT / "experiments" / "case2_model_decision_audit_20260722"
SUBMISSION = ROOT / "submissions" / "urban_cup_2026"
OUTPUT = SUBMISSION / "outputs"
PROCESS = SUBMISSION / "process_evidence"


VARIABLES = [
    ("Built form", "CMAB buildings", "cmab_building_density_per_ha", "Building count per hectare", "Place morphology; no people observed"),
    ("Built form", "CMAB buildings", "cmab_building_coverage_ratio", "Footprint share of grid area", "Place morphology; no people observed"),
    ("Built form", "CMAB buildings", "cmab_mean_height_m", "Mean building height", "Place morphology; no people observed"),
    ("Built form", "CMAB buildings", "cmab_volume_proxy_per_ha", "Footprint-area x height per hectare", "Morphological proxy; not floor area"),
    ("Built form", "CMAB buildings", "cmab_function_entropy", "Diversity of building-function labels", "Label-derived land-use proxy"),
    ("Local opportunity", "OpenStreetMap POIs", "osm_poi_density_per_ha", "Mapped destinations per hectare", "Opportunity context; not visits"),
    ("Local opportunity", "OpenStreetMap POIs", "osm_poi_type_entropy", "Diversity of mapped POI types", "Opportunity diversity; not preference"),
    ("Local opportunity", "OpenStreetMap roads", "osm_road_density_m_per_ha", "Mapped road length per hectare", "Network supply; not experienced access"),
]

VARIABLE_LABELS = {
    "cmab_building_density_per_ha": "Building density",
    "cmab_building_coverage_ratio": "Building coverage",
    "cmab_mean_height_m": "Mean height",
    "cmab_volume_proxy_per_ha": "Volume proxy",
    "cmab_function_entropy": "Function entropy",
    "osm_poi_density_per_ha": "POI density",
    "osm_poi_type_entropy": "POI-type entropy",
    "osm_road_density_m_per_ha": "Road density",
}


def load_scale_frame(scale: str) -> pd.DataFrame:
    suffix = "500m" if scale == "500m" else "200m"
    research_object = "RO1_outcome_table.csv" if scale == "500m" else "RO2_outcome_table.csv"
    valid = set(pd.read_csv(RUN / research_object)["grid_id"].astype(str))
    fp1 = pd.read_csv(RUN / f"FP1_{suffix}.csv")
    fp2 = pd.read_csv(RUN / f"FP2_{suffix}.csv")
    centroids = pd.read_csv(RUN / f"grid_centroids_{suffix}.csv")
    frame = fp1.merge(fp2, on="grid_id", how="outer").merge(centroids, on="grid_id", how="left")
    frame["grid_id"] = frame["grid_id"].astype(str)
    return frame[frame["grid_id"].isin(valid)].copy()


def build_variable_coverage() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for scale in ("500m", "200m"):
        frame = load_scale_frame(scale)
        for package, _, variable, _, _ in VARIABLES:
            values = pd.to_numeric(frame[variable], errors="coerce").fillna(0)
            rows.append(
                {
                    "scale": scale,
                    "package": package,
                    "variable": variable,
                    "variable_label": VARIABLE_LABELS[variable],
                    "coverage_pct": 100 * float(np.mean(values != 0)),
                    "n_model_ready": len(frame),
                }
            )
    coverage = pd.DataFrame(rows)
    coverage.to_csv(OUTPUT / "variable_coverage_by_scale.csv", index=False)
    return coverage


def build_variable_spatial_frame() -> pd.DataFrame:
    frame = load_scale_frame("500m")
    selected = frame[
        [
            "grid_id",
            "lon",
            "lat",
            "cmab_building_coverage_ratio",
            "osm_poi_density_per_ha",
        ]
    ].copy()
    selected.to_csv(OUTPUT / "variable_spatial_500m.csv", index=False)
    return selected


def build_variable_audit() -> pd.DataFrame:
    outcome = pd.read_csv(RUN / "RO1_outcome_table.csv")
    valid = set(outcome["grid_id"].astype(str))
    fp1 = pd.read_csv(RUN / "FP1_500m.csv")
    fp2 = pd.read_csv(RUN / "FP2_500m.csv")
    source = fp1.merge(fp2, on="grid_id", how="outer")
    source["grid_id"] = source["grid_id"].astype(str)
    source = source[source["grid_id"].isin(valid)].copy()
    rows = []
    for package, data_source, variable, meaning, people in VARIABLES:
        values = pd.to_numeric(source[variable], errors="coerce")
        rows.append(
            {
                "package": package,
                "data_source": data_source,
                "variable": variable,
                "operational_meaning": meaning,
                "spatial_support": f"500 m grid; {100 * np.mean(values.fillna(0) != 0):.1f}% non-zero ({len(source)} model-ready grids)",
                "time_support": "Cross-sectional context paired with the seven-day activity outcome",
                "people_support": people,
                "claim_boundary": "Area-level association only",
            }
        )
    audit = pd.DataFrame(rows)
    audit.to_csv(OUTPUT / "variable_evidence_register.csv", index=False)
    return audit


def node(
    node_id: str,
    node_type: str,
    label: str,
    step: int,
    deps: list[str],
    status: str,
    question: str,
    claim: str,
    params: dict[str, object] | None = None,
    outputs: list[str] | None = None,
) -> dict[str, object]:
    return {
        "node_id": node_id,
        "node_type": node_type,
        "display_label": label,
        "step_id": f"S{step}",
        "depends_on": deps,
        "status": status,
        "question": question,
        "claim_boundary": claim,
        "required_parameters": params or {},
        "expected_outputs": outputs or [],
        "time_space_people": {
            "time": "Seven-day activity outcome (19--25 September 2024); static explanatory context.",
            "space": "Shanghai inner-ring analysis on a 500 m main grid; 200 m retained as resolution sensitivity.",
            "people": "Observed device-user activity, not the resident population or individual behaviour.",
        },
    }


def build_state(variable_audit: pd.DataFrame, decision: dict[str, object]) -> dict[str, object]:
    models = decision["models"]
    rf = models["rf"]
    gwr = models["gwr"]
    gwrf = models["gwrf"]
    gwrf_by_k = {int(item["k_neighbors"]): item for item in gwrf}
    retained = next(item for item in gwrf if item["decision"] == "retain_bounded_local_branch")

    nodes = [
        node("RO_500m_main", "research_object", "500 m main object", 1, [], "selected", "Define street vitality as aggregate observed device stays on 500 m grids.", "Street-vitality proxy for observed device activity; not resident vitality.", {"grid": "500 m", "n": 509, "outcome": "log1p aggregate stays"}),
        node("RO_200m_sensitivity", "research_object", "200 m sensitivity", 1, [], "suggested", "Retain a finer grid to test resolution dependence without conflating it with model parameters.", "Scale sensitivity only; privacy-eligible coverage differs.", {"grid": "200 m", "n": 2542}),
        node("FP1_built_form", "feature_package", "Built-form evidence", 2, ["RO_500m_main"], "selected", "Which physical-form variables have defensible spatial and semantic support?", "Area morphology proxies only; no people directly observed.", {"variables": int((variable_audit.package == "Built form").sum()), "source": "CMAB"}, ["variable_evidence_register.csv"]),
        node("FP2_activity_opportunity", "feature_package", "Local-opportunity evidence", 2, ["RO_500m_main"], "selected", "Which mapped destinations and roads can represent local opportunity?", "Mapped opportunity context, not visits, preferences, or network accessibility.", {"variables": int((variable_audit.package == "Local opportunity").sum()), "source": "OpenStreetMap"}, ["variable_evidence_register.csv"]),
        node("ME_RF_spatial_block", "model_execution", "RF / global transfer", 3, ["FP1_built_form", "FP2_activity_opportunity"], "selected", "Can the combined evidence predict held-out contiguous zones?", "Within-city predictive association only.", {"configuration": rf["configuration"], "validation": rf["validation_regime"], "runtime_sec": round(rf["elapsed_sec"], 1)}, ["rf_spatial_block_predictions.csv"]),
        node("ME_GWR_local_linear", "model_execution", "GWR / local linear", 3, ["FP1_built_form", "FP2_activity_opportunity"], "selected", "Where do fitted local linear coefficients vary under an AICc-selected bandwidth?", "Local coefficient geography is diagnostic, not held-out predictive superiority.", {"configuration": gwr["configuration"], "validation": gwr["validation_regime"], "runtime_sec": round(gwr["elapsed_sec"], 1)}, ["gwr_local_diagnostics.csv"]),
    ]
    for k in sorted(gwrf_by_k):
        item = gwrf_by_k[k]
        nodes.append(
            node(
                f"ME_GWRF_k{k}",
                "model_execution",
                f"GWRF / k={k}",
                3,
                ["FP1_built_form", "FP2_activity_opportunity"],
                "selected" if k == int(retained["k_neighbors"]) else "suggested",
                "How sensitive is local non-linear prediction to the spatial-neighbourhood parameter?",
                "Exploratory local predictive heterogeneity; less stringent than spatial-block transfer.",
                {"configuration": item["configuration"], "validation": item["validation_regime"], "runtime_sec": round(item["elapsed_sec"], 1)},
                [f"gwrf_k{k}_predictions.csv", f"gwrf_k{k}_local_importance.csv"],
            )
        )
    nodes.extend(
        [
            node("DIAG_RF_residual", "diagnostic", "Residual geography", 4, ["ME_RF_spatial_block"], "selected", "Do held-out RF errors remain spatially clustered?", "Significant residual structure blocks a complete-mechanism claim.", {"moran_i": round(rf["residual_moran"]["moran_i"], 3), "p": rf["residual_moran"]["permutation_p"]}),
            node("DIAG_GWR_interpretation", "diagnostic", "Coefficient stability", 4, ["ME_GWR_local_linear"], "selected", "Are local coefficient signs stable enough for descriptive mapping?", "Maps describe fitted conditional variation; they do not identify effects."),
            node("DIAG_GWRF_budget", "diagnostic", "Parameter + runtime", 4, [f"ME_GWRF_k{k}" for k in sorted(gwrf_by_k)], "selected", "Which GWRF neighbourhood remains informative within the measured compute budget?", "Retain one bounded branch and disclose all tested configurations."),
            node("RC_model_family_merge", "route_comparison", "Model-role merge", 5, ["DIAG_RF_residual", "DIAG_GWR_interpretation", "DIAG_GWRF_budget"], "merged", "Which model evidence is admitted for which scientific role?", "Merge evidence by claim role, not by selecting the largest unlike R-squared.", {"primary": "RF spatial transfer", "local_linear": "GWR diagnostic", "local_nonlinear": f"GWRF k={int(retained['k_neighbors'])} sensitivity"}, ["model_decision_table.csv", "model_decision_audit.json"]),
            node("CS_bounded_street_vitality", "claim_synthesis", "Bounded street-vitality claims", 6, ["RC_model_family_merge", "RO_200m_sensitivity"], "merged", "What can the case responsibly say about street vitality?", "Permit aggregate associations and parameter-sensitive local patterns; block causal, individual, and resident-population claims."),
        ]
    )

    edges = []
    for item in nodes:
        for dep in item["depends_on"]:
            edges.append({"source": dep, "target": item["node_id"], "relation": "depends_on", "operation": "reviewed transition"})
    active = [item["node_id"] for item in nodes if item["status"] in {"selected", "merged"}]
    suggested = [item["node_id"] for item in nodes if item["status"] == "suggested"]
    merged = [item["node_id"] for item in nodes if item["status"] == "merged"]
    return {
        "schema_version": "urban_case_decision_git_tree_v2",
        "meta": {
            "state_id": "street_vitality_model_decision_20260722",
            "task": "Audit evidence and model-family decisions for Shanghai street vitality",
            "updated_at": "2026-07-22T18:00:00+08:00",
        },
        "planner_todo": [
            {"step_id": f"S{i}", "title": title, "status": "completed"}
            for i, title in enumerate(["Research object", "Variable evidence", "Model branch", "Diagnostics", "Compare and merge", "Claim synthesis"], start=1)
        ],
        "nodes": nodes,
        "edges": edges,
        "visual_edges": edges,
        "active_path": active,
        "main_path": ["RO_500m_main", "FP1_built_form", "ME_RF_spatial_block", "DIAG_RF_residual", "RC_model_family_merge", "CS_bounded_street_vitality"],
        "branch_tree": {"active": active, "suggested": suggested, "deferred": [], "blocked": [], "merged": merged},
        "dialogue": [
            {"role": "user", "title": "Research framing", "body": "Explain the spatial pattern of Shanghai street vitality without hiding consequential data or model choices."},
            {"role": "agent", "title": "Evidence branch", "body": "I separated built-form evidence from local-opportunity evidence and audited what each variable measures across space, time, and people."},
            {"role": "agent", "title": "Model branch", "body": "Residual geography triggered GWR and GWRF branches. Their fitted or local validation scores are not treated as interchangeable with contiguous spatial-block transfer."},
            {"role": "human", "title": "Authorization", "body": "Use RF for the primary association; retain GWR and the selected GWRF setting as bounded local diagnostics; block causal and population-wide claims."},
        ],
        "artifact_index": [],
        "claim_options": decision["merge_rule"],
    }


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    PROCESS.mkdir(parents=True, exist_ok=True)
    variable_audit = build_variable_audit()
    variable_coverage = build_variable_coverage()
    variable_spatial = build_variable_spatial_frame()
    decision = json.loads((AUDIT / "model_decision_audit.json").read_text(encoding="utf-8"))
    for filename in [
        "model_decision_table.csv",
        "model_decision_audit.json",
        "rf_spatial_block_predictions.csv",
        "gwr_local_diagnostics.csv",
        *[f"gwrf_k{k}_{suffix}.csv" for k in [48, 80, 120] for suffix in ["predictions", "local_importance"]],
    ]:
        source = AUDIT / filename
        if source.exists():
            shutil.copy2(source, OUTPUT / filename)
    state = build_state(variable_audit, decision)
    (PROCESS / "case_decision_git_tree_20260722.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(
        f"Wrote {len(variable_audit)} variable rows, {len(variable_coverage)} coverage rows, "
        f"{len(variable_spatial)} mapped grids, and {len(state['nodes'])} Git-tree nodes"
    )


if __name__ == "__main__":
    main()
