"""
Stage 1: 空间记忆基线验证 (Spatial Memory Ablation)

验证现有空间记忆机制（地名匹配 + 按位置分桶 + 历史结果复用）对 CityBench 任务有效。

两个实验条件：
- S1_with_memory:  UrbanAgent(enable_memory=True)  — 现有 MemoryModule
- S1_no_memory:    UrbanAgent(enable_memory=False) — 管线完全跳过记忆

CityBench 8 任务 × N 实例 + UWB memory_continuity 探针。
预期：MP/TS/ON/UE 有记忆增益，PP/OD/GL/GQ 无差异。

用法:
  python run_spatial_memory_ablation.py --provider none   # 冒烟 0 开销
  python run_spatial_memory_ablation.py --provider qwen   # 正式 ~166 API calls
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

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
from urban_agent.core.memory import MemoryModule
from urban_agent.core.reasoning import ReasoningModule

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

RESULTS_DIR = ROOT / "artifacts" / "benchmarks"
MEMORY_SENSITIVE_TASKS = {"mobility_prediction", "traffic_signal", "outdoor_navigation", "urban_exploration"}
MEMORY_INSENSITIVE_TASKS = {"population_prediction", "object_detection", "geolocation", "geoqa"}


# ── CityBench 对照实验 ────────────────────────────────────────────

async def run_citybench_ablation(
    provider: str,
    sample_count: int,
) -> Dict[str, Any]:
    """运行 CityBench 8 任务, with_memory vs no_memory."""

    sampler = CityDataQuickSampler(CITYDATA_ROOT, seed=RANDOM_SEED)
    suite = sampler.build_suite(sample_count)
    runner = QuickBenchmarkRunner(suite)

    # ── 条件 1: enhanced + memory ──
    agent_with_memory = await build_agent(provider, {
        "reasoning": {"mode": "enhanced"},
        "action": {"tool_runtime": "mcp"},
        "enable_memory": True,
    })
    result_with = await runner.run("S1_with_memory", agent_with_memory)

    # ── 条件 2: enhanced + no memory ──
    agent_no_memory = await build_agent(provider, {
        "reasoning": {"mode": "enhanced"},
        "action": {"tool_runtime": "mcp"},
        "enable_memory": False,
    })
    result_no = await runner.run("S1_no_memory", agent_no_memory)

    # ── 计算 task-level delta ──
    task_types = list(suite.keys())
    deltas: Dict[str, float] = {}
    for tt in task_types:
        with_score = result_with["results"][tt]["avg_score"]
        no_score = result_no["results"][tt]["avg_score"]
        deltas[tt] = round(with_score - no_score, 4)

    sensitive_with = _subset_avg(result_with, MEMORY_SENSITIVE_TASKS)
    sensitive_no = _subset_avg(result_no, MEMORY_SENSITIVE_TASKS)
    insensitive_with = _subset_avg(result_with, MEMORY_INSENSITIVE_TASKS)
    insensitive_no = _subset_avg(result_no, MEMORY_INSENSITIVE_TASKS)

    return {
        "platform": "citybench",
        "provider": provider,
        "sample_count": sample_count,
        "with_memory": to_jsonable(result_with),
        "no_memory": to_jsonable(result_no),
        "deltas": deltas,
        "summary": {
            "with_memory_overall": result_with["results"]["overall"]["avg_score"],
            "no_memory_overall": result_no["results"]["overall"]["avg_score"],
            "overall_delta": round(
                result_with["results"]["overall"]["avg_score"]
                - result_no["results"]["overall"]["avg_score"],
                4,
            ),
            "sensitive_with": sensitive_with,
            "sensitive_no": sensitive_no,
            "sensitive_delta": round(sensitive_with - sensitive_no, 4),
            "insensitive_with": insensitive_with,
            "insensitive_no": insensitive_no,
            "insensitive_delta": round(insensitive_with - insensitive_no, 4),
        },
    }


def _subset_avg(run_result: Dict, task_set: set) -> float:
    scores = [
        run_result["results"][tt]["avg_score"]
        for tt in task_set
        if tt in run_result["results"]
    ]
    return round(sum(scores) / len(scores), 4) if scores else 0.0


# ── UWB memory_continuity 对照实验 ─────────────────────────────────

async def evaluate_memory_probe_no_memory(case: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    """与 evaluate_memory_probe 相同流程，但传空 memory_context。"""
    reasoning = ReasoningModule(config={"mode": "enhanced"})
    result = await reasoning.infer(case["perception"], {}, case["task"])
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
        "query_summary": {},
    }


async def run_uwb_memory_ablation() -> Dict[str, Any]:
    """加载 v1.2 manifest 中 memory_probe case，分别以有/无记忆运行。"""

    manifest_path = RESULTS_DIR / "urbanworkflowbench_v1_2_manifest_latest.json"
    if not manifest_path.exists():
        logger.warning("UWB v1.2 manifest not found at %s, skipping", manifest_path)
        return {"platform": "uwb_memory", "status": "skipped", "reason": "manifest_not_found"}

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    memory_cases = [c for c in manifest["cases"] if c["protocol"] == "memory_probe"]
    if not memory_cases:
        return {"platform": "uwb_memory", "status": "skipped", "reason": "no_memory_probe_cases"}

    rows: List[Dict[str, Any]] = []
    with_correct = 0
    no_correct = 0

    for case in memory_cases:
        score_with, detail_with = await evaluate_memory_probe(case)
        score_no, detail_no = await evaluate_memory_probe_no_memory(case)
        with_correct += int(score_with >= 1.0)
        no_correct += int(score_no >= 1.0)
        rows.append({
            "case_id": case["case_id"],
            "with_memory_score": score_with,
            "no_memory_score": score_no,
            "delta": round(score_with - score_no, 4),
            "with_detail": to_jsonable(detail_with),
            "no_detail": to_jsonable(detail_no),
        })

    total = len(memory_cases)
    return {
        "platform": "uwb_memory",
        "status": "completed",
        "case_count": total,
        "with_memory_accuracy": round(with_correct / total, 4),
        "no_memory_accuracy": round(no_correct / total, 4),
        "memory_gain": round((with_correct - no_correct) / total, 4),
        "rows": rows,
    }


# ── Markdown 摘要表 ─────────────────────────────────────────────

def generate_markdown_summary(
    citybench: Dict[str, Any],
    uwb: Dict[str, Any],
) -> str:
    lines = [
        "# Stage 1: Spatial Memory Ablation Results",
        "",
        f"**Provider**: {citybench.get('provider', 'N/A')}",
        f"**Sample count per task**: {citybench.get('sample_count', 'N/A')}",
        f"**Timestamp**: {datetime.now().isoformat()}",
        "",
        "## CityBench Task-Level Comparison",
        "",
        "| Task Type | With Memory | No Memory | Δ (gain) | Memory-Sensitive |",
        "|-----------|:-----------:|:---------:|:--------:|:----------------:|",
    ]

    with_results = citybench.get("with_memory", {}).get("results", {})
    no_results = citybench.get("no_memory", {}).get("results", {})
    all_tasks = [
        "population_prediction", "object_detection", "geolocation", "geoqa",
        "mobility_prediction", "traffic_signal", "outdoor_navigation", "urban_exploration",
    ]

    for tt in all_tasks:
        w = with_results.get(tt, {}).get("avg_score", 0.0)
        n = no_results.get(tt, {}).get("avg_score", 0.0)
        d = round(w - n, 4)
        sensitive = "✓" if tt in MEMORY_SENSITIVE_TASKS else ""
        sign = "+" if d > 0 else ""
        lines.append(f"| {tt} | {w:.4f} | {n:.4f} | {sign}{d:.4f} | {sensitive} |")

    s = citybench.get("summary", {})
    lines.extend([
        f"| **Overall** | **{s.get('with_memory_overall', 0):.4f}** | **{s.get('no_memory_overall', 0):.4f}** | **{'+' if s.get('overall_delta', 0) > 0 else ''}{s.get('overall_delta', 0):.4f}** | |",
        "",
        "## Memory-Sensitive Subset",
        "",
        f"- With Memory: **{s.get('sensitive_with', 0):.4f}**",
        f"- No Memory:   **{s.get('sensitive_no', 0):.4f}**",
        f"- Δ:           **{'+' if s.get('sensitive_delta', 0) > 0 else ''}{s.get('sensitive_delta', 0):.4f}**",
        "",
        "## Memory-Insensitive Subset (Sanity Check)",
        "",
        f"- With Memory: **{s.get('insensitive_with', 0):.4f}**",
        f"- No Memory:   **{s.get('insensitive_no', 0):.4f}**",
        f"- Δ:           **{'+' if s.get('insensitive_delta', 0) > 0 else ''}{s.get('insensitive_delta', 0):.4f}**",
        "",
    ])

    # UWB section
    lines.extend([
        "## UWB Memory Continuity Probe",
        "",
    ])
    if uwb.get("status") == "completed":
        lines.extend([
            f"- Cases: {uwb.get('case_count', 0)}",
            f"- With Memory Accuracy: **{uwb.get('with_memory_accuracy', 0):.4f}**",
            f"- No Memory Accuracy:   **{uwb.get('no_memory_accuracy', 0):.4f}**",
            f"- Memory Gain:          **{'+' if uwb.get('memory_gain', 0) > 0 else ''}{uwb.get('memory_gain', 0):.4f}**",
            "",
            "| Case | With Memory | No Memory | Δ |",
            "|------|:-----------:|:---------:|:-:|",
        ])
        for row in uwb.get("rows", []):
            d = row["delta"]
            lines.append(
                f"| {row['case_id']} | {row['with_memory_score']:.1f} | {row['no_memory_score']:.1f} | {'+' if d > 0 else ''}{d:.1f} |"
            )
    else:
        lines.append(f"*Skipped*: {uwb.get('reason', 'unknown')}")

    lines.append("")
    return "\n".join(lines)


# ── 主流程 ─────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage 1: Spatial Memory Ablation")
    parser.add_argument(
        "--provider",
        choices=["none", "qwen", "kimi"],
        default="none",
        help="LLM provider (none=heuristic smoke test)",
    )
    parser.add_argument("--sample-count", type=int, default=10)
    parser.add_argument("--skip-citybench", action="store_true", help="Skip CityBench, only run UWB")
    parser.add_argument("--skip-uwb", action="store_true", help="Skip UWB, only run CityBench")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    load_env_file()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    logger.info("=== Stage 1: Spatial Memory Ablation ===")
    logger.info("Provider: %s | Samples: %s", args.provider, args.sample_count)

    citybench_result: Dict[str, Any] = {}
    uwb_result: Dict[str, Any] = {}

    # ── CityBench ──
    if not args.skip_citybench:
        logger.info("── CityBench ablation ──")
        citybench_result = await run_citybench_ablation(args.provider, args.sample_count)
        logger.info(
            "CityBench done. Overall delta: %s",
            citybench_result.get("summary", {}).get("overall_delta"),
        )

    # ── UWB memory_continuity ──
    if not args.skip_uwb:
        logger.info("── UWB memory_continuity ablation ──")
        uwb_result = await run_uwb_memory_ablation()
        logger.info("UWB done. Memory gain: %s", uwb_result.get("memory_gain"))

    # ── 保存结果 ──
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    full_report = {
        "experiment": "spatial_memory_ablation_stage1",
        "timestamp": datetime.now().isoformat(),
        "provider": args.provider,
        "sample_count": args.sample_count,
        "citybench": to_jsonable(citybench_result),
        "uwb_memory": to_jsonable(uwb_result),
    }

    json_path = RESULTS_DIR / f"spatial_memory_ablation_{timestamp}.json"
    json_path.write_text(
        json.dumps(full_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("JSON results → %s", json_path)

    # ── Markdown 摘要 ──
    md_text = generate_markdown_summary(citybench_result, uwb_result)
    md_path = RESULTS_DIR / f"spatial_memory_ablation_summary_{timestamp}.md"
    md_path.write_text(md_text, encoding="utf-8")
    logger.info("Markdown summary → %s", md_path)

    # ── 控制台摘要 ──
    console = {
        "json_path": str(json_path),
        "md_path": str(md_path),
    }
    if citybench_result:
        console["citybench_summary"] = citybench_result.get("summary", {})
    if uwb_result:
        console["uwb_summary"] = {
            k: v for k, v in uwb_result.items() if k != "rows"
        }
    print(json.dumps(console, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
