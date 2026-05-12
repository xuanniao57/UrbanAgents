#!/usr/bin/env python
"""UrbanAgent Ablation Runner

批量执行 case study 消融配置，采集每个配置的评估信号。

Usage:
    cd paper4_urban_svgagent
    python scripts/run_ablation.py --case case1 --configs c0_full,c5_wo_memory
    python scripts/run_ablation.py --case case1 --configs all

Design:
    读取 case_studies/ablation_config.yaml，按 flag 组合调用 MultiAgentOrchestrator，
    将每轮运行结果存入 case_studies/<case>/runs/<config_label>/。
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
import time
import yaml
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CASE_STUDIES_DIR = PROJECT_ROOT / "case_studies"
ABLATION_CONFIG_PATH = CASE_STUDIES_DIR / "ablation_config.yaml"


def load_ablation_config() -> Dict[str, Any]:
    with open(ABLATION_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def case_runs_dir(case_id: str, case_config: Dict[str, Any]) -> Path:
    runs_dir = case_config.get("runs_dir")
    if runs_dir:
        return PROJECT_ROOT / runs_dir
    return CASE_STUDIES_DIR / case_config.get("id", case_id) / "runs"


def ensure_run_dir(case_id: str, case_config: Dict[str, Any], config_label: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = case_runs_dir(case_id, case_config) / f"{timestamp}_{config_label}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def load_task_input(case_config: Dict[str, Any]) -> Dict[str, Any]:
    prompt_file = case_config.get("prompt_file")
    if prompt_file:
        prompt_path = PROJECT_ROOT / prompt_file
        return {"question": prompt_path.read_text(encoding="utf-8")}
    input_path = PROJECT_ROOT / case_config["input_file"]
    with open(input_path, "r", encoding="utf-8") as f:
        return json.load(f)


async def run_single_ablation(
    task: Dict[str, Any],
    flags: Dict[str, bool],
    run_dir: Path,
    config_label: str,
    trial: int,
) -> Dict[str, Any]:
    """Run UrbanAgent with the given ablation flags and save results."""
    from urban_agent.agents.orchestrator import MultiAgentOrchestrator
    from urban_agent.cli import _build_exec_llm_client, _build_planner_llm_client
    from urban_agent.core import PerceptionModule, ReasoningModule

    task_payload = dict(task)
    artifact_dir = run_dir / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    task_payload["artifact_dir"] = str(artifact_dir)
    task_payload["run_dir"] = str(run_dir)

    planner_llm_client = _build_planner_llm_client()
    exec_llm_client = _build_exec_llm_client()
    vlm_client = exec_llm_client if hasattr(exec_llm_client, "analyze_image") else None

    # Build orchestrator with ablation flags
    orchestrator = MultiAgentOrchestrator(
        llm_client=exec_llm_client,
        planner_llm_client=planner_llm_client,
        vlm_client=vlm_client,
        perception_module=PerceptionModule(llm_client=exec_llm_client, vlm_client=vlm_client),
        reasoning_module=ReasoningModule(llm_client=exec_llm_client),
        interaction_mode="supervisory",
        disable_capabilities=flags.get("disable_capabilities", False),
        **{k: v for k, v in flags.items() if k != "disable_capabilities"},
    )

    print(f"  [{config_label} trial {trial}] Running with flags: {flags}")
    t0 = time.perf_counter()
    result = await orchestrator.run(task_payload)
    elapsed = time.perf_counter() - t0

    # Extract key signals
    signals = _extract_signals(result, flags, elapsed)
    signals["trial"] = trial
    signals["config_label"] = config_label

    # Save full result
    result_path = run_dir / "result.json"
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)

    # Save signals summary
    signals_path = run_dir / "signals.json"
    with open(signals_path, "w", encoding="utf-8") as f:
        json.dump(signals, f, ensure_ascii=False, indent=2)

    print(f"  [{config_label} trial {trial}] Done in {elapsed:.1f}s -> {run_dir}")
    return signals


def _extract_signals(
    result: Dict[str, Any],
    flags: Dict[str, bool],
    elapsed: float,
) -> Dict[str, Any]:
    """Extract standardized evaluation signals from a run result."""
    signals: Dict[str, Any] = {"config": flags, "elapsed_s": round(elapsed, 1)}

    # --- Gap 1 signals ---
    plan = result.get("plan", {}) if isinstance(result, dict) else {}
    subtask_results = result.get("results", {}).get("subtask_results", {}) if isinstance(result, dict) else {}
    evidence = _first_nested_dict(subtask_results, "evidence_manifest")
    artifacts = _collect_artifacts(subtask_results)
    metric_rows = _collect_metric_rows(subtask_results)
    qc = result.get("quality_control", {}) if isinstance(result, dict) else {}
    exec_qc = qc.get("exec_qc", {}) if isinstance(qc, dict) else {}
    efficiency = result.get("efficiency", {}) if isinstance(result, dict) else {}

    signals["gap1"] = {
        "evidence_manifest_present": bool(evidence),
        "disable_capabilities": flags.get("disable_capabilities", False),
        "spatial_block": {
            "bbox": bool(evidence.get("spatial", {}).get("bbox")),
            "crs": bool(evidence.get("spatial", {}).get("crs")),
            "admin_level": bool(evidence.get("spatial", {}).get("admin_level")),
        },
        "temporal_block": {
            "time_window": bool(evidence.get("temporal", {}).get("time_window")),
            "granularity": bool(evidence.get("temporal", {}).get("granularity")),
            "freshness": bool(evidence.get("temporal", {}).get("freshness")),
        },
        "population_block": {
            "target_group": bool(evidence.get("population", {}).get("target_group")),
            "affected_group": bool(evidence.get("population", {}).get("affected_group")),
        },
        "governance_block": {
            "provenance": bool(evidence.get("governance", {}).get("provenance")),
            "missing_layers": bool(evidence.get("governance", {}).get("missing_layers")),
        },
        "selected_capabilities_count": len(plan.get("capability_context", {}).get("selected_names", []) or []),
    }

    # --- Gap 2 signals ---
    review = result.get("review", {}) if isinstance(result, dict) else {}
    policy_scores = _review_policy_scores(review) if isinstance(review, dict) else {}

    signals["gap2"] = {
        "urban_validity_score": review.get("urban_validity_score"),
        "policy_scores": {
            "spatial": policy_scores.get("spatial_structural_review", {}).get("score"),
            "temporal": policy_scores.get("temporal_consistency_review", {}).get("score"),
            "population": policy_scores.get("population_and_stakeholder_review", {}).get("score"),
            "evidence": policy_scores.get("evidence_and_governance_review", {}).get("score"),
        },
        "hard_failures": review.get("hard_failures", []),
        "review_passed": review.get("passed"),
        "qc_plan_pass": qc.get("plan_passed") if isinstance(qc, dict) else None,
        "qc_exec_pass": qc.get("exec_passed") if isinstance(qc, dict) else None,
        "exec_confidence": exec_qc.get("confidence_score") if isinstance(exec_qc, dict) else None,
        "confidence_dimensions": exec_qc.get("dimension_scores", {}) if isinstance(exec_qc, dict) else {},
        "artifact_count": len(artifacts),
        "metric_row_count": len(metric_rows),
    }

    # --- Gap 3 signals ---
    runtime = result.get("results", {}).get("runtime", {}) if isinstance(result, dict) else {}
    signals["gap3"] = {
        "todos_total": len(runtime.get("todos", [])),
        "todos_completed": sum(
            1 for t in runtime.get("todos", []) if t.get("status") == "completed"
        ),
        "checkpoints_count": len(runtime.get("checkpoints", [])),
        "feedback_lessons_used": bool(
            plan.get("feedback_context", {}).get("lessons")
        ),
    }

    signals["table3"] = {
        "success": bool(result.get("status") == "success" and (qc.get("exec_passed", True) is not False)),
        "latency_s": round(float(efficiency.get("total_latency_s", elapsed)), 2),
        "est_cost_usd": _sum_efficiency_cost(efficiency),
        "exec_confidence": signals["gap2"].get("exec_confidence"),
        "review_score": review.get("urban_validity_score"),
        "warning_count": len(review.get("warnings", [])) if isinstance(review, dict) else 0,
        "hard_failure_count": len(review.get("hard_failures", [])) if isinstance(review, dict) else 0,
        "artifact_count": len(artifacts),
        "metric_row_count": len(metric_rows),
    }

    return signals


def _first_nested_dict(subtask_results: Dict[str, Any], key: str) -> Dict[str, Any]:
    for item in subtask_results.values():
        result = item.get("result", {}) if isinstance(item, dict) else {}
        if isinstance(result, dict) and isinstance(result.get(key), dict):
            return result[key]
    return {}


def _collect_artifacts(subtask_results: Dict[str, Any]) -> List[Dict[str, Any]]:
    artifacts: List[Dict[str, Any]] = []
    for item in subtask_results.values():
        result = item.get("result", {}) if isinstance(item, dict) else {}
        if isinstance(result, dict) and isinstance(result.get("artifacts"), list):
            artifacts.extend(result["artifacts"])
    return artifacts


def _collect_metric_rows(subtask_results: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in subtask_results.values():
        result = item.get("result", {}) if isinstance(item, dict) else {}
        if isinstance(result, dict) and isinstance(result.get("metric_rows"), list):
            rows.extend(result["metric_rows"])
    return rows


def _sum_efficiency_cost(efficiency: Dict[str, Any]) -> float:
    detail = efficiency.get("detail", []) if isinstance(efficiency, dict) else []
    return round(sum(float(row.get("est_cost_usd", 0.0)) for row in detail if isinstance(row, dict)), 6)


def _review_policy_scores(review: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    policy_scores = review.get("policy_scores")
    if isinstance(policy_scores, dict):
        return policy_scores
    policies = review.get("policies")
    if isinstance(policies, list):
        return {str(item.get("name")): item for item in policies if isinstance(item, dict) and item.get("name")}
    return {}


async def run_case_ablations(
    case_id: str,
    config_names: List[str],
    trials: int,
) -> List[Dict[str, Any]]:
    """Run all specified ablation configs for one case."""
    config = load_ablation_config()
    case_config = config["cases"][case_id]
    all_configs = config["configurations"]

    task = load_task_input(case_config)

    results = []
    for cfg_name in config_names:
        if cfg_name not in all_configs:
            print(f"  Warning: config '{cfg_name}' not found, skipping")
            continue

        cfg = all_configs[cfg_name]
        flags = cfg["flags"]
        for trial in range(1, trials + 1):
            run_dir = ensure_run_dir(case_id, case_config, f"{cfg_name}_t{trial}")
            signals = await run_single_ablation(task, flags, run_dir, cfg_name, trial)
            signals["config_description"] = cfg["description"]
            signals["config_display_label"] = cfg.get("label", cfg_name)
            signals["run_dir"] = str(run_dir)
            results.append(signals)

    return results


def write_table3_csv(all_signals: List[Dict[str, Any]], output_path: Path) -> None:
    rows = []
    for signal in all_signals:
        t3 = signal.get("table3", {})
        dims = signal.get("gap2", {}).get("confidence_dimensions", {}) or {}
        rows.append({
            "config": signal.get("config_label"),
            "trial": signal.get("trial"),
            "success": t3.get("success"),
            "latency_s": t3.get("latency_s"),
            "est_cost_usd": t3.get("est_cost_usd"),
            "exec_confidence": t3.get("exec_confidence"),
            "semantic_relevance": dims.get("semantic_relevance"),
            "historical_reliability": dims.get("historical_reliability"),
            "metadata_completeness": dims.get("metadata_completeness"),
            "context_alignment": dims.get("context_alignment"),
            "review_score": t3.get("review_score"),
            "warning_count": t3.get("warning_count"),
            "hard_failure_count": t3.get("hard_failure_count"),
            "artifact_count": t3.get("artifact_count"),
            "metric_row_count": t3.get("metric_row_count"),
            "run_dir": signal.get("run_dir"),
        })
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)


def write_table3_aggregate_csv(all_signals: List[Dict[str, Any]], output_path: Path) -> None:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for signal in all_signals:
        grouped.setdefault(str(signal.get("config_label")), []).append(signal)
    rows = []
    for config_label, signals in grouped.items():
        table_rows = [s.get("table3", {}) for s in signals]
        rows.append({
            "config": config_label,
            "trials": len(signals),
            "success_rate": _mean([1.0 if row.get("success") else 0.0 for row in table_rows]),
            "mean_latency_s": _mean([row.get("latency_s") for row in table_rows]),
            "mean_est_cost_usd": _mean([row.get("est_cost_usd") for row in table_rows]),
            "mean_exec_confidence": _mean([row.get("exec_confidence") for row in table_rows]),
            "mean_review_score": _mean([row.get("review_score") for row in table_rows]),
            "mean_warning_count": _mean([row.get("warning_count") for row in table_rows]),
            "mean_artifact_count": _mean([row.get("artifact_count") for row in table_rows]),
            "mean_metric_row_count": _mean([row.get("metric_row_count") for row in table_rows]),
        })
    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)


def _mean(values: List[Any]) -> Optional[float]:
    nums = [float(value) for value in values if value is not None]
    return round(sum(nums) / len(nums), 4) if nums else None


def print_summary_table(all_signals: List[Dict[str, Any]]) -> None:
    """Print a Markdown-style ablation summary table."""
    print("\n## Ablation Summary\n")
    header = "| Config | Evidence | Urban Validity | Spatial | Temporal | Population | Evidence(Gov) | Hard Fails | Artifacts | Checkpoints |"
    sep = "|---|---|---|---|---|---|---|---|---|---|"
    print(header)
    print(sep)

    for s in all_signals:
        g1 = s.get("gap1", {})
        g2 = s.get("gap2", {})
        g3 = s.get("gap3", {})
        ev = "✓" if g1.get("evidence_manifest_present") else "✗"
        uv = f'{g2.get("urban_validity_score", "N/A")}'
        sp = f'{g2.get("policy_scores", {}).get("spatial", "N/A")}'
        tm = f'{g2.get("policy_scores", {}).get("temporal", "N/A")}'
        pop = f'{g2.get("policy_scores", {}).get("population", "N/A")}'
        eg = f'{g2.get("policy_scores", {}).get("evidence", "N/A")}'
        hf = len(g2.get("hard_failures", []))
        ac = g2.get("artifact_count", 0)
        cp = g3.get("checkpoints_count", 0)

        row = f"| {s['config_label']} | {ev} | {uv} | {sp} | {tm} | {pop} | {eg} | {hf} | {ac} | {cp} |"
        print(row)

    print()


def main():
    parser = argparse.ArgumentParser(description="UrbanAgent Ablation Runner")
    parser.add_argument("--case", required=True, choices=["case1", "case2"],
                        help="Case study to run")
    parser.add_argument("--configs", default="all",
                        help="Comma-separated config names, or 'all'")
    parser.add_argument("--trials", type=int, default=3,
                        help="Trials per configuration")
    parser.add_argument("--output-csv", default=None,
                        help="Per-trial Table 3 CSV output path")
    args = parser.parse_args()

    config = load_ablation_config()
    case_config = config["cases"][args.case]
    all_configs = list(config["configurations"].keys())

    if args.configs == "all":
        config_names = all_configs
    else:
        config_names = [c.strip() for c in args.configs.split(",") if c.strip()]

    print(f"Case: {args.case}")
    print(f"Configs: {', '.join(config_names)}")
    print(f"Trials/config: {args.trials}")
    print(f"Total runs: {len(config_names) * args.trials}\n")

    signals = asyncio.run(run_case_ablations(args.case, config_names, args.trials))
    print_summary_table(signals)

    # Save aggregate summary
    output_root = case_runs_dir(args.case, case_config)
    output_root.mkdir(parents=True, exist_ok=True)
    agg_path = output_root / "ablation_summary.json"
    with open(agg_path, "w", encoding="utf-8") as f:
        json.dump(signals, f, ensure_ascii=False, indent=2)
    print(f"Aggregate summary saved to {agg_path}")

    csv_path = Path(args.output_csv) if args.output_csv else output_root / "ablation_table3_trials.csv"
    write_table3_csv(signals, csv_path)
    agg_csv_path = csv_path.with_name(csv_path.stem + "_aggregate.csv")
    write_table3_aggregate_csv(signals, agg_csv_path)
    print(f"Table 3 per-trial CSV saved to {csv_path}")
    print(f"Table 3 aggregate CSV saved to {agg_csv_path}")


if __name__ == "__main__":
    main()
