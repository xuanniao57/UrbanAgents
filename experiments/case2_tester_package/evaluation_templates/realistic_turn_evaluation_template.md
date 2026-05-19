# Realistic Dialogue Turn Evaluation Template

Use one copy per turn. This template is for the realistic four-stage Case 2 script.

## Turn Metadata

- Turn name:
- Prompt file:
- Session id:
- Resume source session id:
- Transcript path:
- Output folder:
- Runtime / duration:
- Model/provider:

## What Urban-Hermes Did

Short factual summary:

```text

```

## Artifact Inventory

| Artifact | Exists? | Path | Notes |
|---|---|---|---|
| Report / memo | yes / no | | |
| JSON manifest | yes / no | | |
| Variable dictionary / audit CSV | yes / no | | |
| GeoJSON spatial output | yes / no | | |
| QGIS project | yes / no | | |
| Model diagnostics | yes / no | | |
| Reviewer/validator output | yes / no | | |

## Input Grounding Checks

| Check | Result | Evidence path or transcript excerpt |
|---|---|---|
| Read data before method selection | pass / fail / unclear | |
| Identified outcome family | pass / fail / unclear | |
| Separated outcome, exposure, control, proxy, missing evidence | pass / fail / unclear | |
| Did not treat perception as observed vitality | pass / fail / unclear | |
| Did not treat POI as observed activity | pass / fail / unclear | |
| Did not make temporal claims without timestamps | pass / fail / unclear | |

## Method Suitability Checks

| Check | Result | Evidence |
|---|---|---|
| 3D/5D indicators tied to available fields | pass / fail / not applicable | |
| Design and execution separated when requested | pass / fail / not applicable | |
| Observed outcome checked before regression | pass / fail / not applicable | |
| GWR/GWRF gated by sample size, spatial diagnostics, and bandwidth/local estimation | pass / fail / not applicable | |
| PDP/SHAP gated by valid model | pass / fail / not applicable | |
| Causal language avoided unless design supports it | pass / fail / unclear | |

## Reviewer Self-Check

| Reasoning mode | Checked? | Evidence |
|---|---|---|
| Spatial: CRS, geometry, spatial join, analysis unit | yes / no | |
| QGIS: data source, layer loading, symbology fields | yes / no / not generated | |
| Image/perception: provenance and validation | yes / no / not applicable | |
| Text/table: fields, units, missing values, report claims | yes / no | |
| Temporal: timestamp and time-window support | yes / no | |
| Model: residuals, overfitting, spatial autocorrelation, explainability validity | yes / no / not applicable | |

## Overclaims Or Failures

| Issue | Severity | Correction issued? | Evidence |
|---|---|---|---|
| | low / medium / high | yes / no | |

## Usefulness For Section 5.4

- Usable evidence:
- Figure/table material:
- Quote-worthy transcript excerpt:
- Remaining gaps:

## Verdict

Choose one:

- [ ] Accepted as evidence
- [ ] Usable with caveats
- [ ] Needs correction turn
- [ ] Failed / blocked

Reason:

```text

```
