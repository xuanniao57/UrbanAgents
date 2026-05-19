# Layered Literature Memory Extraction Schema

Use this schema after MinerU has extracted one paper to Markdown and images.

The extraction target is not a normal literature review note.
It is a research-memory record that Urban-Hermes can retrieve during Case 2.

## Layer 0: Source Evidence

Record only traceable facts.

- paper_id
- title
- pdfPath
- mineru_extract_dir
- full_md_path
- image_dir
- extraction_status
- sections_used
- figures_or_tables_used

## Layer 1: Research Flow

Extract the paper's research trajectory as an ordered flow.

Each flow stage should answer:

- What decision is made at this stage?
- What evidence does the paper use?
- What operation connects the previous stage to the next one?
- What claim becomes possible only after this stage?

Recommended stages:

1. Problem framing
2. Outcome definition or downgrade
3. Perception / built-environment variable construction
4. Data-source and spatial-unit alignment
5. Direct / proxy / missing evidence classification
6. Exploratory analysis and diagnostics
7. Model selection and gating
8. Spatial heterogeneity or nonlinearity analysis
9. Validation and robustness checks
10. Claim boundary and planning implication

## Layer 2: Problem-Data-Method Triples

Triples are the most abstract retrieval layer.
They should be compact and reusable.

Format:

```json
{
  "problem": "Assess whether perceived streetscape safety relates to pedestrian activity at street-segment level",
  "data": ["street-view perception scores", "observed pedestrian volume", "street segments", "control variables"],
  "method": ["spatial join", "correlation or baseline model", "nonlinear model only if sample size and Y are valid"],
  "claim_limit": "Association only; no causal claim unless design supports causality"
}
```

Rules:

- Do not create a triple unless all three parts are explicit or strongly inferable from the paper.
- If the data are proxies, mark them as proxies.
- If Y is missing in Case 2, the triple can suggest a downgraded workflow but cannot authorize outcome claims.

## Layer 3: Workflow Steps

Workflow steps are operational working memory.
They should be concrete enough for Urban-Hermes to execute or check.

Each step should contain:

- step_id
- action
- inputs
- outputs
- required_checks
- tool_hint
- failure_condition
- fallback_or_downgrade

Example:

```json
{
  "step_id": "align_perception_to_units",
  "action": "Aggregate street-view perception points to the chosen spatial units",
  "inputs": ["streetview_perception.csv", "spatial_units.geojson"],
  "outputs": ["unit_perception_scores.csv", "unit_perception_scores.geojson"],
  "required_checks": ["CRS consistency", "point-in-polygon success rate", "missing-value share"],
  "tool_hint": "urban_host_python or GIS spatial join",
  "failure_condition": "No coordinates or no spatial unit geometry",
  "fallback_or_downgrade": "Report perception data as unavailable for spatial modeling"
}
```

## Layer 4: Case 2 Reuse Rules

This layer controls how a memory can be used in the actual Case 2 dialogue.

Required fields:

- when_to_retrieve
- helps_answer
- allowed_claims
- blocked_claims
- minimum_data_requirements
- reviewer_risk

Example:

```json
{
  "when_to_retrieve": "User asks how to evaluate subjective built-environment perception from street-view imagery",
  "helps_answer": "Suggest perception dimensions, image sampling, model-based scoring, and validation checks",
  "allowed_claims": ["perception scores can be used as explanatory X or contextual indicators"],
  "blocked_claims": ["perception score is observed pedestrian vitality", "LLM score is ground-truth human perception without validation"],
  "minimum_data_requirements": ["image or image-derived scores", "spatial coordinates", "metadata about model or labeling procedure"],
  "reviewer_risk": "High if the workflow treats subjective score as direct outcome or skips validation"
}
```

## Final Memory Record Shape

Save each extracted record as `extracted_memory/{paper_id}.json` and optionally a readable Markdown note.

```json
{
  "paper_id": "...",
  "title": "...",
  "source": {
    "pdfPath": "...",
    "full_md_path": "...",
    "evidence_sections": []
  },
  "research_flow": [],
  "problem_data_method_triples": [],
  "workflow_steps": [],
  "case2_reuse_rules": [],
  "blocked_claims": [],
  "open_questions": []
}
```

## Quality Checks

Before a paper memory is accepted:

- The research flow must have at least 5 stages.
- At least one stage must describe data alignment or variable construction.
- Triples must be fewer and more abstract than workflow steps.
- Workflow steps must include failure conditions.
- Case 2 reuse rules must include blocked claims.
- Every strong claim must point back to a MinerU Markdown section or table/figure.
