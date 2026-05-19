# Case 2 Tester Package

> 给合作者：先读 `TESTER_ROLE.md`，再按 `INSTALL.md` 装环境，最后按 `DIALOGUE_SCRIPT.md` 跑实验。

## 核心文档

| 文档 | 用途 |
|---|---|
| `TESTER_ROLE.md` | 测试者身份、实验规则、逐轮检查清单、回传材料清单 |
| `INSTALL.md` | 从本地目录/压缩包安装 Urban-Hermes + 配置 Kimi Code API + 冒烟测试 |
| `DIALOGUE_SCRIPT.md` | 四阶段真实对话剧本（正式推荐主流程） |
| `ARCGIS_PRO_SUPPORT.md` | ArcGIS Pro 后端说明、`.aprx` 解释、ArcPy/FileGDB 验收策略 |

## 三个对话流程版本

| 版本 | 文件 | 定位 |
|---|---|---|
| 正式推荐 | `DIALOGUE_SCRIPT.md` | 低结构真实对话，合作者主流程 |
| 结构化基线 | `prompts/case2_natural_question_sequence.md` | 早期自然问题序列，保留对照 |
| 合并式对照 | `prompts/case2_full_prompt.md` | 完整 prompt，仅 smoke test |

## 短 prompt（逐轮复制用）

```
prompts/realistic_dialogue/
  turn1_scoping.md
  turn2a_design_3d5d.md
  turn2b_execute_3d5d.md
  turn3_gwr_gwrf_review.md
  turn4_perception_extension.md
```

## 辅助文件

| 路径 | 用途 |
|---|---|
| `env/kimi_code.env.example` | API 配置模板（不含真实 key） |
| `scripts/load_kimi_code_env.ps1` | 本地加载 API key |
| `scripts/gis_backend_preflight.py` | 探测 `urban_gis_workspace`、QGIS Desktop、ArcGIS Pro 后端 |
| `data_canvas/README.md` | 数据画布约定（只约目录，不约格式） |
| `qgis_validation/` | 旧版独立 QGIS 验收脚本；新协议优先用 `urban_gis_workspace` |
| `evaluation_templates/` | 回传清单 + 逐轮评价模板 |
| `literature_memory/` | 十篇文献记忆种子 |
| `prompts/ablation/` | 消融 prompt |

## 已整合的旧文档

以下文件内容已整合入三份核心文档，保留仅供参考：`CASE2_TESTER_HANDBOOK.md`、`COLLABORATOR_REALISTIC_TEST_README.md`、`AGENT_TESTER_OPERATOR_GUIDE.md`、`INSTALL_LATEST_URBAN_HERMES.md`、`KIMI_CODE_API_SETUP.md`、`evaluation_templates/section_5_4_writing_guide.md`、`evaluation_templates/section_5_4_realistic_dialogue_outline.md`
