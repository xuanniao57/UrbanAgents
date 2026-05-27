# Urban-Hermes Route Workspace

Static runtime viewer for Urban-Hermes route-tree state.
It is designed as the browser-side companion to the CLI: the CLI continues the dialogue and writes state files, while this page renders the planner route tree, node-level inputs/outputs, artifacts, reviewer notes, todo status, human choice requests, and benchmark panels.

## Open with live experiment data

From `D:/GitHub_1/world_agent/urban-mobility-agent/paper4_urban_svgagent/`:

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

- `experiments/case2_typed_route_tree_rerun_20260524/typed_route_tree.json`
- `experiments/case2_typed_route_tree_rerun_20260524/route_tree_frontend_state.json` when `?state=...` is supplied
- `experiments/case2_typed_route_tree_rerun_20260524/workflow_trace.json`
- `experiments/case2_typed_route_tree_rerun_20260524/branch_comparison.json`
- `experiments/urbanworkflowbench_60tasks_20260524/condition_traces/all60_design_gate_20260524/condition_trace_score_summary.json`
- `experiments/urbanworkflowbench_60tasks_20260524/condition_traces/all60_design_gate_20260524/full/all60_design_gate_decisions.csv`

## What the workspace shows

- A curved, node-link route tree with selected, candidate, deferred, blocked, and merge states.
- Clickable nodes. The detail panel shows required inputs, method parameters, expected outputs, attached artifacts, time/space/people assumptions, and claim boundaries.
- A CLI-synchronized panel for planner todo, route choice requests, patch events, and recorded human choices.
- A selected-route rail that summarizes each executed step as input -> output -> reviewer question.
- Benchmark condition panels and a filterable UrbanWorkflowBench-60 table.

## Notes

The viewer is intentionally plain black-and-white for paper screenshots.
It has no package install step and does not rerun Urban-Hermes.
It only reads state and artifact files written by the runtime.
