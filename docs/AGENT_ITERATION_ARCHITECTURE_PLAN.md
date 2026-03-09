# Urban Agent / DeGIM 技术架构梳理与迭代改进计划

更新时间：2026-03-04

## 1. 当前核心链路（现状）

### 1.1 能力主链

- **感知（Perception）**：`urban_agent/core/perception.py`
  - 输入：遥感、街景、OSM、GeoJSON、轨迹、文本、混合数据
  - 输出：统一结构化感知结果
- **推理（Reasoning）**：`urban_agent/core/reasoning.py`
  - 输入：感知结果 + 记忆上下文 + 任务定义
  - 输出：任务特定推理链（8类CityBench任务）
- **行为决策（Action）**：`urban_agent/core/action.py`
  - 输入：推理结果
  - 输出：格式化行动结果 / 答案
- **记忆（Memory）**：`urban_agent/core/memory.py`
  - 负责上下文检索与更新（由 `urban_agent/core/agent.py` 编排）

### 1.2 DeGIM 生成链路

- 入口：`degim/engine/degim_engine.py`
- 流程：L1 认知协商 → L2 空间表达 → L3 意象选择 → 跨层对齐
- 指标：`CD` / `CS` / `PD` / `CLC`

### 1.3 CityBench 评测链路

- 综合评测脚本：`test_comprehensive_comparison.py`、`test_20_per_task_v3.py`、`test_100_per_task.py`
- 批跑入口：`run_comparison_test.py`、`run_citybench_benchmark.py`

---

## 2. 结构性问题（需优先收敛）

### P0：双主干 Agent 并存

当前存在两套 `UrbanAgent`：

1. `urban_agent/core.py`（同步分析流程：analyze/query）
2. `urban_agent/core/agent.py`（异步任务流程：execute_task）

风险：
- 能力重复与行为不一致
- 测试与评测脚本调用路径分裂
- 后续功能迭代（记忆、工具调用）无法保证同时升级

### P0：MCP 工具层与 Action 工具层分离

- `urban_agent/mcp_tools.py` 有一套 `register_tool/execute_tool`
- `urban_agent/core/action.py` 还有一套内部 `tools` + `call_tool`

风险：
- 工具定义重复
- 参数模式（schema）与运行时校验不一致
- 无统一可观测性（调用耗时、错误类型、重试次数）

### P1：通讯协议缺少统一“消息封套”

当前通讯方式主要是：
- 模块内函数直调（Python对象）
- LLM 通过 OpenAI-compatible HTTP（`AsyncOpenAI`）

缺失：
- `trace_id/span_id` 全链路追踪
- 标准错误码（超时、限流、schema不匹配、依赖缺失）
- 重试/回退策略的统一配置层

### P1：评测脚本“多入口高重复”

- 对比测试脚本数量多，任务定义和打分逻辑分散
- 结果口径易漂移（指标解释、字段命名、失败处理）

---

## 3. 迭代测试框架（建议标准化）

建议把每轮迭代固定为 4 个阶段：

1. **Build**：环境自检、依赖可用性、API配置检查
2. **Run**：执行 DeGIM + Urban Agent + CityBench 子集回归
3. **Measure**：采集成功率、耗时、错误分布、关键指标（CD/CS/PD/CLC）
4. **Improve**：基于失败模式自动生成改进建议并入 backlog

> 本仓库已新增脚本 `run_iterative_agent_cycle.py`，用于执行上述闭环并自动输出建议。

---

## 4. 改进路线图（按优先级）

### 阶段A（1~2周）：先收敛架构主线

- [ ] 仅保留一个主控制器（建议以 `core/agent.py` 为主）
- [ ] `urban_agent/core.py` 转为兼容层（wrapper）并标注 deprecate
- [ ] 统一任务输入输出 DTO（task/result/error envelope）

### 阶段B（2~3周）：统一 MCP 工具执行面

- [ ] 让 `ActionModule.call_tool` 委托到统一 Tool Runtime
- [ ] 引入参数校验（JSON Schema）+ 超时 + 重试 + 熔断
- [ ] 工具执行日志结构化（tool_name, latency_ms, error_type）

### 阶段C（2周）：统一通讯与可观测性

- [ ] 增加全链路 `trace_id`（任务级）
- [ ] 增加统一错误分类（NETWORK / AUTH / RATE_LIMIT / VALIDATION / TIMEOUT）
- [ ] 输出统一运行清单（模型、参数、环境、数据版本）

### 阶段D（持续）：评测体系收敛

- [ ] 合并重复测试脚本为“单入口 + 配置化任务集”
- [ ] 固化核心回归集（快速、标准、全量三档）
- [ ] 每轮自动生成对比报告（本轮 vs 基线）

---

## 5. 本周可执行动作（建议直接开工）

1. 用 `run_iterative_agent_cycle.py` 跑 3 轮快速循环，建立失败模式基线。
2. 将所有新增任务优先接入 `core/agent.py`，避免继续扩散到双主干。
3. 把工具调用统一打点（先记录调用成功率和耗时中位数）。
4. 每天结束生成 1 份 `results/iterative_cycles/*.md` 作为研发日报。

---

## 6. 架构改进评估指标（DoD）

当以下条件同时满足，可认为“核心技术栈收敛完成”：

- 单一 Agent 主链覆盖率 ≥ 90%（主要脚本与测试都走同一入口）
- MCP 工具调用失败率（非网络）下降 ≥ 50%
- 关键回归集连续 3 轮通过率 ≥ 95%
- 每轮测试均自动产出可追踪报告（JSON + Markdown）
