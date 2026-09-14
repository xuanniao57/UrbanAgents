"""Create a stage-level audit table for the frozen multi-round workflow protocol.

This is deliberately a read-only scorer over saved state and turn records.  It
does not infer scientific quality from framework-specific tool names.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return ""


def stage_turn(run: Path, prefix: str):
    for turn in sorted((run / "turns").glob("*")):
        prompt = read_text(turn / "prompt.txt")
        if prompt.startswith(prefix):
            return turn, prompt, read_json(turn / "summary.json", {}), read_text(turn / "final_answer.txt")
    return None, "", {}, ""


def bool_int(value) -> int:
    return int(bool(value))


root = Path(sys.argv[1]).resolve()
rows = []

repeat_dirs = sorted(p for p in root.iterdir() if p.is_dir() and p.name.startswith("r"))
for repeat_dir in repeat_dirs:
    repeat = repeat_dir.name.split("_", 1)[0]
    repeat_number = int(repeat.removeprefix("r"))
    seed = read_json(repeat_dir / "plan.json", {}).get("seed")
    for run in sorted(p for p in repeat_dir.iterdir() if p.is_dir() and (p / "manifest.json").exists()):
        manifest = read_json(run / "manifest.json", {})
        result = read_json(run / "runner_result.json", {})
        state = read_json(run / "research" / "research_state.json", {})
        nodes = list(state.get("nodes", {}).values())
        route_nodes = [n for n in nodes if n.get("nodeType") == "model_route"]
        route_texts = {
            " ".join(
                [
                    str(n.get("title", "")),
                    str(n.get("summary", "")),
                    str(n.get("parameters", {}).get("analytical_role", "")),
                ]
            ).lower()
            for n in route_nodes
        }
        plan_complete = (
            len(route_nodes) >= 3
            and any("ols" in text for text in route_texts)
            and any(("fixed" in text or "固定" in text) and "gwr" in text for text in route_texts)
            and any(("adaptive" in text or "自适应" in text) and "gwr" in text for text in route_texts)
        )
        artifacts = list(state.get("artifacts", {}).values())
        artifact_roles = {a.get("role") for a in artifacts}
        execution_complete = {"analysis_script", "result_table"}.issubset(artifact_roles)
        review_complete = len(state.get("reviews", [])) > 0
        applied = [p for p in state.get("pendingHumanPatches", []) if p.get("status") == "applied"]
        human_decisions = state.get("humanDecisions", [])
        human_patch_complete = bool(applied and human_decisions)

        _, _, execution_summary, _ = stage_turn(run, "方案可以继续")
        execution_first_pass = execution_complete and execution_summary.get("outcome") == "completed"
        execution_recovery_turns = sum(
            read_text(turn / "prompt.txt").startswith("上一轮执行尚未提交完整产物")
            for turn in sorted((run / "turns").glob("*"))
        )

        _, _, exact_summary, exact_answer = stage_turn(run, "请回查刚才实际计算的文件")
        exact_readback_complete = (
            exact_summary.get("outcome") == "completed"
            and all(token in exact_answer for token in ("200", "500", "800"))
        )
        _, _, recovery_summary, recovery_answer = stage_turn(run, "请从研究记录和产物文件恢复当前进度")
        recovery_complete = (
            recovery_summary.get("outcome") == "completed"
            and "OLS" in recovery_answer
            and "GWR" in recovery_answer
        )

        turn_summaries = [read_json(p, {}) for p in sorted((run / "turns").glob("*/summary.json"))]
        request_summaries = [read_json(p, {}) for p in sorted((run / "requests").glob("*/summary.json"))]
        prompt_tokens = sum(int(r.get("usage", {}).get("prompt_tokens", 0) or 0) for r in request_summaries)
        completion_tokens = sum(int(r.get("usage", {}).get("completion_tokens", 0) or 0) for r in request_summaries)
        duration_seconds = round(sum(float(t.get("durationMs", 0)) for t in turn_summaries) / 1000, 1)
        tool_calls = sum(len(t.get("toolCalls", [])) for t in turn_summaries)
        completed_stages = sum(
            map(bool_int, [plan_complete, execution_complete, review_complete, human_patch_complete,
                           exact_readback_complete, recovery_complete])
        )
        failure = result.get("failure", "")
        if not failure:
            failure_stage = "completed"
        elif "PLAN" in failure:
            failure_stage = "planning"
        elif "commit artifacts" in failure:
            failure_stage = "execution_commit"
        elif "state recovery" in failure:
            failure_stage = "state_recovery"
        else:
            failure_stage = "other"

        rows.append({
            "repeat": repeat_number,
            "seed": result.get("seed", seed),
            "model": manifest.get("model", result.get("model", run.name.split("_", 1)[0])),
            "condition": manifest.get("condition", result.get("condition", "")),
            "plan": bool_int(plan_complete),
            "execute_commit": bool_int(execution_complete),
            "execute_first_pass": bool_int(execution_first_pass),
            "execution_recovery_turns": execution_recovery_turns,
            "review": bool_int(review_complete),
            "human_patch": bool_int(human_patch_complete),
            "exact_readback": bool_int(exact_readback_complete),
            "state_recovery": bool_int(recovery_complete),
            "stages_completed": completed_stages,
            "full_protocol": bool_int(completed_stages == 6),
            "failure_stage": failure_stage,
            "turns": len(turn_summaries),
            "tool_calls": tool_calls,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "duration_seconds": duration_seconds,
            "tree_nodes": len(nodes),
            "artifacts": len(artifacts),
            "reviews": len(state.get("reviews", [])),
            "human_decisions": len(human_decisions),
            "applied_patches": len(applied),
            "pending_questions": len(state.get("pendingQuestions", [])),
            "failure": failure,
            "run_dir": str(run),
        })

if not rows:
    raise SystemExit(f"No formal runs found under {root}")

long_path = root / "formal_stage_long.csv"
with long_path.open("w", encoding="utf-8-sig", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)

groups = defaultdict(list)
for row in rows:
    groups[(row["model"], row["condition"])].append(row)

summary_rows = []
for (model, condition), group in sorted(groups.items()):
    summary_rows.append({
        "model": model,
        "condition": condition,
        "runs": len(group),
        "plan_n": sum(r["plan"] for r in group),
        "execute_commit_n": sum(r["execute_commit"] for r in group),
        "execute_first_pass_n": sum(r["execute_first_pass"] for r in group),
        "review_n": sum(r["review"] for r in group),
        "human_patch_n": sum(r["human_patch"] for r in group),
        "exact_readback_n": sum(r["exact_readback"] for r in group),
        "state_recovery_n": sum(r["state_recovery"] for r in group),
        "full_protocol_n": sum(r["full_protocol"] for r in group),
        "mean_stages_completed": round(sum(r["stages_completed"] for r in group) / len(group), 2),
        "mean_duration_seconds": round(sum(r["duration_seconds"] for r in group) / len(group), 1),
        "mean_tool_calls": round(sum(r["tool_calls"] for r in group) / len(group), 1),
        "mean_total_tokens": round(sum(r["total_tokens"] for r in group) / len(group)),
    })

summary_path = root / "formal_stage_summary.csv"
with summary_path.open("w", encoding="utf-8-sig", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(summary_rows[0]))
    writer.writeheader()
    writer.writerows(summary_rows)

md = [
    "# Formal multi-round stage audit",
    "",
    "Each cell reports completed runs / three frozen repeats. `full` requires all six stages.",
    "",
    "| model | condition | plan | execute first pass | execute after recovery | review | human patch | exact readback | state recovery | full | mean stages /6 | mean seconds | mean tool calls | mean tokens |",
    "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
]
for row in summary_rows:
    n = row["runs"]
    md.append(
        f"| {row['model']} | {row['condition']} | {row['plan_n']}/{n} | "
        f"{row['execute_first_pass_n']}/{n} | {row['execute_commit_n']}/{n} | "
        f"{row['review_n']}/{n} | {row['human_patch_n']}/{n} | "
        f"{row['exact_readback_n']}/{n} | {row['state_recovery_n']}/{n} | "
        f"{row['full_protocol_n']}/{n} | {row['mean_stages_completed']} | "
        f"{row['mean_duration_seconds']} | {row['mean_tool_calls']} | {row['mean_total_tokens']} |"
    )
(root / "FORMAL_STAGE_REPORT.md").write_text("\n".join(md) + "\n", encoding="utf-8")

print(json.dumps({"runs": len(rows), "long": str(long_path), "summary": str(summary_path)}, indent=2))
