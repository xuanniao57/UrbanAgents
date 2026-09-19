"""Portable synthetic checks; optional corrected-cache parity checks for developers.

python test_analysis.py
python test_analysis.py --corrected-root PATH_TO_CORRECTED_EXPERIMENT
Cache files are read ONLY by this developer test, never analysis.py or agent fit.
"""
import argparse
import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler

import analysis


def synthetic_checks():
    rng = np.random.default_rng(42)
    x = rng.normal(size=(80, 8))
    xy = rng.uniform(0, 100, size=(80, 2))
    beta = np.arange(1, 9) * .05
    y = 2 + x @ beta
    for model, bandwidth in [("ols", 0), ("gwr_fixed", 300), ("gwr_adaptive", .5)]:
        prediction, fitted, diagnostics = analysis.solve(xy, x, y, xy, x, model, bandwidth)
        np.testing.assert_allclose(prediction, y, atol=1e-11)
        np.testing.assert_allclose(fitted, np.tile(np.r_[2, beta], (80, 1)), atol=1e-11)
        assert diagnostics["rank"].eq(9).all()
    try:
        analysis.solve(xy, x, y, xy, x, "gwr_fixed", .0001)
    except ValueError:
        pass
    else:
        raise AssertionError("Infeasible fixed radius did not fail")
    with tempfile.TemporaryDirectory() as directory:
        out = Path(directory) / "run"
        analysis.fresh_output(out)
        (out / "marker").touch()
        try:
            analysis.fresh_output(out)
        except ValueError:
            pass
        else:
            raise AssertionError("Nonempty output was not refused")
    print("PASS synthetic OLS/GWR exact linear recovery, local rank, infeasible radius and output protection")


def corrected_checks(root):
    for scale, model, bandwidth, label, cached_path in [
        (800, "ols", 0, "OLS", root / "outputs/scale_bandwidth_oof_predictions.csv"),
        (700, "gwr_adaptive", .1, "GWR adaptive 10%", root / "outputs/scale_bandwidth_oof_predictions.csv"),
        (800, "gwr_fixed", 7000, "GWR fixed 7 km", root / "outputs_fixed_distance/fixed_distance_gwr_oof_predictions.csv"),
    ]:
        frame = analysis.load_scale(root / "outputs", scale)
        x = frame[list(analysis.FEATURES)].to_numpy()
        xy = frame[["x_m", "y_m"]].to_numpy()
        y = frame.log_stay_count.to_numpy()
        groups = analysis.shared_groups(root / "outputs", frame)
        prediction = np.full(len(frame), np.nan)
        for train, test in GroupKFold(n_splits=5).split(frame, groups=groups):
            imputer, scaler = SimpleImputer(strategy="median"), StandardScaler()
            x_train = scaler.fit_transform(imputer.fit_transform(x[train]))
            x_test = scaler.transform(imputer.transform(x[test]))
            result, beta, _ = analysis.solve(xy[train], x_train, y[train], xy[test], x_test, model, bandwidth)
            prediction[test] = result
            native = beta.copy()
            native[:, 1:] /= scaler.scale_
            native[:, 0] -= native[:, 1:] @ scaler.mean_
            reconstructed = native[:, 0] + np.einsum("ij,ij->i", native[:, 1:], imputer.transform(x[test]))
            np.testing.assert_allclose(result, reconstructed, rtol=1e-10, atol=1e-10)
        cached = pd.read_csv(cached_path)
        cached = cached.loc[cached.scale_m.eq(scale) & cached.model.eq(label)].set_index("grid_id")
        reference = cached.loc[frame.grid_id, "predicted_log_stay_count"].to_numpy()
        error = float(np.max(np.abs(prediction - reference)))
        np.testing.assert_allclose(prediction, reference, rtol=1e-9, atol=1e-9)
        print(json.dumps({"status": "PASS", "scale": scale, "model": model,
                          "max_absolute_cached_prediction_error": error,
                          "native_coefficient_reconstruction": "PASS"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--corrected-root", type=Path)
    args = parser.parse_args()
    with analysis.threadpool_limits(limits=1):
        synthetic_checks()
        if args.corrected_root:
            corrected_checks(args.corrected_root)
