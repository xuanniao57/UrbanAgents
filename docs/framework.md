# Framework（实现导向版）

## 1. 系统边界

本项目分为两条系统链路：

1. **DeGIM 生成链路**：多智能体协商 → 空间表达 → 报告输出。
2. **CityBench 评测链路**：统一调度 → 8 任务执行 → 指标汇总。

两条链路共享同一仓库，但运行环境可分离（Windows/WSL2）。

## 2. DeGIM 核心架构

### 2.1 三层结构

- **L1 Cognitive**：多角色协商，输出 shared narrative 与 CD。
- **L2 Spatial**：文本约束转拓扑/矢量表达，输出空间布局与 CS。
- **L3 Imagery**：意象选择与风格一致性，输出 PD。

### 2.2 生成-检验闭环

每层遵循：
1) Generator 产出候选结果；
2) Inspector 做规则/语义检查；
3) 不通过则迭代修订；
4) 通过后向下游传递。

### 2.3 指标

- `CD`: 共识度
- `CS`: 空间一致性
- `PD`: 范式多样性
- `CLC`: 跨层一致性综合指标

## 3. CityBench 集成架构

### 3.1 调度层

- 入口：`run_citybench_benchmark.py`
- 能力：任务筛选、日志拆分、失败隔离、断点跳过、摘要输出

### 3.2 数据层

- 路径：`third_party/CityBench-main/citydata`
- 要求：完整 `citydata` 解压，且 CityBench 工作目录可读写 `results/`

### 3.3 模型与 API 层

- 通过 OpenAI-compatible 接口桥接 Qwen 系列模型
- 文本/视觉调用统一走环境变量注入

## 4. 运行策略（当前实践）

- **DeGIM**：优先 Windows（保持现有流程稳定）
- **CityBench 8 任务**：优先 WSL2（避免 Linux 依赖缺失）

## 5. 下一步架构演进

1. 对 CityBench 增加任务级重试与超时控制
2. 对 DeGIM 增加空间反馈二次协商环
3. 统一实验元数据（环境、模型、参数）到单一 manifest 文件