"""Read-only audit for the three-seed context-fix regression."""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


root = Path(sys.argv[1]).resolve()
rows = []
for seed_dir in sorted(root.glob("seed*")):
    match = re.match(r"seed(\d+)", seed_dir.name)
    if not match:
        continue
    seed = int(match.group(1))
    for run in sorted(path for path in seed_dir.iterdir() if path.is_dir() and (path / "runner_result.json").exists()):
        result = load(run / "runner_result.json", {})
        state = load(run / "research" / "research_state.json", {})
        turns = [load(path, {}) for path in sorted((run / "turns").glob("*/summary.json"))]
        routes = [node for node in state.get("nodes", {}).values() if node.get("nodeType") == "model_route"]
        artifacts = list(state.get("artifacts", {}).values())
        roles = {artifact.get("role") for artifact in artifacts}
        patches = state.get("pendingHumanPatches", [])
        budget_events = []
        budget_path = run / "request-budget" / "events.jsonl"
        if budget_path.exists():
            budget_events = [json.loads(line) for line in budget_path.read_text(encoding="utf-8").splitlines() if line]
        compactions = [event for event in budget_events if event.get("event") == "preflight_compaction"]
        failure = result.get("failure") or ""
        rows.append({
            "seed": seed,
            "condition": result.get("condition", run.name),
            "plan": int(len(routes) >= 3),
            "execute_commit": int({"analysis_script", "result_table"}.issubset(roles)),
            "review": int(bool(state.get("reviews"))),
            "human_patch": int(any(patch.get("status") == "applied" for patch in patches)),
            "full_protocol": int(not failure),
            "failure": failure,
            "turns": len(turns),
            "tool_calls": sum(len(turn.get("toolCalls", [])) for turn in turns),
            "final_turn_tools": len(turns[-1].get("toolCalls", [])) if turns else 0,
            "preflight_compactions": len(compactions),
            "exact_1024_summary_calls": sum(event.get("summaryCap") == 1024 for event in compactions),
            "deterministic_fallbacks": sum(bool(event.get("capped")) for event in compactions),
            "active_pending_unclassified": sum(patch.get("status") == "pending_unclassified" for patch in patches),
            "active_explicit_pending": sum(patch.get("status") == "pending" for patch in patches),
            "consumed_no_patch": sum(patch.get("status") == "consumed_no_patch" for patch in patches),
            "applied_patches": sum(patch.get("status") == "applied" for patch in patches),
            "run_dir": str(run),
        })

if not rows:
    raise SystemExit(f"No runs found under {root}")
with (root / "contextfix_audit.csv").open("w", encoding="utf-8-sig", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
print(json.dumps(rows, ensure_ascii=False, indent=2))
