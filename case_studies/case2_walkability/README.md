# Case Study 2: 城市步行可达性评估

> 对应论文 Section 5.6 Case Study 2
> 待实现

## 研究背景

以巴黎 Le Marais 历史街区为例，执行完整的步行可达性评估工作流：
OSM 数据获取 → 拓扑图构建 → 路网连通性分析 → 设施可达性测量 → 密度计算 → SVG 叠加图 → QC 审查 → 报告生成。

重点检验 UrbanAgent 在以下 gap 上的表现：
- **Gap 1**：PlannerAgent 能否自动选择 OSM acquisition + network connectivity + accessibility 等 capabilities
- **Gap 2**：dual-space cognition 能否检测 canal/footbridge 等空间结构误判；Review Hub 能否产出 spatial 评分
- **Gap 3**：人工纠正（如 footbridge 重分类）后 FeedbackMemory 是否在后续 Le Marais 分析中复用

## 任务输入

（待定义 `task_input.json`）

## 运行列表

| 运行 ID | 配置 | 日期 | 状态 |
|---|---|---|---|
| — | — | — | 待实现 |
