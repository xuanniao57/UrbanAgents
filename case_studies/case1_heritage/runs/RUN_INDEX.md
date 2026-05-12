# Case1 Run Index

This folder keeps every Case1 experiment as an isolated run directory. Formal
ablation summaries are stored at the root of `runs/`; raw outputs remain in
their timestamped folders.

## Formal Ablation Set

The current Table 3 candidate set is `ablation_table3_trials_20260509_complete.csv`
and its aggregate file `ablation_table3_trials_20260509_complete_aggregate.csv`.
It contains 21 trials:

| Config | Trials | Meaning |
|---|---:|---|
| `c0_full` | 3 | Planning + review + QC + dual-space + memory |
| `c1_wo_planning` | 3 | Planning disabled |
| `c2_wo_review` | 3 | Review disabled |
| `c3_wo_qc` | 3 | Quality control disabled |
| `c4_wo_dualspace` | 3 | Dual-space diagnostics disabled |
| `c5_wo_memory` | 3 | Feedback/workflow memory disabled |
| `c6_vanilla` | 3 | Planning, review, QC, dual-space, and memory disabled |

## Aggregate Snapshot

| Config | Success | Mean Latency (s) | Mean Cost (USD) | Mean Exec Confidence | Mean Review Score | Mean Artifacts | Mean Metric Rows |
|---|---:|---:|---:|---:|---:|---:|---:|
| `c0_full` | 1.0 | 146.14 | 1.2050 | 0.8433 | 1.0 | 4.0 | 29.33 |
| `c1_wo_planning` | 1.0 | 37.09 | 0.4320 | 0.8725 | 1.0 | 0.0 | 22.00 |
| `c2_wo_review` | 1.0 | 125.57 | 1.0929 | 0.8429 | n/a | 6.0 | 22.00 |
| `c3_wo_qc` | 1.0 | 127.19 | 1.0999 | n/a | 1.0 | 6.0 | 22.00 |
| `c4_wo_dualspace` | 1.0 | 130.85 | 1.1064 | 0.8173 | 1.0 | 6.0 | 22.00 |
| `c5_wo_memory` | 1.0 | 130.41 | 1.1027 | 0.8298 | 1.0 | 6.0 | 22.00 |
| `c6_vanilla` | 1.0 | 24.52 | 0.4191 | n/a | n/a | 0.0 | 22.00 |

## Historical And Incomplete Runs

- `20260507_161034_full/`: early full run with event/manifest/summary outputs.
- `inputA_20260508_full/`: earlier Input A full-condition run.
- `_incomplete/`: empty interrupted folders retained for audit provenance.
- Duplicate timestamped `c4`, `c5`, and `c6` folders are retained because they
  contain valid raw `result.json` and `signals.json`; the formal CSV determines
  which three trials enter the table.

## Latest Raw Run

Latest timestamped raw run: `20260509_174939_c6_vanilla_t3/`.
It is a vanilla baseline trial, not the recommended representative full-system
run.
