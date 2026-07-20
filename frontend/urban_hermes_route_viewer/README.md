# Urban-Hermes Route Workspace

Static research workspace for Urban-Hermes route-tree state.
It is the browser-side companion to the CLI: the CLI executes the runtime and writes state files, while this page turns the same state into a human-reviewable research record.

The July 2026 visual-analytics layout uses three synchronized columns:

- left: research stages, branch coverage, and unresolved human checkpoints;
- centre: an outcome-first evidence workbench with linked spatial and statistical views, the typed route graph, and node-level artifacts;
- right: a full-height Human--Planner--Worker--Reviewer dialogue, with a raw TUI view available as a secondary mode.

The default Shanghai case distinguishes passive, regime-embedded failures (for example, who is missing from an LBS sample) from active, choice-contingent failures (for example, grid scale or validation design). Each control card records the source, observable consequence, preventability, claim gate, and required human action. This makes caution operational: a reviewer is credited only when a diagnostic changes a route, artifact, or admissible claim.

## Open with live experiment data

From `D:/GitHub_1/world_agent/urban-mobility-agent/paper4_urban_svgagent/`:

```powershell
python scripts/start_urban_agent_workspace.py --toolsets urban,todo,memory,delegation
```

This starts the static frontend, opens the Urban Agent workspace, and then
launches the Urban-Hermes CLI with the same frontend port. If you only need the
viewer without the CLI, run the static server directly:

```powershell
python -m http.server 8017
```

Then open:

```text
http://localhost:8017/frontend/urban_hermes_route_viewer/index.html
```

To open a live Urban-Hermes route-tree state exported by `urban_route_tree`, pass the state file as a query parameter:

```text
http://localhost:8017/frontend/urban_hermes_route_viewer/index.html?state=experiments/case2_typed_route_tree_rerun_20260524/route_tree_frontend_state.json
```

The CLI-side route-tree tool writes this URL in its return payload as `frontend_url`.
Use the Refresh button to reload the latest route state, or enable Auto refresh during an Urban-Hermes run.

This mode reads:

- `submissions/urban_cup_2026/process_evidence/route_tree_state.json` by default;
- `submissions/urban_cup_2026/process_evidence/step_reviews/*.json`;
- `submissions/urban_cup_2026/outputs/case_findings.json`;
- `submissions/urban_cup_2026/outputs/model_validation_summary.csv`;
- `submissions/urban_cup_2026/outputs/combined_rf_oof_predictions.csv`;
- `submissions/urban_cup_2026/outputs/temporal_cohort_summary.csv`;
- `submissions/urban_cup_2026/reproducibility_manifest.json`;
- a route state supplied through `?state=...` for other live cases;
- `experiments/urbanworkflowbench_60tasks_20260524/condition_traces/all60_design_gate_20260524/condition_trace_score_summary.json`
- `experiments/urbanworkflowbench_60tasks_20260524/condition_traces/all60_design_gate_20260524/full/all60_design_gate_decisions.csv`

## What the workspace shows

- A continuous human--AI research thread; raw terminal text is a toggle rather than the primary workspace.
- Stage and checkpoint navigation with selected, candidate, deferred, blocked, and merge states.
- Passive and active epistemic-control cards with explicit human actions.
- A reusable declarative visualization-skill registry for linked residual geography, observed--predicted comparison, residual distributions, validation-regime gaps, feature-package comparisons, cohort activity, and spatial diagnostics.
- A clickable route graph and selected-node evidence panel with inputs, method parameters, artifacts, time/space/people assumptions, and claim boundaries.

## Verified visual-analytics stack

The implementation is based on what can be verified from the two cited systems rather than on inferred libraries:

- LightVA explicitly describes Python analysis with pandas and Altair, compiled to Vega-Lite, including brushing, tooltips, legends, linked views, and coordinated layouts. Its official project page publishes the paper, appendix, demo, and slides, but no implementation repository.
- ProactiveVA's appendix explicitly describes Tableau dashboards and the Tableau Embedding API, with UI-agent actions for reading data, selecting marks, and filtering. The public GitHub repository is the academic project-page source, not the visual-analytics system implementation.
- Urban-Hermes therefore reproduces the public design pattern through a locally vendored Vega stack: Vega 6.2.0, Vega-Lite 6.4.3, and Vega-Embed 7.1.0. The declarative specs live in `visual_skills.js`; the LLM chooses a registered skill and parameters rather than generating ad-hoc plotting code.

This repository does not claim to copy unpublished LightVA or ProactiveVA source code. It implements a compatible, independently written visualization layer from the methods and interaction patterns disclosed in their papers.

## Notes

The viewer uses a flat black-and-white technical style inspired by City Syntax: white space, thin rules, a monospaced interface layer, sans-serif research content, and restrained colorblind-safe accents for passive, active, blocked, and accepted states. It intentionally avoids 3D effects, gradients, decorative shadows, and game-like pixel panels.
It has no package install step and does not rerun Urban-Hermes.
It only reads state and artifact files written by the runtime.
Human controls and notes in the static viewer are explicitly labelled as local previews; they are not silently written back to runtime state.
