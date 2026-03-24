"""Build UrbanWorkflowBench v1.1 manifest."""

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
EXTERNAL_TASKS = {
    "geoqa": "spatial_understanding",
    "mobility_prediction": "recurrent_place_analysis",
    "outdoor_navigation": "route_reasoning",
    "urban_exploration": "destination_selection",
}


def parse_task_types(raw: str) -> List[str]:
    task_types = [item.strip() for item in raw.split(",") if item.strip()]
    invalid = [task_type for task_type in task_types if task_type not in EXTERNAL_TASKS]
    if invalid:
        raise ValueError(f"Unsupported external task types: {invalid}")
    return task_types


def build_external_cases(sample_count: int, seed: int, task_types: List[str]) -> List[Dict[str, Any]]:
    sampler = CityDataQuickSampler(CITYDATA_ROOT, seed=seed)
    suite = sampler.build_suite(sample_count)
    cases: List[Dict[str, Any]] = []
    for task_type in task_types:
        capability = EXTERNAL_TASKS[task_type]
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
    return [{**definition, "suite": "dual_space_design", "protocol": "dual_space_probe", "source": "urbanagent_native"} for definition in definitions]


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


def build_tool_orchestration_cases() -> List[Dict[str, Any]]:
    return [
        {
            "case_id": "tool_orchestration_poi_lookup_1",
            "suite": "tool_orchestration",
            "protocol": "tool_orchestration_probe",
            "capability": "tool_orchestration",
            "source": "urbanagent_native",
            "tool_steps": [
                {"tool": "geocode", "params": {"address": "People's Square, Shanghai"}, "expect_success": True},
                {"tool": "get_poi", "params": {"location": [31.2304, 121.4737], "radius": 800, "category": "park"}, "expect_success": True}
            ],
            "workflow_expectation": {
                "expected_tools": ["geocode", "get_poi"],
                "required_successes": 2,
                "require_sequence_match": True,
                "recovery_expected": False
            }
        },
        {
            "case_id": "tool_orchestration_osm_analysis_1",
            "suite": "tool_orchestration",
            "protocol": "tool_orchestration_probe",
            "capability": "tool_orchestration",
            "source": "urbanagent_native",
            "tool_steps": [
                {"tool": "query_osm", "params": {"bbox": [121.46, 31.22, 121.49, 31.24], "tags": ["highway", "building"]}, "expect_success": True},
                {"tool": "spatial_analysis", "params": {"geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}, "operation": "connectivity"}, "expect_success": True}
            ],
            "workflow_expectation": {
                "expected_tools": ["query_osm", "spatial_analysis"],
                "required_successes": 2,
                "require_sequence_match": True,
                "recovery_expected": False
            }
        },
        {
            "case_id": "tool_orchestration_recovery_1",
            "suite": "tool_orchestration",
            "protocol": "tool_orchestration_probe",
            "capability": "tool_orchestration_recovery",
            "source": "urbanagent_native",
            "tool_steps": [
                {"tool": "missing_tool", "params": {"foo": "bar"}, "expect_success": False},
                {"tool": "geocode", "params": {"address": "Xujiahui, Shanghai"}, "expect_success": True},
                {"tool": "calculate_distance", "params": {"point1": [31.2304, 121.4737], "point2": [31.2000, 121.4300]}, "expect_success": True}
            ],
            "workflow_expectation": {
                "expected_tools": ["missing_tool", "geocode", "calculate_distance"],
                "required_successes": 2,
                "require_sequence_match": True,
                "recovery_expected": True
            }
        }
    ]


def build_hitl_cases() -> List[Dict[str, Any]]:
    return [
        {
            "case_id": "hitl_scope_modify_1",
            "suite": "hitl_checkpoint",
            "protocol": "hitl_checkpoint_probe",
            "capability": "human_checkpoint_controllability",
            "source": "urbanagent_native",
            "state": {
                "task_interpretation": {"task_type": "walkability_assessment", "location": "Shanghai, China", "radius": 500},
                "data_plan": {"osm_layers": ["highway", "building", "amenity"]},
                "selected_proposals": []
            },
            "checkpoint_flow": [
                {"checkpoint_id": "dp-1", "action": "modify", "patch": {"task_interpretation": {"location": "Shanghai Inner Ring", "radius": 800}}},
                {"checkpoint_id": "dp-2", "action": "approve"}
            ],
            "evaluation": {
                "expected_final": {"task_interpretation": {"location": "Shanghai Inner Ring", "radius": 800}},
                "cancelled": False
            }
        },
        {
            "case_id": "hitl_proposal_reselect_1",
            "suite": "hitl_checkpoint",
            "protocol": "hitl_checkpoint_probe",
            "capability": "human_checkpoint_controllability",
            "source": "urbanagent_native",
            "state": {
                "task_interpretation": {"task_type": "connectivity_analysis", "location": "Beijing", "radius": 600},
                "selected_proposals": ["add_flyover"],
                "proposal_pool": ["add_flyover", "add_crosswalk", "add_green_link"]
            },
            "checkpoint_flow": [
                {"checkpoint_id": "dp-4", "action": "modify", "patch": {"selected_proposals": ["add_crosswalk", "add_green_link"]}}
            ],
            "evaluation": {
                "expected_final": {"selected_proposals": ["add_crosswalk", "add_green_link"]},
                "cancelled": False
            }
        },
        {
            "case_id": "hitl_cancel_1",
            "suite": "hitl_checkpoint",
            "protocol": "hitl_checkpoint_probe",
            "capability": "human_checkpoint_controllability",
            "source": "urbanagent_native",
            "state": {
                "task_interpretation": {"task_type": "general_analysis", "location": "Paris", "radius": 400}
            },
            "checkpoint_flow": [
                {"checkpoint_id": "dp-1", "action": "reject"}
            ],
            "evaluation": {
                "expected_final": {},
                "cancelled": True
            }
        }
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-count", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--external-task-types",
        default=",".join(EXTERNAL_TASKS.keys()),
        help="Comma-separated external task types",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    task_types = parse_task_types(args.external_task_types)
    cases = (
        build_external_cases(args.sample_count, args.seed, task_types)
        + build_dual_space_cases()
        + build_memory_cases()
        + build_tool_orchestration_cases()
        + build_hitl_cases()
    )
    manifest = {
        "benchmark": "UrbanWorkflowBench",
        "version": "1.1",
        "created_at": datetime.now().isoformat(),
        "notes": [
            "v1.1 adds tool orchestration and HITL checkpoint probes.",
            "External CityData sampling is configurable by task type and per-task sample count.",
        ],
        "config": {
            "sample_count": args.sample_count,
            "seed": args.seed,
            "external_task_types": task_types,
        },
        "cases": cases,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = OUTPUT_DIR / f"urbanworkflowbench_v1_1_manifest_{timestamp}.json"
    latest_path = OUTPUT_DIR / "urbanworkflowbench_v1_1_manifest_latest.json"
    payload = json.dumps(manifest, ensure_ascii=False, indent=2)
    output_path.write_text(payload, encoding="utf-8")
    latest_path.write_text(payload, encoding="utf-8")

    print(json.dumps({
        "output_path": str(output_path),
        "latest_path": str(latest_path),
        "case_count": len(cases),
        "suite_counts": {
            suite_name: sum(1 for case in cases if case["suite"] == suite_name)
            for suite_name in [
                "external_citydata_subset",
                "dual_space_design",
                "memory_continuity",
                "tool_orchestration",
                "hitl_checkpoint",
            ]
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()