# Literature Memory Preload

Case 2 begins with research memory, not with a blank prompt. The memory preload step converts the ten-paper Case 2 literature seed into compact Urban-Hermes research-memory records.

## What Gets Loaded

The default preload uses:

```text
experiments/case2_tester_package/literature_memory/case2_research_memory_cards.json
```

These are Level-1 memory cards. They summarize research-design cues such as urban-vitality outcome evidence, street-view perception as an explanatory layer, 3D/5D built-environment baselines, nonlinear explanation gates, spatial heterogeneity gates, and GIS artifact validation.

They do not load full paper text into the agent context.

## Where It Is Written

The cards are written to Urban-Hermes research memory:

```text
<URBAN_HERMES_MEMORY_ROOT>/research_memory/research_lessons.jsonl
```

Recommended Case 2 memory root:

```powershell
$env:URBAN_HERMES_MEMORY_ROOT = "D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_tester_package/hermes_memory"
```

## Command

```powershell
Set-Location D:/UrbanAgents_Case2/paper4_urban_svgagent
$env:PYTHONPATH = "$PWD\hermes_urban_agent;$PWD"
$env:URBAN_HERMES_MEMORY_ROOT = "D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_tester_package/hermes_memory"
python experiments/case2_tester_package/scripts/seed_case2_research_memory.py --replace-case2
```

The script prints a JSON summary and writes a copy to:

```text
D:/UrbanAgents_Case2_Output/preflight/case2_research_memory_seed.json
```

Look for `inserted_count` and `probe_hits`. A healthy run should retrieve cards about street vitality, streetscape perception, built environment, nonlinear explanation, or spatial heterogeneity.

## How Turn 1 Uses It

Turn 1 says:

```text
你先结合你已有的城市活力、街景感知和建成环境研究记忆...
```

Urban-Hermes should then call or cite `urban_research_memory` before committing to a workflow. The right behavior is not to quote papers. The right behavior is to translate remembered research norms into a local data audit: outcome evidence, explanatory variables, proxy indicators, missing data, spatial analysis units, method gates, and evidence boundaries.

## If The Attached Literature Folder Is Also Present

Some offline packages also include:

```text
experiments/case2_literature_memory_20260518/
```

That folder stores source metadata and extracted paper files for later paper writing or deeper literature checks. It is not needed for the basic Turn 1 preload. Use it only when you need Level-2/Level-3 paper inspection after the dialogue run.