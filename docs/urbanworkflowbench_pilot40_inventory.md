# UrbanWorkflowBench Pilot40 Inventory

This note records the 40-case development-stage pilot executed for UrbanWorkflowBench v1.2 before the canonical 160-evaluation comparison.

The pilot uses the official v1.2 manifest as its source and keeps the original benchmark tasks unchanged.
Two backends were tested through direct API access: Qwen and Kimi.
Proxy-related environment variables were cleared before execution so that the runs followed the intended non-proxied path.

## 1. Suite design and data inventory

| Suite | Cases | Source benchmark or data | Protocol | Capability focus | Core data or state |
|---|---:|---|---|---|---|
| external_citydata_subset | 8 | CityData / CityBench slice | agent_task | spatial understanding, route reasoning, recurrent place analysis, destination selection | Text QA prompts, trajectory histories, route-step sequences, POI candidate lists |
| dual_space_design | 5 | UrbanAgent native probes | dual_space_probe | dual-space cognition | Structured junction, road, connectivity, and spatial-pattern feature packs |
| memory_continuity | 3 | UrbanAgent native probes | memory_probe | memory continuity | Follow-up task states for Tokyo, Beijing, and Paris |
| tool_orchestration | 3 | UrbanAgent native probes | tool_orchestration_probe | tool orchestration and recovery | Tool-step programs including POI lookup, OSM analysis, and recovery from a missing tool |
| hitl_checkpoint | 3 | UrbanAgent native probes | hitl_checkpoint_probe | human checkpoint controllability | Workflow states, selected proposals, and user-issued modification or cancel actions |
| external_open_workflow_t1_core | 9 | GeoAnalystBench | open_workflow_planning | workflow planning | Curated open urban workflow seeds with explicit workflow steps and deliverables |
| external_open_workflow_t2_standard | 9 | GeoBenchX | open_workflow_planning | workflow planning | Official open workflow catalog tasks from GeoBenchX |

## 2. Pilot40 score summary

| Suite | Cases | Qwen | Kimi |
|---|---:|---:|---:|
| external_citydata_subset | 8 | 0.8750 | 0.7500 |
| dual_space_design | 5 | 0.8000 | 0.8000 |
| memory_continuity | 3 | 1.0000 | 1.0000 |
| tool_orchestration | 3 | 1.0000 | 1.0000 |
| hitl_checkpoint | 3 | 1.0000 | 1.0000 |
| external_open_workflow_t1_core | 9 | 0.2012 | 0.3574 |
| external_open_workflow_t2_standard | 9 | 0.2145 | 0.3263 |
| Overall | 40 | 0.7272 | 0.7477 |

Zero-score cases:

| Provider | Zero-score cases |
|---|---|
| Qwen | external_geoqa_2; dual_space_connected_1 |
| Kimi | external_geoqa_1; external_geoqa_2; dual_space_connected_1 |

Result artifacts:

| Provider | Result file |
|---|---|
| Qwen | artifacts/benchmarks/urbanworkflowbench_v1_2_results_20260425_164126.json |
| Kimi | artifacts/benchmarks/urbanworkflowbench_v1_2_results_20260425_164636.json |

## 3. Case list

| Suite | Case ID | Benchmark or data source | Brief task |
|---|---|---|---|
| external_citydata_subset | external_geoqa_1 | CityData GeoQA | Road-length multiple-choice question for a named road |
| external_citydata_subset | external_geoqa_2 | CityData GeoQA | Identify the most likely AOI from an environment description |
| external_citydata_subset | external_mobility_prediction_1 | CityData mobility, Tokyo | Predict the next stay from a historical trajectory sequence |
| external_citydata_subset | external_mobility_prediction_2 | CityData mobility, Mumbai | Predict the next stay from a historical trajectory sequence |
| external_citydata_subset | external_outdoor_navigation_1 | CityData outdoor navigation, Beijing | Follow a route sequence with three forward moves and stop |
| external_citydata_subset | external_outdoor_navigation_2 | CityData outdoor navigation, Beijing | Follow a route sequence with a left turn and stop |
| external_citydata_subset | external_urban_exploration_1 | CityData urban exploration | Choose the best next exploration target from Wardour Street nearby |
| external_citydata_subset | external_urban_exploration_2 | CityData urban exploration | Choose the best next exploration target from Rue Jules Auffret nearby |
| dual_space_design | dual_space_contains_1 | UrbanAgent native probe | Judge the contains relation from structured road-network features |
| dual_space_design | dual_space_aligned_1 | UrbanAgent native probe | Judge the aligned relation from structured road-network features |
| dual_space_design | dual_space_separated_1 | UrbanAgent native probe | Judge the separated relation from structured road-network features |
| dual_space_design | dual_space_adjacent_1 | UrbanAgent native probe | Judge the adjacent relation from structured road-network features |
| dual_space_design | dual_space_connected_1 | UrbanAgent native probe | Judge the connected relation from structured road-network features |
| memory_continuity | memory_mobility_1 | UrbanAgent native probe | Reuse prior context for a follow-up Tokyo mobility prediction |
| memory_continuity | memory_navigation_1 | UrbanAgent native probe | Reuse prior context for a follow-up Beijing navigation task |
| memory_continuity | memory_exploration_1 | UrbanAgent native probe | Reuse prior context for a follow-up Paris exploration decision |
| tool_orchestration | tool_orchestration_poi_lookup_1 | UrbanAgent native probe | Execute a POI lookup tool sequence |
| tool_orchestration | tool_orchestration_osm_analysis_1 | UrbanAgent native probe | Execute a chained OSM analysis tool sequence |
| tool_orchestration | tool_orchestration_recovery_1 | UrbanAgent native probe | Recover from a missing tool and continue with geocode and distance steps |
| hitl_checkpoint | hitl_scope_modify_1 | UrbanAgent native probe | Modify the workflow scope at a checkpoint and persist the patch |
| hitl_checkpoint | hitl_proposal_reselect_1 | UrbanAgent native probe | Reselect a proposal at the checkpoint stage |
| hitl_checkpoint | hitl_cancel_1 | UrbanAgent native probe | Cancel the workflow at the checkpoint stage |
| external_open_workflow_t1_core | open_geoanalystbench_1 | GeoAnalystBench | Find heat islands and at-risk populations in Madison, Wisconsin |
| external_open_workflow_t1_core | open_geoanalystbench_2 | GeoAnalystBench | Find future bus stop locations in Hamilton, Tennessee |
| external_open_workflow_t1_core | open_geoanalystbench_7 | GeoAnalystBench | Analyze the impacts of land subsidence on flooding |
| external_open_workflow_t1_core | open_geoanalystbench_8 | GeoAnalystBench | Find gap for Toronto fire station service coverage |
| external_open_workflow_t1_core | open_geoanalystbench_23 | GeoAnalystBench | Assess open space to lower flood insurance cost |
| external_open_workflow_t1_core | open_geoanalystbench_29 | GeoAnalystBench | Calculate travel time for a tsunami |
| external_open_workflow_t1_core | open_geoanalystbench_30 | GeoAnalystBench | Designate bike routes for commuting professionals |
| external_open_workflow_t1_core | open_geoanalystbench_34 | GeoAnalystBench | Estimate the accessibility of roads to rural areas in Japan |
| external_open_workflow_t1_core | open_geoanalystbench_37 | GeoAnalystBench | Analyze human sentiments of heat exposure using social media data |
| external_open_workflow_t2_standard | open_TASK_250309_135125_264811 | GeoBenchX | Create contour lines of snow accumulation in urban agglomerations |
| external_open_workflow_t2_standard | open_TASK_250309_135125_381719 | GeoBenchX | Calculate the total population affected by floods in Peru during February 2018 |
| external_open_workflow_t2_standard | open_TASK_250309_135125_208110 | GeoBenchX | Compare the population density along railways in Bangladesh with the national average |
| external_open_workflow_t2_standard | open_TASK_250309_135125_673274 | GeoBenchX | What percentage of Bangladesh's population lives within 5 km of a railway line? |
| external_open_workflow_t2_standard | open_TASK_250309_135125_133682 | GeoBenchX | Create a heatmap of earthquake occurrences in regions with high population growth |
| external_open_workflow_t2_standard | open_TASK_250309_135125_429627 | GeoBenchX | Calculate the average electric power consumption in African countries with power stations capacity above 1000 MW |
| external_open_workflow_t2_standard | open_TASK_250309_135125_631643 | GeoBenchX | Make a map visualizing the relationship between fertility rate and net migration normalized by total population across the world |
| external_open_workflow_t2_standard | open_TASK_250309_135125_710732 | GeoBenchX | How many mineral extraction facilities in Africa are located in countries with rapid urbanization? |
| external_open_workflow_t2_standard | open_TASK_250309_135125_763412 | GeoBenchX | Create contour lines from Chile's population density data in relation to rivers |

## 4. Interpretation notes

The Pilot40 subset is a development-stage validation pass rather than the final benchmark reported in the paper.
Its main value is diagnostic: the native design-sensitive probes are already stable across both backends, while open workflow planning remains the dominant source of difficulty.
This split is useful for writing Section 5 because it shows that orchestration, memory continuity, and HITL checkpoint control are already wired correctly even though cross-dataset workflow planning still needs improvement.