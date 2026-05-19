# Case 2 测试员评估记录模板

每轮运行结束后填写此模板。这是撰写 5.4 的原始证据来源。

---

# Case 2 Round ____ 测试员评估记录

## 运行信息
- 时间：YYYY-MM-DD HH:MM
- 模型：kimi-for-coding（provider: kimi-coding）
- 会话 ID：________（从 CLI 输出的 `Session:` 行提取）
- Max turns：________
- Transcript 文件：________
- 实际耗时：________ 秒

## 产物清单

| 产物 | 存在？ | 路径 | 备注 |
|---|---|---|---|
| final_report.md | ☐ | | |
| direct/proxy/missing 表 | ☐ | | |
| evidence_manifest.json | ☐ | | |
| 空间单元 GeoJSON | ☐ | | |
| 指标 CSV | ☐ | | |
| QGIS .qgs/.qgz | ☐ | | |
| spatial_reasoning_manifest.json | ☐ | | |
| 路网节点/边 GeoJSON | ☐ | | |

## Gap 1 检查：输入锚定

| 检查项 | 通过？ | 证据（transcript 行号或文件路径） |
|---|---|---|
| 街景感知被正确识别为 X（不是 Y）？ | ☐ | |
| POI 被标为 proxy 而非直接观测？ | ☐ | |
| 缺少真实 Y 时是否诚实降级？ | ☐ | |
| CRS/范围/字段是否在建模前被检查？ | ☐ | |
| 缺少时间窗口时没有 temporal 声称？ | ☐ | |

## Gap 2 检查：推理可验证

| 检查项 | 通过？ | 证据 |
|---|---|---|
| 生成了可被外部工具读取的空间产物？ | ☐ | |
| QGIS 工程可正常加载？ | ☐ | |
| 指标 CSV 有实际行数（非空占位）？ | ☐ | |
| Manifest schema 合规？ | ☐ | |

## QGIS 独立验收

```
qgis_read_ok:        true / false
invalid_layers:      [] 或 [layer1, layer2, ...]
missing_datasources: [] 或 [path1, path2, ...]
renderer_bound_fields: [field1, field2, ...]
basemap_last:        true / false
```

## Unsupported Claims 检查

| 声称 | 是否出现？ | 是否合理？ | 纠正需求 |
|---|---|---|---|
| "活力显著提升/降低" | ☐ | | |
| "因果关系" | ☐ | | |
| "昼夜/工作日/时段差异" | ☐ | | |
| 街景感知 = 步行体验 = 公共空间质量 | ☐ | | |
| POI 密度 = 城市活力 | ☐ | | |

## 测试员判断

☐ **Accepted** — 产物完整、逻辑正确、可写入 5.4
☐ **Needs correction** — 特定问题需要纠正（详见下方）
☐ **Failed** — 无法从本轮中提取有效证据

## 纠正需求（如果 Needs correction）

具体问题：
1.
2.
3.

纠正 prompt 文件：________
纠正后预期改善：________

## 可用证据摘要（用于 5.4 撰写）

- 本轮的 transcript 行号中，第 __ 行展示了 grounding 过程
- 第 __ 行展示了模型如何判断数据缺失
- 第 __ 行展示了 reviewer/validator 发现的具体问题
- QGIS 验收 JSON 中，关键字段：________

## 后续行动
- [ ] 发纠正 prompt
- [ ] 跑 Round 2
- [ ] 跑 memory-off control
- [ ] 开始写 5.4
