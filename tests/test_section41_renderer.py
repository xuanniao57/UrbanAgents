"""The plotting contract must reject missing variables or changed map bandwidth."""
import importlib.util
import sys
from pathlib import Path
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments/case2_multiscale_aoi_corrected_20260830"
spec = importlib.util.spec_from_file_location("section41_render", EXP / "render_section41_artifacts.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

@pytest.fixture
def frames():
    return (pd.read_csv(EXP / "outputs_coefficients/gwr_fixed7km_coefficients_all8_all7.csv"),
            pd.read_csv(EXP / "outputs_coefficients/ols_coefficients_all8_all7.csv"))

def test_valid_full_model(frames):
    assert module.validate_inputs(*frames)["map_count"] == 56

def test_reject_reduced_predictor_model(frames):
    local, ols = frames
    with pytest.raises(ValueError, match="eight covariates"):
        module.validate_inputs(local.drop(columns=[module.plots.exp.FEATURES[0]]), ols)

def test_reject_changed_bandwidth(frames):
    local, ols = frames
    local.loc[0, "bandwidth_m"] = 8000
    with pytest.raises(ValueError, match="common 7 km"):
        module.validate_inputs(local, ols)

def test_reject_duplicate_location(frames):
    local, ols = frames
    with pytest.raises(ValueError, match="Duplicate"):
        module.validate_inputs(pd.concat([local, local.iloc[:1]]), ols)

def test_reject_oof_maps(frames):
    local, ols = frames
    local.loc[0, "fit_scope"] = "out_of_fold"
    with pytest.raises(ValueError, match="OOF fits"):
        module.validate_inputs(local, ols)

def test_never_overwrite_archived_experiment():
    with pytest.raises(ValueError, match="separate run directory"):
        module.render(EXP / "figures_revised")
