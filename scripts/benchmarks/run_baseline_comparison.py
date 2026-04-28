"""
External Baseline Comparison Runner

对标 GeoAgent Table 3 / GeoJSON Agents Table 7 的基线对比方法:
1. Vanilla LLM (direct prompting, no agent framework)
2. Single-Agent (UrbanAgent core without multi-agent orchestration)
3. UrbanAgent Full (multi-agent with all layers)

同时对标 GeoJSON Agents 的两种工具使用策略:
a. Function Calling (tool-use mode)
b. Code Generation (code-gen mode)

Usage:
    python run_baseline_comparison.py --manifest <path> --models gpt-4o,deepseek-v3
    python run_baseline_comparison.py --quick
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
from urban_agent.evaluation.citybench_evaluator_v2 import CityBenchEvaluatorV2
from urban_agent.llm.kimi_client import KimiClient
from urban_agent.llm.qwen_client import QwenClient
from urban_agent.task_agent import UrbanTaskAgent
from scripts.benchmarks.citydata_scoring import (
    build_safe_vanilla_prompt,
    evaluate_citydata_case,
    make_case_record,
    prediction_to_log_string,
)
from scripts.benchmarks.run_citydata_quick_benchmark import CityDataQuickSampler, CITYDATA_ROOT, load_env_file

OUTPUT_DIR = ROOT / "artifacts" / "baselines"

# ---------------------------------------------------------------------------
# Baseline configurations
# ---------------------------------------------------------------------------

BASELINE_CONFIGS = {
    "Vanilla LLM": {
        "type": "vanilla",
        "description": "Direct LLM prompting without agent framework",
    },
    "Single-Agent": {
        "type": "single_agent",
        "description": "UrbanAgent core pipeline (perceive→reason→act) without multi-agent",
    },
    "UrbanAgent (Full)": {
        "type": "multi_agent",
        "description": "Full 4-layer multi-agent orchestration",
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


def provider_available(provider: str) -> bool:
    if provider == "none":
        return True
    if provider == "qwen":
        return bool(os.getenv("QWEN_API_KEY"))
    if provider == "kimi":
        return bool(os.getenv("KIMI_API_KEY"))
    return False


# ---------------------------------------------------------------------------
# Vanilla LLM baseline
# ---------------------------------------------------------------------------

async def run_vanilla_llm(
    task: Dict[str, Any],
    task_type: str,
    llm_client: Any,
) -> Dict[str, Any]:
    """
    Vanilla LLM: direct prompting without any agent framework.
    Same as GeoAgent's 'Direct Prompting' and GeoJSON Agents' 'Baseline'.
    """
    prompt = _build_vanilla_prompt(task, task_type)

    if llm_client is not None and hasattr(llm_client, "generate"):
        response = await llm_client.generate(prompt, temperature=0.2, max_tokens=900)
        answer = response if isinstance(response, str) else str(response)
        if isinstance(answer, str) and answer.strip().lower().startswith("error:"):
            raise RuntimeError(answer)
    else:
        # Mock for dry-run
        answer = f"[vanilla_mock] {task.get('question', str(task)[:100])}"

    return {
        "final_answer": answer,
        "trace_id": f"vanilla_{task_type}_{datetime.now().strftime('%H%M%S')}",
        "results": {"completed": 1},
        "efficiency": {"total_latency_s": 0},
    }


def _build_vanilla_prompt(task: Dict[str, Any], task_type: str) -> str:
    """Build a direct prompt without agent scaffolding."""
    return build_safe_vanilla_prompt(task, task_type)


# ---------------------------------------------------------------------------
# Single-Agent baseline
# ---------------------------------------------------------------------------

async def run_single_agent(
    task: Dict[str, Any],
    task_type: str,
    llm_client: Any,
) -> Dict[str, Any]:
    """
    Single-Agent: UrbanAgent core (perceive→reason→act) without multi-agent
    orchestration layers. Equivalent to disabling Planning + Review + QC.
    """
    agent = UrbanTaskAgent(
        llm_client=llm_client,
        vlm_client=llm_client,
        config={
            "reasoning": {"mode": "legacy"},
            "action": {"tool_runtime": "legacy"},
            "enable_memory": True,
        },
    )
    return await agent.execute_task(task=task, task_type=task_type)


# ---------------------------------------------------------------------------
# Full Agent
# ---------------------------------------------------------------------------

async def run_full_agent(
    task: Dict[str, Any],
    task_type: str,
    llm_client: Any,
) -> Dict[str, Any]:
    """Full 4-layer multi-agent orchestration."""
    orchestrator = MultiAgentOrchestrator(llm_client=llm_client)
    return await orchestrator.run(task=task, task_type=task_type)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

RUNNERS = {
    "Vanilla LLM": run_vanilla_llm,
    "Single-Agent": run_single_agent,
    "UrbanAgent (Full)": run_full_agent,
}


async def run_baseline_comparison(
    cases: List[Dict[str, Any]],
    llm_client: Optional[Any] = None,
    configs: Optional[List[str]] = None,
    use_citydata_scoring: bool = False,
) -> Dict[str, Any]:
    """Run all baseline configurations on all cases."""
    config_names = configs or list(BASELINE_CONFIGS.keys())
    evaluator = CityBenchEvaluatorV2()
    all_results: Dict[str, Any] = {}

    for config_name in config_names:
        runner = RUNNERS[config_name]
        print(f"\n{'='*60}")
        print(f"Running baseline: {config_name}")
        print(f"  {BASELINE_CONFIGS[config_name]['description']}")
        print(f"{'='*60}")

        results = []
        for case in cases:
            case_id = case["case_id"]
            task_type = case["task_type"]
            task = case["task"]
            ground_truth = case.get("ground_truth")

            start = time.perf_counter()
            try:
                output = await runner(task, task_type, llm_client)
                latency = time.perf_counter() - start

                is_bare = (config_name == "Vanilla LLM")
                if use_citydata_scoring:
                    prediction, eval_result = evaluate_citydata_case(case, output, is_bare_model=is_bare)
                else:
                    prediction = output.get("final_answer", "")
                    eval_result = evaluator.evaluate_task(
                        task_type=task_type,
                        prediction=prediction,
                        ground_truth=ground_truth,
                        agent_output=output,
                        is_bare_model=is_bare,
                    )
                task_score = eval_result.get("task_outcome", {}).get("accuracy", eval_result.get("overall_score", 0))

                results.append({
                    "case_id": case_id,
                    "task_type": task_type,
                    "baseline": config_name,
                    "prediction": prediction_to_log_string(prediction)[:200],
                    "score": task_score,
                    "evaluation": eval_result,
                    "latency_s": round(latency, 3),
                    "status": "success",
                })
            except Exception as e:
                results.append({
                    "case_id": case_id,
                    "task_type": task_type,
                    "baseline": config_name,
                    "status": "error",
                    "error": str(e)[:200],
                    "score": 0,
                    "latency_s": round(time.perf_counter() - start, 3),
                })

        scores = [r["score"] for r in results if r["status"] == "success"]
        all_results[config_name] = {
            "num_cases": len(cases),
            "num_success": sum(1 for r in results if r["status"] == "success"),
            "avg_score": round(sum(scores) / len(scores), 4) if scores else 0,
            "avg_latency_s": round(sum(r["latency_s"] for r in results) / len(results), 3) if results else 0,
            "per_task_type": _aggregate_by_task_type(results),
            "details": results,
        }
        print(f"  → avg_score={all_results[config_name]['avg_score']}")

    # Build comparison table (GeoAgent Table 3 format)
    table = _build_comparison_table(all_results)

    return {
        "timestamp": datetime.now().isoformat(),
        "num_baselines": len(config_names),
        "num_cases": len(cases),
        "table": table,
        "baselines": all_results,
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
        }
    return agg


def _build_comparison_table(all_results: Dict[str, Dict]) -> List[Dict[str, Any]]:
    """Build paper-ready comparison table (GeoAgent Table 3 format)."""
    # Collect all task types
    all_types: set = set()
    for res in all_results.values():
        all_types.update(res.get("per_task_type", {}).keys())

    rows = []
    for config_name, res in all_results.items():
        row: Dict[str, Any] = {
            "Method": config_name,
            "Overall": res["avg_score"],
        }
        for tt in sorted(all_types):
            row[tt] = res.get("per_task_type", {}).get(tt, {}).get("avg_score", 0)
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

MINI_SUITE = [
    {
        "case_id": "baseline_geoqa_01",
        "task_type": "geoqa",
        "task": {"question": "What is the capital of France?", "choices": {"A": "London", "B": "Paris", "C": "Berlin", "D": "Rome"}},
        "ground_truth": "B",
    },
    {
        "case_id": "baseline_traffic_01",
        "task_type": "traffic_signal",
        "task": {"question": "Rank signal phases", "phase_options": [
            {"option": "A", "waiting_vehicle_count": 15, "vehicle_count": 30, "lane_count": 2},
            {"option": "B", "waiting_vehicle_count": 5, "vehicle_count": 10, "lane_count": 1},
        ]},
        "ground_truth": "A",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="External Baseline Comparison")
    parser.add_argument("--manifest", type=str, default=None)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--citydata-suite", action="store_true", help="Use CityData direct 8-task suite")
    parser.add_argument("--sample-count", type=int, default=10, help="Per-task sample count for CityData suite")
    parser.add_argument("--provider", choices=["none", "qwen", "kimi"], default="none")
    parser.add_argument("--strict-provider", action="store_true")
    parser.add_argument("--output-dir", type=str, default=str(OUTPUT_DIR))
    parser.add_argument("--configs", nargs="*", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_env_file()
    cases = MINI_SUITE if args.quick else _load_cases(args.manifest, args.citydata_suite, args.sample_count)
    configs = args.configs

    if not provider_available(args.provider):
        message = {"provider": args.provider, "reason": "missing API key"}
        if args.strict_provider:
            raise RuntimeError(f"Provider unavailable: {message}")
        print(f"Provider unavailable, falling back to none: {message}")
        args.provider = "none"

    llm_client = build_llm_client(args.provider)

    result = asyncio.run(
        run_baseline_comparison(
            cases,
            llm_client=llm_client,
            configs=configs,
            use_citydata_scoring=bool(args.citydata_suite),
        )
    )
    result["provider"] = args.provider
    result["sample_count"] = args.sample_count if args.citydata_suite else None
    result["citydata_suite"] = bool(args.citydata_suite)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"baseline_results_{ts}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nResults saved to {out_path}")

    # Print table
    print(f"\n{'='*80}")
    print("BASELINE COMPARISON TABLE (GeoAgent Table 3 format)")
    print(f"{'='*80}")
    if result["table"]:
        header_keys = list(result["table"][0].keys())
        header = "  ".join(f"{k:<15}" for k in header_keys)
        print(header)
        print("-" * 80)
        for row in result["table"]:
            vals = []
            for k in header_keys:
                v = row[k]
                vals.append(f"{v:<15}" if isinstance(v, str) else f"{v:<15.4f}")
            print("  ".join(vals))


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


def _manifest_cases(manifest_path: str) -> List[Dict[str, Any]]:
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
                case_id=case.get("case_id", ""),
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
                case_id=case.get("case_id", ""),
                task_type=task_type,
                task=task,
                ground_truth=case.get("ground_truth", case.get("evaluation", {}).get("expected")),
                ground_truth_option=case.get("ground_truth_option"),
                ground_truth_destination=case.get("ground_truth_destination"),
            ))
    return cases


def _load_cases(manifest_path: Optional[str], citydata_suite: bool, sample_count: int) -> List[Dict[str, Any]]:
    if citydata_suite:
        return _citydata_cases(sample_count)
    if manifest_path is None:
        return MINI_SUITE
    return _manifest_cases(manifest_path)


if __name__ == "__main__":
    main()
