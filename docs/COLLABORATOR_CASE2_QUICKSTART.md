# Collaborator Quickstart: Case2 Urban Vitality

This guide is the collaborator-facing path for running UrbanAgent on a new urban vitality case. It avoids any Paper9 or local Case1 assumptions: study-area data paths belong in the task input JSON, not in framework code.

## 1. Install

```bash
git clone https://github.com/xuanniao57/UrbanAgents.git
cd UrbanAgents

conda create -n urban-agent python=3.10 -y
conda activate urban-agent

python -m pip install -e ".[dev,vision]"
urban-agent init
```

Edit `.urban-agent/.env` and set one provider key, for example `QWEN_API_KEY`, `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, or `KIMI_API_KEY`. By default UrbanAgent keeps config, runs, sessions, logs, cache, and memory under the project-local `.urban-agent/` directory rather than a Windows C-drive profile path. Set `URBAN_AGENT_HOME` before running `urban-agent init` if you want those files on a different drive.

Then verify:

```bash
urban-agent doctor
pytest -q
```

## 2. Prepare Data

Create a copy of `examples/case2_urban_vitality_input.example.json` and replace the placeholder paths with the collaborator's local data.

Minimum useful inputs:

- AOI boundary: GeoJSON polygon for the study area.
- OSM roads/buildings: either local files or allow `fetch_osm_overpass` to retrieve them from the AOI.
- POI or activity points: CSV/GeoJSON with categories if available.
- Optional vitality evidence: population, mobile signaling, transit stops, land-use parcels, street-view images, business reviews, or nighttime light.

UrbanAgent should treat these resources through dataset cards: each resource says what it can support, what it cannot support, and which claims should be blocked or downgraded to proxy indicators.

## 3. Run Case2

```bash
urban-agent analyze ^
  --task "Assess urban vitality for the provided study area. Build a data-grounded workflow, compute supported indicators, disclose proxy and missing indicators, and generate reviewable artifacts." ^
  --input examples/case2_urban_vitality_input.example.json ^
  --interaction-mode supervisory ^
  --output-dir outputs/case2_vitality ^
  --name case2_vitality_first_run
```

On macOS/Linux, replace `^` line continuations with `\`.

## 4. What To Inspect

After the run, inspect:

- `request.json`: confirms the exact input paths and grounding policy.
- `summary.json`: compact status, plan, runtime, and review summary.
- `result.json`: full planner/worker/reviewer record.
- `artifacts/`: maps, tables, data cards, evidence manifests, and reviewer outputs.

For a good Case2 handoff, ask the collaborator to report:

- whether `urban-agent doctor` passed;
- which provider/model was used;
- whether Overpass fetching was needed;
- which indicators were direct, proxy, or missing;
- whether Reviewer blocked any overclaim or source mismatch.

## 5. Expected Case2 Reviewer Behavior

The input-grounding reviewer should check:

- AOI, CRS, and spatial extent are explicit.
- Resource paths exist or an explicit fetch tool is allowed.
- OSM-derived road/building metrics are not confused with POI, mobile, or social vitality evidence.
- POI counts are not overclaimed as human activity unless the input says the POI source and date support that interpretation.
- Proxy indicators are labelled as proxy in tables and final text.

Literature grounding is intentionally left as a reserved interface for now. Do not include it in the Case2 ablation unless a curated paper-card set is provided.

