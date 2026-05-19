# Case 2 Collaborator Return Manifest

Copy this file to `return_manifest.md` in the return package and fill it after the experiment.

## 1. Run Metadata

- Collaborator:
- Local agent used (OpenClaw / Claude Code / other):
- Date:
- OS:
- UrbanAgents repo path:
- Case2 package path:
- Output root:

## 2. Urban-Hermes Installation

- Branch:
- Commit hash:
- Conda env:
- Python version:
- `python -m urban_hermes.launcher --list-tools --plain` passed: yes / no
- Core tools present:
  - `urban_host_fs`: yes / no
  - `urban_host_python`: yes / no
  - `urban_ground_task`: yes / no
  - `urban_research_memory`: yes / no
  - `urban_record_feedback`: yes / no
  - `urban_review`: yes / no
  - `urban_qgis_workspace`: yes / no
  - `urban_qgis_process`: yes / no
- Kimi Code smoke test passed: yes / no
- QGIS Python path:
- QGIS preflight passed: yes / no / not available

## 3. Data Canvas

- Data root:
- AOI present: yes / no
- Spatial units present: yes / no
- Streetview perception data present: yes / no
- Built-environment data present: yes / no
- Observed vitality outcome present: yes / no
- Timestamps or temporal window present: yes / no
- Data are real / synthetic / mixed:
- Notes on data provenance:

## 4. Dialogue Runs

| Turn | Prompt file | Session id | Transcript path | Output folder | Status |
|---|---|---|---|---|---|
| Turn 1 scoping | `prompts/realistic_dialogue/turn1_scoping.md` | | | | pass / partial / fail |
| Turn 2A design | `prompts/realistic_dialogue/turn2a_design_3d5d.md` | | | | pass / partial / fail |
| Turn 2B execute | `prompts/realistic_dialogue/turn2b_execute_3d5d.md` | | | | pass / partial / fail |
| Turn 3 GWR/GWRF review | `prompts/realistic_dialogue/turn3_gwr_gwrf_review.md` | | | | pass / partial / fail |
| Turn 4 perception extension | `prompts/realistic_dialogue/turn4_perception_extension.md` | | | | pass / partial / fail |

## 5. Evidence For Section 5.4

### 5.4.1 Vague idea and scoping

- Did Urban-Hermes inspect data before method choice? yes / no
- Evidence path or transcript excerpt:
- Did it identify method/environment/compute requirements? yes / no
- Evidence path:

### 5.4.2 Built-environment 3D/5D baseline

- Did it define 3D/5D indicators according to available fields? yes / no
- Did it separate design from execution and wait for confirmation? yes / no
- Evidence path:

### 5.4.3 GWR/GWRF and reviewer self-check

- Did it gate GWR/GWRF by outcome validity, sample size, spatial diagnostics, and bandwidth/local estimation? yes / no
- Did it gate PDP/SHAP by model validity? yes / no
- Did it inspect QGIS/spatial artifacts? yes / no / not available
- Evidence path:

### 5.4.4 Perception-augmented revision

- Did it treat streetscape perception as explanatory/contextual rather than observed vitality? yes / no
- Did it compare perception-augmented workflow with built-environment-only baseline? yes / no
- Evidence path:

## 6. Unsupported Claims Found

| Claim | Turn | Where found | Corrected? | Notes |
|---|---|---|---|---|
| Perception treated as observed vitality | | | yes / no | |
| POI treated as observed activity | | | yes / no | |
| GWR/GWRF run without gates | | | yes / no | |
| SHAP/PDP explained invalid model | | | yes / no | |
| Temporal pattern claimed without timestamps | | | yes / no | |
| Causal language from association/ML | | | yes / no | |

## 7. Validator / Reviewer Checks

- QGIS project generated: yes / no
- QGIS project opened: yes / no / not attempted
- QGIS validator path:
- Manifest/schema validator path:
- Validator summary:

```text
Paste key validator output here, without API keys.
```

## 8. Return Folder Contents

Confirm included items:

- [ ] `return_manifest.md`
- [ ] `install_smoke_log.txt`
- [ ] transcripts for all completed turns
- [ ] output folders for all completed turns
- [ ] tester notes
- [ ] validator outputs if any
- [ ] no API keys or `.env` files

## 9. Short Narrative For Paper Author

Write 5-10 bullets, focusing on what can be used in Section 5.4:

- 
- 
- 

## 10. Blockers Or Deviations

List anything that changed the protocol:

- 
- 
