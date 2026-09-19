# Four-condition adaptive-dialogue test — preparation version

Conditions: urban_full_v2 / urban_single_v2 / urban_no_memory_v2 / pi_native_v2.
This protocol replaces neither historical scores nor their task definitions. Do not append new scores to an old fixed-route table as if the protocol were unchanged.

See TESTER_CN.md and JUDGE_CN.md. The model proposes feasible scales; the tester follows actual outputs. No fixed route count and no fixed number of workers/reviewers.

Launch from pi_urban_agent (Node dependencies installed):

```sh
node --import tsx scripts/long-workflow-session.ts --out /absolute/fresh-run --condition urban_full_v2 --data-root /absolute/package/pi_urban_agent/raw_case/data --model YOUR_MODEL --provider local-vllm --base-url http://127.0.0.1:8000/v1 --window 16384 --output-tokens 4096 --deadline 600
```

Set URBAN_PI_PYTHON to an absolute Python executable with numpy/pandas/scipy/scikit-learn/geopandas/shapely/pyproj. Prepare raw_case using scripts/prepare-raw-case.ts on the source machine, and verify source_manifest.json when transferring. These are retained event-level samples and vector layers, not preaggregated grids. Each condition/repetition gets a fresh run and separate workspace. The human-tester Codex supplies the inbox messages interactively; the fixed-message matrix runner intentionally rejects this protocol. After finishing, create run/STOP. Do not run models until power and endpoint availability are confirmed.

Status: new delegation entry and condition definitions compile; real-model multi-agent integration is not yet validated. Existing legacy run-pi-role and module score scripts are not the v2 evaluator. Final independent LLM judging is performed using JUDGE_CN.md in a separate context, not by those legacy scripts. A single conversation is a pilot, not formal statistical evidence.

Native Pi here means no Urban extension, under the same controlled data/model harness. The package pins Pi with the existing shared budget compatibility patch; it is not an untouched upstream binary. Report this explicitly.
