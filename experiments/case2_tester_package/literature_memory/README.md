# Case 2 Literature Memory Workflow

This folder defines the paper-library memory workflow used to support Case 2.

The goal is not to paste a complex manuscript-style research question into Urban-Hermes.
The goal is to let Urban-Hermes use prior research experience to move from small natural questions to a defensible research trajectory.

## Core Rule

Process papers one by one.

Do not upload 10 PDFs to MinerU in one request.
Do not run a large unattended batch for this step.
For each paper, create a single-paper JSON input, run MinerU for that one paper, check the output, then move to the next paper.

Recommended command pattern:

```powershell
python .\literature_memory\scripts\prepare_single_paper_input.py `
  --manifest .\literature_memory\selected_papers.json `
  --paper-id subjective_vitality_multimodal `
  --output-dir .\literature_memory\single_inputs

python C:/Users/18029/.claude/skills/zotero-pdf-analyzer/scripts/mineru_api_v4.py `
  --input .\literature_memory\single_inputs\subjective_vitality_multimodal.json `
  --output .\literature_memory\mineru_output `
  --batch-size 1 `
  --model-version vlm
```

After each run, inspect the extracted folder and update `selected_papers.json` status fields before processing the next paper.

## Runtime Preload For Urban-Hermes

Before the formal Case 2 dialogue, the tester should import the lightweight memory cards into Urban-Hermes research memory:

```powershell
Set-Location D:/UrbanAgents_Case2/paper4_urban_svgagent
$env:URBAN_HERMES_MEMORY_ROOT = "D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_tester_package/hermes_memory"
python experiments/case2_tester_package/scripts/seed_case2_research_memory.py --replace-case2
```

The script writes to:

```text
<URBAN_HERMES_MEMORY_ROOT>/research_memory/research_lessons.jsonl
```

It also runs a retrieval probe for street vitality, streetscape perception, built environment, nonlinearity, and spatial heterogeneity. This means Turn 1 can ask Urban-Hermes to use its existing research memory without pasting the ten-paper notes into the prompt.

The imported cards are Level-1 memory only: compact research-design cues, method gates, and evidence boundaries. Full `full.md` paper text should not be loaded into Turn 1. Use Level-2 outlines and Level-3 original sections only when the paper-writing task later requires a specific citation or figure/table comparison.

## Memory Layers

The extraction is deliberately layered.
It should not jump directly from full paper text to flat triples.

Layer 1: Research Flow

This is the paper's research trajectory.
It captures how the authors move from a problem to data, variables, spatial units, methods, validation, and claims.

Layer 2: Problem-Data-Method Triples

This is the most abstract representation.
Each triple links a research problem to the data evidence and method family that can support it.
These triples are useful for retrieval and quick planning, but they are not enough by themselves.

Layer 3: Workflow Steps

This is the operational working memory.
It expands each research-flow stage into concrete steps Urban-Hermes can reuse:
field checks, CRS checks, spatial joins, direct/proxy/missing decisions, model gating, validation artifacts, and claim limits.

Layer 4: Case 2 Reuse Rules

This layer states when a memory can be reused in Case 2 and when it must be blocked.
It is where unsupported claims, missing outcome variables, temporal gaps, and causal language are controlled.

## Folder Layout

```text
literature_memory/
├── README.md
├── selected_papers.json
├── case2_research_memory_cards.json
├── extraction_schema.md
├── memory_template.md
├── single_inputs/
├── mineru_output/
├── extracted_memory/
└── scripts/
    └── prepare_single_paper_input.py
```

## Case 2 Question Design

The user-facing Case 2 prompt should be split into small natural questions.
Use `../prompts/case2_natural_question_sequence.md` as the preferred prompt sequence.

Suggested sequence:

1. I want to explore factors associated with human activity or urban vitality in this area.
2. Can subjective built-environment perception from street-view images be evaluated, and how would it fit into that study?
3. If the data support it, how should we examine nonlinear relationships or spatial heterogeneity without overstating the evidence?

This preserves a realistic user interaction.
It lets the agent infer subquestions and evidence requirements instead of receiving a finished research design as a single prompt.
