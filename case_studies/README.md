# UrbanAgent Case Studies & Ablation Framework

> 设计思路参照 RDMA 的 ablation 风格：通过 feature-flag 控制消融，验证每个架构组件的必要性。

## 总体实验设计

两个端到端 case study + 每 case 7 组消融配置，覆盖三个 gap 对应的模块。

```
Case 1: 历史街区建成环境分析 (Heritage District X-Indicator Construction)
Case 2: 城市步行可达性评估 (Urban Walkability Assessment)
```

每组消融配置在 3 个 gap 维度上产生对应信号，汇总为 ablation table。

## Gap → Module → Flag 映射

| Gap | 问题 | 模块 | 消融 Flag |
|---|---|---|---|
| **Gap 1** 输入阶段 | 问题-数据-方法匹配 | PlannerAgent + CapabilityRegistry + EvidenceManifest | `enable_planning=False` |
| **Gap 2** 推理阶段 | 空间/时间/人群推理可靠性 | Review Hub + QualityController + DualSpace | `enable_review=False`, `enable_quality_control=False`, `enable_dual_space=False` |
| **Gap 3** 输出阶段 | 反馈→长期记忆复用 | FeedbackMemory + MemoryModule + RuntimeLedger | `enable_memory=False` |

## 消融矩阵 (每 Case)

| # | 配置 | Planning | Review | QC | DualSpace | Memory | 测试 Gap |
|---|---|---|---|---|---|---|---|
| C0 | FULL | ✓ | ✓ | ✓ | ✓ | ✓ | baseline |
| C1 | w/o Planning | ✗ | ✓ | ✓ | ✓ | ✓ | Gap 1 |
| C2 | w/o Review | ✓ | ✗ | ✓ | ✓ | ✓ | Gap 2 |
| C3 | w/o QC | ✓ | ✓ | ✗ | ✓ | ✓ | Gap 2 |
| C4 | w/o DualSpace | ✓ | ✓ | ✓ | ✗ | ✓ | Gap 2 |
| C5 | w/o Memory | ✓ | ✓ | ✓ | ✓ | ✗ | Gap 3 |
| C6 | VANILLA | ✗ | ✗ | ✗ | ✗ | ✗ | all |

## 评估信号

每配置采集以下信号用于对比：

| Gap | 信号 | 来源 |
|---|---|---|
| Gap 1 | evidence_manifest 是否生成、是否含 spatial/temporal/population/governance 四块 | `summary.json` |
| Gap 1 | selected_capabilities 是否与 task 匹配 | `manifest.json` → planner breadcrumb |
| Gap 2 | urban_validity_score 和 4 个 policy 分项得分 | `summary.json` → review |
| Gap 2 | hard_failures 数量 | `summary.json` → review |
| Gap 3 | feedback_lessons 是否注入 Planner 上下文 | `manifest.json` → planner |
| Gap 3 | RuntimeLedger 是否保留 checkpoint 记录 | `summary.json` → runtime |

## 目录结构

```
case_studies/
├── README.md                    # 本文件
├── ablation_config.yaml         # 消融配置清单
├── case1_heritage/
│   ├── README.md                # Case 1 详细说明
│   ├── task_input.json          # 标准化任务输入
│   ├── prompts/
│   │   └── case1_task.md        # 任务提示词
│   ├── data_manifest.json       # 数据清单（路径、格式、覆盖范围）
│   └── runs/
│       ├── 20260507_161034_full/ # C0: FULL 配置运行
│       ├── c1_wo_planning/       # C1: w/o Planning
│       ├── c2_wo_review/         # C2: w/o Review
│       ├── c3_wo_qc/             # C3: w/o QC
│       ├── c4_wo_dualspace/      # C4: w/o DualSpace
│       ├── c5_wo_memory/         # C5: w/o Memory
│       └── c6_vanilla/           # C6: VANILLA
└── case2_walkability/
    ├── README.md
    ├── task_input.json
    └── runs/
        └── ...
```

## 运行方式

在 `paper4_urban_svgagent` 目录下，通过 `scripts/run_ablation.py` 批量执行消融：

```bash
cd d:\GitHub_1\world_agent\urban-mobility-agent\paper4_urban_svgagent
conda activate urban-mobility
python scripts/run_ablation.py --case case1 --configs all
```

单次手动运行（测试用）：
```bash
python -m urban_agent analyze --input case_studies/case1_heritage/task_input.json
```
