# UrbanAgent Benchmark Standard Proposal

更新时间：2026-03-19

## 1. 为什么不能直接沿用 CityBench

CityBench 很有价值，但它更接近“城市任务上的通用 LLM/VLM 能力测试”，而不是“城市分析 agent 框架能力测试”。对于 UrbanAgent，这里至少有四个不完全对齐的地方。

1. CityBench 的 8 个任务覆盖广，但与“城市分析工作流”并不完全同构。
   - 例如 `population`, `objects`, `geoloc` 更像感知或识别任务。
   - 它们能够测试模型能力，但不一定能体现 UrbanAgent 的 workflow orchestration、dual-space cognition、memory continuity。

2. CityBench 更强调任务结果，而不充分区分“为什么成功”。
   - UrbanAgent 的核心贡献不是只答对，而是：
   - 是否构建了正确的空间表示
   - 是否进行了合理的工具调用
   - 是否在多轮分析中复用了历史上下文

3. CityBench 对“空间分析流程”覆盖不足。
   - UrbanAgent 不是单纯 urban QA agent。
   - 它更接近 spatial workflow agent，需要评估：
   - 任务解析
   - 数据选择
   - 中间空间结构构建
   - 多步决策与报告输出

4. CityBench 不足以验证 UrbanAgent 的设计主张。
   - UrbanAgent 想证明的是三件事：
   - 面向异构工具的 orchestration
   - dual-space spatial cognition
   - place-based memory
   - 因此需要补一套“设计敏感”的 benchmark。

结论：CityBench 应该保留，但角色应从“唯一主 benchmark”改为“外部对齐 benchmark”。UrbanAgent 还需要一套自己的 benchmark standard。

---

## 2. 应该参考哪些已有工作

建议不是照搬某一篇，而是吸收多篇 benchmark 的长处。

### 2.1 CityBench 的价值

可借鉴点：

1. 城市任务覆盖面广。
2. 有现成的任务口径，适合做 external comparability。
3. 可以继续作为 outcome-level baseline。

不宜直接继承的点：

1. 任务集合与 UrbanAgent 的真实能力边界不完全一致。
2. 对 workflow-level 中间状态评估不足。

### 2.2 USTBench 的价值

可借鉴点：

1. 强调时空推理，而不是只看最终答案。
2. 更适合拆解“城市 agent 到底卡在什么类型的 reasoning”。
3. 对 UrbanAgent 的 dual-space cognition 和 memory continuity 很重要。

适合吸收为：

1. 空间关系推理子集
2. 时序上下文理解子集
3. 路径、邻接、拓扑、地标等结构化任务

### 2.3 GeoAnalystBench 的价值

可借鉴点：

1. 更强调 spatial analysis workflow 和 code/tool use。
2. 更适合 UrbanAgent 这种“不是只答题，而是会调工具”的系统。
3. 可以帮助我们把 benchmark 从 task QA 转向 analysis workflow。

适合吸收为：

1. 工具调用正确率
2. 工作流完整率
3. 中间数据结构有效性

### 2.4 GeoBenchX 的价值

可借鉴点：

1. 关注多步 geospatial task agent solving。
2. 能更好体现 planning-execution-review 的多步协作。

适合吸收为：

1. 多步任务成功率
2. 多步稳定性
3. 错误恢复能力

---

## 3. UrbanAgent 的 benchmark 应该测什么

建议把 UrbanAgent 的 benchmark 目标定义为：

> 评估一个城市分析 agent 是否能在真实城市分析工作流中，完成任务解析、空间表示构建、推理决策、工具调用、记忆复用与结果输出。

这意味着 benchmark 不应只是一组题，而应该是一个分层协议。

建议采用四层评测结构。

### Layer A. Design-sensitive core evaluation

这层直接验证 UrbanAgent 的架构主张。

#### A1. Dual-space cognition

测试目标：

1. 是否能正确构建拓扑关系。
2. 是否能正确构建向量关系。
3. 是否能在 topology 和 vector 之间建立可用映射。

建议任务：

1. adjacency / connectivity / containment / alignment / barrier separation
2. route detour reasoning
3. landmark-grounded path interpretation

建议指标：

1. relation accuracy
2. mapping completeness
3. structure consistency score

建议消融：

1. dual-space
2. vector-only
3. topology-only

#### A2. Memory continuity

测试目标：

1. 是否能在重复任务中复用历史结果。
2. 是否能按地点、时间、主题检索历史经验。
3. 是否能把用户修正转化为后续默认行为。

建议任务：

1. repeated navigation in same area
2. repeated exploration with prior preferences
3. mobility prediction with historical cases
4. user override replay

建议指标：

1. with-memory vs without-memory accuracy
2. retrieval precision
3. cross-session transfer gain
4. preference persistence rate

#### A3. Tool orchestration

测试目标：

1. 是否能调用对的工具。
2. 是否能按合理顺序调用工具。
3. 是否能处理调用失败并恢复。

建议指标：

1. tool selection accuracy
2. workflow completion rate
3. tool-call validity rate
4. recovery success rate

### Layer B. Urban workflow task evaluation

这层是 UrbanAgent 自己的主 benchmark，应该比 CityBench 更贴近城市分析 workflow。

建议分成 5 类任务，而不是直接沿用 CityBench 8 类。

#### B1. Spatial understanding

关注：

1. 城市空间关系理解
2. morphology / topology / accessibility 解释

示例：

1. identify barriers and permeable links
2. classify street-network pattern
3. locate activity centers and weak connections

#### B2. Analysis workflow execution

关注：

1. 从 query 到 structured task
2. 从 task 到 data selection
3. 从 data 到 intermediate representation
4. 从 representation 到 result

示例：

1. walkability assessment workflow
2. connectivity diagnosis workflow
3. open-space deficit analysis workflow

#### B3. Intervention and decision support

关注：

1. 是否能提出合理 intervention proposal
2. 是否能解释 proposal 与空间结构的关系

示例：

1. add pedestrian connection
2. identify public-space deficit and propose insertion
3. prioritize candidate interventions

#### B4. Recurrent place-based analysis

关注：

1. 同一地点跨任务连续分析
2. 记忆驱动的分析一致性与改进

示例：

1. neighborhood revisit benchmark
2. multi-round planning refinement

#### B5. Human-in-the-loop collaboration

关注：

1. checkpoint 是否可解释
2. 用户修正能否被系统吸收
3. guided / supervisory / autonomous 三种模式是否可比较

示例：

1. DP-3 barrier correction
2. DP-4 intervention rejection and re-proposal
3. DP-5 parameter override and rerun

### Layer C. External comparability evaluation

这层保留已有 benchmark，保证论文可比性。

建议保留：

1. CityBench
2. USTBench 中与时空推理直接相关的子集
3. GeoAnalystBench 中与 spatial workflow/code/tool use 相关的子集

原则：

1. 外部 benchmark 只负责“对齐别人”。
2. 自定义 benchmark 才负责“证明 UrbanAgent 自己的设计”。

### Layer D. Case-based ecological evaluation

这层不是 leaderboard，而是软件论文需要的生态有效性。

建议保留 2 到 3 个案例：

1. 真实 OSM neighborhood analysis
2. 带人机交互 checkpoint 的规划支持案例
3. 外部 connector 案例，例如 Rhino / Grasshopper

目的：

1. 证明系统不是只会 benchmark。
2. 证明它在真实分析工作流中可用。

---

## 4. 建议的指标体系

建议不要只保留单一 accuracy，而是采用 4 维指标体系。

### 4.1 Representation

衡量中间空间表示是否正确。

建议指标：

1. topology relation accuracy
2. vector mapping completeness
3. spatial consistency score
4. landmark-path consistency

### 4.2 Workflow

衡量 agent 是否完成了分析流程。

建议指标：

1. task grounding correctness
2. data-source selection accuracy
3. workflow completion rate
4. tool-call validity rate

### 4.3 Decision

衡量决策质量。

建议指标：

1. proposal relevance
2. intervention ranking quality
3. route/action correctness
4. stability across reruns

### 4.4 Continuity

衡量记忆和人机协作是否有效。

建议指标：

1. with-memory gain
2. cross-session transfer accuracy
3. override retention rate
4. adaptation latency

---

## 5. 建议的数据组织方式

建议不要只有一个题库，而是采用三类数据资产。

### 5.1 Synthetic diagnostic set

作用：

1. 用来做设计敏感消融。
2. 便于精确控制 ground truth。

适合：

1. dual-space relations
2. memory transfer
3. tool-call order

### 5.2 CityData-aligned benchmark set

作用：

1. 复用 CityBench/USTBench 的部分资产。
2. 保证可比性。

### 5.3 Real-place workflow set

作用：

1. 测 UrbanAgent 真正关心的城市分析 workflow。
2. 强化软件论文的生态有效性。

建议每个案例都保存：

1. input task
2. selected data
3. intermediate topology/vector state
4. memory retrieval trace
5. final output
6. human override log

---

## 6. 建议的协议设计

建议最终采用“双协议”而不是单协议。

### Protocol 1. External benchmark protocol

用于和已有论文对齐。

包括：

1. CityBench 全量或子集
2. USTBench 子集
3. GeoAnalystBench 子集

报告方式：

1. outcome metrics 主表
2. 不过度声称这就是 UrbanAgent 全部能力

### Protocol 2. UrbanAgent-native protocol

用于证明 UrbanAgent 自己的设计。

包括：

1. design ablation
2. workflow benchmark
3. recurrent memory benchmark
4. HITL benchmark

报告方式：

1. architecture-sensitive ablation table
2. workflow success table
3. memory gain table
4. case diagnostics

---

## 7. 一套可执行的最小版本

如果现在就要做，不建议一口气做很大。建议先做一个最小可发表版本。

### Phase 1. 立即可做

1. 保留 CityBench quick benchmark 作为 external baseline。
2. 扩展当前 design ablation：
   - dual-space
   - memory
   - tool orchestration
3. 新增一个 Urban workflow subset：
   - walkability diagnosis
   - navigation with barrier correction
   - intervention proposal selection

### Phase 2. 下一步增强

1. 引入 USTBench 风格的时空推理题组。
2. 引入 GeoAnalystBench 风格的 workflow/tool 题组。
3. 加入 guided/supervisory/autonomous 三模式对比。

### Phase 3. 完整版 benchmark

形成一套正式命名的 UrbanAgent benchmark，例如：

1. UrbanAgentBench
2. UrbanWorkflowBench
3. UrbanSpatialAgentBench

其中我更建议：

UrbanWorkflowBench

因为它最能体现和 CityBench 的差异：

1. CityBench 偏城市任务能力。
2. UrbanWorkflowBench 偏城市分析工作流能力。

---

## 8. 对论文写作的建议表述

建议论文里不要写成“我们重新发明了一个 benchmark 来替代 CityBench”，而应写成：

> We retain CityBench for external comparability, but complement it with an UrbanAgent-native evaluation protocol designed to assess workflow orchestration, dual-space spatial representation, and place-based analytical continuity, which are not fully captured by existing urban-task benchmarks.

对应中文意思是：

1. 保留 CityBench，保证可比性。
2. 但新增一套 UrbanAgent-native protocol。
3. 因为现有 benchmark 没有充分测到 workflow、dual-space、memory 这三类能力。

---

## 9. 当前建议结论

可以，而且应该这样做。

更具体地说：

1. 不要放弃 CityBench。
2. 不要让 CityBench 成为唯一 benchmark。
3. 参考 USTBench、CityBench、GeoAnalystBench、GeoBenchX，构建一套 UrbanAgent-native benchmark standard。
4. 这套标准应当是：
   - 设计敏感
   - workflow 导向
   - 可与外部 benchmark 对齐
   - 能测中间状态而非只测最终答案

如果后续继续推进，我建议下一步直接做两件事：

1. 把这份标准收敛成正式的 benchmark schema。
2. 按这个 schema 开始整理一个最小 UrbanWorkflowBench v0.1。