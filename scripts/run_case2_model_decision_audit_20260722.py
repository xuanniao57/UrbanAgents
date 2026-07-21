"""Model-family and compute-budget audit for the Shanghai street-vitality case.

This script keeps three decisions separate:

1. the 500 m/200 m research-object resolution;
2. the evidence package used as predictors; and
3. the model family and its spatial parameters.

The paper-facing audit uses the selected 500 m, combined-evidence table.  It
does not rank unlike validation regimes as if their R-squared values were
interchangeable.  Global RF is reported with spatial-block validation, GWR as
a fitted local-association diagnostic, and GWRF with focal-location exclusion
plus an explicit neighbourhood sensitivity and runtime budget.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd
from mgwr.gwr import GWR
from mgwr.sel_bw import Sel_BW
from pyproj import Transformer
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler


PROJECT = Path(__file__).resolve().parents[1]
RUN = PROJECT / "experiments" / "case2_uuid10_multiroute_rerun_20260528_095026"
OUTPUT = PROJECT / "experiments" / "case2_model_decision_audit_20260722"


def load_combined_500m() -> tuple[pd.DataFrame, list[str]]:
    outputs = RUN / "outputs"
    outcome = pd.read_csv(outputs / "RO1_outcome_table.csv")
    outcome = outcome.groupby("grid_id", as_index=False).agg(stay_count=("stay_count", "sum"))
    outcome["log_stays"] = np.log1p(outcome["stay_count"])
    fp1 = pd.read_csv(outputs / "FP1_500m.csv")
    fp2 = pd.read_csv(outputs / "FP2_500m.csv").drop(columns=["osm_poi_count"], errors="ignore")
    centroids = pd.read_csv(outputs / "grid_centroids_500m.csv")
    frame = outcome.merge(fp1, on="grid_id").merge(fp2, on="grid_id").merge(centroids, on="grid_id")
    features = [c for c in fp1.columns if c != "grid_id"] + [c for c in fp2.columns if c != "grid_id"]
    frame[features] = SimpleImputer(strategy="median").fit_transform(frame[features])
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:32651", always_xy=True)
    x, y = transformer.transform(frame["lon"].to_numpy(), frame["lat"].to_numpy())
    frame["coord_x"] = x
    frame["coord_y"] = y
    return frame, features


def moran_knn(coords: np.ndarray, values: np.ndarray, k: int = 8, permutations: int = 999) -> dict[str, float]:
    centered = np.asarray(values, dtype=float) - np.nanmean(values)
    nn = NearestNeighbors(n_neighbors=min(k + 1, len(centered))).fit(coords)
    indices = nn.kneighbors(return_distance=False)[:, 1:]

    def statistic(vector: np.ndarray) -> float:
        lag = vector[indices].mean(axis=1)
        return float(np.dot(vector, lag) / np.dot(vector, vector))

    observed = statistic(centered)
    rng = np.random.default_rng(20260722)
    permuted = np.array([statistic(rng.permutation(centered)) for _ in range(permutations)])
    p = (np.sum(np.abs(permuted) >= abs(observed)) + 1) / (permutations + 1)
    return {"moran_i": observed, "permutation_p": float(p), "k": k}


def run_rf(frame: pd.DataFrame, features: list[str]) -> tuple[dict[str, object], pd.DataFrame]:
    X = frame[features].to_numpy()
    y = frame["log_stays"].to_numpy()
    groups = KMeans(n_clusters=5, n_init=20, random_state=100).fit_predict(
        StandardScaler().fit_transform(frame[["coord_x", "coord_y"]])
    )
    predictions = np.full(len(frame), np.nan)
    started = time.perf_counter()
    for train, test in GroupKFold(n_splits=5).split(X, groups=groups):
        model = RandomForestRegressor(
            n_estimators=200,
            max_depth=10,
            min_samples_leaf=5,
            max_features=0.8,
            random_state=42,
            n_jobs=-1,
        )
        model.fit(X[train], y[train])
        predictions[test] = model.predict(X[test])
    elapsed = time.perf_counter() - started
    residual = y - predictions
    saved_summary_path = PROJECT / "submissions" / "urban_cup_2026" / "outputs" / "model_validation_summary.csv"
    saved_findings_path = PROJECT / "submissions" / "urban_cup_2026" / "outputs" / "case_findings.json"
    saved_summary = pd.read_csv(saved_summary_path)
    repeated = saved_summary[
        (saved_summary["scale"] == "500m")
        & (saved_summary["package"] == "combined")
        & (saved_summary["model"] == "random_forest")
        & (saved_summary["scheme"] == "spatial_block")
    ].iloc[0]
    saved_findings = json.loads(saved_findings_path.read_text(encoding="utf-8"))
    repeated_moran = saved_findings["spatial_oof_residual_moran"]["500m"]
    result = {
        "model_family": "Global RF",
        "configuration": "200 trees; depth 10; min leaf 5; max features 0.8",
        "validation_regime": "five repeated 5-fold contiguous spatial-block holdout",
        "validation_r2": float(repeated["r2_mean"]),
        "validation_rmse": float(repeated["rmse_mean"]),
        "validation_mae": float(repeated["mae_mean"]),
        "residual_moran": repeated_moran,
        "synchronized_runtime_audit": {
            "single_5fold_r2": float(r2_score(y, predictions)),
            "single_5fold_residual_moran": moran_knn(frame[["coord_x", "coord_y"]].to_numpy(), residual),
            "timing_scope": "one five-fold audit using the registered RF configuration",
        },
        "elapsed_sec": elapsed,
        "claim_role": "Primary route for transferable within-city association",
        "decision": "admit_primary",
        "comparability_note": "R2 is the repeated estimate; runtime times one synchronized five-fold audit.",
    }
    output = frame[["grid_id", "lon", "lat", "coord_x", "coord_y", "log_stays"]].copy()
    output["prediction"] = predictions
    output["residual"] = residual
    return result, output


def run_gwr(frame: pd.DataFrame, features: list[str]) -> tuple[dict[str, object], pd.DataFrame]:
    coords = frame[["coord_x", "coord_y"]].to_numpy()
    X = StandardScaler().fit_transform(frame[features].to_numpy())
    y = StandardScaler().fit_transform(frame[["log_stays"]]).reshape(-1, 1)
    started = time.perf_counter()
    selector = Sel_BW(coords, y, X, fixed=False, kernel="bisquare", constant=True)
    bandwidth = int(round(float(selector.search(criterion="AICc"))))
    fit = GWR(coords, y, X, bw=bandwidth, fixed=False, kernel="bisquare", constant=True).fit()
    elapsed = time.perf_counter() - started
    residual = np.asarray(fit.resid_response).reshape(-1)
    params = np.asarray(fit.params)
    sign_stability = []
    for index, feature in enumerate(features, start=1):
        values = params[:, index]
        sign_stability.append(
            {
                "feature": feature,
                "positive_share": float(np.mean(values > 0)),
                "negative_share": float(np.mean(values < 0)),
                "median_coefficient": float(np.median(values)),
            }
        )
    result = {
        "model_family": "GWR",
        "configuration": f"adaptive bi-square bandwidth {bandwidth}; AICc-selected; standardized X/Y",
        "validation_regime": "fitted local-association diagnostic (not spatial holdout)",
        "fitted_r2": float(fit.R2),
        "aicc": float(fit.aicc),
        "residual_moran": moran_knn(coords, residual),
        "elapsed_sec": elapsed,
        "claim_role": "Conditional local linear coefficient diagnostic",
        "decision": "admit_diagnostic",
        "comparability_note": "Fitted R2 is intentionally not ranked against RF spatial-block R2.",
        "coefficient_sign_stability": sign_stability,
    }
    output = frame[["grid_id", "lon", "lat", "coord_x", "coord_y", "log_stays"]].copy()
    output["local_r2"] = np.asarray(fit.localR2).reshape(-1)
    output["residual"] = residual
    for index, feature in enumerate(features, start=1):
        output[f"coef__{feature}"] = params[:, index]
    return result, output


def run_gwrf_variant(
    frame: pd.DataFrame,
    features: list[str],
    k_neighbors: int,
    trees: int,
) -> tuple[dict[str, object], pd.DataFrame, pd.DataFrame]:
    coords = frame[["coord_x", "coord_y"]].to_numpy()
    X = frame[features].to_numpy()
    y = frame["log_stays"].to_numpy()
    nn = NearestNeighbors(n_neighbors=min(k_neighbors + 1, len(frame))).fit(coords)
    distances, indices = nn.kneighbors(coords)
    predictions = np.zeros(len(frame))
    importances = np.zeros((len(frame), len(features)))
    started = time.perf_counter()
    for focal in range(len(frame)):
        candidate = indices[focal]
        distance = distances[focal]
        keep = candidate != focal
        train = candidate[keep][:k_neighbors]
        train_distance = distance[keep][:k_neighbors]
        bandwidth = max(float(train_distance.max()), 1.0)
        weights = np.exp(-0.5 * (train_distance / bandwidth) ** 2)
        model = RandomForestRegressor(
            n_estimators=trees,
            max_depth=8,
            min_samples_leaf=3,
            random_state=1000 + focal,
            n_jobs=1,
        )
        model.fit(X[train], y[train], sample_weight=weights)
        predictions[focal] = model.predict(X[focal].reshape(1, -1))[0]
        importances[focal] = model.feature_importances_
    elapsed = time.perf_counter() - started
    residual = y - predictions
    result = {
        "model_family": "GWRF",
        "configuration": f"adaptive Gaussian k={k_neighbors}; {trees} trees/location; depth 8; min leaf 3",
        "k_neighbors": k_neighbors,
        "trees_per_location": trees,
        "validation_regime": "leave-focal-location-out local prediction",
        "validation_r2": float(r2_score(y, predictions)),
        "validation_rmse": float(math.sqrt(mean_squared_error(y, predictions))),
        "validation_mae": float(mean_absolute_error(y, predictions)),
        "residual_moran": moran_knn(coords, residual),
        "elapsed_sec": elapsed,
        "claim_role": "Exploratory local non-linear reliance and heterogeneity",
        "decision": "candidate_sensitivity",
        "comparability_note": "Leave-location-out neighborhoods are less stringent than contiguous spatial-block holdout.",
    }
    predictions_frame = frame[["grid_id", "lon", "lat", "coord_x", "coord_y", "log_stays"]].copy()
    predictions_frame["prediction"] = predictions
    predictions_frame["residual"] = residual
    importance_frame = pd.DataFrame(importances, columns=features)
    importance_frame.insert(0, "grid_id", frame["grid_id"].to_numpy())
    return result, predictions_frame, importance_frame


def decision_rows(rf: dict[str, object], gwr: dict[str, object], gwrf: list[dict[str, object]]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for record in [rf, gwr, *gwrf]:
        residual = record["residual_moran"]
        rows.append(
            {
                "model_family": record["model_family"],
                "configuration": record["configuration"],
                "validation_regime": record["validation_regime"],
                "reported_r2": record.get("validation_r2", record.get("fitted_r2")),
                "r2_kind": "validation" if "validation_r2" in record else "fitted_diagnostic",
                "residual_moran_i": residual["moran_i"],
                "residual_moran_p": residual["permutation_p"],
                "elapsed_sec": record["elapsed_sec"],
                "claim_role": record["claim_role"],
                "decision": record["decision"],
                "comparability_note": record["comparability_note"],
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-gwr", action="store_true")
    parser.add_argument("--gwrf-k", nargs="+", type=int, default=[48, 80, 120])
    parser.add_argument("--trees", type=int, default=60)
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    frame, features = load_combined_500m()
    frame.to_csv(OUTPUT / "model_ready_500m_combined.csv", index=False)

    rf, rf_predictions = run_rf(frame, features)
    rf_predictions.to_csv(OUTPUT / "rf_spatial_block_predictions.csv", index=False)

    if args.skip_gwr and (OUTPUT / "gwr_summary.json").exists():
        gwr = json.loads((OUTPUT / "gwr_summary.json").read_text(encoding="utf-8"))
    else:
        gwr, gwr_output = run_gwr(frame, features)
        gwr_output.to_csv(OUTPUT / "gwr_local_diagnostics.csv", index=False)
        (OUTPUT / "gwr_summary.json").write_text(json.dumps(gwr, indent=2), encoding="utf-8")

    gwrf_results: list[dict[str, object]] = []
    for k in args.gwrf_k:
        result, predictions, importances = run_gwrf_variant(frame, features, k, args.trees)
        gwrf_results.append(result)
        predictions.to_csv(OUTPUT / f"gwrf_k{k}_predictions.csv", index=False)
        importances.to_csv(OUTPUT / f"gwrf_k{k}_local_importance.csv", index=False)

    admitted = min(gwrf_results, key=lambda item: item["validation_rmse"])
    for result in gwrf_results:
        result["decision"] = "retain_bounded_local_branch" if result is admitted else "retain_parameter_sensitivity"

    decision = {
        "research_object": "500 m main analysis; 200 m retained separately as resolution sensitivity",
        "evidence_package": "combined built-form and local-opportunity variables",
        "features": features,
        "models": {"rf": rf, "gwr": gwr, "gwrf": gwrf_results},
        "merge_rule": {
            "primary": "RF supplies the spatial-holdout-backed within-city association claim.",
            "local_linear": "GWR supplies coefficient geography only; its fitted R2 is not used to select the primary model.",
            "local_nonlinear": f"GWRF k={admitted['k_neighbors']} is retained as a bounded local sensitivity branch under the measured runtime budget.",
            "blocked": "No branch supports causal effects, resident-population inference, or a universal local mechanism.",
        },
    }
    (OUTPUT / "model_decision_audit.json").write_text(json.dumps(decision, indent=2), encoding="utf-8")
    table = decision_rows(rf, gwr, gwrf_results)
    table.to_csv(OUTPUT / "model_decision_table.csv", index=False)
    print(table.to_string(index=False))
    print(json.dumps(decision["merge_rule"], indent=2))


if __name__ == "__main__":
    main()
