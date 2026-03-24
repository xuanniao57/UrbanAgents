"""Build UrbanWorkflowBench v1.2 manifest with layered open workflow suites."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.benchmarks.build_urbanworkflowbench_v1_1 import (
    EXTERNAL_TASKS,
    build_dual_space_cases,
    build_external_cases,
    build_hitl_cases,
    build_memory_cases,
    build_tool_orchestration_cases,
    parse_task_types,
)


OUTPUT_DIR = ROOT / "artifacts" / "benchmarks"
BANK_PATH = ROOT / "benchmarks" / "urbanworkflowbench" / "v1_1" / "open_workflow_task_bank.json"

OPEN_PROFILES = {
    "official": [1, 2],
    "fullbank": [1, 2, 3],
}

OPEN_SUITE_NAMES = {
    1: "external_open_workflow_t1_core",
    2: "external_open_workflow_t2_standard",
    3: "external_open_workflow_t3_challenge",
}

CORE_GEOBENCHX_COUNT = 11
STANDARD_GEOBENCHX_COUNT = 36

TOOL_KEYWORDS = {
    "load_data": ["load", "read", "import", "prepare data", "dataset"],
    "filter_features": ["filter", "select", "subset"],
    "buffer": ["buffer"],
    "overlay_analysis": ["overlay", "intersect", "intersection", "union"],
    "clip": ["clip", "extract by mask", "extract"],
    "spatial_join": ["join", "merge", "relate"],
    "interpolation": ["kriging", "interpolate", "interpolation"],
    "aggregate_stats": ["aggregate", "average", "summarize", "zonal", "mean"],
    "network_analysis": ["network", "route", "travel time", "accessibility", "service area"],
    "raster_calculation": ["raster calculation", "raster", "map algebra"],
    "hotspot_analysis": ["hotspot", "cluster", "heat island", "sprawl"],
    "classification": ["classify", "normalize", "score", "weighted overlay"],
    "visualization": ["visualization", "visualize", "choropleth", "map", "plot", "highlight"],
    "reporting": ["report", "table", "summary", "narrative"],
}

TIER_KEYWORDS = {
    "urban": 6,
    "city": 6,
    "population": 5,
    "flood": 5,
    "road": 4,
    "railway": 4,
    "accessibility": 4,
    "bike": 4,
    "air quality": 4,
    "sprawl": 4,
    "migration": 3,
    "travel time": 3,
    "heat": 3,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-count", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--external-task-types",
        default=",".join(EXTERNAL_TASKS.keys()),
        help="Comma-separated external task types",
    )
    parser.add_argument(
        "--open-workflow-profile",
        choices=sorted(OPEN_PROFILES.keys()),
        default="official",
        help="Open workflow profile to include in the manifest",
    )
    return parser.parse_args()


def normalize_text(text: str) -> str:
    lowered = (text or "").lower().strip()
    lowered = re.sub(r"[^a-z0-9\s]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def collect_text(task: Dict[str, Any]) -> str:
    parts = [
        task.get("task_title", ""),
        task.get("task_instruction", ""),
        " ".join(task.get("task_categories", [])),
        " ".join(task.get("workflow_steps", [])),
    ]
    return normalize_text(" ".join(parts))


def canonical_tool_name(raw_name: str) -> str:
    text = normalize_text(raw_name)
    for tool_name, keywords in TOOL_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return tool_name
    return text.replace(" ", "_") if text else "unknown_tool"


def infer_reference_tools(task: Dict[str, Any]) -> List[str]:
    tools: List[str] = []
    for step in task.get("reference_tool_steps", []):
        function_name = step.get("function_name")
        if function_name:
            tools.append(canonical_tool_name(function_name))
    if tools:
        return list(dict.fromkeys(tools))

    for step in task.get("workflow_steps", []):
        tool = canonical_tool_name(step)
        if tool != "unknown_tool":
            tools.append(tool)
    return list(dict.fromkeys(tools))


def infer_expected_deliverables(task: Dict[str, Any]) -> List[str]:
    text = " ".join([
        task.get("task_title", ""),
        task.get("task_instruction", ""),
        " ".join(task.get("workflow_steps", [])),
    ])
    lowered = text.lower()
    deliverables: List[str] = []

    for extension in re.findall(r"\.([a-z0-9]+)", lowered):
        if extension in {"png", "svg", "geojson", "json", "csv", "pdf", "md"}:
            deliverables.append(extension)

    keyword_deliverables = {
        "choropleth": "map",
        "map": "map",
        "visualization": "figure",
        "plot": "figure",
        "report": "report",
        "table": "table",
        "dashboard": "dashboard",
    }
    for keyword, deliverable in keyword_deliverables.items():
        if keyword in lowered:
            deliverables.append(deliverable)

    return list(dict.fromkeys(deliverables)) or ["report"]


def geobenchx_priority(task: Dict[str, Any]) -> float:
    text = collect_text(task)
    score = 0.0
    for keyword, weight in TIER_KEYWORDS.items():
        if keyword in text:
            score += weight
    score += min(len(task.get("workflow_steps", [])), 8) * 0.15
    score += min(len(task.get("reference_tool_steps", [])), 6) * 0.25
    if "urban" in text or "city" in text:
        score += 2.0
    return round(score, 4)


def assign_open_tiers(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    geoanalyst = []
    geobenchx = []
    for task in tasks:
        task_copy = dict(task)
        if task_copy.get("source_benchmark") == "GeoAnalystBench":
            task_copy["tier_rank"] = 1
            task_copy["tier"] = "t1_core"
            task_copy["tier_reason"] = "curated urban workflow anchor task"
            geoanalyst.append(task_copy)
        else:
            task_copy["priority_score"] = geobenchx_priority(task_copy)
            geobenchx.append(task_copy)

    geobenchx.sort(key=lambda item: (-item["priority_score"], item.get("task_id", "")))
    for index, task in enumerate(geobenchx):
        if index < CORE_GEOBENCHX_COUNT:
            task["tier_rank"] = 1
            task["tier"] = "t1_core"
            task["tier_reason"] = "highest-signal urban workflow case"
        elif index < CORE_GEOBENCHX_COUNT + STANDARD_GEOBENCHX_COUNT:
            task["tier_rank"] = 2
            task["tier"] = "t2_standard"
            task["tier_reason"] = "broad official urban workflow coverage"
        else:
            task["tier_rank"] = 3
            task["tier"] = "t3_challenge"
            task["tier_reason"] = "long-tail challenge workflow case"

    return geoanalyst + geobenchx


def load_open_bank() -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    bank = json.loads(BANK_PATH.read_text(encoding="utf-8"))
    tasks = assign_open_tiers(bank.get("tasks", []))
    return bank, tasks


def build_open_workflow_cases(profile: str) -> List[Dict[str, Any]]:
    _, tasks = load_open_bank()
    included_tiers = set(OPEN_PROFILES[profile])
    cases: List[Dict[str, Any]] = []

    for task in tasks:
        tier_rank = int(task["tier_rank"])
        if tier_rank not in included_tiers:
            continue
        cases.append({
            "case_id": f"open_{task['task_id']}",
            "suite": OPEN_SUITE_NAMES[tier_rank],
            "protocol": "open_workflow_planning",
            "capability": "workflow_planning",
            "source": "open_benchmark",
            "source_benchmark": task.get("source_benchmark"),
            "tier": task.get("tier"),
            "tier_rank": tier_rank,
            "task_seed": task,
            "evaluation": {
                "reference_workflow_steps": task.get("workflow_steps", []),
                "reference_tools": infer_reference_tools(task),
                "expected_deliverables": infer_expected_deliverables(task),
                "task_categories": task.get("task_categories", []),
            },
        })
    return cases


def summarize_open_cases(cases: List[Dict[str, Any]]) -> Dict[str, int]:
    summary: Dict[str, int] = {}
    for case in cases:
        summary[case["suite"]] = summary.get(case["suite"], 0) + 1
    return summary


def main() -> None:
    args = parse_args()
    task_types = parse_task_types(args.external_task_types)
    open_cases = build_open_workflow_cases(args.open_workflow_profile)
    cases = (
        build_external_cases(args.sample_count, args.seed, task_types)
        + build_dual_space_cases()
        + build_memory_cases()
        + build_tool_orchestration_cases()
        + build_hitl_cases()
        + open_cases
    )

    manifest = {
        "benchmark": "UrbanWorkflowBench",
        "version": "1.2",
        "created_at": datetime.now().isoformat(),
        "notes": [
            "v1.2 keeps v1.1 native suites and formally integrates the layered open workflow task bank.",
            "Open workflow planning is evaluated against hidden reference workflow steps, reference tools, and expected deliverables.",
            f"Open workflow profile: {args.open_workflow_profile}.",
        ],
        "config": {
            "sample_count": args.sample_count,
            "seed": args.seed,
            "external_task_types": task_types,
            "open_workflow_profile": args.open_workflow_profile,
            "open_suite_counts": summarize_open_cases(open_cases),
        },
        "cases": cases,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    profile = args.open_workflow_profile
    output_path = OUTPUT_DIR / f"urbanworkflowbench_v1_2_manifest_{profile}_{timestamp}.json"
    latest_path = OUTPUT_DIR / "urbanworkflowbench_v1_2_manifest_latest.json"
    profile_latest_path = OUTPUT_DIR / f"urbanworkflowbench_v1_2_manifest_{profile}_latest.json"
    payload = json.dumps(manifest, ensure_ascii=False, indent=2)
    output_path.write_text(payload, encoding="utf-8")
    profile_latest_path.write_text(payload, encoding="utf-8")
    if profile == "official":
        latest_path.write_text(payload, encoding="utf-8")

    suite_names = [
        "external_citydata_subset",
        "dual_space_design",
        "memory_continuity",
        "tool_orchestration",
        "hitl_checkpoint",
        "external_open_workflow_t1_core",
        "external_open_workflow_t2_standard",
        "external_open_workflow_t3_challenge",
    ]
    print(json.dumps({
        "output_path": str(output_path),
        "latest_path": str(latest_path) if profile == "official" else str(profile_latest_path),
        "profile_latest_path": str(profile_latest_path),
        "case_count": len(cases),
        "suite_counts": {
            suite_name: sum(1 for case in cases if case["suite"] == suite_name)
            for suite_name in suite_names
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
