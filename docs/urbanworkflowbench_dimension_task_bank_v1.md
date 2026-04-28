# UrbanWorkflowBench 六维度任务银行草案 v1

本文件给出一版面向论文写作和 benchmark 资产重组的任务银行草案。

目标不是立即替换当前 runner，而是先把三件事钉清楚：

1. 六个 benchmark 能力维度各自到底测什么。
2. 每道题可以追溯到哪些现有数据源或现有 probe 资产。
3. 每道题应如何定义 gold answer 和评估协议。

说明：

1. 下列题目分为两类：
   - existing：可以直接由当前 CityData / UrbanWorkflowBench / open workflow 资产实例化。
   - derived：基于现有资产做模板化扩展，来源仍可追溯，但需要在后续 manifest builder 中显式落地。
2. USTBench 当前仅作为维度设计参考，不作为本地题目直接来源，因为仓库中没有稳定公开的任务库入口。
3. 题号格式为 D{dimension}-{index}。

## 一、六个能力维度

1. Spatial Evidence Understanding
2. Urban State Forecasting
3. Workflow Grounding and Planning
4. Tool-Orchestrated Analytical Execution
5. Place-Based Memory Continuity
6. Governed Decision Support and Reflective Revision

## 二、数据源索引

- SRC-CD-GEOQA
  - 类型：existing
  - 数据源：CityData GeoQA
  - 路径：third_party/CityBench-main/citydata/task_Geo_knowledge/*/*/eval_*.csv
  - 可用字段：question, answer, A, B, C, D, E

- SRC-CD-MOB
  - 类型：existing
  - 数据源：CityData mobility
  - 路径：third_party/CityBench-main/citydata/mobility/checkin_split/*.csv 和 third_party/CityBench-main/citydata/mobility/checkin_test_pk/*_fin.pk
  - 可用字段：user history, context_stay, target_stay, Y

- SRC-CD-NAV
  - 类型：existing
  - 数据源：CityData outdoor navigation
  - 路径：third_party/CityBench-main/citydata/outdoor_navigation_tasks/*
  - 可用字段：start, end, steps, route_actions, ground_truth

- SRC-CD-EXP
  - 类型：existing
  - 数据源：CityData urban exploration
  - 路径：third_party/CityBench-main/citydata/exploration_tasks/*
  - 可用字段：candidates, selected_option, selected_destination, ground_truth_option or destination

- SRC-CD-STV
  - 类型：existing
  - 数据源：CityData street-view geolocation
  - 路径：third_party/CityBench-main/citydata/street_view/*_CUT/*.jpg
  - 可用字段：image_path, city_options, ground_truth city

- SRC-CD-POP
  - 类型：existing
  - 数据源：CityData remote sensing population
  - 路径：third_party/CityBench-main/citydata/remote_sensing/*_img_indicators.csv 和 third_party/CityBench-main/citydata/remote_sensing/<city>/*.png
  - 可用字段：worldpop, nightlight, carbon, choices, ground_truth_option

- SRC-CD-OBJ
  - 类型：existing
  - 数据源：CityData remote sensing object detection
  - 路径：third_party/CityBench-main/citydata/remote_sensing/all_city_img_object_set.json 和 third_party/CityBench-main/citydata/remote_sensing/<city>/*.png
  - 可用字段：object presence label set, image_id, ground_truth object list

- SRC-CD-TRAF
  - 类型：existing
  - 数据源：CityData traffic proxy built by TrafficSignalAdapter
  - 路径：scripts/benchmarks/run_citydata_quick_benchmark.py
  - 可用字段：queue_lengths, phase_map, phase_options, ground_truth phase, ground_truth_option

- SRC-UW-REL
  - 类型：existing
  - 数据源：UrbanWorkflowBench native relation probes
  - 路径：artifacts/benchmarks/urbanworkflowbench_v1_1_manifest_latest.json
  - 代表 case：dual_space_contains_1, dual_space_aligned_1, dual_space_separated_1, dual_space_adjacent_1, dual_space_connected_1
  - 可用字段：features, expected_relation

- SRC-UW-MEM
  - 类型：existing
  - 数据源：UrbanWorkflowBench memory continuity probes
  - 路径：artifacts/benchmarks/urbanworkflowbench_v1_1_manifest_latest.json
  - 代表 case：memory_mobility_1, memory_navigation_1, memory_exploration_1
  - 可用字段：memory_seed, task, evaluation.expected*

- SRC-UW-TMEM
  - 类型：existing
  - 数据源：temporal memory probe cases
  - 路径：artifacts/benchmarks/temporal_memory_probe_cases.json
  - 代表 case：temporal_conflict_mobility, temporal_weekday_traffic, temporal_season_exploration, temporal_recency_navigation
  - 可用字段：memory_seed, temporal_context, evaluation.expected*

- SRC-UW-TOOL
  - 类型：existing
  - 数据源：UrbanWorkflowBench tool orchestration probes
  - 路径：artifacts/benchmarks/urbanworkflowbench_v1_1_manifest_latest.json
  - 代表 case：tool_orchestration_poi_lookup_1, tool_orchestration_osm_analysis_1, tool_orchestration_recovery_1
  - 可用字段：tool_steps, workflow_expectation.expected_tools, required_successes, recovery_expected

- SRC-UW-HITL
  - 类型：existing
  - 数据源：UrbanWorkflowBench HITL checkpoint probes
  - 路径：artifacts/benchmarks/urbanworkflowbench_v1_1_manifest_latest.json
  - 代表 case：hitl_scope_modify_1, hitl_proposal_reselect_1, hitl_cancel_1
  - 可用字段：state, checkpoint_flow, evaluation.expected_final, evaluation.cancelled

- SRC-OW-GAB
  - 类型：existing
  - 数据源：GeoAnalystBench task bank in UrbanWorkflowBench open workflow bank
  - 路径：benchmarks/urbanworkflowbench/v1_1/open_workflow_task_bank.json
  - 原始来源：third_party/GeoAnalystBench/dataset/GeoAnalystBench.csv
  - 可用字段：task_title, task_instruction, workflow_steps, dataset_description

- SRC-OW-GBX
  - 类型：existing
  - 数据源：GeoBenchX task bank in UrbanWorkflowBench open workflow bank
  - 路径：benchmarks/urbanworkflowbench/v1_1/open_workflow_task_bank.json
  - 原始来源：third_party/GeoBenchX/benchmark_set/tasks_and_reference_solutions.json
  - 可用字段：task_title, task_instruction, workflow_steps, reference_tool_steps, dataset_description

## 三、评分协议索引

- SC-01 Option Exact Match
  - 适用：多项选择题
  - 评分：预测选项与 gold option 完全一致记 1，否则 0。

- SC-02 Numeric Relative Error or Nearest-Option
  - 适用：人口估计等数值任务
  - 评分：若存在 gold option，则按 SC-01；否则按 1 - relative_error，最低截断为 0。

- SC-03 Set F1
  - 适用：对象检测类任务
  - 评分：对 predicted set 与 gold set 计算 precision, recall, F1，以 F1 为主分数。

- SC-04 City Exact Match
  - 适用：城市识别
  - 评分：预测城市名标准化后与 gold city 完全一致记 1，否则 0。

- SC-05 Location ID Exact Match
  - 适用：mobility next-location prediction
  - 评分：predicted_location 与 gold location id 完全一致记 1，否则 0。

- SC-06 Action Sequence Exact Match
  - 适用：outdoor navigation
  - 评分：route_actions 与 gold action list 顺序完全一致记 1，否则 0。

- SC-07 Phase or Signal Option Exact Match
  - 适用：traffic proxy
  - 评分：selected_phase 或 selected_option 与 gold 完全一致记 1，否则 0。

- SC-08 Relation Label Exact Match
  - 适用：结构关系判断
  - 评分：predicted relation 与 expected_relation 完全一致记 1，否则 0。

- SC-09 Workflow Step F1 + Order Consistency
  - 适用：workflow grounding and planning
  - 评分：
    - step coverage F1：预测步骤集合与 reference workflow_steps 的 F1。
    - order consistency：预测序列中相邻关键步骤的顺序正确比例。
    - 最终分数默认 = 0.7 * F1 + 0.3 * order consistency。

- SC-10 Reference Tool Sequence Match
  - 适用：tool orchestration
  - 评分：
    - tool selection accuracy
    - sequence match
    - valid call rate
    - 若 recovery_expected 为 true，再加 recovery success
    - 最终分数默认平均。

- SC-11 Memory Transfer Exact Match
  - 适用：memory continuity
  - 评分：最终答案与 memory-conditioned gold 完全一致记 1，否则 0；同时记录 retrieved seed 是否正确，作为诊断信号。

- SC-12 Checkpoint Compliance and Patch Persistence
  - 适用：HITL 与 governed revision
  - 评分：
    - 是否执行 checkpoint action
    - 修改是否写入最终状态
    - reject 是否正确终止
    - 默认取三项平均。

- SC-13 Ranked Decision Quality
  - 适用：候选方案排序
  - 评分：
    - 若任务要求 top-1，按 top-1 exact match。
    - 若任务要求全排序，按 Kendall tau 或 NDCG。

- SC-14 Evidence-Grounded Governance Rubric
  - 适用：治理型建议与反思修订
  - 评分项：
    - decision correctness
    - evidence traceability
    - policy compliance
    - revision faithfulness
    - 每项 0/0.5/1，平均后得到最终分数。

## 四、D1 Spatial Evidence Understanding（20 题）

1. D1-01；题目：给定 CityData GeoQA 的道路长度题，判断哪一个选项最符合题干描述；来源：SRC-CD-GEOQA；gold：CSV 中 answer 字段；评估：SC-01。
2. D1-02；题目：给定 CityData GeoQA 的 AOI 描述题，从 A-E 中选出最可能地点；来源：SRC-CD-GEOQA；gold：CSV 中 answer 字段；评估：SC-01。
3. D1-03；题目：给定 CityData GeoQA 的设施语义题，识别最可能的地理对象类别；来源：SRC-CD-GEOQA；gold：CSV 中 answer 字段；评估：SC-01。
4. D1-04；题目：给定 CityData GeoQA 的区域功能判断题，选出最合理空间解释；来源：SRC-CD-GEOQA；gold：CSV 中 answer 字段；评估：SC-01。
5. D1-05；题目：给定 street_view 样本，候选城市为 Beijing, Moscow, Paris, Tokyo，识别所属城市；来源：SRC-CD-STV；gold：样本目录城市名；评估：SC-04。
6. D1-06；题目：给定另一张 street_view 样本，识别所属城市；来源：SRC-CD-STV；gold：样本目录城市名；评估：SC-04。
7. D1-07；题目：给定第三张 street_view 样本，识别所属城市；来源：SRC-CD-STV；gold：样本目录城市名；评估：SC-04。
8. D1-08；题目：给定第四张 street_view 样本，识别所属城市；来源：SRC-CD-STV；gold：样本目录城市名；评估：SC-04。
9. D1-09；题目：给定 remote sensing 样本，输出主要对象集合；来源：SRC-CD-OBJ；gold：all_city_img_object_set.json 中 positives；评估：SC-03。
10. D1-10；题目：给定第二张 remote sensing 样本，输出主要对象集合；来源：SRC-CD-OBJ；gold：object label positives；评估：SC-03。
11. D1-11；题目：给定第三张 remote sensing 样本，输出主要对象集合；来源：SRC-CD-OBJ；gold：object label positives；评估：SC-03。
12. D1-12；题目：给定第四张 remote sensing 样本，输出主要对象集合；来源：SRC-CD-OBJ；gold：object label positives；评估：SC-03。
13. D1-13；题目：给定 remote sensing + indicator_values，选择最接近真实人口估计的选项；来源：SRC-CD-POP；gold：ground_truth_option；评估：SC-02。
14. D1-14；题目：给定另一组 indicator_values，选择最接近真实人口估计的选项；来源：SRC-CD-POP；gold：ground_truth_option；评估：SC-02。
15. D1-15；题目：给定第三组 indicator_values，选择最接近真实人口估计的选项；来源：SRC-CD-POP；gold：ground_truth_option；评估：SC-02。
16. D1-16；题目：给定第四组 indicator_values，在不提供选项时直接估计人口数值；来源：SRC-CD-POP derived；gold：worldpop；评估：SC-02。
17. D1-17；题目：根据结构化 road-network features 判断关系是否为 contains；来源：SRC-UW-REL；gold：dual_space_contains_1.expected_relation=contains；评估：SC-08。
18. D1-18；题目：根据结构化 features 判断关系是否为 aligned；来源：SRC-UW-REL；gold：dual_space_aligned_1.expected_relation=aligned；评估：SC-08。
19. D1-19；题目：根据结构化 features 判断关系是否为 separated；来源：SRC-UW-REL；gold：dual_space_separated_1.expected_relation=separated；评估：SC-08。
20. D1-20；题目：根据结构化 features 判断关系是否为 connected；来源：SRC-UW-REL；gold：dual_space_connected_1.expected_relation=connected；评估：SC-08。

## 五、D2 Urban State Forecasting（20 题）

1. D2-01；题目：给定 Tokyo mobility 历史序列，预测下一停留 location id；来源：SRC-CD-MOB；gold：test sample 的 Y；评估：SC-05。
2. D2-02；题目：给定 Mumbai mobility 历史序列，预测下一停留 location id；来源：SRC-CD-MOB；gold：Y；评估：SC-05。
3. D2-03；题目：给定第三个 mobility 测试样本，预测下一 location id；来源：SRC-CD-MOB；gold：Y；评估：SC-05。
4. D2-04；题目：给定第四个 mobility 测试样本，预测下一 location id；来源：SRC-CD-MOB；gold：Y；评估：SC-05。
5. D2-05；题目：给定第五个 mobility 测试样本，预测下一 location id；来源：SRC-CD-MOB；gold：Y；评估：SC-05。
6. D2-06；题目：给定第六个 mobility 测试样本，预测下一 location id；来源：SRC-CD-MOB；gold：Y；评估：SC-05。
7. D2-07；题目：给定第七个 mobility 测试样本，预测下一 location id；来源：SRC-CD-MOB；gold：Y；评估：SC-05。
8. D2-08；题目：给定第八个 mobility 测试样本，预测下一 location id；来源：SRC-CD-MOB；gold：Y；评估：SC-05。
9. D2-09；题目：给定 queue_lengths，预测应优先放行的相位；来源：SRC-CD-TRAF；gold：ground_truth phase；评估：SC-07。
10. D2-10；题目：给定第二组 queue_lengths，预测应优先放行的相位选项；来源：SRC-CD-TRAF；gold：ground_truth_option；评估：SC-07。
11. D2-11；题目：给定第三组 queue_lengths，预测应优先放行的相位；来源：SRC-CD-TRAF；gold：ground_truth phase；评估：SC-07。
12. D2-12；题目：给定第四组 queue_lengths，预测应优先放行的相位选项；来源：SRC-CD-TRAF；gold：ground_truth_option；评估：SC-07。
13. D2-13；题目：给定 exploration 候选点集，选择最佳下一探索目标；来源：SRC-CD-EXP；gold：ground_truth option；评估：SC-01。
14. D2-14；题目：给定第二个 exploration 样本，选择最佳下一探索目标；来源：SRC-CD-EXP；gold：ground_truth option；评估：SC-01。
15. D2-15；题目：给定第三个 exploration 样本，选择最佳下一探索目标；来源：SRC-CD-EXP；gold：ground_truth option；评估：SC-01。
16. D2-16；题目：给定第四个 exploration 样本，输出预测 destination 名称；来源：SRC-CD-EXP derived；gold：ground_truth_destination；评估：SC-01 或 exact destination match。
17. D2-17；题目：给定 outdoor navigation 步骤描述，预测完整 route_actions；来源：SRC-CD-NAV；gold：ground_truth route_actions；评估：SC-06。
18. D2-18；题目：给定第二个 navigation 样本，预测完整 route_actions；来源：SRC-CD-NAV；gold：ground_truth route_actions；评估：SC-06。
19. D2-19；题目：给定第三个 navigation 样本，预测完整 route_actions；来源：SRC-CD-NAV；gold：ground_truth route_actions；评估：SC-06。
20. D2-20；题目：给定第四个 navigation 样本，预测完整 route_actions；来源：SRC-CD-NAV；gold：ground_truth route_actions；评估：SC-06。

## 六、D3 Workflow Grounding and Planning（20 题）

1. D3-01；题目：为“Find heat islands and at-risk populations in Madison, Wisconsin”写出最小有效 workflow plan；来源：SRC-OW-GAB；gold：GeoAnalystBench 任务 geoanalystbench_1.workflow_steps；评估：SC-09。
2. D3-02；题目：为同一任务列出必须加载的数据层；来源：SRC-OW-GAB；gold：Temperature.geojson 和 CensusBlock.geojson；评估：SC-09，以 required input coverage 为主。
3. D3-03；题目：为“Find future bus stop locations in Hamilton, Tennessee”写出 workflow plan；来源：SRC-OW-GAB；gold：geoanalystbench_2.workflow_steps；评估：SC-09。
4. D3-04；题目：为“Analyze the impacts of land subsidence on flooding”写出 workflow plan；来源：SRC-OW-GAB；gold：geoanalystbench_7.workflow_steps；评估：SC-09。
5. D3-05；题目：为“Find gap for Toronto fire station service coverage”写出 workflow plan；来源：SRC-OW-GAB；gold：geoanalystbench_8.workflow_steps；评估：SC-09。
6. D3-06；题目：为“Assess Open Space to Lower Flood Insurance Cost”写出 workflow plan；来源：SRC-OW-GAB；gold：geoanalystbench_23.workflow_steps；评估：SC-09。
7. D3-07；题目：为“Calculate Travel Time for a Tsunami”写出 workflow plan；来源：SRC-OW-GAB；gold：geoanalystbench_29.workflow_steps；评估：SC-09。
8. D3-08；题目：为“Designate bike routes for commuting professionals”写出 workflow plan；来源：SRC-OW-GAB；gold：geoanalystbench_30.workflow_steps；评估：SC-09。
9. D3-09；题目：为“Estimate the accessibility of roads to rural areas in Japan”写出 workflow plan；来源：SRC-OW-GAB；gold：geoanalystbench_34.workflow_steps；评估：SC-09。
10. D3-10；题目：为“Map air quality index for major cities in South Asia?”判断该任务是否应直接拒绝；来源：SRC-OW-GBX；gold：reference tool step 为 reject_task；评估：SC-09，要求输出 reject_task。
11. D3-11；题目：为“Which Eastern African countries had the highest net migration rates in 2019?”写出 workflow plan；来源：SRC-OW-GBX；gold：TASK_250309_135125_734213.reference_tool_steps 或 workflow_steps；评估：SC-09。
12. D3-12；题目：为“How many Latin American seaports are located in regions with high population growth?”写出 workflow plan；来源：SRC-OW-GBX；gold：TASK_250309_135125_104119.reference_tool_steps；评估：SC-09。
13. D3-13；题目：为“What is the total length of railways in Brazilian states with GDP per capita above national average?”判断是否拒绝；来源：SRC-OW-GBX；gold：reject_task；评估：SC-09。
14. D3-14；题目：为“How many people live within 1 km from a railway in Bangladesh”写出最小 workflow；来源：SRC-OW-GBX；gold：TASK_250309_135125_618282.reference_tool_steps；评估：SC-09。
15. D3-15；题目：为“What is the total length of railways within areas that received more than 3 feet of snow this season in the USA?”写出最小 workflow；来源：SRC-OW-GBX；gold：TASK_250309_135125_310610.reference_tool_steps；评估：SC-09。
16. D3-16；题目：针对 walkability_assessment，用户将研究半径从 500m 改为 800m，重写 task grounding；来源：SRC-UW-HITL；gold：task_interpretation.location 和 radius 应与 expected_final 一致；评估：SC-12。
17. D3-17；题目：针对 connectivity_analysis，在 proposal pool 中重选更合适候选；来源：SRC-UW-HITL；gold：selected_proposals 应改为 add_crosswalk + add_green_link；评估：SC-12。
18. D3-18；题目：针对 general_analysis，用户在 checkpoint 拒绝后给出正确终态；来源：SRC-UW-HITL；gold：cancelled=true，expected_final={}；评估：SC-12。
19. D3-19；题目：根据 temporal_conflict_mobility 的 query_time 和 task，判断应检索哪一类历史案例再进入 planning；来源：SRC-UW-TMEM；gold：morning_peak mobility seed；评估：SC-11。
20. D3-20；题目：根据 temporal_season_exploration 的 query_time，判断 planning 时优先采用哪条历史探索偏好；来源：SRC-UW-TMEM；gold：winter seed / Louvre；评估：SC-11。

## 七、D4 Tool-Orchestrated Analytical Execution（20 题）

1. D4-01；题目：执行 People's Square park lookup 时，给出正确工具序列；来源：SRC-UW-TOOL；gold：geocode -> get_poi；评估：SC-10。
2. D4-02；题目：执行 Shanghai OSM connectivity analysis 时，给出正确工具序列；来源：SRC-UW-TOOL；gold：query_osm -> spatial_analysis；评估：SC-10。
3. D4-03；题目：当 missing_tool 失败后，给出正确恢复后的工具序列；来源：SRC-UW-TOOL；gold：missing_tool -> geocode -> calculate_distance；评估：SC-10。
4. D4-04；题目：判断 tool_orchestration_poi_lookup_1 是否要求 sequence match；来源：SRC-UW-TOOL；gold：workflow_expectation.require_sequence_match=true；评估：SC-10。
5. D4-05；题目：判断 tool_orchestration_recovery_1 是否要求 recovery success；来源：SRC-UW-TOOL；gold：recovery_expected=true；评估：SC-10。
6. D4-06；题目：对 geoanalystbench_1，输出参考工具链的 canonical tool names；来源：SRC-OW-GAB；gold：由 workflow_steps 映射得到 load_data, interpolation, filter_features, spatial_join/merge, aggregate_stats, visualization；评估：SC-10。
7. D4-07；题目：对 geoanalystbench_2，输出参考工具链的 canonical tool names；来源：SRC-OW-GAB；gold：load_data, filter_features, overlay_analysis, visualization；评估：SC-10。
8. D4-08；题目：对 geoanalystbench_7，输出参考工具链的 canonical tool names；来源：SRC-OW-GAB；gold：load_data, raster_calculation, overlay_analysis, aggregate_stats, visualization；评估：SC-10。
9. D4-09；题目：对 geoanalystbench_8，输出参考工具链的 canonical tool names；来源：SRC-OW-GAB；gold：load_data, buffer, overlay_analysis, visualization；评估：SC-10。
10. D4-10；题目：对 geoanalystbench_30，输出参考工具链的 canonical tool names；来源：SRC-OW-GAB；gold：load_data, spatial_join, classification, network_analysis, reporting；评估：SC-10。
11. D4-11；题目：对 GeoBenchX 东非 migration 任务，输出 reference tool sequence；来源：SRC-OW-GBX；gold：load_data -> load_geodata -> filter_categorical -> merge_dataframes -> make_choropleth_map；评估：SC-10。
12. D4-12；题目：对 Latin America seaports 任务，输出 reference tool sequence；来源：SRC-OW-GBX；gold：TASK_250309_135125_104119.reference_tool_steps；评估：SC-10。
13. D4-13；题目：对 Bangladesh railway population 任务，输出 reference tool sequence；来源：SRC-OW-GBX；gold：load_geodata -> create_buffer -> get_raster_path -> get_values_from_raster_with_geometries；评估：SC-10。
14. D4-14；题目：对 USA snow-railway task，输出 reference tool sequence；来源：SRC-OW-GBX；gold：TASK_250309_135125_310610.reference_tool_steps；评估：SC-10。
15. D4-15；题目：对 South Asia AQI task，判断是否应真正执行工具调用；来源：SRC-OW-GBX；gold：否，应 reject_task；评估：SC-10。
16. D4-16；题目：在 bike routes 任务中，判断 network analysis 是否应早于 suitability analysis；来源：SRC-OW-GAB；gold：否，应先 suitability / demand delineation 再 network analysis；评估：SC-10。
17. D4-17；题目：在 Toronto fire station gap task 中，判断是否必须先 buffer 后 overlay；来源：SRC-OW-GAB；gold：是；评估：SC-10。
18. D4-18；题目：在 tsunami travel time task 中，判断 geodesic path derivation 是否在 speed raster 之后；来源：SRC-OW-GAB；gold：是；评估：SC-10。
19. D4-19；题目：在 rural road accessibility Japan task 中，判断 clip rural population 是否早于 2km buffer overlay；来源：SRC-OW-GAB；gold：是；评估：SC-10。
20. D4-20；题目：在 tool_orchestration_recovery_1 中，计算最少 required_successes；来源：SRC-UW-TOOL；gold：2；评估：SC-10。

## 八、D5 Place-Based Memory Continuity（20 题）

1. D5-01；题目：在 memory_mobility_1 中，后续 Tokyo mobility query 应返回哪个 predicted_location；来源：SRC-UW-MEM；gold：36153；评估：SC-11。
2. D5-02；题目：在 memory_navigation_1 中，后续 Beijing navigation query 应返回哪条 route_actions；来源：SRC-UW-MEM；gold：gold route from memory seed；评估：SC-11。
3. D5-03；题目：在 memory_exploration_1 中，后续 Paris exploration query 应返回哪个 selected_destination；来源：SRC-UW-MEM；gold：gold destination from memory seed；评估：SC-11。
4. D5-04；题目：在 temporal_conflict_mobility 中，早高峰 query 应检索哪个 seed；来源：SRC-UW-TMEM；gold：morning_peak seed；评估：SC-11。
5. D5-05；题目：在 temporal_conflict_mobility 中，最终 predicted_location 应为何；来源：SRC-UW-TMEM；gold：36153；评估：SC-11。
6. D5-06；题目：在 temporal_weekday_traffic 中，weekday query 应返回哪个 selected_phase；来源：SRC-UW-TMEM；gold：north_south；评估：SC-11。
7. D5-07；题目：在 temporal_season_exploration 中，winter query 应返回哪个 selected_destination；来源：SRC-UW-TMEM；gold：Louvre；评估：SC-11。
8. D5-08；题目：在 temporal_recency_navigation 中，最近一次 route 应覆盖更早 route；来源：SRC-UW-TMEM；gold：recent route_actions；评估：SC-11。
9. D5-09；题目：在 temporal_baseline_mobility 中，Berlin query 应返回哪个 predicted_location；来源：SRC-UW-TMEM；gold：42000；评估：SC-11。
10. D5-10；题目：在 temporal_traffic_weekday_beijing 中，weekday query 应返回哪个 selected_phase；来源：SRC-UW-TMEM；gold：protected_left；评估：SC-11。
11. D5-11；题目：对 Tokyo mobility 样本加入“上轮已确认 morning_peak 更稳定”的记忆，预测下一 location；来源：SRC-CD-MOB + SRC-UW-TMEM derived；gold：与 morning_peak memory 对齐的 location id；评估：SC-11。
12. D5-12；题目：对 Shanghai traffic proxy 样本加入“weekday 应优先 north_south”的记忆，预测当前 phase；来源：SRC-CD-TRAF + SRC-UW-TMEM derived；gold：north_south；评估：SC-11。
13. D5-13；题目：对 Paris exploration 样本加入“冬季偏好 Louvre”的记忆，选择下一 destination；来源：SRC-CD-EXP + SRC-UW-TMEM derived；gold：Louvre 或对应 option；评估：SC-11。
14. D5-14；题目：对 navigation 样本加入“北门封闭”的记忆，选择不经过北门的 route；来源：SRC-CD-NAV + SRC-UW-MEM derived；gold：绕行开放入口的 route_actions；评估：SC-11。
15. D5-15；题目：对 walkability 子任务加入“偏好有树荫路线”的用户记忆，二选一路线；来源：SRC-UW-MEM derived；gold：林荫连续路线；评估：SC-11。
16. D5-16；题目：对 exploration 子任务加入“避免商业街拥挤”的偏好记忆，二选一 destination；来源：SRC-UW-MEM derived；gold：较安静 destination；评估：SC-11。
17. D5-17；题目：对 mobility query 加入“上轮弱连接点 J7 已确认”的 place note，判断是否首先回看 J7；来源：SRC-UW-MEM derived；gold：是；评估：SC-11。
18. D5-18；题目：对交通相位选择加入“周末 east_west, 工作日 north_south”的时序记忆，当前周三应选哪一相位；来源：SRC-UW-TMEM derived；gold：north_south；评估：SC-11。
19. D5-19；题目：对探索样本加入“夏季 Grand Palais, 冬季 Louvre”的季节记忆，当前 1 月查询应返回何地；来源：SRC-UW-TMEM；gold：Louvre；评估：SC-11。
20. D5-20；题目：对 repeated navigation query，判断 recent route 是否应压过 older conflicting route；来源：SRC-UW-TMEM；gold：是，采用 recent route；评估：SC-11。

## 九、D6 Governed Decision Support and Reflective Revision（20 题）

1. D6-01；题目：在 hitl_scope_modify_1 中，用户把 location 改为 Shanghai Inner Ring、radius 改为 800，最终状态应为何；来源：SRC-UW-HITL；gold：evaluation.expected_final；评估：SC-12。
2. D6-02；题目：在 hitl_proposal_reselect_1 中，用户取消 add_flyover 后最终 selected_proposals 应为何；来源：SRC-UW-HITL；gold：add_crosswalk + add_green_link；评估：SC-12。
3. D6-03；题目：在 hitl_cancel_1 中，用户 reject 后系统是否应继续执行；来源：SRC-UW-HITL；gold：否，cancelled=true；评估：SC-12。
4. D6-04；题目：对 walkability_assessment，若用户要求扩大研究边界，是否必须重写 task_interpretation；来源：SRC-UW-HITL；gold：是；评估：SC-12。
5. D6-05；题目：对 connectivity_analysis，若用户重排 proposal pool，最终结果是否应保留旧 proposal；来源：SRC-UW-HITL；gold：否；评估：SC-12。
6. D6-06；题目：对 general_analysis，如果 checkpoint reject，最终 expected_final 是否应为空；来源：SRC-UW-HITL；gold：是；评估：SC-12。
7. D6-07；题目：在 Toronto fire station gap 任务上，若政策要求优先公平覆盖而非最小成本，应首选哪类建议；来源：SRC-OW-GAB derived；gold：优先覆盖缺口最大的 underserved area；评估：SC-14。
8. D6-08；题目：在 bike routes 任务上，若用户否决新增机动车道，应保留何类方案；来源：SRC-OW-GAB derived；gold：非机动车与慢行优先方案；评估：SC-14。
9. D6-09；题目：在 rural road accessibility Japan 任务上，若用户只关心偏远地区公平覆盖，应如何调整结论；来源：SRC-OW-GAB derived；gold：突出 underserved rural area 和 within-2km coverage gap；评估：SC-14。
10. D6-10；题目：在 heat island + elder population 任务上，若结论无 elder density evidence，是否允许直接通过；来源：SRC-OW-GAB derived；gold：否；评估：SC-14。
11. D6-11；题目：在 flood damage 任务上，若建筑损失公式未被引用或解释，是否应标记为 evidence incomplete；来源：SRC-OW-GAB；gold：是；评估：SC-14。
12. D6-12；题目：在 Bangladesh railway buffer 任务上，若模型给出人口数量但未说明 buffer 距离和 raster 源，是否应通过 review；来源：SRC-OW-GBX derived；gold：否；评估：SC-14。
13. D6-13；题目：在 migration choropleth 任务上，若用户要求只报告 Eastern Africa 而输出包含全非洲，是否符合治理约束；来源：SRC-OW-GBX；gold：不符合；评估：SC-14。
14. D6-14；题目：在 South Asia AQI 任务上，正确治理行为是直接执行还是 reject；来源：SRC-OW-GBX；gold：reject；评估：SC-14。
15. D6-15；题目：给定三个候选干预项目 P1, P2, P3 和公平/效率双指标，若政策权重为公平 0.7、效率 0.3，输出全排序；来源：SRC-UW-HITL derived；gold：按加权得分排序；评估：SC-13。
16. D6-16；题目：给定两个路线方案，用户明确要求“避免高架跨越”，应保留哪一方案；来源：SRC-UW-HITL derived；gold：不跨高架方案；评估：SC-14。
17. D6-17；题目：当 checkpoint 要求“从 autonomous 切到 supervised mode”时，系统是否应插入新的人工确认节点；来源：SRC-UW-HITL derived；gold：是；评估：SC-12。
18. D6-18；题目：当用户指出 POI 已失效后，后续建议是否应保留以该 POI 为锚点的结论；来源：SRC-UW-HITL derived；gold：否；评估：SC-14。
19. D6-19；题目：当用户要求解释为什么调用某个工具时，回答中是否必须引用 workflow step 与 expected deliverable；来源：SRC-UW-TOOL + SRC-OW-GAB derived；gold：是；评估：SC-14。
20. D6-20；题目：在 scope modify 后重新生成的建议，若仍沿用旧半径 500m 的排序结果，是否算 checkpoint compliant；来源：SRC-UW-HITL；gold：否；评估：SC-12。

## 十、后续落地建议

1. 先把上面 120 题中的 existing 题落进一个新的 capability-indexed manifest，形成 v2 alpha。
2. 将 derived 题分三批补齐：
   - 批次 A：CityData 派生题
   - 批次 B：memory / hitl 派生题
   - 批次 C：open workflow 治理型题
3. 论文中 Table 2 建议直接改写为“六个能力维度 × 数据源映射 × 当前覆盖状态”。
4. 当前 v1.2 的 suite 名不需要删除，但应退居为 runner-level implementation layer，而不是 benchmark dimension 本体。