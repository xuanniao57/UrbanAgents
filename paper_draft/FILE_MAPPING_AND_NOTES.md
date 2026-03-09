# UrbanAgent 论文 — 文件映射与框架调整建议

> 配套文档：追踪论文各章节与代码文件的对应关系，并记录框架调整建议

---

## 一、论文章节 → 代码文件映射

| 论文章节 | 对应代码文件 | 状态 | 备注 |
|---|---|---|---|
| §3.2 Multi-Source Perception | `urban_agent/perception/osm_processor.py` | ✅ 完整 | OSM数据获取与解析 |
| | `urban_agent/perception/remote_sensing.py` | ✅ 完整 | 遥感影像处理(VLM) |
| | `urban_agent/perception/street_view.py` | ✅ 完整 | 街景六维感知 |
| | `urban_agent/core/perception.py` | ✅ 完整 | 7种数据路由 |
| §3.3 Dual-Space Cognition | `urban_agent/cognition.py` (585行) | ✅ 核心 | 拓扑图+矢量映射 |
| §3.4 Reasoning & Decision | `urban_agent/core/reasoning.py` (464行) | ✅ 完整 | 8种推理策略 |
| | `urban_agent/decision.py` (521行) | ✅ 完整 | 干预生成+5种测量 |
| | `urban_agent/core/action.py` | ⚠️ 需增强 | 大多action仅格式化 |
| §3.5 Memory Module | `urban_agent/core/memory.py` | ✅ 完整 | 三级记忆系统 |
| §3.6 MCP Tool Interface | `urban_agent/mcp_tools.py` | ✅ 完整 | 7个注册工具 |
| §3.7 Visualization | `urban_agent/visualization.py` | ✅ 完整 | SVG+GeoJSON |
| §4.2 LLM Backends | `urban_agent/llm/qwen_client.py` | ✅ | 文本+视觉 |
| | `urban_agent/llm/deepseek_client.py` | ✅ | 文本(chat+reasoner) |
| | `urban_agent/llm/kimi_client.py` | ✅ | 文本+视觉 |
| §4.3 Data Integration | `urban_agent/tools/geo_tools.py` | ✅ | CityBenchDataLoader |
| §6 Benchmark | `urban_agent/evaluation/citybench_evaluator_v2.py` | ✅ | 五维评估器 |
| | `results/ALL_MODELS_COMPARISON_SUMMARY.md` | ✅ | 完整结果 |

---

## 二、当前架构问题与论文叙事的调和

### 问题1：双主干Agent并存

**现状**：
- `urban_agent/core.py` — 旧版同步Agent (SVG/空间设计导向)
- `urban_agent/core/agent.py` — 新版异步Agent (CityBench导向)

**论文叙事方案**：
论文中统一表述为**一个Agent**，具有两种运行模式：
1. **分析模式** (Analytical Mode)：对应 `core.py` 的 Perception→Cognition→Decision→Visualization 流程，用于开放式空间分析（Case Study 1-2）
2. **任务模式** (Task Mode)：对应 `core/agent.py` 的 Perceive→Memory→Reason→Act 流程，用于标准化基准测试（Section 6）

**代码建议**：不需要真的合并代码，但可以在 `__init__.py` 中提供统一入口：
```python
class UrbanAgent:
    def analyze(self, location, task, radius):  # 分析模式
        ...
    async def execute_task(self, task, task_type, city_data):  # 任务模式
        ...
```

### 问题2：MCP工具层与Action工具层分离

**现状**：
- `mcp_tools.py` 注册7个MCP工具（OSM获取、连通性分析等）
- `core/action.py` 注册7个内置工具（geocode、距离计算等）

**论文叙事方案**：
统一表述为 MCP Tool Layer，包含两类工具：
1. **空间分析工具**（对应 `mcp_tools.py`）：面向城市空间计算
2. **基础地理工具**（对应 `core/action.py`）：面向数据查询和基础计算

论文表格中已合并呈现。

### 问题3：DeGIM 框架的处理

**决定**：DeGIM 是独立工作，不纳入本论文主体。若需要，可在 Discussion 中简要提及作为"多Agent城市设计"的扩展方向。

---

## 三、论文核心narrative（故事线）

### 主线叙事

> 城市数据科学需要一个**开源的LLM编排框架**，将分散的地理空间工具整合为连贯的分析工作流。
> UrbanAgent通过**双空间认知模型**（拓扑+矢量）赋予LLM对城市形态的结构化理解，
> 并通过**MCP协议**标准化工具调用，实现了从原始数据到空间分析报告的端到端自动化。

### 投稿卖点对齐CEUS特刊

| CEUS特刊要求 | UrbanAgent对应 |
|---|---|
| Open-source software | ✅ Python开源框架，pip install |
| Urban data science | ✅ 城市空间分析（步行性、连通性、密度） |
| Geospatial perspective | ✅ OSM + 拓扑图 + SVG坐标映射 |
| Reproducible research | ✅ Jupyter notebooks + CityBench基准 |
| Demo on urban research | ✅ 3个案例研究（田子坊） |

### 差异化定位

UrbanAgent ≠ 又一个LLM应用。UrbanAgent = **城市科学的LangChain/AutoGIS**

- vs OSMnx：OSMnx是网络分析工具，UrbanAgent是编排框架
- vs CityGPT/UrbanGPT：它们是特定任务的LLM，UrbanAgent是通用框架
- vs GeoGPT：GeoGPT缺少空间结构推理（拓扑图），UrbanAgent有双空间认知

---

## 四、待完善事项（论文提交前）

### 必须完成
- [ ] 运行3个Case Study并截取SVG/GeoJSON可视化结果图
- [ ] 绘制框架架构图（Fig.1）的正式版本（建议用draw.io/Mermaid）
- [ ] 完善实验数据表格（Table 2的精确数字需要从结果文件中提取）
- [ ] 补充分任务的Agent增强分析图（Fig.2）
- [ ] 确认References格式符合CEUS要求

### 建议完善
- [ ] 在 `__init__.py` 中添加统一 `UrbanAgent` 入口类
- [ ] 为 `mcp_tools.py` 补充 `generate_measurement_report` 工具文档
- [ ] 添加 `pip install urban-agent` 的 `setup.py` / `pyproject.toml`
- [ ] 创建 tutorial notebooks（至少3个，对应3个case study）
- [ ] 补充 README 中的 Quick Start 章节

---

## 五、关键文件清单（与论文直接相关）

### 核心框架代码
```
urban_agent/core.py                    → 主Agent编排器（分析模式）
urban_agent/cognition.py               → 双空间认知（585行，论文核心贡献）
urban_agent/decision.py                → 空间决策引擎（521行）
urban_agent/visualization.py           → SVG/GeoJSON可视化
urban_agent/mcp_tools.py               → MCP工具注册表
urban_agent/core/agent.py              → Agent执行引擎（任务模式）
urban_agent/core/perception.py         → 多源感知路由
urban_agent/core/reasoning.py          → 8种推理策略
urban_agent/core/action.py             → 行动执行+工具调用
urban_agent/core/memory.py             → 三级记忆系统
```

### 感知子模块
```
urban_agent/perception/osm_processor.py    → OSM数据处理
urban_agent/perception/remote_sensing.py   → 遥感影像处理
urban_agent/perception/street_view.py      → 街景分析
```

### 工具和数据
```
urban_agent/tools/geo_tools.py             → 地理空间工具集
urban_agent/llm/qwen_client.py             → Qwen LLM客户端
urban_agent/llm/deepseek_client.py         → DeepSeek LLM客户端
urban_agent/llm/kimi_client.py             → Kimi LLM客户端
```

### 评测
```
urban_agent/evaluation/citybench_evaluator_v2.py → 五维评估器
results/ALL_MODELS_COMPARISON_SUMMARY.md         → 全量对比结果
```

### 文档
```
docs/LITERATURE_REVIEW.md               → 文献综述（41篇）
docs/CITYBENCH_EMBODIED_METRICS.md      → 评测指标设计
docs/AGENT_SYSTEM_DESIGN.md             → 系统设计文档（1290行）
```
