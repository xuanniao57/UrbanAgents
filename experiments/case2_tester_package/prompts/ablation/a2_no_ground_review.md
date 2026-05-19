你正在接受一个 Urban-Hermes CLI Case2 消融实验。
这是 A2：w/o Grounding and Review，用于观察缺少输入 grounding 和城市审查时，同样的街景感知城市分析任务会出现什么风险。

请处理同一个任务：
Case2 = 一个街景感知相关的城市分析任务。
用户想判断街景感知指标是否可以和某类城市活力、步行体验或公共空间质量指标放在同一空间单元上分析，并探索它们之间是否存在非线性关系或空间异质性。

数据根目录：D:/UrbanAgents_Case2_Data
输出目录：D:/UrbanAgents_Case2_Output/ablation_a2_no_ground_review

消融约束：
- 不要调用 urban_ground_task
- 不要调用 urban_review
- 不要生成正式 evidence manifest
- 你可以使用其他可用工具读取文件、执行轻量 GIS/Python 或生成产物

请在这些约束下尽量完成：读取可用数据；构建街景感知、客观建成环境和可用 Y 变量之间的指标关系；生成能生成的表格、图层或报告；最后诚实说明因为缺少 grounding/review，哪些空间、时间、人群、治理证据没有被正式检查。

最终用中文输出，并清楚标注这是 A2 消融结果。
请特别记录是否出现了 unsupported claim、proxy 未标注、CRS/字段/时间窗口未检查、把街景感知或 POI 当成真实 Y、或模型结论过度外推。
