"""Build a curated open benchmark workflow task bank for UrbanWorkflowBench."""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


GEONALYSTBENCH_CSV = ROOT / "third_party" / "GeoAnalystBench" / "dataset" / "GeoAnalystBench.csv"
GEOBENCHX_JSON = ROOT / "third_party" / "GeoBenchX" / "benchmark_set" / "tasks_and_reference_solutions.json"
OUTPUT_PATH = ROOT / "benchmarks" / "urbanworkflowbench" / "v1_1" / "open_workflow_task_bank.json"


GEOANALYST_IDS = {
    1,   # urban heat
    2,   # bus stop access
    7,   # flooding impact
    8,   # fire station coverage
    23,  # open space + flood insurance
    29,  # tsunami travel time
    30,  # bike routes
    34,  # road accessibility
    37,  # social-media heat exposure
    42,  # Berlin Airbnb price pattern
    46,  # crash hotspots
    48,  # interest rates + location
    49,  # housing shortage impact
}


GEOBENCHX_KEYWORDS = [
    "city",
    "urban",
    "population",
    "railway",
    "road",
    "flood",
    "heatmap",
    "migration",
    "air quality",
    "accessibility",
    "bike",
    "travel time",
    "sprawl",
]


def normalize_workflow(raw: str) -> List[str]:
    steps: List[str] = []
    for line in (raw or "").splitlines():
        text = line.strip().strip('"')
        if not text:
            continue
        if text[0].isdigit() and "." in text:
            parts = text.split(".", 1)
            if len(parts) == 2:
                steps.append(parts[1].strip())
                continue
        steps.append(text)
    return steps


def build_geoanalystbench_tasks() -> List[Dict[str, Any]]:
    tasks: List[Dict[str, Any]] = []
    with GEONALYSTBENCH_CSV.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            task_id = int(row["id"])
            if task_id not in GEOANALYST_IDS:
                continue
            tasks.append({
                "task_id": f"geoanalystbench_{task_id}",
                "source_benchmark": "GeoAnalystBench",
                "source_license": "Apache-2.0",
                "source_file": "third_party/GeoAnalystBench/dataset/GeoAnalystBench.csv",
                "task_title": row["Task"],
                "task_instruction": row["Instruction"],
                "task_categories": [
                    value for value in [row["Task Categories1"], row["Task Categories2"], row["Task Categories3"]] if value
                ],
                "workflow_steps": normalize_workflow(row["Human Designed Workflow"]),
                "task_length": int(row["Task Length"]) if row.get("Task Length") else None,
                "dataset_description": row["Dataset Description"],
                "domain_knowledge": row["Domain Knowledge"],
                "open_source_code_or_task": row["Open Source"] == "T",
                "urbanworkflow_use": "workflow_task_seed",
                "recommended_suite": "external_open_workflow_subset",
            })
    return tasks


def geobenchx_matches(task_text: str) -> bool:
    text = (task_text or "").lower()
    return any(keyword in text for keyword in GEOBENCHX_KEYWORDS)


def build_geobenchx_tasks() -> List[Dict[str, Any]]:
    payload = json.loads(GEOBENCHX_JSON.read_text(encoding="utf-8"))
    tasks: List[Dict[str, Any]] = []
    for row in payload.get("tasks", []):
        task_text = row.get("task_text", "")
        labels = row.get("task_labels", [])
        if "Control question" in labels:
            continue
        if not geobenchx_matches(task_text):
            continue
        reference_steps = row.get("reference_solutions", [{}])[0].get("steps", [])
        tasks.append({
            "task_id": row["task_ID"],
            "source_benchmark": "GeoBenchX",
            "source_license": "MIT",
            "source_file": "third_party/GeoBenchX/benchmark_set/tasks_and_reference_solutions.json",
            "task_title": task_text,
            "task_instruction": task_text,
            "task_categories": labels,
            "workflow_steps": [step.get("function_name") for step in reference_steps],
            "reference_tool_steps": reference_steps,
            "dataset_description": "See GeoBenchX data catalog and benchmark_set reference solution datasets.",
            "open_source_code_or_task": True,
            "urbanworkflow_use": "workflow_task_seed",
            "recommended_suite": "external_open_workflow_subset",
        })
    return tasks


def main() -> None:
    bank = {
        "benchmark": "UrbanWorkflowBench Open Workflow Task Bank",
        "version": "2026-03-19",
        "created_at": datetime.now().isoformat(),
        "sources": [
            {
                "name": "CityBench",
                "status": "already integrated separately",
                "path": "third_party/CityBench-main",
            },
            {
                "name": "GeoAnalystBench",
                "status": "downloaded and curated",
                "path": "third_party/GeoAnalystBench",
            },
            {
                "name": "GeoBenchX",
                "status": "downloaded and curated",
                "path": "third_party/GeoBenchX",
            },
            {
                "name": "USTBench",
                "status": "no confirmed public task repository found",
            },
        ],
        "tasks": build_geoanalystbench_tasks() + build_geobenchx_tasks(),
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(bank, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output_path": str(OUTPUT_PATH),
        "task_count": len(bank["tasks"]),
        "geoanalystbench_count": sum(1 for task in bank["tasks"] if task["source_benchmark"] == "GeoAnalystBench"),
        "geobenchx_count": sum(1 for task in bank["tasks"] if task["source_benchmark"] == "GeoBenchX"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()