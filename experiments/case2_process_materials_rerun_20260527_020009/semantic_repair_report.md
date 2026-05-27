# Semantic Repair Report — Shanghai Street-Vitality Route Tree

## Repair Date
2026-05-27T02:50:00

## Source Files
- plan/route_tree.json
- trace/workflow_trace.json

## Main Selected Route (Black Line)
```
RO_01_all_window_aggregate
  -> FP_01_built_form_baseline + FP_02_activity_opportunity
  -> ME_01_rf_baseline_model
  -> DI_01_residual_spatial_autocorrelation + MX_01_shap_pdp_explanation
  -> RC_01_route_comparison
  -> CS_01_claim_synthesis
```

## Branch Statuses and Reasons

| Node | Status | Reason |
|------|--------|--------|
| RO_01_all_window_aggregate | approved | Main outcome branch; data ready; baseline association model |
| FP_01_built_form_baseline | approved | Core built-form variables; data ready |
| FP_02_activity_opportunity | approved | Core opportunity variables; data ready |
| ME_01_rf_baseline | approved | Existing baseline model; use as-is then review residuals |
| DI_01_residual_spatial_autocorrelation | completed | Residual check completed; Moran's I=0.191 significant |
| MX_01_shap_pdp_explanation | completed | SHAP/PDP explanation completed on fitted RF model |
| RC_01_route_comparison | completed | Route comparison completed with all approved branches |
| CS_01_claim_synthesis | completed | Final claim synthesis completed |
| RO_02_weekday_weekend_contrast | completed | Completed comparison branch feeding RC_01; not main path |
| ME_02_gwrf_spatial_heterogeneity | blocked | Moran's I supported exploration, but GWRF requirements failed because local multicollinearity exceeded threshold (50.2% windows with condition number >= 30) |
| RO_03_day_period_split | deferred | Deferred by user; can be activated later |
| RO_04_population_profile_aggregation | deferred | Raw UUID join not prepared; privacy risk |
| FP_03_accessibility_connectivity | deferred | Deferred by user; requires GIS processing |
| FP_04_full_multimodal | deferred | Deferred by user; high collinearity risk without review |

## Validation
- **Status**: valid
- **Main path reaches CS_01**: yes
- **Each branch has status and reason**: yes
- **All nodes have time-space-people meaning**: yes
- **All edges have operation and reason**: yes
- **Main path continuity**: all 8 nodes connected

## Files Updated
- route_tree_state.json
- route_tree_frontend_state.json
- route_tree_visual_spec.json
- route_tree_events.jsonl
