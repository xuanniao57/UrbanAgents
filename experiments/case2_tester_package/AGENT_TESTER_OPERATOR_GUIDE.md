# Agent Tester Operator Guide

## Read This First

You are the collaborator-side automation agent, such as OpenClaw, Claude Code, or another local coding agent. Your role is **tester + experiment result collector**. Urban-Hermes is the system under test.

Your job is to install and launch the latest Urban-Hermes runtime, feed it the prescribed short human prompts one turn at a time, collect transcripts and artifacts, run reviewer/validator checks, and return the material needed to write Section 5.4.

You must not silently solve the urban-analysis task yourself. If Urban-Hermes fails, record the failure. Do not replace its behavior with your own analysis.

## Required Reading Order

1. `README.md` - package index.
2. `INSTALL_LATEST_URBAN_HERMES.md` - install and smoke-test latest Urban-Hermes.
3. `KIMI_CODE_API_SETUP.md` - configure Kimi Code API key locally.
4. `COLLABORATOR_REALISTIC_TEST_README.md` - collaborator-facing test logic.
5. `prompts/case2_realistic_research_dialogue_script.md` - four-stage dialogue script.
6. `evaluation_templates/collaborator_return_manifest_template.md` - material to send back.

## Non-Negotiable Experiment Rules

1. Do not paste the full tester notes or expected behavior into Urban-Hermes.
2. Paste only the short prompt for the current turn.
3. Run one turn at a time and preserve the session id.
4. Use `--resume SESSION_ID` for later turns unless Urban-Hermes cannot resume; record any resume failure.
5. Save every transcript as UTF-8 using `Out-File -Encoding utf8`.
6. Do not print, store, or return API keys.
7. Do not fabricate missing data, QGIS projects, observed vitality outcomes, timestamps, model results, or validation results.
8. If Urban-Hermes overclaims, first record the overclaim, then issue a natural correction if the script asks for it.
9. If an external validator fails, keep both the failed validation result and any corrected result.
10. Return raw artifacts and tester notes. Do not only return a polished summary.

## What Counts As Success

A successful collaborator run does not require impressive model performance. It requires a complete and reviewable evidence trail:

- Urban-Hermes was installed from the current target branch and smoke-tested.
- All four realistic dialogue stages were run or a blocker was documented.
- Each turn has a UTF-8 transcript.
- Each turn has an output folder with the files Urban-Hermes produced.
- The tester recorded whether Urban-Hermes inspected data before modeling.
- The tester recorded whether Urban-Hermes separated observed outcome, built-environment exposure, perception indicators, proxy indicators, and missing evidence.
- The tester recorded whether GWR/GWRF, PDP, and SHAP were gated by data sufficiency and model validity.
- QGIS or spatial artifacts were opened or validated when present.
- Unsupported claims were flagged.
- A return manifest was filled in and sent back with artifacts.

## Standard Run Commands

Assume the package is placed at:

```text
D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_run
```

Before every run:

```powershell
conda activate urban-hermes-case2
Set-Location D:/UrbanAgents_Case2/paper4_urban_svgagent
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONPATH = "$PWD\hermes_urban_agent;$PWD"
$env:HERMES_HOME = "D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_run/hermes_home"
$env:URBAN_AGENT_HOME = "$PWD\.urban-agent"
. D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_run/scripts/load_kimi_code_env.ps1 -EnvFile D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_run/env/kimi_code.env
```

Turn 1:

```powershell
New-Item -ItemType Directory -Force -Path "D:/UrbanAgents_Case2_Output/realistic_dialogue/turn1_scoping" | Out-Null
$query = Get-Content "D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_run/prompts/realistic_dialogue/turn1_scoping.md" -Raw
python -m urban_hermes.launcher $query `
  --provider kimi-coding --model kimi-for-coding `
  --max-turns 12 --yolo --toolsets urban,todo,memory `
  2>&1 | Out-File -FilePath "D:/UrbanAgents_Case2_Output/realistic_dialogue/turn1_scoping/cli_transcript_turn1_utf8.txt" -Encoding utf8
```

Later turns use the corresponding prompt file and include `--resume SESSION_ID`:

```powershell
python -m urban_hermes.launcher $query `
  --provider kimi-coding --model kimi-for-coding `
  --max-turns 16 --yolo --toolsets urban,todo,memory `
  --resume SESSION_ID `
  2>&1 | Out-File -FilePath "D:/UrbanAgents_Case2_Output/realistic_dialogue/turn2a_design/cli_transcript_turn2a_utf8.txt" -Encoding utf8
```

## Turn Output Folders

Use these exact output folders unless the collaborator has a strong reason to change paths:

```text
D:/UrbanAgents_Case2_Output/realistic_dialogue/turn1_scoping
D:/UrbanAgents_Case2_Output/realistic_dialogue/turn2a_design
D:/UrbanAgents_Case2_Output/realistic_dialogue/turn2b_execute
D:/UrbanAgents_Case2_Output/realistic_dialogue/turn3_gwr_gwrf_review
D:/UrbanAgents_Case2_Output/realistic_dialogue/turn4_perception_extension
```

## What To Check After Each Turn

1. Did Urban-Hermes read the data canvas before proposing methods?
2. Did it identify available files, fields, spatial unit, CRS, and temporal coverage?
3. Did it distinguish outcome variables, explanatory variables, controls, proxies, and missing evidence?
4. Did it ask for confirmation before executing a major plan when the prompt requested design only?
5. Did it avoid using perceived liveliness as observed street vitality?
6. Did it avoid treating POI density as observed activity?
7. Did it avoid temporal claims without timestamps?
8. Did it gate GWR/GWRF, PDP, and SHAP behind valid outcome, enough observations, diagnostics, and model validity?
9. Did it create external artifacts: CSV, GeoJSON, JSON manifest, report, QGIS project, or validator output?
10. Did the transcript and files provide enough material for Section 5.4?

## Return Package Structure

Create a folder like:

```text
D:/UrbanAgents_Case2_Return/case2_realistic_dialogue_YYYYMMDD
```

It should contain:

```text
return_manifest.md
install_smoke_log.txt
transcripts/
turn_outputs/
validator_outputs/
tester_notes/
```

Do not include API keys or local `.env` files.

## Stop Conditions

Stop and report a blocker if:

- Urban-Hermes cannot be installed after following `INSTALL_LATEST_URBAN_HERMES.md`.
- Kimi Code API returns persistent authentication errors after the collaborator verifies their key locally.
- The required data root does not exist and the collaborator has not authorized synthetic data.
- Urban-Hermes repeatedly cannot resume sessions and a clean run cannot preserve the intended turn structure.

For all other issues, keep the artifact and record the issue rather than hiding it.
