"""Run UrbanWorkflowBench v1.1."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.benchmarks.run_citydata_quick_benchmark import load_env_file, to_jsonable
from urban_agent.cognition import SpatialCognition
from urban_agent.core.action import ActionModule
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


def write_report(output_path: Path, report: Dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(OUTPUT_DIR / "urbanworkflowbench_v1_1_manifest_latest.json"))
    parser.add_argument("--provider", choices=["none", "qwen", "kimi", "all"], default="none")
    parser.add_argument("--strict-provider", action="store_true")
    return parser.parse_args()


async def build_agent(provider: str) -> UrbanTaskAgent:
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


def provider_available(provider: str) -> bool:
    if provider == "none":
        return True
    if provider == "qwen":
        return bool(os.getenv("QWEN_API_KEY"))
    if provider == "kimi":
        return bool(os.getenv("KIMI_API_KEY"))
    return False


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


async def evaluate_tool_orchestration(case: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    action_module = ActionModule(config={"tool_runtime": "local"})
    executed_tools: List[str] = []
    step_results: List[Dict[str, Any]] = []
    success_count = 0
    failure_indices: List[int] = []

    for index, step in enumerate(case.get("tool_steps", []), start=1):
        executed_tools.append(step["tool"])
        result = await action_module.call_tool(step["tool"], step.get("params", {}))
        succeeded = bool(result.get("success"))
        expected_success = bool(step.get("expect_success", True))
        if succeeded:
            success_count += 1
        else:
            failure_indices.append(index)
        step_results.append({
            "tool": step["tool"],
            "succeeded": succeeded,
            "expected_success": expected_success,
            "matched_expectation": succeeded == expected_success,
            "result": to_jsonable(result),
        })

    expectation = case["workflow_expectation"]
    expected_tools = expectation.get("expected_tools", [])
    sequence_match = executed_tools == expected_tools if expectation.get("require_sequence_match", False) else True
    valid_rate = 0.0
    if step_results:
        valid_rate = sum(1.0 for item in step_results if item["matched_expectation"]) / len(step_results)
    workflow_completed = success_count >= expectation.get("required_successes", 0)
    recovery_expected = expectation.get("recovery_expected", False)
    recovery_success = (len(failure_indices) > 0 and workflow_completed) if recovery_expected else workflow_completed
    score = (float(sequence_match) + valid_rate + float(workflow_completed) + float(recovery_success)) / 4.0

    return round(score, 4), {
        "executed_tools": executed_tools,
        "expected_tools": expected_tools,
        "sequence_match": sequence_match,
        "valid_rate": round(valid_rate, 4),
        "workflow_completed": workflow_completed,
        "recovery_success": recovery_success,
        "step_results": step_results,
    }


def deep_update(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_update(base[key], value)
        else:
            base[key] = value
    return base


def contains_expected(base: Dict[str, Any], expected: Dict[str, Any]) -> bool:
    for key, value in expected.items():
        if isinstance(value, dict):
            child = base.get(key)
            if not isinstance(child, dict) or not contains_expected(child, value):
                return False
        else:
            if base.get(key) != value:
                return False
    return True


def evaluate_hitl_checkpoint(case: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    state = json.loads(json.dumps(case.get("state", {})))
    cancelled = False
    actions_handled = 0
    action_log: List[Dict[str, Any]] = []

    for step in case.get("checkpoint_flow", []):
        action = step.get("action")
        checkpoint_id = step.get("checkpoint_id")
        actions_handled += 1
        if action == "approve":
            action_log.append({"checkpoint_id": checkpoint_id, "action": action, "applied": True})
            continue
        if action == "modify":
            deep_update(state, step.get("patch", {}))
            action_log.append({"checkpoint_id": checkpoint_id, "action": action, "applied": True})
            continue
        if action == "reject":
            cancelled = True
            action_log.append({"checkpoint_id": checkpoint_id, "action": action, "applied": True})
            break
        action_log.append({"checkpoint_id": checkpoint_id, "action": action, "applied": False})

    expected_final = case["evaluation"].get("expected_final", {})
    expected_cancelled = bool(case["evaluation"].get("cancelled", False))
    checkpoint_compliance = float(actions_handled == len(case.get("checkpoint_flow", [])))
    modification_persistence = float(contains_expected(state, expected_final))
    cancellation_handling = float(cancelled == expected_cancelled)
    score = round((checkpoint_compliance + modification_persistence + cancellation_handling) / 3.0, 4)

    return score, {
        "cancelled": cancelled,
        "expected_cancelled": expected_cancelled,
        "checkpoint_compliance": checkpoint_compliance,
        "modification_persistence": modification_persistence,
        "cancellation_handling": cancellation_handling,
        "final_state": state,
        "action_log": action_log,
    }


async def run_provider(manifest: Dict[str, Any], provider: str) -> Dict[str, Any]:
    agent = await build_agent(provider)
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
        elif protocol == "tool_orchestration_probe":
            score, detail = await evaluate_tool_orchestration(case)
            payload = {}
        elif protocol == "hitl_checkpoint_probe":
            score, detail = evaluate_hitl_checkpoint(case)
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

    summary = {suite: round(sum(scores) / len(scores), 4) for suite, scores in suite_scores.items()}
    summary["overall"] = round(sum(summary.values()) / len(summary), 4) if summary else 0.0
    return {"provider": provider, "summary": summary, "rows": rows}


async def main() -> None:
    args = parse_args()
    load_env_file()
    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    requested_providers = [args.provider] if args.provider != "all" else ["none", "qwen", "kimi"]
    provider_reports: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    output_path = OUTPUT_DIR / f"urbanworkflowbench_v1_1_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report = {
        "benchmark": manifest["benchmark"],
        "version": manifest["version"],
        "requested_provider": args.provider,
        "created_at": datetime.now().isoformat(),
        "manifest": str(manifest_path),
        "provider_reports": provider_reports,
        "skipped": skipped,
        "status": "in_progress",
    }
    write_report(output_path, report)

    for provider in requested_providers:
        if not provider_available(provider):
            message = {"provider": provider, "reason": "missing API key"}
            if args.strict_provider:
                raise RuntimeError(f"Provider unavailable: {message}")
            skipped.append(message)
            write_report(output_path, report)
            continue
        provider_reports.append(await run_provider(manifest, provider))
        report["last_completed_provider"] = provider
        write_report(output_path, report)

    report["status"] = "completed"
    if len(provider_reports) == 1:
        report["provider"] = provider_reports[0]["provider"]
        report["summary"] = provider_reports[0]["summary"]
        report["rows"] = provider_reports[0]["rows"]

    write_report(output_path, report)

    console_summary = {
        "output_path": str(output_path),
        "provider_count": len(provider_reports),
        "providers": [item["provider"] for item in provider_reports],
        "skipped": skipped,
    }
    if len(provider_reports) == 1:
        console_summary["summary"] = provider_reports[0]["summary"]
        console_summary["case_count"] = len(provider_reports[0]["rows"])
    print(json.dumps(console_summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())