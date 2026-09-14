# 27B 实验室运行包（2026-09-14）

目标：同一个六轮完整工作流，五条件各3次，共15次。不是旧版只执行OLS的上下文测试。压缩后恢复仅在真实发生压缩的运行中评价。

## 包内内容

Pi 0.84.2、Urban源码、锁文件、通用工具适配、实验脚本、七尺度聚合CSV和网格GeoJSON、数据合同、协议和评分说明、Qwen tokenizer。无API密钥、原始设备轨迹、模型权重或node_modules。不对外公开本研究数据。

## 环境

推荐Linux、Node 22（npm须可用）、Python 3.12。推理服务与分析Python环境分开。先进入解压后的 `pi_urban_agent`：

```bash
python3.12 -m venv .venv-analysis
.venv-analysis/bin/python -m pip install numpy==2.4.6 pandas==3.0.5 scipy==1.17.1 scikit-learn==1.9.0
npm ci
export URBAN_PI_PYTHON="$(pwd)/.venv-analysis/bin/python"
```

若镜像源无法提供指定版本，请保留报错并联系核对，不要悄悄换版本。`npm ci`会执行共享请求预算兼容补丁，不能使用`--ignore-scripts`。不要整体搬运Windows的node_modules。

## 连接27B服务

使用你已有、支持工具调用的Qwen3.5-27B OpenAI兼容服务。服务需要 `/v1/chat/completions`，模型列表需包含所填模型名。服务上下文至少8192，测试脚本统一8192输入输出总窗口、2048输出上限、关闭thinking。权重精度/量化方式、服务版本、GPU型号请保存到运行说明，不同量化不能假装相同模型配置。

```bash
export URBAN_LAB_MODEL='Qwen3.5-27B'
export URBAN_LAB_BASE_URL='http://127.0.0.1:8000/v1'
curl "$URBAN_LAB_BASE_URL/models"
node scripts/run-lab-framework.mjs
```

Windows同样可运行，先安装对应Python包和 `npm ci`，使用PowerShell设置 `$env:URBAN_PI_PYTHON='分析环境python.exe的绝对路径'`、`$env:URBAN_LAB_MODEL`、`$env:URBAN_LAB_BASE_URL`，然后相同node命令。

本包不捆绑或自动启动vLLM；具体启动参数取决于实验室已有版本及模型模板。不要在未验证工具调用支持时跑整批实验。

## 运行与回收

每个条件/重复均为新会话和独立工作区，默认串行，最多每轮600秒。重复编号对应42、43、44。不要复用旧输出目录；重跑设置 `URBAN_LAB_OUTPUT=evaluation/lab27b_retry_日期`，保留失败记录。

回传整个 `evaluation/lab27b_full`，其中含请求使用量、对话、工具调用、生成脚本、结果、研究状态与运行汇总；同时回传模型服务版本和硬件信息。目录内模型产生的文本均为未可信研究产物，不能直接当论文结果。

`framework_ablation_summary.json`只报告运行状态与耗时，不代表科学正确率。依据 `JUDGE_RUBRIC.md` 和 `SCORING_ADDENDUM_20260914.md` 独立复核后才填论文表。当前包不冒充已完成27B测试。

## 条件解释

- urban_full：全部Urban模块。
- urban_no_planner：去专用规划/路线族模块，仍允许模型自然规划。
- urban_no_reviewer：去专用Reviewer及审核记录，仍允许模型检查并修复。
- urban_no_context：保留Tree、Planner、Reviewer，去自动书签/召回注入，用Pi压缩。
- pi_plain：无Urban扩展，通用文件/终端工具，仍使用双方共同的底层请求预算保护。

因此最后一项应在论文写作中说明“Pi baseline with shared request-budget safeguards”，不是完全未改动的上游Pi软件。
