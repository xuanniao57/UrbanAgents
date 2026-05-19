# Tester Role: Case 2 Realistic Dialogue Experiment

## 你是谁

你是合作者一方的测试员。Urban-Hermes 是受测系统。你的任务是：

本测试包中，`Urban Agent` 指当前的 `Urban-Hermes` 分支与运行时。回传记录、transcript 标注和第 5 章材料都按这个口径写。

1. 安装 Urban-Hermes 并验证环境可用
2. 导入 Case 2 文献研究记忆，并确认 `urban_research_memory` 能检索到
3. 准备数据画布（把数据文件放到约定目录）
4. 按对话剧本逐轮把短 prompt 喂给 Urban-Hermes
5. 保存每轮 transcript 和产物
6. 填写回传清单，连同实验素材传回

你**不是** Urban-Hermes。如果 Urban-Hermes 出错，记录错误，不要替它手写正确结果。

如果你用 OpenClaw、Claude Code 等本地 agent 代劳，让它先读本文件。

## 实验规则

1. 每次只喂本轮 prompt，不要把预期行为、检查清单也粘贴进去。
2. 每轮跑完再跑下一轮，优先用 `--resume SESSION_ID` 保持会话连续。
3. Transcript 用 `Out-File -Encoding utf8` 保存。
4. 不打印、不存储、不回传 API key。
5. 不伪造数据、GIS 工程/工作空间、活力结果、时间戳、模型结果、验证结果。
6. Urban-Hermes 过度声称时，先记录，再视情况自然纠正。
7. 如果外部 validator 失败，同时保留失败和纠正后的结果。
8. 回传原始产物和记录，不要只传一份总结。
9. GitHub clone 失败时不要反复重试；改用离线 zip 或本地目录路径。
10. QGIS 不是硬性要求。如果机器只有 ArcGIS Pro，优先运行 ArcGIS Pro backend preflight 和 ArcGIS validation。

## 数据画布

把数据文件放在 `D:/UrbanAgents_Case2_Data`。需要什么数据由合作者自行决定。Urban-Hermes 会自行盘点目录内的文件。约定：

- 数据根目录：`D:/UrbanAgents_Case2_Data`
- 输出根目录：`D:/UrbanAgents_Case2_Output/realistic_dialogue`

详见 `data_canvas/README.md`。

如果数据目录为空，先完成安装、Kimi 冒烟和 GIS backend preflight，并把“数据缺失，未进入真实分析”写入回传清单。

## GIS 后端规则

## 文献记忆规则

正式实验不是让 Urban-Hermes 从零发明研究流程。运行 Turn 1 前，先导入 `literature_memory/case2_research_memory_cards.json`，让系统能召回这些研究范式：

- 城市活力结果变量与代理指标的区分
- 街景感知作为解释层或情境层，而不是自动等同于观测活力
- 3D/5D 建成环境基线
- 非线性、SHAP/PDP、GWR/GWRF 的方法前提
- GIS 产物验收和空间推理可复查

导入命令：

```powershell
Set-Location D:/UrbanAgents_Case2/paper4_urban_svgagent
$env:URBAN_HERMES_MEMORY_ROOT = "D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_tester_package/hermes_memory"
python experiments/case2_tester_package/scripts/seed_case2_research_memory.py --replace-case2
```

检查 Turn 1 transcript 时，重点看 Urban-Hermes 是否在数据盘点前后调用或引用了 `urban_research_memory`。合格表现不是照搬文献结论，而是把文献经验转化为本地数据能否支撑的研究问题、变量角色、空间单元、方法门槛和证据边界。

## GIS 后端规则

Urban-Hermes 现在通过 `urban_gis_workspace` 调用可拆装 GIS 后端：

- `qgis_desktop`：生成/验证 QGIS `.qgz` + preview PNG。
- `arcgis_pro`：探测 ArcPy，生成/验证 FileGDB；若本机有 ArcGIS Pro 空白模板，也会生成/验证 `.aprx` 工程。

如果只有 ArcGIS Pro：

1. 先运行 `python experiments/case2_tester_package/scripts/gis_backend_preflight.py`。
2. 继续实验，不要因为缺 QGIS 停止。
3. 回传 `arcgis_workspace/`、`arcgis_validation_report.json`、`spatial_reasoning_manifest.json`。
4. 如果日志里出现 “no .aprx project was validated”，这表示没有找到可读 ArcGIS Pro 工程模板，不是 FileGDB 数据级验收失败。

## 四阶段流程

入口脚本：`DIALOGUE_SCRIPT.md`

| 阶段 | prompt 文件 | 输出目录 |
|---|---|---|
| Turn 1 摸底 | `prompts/realistic_dialogue/turn1_scoping.md` | `turn1_scoping` |
| Turn 2A 设计 | `prompts/realistic_dialogue/turn2a_design_3d5d.md` | `turn2a_design` |
| Turn 2B 执行 | `prompts/realistic_dialogue/turn2b_execute_3d5d.md` | `turn2b_execute` |
| Turn 3 审查 | `prompts/realistic_dialogue/turn3_gwr_gwrf_review.md` | `turn3_gwr_gwrf_review` |
| Turn 4 扩展 | `prompts/realistic_dialogue/turn4_perception_extension.md` | `turn4_perception_extension` |

## 运行命令模板

每次运行前：

```powershell
conda activate urban-hermes-case2
Set-Location D:/UrbanAgents_Case2/paper4_urban_svgagent
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONPATH = "$PWD\hermes_urban_agent;$PWD"
$env:HERMES_HOME = "D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_tester_package/hermes_home"
$env:URBAN_HERMES_MEMORY_ROOT = "D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_tester_package/hermes_memory"
. D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_tester_package/scripts/load_kimi_code_env.ps1 -EnvFile D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_tester_package/env/kimi_code.env
```

Turn 1 示例：

```powershell
New-Item -ItemType Directory -Force -Path "D:/UrbanAgents_Case2_Output/realistic_dialogue/turn1_scoping" | Out-Null
$query = Get-Content "D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_tester_package/prompts/realistic_dialogue/turn1_scoping.md" -Raw
python -m urban_hermes.launcher $query `
  --provider kimi-coding --model kimi-for-coding `
  --max-turns 12 --yolo --toolsets urban,todo,memory `
  2>&1 | Out-File -FilePath "D:/UrbanAgents_Case2_Output/realistic_dialogue/turn1_scoping/cli_transcript_turn1_utf8.txt" -Encoding utf8
```

后续轮次追加 `--resume SESSION_ID`。

## 每轮检查重点

1. Urban-Hermes 是否在提议方法前先读了数据目录？
2. Urban-Hermes 是否在研究摸底阶段召回了相关文献记忆？
3. 是否区分了结果变量、解释变量、控制变量、代理指标和数据缺口？
4. 是否把街景感知分数当成观测活力？
5. 是否把 POI 密度当成人群活动？
6. 是否在没有时间戳时声称昼夜/时间变化？
7. GWR/GWRF 是否先检查了样本量、结果变量、空间诊断才运行？
8. PDP/SHAP 是否建立在有效模型之上？
9. 产物是否包含可外部检查的 CSV、GeoJSON、JSON、报告？

## 回传材料清单

打包一个 `case2_return_YYYYMMDD` 目录，包含：

```text
return_manifest.md           ← 填写 evaluation_templates/collaborator_return_manifest_template.md
install_smoke_log.txt        ← release/commit id、工具列表、Kimi 冒烟结果、GIS backend preflight 状态
case2_research_memory_seed.json ← 文献记忆导入与检索自测结果
turn1_scoping/               ← transcript + 产物
turn2a_design/               ← transcript + 产物
turn2b_execute/              ← transcript + 产物
turn3_gwr_gwrf_review/       ← transcript + 产物
turn4_perception_extension/  ← transcript + 产物
tester_notes.md              ← 测试者观察记录
```

不要打包：`kimi_code.env`、`.env`、含 key 的截图或终端输出。
