# Collaborator README: Case 2 Realistic Dialogue Test

## What This Test Is For

This package tests whether Urban-Hermes can behave like a research assistant in a realistic urban-science conversation. The collaborator should not give it a fully specified protocol at the beginning. Start with a short research idea and let Urban-Hermes inspect data, define evidence boundaries, design methods, ask for confirmation, execute, review artifacts, and revise the workflow.

Use this as the main script:

```text
prompts/case2_realistic_research_dialogue_script.md
```

If a local automation agent such as OpenClaw or Claude Code will operate the experiment for you, make it read this file first:

```text
AGENT_TESTER_OPERATOR_GUIDE.md
```

For installing the latest Urban-Hermes runtime, use:

```text
INSTALL_LATEST_URBAN_HERMES.md
```

The older files are still useful:

```text
prompts/case2_natural_question_sequence.md  - earlier structured natural sequence
prompts/case2_full_prompt.md               - one-shot smoke test or control only
```

## Four-Stage Test Logic

### Stage 1: Vague idea and scoping

Human gives only a broad idea: study factors shaping street vitality. Urban-Hermes should inspect the data canvas and decide whether the task is feasible. It should list data sufficiency, variable roles, method requirements, runtime environment, and compute needs.

### Stage 2: Built-environment 3D/5D design and execution

Human asks for a classic built-environment 3D/5D workflow first, without streetscape perception. Urban-Hermes should design the complete workflow, wait for confirmation, then execute the confirmed version. If the observed vitality outcome is missing, it should downgrade rather than fake a model.

### Stage 3: GWR/GWRF, PDP/SHAP, and reviewer self-check

Human pushes for spatial non-stationarity and nonlinearity. Urban-Hermes should treat GWR, GWRF, PDP, and SHAP as gated methods. It should review QGIS layers, fields, spatial joins, model diagnostics, table claims, image-derived variables, and temporal assumptions before explaining results.

### Stage 4: Add subjective streetscape perception

Human asks to add perceived safety, comfort, greenery, liveliness, beauty, and related subjective indicators. Urban-Hermes should use them as explanatory or contextual variables unless a validated observed outcome exists. It should compare the perception-augmented version with the built-environment-only baseline.

## How To Run Each Turn

From the Urban-Hermes repo root or the installed package location, load the environment as described in `CASE2_TESTER_HANDBOOK.md` and `KIMI_CODE_API_SETUP.md`. Then run one prompt at a time.

Before the first turn, the operator should complete `INSTALL_LATEST_URBAN_HERMES.md` and record commit id, tool list, Kimi Code smoke result, and QGIS preflight status.

Example for Turn 1:

```powershell
$query = Get-Content "D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_run/prompts/realistic_dialogue/turn1_scoping.md" -Raw
python -m urban_hermes.launcher $query `
  --provider kimi-coding --model kimi-for-coding `
  --max-turns 12 --yolo --toolsets urban,todo,memory `
  2>&1 | Out-File -FilePath "D:/UrbanAgents_Case2_Output/realistic_dialogue/turn1_scoping/cli_transcript_turn1_utf8.txt" -Encoding utf8
```

For later turns, use the corresponding prompt files and resume the same session when possible:

```powershell
python -m urban_hermes.launcher $query `
  --provider kimi-coding --model kimi-for-coding `
  --max-turns 16 --yolo --toolsets urban,todo,memory `
  --resume SESSION_ID `
  2>&1 | Out-File -FilePath "D:/UrbanAgents_Case2_Output/realistic_dialogue/turn2a_design/cli_transcript_turn2a_utf8.txt" -Encoding utf8
```

Replace `SESSION_ID` with the session id printed by the previous Urban-Hermes run.

## What To Send Back

Please send back:

1. Transcript files for each turn.
2. Output folders under `D:/UrbanAgents_Case2_Output/realistic_dialogue/`.
3. A short tester note explaining where Urban-Hermes grounded correctly, where it overclaimed, and where correction changed behavior.
4. Whether your data had a real observed vitality outcome.
5. Whether QGIS artifacts opened correctly and whether validator/reviewer checks caught any issues.

Use `evaluation_templates/collaborator_return_manifest_template.md` as the return manifest. Use `evaluation_templates/realistic_turn_evaluation_template.md` for per-turn notes.

Do not send API keys, `.env` files, screenshots containing keys, or terminal logs that print secrets.

## Evaluation Focus

The strongest evidence for Section 5.4 is not a high model score. The strongest evidence is a traceable workflow showing:

- Vague intent became a grounded research design.
- Built-environment 3D/5D indicators were handled before adding subjective perception.
- GWR/GWRF and PDP/SHAP were used only when method gates passed.
- QGIS and artifact review made spatial reasoning checkable.
- Subjective streetscape perception was not confused with observed urban vitality.
