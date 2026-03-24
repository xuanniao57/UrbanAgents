"""
Stage 2: 时空记忆增量消融实验 (Temporal Memory Ablation)

验证 v3 新增时空组件各自的贡献：
- C1: TemporalContext (结构化时间元数据)
- C2: ACT-R activation (时空激活度模型)
- C3: temporal_match (多粒度时间匹配)
- C4: MemoryReflector (反思压缩)
- C5: TemporalPatternDetector (周期模式检测)

9 个实验条件 (A0-A8):
  A0 = Full Model (all on)
  A1 = w/o TemporalContext
  A2 = w/o ACT-R
  A3 = w/o TemporalMatch
  A4 = w/o Reflector
  A5 = w/o PatternDetector
  A6 = w/o AllTemporal (C1+C3+C5 off)
  A7 = Baseline (v2 memory, all off)
  A8 = No Memory

用法:
  python run_memory_ablation.py --provider none --sample-count 3   # 冒烟
  python run_memory_ablation.py --provider qwen --sample-count 10  # 正式
  python run_memory_ablation.py --provider qwen --conditions A0,A7,A8  # 选跑
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.benchmarks.run_citydata_quick_benchmark import (
    CityDataQuickSampler,
    QuickBenchmarkRunner,
    build_agent,
    load_env_file,
    to_jsonable,
    CITYDATA_ROOT,
    RANDOM_SEED,
)
from scripts.benchmarks.run_urbanworkflowbench_v1_1 import (
    evaluate_memory_probe,
)
from urban_agent.core.memory import MemoryModule, TemporalContext, _tc_from_any
from urban_agent.core.reasoning import ReasoningModule

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def setup_file_logging(logfile: Path) -> None:
    """Add a file handler to root logger so all output goes to logfile too."""
    logfile.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(logfile, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logging.getLogger().addHandler(fh)


def save_checkpoint(path: Path, data: Dict[str, Any]) -> None:
    """Atomically save incremental checkpoint."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    logger.info("Checkpoint saved → %s", path)

RESULTS_DIR = ROOT / "artifacts" / "benchmarks"
TEMPORAL_PROBE_PATH = RESULTS_DIR / "temporal_memory_probe_cases.json"
UWB_V12_MANIFEST = RESULTS_DIR / "urbanworkflowbench_v1_2_manifest_latest.json"

MEMORY_SENSITIVE_TASKS = {"mobility_prediction", "traffic_signal", "outdoor_navigation", "urban_exploration"}
MEMORY_INSENSITIVE_TASKS = {"population_prediction", "object_detection", "geolocation", "geoqa"}


# ── Ablation Config ───────────────────────────────────────────────

@dataclass
class MemoryAblationConfig:
    """Controls which v3 temporal components are enabled."""
    enable_temporal_context: bool = True     # C1
    enable_actr_activation: bool = True      # C2
    enable_temporal_match: bool = True        # C3
    enable_reflector: bool = True             # C4
    enable_pattern_detector: bool = True      # C5
    enable_memory: bool = True                # total switch


CONDITIONS: Dict[str, MemoryAblationConfig] = {
    "A0_full": MemoryAblationConfig(),
    "A1_no_tc": MemoryAblationConfig(enable_temporal_context=False),
    "A2_no_actr": MemoryAblationConfig(enable_actr_activation=False),
    "A3_no_tmatch": MemoryAblationConfig(enable_temporal_match=False),
    "A4_no_reflector": MemoryAblationConfig(enable_reflector=False),
    "A5_no_pattern": MemoryAblationConfig(enable_pattern_detector=False),
    "A6_no_all_temporal": MemoryAblationConfig(
        enable_temporal_context=False,
        enable_temporal_match=False,
        enable_pattern_detector=False,
    ),
    "A7_baseline_memory": MemoryAblationConfig(
        enable_temporal_context=False,
        enable_actr_activation=False,
        enable_temporal_match=False,
        enable_reflector=False,
        enable_pattern_detector=False,
    ),
    "A8_no_memory": MemoryAblationConfig(enable_memory=False),
}


def ablation_config_to_agent_config(ac: MemoryAblationConfig) -> Dict[str, Any]:
    """Build UrbanAgent config dict from ablation config."""
    cfg: Dict[str, Any] = {
        "reasoning": {"mode": "enhanced"},
        "action": {"tool_runtime": "mcp"},
        "enable_memory": ac.enable_memory,
    }
    if ac.enable_memory:
        cfg["memory"] = {
            "enable_temporal_context": ac.enable_temporal_context,
            "enable_actr_activation": ac.enable_actr_activation,
            "enable_temporal_match": ac.enable_temporal_match,
            "enable_reflector": ac.enable_reflector,
            "enable_pattern_detector": ac.enable_pattern_detector,
        }
    return cfg


# ── CityBench ablation ───────────────────────────────────────────

async def run_citybench_for_condition(
    cond_name: str,
    ac: MemoryAblationConfig,
    provider: str,
    suite: Dict,
) -> Dict[str, Any]:
    """Run CityBench suite under one ablation condition."""
    agent_cfg = ablation_config_to_agent_config(ac)
    agent = await build_agent(provider, agent_cfg)

    # Inject ablation flags into existing MemoryModule
    if ac.enable_memory and hasattr(agent, "memory") and agent.memory is not None:
        agent.memory.enable_temporal_context = ac.enable_temporal_context
        agent.memory.enable_actr_activation = ac.enable_actr_activation
        agent.memory.enable_temporal_match = ac.enable_temporal_match
        agent.memory.enable_reflector = ac.enable_reflector
        agent.memory.enable_pattern_detector = ac.enable_pattern_detector

    runner = QuickBenchmarkRunner(suite)
    return await runner.run(cond_name, agent)


async def run_citybench_ablation(
    provider: str,
    sample_count: int,
    condition_names: List[str],
    parallel: int = 1,
) -> Dict[str, Any]:
    """Run CityBench ablation across specified conditions.

    Args:
        parallel: max number of conditions to run concurrently.
    """
    sampler = CityDataQuickSampler(CITYDATA_ROOT, seed=RANDOM_SEED)
    suite = sampler.build_suite(sample_count)

    results: Dict[str, Any] = {}
    checkpoint_path = RESULTS_DIR / "citybench_checkpoint.json"

    # Resume: load existing checkpoint
    if checkpoint_path.exists():
        try:
            existing = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            results.update(existing)
            logger.info("Resumed %d conditions from checkpoint: %s", len(existing), list(existing.keys()))
        except Exception:
            pass

    # Filter out already-completed conditions
    remaining = [c for c in condition_names if c not in results]
    if remaining:
        logger.info("CityBench remaining: %s", remaining)
    else:
        logger.info("All CityBench conditions already in checkpoint, skipping.")

    if parallel <= 1:
        # Sequential (original behaviour)
        for cond_name in remaining:
            ac = CONDITIONS[cond_name]
            logger.info("── CityBench: %s ──", cond_name)
            run_result = await run_citybench_for_condition(cond_name, ac, provider, suite)
            results[cond_name] = to_jsonable(run_result)
            save_checkpoint(checkpoint_path, results)
    else:
        sem = asyncio.Semaphore(parallel)
        lock = asyncio.Lock()

        async def _run_one(cond_name: str) -> Tuple[str, Dict]:
            async with sem:
                ac = CONDITIONS[cond_name]
                logger.info("── CityBench START: %s ──", cond_name)
                r = await run_citybench_for_condition(cond_name, ac, provider, suite)
                logger.info("── CityBench DONE:  %s ──", cond_name)
                # Save incrementally under lock
                async with lock:
                    results[cond_name] = to_jsonable(r)
                    save_checkpoint(checkpoint_path, results)
                return cond_name, r

        await asyncio.gather(*[_run_one(c) for c in remaining])

    return {
        "platform": "citybench",
        "provider": provider,
        "sample_count": sample_count,
        "conditions": {k: to_jsonable(v) for k, v in results.items()},
    }


# ── UWB Memory Probe (v1.2 existing) ─────────────────────────────

async def evaluate_memory_probe_with_config(
    case: Dict[str, Any],
    ac: MemoryAblationConfig,
) -> Tuple[float, Dict[str, Any]]:
    """Run a v1.2 memory_probe case under a given ablation config."""
    if not ac.enable_memory:
        # No memory: infer with empty context
        reasoning = ReasoningModule(config={"mode": "enhanced"})
        result = await reasoning.infer(case["perception"], {}, case["task"])
        expected = case["evaluation"]["expected"]
        if case["task"]["task_type"] == "mobility_prediction":
            predicted = result.get("predicted_location")
        elif case["task"]["task_type"] == "outdoor_navigation":
            predicted = result.get("route_actions")
        else:
            predicted = result.get("exploration_plan", {}).get("selected_destination")
        return float(predicted == expected), {"predicted": predicted, "expected": expected}

    # With memory: create MemoryModule with ablation flags
    memory = MemoryModule(
        config={"short_term_size": 10},
        enable_temporal_context=ac.enable_temporal_context,
        enable_actr_activation=ac.enable_actr_activation,
        enable_temporal_match=ac.enable_temporal_match,
        enable_reflector=ac.enable_reflector,
        enable_pattern_detector=ac.enable_pattern_detector,
    )
    for experience in case.get("memory_seed", []):
        await memory.store(experience)
    memory_context = await memory.retrieve(case["task"])

    reasoning = ReasoningModule(config={"mode": "enhanced"})
    result = await reasoning.infer(case["perception"], memory_context, case["task"])
    expected = case["evaluation"]["expected"]

    if case["task"]["task_type"] == "mobility_prediction":
        predicted = result.get("predicted_location")
    elif case["task"]["task_type"] == "outdoor_navigation":
        predicted = result.get("route_actions")
    else:
        predicted = result.get("exploration_plan", {}).get("selected_destination")

    return float(predicted == expected), {
        "predicted": predicted,
        "expected": expected,
        "query_summary": memory_context.get("query_summary", {}),
    }


async def _run_uwb_one_condition(
    cond_name: str, memory_cases: List[Dict],
) -> Tuple[str, Dict]:
    ac = CONDITIONS[cond_name]
    correct = 0
    rows = []
    for case in memory_cases:
        score, detail = await evaluate_memory_probe_with_config(case, ac)
        correct += int(score >= 1.0)
        rows.append({"case_id": case["case_id"], "score": score, "detail": to_jsonable(detail)})
    total = len(memory_cases)
    return cond_name, {
        "accuracy": round(correct / total, 4),
        "correct": correct,
        "total": total,
        "rows": rows,
    }


async def run_uwb_ablation(condition_names: List[str], parallel: int = 1) -> Dict[str, Any]:
    """Run v1.2 memory_probe cases across conditions."""
    if not UWB_V12_MANIFEST.exists():
        return {"platform": "uwb_memory", "status": "skipped", "reason": "manifest_not_found"}

    manifest = json.loads(UWB_V12_MANIFEST.read_text(encoding="utf-8"))
    memory_cases = [c for c in manifest["cases"] if c["protocol"] == "memory_probe"]
    if not memory_cases:
        return {"platform": "uwb_memory", "status": "skipped", "reason": "no_memory_probe_cases"}

    results: Dict[str, Any] = {}
    if parallel <= 1:
        for cond_name in condition_names:
            _, res = await _run_uwb_one_condition(cond_name, memory_cases)
            results[cond_name] = res
    else:
        pairs = await asyncio.gather(*[_run_uwb_one_condition(c, memory_cases) for c in condition_names])
        for cond_name, res in pairs:
            results[cond_name] = res

    return {"platform": "uwb_memory", "status": "completed", "conditions": results}


# ── Temporal Memory Probe (v1.3 new) ──────────────────────────────

async def evaluate_temporal_probe(
    case: Dict[str, Any],
    ac: MemoryAblationConfig,
) -> Tuple[float, Dict[str, Any]]:
    """Evaluate one temporal_memory_probe case under ablation config."""
    if not ac.enable_memory:
        reasoning = ReasoningModule(config={"mode": "enhanced"})
        result = await reasoning.infer(case["perception"], {}, case["task"])
        return _check_temporal_probe_result(case, result, {})

    memory = MemoryModule(
        config={"short_term_size": 50},
        enable_temporal_context=ac.enable_temporal_context,
        enable_actr_activation=ac.enable_actr_activation,
        enable_temporal_match=ac.enable_temporal_match,
        enable_reflector=ac.enable_reflector,
        enable_pattern_detector=ac.enable_pattern_detector,
    )

    for experience in case.get("memory_seed", []):
        await memory.store(dict(experience))  # defensive copy

    # Use explicit query_time if available
    query_time = None
    if "query_time" in case:
        try:
            query_time = datetime.fromisoformat(case["query_time"])
        except (ValueError, TypeError):
            pass

    memory_context = await memory.retrieve(case["task"], query_time=query_time)

    reasoning = ReasoningModule(config={"mode": "enhanced"})
    result = await reasoning.infer(case["perception"], memory_context, case["task"])
    return _check_temporal_probe_result(case, result, memory_context)


def _check_temporal_probe_result(
    case: Dict,
    result: Dict,
    memory_context: Dict,
) -> Tuple[float, Dict[str, Any]]:
    """Check result against evaluation criteria."""
    evaluation = case["evaluation"]
    task_type = case["task"]["task_type"]

    if "expected" in evaluation:
        if task_type == "mobility_prediction":
            predicted = result.get("predicted_location")
        elif task_type == "outdoor_navigation":
            predicted = result.get("route_actions")
        elif task_type == "urban_exploration":
            predicted = result.get("exploration_plan", {}).get("selected_destination")
        else:
            predicted = None
        score = float(predicted == evaluation["expected"])
        return score, {"predicted": predicted, "expected": evaluation["expected"]}

    if "expected_phase" in evaluation:
        signal_plan = result.get("signal_plan", {})
        predicted = signal_plan.get("selected_phase")
        score = float(predicted == evaluation["expected_phase"])
        return score, {"predicted": predicted, "expected": evaluation["expected_phase"]}

    if "expected_destination" in evaluation:
        plan = result.get("exploration_plan", {})
        predicted = plan.get("selected_destination")
        score = float(predicted == evaluation["expected_destination"])
        return score, {"predicted": predicted, "expected": evaluation["expected_destination"]}

    return 0.0, {"error": "unknown evaluation type"}


async def _run_temporal_one_condition(
    cond_name: str, cases: List[Dict],
) -> Tuple[str, Dict]:
    ac = CONDITIONS[cond_name]
    correct = 0
    rows = []
    for case in cases:
        score, detail = await evaluate_temporal_probe(case, ac)
        correct += int(score >= 1.0)
        rows.append({"case_id": case["case_id"], "score": score, "detail": to_jsonable(detail)})
        logger.info("  %s / %s -> %.1f", cond_name, case["case_id"], score)
    total = len(cases)
    return cond_name, {
        "accuracy": round(correct / total, 4),
        "correct": correct,
        "total": total,
        "rows": rows,
    }


async def run_temporal_probe_ablation(condition_names: List[str], parallel: int = 1) -> Dict[str, Any]:
    """Run temporal_memory_probe cases across conditions."""
    if not TEMPORAL_PROBE_PATH.exists():
        return {"platform": "temporal_probe", "status": "skipped", "reason": "cases_not_found"}

    probe_data = json.loads(TEMPORAL_PROBE_PATH.read_text(encoding="utf-8"))
    cases = probe_data.get("cases", [])
    if not cases:
        return {"platform": "temporal_probe", "status": "skipped", "reason": "no_cases"}

    results: Dict[str, Any] = {}
    if parallel <= 1:
        for cond_name in condition_names:
            _, res = await _run_temporal_one_condition(cond_name, cases)
            results[cond_name] = res
    else:
        pairs = await asyncio.gather(*[_run_temporal_one_condition(c, cases) for c in condition_names])
        for cond_name, res in pairs:
            results[cond_name] = res

    return {"platform": "temporal_probe", "status": "completed", "conditions": results}


# ── Markdown summary ──────────────────────────────────────────────

def generate_markdown_summary(
    citybench: Dict[str, Any],
    uwb: Dict[str, Any],
    temporal: Dict[str, Any],
    condition_names: List[str],
) -> str:
    lines = [
        "# Stage 2: Temporal Memory Ablation Results",
        "",
        f"**Provider**: {citybench.get('provider', 'N/A')}",
        f"**Sample count per task**: {citybench.get('sample_count', 'N/A')}",
        f"**Timestamp**: {datetime.now().isoformat()}",
        f"**Conditions**: {', '.join(condition_names)}",
        "",
    ]

    # ── CityBench table ──
    all_tasks = [
        "population_prediction", "object_detection", "geolocation", "geoqa",
        "mobility_prediction", "traffic_signal", "outdoor_navigation", "urban_exploration",
    ]
    cb_conditions = citybench.get("conditions", {})
    if cb_conditions:
        lines.extend([
            "## CityBench Overall Scores",
            "",
            "| Condition | PP | OD | GL | GQ | MP | TS | ON | UE | Avg | Sens | Insens |",
            "|-----------|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:---:|:----:|:------:|",
        ])
        for cond in condition_names:
            r = cb_conditions.get(cond, {}).get("results", {})
            if not r:
                continue
            scores = [r.get(tt, {}).get("avg_score", 0.0) for tt in all_tasks]
            overall = r.get("overall", {}).get("avg_score", 0.0)
            sens = _avg([r.get(tt, {}).get("avg_score", 0.0) for tt in MEMORY_SENSITIVE_TASKS])
            insens = _avg([r.get(tt, {}).get("avg_score", 0.0) for tt in MEMORY_INSENSITIVE_TASKS])
            vals = " | ".join(f"{s:.2f}" for s in scores)
            lines.append(f"| {cond} | {vals} | {overall:.3f} | {sens:.3f} | {insens:.3f} |")
        lines.append("")

        # Delta table vs A0
        if "A0_full" in cb_conditions:
            a0_results = cb_conditions["A0_full"].get("results", {})
            a0_overall = a0_results.get("overall", {}).get("avg_score", 0.0)
            lines.extend([
                "## CityBench Δ vs A0 (Full Model)",
                "",
                "| Condition | MP Δ | TS Δ | ON Δ | UE Δ | Avg Δ | Sens Δ |",
                "|-----------|:----:|:----:|:----:|:----:|:-----:|:------:|",
            ])
            for cond in condition_names:
                if cond == "A0_full":
                    continue
                r = cb_conditions.get(cond, {}).get("results", {})
                if not r:
                    continue
                deltas = {}
                for tt in MEMORY_SENSITIVE_TASKS:
                    a0_s = a0_results.get(tt, {}).get("avg_score", 0.0)
                    c_s = r.get(tt, {}).get("avg_score", 0.0)
                    deltas[tt] = round(a0_s - c_s, 4)
                avg_d = round(a0_overall - r.get("overall", {}).get("avg_score", 0.0), 4)
                a0_sens = _avg([a0_results.get(tt, {}).get("avg_score", 0.0) for tt in MEMORY_SENSITIVE_TASKS])
                c_sens = _avg([r.get(tt, {}).get("avg_score", 0.0) for tt in MEMORY_SENSITIVE_TASKS])
                sens_d = round(a0_sens - c_sens, 4)
                lines.append(
                    f"| {cond} | {_fmt_delta(deltas.get('mobility_prediction',0))} "
                    f"| {_fmt_delta(deltas.get('traffic_signal',0))} "
                    f"| {_fmt_delta(deltas.get('outdoor_navigation',0))} "
                    f"| {_fmt_delta(deltas.get('urban_exploration',0))} "
                    f"| {_fmt_delta(avg_d)} | {_fmt_delta(sens_d)} |"
                )
            lines.append("")

    # ── UWB v1.2 memory probe ──
    uwb_conds = uwb.get("conditions", {})
    if uwb_conds:
        lines.extend([
            "## UWB Memory Continuity Probe",
            "",
            "| Condition | Accuracy | Correct/Total |",
            "|-----------|:--------:|:-------------:|",
        ])
        for cond in condition_names:
            r = uwb_conds.get(cond, {})
            if not r:
                continue
            lines.append(f"| {cond} | {r.get('accuracy', 0):.4f} | {r.get('correct', 0)}/{r.get('total', 0)} |")
        lines.append("")

    # ── Temporal probe ──
    tp_conds = temporal.get("conditions", {})
    if tp_conds:
        lines.extend([
            "## Temporal Memory Probe (v1.3)",
            "",
            "| Condition | Accuracy | Correct/Total |",
            "|-----------|:--------:|:-------------:|",
        ])
        for cond in condition_names:
            r = tp_conds.get(cond, {})
            if not r:
                continue
            lines.append(f"| {cond} | {r.get('accuracy', 0):.4f} | {r.get('correct', 0)}/{r.get('total', 0)} |")
        lines.append("")

        # Per-case breakdown
        lines.extend([
            "### Per-Case Detail",
            "",
        ])
        # Gather all case_ids
        case_ids = []
        for r in tp_conds.values():
            for row in r.get("rows", []):
                if row["case_id"] not in case_ids:
                    case_ids.append(row["case_id"])

        header = "| Case | " + " | ".join(condition_names) + " |"
        sep = "|------|" + "|".join(":---:" for _ in condition_names) + "|"
        lines.extend([header, sep])

        for cid in case_ids:
            vals = []
            for cond in condition_names:
                rows = tp_conds.get(cond, {}).get("rows", [])
                row = next((r for r in rows if r["case_id"] == cid), None)
                vals.append(f"{row['score']:.0f}" if row else "—")
            lines.append(f"| {cid} | " + " | ".join(vals) + " |")
        lines.append("")

    # ── Component contribution ranking ──
    if "A0_full" in cb_conditions and len(cb_conditions) > 1:
        a0_avg = cb_conditions["A0_full"].get("results", {}).get("overall", {}).get("avg_score", 0.0)
        contributions = []
        for cond in ["A1_no_tc", "A2_no_actr", "A3_no_tmatch", "A4_no_reflector", "A5_no_pattern"]:
            if cond not in cb_conditions:
                continue
            c_avg = cb_conditions[cond].get("results", {}).get("overall", {}).get("avg_score", 0.0)
            contributions.append((cond, round(a0_avg - c_avg, 4)))
        if contributions:
            contributions.sort(key=lambda x: x[1], reverse=True)
            lines.extend([
                "## Component Contribution Ranking (CityBench Avg Δ)",
                "",
            ])
            for i, (cond, delta) in enumerate(contributions, 1):
                lines.append(f"{i}. **{cond}**: {_fmt_delta(delta)}")
            lines.append("")

    lines.append("")
    return "\n".join(lines)


def _avg(values: list) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def _fmt_delta(d: float) -> str:
    return f"+{d:.4f}" if d > 0 else f"{d:.4f}"


# ── CLI ───────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage 2: Temporal Memory Ablation")
    parser.add_argument(
        "--provider", choices=["none", "qwen", "kimi"], default="none",
        help="LLM provider (none=heuristic smoke test)",
    )
    parser.add_argument("--sample-count", type=int, default=10)
    parser.add_argument(
        "--conditions", type=str, default=None,
        help="Comma-separated condition names (default: all 9)",
    )
    parser.add_argument("--skip-citybench", action="store_true")
    parser.add_argument("--skip-uwb", action="store_true")
    parser.add_argument("--skip-temporal", action="store_true")
    parser.add_argument(
        "--parallel", type=int, default=1,
        help="Max parallel conditions for CityBench (default: 1=sequential, 3 recommended for Qwen)",
    )
    parser.add_argument(
        "--logfile", type=str, default=None,
        help="Log to file in addition to console (auto-generated if not set)",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    load_env_file()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Setup file logging
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    logfile = Path(args.logfile) if args.logfile else RESULTS_DIR / f"ablation_run_{timestamp}.log"
    setup_file_logging(logfile)
    logger.info("Logging to %s", logfile)

    if args.conditions:
        condition_names = [c.strip() for c in args.conditions.split(",")]
        for c in condition_names:
            if c not in CONDITIONS:
                logger.error("Unknown condition: %s. Available: %s", c, list(CONDITIONS.keys()))
                return
    else:
        condition_names = list(CONDITIONS.keys())

    logger.info("=== Stage 2: Temporal Memory Ablation ===")
    logger.info("Provider: %s | Samples: %s | Parallel: %d | Conditions: %s",
                args.provider, args.sample_count, args.parallel, condition_names)

    citybench_result: Dict[str, Any] = {}
    uwb_result: Dict[str, Any] = {}
    temporal_result: Dict[str, Any] = {}

    # ── CityBench ──
    if not args.skip_citybench:
        logger.info("══ CityBench ablation (%d conditions) ══", len(condition_names))
        citybench_result = await run_citybench_ablation(args.provider, args.sample_count, condition_names, parallel=args.parallel)
        logger.info("CityBench done.")

    # ── UWB v1.2 memory_probe ──
    if not args.skip_uwb:
        logger.info("══ UWB v1.2 memory_probe ══")
        uwb_result = await run_uwb_ablation(condition_names, parallel=args.parallel)
        logger.info("UWB done. Status: %s", uwb_result.get("status"))

    # ── Temporal probe v1.3 ──
    if not args.skip_temporal:
        logger.info("══ Temporal memory probe v1.3 ══")
        temporal_result = await run_temporal_probe_ablation(condition_names, parallel=args.parallel)
        logger.info("Temporal probe done. Status: %s", temporal_result.get("status"))

    # ── Save results ──
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    full_report = {
        "experiment": "temporal_memory_ablation_stage2",
        "timestamp": datetime.now().isoformat(),
        "provider": args.provider,
        "sample_count": args.sample_count,
        "conditions": condition_names,
        "citybench": to_jsonable(citybench_result),
        "uwb_memory": to_jsonable(uwb_result),
        "temporal_probe": to_jsonable(temporal_result),
    }

    json_path = RESULTS_DIR / f"memory_ablation_{timestamp}.json"
    json_path.write_text(json.dumps(full_report, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("JSON results → %s", json_path)

    md_text = generate_markdown_summary(citybench_result, uwb_result, temporal_result, condition_names)
    md_path = RESULTS_DIR / f"memory_ablation_summary_{timestamp}.md"
    md_path.write_text(md_text, encoding="utf-8")
    logger.info("Markdown summary → %s", md_path)

    # Console summary
    console: Dict[str, Any] = {"json_path": str(json_path), "md_path": str(md_path)}
    if citybench_result:
        conds = citybench_result.get("conditions", {})
        console["citybench_overall"] = {
            k: v.get("results", {}).get("overall", {}).get("avg_score", None)
            for k, v in conds.items()
        }
    if uwb_result.get("conditions"):
        console["uwb_accuracy"] = {
            k: v.get("accuracy") for k, v in uwb_result["conditions"].items()
        }
    if temporal_result.get("conditions"):
        console["temporal_accuracy"] = {
            k: v.get("accuracy") for k, v in temporal_result["conditions"].items()
        }
    print(json.dumps(console, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
