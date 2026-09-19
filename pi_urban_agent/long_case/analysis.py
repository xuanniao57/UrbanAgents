"""Portable, actual OLS/GWR analysis of already-harmonized released grid tables.

No event/device records, saved model results, network access, plotting, or automatic
model selection are used. Full-sample coefficient exploration is primary; optional
five shared-region holdouts are auxiliary predictive-transfer diagnostics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

FEATURES = (
    "cmab_building_density_per_ha", "cmab_building_coverage_ratio",
    "cmab_mean_height_m", "cmab_volume_proxy_per_ha", "cmab_function_entropy",
    "osm_poi_density_per_ha", "osm_poi_type_entropy", "osm_road_density_m_per_ha",
)
SCALES = (200, 300, 400, 500, 600, 700, 800)
MIN_NEIGHBOURS = 20
VERSION = "1.0.0"
LIMITS = [
    "Inputs are already harmonized aggregates; this tool does not aggregate raw device data.",
    "Full-sample scores describe fit, not held-out predictive accuracy.",
    "Local coefficients are descriptive associations, not causal effects or significance tests.",
    "Support resolution and kernel bandwidth are distinct; no optimal choice is declared.",
    "Two sampled days and fixed zoning do not establish population-wide or complete MAUP claims.",
    "Shared-region OOF is auxiliary; choosing bandwidth on its scores requires separate confirmation.",
    "Rank-deficient or ill-conditioned fits need caution; positive shares are not significance shares.",
]


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, (np.integer, np.floating)):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def write_json(path, payload):
    Path(path).write_text(json.dumps(clean(payload), ensure_ascii=False, indent=2,
                                    allow_nan=False), encoding="utf-8")


def emit(payload, limit=None):
    payload = clean(payload)
    if limit:
        # Keep valid JSON and explicitly mark that only a preview is printed.
        for key in ("coefficient_preview", "model_preview", "rows"):
            while (len(json.dumps(payload, ensure_ascii=False)) > limit
                   and payload.get(key)):
                payload[key].pop()
                payload["preview_truncated"] = True
    print(json.dumps(payload, ensure_ascii=False, allow_nan=False))


def fresh_output(path):
    if path is None:
        raise ValueError("--out is required for fit and compare")
    path = Path(path).resolve()
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise ValueError(f"Output must be a new or empty directory: {path}; choose a unique --out")
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_scale(root, scale, geometry_only=False):
    wanted = ["grid_id", "scale_m", "x_m", "y_m"]
    frame = pd.read_csv(root / f"model_ready_{scale}m.csv",
                        usecols=wanted if geometry_only else None)
    needed = wanted if geometry_only else wanted + list(FEATURES) + ["log_stay_count"]
    missing = sorted(set(needed) - set(frame.columns))
    if missing:
        raise ValueError(f"{scale} m missing required columns: {missing}")
    if frame.empty or frame.grid_id.isna().any() or frame.grid_id.duplicated().any():
        raise ValueError(f"{scale} m has empty or non-unique grid IDs")
    if not frame.scale_m.eq(scale).all():
        raise ValueError(f"{scale} m has inconsistent scale_m")
    finite = ["x_m", "y_m"] + ([] if geometry_only else ["log_stay_count"])
    if not np.isfinite(frame[finite].to_numpy(dtype=float)).all():
        raise ValueError(f"{scale} m has non-finite coordinates or outcome")
    if not geometry_only:
        x = frame[list(FEATURES)].to_numpy(dtype=float)
        if np.isinf(x).any():
            raise ValueError(f"{scale} m predictors contain infinity; inventory and repair inputs first")
        if np.isnan(x).all(axis=0).any():
            raise ValueError(f"{scale} m has an entirely missing predictor; all eight must be retained")
        if "stay_count" in frame:
            stays = frame.stay_count.to_numpy(dtype=float)
            if (not np.isfinite(stays).all() or (stays < 0).any()
                    or not np.allclose(np.log1p(stays), frame.log_stay_count, atol=1e-10)):
                raise ValueError(f"{scale} m log_stay_count differs from log1p(stay_count)")
    return frame.reset_index(drop=True)


def shared_groups(root, frame):
    assignments = pd.read_csv(root / "shared_macro_fold_assignments.csv")
    scale = int(frame.scale_m.iloc[0])
    if "scale_m" in assignments:
        assignments = assignments.loc[assignments.scale_m.eq(scale)]
    merged = frame[["grid_id"]].merge(assignments[["grid_id", "macro_region"]],
                                      how="left", on="grid_id", validate="one_to_one")
    if merged.macro_region.isna().any() or merged.macro_region.nunique() != 5:
        raise ValueError(f"{scale} m requires complete assignments to exactly five shared regions")
    return merged.macro_region.to_numpy()


def partitions(root, frame, validation):
    indexes = np.arange(len(frame))
    yield "full_sample", -1, indexes, indexes
    if validation == "shared_regions":
        groups = shared_groups(root, frame)
        for fold, (train, test) in enumerate(GroupKFold(n_splits=5).split(frame, groups=groups)):
            yield "shared_regions_oof", fold, train, test


def kernel_neighbours(train_xy, test_xy, model, bandwidth):
    """Exactly the corrected experiment's search/radius convention."""
    if model == "gwr_adaptive":
        k = min(max(MIN_NEIGHBOURS, int(math.ceil(bandwidth * len(train_xy)))), len(train_xy))
        search = NearestNeighbors(n_neighbors=k, algorithm="auto").fit(train_xy)
        distances, indices = search.kneighbors(test_xy, return_distance=True)
        radii = np.maximum(distances[:, -1], 1.0) * (1.0 + 1e-9)
    else:
        search = NearestNeighbors(radius=bandwidth).fit(train_xy)
        distances, indices = search.radius_neighbors(test_xy, return_distance=True, sort_results=True)
        radii = np.full(len(test_xy), bandwidth)
    return distances, indices, radii


def solve(train_xy, x_train, y_train, test_xy, x_test, model, bandwidth):
    """Return predictions, X-standardized coefficients and row-wise diagnostics."""
    design = np.column_stack([np.ones(len(x_train)), x_train])
    test_design = np.column_stack([np.ones(len(x_test)), x_test])
    if model == "ols":
        estimator = LinearRegression().fit(x_train, y_train)
        beta = np.r_[estimator.intercept_, estimator.coef_]
        betas = np.tile(beta, (len(x_test), 1))
        diagnostics = pd.DataFrame({
            "rank": np.repeat(np.linalg.matrix_rank(design), len(x_test)),
            "condition_number": np.repeat(np.linalg.cond(design), len(x_test)),
            "neighbour_count": len(x_train), "radius_m": np.nan,
            "effective_neighbours": float(len(x_train)),
        })
        return estimator.predict(x_test), betas, diagnostics
    distances, indices, radii = kernel_neighbours(train_xy, test_xy, model, bandwidth)
    betas = np.empty((len(x_test), design.shape[1]))
    rows = []
    for i, (distance, index, radius) in enumerate(zip(distances, indices, radii)):
        if len(index) < MIN_NEIGHBOURS:
            raise ValueError(f"{model} bandwidth {bandwidth:g} gives {len(index)} neighbours "
                             f"at predicted row {i}; minimum {MIN_NEIGHBOURS}. Run feasibility first.")
        weights = np.square(np.maximum(0.0, 1.0 - np.square(distance / radius)))
        # Compatibility floor keeps boundary neighbours in the same numerical fit.
        weights = np.maximum(weights, 1e-12)
        root = np.sqrt(weights)
        local_design = design[index] * root[:, None]
        betas[i], _, rank, singular = np.linalg.lstsq(local_design, y_train[index] * root, rcond=None)
        condition = float(singular[0] / singular[-1]) if singular[-1] > 0 else float("inf")
        rows.append({"rank": int(rank), "condition_number": condition,
                     "neighbour_count": len(index), "radius_m": float(radius),
                     "effective_neighbours": float(weights.sum() ** 2 / np.square(weights).sum())})
    return np.einsum("ij,ij->i", test_design, betas), betas, pd.DataFrame(rows)


def coefficient_summary(rows, spatial=False):
    keys = ["scale_m", "model", "bandwidth", "scope"] + (["quadrant"] if spatial else [])
    result = []
    for key, part in rows.groupby(keys, sort=True, dropna=False):
        base = dict(zip(keys, key))
        for variable in ("intercept",) + FEATURES:
            for units in ("native", "x_standardized"):
                values = part[f"{units}__{variable}"].to_numpy()
                finite = values[np.isfinite(values)]
                if not len(finite):
                    continue
                q25, median, q75 = np.quantile(finite, [0.25, 0.5, 0.75])
                result.append({**base, "variable": variable, "coefficient_units": units,
                               "n": len(values), "finite_n": len(finite), "median": median,
                               "q25": q25, "q75": q75, "iqr": q75 - q25,
                               "positive_share": float(np.mean(finite > 0)),
                               "negative_share": float(np.mean(finite < 0)),
                               "rank_deficient_share": float(np.mean(part["rank"] < 9))})
    return pd.DataFrame(result)


def inventory(args):
    rows = []
    for scale in args.scales:
        path = args.data_root / f"model_ready_{scale}m.csv"
        frame = pd.read_csv(path)
        numeric = frame.select_dtypes(include=np.number)
        support_path = args.data_root / f"grid_supports_{scale}m.geojson"
        support = json.loads(support_path.read_text(encoding="utf-8")) if support_path.exists() else None
        rows.append({"scale_m": scale, "shape": list(frame.shape), "columns": frame.columns.tolist(),
                     "missing_by_column": {k: int(v) for k, v in frame.isna().sum().items()},
                     "nonfinite_numeric_by_column": {k: int((~np.isfinite(v)).sum()) for k, v in numeric.items()},
                     "duplicate_grid_ids": int(frame.grid_id.duplicated().sum()),
                     "csv_sha256": sha256(path),
                     "support_count": len(support.get("features", [])) if support else None,
                     "support_sha256": sha256(support_path) if support else None,
                     "missing_required_columns": sorted(set(FEATURES + ("log_stay_count", "x_m", "y_m")) - set(frame.columns))})
    payload = {"action": "inventory", "input_status": "already_harmonized_grid_aggregates", "rows": rows}
    if args.out:
        out = fresh_output(args.out)
        write_json(out / "inventory.json", payload)
        payload["report"] = str(out / "inventory.json")
    compact = {"action": "inventory", "input_status": "already_harmonized_grid_aggregates",
               "columns": rows[0]["columns"], "rows": []}
    for row in rows:
        item = {"scale_m": row["scale_m"], "shape": row["shape"],
                "missing": sum(row["missing_by_column"].values()),
                "nonfinite_numeric": sum(row["nonfinite_numeric_by_column"].values()),
                "duplicate_grid_ids": row["duplicate_grid_ids"],
                "sha256": row["csv_sha256"], "support_count": row["support_count"]}
        if row["columns"] != compact["columns"]:
            item["columns"] = row["columns"]
        if row["missing_required_columns"]:
            item["missing_required_columns"] = row["missing_required_columns"]
        compact["rows"].append(item)
    if "report" in payload:
        compact["report"] = payload["report"]
    compact["detail"] = "Use --out NEW_DIRECTORY to save full per-column counts and support hashes."
    emit(compact, limit=3000)


def candidates(args):
    models = [args.model] if args.model else (["gwr_fixed", "gwr_adaptive"] if args.action == "feasibility" else ["ols"])
    if args.bandwidths and len(models) != 1:
        raise ValueError("Specify --model when providing --bandwidths (metres vs fractions)")
    result = []
    for model in models:
        if model == "ols":
            if args.bandwidths:
                raise ValueError("OLS has no bandwidth; omit --bandwidths")
            values = [0.0]
        else:
            default = [1000.0, 2000.0, 4000.0, 7000.0] if model == "gwr_fixed" else [0.1, 0.2, 0.3]
            values = args.bandwidths or (default if args.action == "feasibility" else default[:1])
            for value in values:
                if not math.isfinite(value) or value <= 0 or (model == "gwr_adaptive" and value > 1):
                    raise ValueError("Bandwidth must be finite positive metres, or an adaptive fraction in (0, 1]")
        result.extend((model, value) for value in values)
    return result


def feasibility(args):
    rows = []
    for scale in args.scales:
        # Reading selected columns proves this action does not inspect outcomes/predictors.
        frame = load_scale(args.data_root, scale, geometry_only=True)
        xy = frame[["x_m", "y_m"]].to_numpy()
        for scope, fold, train, test in partitions(args.data_root, frame, args.validation):
            for model, bandwidth in candidates(args):
                if model == "ols":
                    counts, radii = np.repeat(len(train), len(test)), np.full(len(test), np.nan)
                else:
                    _, indices, radii = kernel_neighbours(xy[train], xy[test], model, bandwidth)
                    counts = np.array([len(index) for index in indices])
                rows.append({"scale_m": scale, "model": model, "bandwidth": bandwidth,
                             "scope": scope, "fold": fold, "n_train": len(train), "n_test": len(test),
                             "minimum_neighbours": int(counts.min()), "median_neighbours": float(np.median(counts)),
                             "below_20_share": float(np.mean(counts < MIN_NEIGHBOURS)),
                             "minimum_radius_m": float(np.min(radii)), "median_radius_m": float(np.median(radii)),
                             "geometry_support_feasible": bool(counts.min() >= MIN_NEIGHBOURS)})
    payload = {"action": "feasibility", "outcome_used": False,
               "warning": "Geometry support only: this does not establish local rank, conditioning or a preferred bandwidth.",
               "rows": rows}
    if args.out:
        out = fresh_output(args.out)
        pd.DataFrame(rows).to_csv(out / "feasibility.csv", index=False)
        write_json(out / "feasibility.json", payload)
        payload["report"] = str(out / "feasibility.csv")
    emit(payload)


def fit(args):
    specs = candidates(args)
    frames = {scale: load_scale(args.data_root, scale) for scale in args.scales}
    # Validate all folds before creating a run directory.
    splits = {scale: list(partitions(args.data_root, frame, args.validation)) for scale, frame in frames.items()}
    out = fresh_output(args.out)
    started = time.perf_counter()
    inputs = [args.data_root / f"model_ready_{scale}m.csv" for scale in args.scales]
    if args.validation == "shared_regions":
        inputs.append(args.data_root / "shared_macro_fold_assignments.csv")
    contract = args.data_root / "data_contract.json"
    if not contract.exists():
        contract = args.data_root.parent / "data_contract.json"
    if contract.exists():
        inputs.append(contract)
    manifest = {"status": "running", "version": VERSION, "action": "fit",
                "started_utc": datetime.now(timezone.utc).isoformat(),
                "scales": args.scales, "specifications": [{"model": m, "bandwidth": b} for m, b in specs],
                "validation": args.validation, "input_sha256": {str(p.resolve()): sha256(p) for p in inputs},
                "code_sha256": sha256(Path(__file__)), "features": FEATURES,
                "coefficient_definition": {
                    "native": "log1p(stay_count) change per original predictor unit, holding others fixed; intercept at X=0",
                    "x_standardized": "log1p(stay_count) change per training-sample predictor SD (ddof=0); y is NOT standardized; intercept at training X means",
                    "conversion": "native slope = x_standardized slope / scaler.scale_; native intercept = standardized intercept - sum(native slope * scaler.mean_)",
                    "oof": "Scaler/imputer refitted within each training fold; OOF coefficients at held-out locations describe that training-fold fit",
                }, "quadrants": "E/W and N/S split at median x_m/y_m separately per support; descriptive only, not matched zones across scales",
                "preprocessing": "Training-only median imputation and StandardScaler; never discard an all-missing predictor",
                "minimum_neighbours": MIN_NEIGHBOURS, "weight_floor": 1e-12,
                "software": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__, "scikit_learn": sklearn.__version__},
                "claim_limits": LIMITS}
    write_json(out / "run_manifest.json", manifest)
    coefficient_frames, preprocess_rows, metrics, globals_ = [], [], [], []
    try:
        for scale, frame in frames.items():
            xy = frame[["x_m", "y_m"]].to_numpy(dtype=float)
            x = frame[list(FEATURES)].to_numpy(dtype=float)
            y = frame.log_stay_count.to_numpy(dtype=float)
            scale_frames = []
            for scope, fold, train, test in splits[scale]:
                if np.isnan(x[train]).all(axis=0).any():
                    raise ValueError(f"{scale} m {scope} fold {fold}: an entirely missing training predictor")
                imputer = SimpleImputer(strategy="median")
                scaler = StandardScaler()
                x_train = scaler.fit_transform(imputer.fit_transform(x[train]))
                x_test = scaler.transform(imputer.transform(x[test]))
                for i, variable in enumerate(FEATURES):
                    preprocess_rows.append({"scale_m": scale, "scope": scope, "fold": fold,
                                            "variable": variable, "impute_median": imputer.statistics_[i],
                                            "mean": scaler.mean_[i], "scale": scaler.scale_[i],
                                            "variance": scaler.var_[i], "n_train": len(train)})
                for model, bandwidth in specs:
                    prediction, beta, diagnostics = solve(xy[train], x_train, y[train], xy[test], x_test, model, bandwidth)
                    native = beta.copy()
                    native[:, 1:] /= scaler.scale_
                    native[:, 0] -= native[:, 1:] @ scaler.mean_
                    rows = frame.iloc[test][["grid_id", "scale_m", "x_m", "y_m"]].reset_index(drop=True)
                    rows = rows.assign(model=model, bandwidth=bandwidth, scope=scope, fold=fold,
                                       observed_log_stay_count=y[test], predicted_log_stay_count=prediction,
                                       residual=y[test] - prediction,
                                       quadrant=np.where(xy[test, 1] >= np.median(xy[:, 1]), "N", "S") +
                                       np.where(xy[test, 0] >= np.median(xy[:, 0]), "E", "W"))
                    rows = pd.concat([rows, diagnostics], axis=1)
                    for i, variable in enumerate(("intercept",) + FEATURES):
                        rows[f"native__{variable}"] = native[:, i]
                        rows[f"x_standardized__{variable}"] = beta[:, i]
                        if model == "ols":
                            globals_.append({"scale_m": scale, "model": model, "scope": scope,
                                             "fold": fold, "variable": variable,
                                             "native": native[0, i], "x_standardized": beta[0, i]})
                    scale_frames.append(rows)
            scale_rows = pd.concat(scale_frames, ignore_index=True)
            coefficient_frames.append(scale_rows)
            for key, part in scale_rows.groupby(["model", "bandwidth", "scope"], sort=True):
                observed, predicted = part.observed_log_stay_count, part.predicted_log_stay_count
                if len(part) != len(frame) or part.grid_id.duplicated().any():
                    raise AssertionError("Each scope/specification must predict each grid exactly once")
                fold_scores = [r2_score(p.observed_log_stay_count, p.predicted_log_stay_count)
                               for _, p in part.groupby("fold") if len(p) >= 2]
                metrics.append({"scale_m": scale, "model": key[0], "bandwidth": key[1], "scope": key[2],
                                "n": len(part), "n_features": len(FEATURES), "r2": r2_score(observed, predicted),
                                "rmse": float(np.sqrt(mean_squared_error(observed, predicted))),
                                "mae": mean_absolute_error(observed, predicted),
                                "fold_r2_mean": np.mean(fold_scores),
                                "fold_r2_sd": np.std(fold_scores, ddof=1) if len(fold_scores) > 1 else np.nan,
                                "minimum_neighbours": int(part.neighbour_count.min()),
                                "median_neighbours": part.neighbour_count.median(),
                                "median_radius_m": part.radius_m.median(),
                                "median_condition_number": part.condition_number.median(),
                                "p90_condition_number": part.condition_number.quantile(.9),
                                "rank_deficient_share": float(np.mean(part["rank"] < 9))})
            print(f"computed scale={scale} models={len(specs)} validation={args.validation}", file=sys.stderr, flush=True)
        coefficients = pd.concat(coefficient_frames, ignore_index=True)
        coefficients.to_csv(out / "local_coefficients.csv", index=False)
        coefficient_summary(coefficients).to_csv(out / "coefficient_summary.csv", index=False)
        coefficient_summary(coefficients, spatial=True).to_csv(out / "spatial_summary.csv", index=False)
        pd.DataFrame(metrics).to_csv(out / "model_summary.csv", index=False)
        pd.DataFrame(preprocess_rows).to_csv(out / "preprocessing.csv", index=False)
        pd.DataFrame(globals_, columns=["scale_m", "model", "scope", "fold", "variable", "native", "x_standardized"]).to_csv(out / "global_coefficients.csv", index=False)
        coefficients[[c for c in coefficients if "__" not in c]].to_csv(out / "predictions.csv", index=False)
        manifest.update(status="completed", runtime_seconds=time.perf_counter() - started,
                        output_sha256={p.name: sha256(p) for p in sorted(out.glob("*.csv"))})
        write_json(out / "run_manifest.json", manifest)
    except Exception as exc:
        manifest.update(status="failed", error=str(exc), runtime_seconds=time.perf_counter() - started)
        write_json(out / "run_manifest.json", manifest)
        raise
    emit({"action": "fit", "status": "completed", "out": str(out), "computed_from_inputs": True,
          "model_preview": metrics, "claim": "Descriptive evidence; no optimal scale/bandwidth declared.",
          "reports": ["model_summary.csv", "local_coefficients.csv", "coefficient_summary.csv", "spatial_summary.csv", "run_manifest.json"]}, limit=3000)


def compare(args):
    if not args.out:
        raise ValueError("compare requires --out pointing to a completed run or a parent of runs")
    root = Path(args.out).resolve()
    paths = [root / "run_manifest.json"] if (root / "run_manifest.json").exists() else sorted(root.rglob("run_manifest.json"))
    model_frames, coef_frames, source_runs, signatures = [], [], [], set()
    for path in paths:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if manifest.get("status") != "completed":
            continue
        directory = path.parent
        for name in ("model_summary.csv", "coefficient_summary.csv"):
            expected = manifest.get("output_sha256", {}).get(name)
            if not expected or sha256(directory / name) != expected:
                raise ValueError(f"Run output missing or hash mismatch: {directory / name}")
        model_frame = pd.read_csv(directory / "model_summary.csv").assign(run=str(directory))
        coef_frame = pd.read_csv(directory / "coefficient_summary.csv").assign(run=str(directory))
        model_frame = model_frame.loc[model_frame.scale_m.isin(args.scales)]
        coef_frame = coef_frame.loc[coef_frame.scale_m.isin(args.scales)]
        if args.model:
            model_frame = model_frame.loc[model_frame.model.eq(args.model)]
            coef_frame = coef_frame.loc[coef_frame.model.eq(args.model)]
        if args.variables:
            coef_frame = coef_frame.loc[coef_frame.variable.isin(args.variables)]
        model_frames.append(model_frame)
        coef_frames.append(coef_frame)
        source_runs.append({"run": str(directory), "manifest_sha256": sha256(path)})
        signatures.add(tuple(manifest.get("features", [])))
    if not model_frames or all(part.empty for part in model_frames):
        raise ValueError("No completed analysis runs match the requested filters")
    models, coefs = pd.concat(model_frames, ignore_index=True), pd.concat(coef_frames, ignore_index=True)
    digest = hashlib.sha256(json.dumps([source_runs, args.scales, args.model, args.variables], sort_keys=True).encode()).hexdigest()[:12]
    report = root / f"comparison_{digest}.csv"
    combined = pd.concat([models.assign(record_type="model_summary"), coefs.assign(record_type="coefficient_summary")], ignore_index=True, sort=False)
    combined.to_csv(report, index=False)
    # Summaries are ordered by support/specification, never ranked or labeled winners.
    model_columns = ["scale_m", "model", "bandwidth", "scope", "r2", "rmse", "rank_deficient_share"]
    coefficient_columns = ["scale_m", "model", "bandwidth", "scope", "variable", "coefficient_units", "median", "iqr", "positive_share"]
    emit({"action": "compare", "runs": len(source_runs), "report_csv": str(report),
          "model_rows": len(models), "coefficient_rows": len(coefs),
          "common_feature_contract": len(signatures) == 1,
          "warning": "No optimal model is declared. Check input hashes, conditioning, coverage and scale-dependent coefficient units; full-sample and OOF are different evidence.",
          "model_preview": models[model_columns].round(6).head(12).to_dict("records"),
          "coefficient_preview": coefs[coefficient_columns].round(6).head(12).to_dict("records")}, limit=3000)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", required=True, choices=["inventory", "feasibility", "fit", "compare"])
    parser.add_argument("--data-root", type=Path, default=Path(__file__).resolve().parent / "data")
    parser.add_argument("--out", type=Path, help="fit: new/empty run directory; compare: existing run or parent; other actions: optional new report directory")
    parser.add_argument("--scales", default=",".join(map(str, SCALES)))
    parser.add_argument("--model", choices=["ols", "gwr_fixed", "gwr_adaptive"], default=None,
                        help="fit defaults to OLS; feasibility defaults to both GWR kernels")
    parser.add_argument("--bandwidths", help="Comma-separated fixed radii in metres or adaptive fractions in (0,1]")
    parser.add_argument("--validation", default="none", choices=["none", "shared_regions"])
    parser.add_argument("--variables", help="compare-only comma-separated predictor names or intercept")
    args = parser.parse_args(argv)
    args.scales = list(dict.fromkeys(int(s) for s in args.scales.split(",")))
    if not args.scales or set(args.scales) - set(SCALES):
        parser.error(f"--scales must be selected from {SCALES}")
    args.bandwidths = list(dict.fromkeys(float(b) for b in args.bandwidths.split(","))) if args.bandwidths else None
    args.variables = list(dict.fromkeys(args.variables.split(","))) if args.variables else None
    if args.variables and (args.action != "compare" or set(args.variables) - set(("intercept",) + FEATURES)):
        parser.error("--variables is compare-only and must name contract predictors or intercept")
    args.data_root = args.data_root.resolve()
    return args


def main(argv=None):
    try:
        args = parse_args(argv)
        with threadpool_limits(limits=1):
            {"inventory": inventory, "feasibility": feasibility, "fit": fit, "compare": compare}[args.action](args)
        return 0
    except (ValueError, OSError, KeyError, pd.errors.MergeError) as exc:
        emit({"status": "error", "error": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
