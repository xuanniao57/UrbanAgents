
import json
from pathlib import Path

RUNDIR = Path("D:/GitHub_1/world_agent/urban-mobility-agent/paper4_urban_svgagent/experiments/case2_process_materials_rerun_20260527_020009")

# 1. Update artifact_manifest.json
manifest_path = RUNDIR / "trace" / "artifact_manifest.json"
with open(manifest_path, 'r', encoding='utf-8') as f:
    manifest = json.load(f)

# Append new artifacts
new_artifacts = [
    {
        "node_id": "RO_01_all_window_aggregate",
        "path": str(RUNDIR / "artifacts" / "s1_outcome" / "study_area_locator_map.png"),
        "type": "map",
        "title": "Study area locator map (two-panel publication layout)",
        "produced_at": "2026-05-27T03:18:00Z",
        "produced_by": "urban_host_python"
    },
    {
        "node_id": "RO_01_all_window_aggregate",
        "path": str(RUNDIR / "artifacts" / "s1_outcome" / "study_area_locator_map_note.json"),
        "type": "metadata",
        "title": "Study area locator map artifact note",
        "produced_at": "2026-05-27T03:18:00Z",
        "produced_by": "urban_host_python"
    }
]
manifest["artifacts"].extend(new_artifacts)
manifest["review_status"] = "passed_with_warnings"
manifest["reviewer_notes"] = "Locator map produced with approximate broader context frame (no Shanghai boundary or river layer locally). Scalebar approximate at 31.2N."

with open(manifest_path, 'w', encoding='utf-8') as f:
    json.dump(manifest, f, indent=2, ensure_ascii=False)

print(f"Updated artifact_manifest.json ({manifest_path.stat().st_size:,} bytes)")

# 2. Update route_tree_state.json — add artifacts to RO_01 node and artifact_index
state_path = RUNDIR / "route_tree_state.json"
with open(state_path, 'r', encoding='utf-8') as f:
    state = json.load(f)

new_artifact_entries = [
    {
        "path": str(RUNDIR / "artifacts" / "s1_outcome" / "study_area_locator_map.png"),
        "type": "map",
        "title": "Study area locator map (two-panel publication layout)",
        "review_status": "reviewed"
    },
    {
        "path": str(RUNDIR / "artifacts" / "s1_outcome" / "study_area_locator_map_note.json"),
        "type": "metadata",
        "title": "Study area locator map artifact note",
        "review_status": "reviewed"
    }
]

# Add to RO_01 node artifacts
for node in state["nodes"]:
    if node["node_id"] == "RO_01_all_window_aggregate":
        node["artifacts"].extend(new_artifact_entries)
        break

# Add to artifact_index
for entry in state["artifact_index"]:
    if entry["node_id"] == "RO_01_all_window_aggregate":
        entry["artifacts"].extend(new_artifact_entries)
        break

# Update meta timestamp
state["meta"]["updated_at"] = "2026-05-27T03:20:00"

with open(state_path, 'w', encoding='utf-8') as f:
    json.dump(state, f, indent=2, ensure_ascii=False)

print(f"Updated route_tree_state.json ({state_path.stat().st_size:,} bytes)")

# 3. Update route_tree_frontend_state.json
frontend_path = RUNDIR / "route_tree_frontend_state.json"
with open(frontend_path, 'r', encoding='utf-8') as f:
    frontend = json.load(f)

# Add artifacts to RO_01 in frontend
for node in frontend.get("nodes", []):
    if node.get("node_id") == "RO_01_all_window_aggregate":
        if "artifacts" not in node:
            node["artifacts"] = []
        node["artifacts"].extend([
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
        ])
        break

# Also update the artifact_index in frontend if present
if "artifact_index" in frontend:
    for entry in frontend["artifact_index"]:
        if entry.get("node_id") == "RO_01_all_window_aggregate":
            if "artifacts" not in entry:
                entry["artifacts"] = []
            entry["artifacts"].extend([
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
            ])
            break

frontend["meta"]["updated_at"] = "2026-05-27T03:20:00"

with open(frontend_path, 'w', encoding='utf-8') as f:
    json.dump(frontend, f, indent=2, ensure_ascii=False)

print(f"Updated route_tree_frontend_state.json ({frontend_path.stat().st_size:,} bytes)")

# 4. Append event to route_tree_events.jsonl
events_path = RUNDIR / "route_tree_events.jsonl"
new_event = {
    "event_type": "attach_artifact",
    "node_id": "RO_01_all_window_aggregate",
    "artifacts": [
        str(RUNDIR / "artifacts" / "s1_outcome" / "study_area_locator_map.png"),
        str(RUNDIR / "artifacts" / "s1_outcome" / "study_area_locator_map_note.json")
    ],
    "timestamp": "2026-05-27T03:20:00",
    "actor": "main_agent",
    "note": "Publication-oriented S1 study-area locator map produced from local data canvas only. Two-panel layout with approximate broader context frame."
}

with open(events_path, 'a', encoding='utf-8') as f:
    f.write(json.dumps(new_event, ensure_ascii=False) + "\n")

print(f"Appended event to route_tree_events.jsonl")

print("\nAll updates complete.")
