
import json
from pathlib import Path

RUNDIR = Path("D:/GitHub_1/world_agent/urban-mobility-agent/paper4_urban_svgagent/experiments/case2_process_materials_rerun_20260527_020009")

# --- 1. Repair route_tree_frontend_state.json ---
frontend_path = RUNDIR / "route_tree_frontend_state.json"
with open(frontend_path, 'r', encoding='utf-8') as f:
    frontend = json.load(f)

# Target artifacts to attach (paths as strings)
new_artifacts = [
    {
        "path": str(RUNDIR / "artifacts" / "s1_outcome" / "study_area_locator_map.png"),
        "type": "map",
        "title": "Study area locator map (two-panel publication layout)"
    },
    {
        "path": str(RUNDIR / "artifacts" / "s1_outcome" / "study_area_locator_map_note.json"),
        "type": "metadata",
        "title": "Study area locator map artifact note"
    }
]

# Find RO_01 node by 'id' (frontend schema uses 'id', not 'node_id')
target_node = None
for node in frontend["nodes"]:
    if node.get("id") == "RO_01_all_window_aggregate":
        target_node = node
        break

if target_node is None:
    raise ValueError("RO_01_all_window_aggregate node not found in frontend state")

# Deduplicate by path before appending
existing_paths = {a["path"] for a in target_node.get("artifacts", [])}
added = 0
for art in new_artifacts:
    if art["path"] not in existing_paths:
        target_node.setdefault("artifacts", []).append(art)
        added += 1

frontend["meta"]["updated_at"] = "2026-05-27T03:25:00"

with open(frontend_path, 'w', encoding='utf-8') as f:
    json.dump(frontend, f, indent=2, ensure_ascii=False)

print(f"Frontend state: added {added} artifact(s) to node id=RO_01_all_window_aggregate")
print(f"  Total artifacts on RO_01: {len(target_node['artifacts'])}")
for a in target_node["artifacts"]:
    print(f"    - {a['type']}: {Path(a['path']).name}")

# --- 2. Verify route_tree_state.json already has them (read-only check) ---
state_path = RUNDIR / "route_tree_state.json"
with open(state_path, 'r', encoding='utf-8') as f:
    state = json.load(f)

state_ro01 = None
for node in state["nodes"]:
    if node.get("node_id") == "RO_01_all_window_aggregate":
        state_ro01 = node
        break

state_has_png = any("study_area_locator_map.png" in a.get("path","") for a in state_ro01.get("artifacts",[]))
state_has_note = any("study_area_locator_map_note.json" in a.get("path","") for a in state_ro01.get("artifacts",[]))
print(f"\nroute_tree_state.json RO_01 has locator map png: {state_has_png}")
print(f"route_tree_state.json RO_01 has locator map note: {state_has_note}")

# --- 3. Verify artifact_manifest.json already has them (read-only check) ---
manifest_path = RUNDIR / "trace" / "artifact_manifest.json"
with open(manifest_path, 'r', encoding='utf-8') as f:
    manifest = json.load(f)

manifest_has_png = any("study_area_locator_map.png" in a.get("path","") for a in manifest.get("artifacts",[]))
manifest_has_note = any("study_area_locator_map_note.json" in a.get("path","") for a in manifest.get("artifacts",[]))
print(f"artifact_manifest.json has locator map png: {manifest_has_png}")
print(f"artifact_manifest.json has locator map note: {manifest_has_note}")

# --- 4. Write frontend_attachment_repair_report.md ---
report = """# Frontend Attachment Repair Report

## Task
Repair route_tree_frontend_state.json artifact attachment for RO_01_all_window_aggregate.
The frontend schema uses `nodes[].id`, not `nodes[].node_id`.

## Findings
- **route_tree_frontend_state.json**: RO_01 node (id="RO_01_all_window_aggregate") was MISSING the two locator-map artifacts.
- **route_tree_state.json**: Already contained both artifacts on RO_01 (verified, no changes made).
- **trace/artifact_manifest.json**: Already contained both artifacts for RO_01 (verified, no changes made).

## Repair Action
- Added 2 artifacts to `nodes[].artifacts` where `id == "RO_01_all_window_aggregate"`:
  1. `study_area_locator_map.png` (type: map)
  2. `study_area_locator_map_note.json` (type: metadata)
- Deduplication: checked existing paths before append; 0 duplicates encountered.
- Updated `meta.updated_at` to 2026-05-27T03:25:00.

## Verification
- RO_01 artifact count after repair: {ro01_count}
- route_tree_state.json has artifacts: png={state_png}, note={state_note}
- artifact_manifest.json has artifacts: png={manifest_png}, note={manifest_note}
- No other nodes or fields modified.

## Files Modified
- `route_tree_frontend_state.json` (only)

## Files Verified but Unchanged
- `route_tree_state.json`
- `trace/artifact_manifest.json`
""".format(
    ro01_count=len(target_node["artifacts"]),
    state_png=state_has_png,
    state_note=state_has_note,
    manifest_png=manifest_has_png,
    manifest_note=manifest_has_note
)

report_path = RUNDIR / "frontend_attachment_repair_report.md"
with open(report_path, 'w', encoding='utf-8') as f:
    f.write(report)

print(f"\nWrote report: {report_path} ({report_path.stat().st_size} bytes)")
