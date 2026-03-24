# UrbanWorkflowBench v1.1

UrbanWorkflowBench v1.1 extends v1.0 with two workflow-sensitive suites:

1. tool_orchestration
2. hitl_checkpoint

It also upgrades the external subset builder and runner:

1. configurable external task selection
2. configurable per-task sampling
3. provider modes for none, qwen, kimi, and all

## Included Suites

1. external_citydata_subset
2. dual_space_design
3. memory_continuity
4. tool_orchestration
5. hitl_checkpoint

## Build

```powershell
C:/Users/18029/.conda/envs/urban-mobility/python.exe paper4_urban_svgagent/scripts/benchmarks/build_urbanworkflowbench_v1_1.py --sample-count 2 --external-task-types geoqa,mobility_prediction,outdoor_navigation,urban_exploration
```

## Run

Smoke test without remote models:

```powershell
C:/Users/18029/.conda/envs/urban-mobility/python.exe paper4_urban_svgagent/scripts/benchmarks/run_urbanworkflowbench_v1_1.py --provider none
```

Formal scoring with one provider:

```powershell
C:/Users/18029/.conda/envs/urban-mobility/python.exe paper4_urban_svgagent/scripts/benchmarks/run_urbanworkflowbench_v1_1.py --provider qwen
```

Formal scoring across all configured providers:

```powershell
C:/Users/18029/.conda/envs/urban-mobility/python.exe paper4_urban_svgagent/scripts/benchmarks/run_urbanworkflowbench_v1_1.py --provider all
```

## Output Artifacts

Builder output:

- artifacts/benchmarks/urbanworkflowbench_v1_1_manifest_*.json
- artifacts/benchmarks/urbanworkflowbench_v1_1_manifest_latest.json

Runner output:

- artifacts/benchmarks/urbanworkflowbench_v1_1_results_*.json

## Notes

1. provider none is intended for local smoke testing.
2. provider qwen and provider kimi require their API keys in the environment.
3. provider all will skip unavailable providers unless --strict-provider is enabled.