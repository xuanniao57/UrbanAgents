# UrbanAgent

> An open framework for LLM-orchestrated urban spatial analysis.
>
> **[English](#english) | [中文](#中文)**

---

## English

### Overview

UrbanAgent is a multi-agent framework that uses Large Language Models to perform urban spatial analysis tasks — from geographic Q&A and walkability assessment to mobility prediction and route planning. It features a three-layer multi-agent architecture (Planner → Manager/Workers → Reviewer), dual-space spatial cognition (topological + vector), and an integrated benchmark suite (UrbanWorkflowBench) for systematic evaluation.

### Key Features

- **Three-Layer Multi-Agent Architecture** *(experimental — aligned with paper design, pending full validation)*
  - **PlannerAgent**: Task decomposition and complexity assessment
  - **ManagerAgent + Workers**: Coordinated execution with information isolation (Perception, Analyst, Cartographer, Reporter)
  - **SpatialReviewer + HumanCheckpoint**: Quality review and human-in-the-loop gating

- **Multi-Source Perception**: OpenStreetMap, remote sensing imagery, street-view classification, trajectory data

- **Dual-Space Cognition**: Combined topological (graph-based) and vector (coordinate-based) spatial reasoning

- **Multi-LLM Support**: Qwen, OpenAI, DeepSeek, Kimi — any OpenAI-compatible endpoint

- **UrbanWorkflowBench**: Built-in benchmark suite for evaluating agent capabilities across 8 urban task types

- **CLI + Python API + MCP Server**: Multiple integration modes

### Project Layout

```
urbanagent/
├── .env.example              # API key template
├── pyproject.toml             # Package metadata & dependencies
├── run_iterative_agent_cycle.py  # Iterative test runner
│
├── urban_agent/               # Core framework
│   ├── cli.py                 # CLI: python -m urban_agent <command>
│   ├── config.py              # Configuration dataclasses
│   ├── agents/                # Three-layer multi-agent system [experimental]
│   │   ├── orchestrator.py    # MultiAgentOrchestrator (main runtime)
│   │   ├── planner.py         # Task decomposition
│   │   ├── manager.py         # Execution orchestration
│   │   ├── workers.py         # Specialized workers
│   │   └── reviewers.py       # Quality review layer
│   ├── core/                  # Agent internals
│   │   ├── agent.py           # Async UrbanAgent controller
│   │   ├── perception.py      # Data ingestion pipeline
│   │   ├── reasoning.py       # Spatial reasoning engine
│   │   ├── memory.py          # Spatiotemporal memory
│   │   └── action.py          # Tool execution runtime
│   ├── perception/            # Data source processors
│   │   ├── osm_processor.py   # OpenStreetMap
│   │   ├── remote_sensing.py  # Satellite/aerial imagery
│   │   └── street_view.py     # Street-level classification
│   ├── cognition.py           # Dual-space cognition module
│   ├── decision.py            # Design generation
│   ├── visualization.py       # SVG overlay + GeoJSON export
│   ├── llm/                   # LLM client wrappers
│   └── evaluation/            # Task evaluation metrics
│
├── benchmarks/                # UrbanWorkflowBench
│   └── urbanworkflowbench/
│       ├── v1/                # v1.0: CityData subset + design probes + memory probes
│       ├── v1_1/              # v1.1: Open workflow task bank
│       └── v1_2/              # v1.2: Extended evaluation
│
├── scripts/
│   ├── benchmarks/            # Benchmark builders & runners
│   │   ├── build_urbanworkflowbench_v1.py
│   │   ├── run_urbanworkflowbench_v1.py
│   │   └── run_citydata_quick_benchmark.py
│   └── runners/               # Batch runners
│
├── tests/                     # Unit & integration tests
├── docs/                      # Architecture docs & runbooks
└── LICENSE                    # MIT
```

### Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/xuanniao57/urbanagent.git
cd urbanagent

# 2. Create environment
conda create -n urban-mobility python=3.10 -y
conda activate urban-mobility

# 3. Install dependencies
pip install -e .
# Or: pip install -r requirements_combined.txt

# 4. Configure API key
cp .env.example .env
# Edit .env → set at least ONE provider key (e.g., QWEN_API_KEY)

# 5. Run tests
pytest tests/ -q

# 6. Try the CLI
python -m urban_agent run --task-type geoqa --question "Analyze walkability around Tongji University"
```

### Usage

#### CLI

```bash
# End-to-end analysis pipeline
python -m urban_agent run --task-type geoqa --question "分析同济大学周边步行可达性"

# Step-by-step
python -m urban_agent perceive --data-type osm --bbox "121.4,31.2,121.5,31.3"
python -m urban_agent cognize --input perception_result.json
python -m urban_agent reason --task-type geoqa --input cognition_result.json --question "..."
python -m urban_agent visualize --input analysis_result.json --format svg
python -m urban_agent review --input results.json
```

#### Python API

```python
from urban_agent.agents import MultiAgentOrchestrator

orchestrator = MultiAgentOrchestrator()
result = await orchestrator.run(
    task="Analyze walkability around Tongji University",
    task_type="geoqa"
)
```

### LLM Configuration

Edit `.env` to switch providers:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `qwen` | `qwen` / `openai` / `deepseek` / `kimi` |
| `QWEN_API_KEY` | — | DashScope API key |
| `OPENAI_API_KEY` | — | OpenAI API key |
| `Deepseek_API_KEY` | — | DeepSeek API key |
| `KIMI_API_KEY` | — | Moonshot API key |

Any OpenAI-compatible endpoint works. See `.env.example` for all options.

### Supported Tasks (CityBench-aligned)

| Task | Description |
|------|-------------|
| `geoqa` | Geographic question answering |
| `population_prediction` | Population density estimation |
| `object_detection` | Urban object identification from imagery |
| `geolocation` | Reverse geocoding |
| `mobility_prediction` | Origin-destination flow forecasting |
| `traffic_signal` | Signal timing optimization |
| `outdoor_navigation` | Route planning |
| `urban_exploration` | Destination discovery & recommendation |

---

## UrbanWorkflowBench

UrbanWorkflowBench is an UrbanAgent-native benchmark protocol for evaluating workflow-oriented urban analysis agents. It tests not just task accuracy, but also spatial cognition and context continuity.

### Benchmark Structure

**v1.0** includes three test suites:

| Suite | Protocol | What it tests |
|-------|----------|---------------|
| `external_citydata_subset` | `agent_task` | Standard urban tasks (geoqa, mobility, navigation, exploration) using CityData |
| `dual_space_design` | `dual_space_probe` | Topological + vector spatial cognition (contains, aligned, separated, adjacent, connected) |
| `memory_continuity` | `memory_probe` | Context transfer across repeated tasks |

### Running the Benchmark

```bash
# Step 1: Build the benchmark manifest
python scripts/benchmarks/build_urbanworkflowbench_v1.py

# Step 2: Run without LLM (baseline / schema validation)
python scripts/benchmarks/run_urbanworkflowbench_v1.py --provider none

# Step 3: Run with an LLM provider
python scripts/benchmarks/run_urbanworkflowbench_v1.py --provider qwen
```

### CityData Setup (Required for benchmark)

The benchmark uses CityBench datasets. Download and place them:

```bash
# Download CityBench (not included in repo due to size)
# Place under: third_party/CityBench-main/citydata/
```

Refer to `docs/CITYBENCH_RUNBOOK.md` for detailed data setup instructions.

### Benchmark Output

Results are saved to `artifacts/benchmarks/`:
- `urbanworkflowbench_v1_manifest_*.json` — Test case definitions
- `urbanworkflowbench_v1_results_*.json` — Evaluation results with per-task scores

### Iterative Testing

Use the iterative cycle runner for repeated evaluation:

```bash
# Dry run (preview commands)
python run_iterative_agent_cycle.py --dry-run --iterations 3

# Full execution
python run_iterative_agent_cycle.py --iterations 3

# Results in: results/iterative_cycles/
```

### Architecture

```
┌─────────────────────────────────────────────────────┐
│  PLANNING LAYER: PlannerAgent                       │
│  • Task parsing → complexity + category             │
│  • Subtask decomposition + dependency ordering      │
└──────────────┬──────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────┐
│  EXECUTION LAYER: ManagerAgent + Workers            │
│  • PerceptionWorker → OSM / remote sensing / traj   │
│  • AnalystWorker → spatial reasoning + task logic   │
│  • CartographerWorker → SVG / GeoJSON visualization │
│  • ReporterWorker → narrative + aggregation         │
└──────────────┬──────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────┐
│  REVIEW LAYER: SpatialReviewer + HumanCheckpoint    │
│  • Spatial consistency validation                   │
│  • Human-in-the-loop decision gates                 │
└─────────────────────────────────────────────────────┘
```

---

## 中文

### 项目简介

UrbanAgent 是一个基于大语言模型（LLM）驱动的城市空间分析多智能体框架，支持地理问答、步行可达性评估、出行预测、路径规划等城市分析任务。采用三层多智能体架构（规划 → 执行/工人 → 审查），结合双空间认知（拓扑 + 矢量），并内置 UrbanWorkflowBench 评测套件。

### 核心特性

- **三层多智能体架构**：PlannerAgent（任务分解）→ ManagerAgent + Workers（协同执行，信息隔离）→ SpatialReviewer（质量审查）
- **多源感知**：OpenStreetMap、遥感影像、街景分类、轨迹数据
- **双空间认知**：拓扑（图）+ 矢量（坐标）融合的空间推理
- **多模型支持**：Qwen、OpenAI、DeepSeek、Kimi 等 OpenAI 兼容端点
- **UrbanWorkflowBench**：内置 8 类城市任务评测基准
- **多种接入方式**：CLI / Python API / MCP Server

### 快速开始

```bash
# 1. 克隆仓库
git clone https://github.com/xuanniao57/urbanagent.git
cd urbanagent

# 2. 创建环境
conda create -n urban-mobility python=3.10 -y
conda activate urban-mobility

# 3. 安装依赖
pip install -e .
# 或者: pip install -r requirements_combined.txt

# 4. 配置密钥
cp .env.example .env
# 编辑 .env → 至少设置一个 LLM 密钥（如 QWEN_API_KEY）

# 5. 运行测试
pytest tests/ -q

# 6. 试用 CLI
python -m urban_agent run --task-type geoqa --question "分析同济大学周边步行可达性"
```

### 使用方式

#### 命令行

```bash
# 端到端分析
python -m urban_agent run --task-type geoqa --question "分析同济大学周边步行可达性"

# 分步执行
python -m urban_agent perceive --data-type osm --bbox "121.4,31.2,121.5,31.3"
python -m urban_agent cognize --input perception_result.json
python -m urban_agent reason --task-type geoqa --input cognition_result.json --question "..."
python -m urban_agent visualize --input analysis_result.json --format svg
```

#### Python API

```python
from urban_agent.agents import MultiAgentOrchestrator

orchestrator = MultiAgentOrchestrator()
result = await orchestrator.run(
    task="分析同济大学周边步行可达性",
    task_type="geoqa"
)
```

### 大模型配置

编辑 `.env` 切换服务商（详见 `.env.example`）：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_PROVIDER` | `qwen` | `qwen` / `openai` / `deepseek` / `kimi` |
| `QWEN_API_KEY` | — | 通义千问 DashScope 密钥 |
| `OPENAI_API_KEY` | — | OpenAI 密钥 |
| `Deepseek_API_KEY` | — | DeepSeek 密钥 |
| `KIMI_API_KEY` | — | 月之暗面 Moonshot 密钥 |

### UrbanWorkflowBench（评测基准）

UrbanWorkflowBench 是 UrbanAgent 的内置评测协议，用于系统评估城市分析智能体的工作流能力。

#### 三个评测维度

| 测试套件 | 协议类型 | 评测内容 |
|---------|---------|---------|
| `external_citydata_subset` | `agent_task` | 标准城市任务（地理问答、出行预测、导航、探索） |
| `dual_space_design` | `dual_space_probe` | 双空间认知能力（包含、对齐、分离、邻接、连通） |
| `memory_continuity` | `memory_probe` | 跨任务上下文记忆迁移 |

#### 运行评测

```bash
# 第 1 步：构建评测清单
python scripts/benchmarks/build_urbanworkflowbench_v1.py

# 第 2 步：无 LLM 基线运行（验证格式）
python scripts/benchmarks/run_urbanworkflowbench_v1.py --provider none

# 第 3 步：使用 LLM 运行
python scripts/benchmarks/run_urbanworkflowbench_v1.py --provider qwen
```

#### CityData 数据准备

评测依赖 CityBench 数据集（因体积未包含在仓库中）：

```bash
# 下载 CityBench 数据，放置到: third_party/CityBench-main/citydata/
```

详见 `docs/CITYBENCH_RUNBOOK.md`。

#### 迭代测试

```bash
# 预览测试计划
python run_iterative_agent_cycle.py --dry-run --iterations 3

# 执行迭代测试
python run_iterative_agent_cycle.py --iterations 3

# 结果保存在: results/iterative_cycles/
```

### License

MIT
