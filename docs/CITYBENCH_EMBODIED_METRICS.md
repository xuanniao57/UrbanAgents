# CityBench 任务三维指标表（Embodied/Simulation 视角）

更新时间：2026-02-26

本文档将 CityBench 的 8 个任务统一映射到 3 个评测维度：
1. 状态感知（State Perception）
2. 决策序列（Decision Sequence）
3. 任务结果（Task Outcome）

用于 DeGIM 的评测协议设计与论文方法节描述。

---

## 1) 任务类型分层

- **强 Embodied / Simulation**：`traffic`, `exploration`, `navigation`, `mobility`
- **弱 Embodied（偏静态推理）**：`geoqa`
- **感知型（近静态）**：`population`, `objects`, `geoloc`

说明：后 4 项通常不依赖长时动作链，更接近“单步或短链感知/问答”。

---

## 2) 三维指标总表

| 任务 | 任务性质 | 状态感知（建议指标） | 决策序列（建议指标） | 任务结果（CityBench主指标） |
|---|---|---|---|---|
| `traffic` | 强仿真控制 | 路口相位识别准确率、队列长度估计误差 | 动作合法率、冲突动作率、时序稳定性（phase switch consistency） | `Average_Queue_Length`（越低越好）, `Throughput`（越高越好） |
| `exploration` | 多步空间探索 | 当前位置与目标相对关系识别、可达性判断准确率 | 成功轨迹率、平均决策步数、无效动作率 | `Exploration_Success_Ratio`, `Exploration_Average_Steps` |
| `navigation` | 多步导航 | 邻接路段识别、方向感知准确率、地标-路径一致性 | 路径执行成功率、回退/震荡率、平均决策轮数 | `Navigation_Success_Ratio`, `Navigation_Average_Distance` |
| `mobility` | 时序出行预测 | 用户历史停留模式感知、时间上下文理解 | 多轮候选更新质量、Top-k 收敛稳定性 | `Acc@1`, `F1` |
| `geoqa` | 空间知识问答 | 空间关系识别准确率、地理常识命中率 | （弱）可用“多跳推理一致率”替代 | `GeoQA_Average_Accuracy` |
| `population` | 遥感回归 | 图像场景与人口密度相关特征感知 | （弱）一般无显式动作序列 | `RMSE`（越低越好）, `r2`（越高越好） |
| `objects` | 遥感识别 | 基础设施目标识别准确率 | （弱）一般无显式动作序列 | `Infrastructure_Accuracy` |
| `geoloc` | 街景定位 | 视觉地标感知、城市特征匹配 | （弱）可用候选城市重排稳定性 | `City_Accuracy`, `Acc@25km` |

---

## 3) 与 CityBench 原始口径对齐说明

当前项目中可直接对齐的任务结果指标来自 `config.py` 的 `METRICS_SELECTION`：
- `traffic`: `Average_Queue_Length`, `Throughput`
- `geoqa`: `GeoQA_Average_Accuracy`
- `mobility`: `Acc@1`, `F1`
- `exploration`: `Exploration_Success_Ratio`, `Exploration_Average_Steps`
- `population`: `RMSE`, `r2`
- `objects`: `Infrastructure_Accuracy`
- `geoloc`: `City_Accuracy`, `Acc@25km`
- `navigation`: `Navigation_Success_Ratio`, `Navigation_Average_Distance`

建议：论文中将“任务结果”作为主表，“状态感知/决策序列”作为扩展诊断指标表。

---

## 4) DeGIM 导向的最小评测子集（推荐）

若目标是验证“空间 + 要素流动（mobility）感知增强”，优先：
- 必跑：`mobility`, `geoqa`
- 可补：`navigation`（若 Mongo/路由链路打通）
- 感知补充：`geoloc`, `objects`

这样可覆盖：
- 空间语义理解（geoqa）
- 时序行为预测（mobility）
- 视觉地理感知（geoloc/objects）
- 多步决策（navigation，可选）

---

## 5) 报告模板（可直接引用）

> We evaluate DeGIM under a three-axis protocol: **state perception**, **decision sequence quality**, and **task outcome**. We report CityBench-native outcome metrics for comparability, while adding diagnostic indicators for perception and multi-step policy stability to measure framework-level gains beyond base model performance.
