# Section 5.4 撰写指南：Case 2 街景感知的输入锚定与推理可验证性

## 5.4 在第五章中的位置

```
5.1  实验目标
5.2  实验设置
5.3  过程证据：Grounding quiz 与空间推理验证闭环
5.4  Case 2：街景感知分析的输入锚定与推理可验证性    ← 本文件
5.5  两层记忆与跨任务累积
5.6  十任务结果与诊断性消融
5.7  讨论与限制
```

## 5.4 的核心论证

**不要写**"模型答对了"。写"模型在什么条件下做出什么行为，系统通过什么机制让这些行为可检查、可纠正"。

Gap 1 → 输入锚定：模型能从一句话研究意图 + 数据画布中，区分什么是真实 Y、什么是感知 X、什么是 proxy、什么是 missing。如果没有 Y，它能诚实降级。

Gap 2 → 推理可验证：模型的中间推理不是藏在文字里，而是转化为外部可读的空间产物（GeoJSON、CSV、QGIS）。独立 validator 可以抓到产物中的问题，纠正指令可以定向修复。

**Gap 3 留给 5.5**，5.4 不展开记忆复用。

## 建议的段落结构

### 5.4.1 Case 2 的任务设定（~150 词）

- 一句话：Case 2 是一个更短、更自然的街景感知任务，用于检验 Urban-Hermes 在缺少详细研究设计 prompt 时的自主 grounding 行为
- 数据画布：有 AOI、有空间单元、有街景感知表、有 OSM 建成环境、**没有真实 Y 变量、没有时间窗口**
- Round 1→纠正→Round 2→memory-off control 的四轮设计
- 与 Case 1（详细 prompt + 完整数据）形成对比：Case 2 更"野生"

### 5.4.2 Gap 1：输入锚定的行为证据（~400 词）

**Round 1 的 grounding 行为：**
- 引用 transcript 中模型调用 urban_host_fs 盘点数据的行
- 引用 direct/proxy/missing 表的生成过程
- 如果模型在 Round 1 犯了错（如把街景感知当 Y、POI 当活力），**诚实写出这个错误**
- 这是 grounding 失败的证据——模型在没有明确指令时可能滑向 unsupported claim

**纠正的效果：**
- 测试者发纠正 prompt 后，模型在回复中如何改写指标表
- 引用 urban_record_feedback 的记录（transcript 行号）
- 纠正后的 report 中是否出现了"本次无法做 Y-X 建模""街景感知仅作为视觉环境代理"等降级表述

**Round 2 的 grounding 改善：**
- Round 2 中模型是否比 Round 1 更早地标注 proxy/missing
- 如果没有真实 Y，Round 2 是否诚实降级为"X 侧审计"
- Round 1 vs Round 2 的 direct/proxy/missing 表对比（可做小表）

**可用的图/表：**
- Table 5.X: Round 1 vs Round 2 的指标分类变化（例：Round 1 中 `lively=Y` → Round 2 中 `lively=proxy_X`）
- Figure 5.X: Grounding quiz 流程图（从"用户一句话"到"证据缺口表"到"纠正后降级声明"）

### 5.4.3 Gap 2：推理可验证的行为证据（~350 词）

**中间产物的证据：**
- 列出 Round 1 或 Round 2 实际生成的文件路径
- 不需要全列，选 3-5 个代表性文件
- 每个文件说明它验证了什么空间推理环节

**QGIS 验证闭环：**
- 引用独立 validator JSON 的关键字段
- 如果 validator 发现了问题（如 invalid layers）→ 展示 before/after
- 如果模型没有生成 QGIS → 诚实写"本 case 未完成 QGIS 工程，空间推理仅通过 GeoJSON/CSV 检查"
- 描述纠正指令 → 修复后的验收状态

**可用的图：**
- QGIS workspace overlay 截图（如果 QGIS 生成成功）
- validator JSON before/after 对比表
- Figure 5.X: 空间产物验证闭环（从"模型声称完成"到"validator 发现失败"到"定向纠正"到"复验通过"）

### 5.4.4 讨论（~150 词）

- Case 2 和 Case 1 形成互补：Case 1 有完整数据 + 详细 prompt，Case 2 更野生
- Gap 1 的核心发现：input grounding 不是一句 prompt 中写的提醒，而是需要系统机制（dataset card、证据清单、反使用规则）
- Gap 2 的核心发现：独立 validator 比模型自述更可靠；纠正闭环使"失败"变成有用的实验证据而不是实验噪声
- 限制：本 case 的数据画布不含真实 Y 变量，所以不能检验模型在"真能做 Y-X 分析"时的行为

## 写作风格要求

1. **一个段落开头，一句 evidence。** 每段第一句就告诉读者本段的证据是什么（transcript 行号、文件路径、JSON 字段），然后才展开解释。
2. **不省略失败。** 如果 Round 1 犯了错，那是 grounding 机制需要存在的直接证据——写进去，不要删。
3. **不写成 benchmark leaderboard。** 不写"准确率 XX%"。写"在条件 Y 下，系统行为是 Z"。
4. **中文术语一致。** 固定使用：
   - input grounding = 输入锚定（不写成"输入接地""输入对齐"）
   - reviewer gate = 审查门控
   - artifact validation = 产物验收
   - proxy evidence = 代理证据
   - unsupported claim = 无证据声称
5. **每张图/表都要在正文被引用。** 不能只放图不解释。

## 交付前自查

- [ ] 5.4 中的每个断言都能追溯到 transcript 或产物文件？
- [ ] Gap 1 和 Gap 2 都有 Round 1 + 纠正 + Round 2 的三阶段证据？
- [ ] 失败行为没有被掩盖或改写为成功？
- [ ] 所有图/表在正文中有解释？
- [ ] 没有跨到 Gap 3（记忆复用）的内容？（那留给 5.5）
- [ ] 讨论段诚实写了限制（没有真实 Y、数据画布规模小）？
