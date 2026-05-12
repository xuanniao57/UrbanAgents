# Case Study 1: 宁波老外滩历史街区 X 指标构建

对应论文 Case Study 1。目标不是直接进入游客感知 `Y` 建模，而是先验证 UrbanAgent 能否从多源原始数据构建可审查、可修正、可复用的历史街区建成环境 `X` 指标。

## 核心问题

- **Gap 1 输入 grounding**：任务提示词和记忆能否自动加载 AOI、OSM/cache、建筑功能、街景等数据资源，并生成 dataset cards / grounding policy / computability matrix。
- **Gap 2 空间推理审查**：Review Hub 能否检查 AOI、context buffer、source extent、CRS、时间新鲜度、人群对象和治理证据。
- **Gap 3 纠偏记忆**：Reviewer 发现的问题能否写入 experience memory，并在下一次 Case1 或相似历史街区任务中复用。

## 任务输入

- `prompts/case1_task.md`：自然语言任务提示词，包含研究目标和数据资源描述。
- `task_input.json`：结构化任务输入。
- `workflow_memory/case1_heritage_workflow.json`：Case1 专属 workflow memory。
- `experience_memory/case1_feedback_20260511.jsonl`：上一次 reviewer 纠偏经验。

## Prompt + Memory 运行方式

UrbanAgent 核心包不内置宁波老外滩路径。运行 Case1 时，把本 case study 目录作为额外记忆根即可：

```powershell
$env:URBAN_AGENT_EXTRA_MEMORY_ROOTS="D:\GitHub_1\world_agent\urban-mobility-agent\paper4_urban_svgagent\case_studies\case1_heritage"
python -m urban_agent analyze --task "请完成 Case Study 1 宁波老外滩历史街区 X 指标构建，只根据任务提示词和记忆加载数据。"
```

在这个模式下，用户只需要提供任务提示词；AOI、功能数据、OSM/cache、街景路径和前次纠偏经验从 case memory 加载。核心 `urban_agent/memory` 只保留通用 policy/workflow，不写入具体案例名或路径。

## 数据资源

| 资源 | 角色 | 路径 |
|---|---|---|
| AOI boundary | `boundary` | `paper9_heritageIntelligence/data/district_boundaries_v2/district_boundaries/009_宁波_宁波老外滩_boundary.geojson` |
| OSM/cache | `roads/buildings/context` | `paper9_heritageIntelligence/heritage_district_batch/` |
| Building function source | `function_root` | `paper9_heritageIntelligence/data/sinobf1/` |
| Street-view images | `streetview_dir` | `D:/街景/streetview_images_batch/宁波/009_宁波老外滩` |

## 实验输出

- `runs/RUN_INDEX.md`：正式 ablation set、历史 run、重复 run 和不完整目录索引。
- `runs/LATEST_EXPERIMENT_REFLECTION.md`：最近一次实验结果反思和下一轮实验建议。
- `runs/ablation_table3_trials_20260509_complete.csv`：当前 21 条正式 trial。
- `runs/ablation_table3_trials_20260509_complete_aggregate.csv`：当前聚合表。

## 下一轮重点

下一次实验不再只看 `success=true`，而要增加 evidence completeness、artifact validity、computability correctness、reviewer issue detection、memory transfer reuse 等复合质量指标。
