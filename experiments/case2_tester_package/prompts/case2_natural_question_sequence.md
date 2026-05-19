# Case 2 Natural Question Sequence

> Status: retained as an earlier structured baseline. For collaborator-facing realistic testing, use `case2_realistic_research_dialogue_script.md` and the short prompts in `prompts/realistic_dialogue/`.

Use this sequence instead of asking Urban-Hermes one complex manuscript-style question.

The sequence is intentionally conversational.
It lets the agent infer subquestions, retrieve research memory, inspect data, and then decide what can be supported.

## Turn 1: Vitality Factors

Purpose: start from a normal planning-analysis question.

User prompt:

```text
我想探究这个片区人群活力或街道活力的影响因素。

请先不要急着建模。
请把 D:/UrbanAgents_Case2_Data 当作数据画布，先帮我判断：
1. 这个问题里可能的 Y 是什么；
2. 现有数据里哪些能作为直接观测，哪些只能作为 proxy，哪些是 missing；
3. 适合用什么空间单元和时间窗口；
4. 如果现在数据不够，研究问题应该怎么降级才合理。

请把初步判断、数据清单、direct/proxy/missing 表和下一步建议保存到 D:/UrbanAgents_Case2_Output/natural_sequence/turn1。
```

Expected behavior:

- The agent should inspect data before method choice.
- It should not assume street-view perception or POI is observed vitality.
- It should produce a grounded research-problem decomposition.

## Turn 2: Subjective Built-Environment Perception

Purpose: introduce subjective perception naturally as a subquestion.

User prompt:

```text
如果我还关心人的主观建成环境感知，比如街景是否安全、舒适、绿色、热闹或有美感，这类 X 应该怎么评估？

这些感知指标能不能通过街景图像或大模型来得到？
它们在刚才的活力研究里应该算解释变量、情境变量，还是结果变量？

请结合你能检索到的研究记忆或已有经验，给出一个可执行但谨慎的工作流。
如果需要生成中间表或空间文件，请保存到 D:/UrbanAgents_Case2_Output/natural_sequence/turn2。
```

Expected behavior:

- The agent should retrieve literature memory about perception measurement.
- It should distinguish subjective perception X from observed outcome Y.
- It should state validation needs for LLM or image-derived perception scores.

## Turn 3: Nonlinearity and Spatial Heterogeneity

Purpose: add the advanced research-design question only after variables and evidence boundaries are clear.

User prompt:

```text
在前两步的基础上，如果数据支持，我想进一步看这些感知 X、客观建成环境变量和活力 Y 之间是否存在非线性关系或空间异质性。

请你判断当前数据是否足以做这一步。
如果足够，请设计从基线模型到非线性诊断、解释性分析和空间异质性诊断的流程。
如果不足，请说明缺什么，并给出一个不夸大结论的降级方案。

请把方法门槛、可执行步骤、失败条件、最终报告和可检查产物保存到 D:/UrbanAgents_Case2_Output/natural_sequence/turn3。
```

Expected behavior:

- The agent should gate advanced models behind data sufficiency checks.
- It should avoid causal language unless the design supports causality.
- It should create or request checkable artifacts rather than only narrative.

## Tester Evaluation Focus

For each turn, record:

- Did the agent read the data canvas?
- Did it separate direct, proxy, and missing evidence?
- Did it retrieve or reuse literature memory in a traceable way?
- Did it avoid turning perception scores into observed vitality?
- Did it create checkable files under the requested output folder?
- Did it state model failure conditions and downgrade paths?

## Paper-Writing Interpretation

This sequence supports Section 5.4 as a process experiment:

- Turn 1 shows Gap 1: vague intent becomes grounded research requirements.
- Turn 2 shows how literature memory helps introduce subjective perception without making the setup artificial.
- Turn 3 shows Gap 2: reasoning becomes a reviewable workflow with model gates, artifacts, and claim limits.

Gap 3 should only be mentioned lightly here if memory retrieval is observed.
The main cross-task memory claim belongs in Section 5.5.
