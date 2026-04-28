# Benchmark Evaluation Pipeline Reconciliation

## Issue

Two evaluation pipelines co-exist in the project, producing different scores for the same model configurations:

| Pipeline | Script | Avg Agent Score | Avg Bare Score |
|----------|--------|----------------|----------------|
| CityData Quick | `run_citydata_quick_benchmark.py` | ~0.538 | ~0.550 |
| Full Comparison | `run_comparison_test.py` | ~0.406 | ~0.406 |

## Root Cause

1. **CityData Quick Benchmark** runs a fixed 2-sample-per-task evaluation using `CityBenchEvaluatorV2` with synthetic task generation, producing optimistic scores because:
   - Small sample size (2 per task type × 8 types = 16 total)
   - Tasks auto-generated to be solvable
   - No real CityBench dataset items used

2. **Full Comparison Test** uses 20 samples per task from cached CityBench data with stricter evaluation, producing lower but more realistic scores.

## Resolution

The paper should report **Full Comparison** scores as the primary metric (more rigorous and reproducible). The Quick Benchmark exists for development-time smoke testing only.

### Paper Table Updates Required

- **Table 2 (main results)**: Use Full Comparison results (avg ~0.41)
- **Footnote**: Explain Quick Benchmark exists for validation, not primary reporting
- **New Table (ablation)**: Use consistent pipeline for all ablation configs
- **New Table (baselines)**: Use `run_baseline_comparison.py` which extends the Full Comparison evaluator

### Reporting Protocol

For all future experiments, the canonical evaluation pipeline is:

```
CityBenchEvaluatorV2 + UrbanWorkflowBench v1.2 manifest + ≥20 samples per task type
```

Sample size justification: 20 samples × 8 task types = 160 evaluations per configuration, consistent with GeoAgent's 147-task and GeoJSON Agents' 70-task × 3-complexity evaluation density.

## Action Items

- [x] Document the discrepancy (this file)
- [ ] Update paper Table 2 with Full Comparison scores
- [ ] Add footnote about Quick Benchmark scope
- [ ] Ensure ablation runner uses consistent pipeline
- [ ] Ensure baseline runner uses consistent pipeline
