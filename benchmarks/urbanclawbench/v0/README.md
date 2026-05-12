# UrbanClawBench v0 Local MVP

UrbanClawBench is a real-data execution layer for Paper4 UrbanAgent. It should not replace UrbanWorkflowBench v1.2. The intended role is to add WildClawBench-style ecological pressure: the agent must work on noisy local urban data, produce executable artifacts, and pass hidden post-run checks.

## Positioning

UrbanWorkflowBench v1.2 already covers three things well:

1. External comparability through CityBench-aligned tasks.
2. Design-sensitive probes for dual-space cognition, memory continuity, tool orchestration, and HITL checkpoints.
3. Open workflow planning against reference steps and tools.

UrbanClawBench v0 should add one missing layer:

1. Real-data execution on local GIS, OSM, street-view, heritage, and trajectory-like assets.
2. Ground-truth hiding by separating public task manifests from private scorer metadata.
3. Artifact-level scoring: GeoPackage/GeoJSON/CSV/PNG/Markdown outputs are checked after the agent finishes.

## Local Data We Can Use Now

The current workspace already supports a credible MVP without collecting new data.

| Data asset | Local source | Best-fit task families |
|---|---|---|
| Shanghai Tongji OSM GeoJSON layers | `data/city_data/` | spatial data engineering, service coverage, POI robustness, visualization |
| Shanghai Hengfu OSM page files | `data/trajectories/shanghai_hengfu/` | graph construction, route/connectivity workflow, parser robustness |
| Paris Marais OSM page files | `data/trajectories/paris_marais/` | walkability, network connectivity, cross-place transfer |
| Heritage district AOI/OSM cache | `paper9_heritageIntelligence/...` referenced by case1 inputs | heritage indicator computability, source extent diagnostics, AOI clipping |
| Street-view batches | `D:/streetview_images_batch` or `D:/街景/streetview_images_batch` when present | visual consistency proxy, facade/style evidence, perception artifact checks |
| Case1 + 20 heritage harness | `scripts/run_case1_plus20_experiment.py` | cumulative refinement, memory/reviewer/input-grounding ablation |

## MVP Scope

Start with 10 to 12 tasks, not 60. The first version should prove the benchmark protocol and paper story before expanding coverage.

Recommended v0 suites:

1. `spatial_data_engineering`: AOI clipping, CRS/extent diagnostics, geometry validity, OSM parser robustness.
2. `urban_perception`: street-view visual proxy, heritage facade evidence disclosure.
3. `simulation_prediction_light`: network accessibility and service coverage with simple graph/buffer baselines.
4. `planning_decision_support`: 15-minute gap diagnosis and heritage indicator computability triage.
5. `communication_visualization`: GIS bundle and report/PPT-ready artifact generation.
6. `safety_robustness`: adversarial POI injection, shifted-CRS/source mismatch detection, privacy-risk disclosure for trajectory-like inputs.

## Execution Protocol

Each case should use two files:

1. Public task manifest: task instruction, visible input paths, required output contract, allowed tools.
2. Private scorer metadata: expected numeric ranges, exact counts, baseline outputs, injected traps, and scoring weights.

The runner should perform four phases:

1. Copy or mount task inputs into a per-case work directory.
2. Run the agent with only the public manifest visible.
3. Inject the private scorer metadata after the run.
4. Score required artifacts and write a compact result row.

## Scoring Dimensions

Use the UrbanClawBench five-dimensional score, but instantiate it with local artifact checks.

| Dimension | Weight | Local checks |
|---|---:|---|
| Functional correctness | 0.40 | numeric metrics, feature counts, coverage ratios, graph measures, required files |
| Code validity | 0.20 | runner exit status, import failures, artifact readability, dependency hygiene |
| Spatial fidelity | 0.15 | CRS, AOI clipping, geometry validity, topology/connectivity, source extent diagnostics |
| Insight quality | 0.15 | evidence-backed diagnosis, uncertainty disclosure, non-trivial spatial interpretation |
| Process efficiency | 0.10 | elapsed time, repeated tool calls, output size, avoidable recomputation |

## Paper4 Integration Path

The cleanest path is to add UrbanClawBench as `UrbanWorkflowBench v1.3` or as a sibling benchmark section:

1. Keep `UrbanWorkflowBench v1.2` for design-sensitive and external benchmark reporting.
2. Add `UrbanClawBench v0` for real-data execution evidence.
3. Report them separately in the paper: v1.2 answers architecture-sensitive capability; v0 answers ecological validity.
4. Reuse existing capability cards: `spatial_source_diagnostics`, `aoi_context_buffer`, `urban_density_morphology`, `function_mix_entropy`, `streetview_visual_consistency`, and `gis_layer_stack_export`.
5. Reuse existing ablation flags for paper tables: full, without planning, without review, without QC, without dual-space, without memory, vanilla.

## Near-Term Implementation Checklist

1. Add a `real_data_execution` protocol to the runner.
2. Implement a public manifest loader for `local_mvp_task_manifest.json`.
3. Keep scorer metadata in a private path outside the public manifest.
4. Write scorers for vector layers, tables, figures, and narrative reports.
5. Add a smoke test with provider `none` that validates task contracts without calling an LLM.
6. Run 3 representative tasks first: source extent diagnostics, 15-minute service gap, and GIS bundle export.
