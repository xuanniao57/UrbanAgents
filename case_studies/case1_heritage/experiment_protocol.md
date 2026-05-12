# Case1 Experiment Protocol

Target district: 宁波老外滩历史文化街区  
Task: construct and audit built-environment `X` indicators for a historical district before any downstream `Y` perception modeling.

## Conditions

| Label | Setting |
|---|---|
| `c0_full` | Planning + review + quality control + dual-space diagnostics + memory |
| `c1_wo_planning` | Planning disabled |
| `c2_wo_review` | Review disabled |
| `c3_wo_qc` | Quality control disabled |
| `c4_wo_dualspace` | Dual-space diagnostics disabled |
| `c5_wo_memory` | Feedback/workflow memory disabled |
| `c6_vanilla` | Planning, review, QC, dual-space, and memory disabled |

## Required Evidence

The full condition should produce:

- dataset cards for AOI, OSM/cache, building-function source, and street-view images;
- grounding policy and indicator computability matrix;
- source extent diagnostics against AOI/context buffer;
- directly computable / proxy-only / unsupported indicator classification;
- metric rows and reviewable GIS/chart/table artifacts;
- reviewer corrections and rerun queue when source coverage or evidence is weak;
- runtime ledger with todos and checkpoints.

## Current Findings

The current 21-trial ablation set is useful but not yet decisive because every condition reports `success=true`. The next protocol should score quality more strictly:

1. evidence completeness;
2. artifact validity;
3. computability classification correctness;
4. unsupported-claim rate;
5. reviewer issue detection on flawed inputs;
6. correction-memory reuse on subsequent similar districts.

## Recommended Next Trial

Run a deliberately flawed Case1 variant:

- AOI-clipped OSM/cache only;
- one missing or stale street-view metadata file;
- one function-source path unavailable;
- one CRS mismatch or source extent mismatch.

The expected paper signal is that `c0_full` identifies and routes these issues, while ablated conditions either miss them, overclaim, or fail to produce usable correction memory.
