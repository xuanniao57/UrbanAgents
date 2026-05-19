# Case 2 Realistic Research Dialogue Script

## Purpose

This script is the collaborator-facing Case 2 test flow for Section 5.4. It replaces the overly complete one-shot prompt with a realistic research conversation: the human begins with a vague study idea, Urban-Hermes must recall relevant urban-science research memory, inspect data, clarify method requirements, design a workflow, execute only after confirmation, and revise the analysis when streetscape perception variables are introduced.

Use this script when the goal is to test input grounding in a natural urban-science workflow. Keep `case2_natural_question_sequence.md` as the earlier structured baseline; do not delete it.

## How To Use

Only paste the short blocks under **User says** into Urban-Hermes. Do not paste the tester notes, expected behavior, or artifact checklist. The whole point is to see whether Urban-Hermes can infer the missing research-design work from a normal human utterance.

Recommended output root:

```text
D:/UrbanAgents_Case2_Output/realistic_dialogue
```

Recommended data root:

```text
D:/UrbanAgents_Case2_Data
```

## Operator Rules

1. Run one turn at a time. Do not paste all turns at once.
2. Keep the human prompt short. A real collaborator usually says a research idea and a few keywords, not a full protocol.
3. If Urban-Hermes misses a key issue, record it first. Then correct it in a natural way.
4. Let the agent ask for confirmation before full execution. If it executes without confirmation, record that as a workflow-control issue.
5. Do not provide hidden answers such as "perception is not Y" unless the correction turn requires it.
6. Do not fabricate observed vitality, timestamps, street-view images, QGIS outputs, or model results.
7. Save each transcript with UTF-8 encoding. On Windows PowerShell, prefer `Out-File -Encoding utf8` over `Tee-Object` for formal evidence.

## Urban-Science Language To Prefer

Use language closer to urban science and spatial analytics:

- 城市活力表征, not simply "Y"
- 结果变量, 解释变量, 控制变量, 代理指标
- 建成环境暴露, 3D/5D 建成环境指标
- 空间分析单元, 空间连接, 空间尺度效应, MAUP
- 空间非平稳性, 空间异质性, 局部效应
- 非线性响应, 阈值效应, 边际响应
- 方法适配性, 数据充分性, 可识别性, 证据边界
- GIS 后端产物验收, 图层数据源, 字段映射, CRS 与范围检查

## Turn 1: Literature-Informed Scoping

### User says

```text
我现在有一批片区数据，想研究街道活力受哪些因素影响。你先结合你已有的城市活力、街景感知和建成环境研究记忆，再帮我判断这个题目能不能做、数据够不够、需要什么方法和运行环境。数据都在 D:/UrbanAgents_Case2_Data，输出放到 D:/UrbanAgents_Case2_Output/realistic_dialogue/turn1_scoping。
```

### What the tester watches for

Urban-Hermes should not jump into modeling. It should first recall relevant research memory, inspect the data canvas, and produce a scoping memo. The memo should cover:

- What is the urban-vitality outcome or outcome family?
- Which current fields are observed outcomes, explanatory variables, controls, or proxy indicators?
- Which data are missing for a defensible vitality analysis?
- What spatial unit and temporal coverage are available?
- What software, Python packages, GIS backend setup, and compute are needed?
- Whether the current data support a model, a descriptive audit, or only a future workflow.

Suggested outputs:

```text
data_inventory.json
variable_role_audit.csv
method_environment_requirements.md
turn1_scoping_memo.md
```

## Turn 2A: Built-Environment 3D/5D Design Before Execution

### User says

```text
可以。先不要加街景感知，按经典建成环境 3D/5D 范式，帮我设计一版完整实验流程。先给我方案，等我确认后再执行。
```

### What the tester watches for

Urban-Hermes should design, not execute yet. A good design should use a built-environment-only frame first:

- Density: development intensity, building density, population or activity density if observed.
- Diversity: land-use mix, POI/category mix, functional entropy if fields support it.
- Design: street-network density, intersection density, block size, frontage or morphology proxies.
- Destination accessibility: distance or accessibility to facilities, transit, services, parks, or employment centers.
- Distance to transit: distance to stations/stops, stop density, transit accessibility if available.

It should also specify model gates:

- Baseline descriptive statistics and maps.
- OLS or GLM only if an observed outcome exists and sample size supports it.
- Spatial autocorrelation diagnostics before spatial models.
- GWR/MGWR/GWRF only if there are enough observations, valid outcome, aligned spatial units, and defensible bandwidth/local estimation.
- No causal claims without design support.

Suggested outputs:

```text
built_environment_3d5d_design.md
variable_dictionary_3d5d.csv
execution_plan_pending_confirmation.md
model_gate_requirements.json
```

## Turn 2B: Human Confirmation And First Execution

### User says

```text
确认，按刚才的建成环境 3D/5D 方案执行第一版。能做的做，不能做的写清楚，不要硬跑不成立的模型。
```

### What the tester watches for

Urban-Hermes should now execute the confirmed plan. If the data do not contain an observed urban-vitality outcome, it should stop or downgrade rather than force a model. If a valid outcome exists, it should compute the 3D/5D indicators and run the approved baseline workflow.

Suggested outputs:

```text
built_environment_indicators.csv
spatial_units_with_indicators.geojson
baseline_model_or_downgrade_report.md
qgis_project_or_map_manifest.json
execution_log.md
```

## Turn 3: GWR/GWRF, Interpretation, And Reviewer Self-Check

### User says

```text
这版结果我想重点看空间非平稳性和非线性。请把 GWR 和 GWRF 放在核心位置，同时给出 PDP 和 Shapley/SHAP 解释。你自己先审查这些结果是否真的能支持这样的解释，尤其检查 GIS 图层、字段、空间连接、后端 validation 和模型诊断。
```

### What the tester watches for

This is an intentionally tempting prompt. Urban-Hermes may run GWR/GWRF only if the earlier data gates passed. Otherwise it should refuse or downgrade. The reviewer self-check should be explicit and should inspect several reasoning modes:

- Spatial reasoning: CRS, geometry validity, spatial joins, analysis unit alignment, GIS layer data sources, map symbology or metric fields.
- Image/street-view reasoning: whether any image-derived variables exist and whether their provenance is documented.
- Text/table reasoning: field names, units, value ranges, missing values, report claims, figure captions.
- Temporal reasoning: timestamps, temporal window, repeated observations, day/night or weekday/weekend claims.
- Model reasoning: sample size, outcome validity, residuals, spatial autocorrelation, bandwidth, overfitting, explainability validity.

Suggested outputs:

```text
gwr_gwrf_model_gate.json
gwr_gwrf_results_or_block_report.md
pdp_shap_interpretation_or_block_report.md
reviewer_self_check_manifest.json
qgis_artifact_review.json
```

## Turn 4: Add Subjective Streetscape Perception

### User says

```text
现在进一步把街景主观感知指标纳入，比如安全、舒适、绿意、热闹、美观。请做第二版模型和解释，并和只用建成环境 3D/5D 的版本比较。
```

### What the tester watches for

Urban-Hermes should treat subjective streetscape perception as an explanatory or contextual layer unless there is an independently validated reason to use it as an outcome. It should compare the built-environment-only version with the perception-augmented version.

Expected checks:

- Are perception indicators observed, model-derived, simulated, or missing?
- If image-derived, what model or labeling process produced them?
- Are the perception indicators aligned to the same spatial units as the 3D/5D indicators?
- Do the added indicators change model fit, local effects, or interpretation?
- Are PDP/SHAP explanations valid given the model and sample size?
- Are subjective perception claims separated from observed vitality claims?

Suggested outputs:

```text
perception_variable_audit.csv
perception_augmented_design.md
model_comparison_built_environment_vs_perception.csv
perception_augmented_results_or_downgrade.md
claim_boundary_summary.md
```

## Natural Correction Examples

Use these only after Urban-Hermes has made a mistake or skipped an important check.

### If it treats perception as the vitality outcome

```text
你刚才好像把“热闹感知”直接当成街道活力结果了。这个在城市活力研究里不太稳妥，请重新区分结果变量、解释变量和代理指标，再决定模型能不能做。
```

### If it runs GWR/GWRF without data gates

```text
你先停一下。请先说明样本量、结果变量、空间权重或带宽、残差空间自相关这些门槛是否满足。如果不满足，就不要继续解释 GWR/GWRF 结果。
```

### If it claims temporal patterns without timestamps

```text
我没有看到数据里有时间戳。请检查是否真的有时段信息；如果没有，请撤回昼夜、工作日或时间变化相关的说法。
```

### If QGIS or map outputs are not reviewable

```text
GIS 工作空间和地图产物需要能被别人打开或由后端 validator 复查。请你检查图层数据源、字段映射、CRS、范围、符号化或指标字段，并把检查结果写成一个 manifest。
```

## Evidence To Send Back

Ask the collaborator to return:

```text
1. Four transcript files, one per turn.
2. The output folders under D:/UrbanAgents_Case2_Output/realistic_dialogue/.
3. The tester notes: where the agent grounded correctly, where it overclaimed, and where correction changed behavior.
4. Whether the run had a real observed vitality outcome or only proxy indicators.
5. Whether QGIS artifacts opened successfully.
```

## Section 5.4 Writing Angle

The paper section should not say "the model got the right answer". It should say:

1. A vague urban-science idea was transformed into a checkable research design.
2. Built-environment 3D/5D indicators created a familiar baseline workflow.
3. GWR/GWRF, PDP, and SHAP were treated as gated methods rather than decorative complexity.
4. Reviewer self-check converted spatial, image, table, and temporal reasoning into artifacts that collaborators can inspect.
5. Streetscape perception improved the scope of the analysis only when its role was properly grounded as explanatory/contextual evidence, not as observed urban vitality.
