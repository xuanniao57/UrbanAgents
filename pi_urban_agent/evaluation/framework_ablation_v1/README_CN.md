# 五条件完整工作流消融

五个条件使用相同模型、数据副本、上下文窗口、随机种子和六轮自然人类消息：

1. `pi_plain`：纯 Pi ReAct，只有通用文件和终端工具；不加载 Urban 扩展。
2. `urban_no_planner`：保留 Worker、Reviewer、Research Tree、人类决议和树感知上下文，只关闭 Planner 的路线族提交与任务包工具。
3. `urban_no_reviewer`：保留 Planner、Worker、Research Tree、人类决议和树感知上下文，只关闭 Reviewer 审核包与审核决议工具。
4. `urban_no_context`：保留 Planner、Reviewer、工具、人类决议和权威 Research Tree；关闭自动状态书签与召回注入，改用 Pi 时间顺序压缩。模型仍可主动查询树。
5. `urban_full`：完整 Urban Agent。

第四个条件不是删除 Research Tree。若把树本身删除，Planner、Reviewer、人工补丁和上下文恢复会同时失去共同状态，无法归因于单一模块。纯 Pi 已提供无 Research Tree 的整体架构基线。

运行示例：

```powershell
npm run eval:framework-ablation -- --model Qwen3.5-9B --provider local-ollama --data-root ..\long_case\data --output-root evaluation\framework_ablation_runs --context-window 8192 --max-output-tokens 2048 --repeats 3
```

独立 LLM judge 使用 `JUDGE_RUBRIC.md`，输入中必须去除条件名。机械完成项和语义质量分开汇总。
