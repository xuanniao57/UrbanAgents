# CubeGraph-Inspired Experimental Retriever

更新时间：2026-04-15

## 1. 当前结论

CubeGraph 适合迁移到 UrbanAgent 的位置，不是一个单独的 attention 模块，而是记忆检索层。

原因很直接：

1. `urban_agent/**` 里没有独立实现的时空 attention 模块。
2. UrbanAgent 已经有较完整的 memory stack，包括 temporal context、ACT-R activation、reflection、pattern detection。
3. CubeGraph 的核心优势本来就更偏向“空间过滤 + 分层索引 + 邻接扩展检索”，与 MemoryModule 的 long-term retrieval 更对齐。

因此本次落地策略是：

1. 不替换现有 memory。
2. 新增一个实验性、可插拔的 retrieval backend。
3. 默认关闭，不影响现有基线与论文主叙事。

---

## 2. 已落地实现

代码位置：

1. `urban_agent/core/cube_retriever.py`
2. `urban_agent/core/memory.py`
3. `tests/test_memory_module.py`

本次实现迁移了 CubeGraph 中最适合 UrbanAgent 的 5 个结构性思想。

### 2.1 分层空间划分

通过 `layer_steps` 定义多层 spatial cell 尺度，例如：

1. coarse layer
2. medium layer
3. fine layer

对应 CubeGraph 的 hierarchical cube partitioning，但这里不构建 ANN 索引，只做 memory retrieval 的层次化候选筛选。

### 2.2 过滤尺度驱动的层选择

查询包含 bbox 时，根据 bbox 尺度选择主层，再同时检索相邻层。

这对应 CubeGraph 的 adaptive layer selection，目标是：

1. 大范围查询优先粗层
2. 小范围查询优先细层
3. 减少“只在一个尺度上搜”的偏置

### 2.3 邻接单元扩展

查询不会只命中中心 cell，还会按 `max_neighbors` 扩展到邻接 cell。

这对应 CubeGraph 的 cross-cube / adjacent cube traversal，适合 UrbanAgent 的 place-based recall：

1. 同一区域
2. 邻近街区
3. 相邻路口

都可以进入候选集。

### 2.4 与任务和时间的联合重排

最终排序不是纯空间命中，而是联合考虑：

1. spatial hit
2. task type match
3. temporal context match

这保持了 UrbanAgent 原有 memory 设计的时序语义，不会把 CubeGraph 误用成纯几何索引。

### 2.5 可插拔开关

MemoryModule 新增：

1. `enable_cube_retrieval`
2. `cube_retrieval_config`

默认关闭。只有显式开启才会：

1. 在写入 long-term memory 时建立 cube index
2. 在检索时返回 `relevant_long_term["cube_rag"]`

---

## 3. 没有迁移的部分

本次刻意没有迁移以下内容。

### 3.1 HNSW / ANN 本体

原因：UrbanAgent 当前 memory 不是高维向量 ANN 数据库，而是结构化经验记忆。直接照搬 HNSW 会把系统复杂度抬高，但不一定立刻带来收益。

### 3.2 SIMD / C++ 高性能实现

原因：当前目标是验证“检索结构是否有益”，不是做极致性能实现。

### 3.3 Polygon / Radius / Composite filter 完整支持

原因：UrbanAgent 当前最常见的空间约束还是 bbox、location token、局部 bounds。先把最常用入口验证清楚，再决定是否扩展到 polygon/radius。

### 3.4 独立向量索引文件

原因：UrbanAgent 当前 memory 还没有独立的 retrieval store / embedding store。现阶段更适合先做内嵌实验模块。

---

## 4. 使用方式

示例配置：

```python
memory = MemoryModule(
    config={
        "cube_retrieval_config": {
            "layer_steps": [1.0, 0.1, 0.01],
            "max_neighbors": 1,
            "max_results": 5,
        }
    },
    enable_cube_retrieval=True,
)
```

检索结果新增字段：

1. `relevant_long_term["cube_rag"]`
2. 每个命中项带 `cube_match`

`cube_match` 记录：

1. score
2. source
3. layer
4. distance

---

## 5. 当前验证状态

已完成：

1. 新模块接入 MemoryModule
2. 默认关闭，不影响原始路径
3. 新增 bbox 检索单测
4. 现有 `tests/test_memory_module.py` 全部通过

当前新增测试证明了一件关键事情：

在 query 只有 bbox、没有显式 location token 的情况下，experimental retriever 仍然能把近邻区域的历史记忆找出来。

这正是当前 UrbanAgent 原始 token-overlap 路径不够强的地方。

---

## 6. 建议实验设计

最小验证集建议如下。

### E1. On / Off 主消融

1. baseline memory
2. baseline memory + cube retrieval

目标：看 place-based recall 和 workflow success 是否提升。

### E2. 层尺度敏感性

1. coarse only
2. coarse + medium
3. coarse + medium + fine

目标：找出对城市尺度任务最稳定的 layer 组合。

### E3. 邻接扩展敏感性

1. `max_neighbors = 0`
2. `max_neighbors = 1`
3. `max_neighbors = 2`

目标：看 recall gain 与 noise 的拐点。

### E4. 任务类型收益拆解

建议至少单独报告：

1. outdoor navigation
2. traffic signal
3. urban exploration
4. mobility prediction

这些任务最可能从 spatial recall 中获益。

### E5. 误检分析

重点看：

1. 同城不同街区误召回
2. 邻接过宽造成的噪声
3. 时间匹配 bonus 是否压不住空间噪声

---

## 7. 下一步工程建议

若 E1-E5 显示有效，下一阶段建议按顺序推进：

1. 给 query 增加 polygon / radius filter 支持
2. 给 memory experience 增加更标准的 geometry normalization
3. 将 cube retrieval 与现有 ACT-R score 做统一 rerank
4. 在 benchmark 脚本中增加 `cube_retrieval` 开关与日志记录
5. 如果 recall 明显提升，再考虑更重的向量化 index

在这之前，不建议把该模块写进论文主贡献，只保留为 experimental track。