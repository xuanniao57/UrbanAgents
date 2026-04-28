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
    # --- Original 3 cases (common_seed, preserved) ---
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
    original_cases = [
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

    # --- Helper: make a memory_continuity case ---
    def _mobility_seed(city: str, place_id: int) -> Dict[str, Any]:
        return {
            "task": {"task_type": "mobility_prediction", "city": city},
            "perception": {"type": "trajectory", "city": city},
            "action": {"predicted_location": place_id}
        }

    def _traffic_seed(city: str, phase: str) -> Dict[str, Any]:
        return {
            "task": {"task_type": "traffic_signal", "city": city},
            "perception": {"type": "text", "city": city},
            "action": {"selected_phase": phase}
        }

    def _nav_seed(start: str, end: str, route: List[str], city: str = "") -> Dict[str, Any]:
        t: Dict[str, Any] = {"task_type": "outdoor_navigation", "start": start, "end": end}
        if city:
            t["city"] = city
        return {
            "task": t,
            "perception": {"type": "text"} if not city else {"type": "text", "city": city},
            "action": {"route_actions": route}
        }

    def _explore_seed(city: str, dest: str, option: str = "A") -> Dict[str, Any]:
        return {
            "task": {"task_type": "urban_exploration", "city": city},
            "perception": {"type": "text", "city": city},
            "action": {"selected_option": option, "selected_destination": dest}
        }

    # =====================================================================
    # Expanded memory_continuity cases (20 new → total 23 with originals)
    # =====================================================================
    expanded: List[Dict[str, Any]] = []

    # --- mobility_prediction (6 cases) ---
    # easy: Tokyo, 1 relevant seed, 0 distractors
    expanded.append({
        "case_id": "memory_mobility_easy_tokyo_2",
        "suite": "memory_continuity", "protocol": "memory_probe",
        "capability": "memory_continuity", "source": "urbanagent_native",
        "memory_seed": [_mobility_seed("Tokyo", 36200)],
        "task": {"task_type": "mobility_prediction", "city": "Tokyo",
                 "historical_data": [], "context_stay": [], "target_stay": ["10:00 AM", "Monday", None]},
        "perception": {"flow_patterns": {}},
        "evaluation": {"expected": 36200}
    })
    # easy: London
    expanded.append({
        "case_id": "memory_mobility_easy_london_1",
        "suite": "memory_continuity", "protocol": "memory_probe",
        "capability": "memory_continuity", "source": "urbanagent_native",
        "memory_seed": [_mobility_seed("London", 50100)],
        "task": {"task_type": "mobility_prediction", "city": "London",
                 "historical_data": [], "context_stay": [], "target_stay": ["08:30 AM", "Wednesday", None]},
        "perception": {"flow_patterns": {}},
        "evaluation": {"expected": 50100}
    })
    # medium: NewYork target with distractors from Sydney and Mumbai
    expanded.append({
        "case_id": "memory_mobility_medium_newyork_1",
        "suite": "memory_continuity", "protocol": "memory_probe",
        "capability": "memory_continuity", "source": "urbanagent_native",
        "memory_seed": [
            _mobility_seed("Sydney", 60001),
            _mobility_seed("NewYork", 55000),
            _mobility_seed("Mumbai", 70001),
        ],
        "task": {"task_type": "mobility_prediction", "city": "NewYork",
                 "historical_data": [], "context_stay": [], "target_stay": ["07:00 AM", "Tuesday", None]},
        "perception": {"flow_patterns": {}},
        "evaluation": {"expected": 55000}
    })
    # medium: Sydney target with distractors
    expanded.append({
        "case_id": "memory_mobility_medium_sydney_1",
        "suite": "memory_continuity", "protocol": "memory_probe",
        "capability": "memory_continuity", "source": "urbanagent_native",
        "memory_seed": [
            _mobility_seed("London", 50200),
            _traffic_seed("Shanghai", "north_south"),
            _mobility_seed("Sydney", 60500),
        ],
        "task": {"task_type": "mobility_prediction", "city": "Sydney",
                 "historical_data": [], "context_stay": [], "target_stay": ["09:00 AM", "Thursday", None]},
        "perception": {"flow_patterns": {}},
        "evaluation": {"expected": 60500}
    })
    # hard: Mumbai — two seeds for same city, different place_ids, must pick latest
    expanded.append({
        "case_id": "memory_mobility_hard_mumbai_1",
        "suite": "memory_continuity", "protocol": "memory_probe",
        "capability": "memory_continuity", "source": "urbanagent_native",
        "memory_seed": [
            _mobility_seed("Mumbai", 70100),
            _mobility_seed("Mumbai", 70200),
            _mobility_seed("Tokyo", 36300),
            _traffic_seed("London", "east_west"),
        ],
        "task": {"task_type": "mobility_prediction", "city": "Mumbai",
                 "historical_data": [], "context_stay": [], "target_stay": ["06:00 PM", "Friday", None]},
        "perception": {"flow_patterns": {}},
        "evaluation": {"expected": 70200}
    })
    # hard: London — two London seeds + cross-task distractors
    expanded.append({
        "case_id": "memory_mobility_hard_london_2",
        "suite": "memory_continuity", "protocol": "memory_probe",
        "capability": "memory_continuity", "source": "urbanagent_native",
        "memory_seed": [
            _mobility_seed("London", 50300),
            _explore_seed("London", "Tower Bridge"),
            _mobility_seed("London", 50400),
            _nav_seed("King's Cross", "Paddington", ["forward", "right", "forward", "stop"], "London"),
        ],
        "task": {"task_type": "mobility_prediction", "city": "London",
                 "historical_data": [], "context_stay": [], "target_stay": ["05:30 PM", "Monday", None]},
        "perception": {"flow_patterns": {}},
        "evaluation": {"expected": 50400}
    })

    # --- traffic_signal (5 cases) ---
    # easy: Shanghai
    expanded.append({
        "case_id": "memory_traffic_easy_shanghai_1",
        "suite": "memory_continuity", "protocol": "memory_probe",
        "capability": "memory_continuity", "source": "urbanagent_native",
        "memory_seed": [_traffic_seed("Shanghai", "north_south")],
        "task": {"task_type": "traffic_signal", "city": "Shanghai",
                 "queue_lengths": {}, "phase_options": []},
        "perception": {"road_network": {}},
        "evaluation": {"expected_phase": "north_south", "expected": "north_south"}
    })
    # easy: Beijing
    expanded.append({
        "case_id": "memory_traffic_easy_beijing_1",
        "suite": "memory_continuity", "protocol": "memory_probe",
        "capability": "memory_continuity", "source": "urbanagent_native",
        "memory_seed": [_traffic_seed("Beijing", "east_west")],
        "task": {"task_type": "traffic_signal", "city": "Beijing",
                 "queue_lengths": {}, "phase_options": []},
        "perception": {"road_network": {}},
        "evaluation": {"expected_phase": "east_west", "expected": "east_west"}
    })
    # medium: London with distractors from CapeTown and Moscow
    expanded.append({
        "case_id": "memory_traffic_medium_london_1",
        "suite": "memory_continuity", "protocol": "memory_probe",
        "capability": "memory_continuity", "source": "urbanagent_native",
        "memory_seed": [
            _traffic_seed("CapeTown", "all_red"),
            _traffic_seed("London", "pedestrian_crossing"),
            _traffic_seed("Moscow", "left_turn_arrow"),
        ],
        "task": {"task_type": "traffic_signal", "city": "London",
                 "queue_lengths": {}, "phase_options": []},
        "perception": {"road_network": {}},
        "evaluation": {"expected_phase": "pedestrian_crossing", "expected": "pedestrian_crossing"}
    })
    # hard: Moscow — two seeds, same city, different phases
    expanded.append({
        "case_id": "memory_traffic_hard_moscow_1",
        "suite": "memory_continuity", "protocol": "memory_probe",
        "capability": "memory_continuity", "source": "urbanagent_native",
        "memory_seed": [
            _traffic_seed("Moscow", "north_south"),
            _traffic_seed("Moscow", "east_west"),
            _mobility_seed("Beijing", 10500),
            _explore_seed("Shanghai", "Yu Garden"),
        ],
        "task": {"task_type": "traffic_signal", "city": "Moscow",
                 "queue_lengths": {}, "phase_options": []},
        "perception": {"road_network": {}},
        "evaluation": {"expected_phase": "east_west", "expected": "east_west"}
    })
    # hard: CapeTown — two seeds + cross-task noise
    expanded.append({
        "case_id": "memory_traffic_hard_capetown_1",
        "suite": "memory_continuity", "protocol": "memory_probe",
        "capability": "memory_continuity", "source": "urbanagent_native",
        "memory_seed": [
            _traffic_seed("CapeTown", "all_red"),
            _nav_seed("Waterfront", "Table Mountain", ["forward", "left", "forward", "right", "stop"], "CapeTown"),
            _traffic_seed("CapeTown", "left_turn_arrow"),
        ],
        "task": {"task_type": "traffic_signal", "city": "CapeTown",
                 "queue_lengths": {}, "phase_options": []},
        "perception": {"road_network": {}},
        "evaluation": {"expected_phase": "left_turn_arrow", "expected": "left_turn_arrow"}
    })

    # --- outdoor_navigation (6 cases) ---
    # easy: Paris
    expanded.append({
        "case_id": "memory_navigation_easy_paris_1",
        "suite": "memory_continuity", "protocol": "memory_probe",
        "capability": "memory_continuity", "source": "urbanagent_native",
        "memory_seed": [_nav_seed("Gare du Nord", "Sacre Coeur", ["forward", "right", "forward", "left", "stop"], "Paris")],
        "task": {"task_type": "outdoor_navigation", "start": "Gare du Nord", "end": "Sacre Coeur", "steps": []},
        "perception": {"road_network": {}, "topology": {}},
        "evaluation": {"expected": ["forward", "right", "forward", "left", "stop"]}
    })
    # easy: Tokyo
    expanded.append({
        "case_id": "memory_navigation_easy_tokyo_1",
        "suite": "memory_continuity", "protocol": "memory_probe",
        "capability": "memory_continuity", "source": "urbanagent_native",
        "memory_seed": [_nav_seed("Shibuya Station", "Meiji Shrine", ["forward", "left", "forward", "stop"], "Tokyo")],
        "task": {"task_type": "outdoor_navigation", "start": "Shibuya Station", "end": "Meiji Shrine", "steps": []},
        "perception": {"road_network": {}, "topology": {}},
        "evaluation": {"expected": ["forward", "left", "forward", "stop"]}
    })
    # medium: NewYork with distractors
    expanded.append({
        "case_id": "memory_navigation_medium_newyork_1",
        "suite": "memory_continuity", "protocol": "memory_probe",
        "capability": "memory_continuity", "source": "urbanagent_native",
        "memory_seed": [
            _nav_seed("Eiffel Tower", "Arc de Triomphe", ["forward", "right", "stop"], "Paris"),
            _nav_seed("Times Square", "Central Park", ["forward", "forward", "left", "stop"], "NewYork"),
            _mobility_seed("NewYork", 55200),
        ],
        "task": {"task_type": "outdoor_navigation", "start": "Times Square", "end": "Central Park", "steps": []},
        "perception": {"road_network": {}, "topology": {}},
        "evaluation": {"expected": ["forward", "forward", "left", "stop"]}
    })
    # medium: London with distractors
    expanded.append({
        "case_id": "memory_navigation_medium_london_1",
        "suite": "memory_continuity", "protocol": "memory_probe",
        "capability": "memory_continuity", "source": "urbanagent_native",
        "memory_seed": [
            _traffic_seed("London", "north_south"),
            _nav_seed("Big Ben", "Buckingham Palace", ["forward", "right", "forward", "right", "stop"], "London"),
            _explore_seed("London", "British Museum"),
        ],
        "task": {"task_type": "outdoor_navigation", "start": "Big Ben", "end": "Buckingham Palace", "steps": []},
        "perception": {"road_network": {}, "topology": {}},
        "evaluation": {"expected": ["forward", "right", "forward", "right", "stop"]}
    })
    # hard: Beijing — two routes same endpoints, must pick latest
    expanded.append({
        "case_id": "memory_navigation_hard_beijing_2",
        "suite": "memory_continuity", "protocol": "memory_probe",
        "capability": "memory_continuity", "source": "urbanagent_native",
        "memory_seed": [
            _nav_seed("Tiananmen", "Temple of Heaven", ["forward", "left", "forward", "stop"], "Beijing"),
            _nav_seed("Tiananmen", "Temple of Heaven", ["forward", "right", "forward", "right", "stop"], "Beijing"),
            _mobility_seed("Beijing", 10800),
            _traffic_seed("Shanghai", "east_west"),
        ],
        "task": {"task_type": "outdoor_navigation", "start": "Tiananmen", "end": "Temple of Heaven", "steps": []},
        "perception": {"road_network": {}, "topology": {}},
        "evaluation": {"expected": ["forward", "right", "forward", "right", "stop"]}
    })
    # hard: Tokyo — two routes + cross-task noise
    expanded.append({
        "case_id": "memory_navigation_hard_tokyo_2",
        "suite": "memory_continuity", "protocol": "memory_probe",
        "capability": "memory_continuity", "source": "urbanagent_native",
        "memory_seed": [
            _nav_seed("Tokyo Station", "Imperial Palace", ["forward", "forward", "stop"], "Tokyo"),
            _explore_seed("Tokyo", "Senso-ji Temple"),
            _nav_seed("Tokyo Station", "Imperial Palace", ["forward", "left", "right", "forward", "stop"], "Tokyo"),
        ],
        "task": {"task_type": "outdoor_navigation", "start": "Tokyo Station", "end": "Imperial Palace", "steps": []},
        "perception": {"road_network": {}, "topology": {}},
        "evaluation": {"expected": ["forward", "left", "right", "forward", "stop"]}
    })

    # --- urban_exploration (6 cases) ---
    # easy: London
    expanded.append({
        "case_id": "memory_exploration_easy_london_1",
        "suite": "memory_continuity", "protocol": "memory_probe",
        "capability": "memory_continuity", "source": "urbanagent_native",
        "memory_seed": [_explore_seed("London", "British Museum")],
        "task": {"task_type": "urban_exploration", "city": "London",
                 "candidates": [
                     {"option": "A", "des_name": "British Museum", "completion": 1.0, "average_step": 3.0, "success_time": 10.0},
                     {"option": "B", "des_name": "Tower of London", "completion": 1.0, "average_step": 5.0, "success_time": 16.0},
                     {"option": "C", "des_name": "Hyde Park", "completion": 1.0, "average_step": 4.0, "success_time": 13.0},
                 ]},
        "perception": {"poi_categories": {}},
        "evaluation": {"expected": "British Museum"}
    })
    # easy: Tokyo
    expanded.append({
        "case_id": "memory_exploration_easy_tokyo_1",
        "suite": "memory_continuity", "protocol": "memory_probe",
        "capability": "memory_continuity", "source": "urbanagent_native",
        "memory_seed": [_explore_seed("Tokyo", "Senso-ji Temple")],
        "task": {"task_type": "urban_exploration", "city": "Tokyo",
                 "candidates": [
                     {"option": "A", "des_name": "Senso-ji Temple", "completion": 1.0, "average_step": 4.0, "success_time": 12.0},
                     {"option": "B", "des_name": "Meiji Shrine", "completion": 1.0, "average_step": 6.0, "success_time": 18.0},
                     {"option": "C", "des_name": "Ueno Park", "completion": 1.0, "average_step": 5.0, "success_time": 14.0},
                 ]},
        "perception": {"poi_categories": {}},
        "evaluation": {"expected": "Senso-ji Temple"}
    })
    # medium: NewYork with distractors
    expanded.append({
        "case_id": "memory_exploration_medium_newyork_1",
        "suite": "memory_continuity", "protocol": "memory_probe",
        "capability": "memory_continuity", "source": "urbanagent_native",
        "memory_seed": [
            _explore_seed("Paris", "Louvre"),
            _explore_seed("NewYork", "Metropolitan Museum"),
            _mobility_seed("NewYork", 55500),
        ],
        "task": {"task_type": "urban_exploration", "city": "NewYork",
                 "candidates": [
                     {"option": "A", "des_name": "Metropolitan Museum", "completion": 1.0, "average_step": 4.0, "success_time": 12.0},
                     {"option": "B", "des_name": "Brooklyn Bridge", "completion": 1.0, "average_step": 7.0, "success_time": 20.0},
                     {"option": "C", "des_name": "High Line Park", "completion": 1.0, "average_step": 5.0, "success_time": 15.0},
                 ]},
        "perception": {"poi_categories": {}},
        "evaluation": {"expected": "Metropolitan Museum"}
    })
    # medium: Shanghai with distractors
    expanded.append({
        "case_id": "memory_exploration_medium_shanghai_1",
        "suite": "memory_continuity", "protocol": "memory_probe",
        "capability": "memory_continuity", "source": "urbanagent_native",
        "memory_seed": [
            _traffic_seed("Shanghai", "east_west"),
            _explore_seed("Shanghai", "Yu Garden"),
            _nav_seed("The Bund", "Nanjing Road", ["forward", "right", "stop"], "Shanghai"),
        ],
        "task": {"task_type": "urban_exploration", "city": "Shanghai",
                 "candidates": [
                     {"option": "A", "des_name": "Yu Garden", "completion": 1.0, "average_step": 4.0, "success_time": 13.0},
                     {"option": "B", "des_name": "Oriental Pearl Tower", "completion": 1.0, "average_step": 6.0, "success_time": 17.0},
                     {"option": "C", "des_name": "Xintiandi", "completion": 1.0, "average_step": 5.0, "success_time": 15.0},
                 ]},
        "perception": {"poi_categories": {}},
        "evaluation": {"expected": "Yu Garden"}
    })
    # hard: Paris — two seeds same city, different dests
    expanded.append({
        "case_id": "memory_exploration_hard_paris_2",
        "suite": "memory_continuity", "protocol": "memory_probe",
        "capability": "memory_continuity", "source": "urbanagent_native",
        "memory_seed": [
            _explore_seed("Paris", "Musee d'Orsay", "A"),
            _explore_seed("Paris", "Jardin du Luxembourg", "B"),
            _mobility_seed("Paris", 33100),
            _traffic_seed("London", "north_south"),
        ],
        "task": {"task_type": "urban_exploration", "city": "Paris",
                 "candidates": [
                     {"option": "A", "des_name": "Musee d'Orsay", "completion": 1.0, "average_step": 4.0, "success_time": 12.0},
                     {"option": "B", "des_name": "Jardin du Luxembourg", "completion": 1.0, "average_step": 5.0, "success_time": 14.0},
                     {"option": "C", "des_name": "Montmartre", "completion": 1.0, "average_step": 6.0, "success_time": 18.0},
                 ]},
        "perception": {"poi_categories": {}},
        "evaluation": {"expected": "Jardin du Luxembourg"}
    })
    # hard: London — two dests + cross-task noise
    expanded.append({
        "case_id": "memory_exploration_hard_london_2",
        "suite": "memory_continuity", "protocol": "memory_probe",
        "capability": "memory_continuity", "source": "urbanagent_native",
        "memory_seed": [
            _explore_seed("London", "Tate Modern", "A"),
            _nav_seed("Westminster", "London Eye", ["forward", "left", "stop"], "London"),
            _explore_seed("London", "Camden Market", "B"),
        ],
        "task": {"task_type": "urban_exploration", "city": "London",
                 "candidates": [
                     {"option": "A", "des_name": "Tate Modern", "completion": 1.0, "average_step": 4.0, "success_time": 12.0},
                     {"option": "B", "des_name": "Camden Market", "completion": 1.0, "average_step": 5.0, "success_time": 14.0},
                     {"option": "C", "des_name": "Greenwich Park", "completion": 1.0, "average_step": 6.0, "success_time": 17.0},
                 ]},
        "perception": {"poi_categories": {}},
        "evaluation": {"expected": "Camden Market"}
    })

    return original_cases + expanded


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