"""Build UrbanWorkflowBench v1.0 manifest from CityData subset and UrbanAgent-native probes."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.benchmarks.run_citydata_quick_benchmark import CITYDATA_ROOT, CityDataQuickSampler, to_jsonable


OUTPUT_DIR = ROOT / "artifacts" / "benchmarks"


def build_external_cases(sample_count: int) -> List[Dict[str, Any]]:
    sampler = CityDataQuickSampler(CITYDATA_ROOT, seed=42)
    suite = sampler.build_suite(sample_count)
    selected_types = [
        ("geoqa", "spatial_understanding"),
        ("mobility_prediction", "recurrent_place_analysis"),
        ("outdoor_navigation", "route_reasoning"),
        ("urban_exploration", "destination_selection"),
    ]

    cases: List[Dict[str, Any]] = []
    for task_type, capability in selected_types:
        for index, task in enumerate(suite.get(task_type, []), start=1):
            cases.append({
                "case_id": f"external_{task_type}_{index}",
                "suite": "external_citydata_subset",
                "protocol": "agent_task",
                "capability": capability,
                "source": "citydata",
                "task": to_jsonable(task),
                "evaluation": {
                    "task_type": task_type,
                    "expected": to_jsonable(task.get("ground_truth")),
                    "expected_option": to_jsonable(task.get("ground_truth_option")),
                },
            })
    return cases


def build_dual_space_cases() -> List[Dict[str, Any]]:
    definitions = [
        {
            "case_id": "dual_space_contains_1",
            "capability": "dual_space_cognition",
            "expected_relation": "contains",
            "features": {
                "clusters": [{"id": 0, "count": 8, "density": 0.82, "centroid": [0.0, 0.0], "radius": 90.0}],
                "open_spaces": [{"type": "plaza", "area": 1200, "centroid": [45.0, 0.0], "shape_type": "square"}],
                "connectivity": {"average_degree": 2.2},
                "roads": {"dominant_orientation": 0, "orientation_entropy": 0.1},
                "spatial_patterns": {"grid_regularity": 0.4, "building_clustering": 0.7}
            }
        },
        {
            "case_id": "dual_space_aligned_1",
            "capability": "dual_space_cognition",
            "expected_relation": "aligned",
            "features": {
                "junctions": [
                    {"id": "j0", "degree": 4, "coordinates": [0.0, 0.0], "road_types": ["primary"]},
                    {"id": "j1", "degree": 3, "coordinates": [0.0, 180.0], "road_types": ["primary"]}
                ],
                "connectivity": {"average_degree": 3.5},
                "roads": {"dominant_orientation": 90, "orientation_entropy": 0.2},
                "spatial_patterns": {"grid_regularity": 0.8, "building_clustering": 0.2}
            }
        },
        {
            "case_id": "dual_space_separated_1",
            "capability": "dual_space_cognition",
            "expected_relation": "separated",
            "features": {
                "junctions": [{"id": "j0", "degree": 4, "coordinates": [0.0, 0.0], "road_types": ["primary"]}],
                "barriers": [{"type": "river", "description": "River barrier", "coordinates": [40.0, 0.0], "strength": 1.0}],
                "connectivity": {"average_degree": 2.0},
                "roads": {"dominant_orientation": 0, "orientation_entropy": 0.4},
                "spatial_patterns": {"grid_regularity": 0.3, "building_clustering": 0.1}
            }
        },
        {
            "case_id": "dual_space_adjacent_1",
            "capability": "dual_space_cognition",
            "expected_relation": "adjacent",
            "features": {
                "junctions": [
                    {"id": "j0", "degree": 4, "coordinates": [0.0, 0.0], "road_types": ["primary"]},
                    {"id": "j1", "degree": 4, "coordinates": [70.0, 20.0], "road_types": ["secondary"]}
                ],
                "connectivity": {"average_degree": 3.0},
                "roads": {"dominant_orientation": 20, "orientation_entropy": 0.3},
                "spatial_patterns": {"grid_regularity": 0.7, "building_clustering": 0.2}
            }
        },
        {
            "case_id": "dual_space_connected_1",
            "capability": "dual_space_cognition",
            "expected_relation": "connected",
            "features": {
                "junctions": [
                    {"id": "j0", "degree": 3, "coordinates": [0.0, 0.0], "road_types": ["primary"]},
                    {"id": "j1", "degree": 3, "coordinates": [220.0, 10.0], "road_types": ["secondary"]}
                ],
                "connectivity": {"average_degree": 2.8},
                "roads": {"dominant_orientation": 5, "orientation_entropy": 0.2},
                "spatial_patterns": {"grid_regularity": 0.5, "building_clustering": 0.2}
            }
        }
    ]

    return [
        {
            **definition,
            "suite": "dual_space_design",
            "protocol": "dual_space_probe",
            "source": "urbanagent_native",
        }
        for definition in definitions
    ]


def build_memory_cases() -> List[Dict[str, Any]]:
    common_seed = [
        {
            "task": {"task_type": "mobility_prediction", "city": "Tokyo", "target_stay": ["09:00 AM", "Saturday", None]},
            "perception": {"type": "trajectory", "city": "Tokyo"},
            "action": {"predicted_location": 36153}
        },
        {
            "task": {"task_type": "outdoor_navigation", "start": "Beijing route start", "end": "Beijing route destination"},
            "perception": {"type": "text", "city": "Beijing"},
            "action": {"route_actions": ["forward", "left", "forward", "stop"]}
        },
        {
            "task": {"task_type": "urban_exploration", "city": "Paris"},
            "perception": {"type": "text", "city": "Paris"},
            "action": {"selected_option": "A", "selected_destination": "Rue Mehul nearby"}
        }
    ]

    return [
        {
            "case_id": "memory_mobility_1",
            "suite": "memory_continuity",
            "protocol": "memory_probe",
            "capability": "memory_continuity",
            "source": "urbanagent_native",
            "memory_seed": common_seed,
            "task": {
                "task_type": "mobility_prediction",
                "city": "Tokyo",
                "historical_data": [],
                "context_stay": [],
                "target_stay": ["09:00 AM", "Saturday", None]
            },
            "perception": {"flow_patterns": {}},
            "evaluation": {"expected": 36153}
        },
        {
            "case_id": "memory_navigation_1",
            "suite": "memory_continuity",
            "protocol": "memory_probe",
            "capability": "memory_continuity",
            "source": "urbanagent_native",
            "memory_seed": common_seed,
            "task": {
                "task_type": "outdoor_navigation",
                "start": "Beijing route start",
                "end": "Beijing route destination",
                "steps": []
            },
            "perception": {"road_network": {}, "topology": {}},
            "evaluation": {"expected": ["forward", "left", "forward", "stop"]}
        },
        {
            "case_id": "memory_exploration_1",
            "suite": "memory_continuity",
            "protocol": "memory_probe",
            "capability": "memory_continuity",
            "source": "urbanagent_native",
            "memory_seed": common_seed,
            "task": {
                "task_type": "urban_exploration",
                "city": "Paris",
                "candidates": [
                    {"option": "A", "des_name": "Rue Mehul nearby", "completion": 1.0, "average_step": 4.0, "success_time": 12.0},
                    {"option": "B", "des_name": "Rue Alpha", "completion": 1.0, "average_step": 6.0, "success_time": 18.0},
                    {"option": "C", "des_name": "Rue Beta", "completion": 1.0, "average_step": 5.0, "success_time": 14.0}
                ]
            },
            "perception": {"poi_categories": {}},
            "evaluation": {"expected": "Rue Mehul nearby"}
        }
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-count", type=int, default=2)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = {
        "benchmark": "UrbanWorkflowBench",
        "version": "1.0",
        "created_at": datetime.now().isoformat(),
        "notes": [
            "Combines CityData subset reuse with UrbanAgent-native design probes.",
            "v1.0 focuses on dual-space cognition, memory continuity, and a workflow-aligned external subset.",
        ],
        "cases": build_external_cases(args.sample_count) + build_dual_space_cases() + build_memory_cases(),
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = OUTPUT_DIR / f"urbanworkflowbench_v1_manifest_{timestamp}.json"
    latest_path = OUTPUT_DIR / "urbanworkflowbench_v1_manifest_latest.json"
    payload = json.dumps(manifest, ensure_ascii=False, indent=2)
    output_path.write_text(payload, encoding="utf-8")
    latest_path.write_text(payload, encoding="utf-8")

    print(json.dumps({
        "output_path": str(output_path),
        "latest_path": str(latest_path),
        "case_count": len(manifest["cases"]),
        "suite_counts": {
            "external_citydata_subset": sum(1 for case in manifest["cases"] if case["suite"] == "external_citydata_subset"),
            "dual_space_design": sum(1 for case in manifest["cases"] if case["suite"] == "dual_space_design"),
            "memory_continuity": sum(1 for case in manifest["cases"] if case["suite"] == "memory_continuity"),
        }
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()