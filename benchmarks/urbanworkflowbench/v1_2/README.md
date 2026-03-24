# UrbanWorkflowBench v1.2

UrbanWorkflowBench v1.2 keeps the v1.1 native design-sensitive suites and formally integrates the open workflow task bank as layered benchmark suites.

## What Is New

1. open benchmark seeds are promoted from a static bank into runnable benchmark cases
2. three layered open workflow suites are added to the formal runner
3. an official profile and a full-bank profile are both supported
4. a new workflow planning protocol scores plan quality against hidden reference workflows

## Layered Open Workflow Suites

1. external_open_workflow_t1_core
   - compact, high-signal tasks
   - intended for headline comparison and frequent regression checks
2. external_open_workflow_t2_standard
   - broader urban workflow coverage
   - included in the v1.2 official profile
3. external_open_workflow_t3_challenge
   - long-tail and harder open tasks
   - included in the full-bank profile only

## Profiles

1. official
   - includes tier 1 and tier 2 open workflow cases
   - recommended for formal reporting
2. fullbank
   - includes all 115 open workflow seeds across all three tiers
   - recommended for stress testing and deeper analysis

## Included Suites

1. external_citydata_subset
2. dual_space_design
3. memory_continuity
4. tool_orchestration
5. hitl_checkpoint
6. external_open_workflow_t1_core
7. external_open_workflow_t2_standard
8. external_open_workflow_t3_challenge

## Build

Official profile:

```powershell
C:/Users/18029/.conda/envs/urban-mobility/python.exe paper4_urban_svgagent/scripts/benchmarks/build_urbanworkflowbench_v1_2.py --open-workflow-profile official --sample-count 2 --external-task-types geoqa,mobility_prediction,outdoor_navigation,urban_exploration
```

Full-bank profile:

```powershell
C:/Users/18029/.conda/envs/urban-mobility/python.exe paper4_urban_svgagent/scripts/benchmarks/build_urbanworkflowbench_v1_2.py --open-workflow-profile fullbank --sample-count 2 --external-task-types geoqa,mobility_prediction,outdoor_navigation,urban_exploration
```

## Run

Smoke test on the latest official manifest:

```powershell
C:/Users/18029/.conda/envs/urban-mobility/python.exe paper4_urban_svgagent/scripts/benchmarks/run_urbanworkflowbench_v1_2.py --provider none
```

Formal scoring with one provider:

```powershell
C:/Users/18029/.conda/envs/urban-mobility/python.exe paper4_urban_svgagent/scripts/benchmarks/run_urbanworkflowbench_v1_2.py --provider qwen
```

Full-bank run:

```powershell
C:/Users/18029/.conda/envs/urban-mobility/python.exe paper4_urban_svgagent/scripts/benchmarks/run_urbanworkflowbench_v1_2.py --manifest paper4_urban_svgagent/artifacts/benchmarks/urbanworkflowbench_v1_2_manifest_fullbank_latest.json --provider qwen
```

## Output Artifacts

Builder output:

1. artifacts/benchmarks/urbanworkflowbench_v1_2_manifest_*.json
2. artifacts/benchmarks/urbanworkflowbench_v1_2_manifest_latest.json
3. artifacts/benchmarks/urbanworkflowbench_v1_2_manifest_official_latest.json
4. artifacts/benchmarks/urbanworkflowbench_v1_2_manifest_fullbank_latest.json

Runner output:

1. artifacts/benchmarks/urbanworkflowbench_v1_2_results_*.json

## Notes

1. provider none is only for protocol wiring and smoke validation
2. open workflow planning scores under provider none are not comparable to real model runs
3. provider qwen and provider kimi require their API keys in the environment
4. provider all will skip unavailable providers unless --strict-provider is enabled
