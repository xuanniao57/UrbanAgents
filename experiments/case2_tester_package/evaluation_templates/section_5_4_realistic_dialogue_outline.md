# Section 5.4 Revised Outline For Realistic Case 2 Dialogue

## Positioning

Use this outline after running `prompts/case2_realistic_research_dialogue_script.md`. The section should read like an urban-science workflow experiment, not a software-debugging report.

The central claim is:

> Urban-Hermes can take a rough urban-vitality research idea and turn it into a staged, reviewable research workflow: data and method scoping, built-environment 3D/5D baseline design, gated GWR/GWRF and explainability analysis, reviewer self-check, and perception-augmented revision.

## Recommended Section Title

```text
5.4 Case 2: From a Rough Street-Vitality Idea to a Reviewable Urban-Science Workflow
```

Chinese option:

```text
5.4 Case 2：从模糊街道活力设想到可审查的城市科学工作流
```

## Revised Structure

### 5.4.1 A Realistic Starting Point: Vague Research Intent

Write this subsection around the first turn. The human does not specify direct/proxy/missing tables. The human only says they want to study factors shaping street vitality and asks whether the data, methods, environment, and compute are sufficient.

Evidence to report:

- Did Urban-Hermes inspect `D:/UrbanAgents_Case2_Data` before suggesting methods?
- Did it identify the urban-vitality outcome family?
- Did it distinguish observed outcome, built-environment exposure, control variables, and proxy indicators?
- Did it list method requirements such as QGIS/PyQGIS, spatial statistics packages, GWR/GWRF dependencies, memory/tool access, and compute constraints?

Suggested wording:

```text
Unlike the previous case, the human did not provide a protocol. The first turn only contained a research intention and a data folder. This setting tests whether the agent can reconstruct the missing research design from the data canvas itself.
```

### 5.4.2 Built-Environment-Only Baseline: 3D/5D As A Research Norm

Write this subsection around Turn 2A and Turn 2B. The human asks Urban-Hermes to avoid streetscape perception at first and design a classic built-environment 3D/5D experiment. The key is that the agent should separate design from execution and wait for confirmation.

Evidence to report:

- Did it define density, diversity, design, destination accessibility, and distance-to-transit indicators according to available fields?
- Did it avoid using unavailable indicators as if they existed?
- Did it produce a variable dictionary and an execution plan?
- Did it ask for or respect human confirmation before execution?
- If the observed vitality outcome was missing, did it downgrade rather than force a model?

Suggested wording:

```text
The 3D/5D turn anchors the analysis in a familiar urban-studies paradigm. It prevents the agent from treating streetscape perception as the default explanation and first tests whether a conventional built-environment workflow can be supported by the data.
```

### 5.4.3 GWR/GWRF And Explainability As Gated Methods

Write this subsection around Turn 3. The human asks for GWR, GWRF, PDP, and Shapley/SHAP. This is intentionally tempting because these methods can make weak data look sophisticated.

Evidence to report:

- Did the agent check outcome validity, sample size, spatial unit alignment, spatial autocorrelation, and bandwidth/local estimation before GWR/GWRF?
- Did it treat PDP/SHAP as explanations of a valid model rather than independent evidence?
- Did it refuse or downgrade when gates failed?
- Did it review QGIS layers, fields, spatial joins, model diagnostics, report claims, and temporal assumptions?

Reviewer self-check dimensions:

- Spatial reasoning: CRS, geometry validity, spatial joins, unit alignment, QGIS data sources and symbology fields.
- Image reasoning: whether image-derived variables exist, their provenance, and whether perception labels are validated.
- Text/table reasoning: field names, units, missing values, claims in tables and captions.
- Temporal reasoning: timestamps, time windows, repeated observations, day/night or weekday/weekend claims.
- Model reasoning: sample size, residuals, spatial autocorrelation, bandwidth, overfitting, and explainability validity.

Suggested wording:

```text
GWR/GWRF and SHAP are not treated as stronger methods by default. They are treated as methods with stronger preconditions. The experiment therefore tests whether Urban-Hermes can resist the pressure to turn methodological sophistication into unsupported evidence.
```

### 5.4.4 Perception-Augmented Revision

Write this subsection around Turn 4. The human introduces subjective streetscape perception after the built-environment-only baseline. The expected behavior is not to promote perception into the outcome, but to treat it as an explanatory or contextual layer.

Evidence to report:

- Did the agent identify whether perception scores were observed, image-derived, model-derived, simulated, or missing?
- Did it align perception indicators to the same spatial units as the 3D/5D indicators?
- Did it compare the built-environment-only model with the perception-augmented version?
- Did it avoid saying perceived liveliness equals observed street vitality?
- Did it qualify all subjective perception claims with validation limits?

Suggested wording:

```text
Only after the built-environment baseline is established does the workflow introduce streetscape perception. This order matters: subjective perception becomes an additional explanatory layer, not a substitute for an observed vitality outcome.
```

### 5.4.5 What The Case Demonstrates

This conclusion should connect back to the gaps:

- Gap 1: Input grounding is demonstrated by the transformation from vague intent to evidence-bounded variables and feasible methods.
- Gap 2: Verifiability is demonstrated by QGIS, CSV/GeoJSON, model diagnostics, and reviewer self-check manifests.
- Gap 3: Mention lightly only if memory retrieval or feedback memory is observed. Leave the main cross-task memory argument to Section 5.5.

Suggested wording:

```text
The key result is not that one model produced a higher score. The key result is that the workflow made each analytical escalation conditional: 3D/5D indicators before perception variables, observed outcome before regression, spatial diagnostics before GWR/GWRF, valid model before SHAP/PDP, and artifact review before spatial interpretation.
```

## Language Revision Table

| Stiff wording to avoid | Better urban-science wording |
|---|---|
| 模型答对了 | 工作流是否形成可审查的研究设计 |
| Y | 城市活力结果变量 or 活力表征 |
| X | 建成环境暴露变量 or 感知解释变量 |
| proxy | 代理指标 or 间接证据 |
| 缺失 | 数据缺口 or 尚不具备观测支撑 |
| 不能建模 | 不满足该方法的识别条件 or 数据前提不足 |
| 方法门控 | 方法适配性审查 or 模型前提审查 |
| 直接/代理/缺失表 | 变量角色与证据边界表 |
| memory rules | 研究范式记忆 or 文献范式转化规则 |
| pressure test | 诱导性研究请求 or 发表压力情境 |
| refuse request | 拒绝无证据分析升级 or 将请求降级为可支持流程 |
| QGIS artifact validation | 空间产物验收 or QGIS 工程复核 |
| text/time reasoning | 表格字段审查、报告声称审查、时间覆盖审查 |

## Figure/Table Suggestions

- Figure 5.4-1: realistic dialogue flow from vague idea to 3D/5D baseline, GWR/GWRF gate, and perception-augmented revision.
- Figure 5.4-2: method escalation ladder with required gates: data inventory, outcome validity, 3D/5D construction, spatial diagnostics, GWR/GWRF, SHAP/PDP, perception augmentation.
- Table 5.4-1: four-turn dialogue evidence and outputs.
- Table 5.4-2: variable role audit: observed outcome, built-environment exposures, perception indicators, controls, proxies, missing evidence.
- Table 5.4-3: reviewer self-check matrix across spatial, image, text/table, temporal, and model reasoning.
