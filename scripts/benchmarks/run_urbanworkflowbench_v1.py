"""Run UrbanWorkflowBench v1.0."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.benchmarks.run_citydata_quick_benchmark import load_env_file, to_jsonable
from legacy.urban_agent_legacy.cognition import SpatialCognition
from urban_agent.core.memory import MemoryModule
from urban_agent.core.reasoning import ReasoningModule
from urban_agent.llm.kimi_client import KimiClient
from urban_agent.llm.qwen_client import QwenClient
from urban_agent.task_agent import UrbanTaskAgent


OUTPUT_DIR = ROOT / "artifacts" / "benchmarks"


class SyntheticContext:
    def __init__(self, raw_features: Dict[str, Any]):
        self.raw_features = raw_features
        self.crs = "EPSG:3857"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(OUTPUT_DIR / "urbanworkflowbench_v1_manifest_latest.json"))
    parser.add_argument("--provider", choices=["none", "qwen", "kimi"], default="none")
    return parser.parse_args()


async def build_agent(provider: str) -> UrbanTaskAgent:
    load_env_file()
    llm_client = None
    vlm_client = None
    if provider == "qwen":
        model = QwenClient()
        llm_client = model
        vlm_client = model
    elif provider == "kimi":
        model = KimiClient(client_type="standard")
        llm_client = model
        vlm_client = model

    return UrbanTaskAgent(
        llm_client=llm_client,
        vlm_client=vlm_client,
        config={
            "reasoning": {"mode": "enhanced"},
            "action": {"tool_runtime": "mcp"},
            "enable_memory": True,
        },
    )


def evaluate_agent_task(case: Dict[str, Any], result: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    action = result.get("action", {})
    task_type = case["evaluation"]["task_type"]
    expected = case["evaluation"].get("expected")
    expected_option = case["evaluation"].get("expected_option")

    if task_type == "geoqa":
        predicted = action.get("selected_option")
        return float(predicted == expected), {"predicted": predicted, "expected": expected}
    if task_type == "mobility_prediction":
        predicted = action.get("predicted_location")
        return float(predicted == expected), {"predicted": predicted, "expected": expected}
    if task_type == "outdoor_navigation":
        predicted = action.get("route_actions", [])
        return float(predicted == expected), {"predicted": predicted, "expected": expected}
    if task_type == "urban_exploration":
        predicted = action.get("selected_option")
        expected_value = expected_option if expected_option is not None else expected
        return float(predicted == expected_value), {"predicted": predicted, "expected": expected_value}
    return 0.0, {"error": "unsupported task type", "task_type": task_type}


def evaluate_dual_space_probe(case: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    cognition = SpatialCognition()
    result = cognition.understand(SyntheticContext(case["features"]), case["case_id"])
    relation_types = [relation["type"] for relation in result["topological_graph"]["relations"]]
    predicted = case["expected_relation"] if case["expected_relation"] in relation_types else None
    score = float(predicted == case["expected_relation"])
    return score, {
        "predicted": predicted,
        "expected": case["expected_relation"],
        "relation_types": relation_types,
        "mapping_completeness": len(result["vector_mapping"]["relation_geometries"]) > 0,
    }


async def evaluate_memory_probe(case: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    memory = MemoryModule(config={"short_term_size": 10})
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


async def main() -> None:
    args = parse_args()
    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    agent = await build_agent(args.provider)

    rows: List[Dict[str, Any]] = []
    suite_scores: Dict[str, List[float]] = {}

    for case in manifest["cases"]:
        protocol = case["protocol"]
        if protocol == "agent_task":
            result = await agent.execute_task(task=case["task"], task_type=case["task"]["task_type"])
            score, detail = evaluate_agent_task(case, result)
            payload = {"result": to_jsonable(result)}
        elif protocol == "dual_space_probe":
            score, detail = evaluate_dual_space_probe(case)
            payload = {}
        elif protocol == "memory_probe":
            score, detail = await evaluate_memory_probe(case)
            payload = {}
        else:
            score, detail = 0.0, {"error": f"Unknown protocol: {protocol}"}
            payload = {}

        suite_scores.setdefault(case["suite"], []).append(score)
        rows.append({
            "case_id": case["case_id"],
            "suite": case["suite"],
            "protocol": protocol,
            "capability": case["capability"],
            "score": score,
            "detail": to_jsonable(detail),
            **payload,
        })

    summary = {
        suite: round(sum(scores) / len(scores), 4)
        for suite, scores in suite_scores.items()
    }
    summary["overall"] = round(sum(summary.values()) / len(summary), 4) if summary else 0.0

    report = {
        "benchmark": manifest["benchmark"],
        "version": manifest["version"],
        "provider": args.provider,
        "created_at": datetime.now().isoformat(),
        "manifest": str(manifest_path),
        "summary": summary,
        "rows": rows,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"urbanworkflowbench_v1_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "output_path": str(output_path),
        "summary": summary,
        "case_count": len(rows),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())