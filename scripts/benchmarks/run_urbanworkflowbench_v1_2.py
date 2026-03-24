"""Run UrbanWorkflowBench v1.2."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.benchmarks.run_citydata_quick_benchmark import load_env_file, to_jsonable
from scripts.benchmarks.run_urbanworkflowbench_v1_1 import (
    build_agent,
    evaluate_agent_task,
    evaluate_dual_space_probe,
    evaluate_hitl_checkpoint,
    evaluate_memory_probe,
    evaluate_tool_orchestration,
    provider_available,
    write_report,
)


OUTPUT_DIR = ROOT / "artifacts" / "benchmarks"
VALIDATION_WORDS = {"validate", "validation", "review", "check", "verify", "sanity", "qa", "inspect"}
TOOL_ALIASES = {
    "load": "load_data",
    "read": "load_data",
    "import": "load_data",
    "filter": "filter_features",
    "select": "filter_features",
    "buffer": "buffer",
    "overlay": "overlay_analysis",
    "intersect": "overlay_analysis",
    "intersection": "overlay_analysis",
    "join": "spatial_join",
    "merge": "spatial_join",
    "kriging": "interpolation",
    "interpolate": "interpolation",
    "network": "network_analysis",
    "route": "network_analysis",
    "accessibility": "network_analysis",
    "raster": "raster_calculation",
    "cluster": "hotspot_analysis",
    "hotspot": "hotspot_analysis",
    "visualize": "visualization",
    "visualization": "visualization",
    "map": "visualization",
    "choropleth": "visualization",
    "report": "reporting",
    "table": "reporting",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(OUTPUT_DIR / "urbanworkflowbench_v1_2_manifest_latest.json"))
    parser.add_argument("--provider", choices=["none", "qwen", "kimi", "all"], default="none")
    parser.add_argument("--strict-provider", action="store_true")
    return parser.parse_args()


def normalize_text(text: str) -> str:
    lowered = (text or "").lower().strip()
    lowered = re.sub(r"[^a-z0-9\s]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def canonical_tool_name(raw_name: str) -> str:
    text = normalize_text(raw_name)
    for keyword, alias in TOOL_ALIASES.items():
        if keyword in text:
            return alias
    return text.replace(" ", "_") if text else "unknown_tool"


def phrase_similarity(left: str, right: str) -> float:
    left_tokens = set(normalize_text(left).split())
    right_tokens = set(normalize_text(right).split())
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    return overlap / union if union else 0.0


def best_match_ratio(references: List[str], candidates: List[str], threshold: float = 0.34) -> float:
    if not references:
        return 1.0
    if not candidates:
        return 0.0
    hits = 0
    for reference in references:
        best = max((phrase_similarity(reference, candidate) for candidate in candidates), default=0.0)
        if best >= threshold:
            hits += 1
    return round(hits / len(references), 4)


def extract_json_object(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            return {}
    return {}


def infer_tools_from_text(texts: List[str]) -> List[str]:
    tools: List[str] = []
    for text in texts:
        canonical = canonical_tool_name(text)
        if canonical != "unknown_tool":
            tools.append(canonical)
    return list(dict.fromkeys(tools))


def heuristic_open_workflow_plan(case: Dict[str, Any]) -> Dict[str, Any]:
    task_seed = case["task_seed"]
    text = " ".join([
        task_seed.get("task_title", ""),
        task_seed.get("task_instruction", ""),
        " ".join(task_seed.get("task_categories", [])),
    ]).lower()
    steps = ["Load and inspect the required spatial datasets"]

    if any(keyword in text for keyword in ["flood", "subsidence", "heat", "exposure"]):
        steps.append("Compute the core hazard or exposure surface for the study area")
    elif any(keyword in text for keyword in ["route", "road", "bike", "accessibility", "service area"]):
        steps.append("Run the required network or accessibility analysis")
    elif any(keyword in text for keyword in ["population", "demographic", "county", "census"]):
        steps.append("Aggregate target demographic indicators over the analysis units")
    else:
        steps.append("Perform the main spatial analysis described by the task")

    steps.append("Validate CRS, geometry, and intermediate outputs before finalizing results")
    steps.append("Produce the requested map, report, or other final deliverable")

    deliverables = case["evaluation"].get("expected_deliverables", ["report"])
    tool_plan = infer_tools_from_text(steps + deliverables)
    checkpoints = [
        "Validate data source coverage and CRS consistency",
        "Review final outputs before submission",
    ]

    return {
        "workflow_steps": steps,
        "tool_plan": tool_plan,
        "checkpoints": checkpoints,
        "deliverables": deliverables,
        "rationale": "Heuristic smoke-test workflow plan.",
        "planning_mode": "heuristic",
    }


async def generate_open_workflow_plan(case: Dict[str, Any], provider: str, agent: Any) -> Dict[str, Any]:
    if provider == "none" or getattr(agent, "llm_client", None) is None:
        return heuristic_open_workflow_plan(case)

    task_seed = case["task_seed"]
    prompt = (
        "You are evaluating urban geospatial workflow planning ability.\n"
        "Given a benchmark seed, propose an executable workflow plan.\n"
        "Return strict JSON with keys: workflow_steps, tool_plan, checkpoints, deliverables, rationale.\n"
        "workflow_steps must be an array of short strings.\n"
        "tool_plan must be an array of concise tool or function names.\n"
        "checkpoints must be an array of validation or review checkpoints.\n"
        "deliverables must be an array of outputs.\n"
        "Do not include markdown fences.\n\n"
        f"Task title: {task_seed.get('task_title', '')}\n"
        f"Task instruction: {task_seed.get('task_instruction', '')}\n"
        f"Task categories: {task_seed.get('task_categories', [])}\n"
        f"Dataset description: {task_seed.get('dataset_description', '')}\n"
    )
    raw_text = await agent.llm_client.generate(prompt, temperature=0.2, max_tokens=900)
    parsed = extract_json_object(raw_text)
    if not parsed:
        parsed = heuristic_open_workflow_plan(case)
        parsed["planning_mode"] = "heuristic_fallback"
        parsed["raw_response"] = raw_text
        return parsed

    parsed.setdefault("workflow_steps", [])
    parsed.setdefault("tool_plan", [])
    parsed.setdefault("checkpoints", [])
    parsed.setdefault("deliverables", [])
    parsed.setdefault("rationale", "")
    parsed["planning_mode"] = "llm"
    parsed["raw_response"] = raw_text
    return parsed


async def evaluate_open_workflow_planning(case: Dict[str, Any], provider: str, agent: Any) -> Tuple[float, Dict[str, Any]]:
    plan = await generate_open_workflow_plan(case, provider, agent)

    predicted_steps = [
        item if isinstance(item, str) else str(item.get("step", ""))
        for item in plan.get("workflow_steps", [])
        if item
    ]
    predicted_tools = [canonical_tool_name(item) for item in plan.get("tool_plan", []) if item]
    predicted_deliverables = [normalize_text(item) for item in plan.get("deliverables", []) if item]
    checkpoints = [normalize_text(item) for item in plan.get("checkpoints", []) if item]

    reference_steps = case["evaluation"].get("reference_workflow_steps", [])
    reference_tools = [canonical_tool_name(item) for item in case["evaluation"].get("reference_tools", []) if item]
    expected_deliverables = [normalize_text(item) for item in case["evaluation"].get("expected_deliverables", []) if item]

    step_recall = best_match_ratio(reference_steps, predicted_steps)
    step_precision = best_match_ratio(predicted_steps, reference_steps)
    if reference_tools:
        matched_tools = len(set(reference_tools) & set(predicted_tools))
        tool_alignment = round(matched_tools / len(set(reference_tools)), 4)
    else:
        tool_alignment = 1.0 if predicted_tools else 0.5

    if expected_deliverables:
        matched_deliverables = len(set(expected_deliverables) & set(predicted_deliverables))
        deliverable_alignment = round(matched_deliverables / len(set(expected_deliverables)), 4)
    else:
        deliverable_alignment = 1.0 if predicted_deliverables else 0.5

    validation_presence = 1.0 if any(word in " ".join(predicted_steps + checkpoints) for word in VALIDATION_WORDS) else 0.0
    completeness = 1.0 if len(predicted_steps) >= 3 and (predicted_tools or predicted_deliverables) else 0.0

    score = round(
        step_recall * 0.35
        + step_precision * 0.15
        + tool_alignment * 0.2
        + deliverable_alignment * 0.15
        + validation_presence * 0.1
        + completeness * 0.05,
        4,
    )

    detail = {
        "planning_mode": plan.get("planning_mode"),
        "step_recall": step_recall,
        "step_precision": step_precision,
        "tool_alignment": tool_alignment,
        "deliverable_alignment": deliverable_alignment,
        "validation_presence": validation_presence,
        "completeness": completeness,
        "predicted_steps": predicted_steps,
        "reference_steps": reference_steps,
        "predicted_tools": predicted_tools,
        "reference_tools": reference_tools,
        "predicted_deliverables": predicted_deliverables,
        "expected_deliverables": expected_deliverables,
        "checkpoints": checkpoints,
        "rationale": plan.get("rationale", ""),
    }
    return score, detail


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
        elif protocol == "open_workflow_planning":
            score, detail = await evaluate_open_workflow_planning(case, provider, agent)
            payload = {"task_seed": to_jsonable(case.get("task_seed", {}))}
        else:
            score, detail = 0.0, {"error": f"Unknown protocol: {protocol}"}
            payload = {}

        suite_scores.setdefault(case["suite"], []).append(score)
        row = {
            "case_id": case["case_id"],
            "suite": case["suite"],
            "protocol": protocol,
            "capability": case["capability"],
            "score": score,
            "detail": to_jsonable(detail),
            **payload,
        }
        if "tier" in case:
            row["tier"] = case["tier"]
            row["tier_rank"] = case.get("tier_rank")
            row["source_benchmark"] = case.get("source_benchmark")
        rows.append(row)

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
    output_path = OUTPUT_DIR / f"urbanworkflowbench_v1_2_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
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