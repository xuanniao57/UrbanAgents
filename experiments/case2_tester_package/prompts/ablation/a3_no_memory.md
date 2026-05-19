你正在接受一个 Urban-Hermes CLI Case2 消融实验。
这是 A3：w/o Memory，用于观察缺少研究设计/方法/反馈记忆复用时，同样的街景感知城市分析任务会怎样。

请处理同一个任务：
Case2 = 一个街景感知相关的城市分析任务。
用户想判断街景感知指标是否可以和某类城市活力、步行体验或公共空间质量指标放在同一空间单元上分析，并探索它们之间是否存在非线性关系或空间异质性。

数据根目录：D:/UrbanAgents_Case2_Data
输出目录：D:/UrbanAgents_Case2_Output/ablation_a3_no_memory

消融约束：
- 不要调用 urban_research_memory
- 不要调用 urban_record_feedback、urban_memory_record 或任何 memory 写入工具
- 不要依赖历史经验、place memory、research-design memory、urban-method memory 或 tool-artifact memory
- 仍然可以调用 urban_ground_task、urban_host_fs、urban_host_python、urban_qgis_process、urban_review 等非记忆工具

请完成与 full run 相同的实质任务：
1. 输入 grounding
2. 数据盘点和 CRS/范围/字段检查
3. direct/proxy/missing 指标表
4. 至少尽量生成可检查中间产物
5. 轻量模型或诊断，若数据不足则说明
6. 调用 urban_review 检查最终城市结论

最终用中文输出，并清楚标注这是 A3 消融结果。
请特别说明：由于 memory 被拿掉，哪些本可复用的方法经验、artifact validation 规则或反馈纠正没有被召回/保存。
