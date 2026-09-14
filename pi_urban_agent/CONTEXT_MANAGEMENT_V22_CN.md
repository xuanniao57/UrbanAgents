# Urban Agent v2.2 上下文管理说明

## 1. 设计结论

Urban Agent 不再把“压缩后的自然语言摘要”当成长期研究记忆。对研究过程具有约束力的信息始终保存在 `research_state.json` 中。Pi 保留原生的时间顺序对话压缩；LLM 每轮只接收一个短书签，包含状态版本、活动节点、未完成审核动作、最新路线裁决、claim ceiling 和下一步动作。完整 Research Tree 不常驻上下文。

因此，模型仍然拥有研究自主权：它决定下一步处理哪个节点、调用什么工具、召回哪条分支；但它不能通过一次不准确的摘要改写已经记录的参数、证据或人类审核结论。

## 2. 什么时候触发压缩

沿用 Pi 的会话触发和事件机制：

```text
contextTokens > contextWindow - reserveTokens
```

`reserveTokens` 和 `keepRecentTokens` 不再使用 Pi 默认的固定 16k/20k，而是根据实际部署窗口生成：

- `reserveTokens = max(512, min(0.20 × window, maxOutputTokens))`
- `keepRecentTokens = max(512, min(12,000, 0.20 × window))`

例如 4k、8k、16k 窗口分别使用约 819、1,638、3,276 token 的保留区。模型名称和参数量不参与判断；API 模型、Qwen 9B、4B 都执行相同机制，只由服务器真正开放的上下文窗口决定预算。

## 3. 压缩具体怎样执行

触发 `session_before_compact` 后，扩展执行以下步骤：

1. 从磁盘重新读取权威 `research_state.json`，不读取上一次摘要作为科学事实来源。
2. 生成机器可读 recovery checkpoint，记录活动路径、人类裁决、Reviewer 约束、未解决问题和精确召回入口。
3. 写入 context manifest，记录状态版本、预算与触发原因。
4. 不替换 Pi 的自然语言摘要，让 Pi 继续保留近期对话连续性。
5. 下一轮只注入短书签；需要科学事实时再调用 `urban_recall`。

这不是对旧摘要再次摘要，因此不会形成 summary-of-summary 漂移。被省略的内容也没有删除，只是不进入当前工作窗口。

## 4. 模型如何“想起”被压缩内容

短书签向模型暴露稳定召回路径。模型可调用 `urban_recall`：

- 按 node / artifact / review / human decision 的稳定 ID；
- 按 branch ID 及其依赖深度；
- 按结构化范围或词项查询；
- 先用不超过 640 token 的 tree digest 找 ID，再用 branch evidence card 取精确参数、指标、审核和人类角色；
- 为召回结果设置 token 上限。

多 ID 的 `full` 请求会自动降为紧凑 evidence card，避免一次召回撑满小模型窗口。未指定 selector 的 branch/review/human-decision 召回默认定位活动节点。精确 ID 与依赖遍历仍是正确性路径。

## 5. 为什么不增加第二个“记忆 Agent”

近年的 MemGPT、A-MEM、Mem0、CAT、ACON 和 Adaptive Context Elasticizer 等工作分别探索了分层内存、图记忆、可调用压缩、学习式压缩策略和可逆弹性上下文。这些方法说明“原始历史外置、按任务恢复”优于不可逆截断。但在科研工作流中，参数、工件哈希和人类 gate 不能依赖概率式抽取或重写。

v2.2 因而将正确性关键路径压缩为三项通用工程操作：

```text
保存结构化状态 → 编译有限工作视图 → 精确召回缺失记录
```

它更接近 event-sourced application，而不是复杂的多记忆智能体。若 capsule 编译失败，源状态不变；若语义查询失败，精确 ID 仍可用；若小模型忘记召回，遗漏会出现在工具轨迹和 manifest 中，而不会静默改写科研记录。

## 6. 人类决议写入保护

`select_main`、`retain_sensitivity`、`defer` 和 `block` 每次只能作用于一个目标分支。若分支已有不同的人类裁决，新写入必须用 `supersedes_decision_id` 引用被替代记录；相同裁决不得重复写入。决议类型和理由冲突时拒绝写入，例如“保留为敏感性证据”不能记录为 `defer` 或 `select_main`，`approve_claim` 也不能替代路线角色变更。

## 7. 已完成验证

- TypeScript 类型检查、17 项单元测试和 smoke test 全部通过。
- 49 节点压力测试覆盖 4k、8k、16k、32k、131k 窗口。
- 4k/8k 使用 pointer capsule，16k/32k 使用 compact capsule，131k 使用 full capsule。
- 对没有进入 capsule 的节点能够通过 `urban_recall` 精确恢复。
- 连续两次编译从权威状态得到一致结果，未发生递归摘要。

2026-08-25 的冻结单次对照覆盖 Qwen3.5 0.8B、2B、4B 和 9B。混合机制在 4B、9B 上完成全部五个检查点，在 0.8B、2B 上仍未完成新的人类决议写回。结果说明外部 Tree 召回改善了中等模型的事实恢复和状态写入，但不能替代小模型本身的工具规划能力；详细结果见 `evaluation/module_ablation_20260825/results_hybrid_vs_pi_v1/EXPERIMENT_REPORT_CN.md`。

本机 Ollama 在低于 24 GiB 显存时默认只分配 4k 上下文。项目因此提供 `local_models/qwen35_9b_urban16k.Modelfile`，创建 `qwen3.5:9b-urban16k` 标签，使 Pi 声明的 16k 与实际服务窗口一致；测试必须用 `ollama ps` 核对 `CONTEXT` 和 GPU offload，而不能只相信模型卡的最大窗口。
