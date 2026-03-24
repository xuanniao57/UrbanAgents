# UrbanWorkflowBench v1.0

UrbanWorkflowBench is an UrbanAgent-native benchmark protocol for evaluating workflow-oriented urban analysis agents.

## Design Goals

UrbanWorkflowBench v1.0 combines two sources of evidence:

1. External comparability subset
   - Reuses a small subset of CityData / CityBench-aligned tasks.
   - Maintains comparability with existing urban-task benchmarks.

2. Design-sensitive probes
   - Evaluates capabilities that are central to UrbanAgent but weakly covered by CityBench.
   - Includes dual-space cognition and memory continuity.

## Included Suites in v1.0

1. external_citydata_subset
   - geoqa
   - mobility_prediction
   - outdoor_navigation
   - urban_exploration

2. dual_space_design
   - relation-sensitive synthetic probes for contains / aligned / separated / adjacent / connected

3. memory_continuity
   - repeated-task transfer probes for mobility / navigation / exploration

## Output Artifacts

Builder output:

- artifacts/benchmarks/urbanworkflowbench_v1_manifest_*.json
- artifacts/benchmarks/urbanworkflowbench_v1_manifest_latest.json

Runner output:

- artifacts/benchmarks/urbanworkflowbench_v1_results_*.json

## Usage

Build the benchmark manifest:

```powershell
C:/Users/18029/.conda/envs/urban-mobility/python.exe paper4_urban_svgagent/scripts/benchmarks/build_urbanworkflowbench_v1.py
```

Run the benchmark:

```powershell
C:/Users/18029/.conda/envs/urban-mobility/python.exe paper4_urban_svgagent/scripts/benchmarks/run_urbanworkflowbench_v1.py --provider none
```

## v1.0 Scope Boundary

v1.0 is intentionally minimal.

Included:

1. UrbanAgent-native design validation
2. External urban-task subset reuse
3. A unified manifest format

Not yet included:

1. Full USTBench ingestion
2. GeoAnalystBench workflow/code-generation cases
3. HITL checkpoint scoring
4. Tool orchestration stress tests

These are natural extensions for v1.1 and later versions.