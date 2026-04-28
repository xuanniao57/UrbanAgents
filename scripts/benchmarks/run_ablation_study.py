"""
Systematic Ablation Study Runner — GeoAgent Table 5 等价

对 UrbanAgent 的 5 个核心组件逐一关闭，运行 UrbanWorkflowBench 全协议，
产出消融表 (paper Table ablation).

Configurations:
  FULL        — All components enabled (baseline)
  w/o Plan    — enable_planning=False
  w/o Review  — enable_review=False
  w/o QC      — enable_quality_control=False
  w/o Dual    — enable_dual_space=False
  w/o Memory  — enable_memory=False
  VANILLA     — All disabled (single-pass LLM)

Usage:
    python run_ablation_study.py --manifest <path> --output-dir artifacts/ablation
    python run_ablation_study.py --quick  # use built-in mini suite
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from urban_agent.agents.orchestrator import MultiAgentOrchestrator
from urban_agent.agents.efficiency import EfficiencyTracker
from urban_agent.evaluation.citybench_evaluator_v2 import CityBenchEvaluatorV2
from urban_agent.llm.kimi_client import KimiClient
from urban_agent.llm.qwen_client import QwenClient
from scripts.benchmarks.citydata_scoring import (
    build_safe_vanilla_prompt,
    evaluate_citydata_case,
    make_case_record,
    prediction_to_log_string,
)
from scripts.benchmarks.run_citydata_quick_benchmark import CityDataQuickSampler, CITYDATA_ROOT, load_env_file

OUTPUT_DIR = ROOT / "artifacts" / "ablation"

# ---------------------------------------------------------------------------
# Ablation configurations (GeoAgent Table 5 style)
# ---------------------------------------------------------------------------

ABLATION_CONFIGS: Dict[str, Dict[str, bool]] = {
    "FULL": {
        "enable_planning": True,
        "enable_review": True,
        "enable_quality_control": True,
        "enable_dual_space": True,
        "enable_memory": True,
    },
    "w/o Planning": {
        "enable_planning": False,
        "enable_review": True,
        "enable_quality_control": True,
        "enable_dual_space": True,
        "enable_memory": True,
    },
    "w/o Review": {
        "enable_planning": True,
        "enable_review": False,
        "enable_quality_control": True,
        "enable_dual_space": True,
        "enable_memory": True,
    },
    "w/o QC": {
        "enable_planning": True,
        "enable_review": True,
        "enable_quality_control": False,
        "enable_dual_space": True,
        "enable_memory": True,
    },
    "w/o DualSpace": {
        "enable_planning": True,
        "enable_review": True,
        "enable_quality_control": True,
        "enable_dual_space": False,
        "enable_memory": True,
    },
    "w/o Memory": {
        "enable_planning": True,
        "enable_review": True,
        "enable_quality_control": True,
        "enable_dual_space": True,
        "enable_memory": False,
    },
    "VANILLA": {
        "enable_planning": False,
        "enable_review": False,
        "enable_quality_control": False,
        "enable_dual_space": False,
        "enable_memory": False,
    },
}


def build_llm_client(provider: str) -> Optional[Any]:
    if provider == "none":
        return None
    if provider == "qwen":
        return QwenClient()
    if provider == "kimi":
        return KimiClient(client_type="standard")
    raise ValueError(f"Unsupported provider: {provider}")


async def run_vanilla_llm(task: Dict[str, Any], task_type: str, llm_client: Any) -> Dict[str, Any]:
    prompt = build_safe_vanilla_prompt(task, task_type)

    if llm_client is not None and hasattr(llm_client, "generate"):
        response = await llm_client.generate(prompt, temperature=0.2, max_tokens=900)
        answer = response if isinstance(response, str) else str(response)
        if isinstance(answer, str) and answer.strip().lower().startswith("error:"):
            raise RuntimeError(answer)
    else:
        answer = f"[vanilla_mock] {task.get('question', task_type)}"

    return {
        "final_answer": answer,
        "trace_id": f"vanilla_{task_type}_{datetime.now().strftime('%H%M%S')}",
        "results": {"completed": 1},
        "efficiency": {"total_latency_s": 0},
    }


def provider_available(provider: str) -> bool:
    if provider == "none":
        return True
    if provider == "qwen":
        return bool(os.getenv("QWEN_API_KEY"))
    if provider == "kimi":
        return bool(os.getenv("KIMI_API_KEY"))
    return False

# ---------------------------------------------------------------------------
# Built-in mini-suite (quick mode — no manifest needed)
# ---------------------------------------------------------------------------

MINI_SUITE: List[Dict[str, Any]] = [
    {
        "case_id": "ablation_geoqa_01",
        "task_type": "geoqa",
        "task": {"question": "What is the capital of France?", "choices": {"A": "London", "B": "Paris", "C": "Berlin", "D": "Rome"}},
        "ground_truth": "B",
    },
    {
        "case_id": "ablation_traffic_01",
        "task_type": "traffic_signal",
        "task": {"question": "Rank the following signal phases by priority", "phase_options": [
            {"option": "A", "waiting_vehicle_count": 15, "vehicle_count": 30, "lane_count": 2},
            {"option": "B", "waiting_vehicle_count": 5, "vehicle_count": 10, "lane_count": 1},
        ]},
        "ground_truth": "A",
    },
    {
        "case_id": "ablation_pop_01",
        "task_type": "population_prediction",
        "task": {"question": "Estimate population for district with nightlight=120, carbon=85", "indicator_values": {"nightlight": 120, "carbon": 85}},
        "ground_truth": 50000,
    },
    {
        "case_id": "ablation_nav_01",
        "task_type": "outdoor_navigation",
        "task": {"question": "Navigate from A to B", "predicted_actions": ["turn_left", "go_straight", "turn_right"]},
        "ground_truth": ["turn_left", "go_straight", "turn_right"],
    },
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def run_single_config(
    config_name: str,
    flags: Dict[str, bool],
    cases: List[Dict[str, Any]],
    llm_client: Optional[Any] = None,
    use_citydata_scoring: bool = False,
) -> Dict[str, Any]:
    """Run all cases under one ablation configuration."""
    tracker = EfficiencyTracker()
    evaluator = CityBenchEvaluatorV2()

    orchestrator = None if config_name == "VANILLA" else MultiAgentOrchestrator(
        llm_client=llm_client,
        **flags,
    )

    results = []
    for case in cases:
        case_id = case["case_id"]
        task_type = case["task_type"]
        task = case["task"]
        ground_truth = case.get("ground_truth")

        start = time.perf_counter()
        try:
            if config_name == "VANILLA":
                output = await run_vanilla_llm(task, task_type, llm_client)
            else:
                output = await orchestrator.run(task=task, task_type=task_type)
            latency = time.perf_counter() - start

            if use_citydata_scoring:
                prediction, eval_result = evaluate_citydata_case(
                    case,
                    output,
                    is_bare_model=(config_name == "VANILLA"),
                )
            else:
                prediction = output.get("final_answer", "")
                eval_result = evaluator.evaluate_task(
                    task_type=task_type,
                    prediction=prediction,
                    ground_truth=ground_truth,
                    agent_output=output,
                    is_bare_model=(config_name == "VANILLA"),
                )
            task_score = eval_result.get("task_outcome", {}).get("accuracy", eval_result.get("overall_score", 0))

            results.append({
                "case_id": case_id,
                "task_type": task_type,
                "config": config_name,
                "prediction": prediction_to_log_string(prediction)[:200],
                "score": task_score,
                "evaluation": eval_result,
                "latency_s": round(latency, 3),
                "efficiency": output.get("efficiency", {}),
                "qc": output.get("quality_control", {}),
                "status": "success",
            })
        except Exception as e:
            results.append({
                "case_id": case_id,
                "task_type": task_type,
                "config": config_name,
                "status": "error",
                "error": str(e)[:200],
                "score": 0,
                "latency_s": round(time.perf_counter() - start, 3),
            })

    # Aggregate
    scores = [r["score"] for r in results if r["status"] == "success"]
    avg_score = sum(scores) / len(scores) if scores else 0
    avg_latency = sum(r["latency_s"] for r in results) / len(results) if results else 0

    return {
        "config": config_name,
        "flags": flags,
        "num_cases": len(cases),
        "num_success": sum(1 for r in results if r["status"] == "success"),
        "avg_score": round(avg_score, 4),
        "avg_latency_s": round(avg_latency, 3),
        "per_task_type": _aggregate_by_task_type(results),
        "details": results,
    }


def _aggregate_by_task_type(results: List[Dict]) -> Dict[str, Dict]:
    from collections import defaultdict
    by_type: Dict[str, List[Dict]] = defaultdict(list)
    for r in results:
        by_type[r["task_type"]].append(r)

    agg = {}
    for tt, recs in sorted(by_type.items()):
        scores = [r["score"] for r in recs if r["status"] == "success"]
        agg[tt] = {
            "count": len(recs),
            "avg_score": round(sum(scores) / len(scores), 4) if scores else 0,
            "success_rate": round(sum(1 for r in recs if r["status"] == "success") / len(recs), 4),
        }
    return agg


async def run_full_ablation(
    cases: List[Dict[str, Any]],
    configs: Optional[Dict[str, Dict[str, bool]]] = None,
    llm_client: Optional[Any] = None,
    use_citydata_scoring: bool = False,
) -> Dict[str, Any]:
    """Run all ablation configurations and produce summary table."""
    configs = configs or ABLATION_CONFIGS
    all_results = {}

    for config_name, flags in configs.items():
        print(f"\n{'='*60}")
        print(f"Running ablation config: {config_name}")
        print(f"  Flags: {flags}")
        print(f"{'='*60}")
        result = await run_single_config(
            config_name,
            flags,
            cases,
            llm_client,
            use_citydata_scoring=use_citydata_scoring,
        )
        all_results[config_name] = result
        print(f"  → avg_score={result['avg_score']}, avg_latency={result['avg_latency_s']}s")

    # Build comparison table (GeoAgent Table 5 format)
    table = build_ablation_table(all_results)

    return {
        "timestamp": datetime.now().isoformat(),
        "num_configs": len(configs),
        "num_cases_per_config": len(cases),
        "table": table,
        "configs": all_results,
    }


def build_ablation_table(all_results: Dict[str, Dict]) -> List[Dict[str, Any]]:
    """Build paper-ready ablation table."""
    full_score = all_results.get("FULL", {}).get("avg_score", 0)
    rows = []
    for config_name, result in all_results.items():
        delta = result["avg_score"] - full_score if config_name != "FULL" else 0
        rows.append({
            "Configuration": config_name,
            "Avg Score": result["avg_score"],
            "Δ vs Full": round(delta, 4),
            "Δ% vs Full": f"{delta / full_score * 100:+.1f}%" if full_score > 0 else "N/A",
            "Avg Latency (s)": result["avg_latency_s"],
            "Success Rate": result["num_success"] / result["num_cases"] if result["num_cases"] > 0 else 0,
        })
    return rows


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Systematic Ablation Study")
    parser.add_argument("--manifest", type=str, default=None, help="Path to UrbanWorkflowBench manifest JSON")
    parser.add_argument("--quick", action="store_true", help="Use built-in mini suite (no LLM needed)")
    parser.add_argument("--citydata-suite", action="store_true", help="Use CityData direct 8-task suite")
    parser.add_argument("--sample-count", type=int, default=10, help="Per-task sample count for CityData suite")
    parser.add_argument("--provider", choices=["none", "qwen", "kimi"], default="none")
    parser.add_argument("--strict-provider", action="store_true")
    parser.add_argument("--output-dir", type=str, default=str(OUTPUT_DIR))
    parser.add_argument("--configs", nargs="*", default=None, help="Subset of config names to run")
    return parser.parse_args()


def _citydata_cases(sample_count: int) -> List[Dict[str, Any]]:
    sampler = CityDataQuickSampler(CITYDATA_ROOT)
    suite = sampler.build_suite(sample_count)
    cases: List[Dict[str, Any]] = []
    for task_type, tasks in suite.items():
        for index, task in enumerate(tasks, start=1):
            cases.append(make_case_record(
                case_id=f"{task_type}_{index}",
                task_type=task_type,
                task=task,
                ground_truth=task.get("ground_truth"),
                ground_truth_option=task.get("ground_truth_option"),
                ground_truth_destination=task.get("ground_truth_destination"),
            ))
    return cases


def load_cases(manifest_path: Optional[str], citydata_suite: bool = False, sample_count: int = 10) -> List[Dict[str, Any]]:
    if citydata_suite:
        return _citydata_cases(sample_count)
    if manifest_path is None:
        return MINI_SUITE
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    cases: List[Dict[str, Any]] = []
    if isinstance(manifest.get("cases"), list):
        for case in manifest["cases"]:
            task = case.get("task", case)
            task_type = task.get("task_type") or case.get("task_type")
            if not task_type:
                continue
            cases.append(make_case_record(
                case_id=case.get("case_id", case.get("id", "")),
                task_type=task_type,
                task=task,
                ground_truth=case.get("ground_truth", case.get("evaluation", {}).get("expected")),
                ground_truth_option=case.get("ground_truth_option"),
                ground_truth_destination=case.get("ground_truth_destination"),
            ))
        return cases

    for suite in manifest.get("suites", []):
        for case in suite.get("cases", []):
            task = case.get("task", case)
            task_type = case.get("task_type", suite.get("task_type", "geoqa"))
            cases.append(make_case_record(
                case_id=case.get("case_id", case.get("id", "")),
                task_type=task_type,
                task=task,
                ground_truth=case.get("ground_truth", case.get("evaluation", {}).get("expected")),
                ground_truth_option=case.get("ground_truth_option"),
                ground_truth_destination=case.get("ground_truth_destination"),
            ))
    return cases


def main() -> None:
    args = parse_args()
    load_env_file()
    cases = MINI_SUITE if args.quick else load_cases(args.manifest, args.citydata_suite, args.sample_count)

    if not provider_available(args.provider):
        message = {"provider": args.provider, "reason": "missing API key"}
        if args.strict_provider:
            raise RuntimeError(f"Provider unavailable: {message}")
        print(f"Provider unavailable, falling back to none: {message}")
        args.provider = "none"

    llm_client = build_llm_client(args.provider)

    configs = ABLATION_CONFIGS
    if args.configs:
        configs = {k: v for k, v in ABLATION_CONFIGS.items() if k in args.configs}

    print(f"Ablation study: {len(configs)} configs × {len(cases)} cases")

    result = asyncio.run(
        run_full_ablation(
            cases,
            configs,
            llm_client=llm_client,
            use_citydata_scoring=bool(args.citydata_suite),
        )
    )
    result["provider"] = args.provider
    result["sample_count"] = args.sample_count if args.citydata_suite else None
    result["citydata_suite"] = bool(args.citydata_suite)

    # Save
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"ablation_results_{ts}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nResults saved to {out_path}")

    # Print table
    print(f"\n{'='*80}")
    print("ABLATION TABLE (GeoAgent Table 5 format)")
    print(f"{'='*80}")
    header = f"{'Configuration':<20} {'Avg Score':>10} {'Δ vs Full':>10} {'Δ%':>8} {'Latency(s)':>11} {'Success':>8}"
    print(header)
    print("-" * 80)
    for row in result["table"]:
        line = f"{row['Configuration']:<20} {row['Avg Score']:>10.4f} {row['Δ vs Full']:>10.4f} {row['Δ% vs Full']:>8} {row['Avg Latency (s)']:>11.3f} {row['Success Rate']:>8.2%}"
        print(line)


if __name__ == "__main__":
    main()
