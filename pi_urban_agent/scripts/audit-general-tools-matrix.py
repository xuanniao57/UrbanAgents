#!/usr/bin/env python3
"""Audit a general-tools Urban/Pi matrix without trusting model prose."""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path


def load(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def valid_ols_csv(path: Path) -> tuple[bool, int]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if not rows:
            return False, 0
        keys = {key.lower(): key for key in rows[0]}
        scale_key = next((keys[k] for k in ("scale_m", "scale", "support_m") if k in keys), None)
        r2_key = next((keys[k] for k in ("r2_in_sample", "r2_insample", "r_squared", "r2") if k in keys), None)
        if not scale_key or not r2_key:
            return False, 0
        scales = {int(float(row[scale_key])) for row in rows if row.get(scale_key)}
        for row in rows:
            float(row[r2_key])
        return scales == {200, 300, 400, 500, 600, 700, 800}, len(scales)
    except Exception:
        return False, 0


def main() -> None:
    root = Path(sys.argv[1]).resolve()
    records = []
    for run in sorted(path for path in root.iterdir() if path.is_dir() and (path / "workspace").exists()):
        calls: Counter[str] = Counter()
        turn_outcomes = []
        durations = 0
        errors = 0
        for summary_path in sorted((run / "turns").glob("*/summary.json")):
            summary = load(summary_path, {})
            turn_outcomes.append(summary.get("outcome"))
            durations += int(summary.get("durationMs") or 0)
            errors += len(summary.get("toolErrors") or [])
            calls.update(item.get("toolName") for item in summary.get("toolCalls") or [] if item.get("toolName"))
        state = load(run / "research" / "research_state.json", {})
        work = list((run / "workspace" / "work").glob("**/*"))
        work = [path for path in work if path.is_file()]
        outputs = list((run / "workspace" / "outputs").glob("**/*"))
        outputs = [path for path in outputs if path.is_file()]
        csv_audits = [valid_ols_csv(path) for path in outputs if path.suffix.lower() == ".csv"]
        valid = any(item[0] for item in csv_audits)
        records.append({
            "run": run.name,
            "turns_completed": sum(value == "completed" for value in turn_outcomes),
            "turns_failed": sum(value == "failed" for value in turn_outcomes),
            "duration_s": round(durations / 1000, 3),
            "tool_calls": sum(calls.values()),
            "tool_errors": errors,
            "read_calls": calls["read"],
            "bash_calls": calls["bash"],
            "write_edit_calls": calls["write"] + calls["edit"],
            "state_recall_calls": calls["urban_state"] + calls["urban_recall"],
            "branch_calls": calls["urban_open_branch"],
            "attach_calls": calls["urban_attach_evidence"],
            "review_calls": calls["urban_record_review"],
            "human_calls": calls["urban_human_decision"],
            "work_files": len(work),
            "output_files": len(outputs),
            "valid_seven_scale_ols": valid,
            "max_scales_in_output": max((item[1] for item in csv_audits), default=0),
            "tree_nodes": len(state.get("nodes") or {}),
            "artifacts": len(state.get("artifacts") or {}),
            "reviews": len(state.get("reviews") or []),
            "human_decisions": len(state.get("humanDecisions") or []),
            "phase": state.get("phase"),
        })
    fieldnames = list(records[0]) if records else []
    with (root / "general_tools_audit.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    (root / "general_tools_audit.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(records, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
