"""Design-focused ablation for dual-space cognition and memory-enabled reasoning."""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from legacy.urban_agent_legacy.cognition import SpatialCognition
from urban_agent.core.memory import MemoryModule
from urban_agent.core.reasoning import ReasoningModule


OUTPUT_DIR = ROOT / "artifacts" / "benchmarks"


@dataclass
class SyntheticContext:
    raw_features: Dict[str, Any]
    crs: str = "EPSG:3857"


def _vector_only_relation(node_a: Dict[str, Any], node_b: Dict[str, Any]) -> str | None:
    ax, ay = node_a["coordinates"]
    bx, by = node_b["coordinates"]
    distance = ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5
    if distance < 100:
        return "adjacent"
    if distance < 300:
        return "connected"
    return None


def _topology_only_relation(node_a: Dict[str, Any], node_b: Dict[str, Any], topology_edges: List[Tuple[str, str]]) -> str | None:
    edge = (node_a["id"], node_b["id"])
    reverse_edge = (node_b["id"], node_a["id"])
    if edge in topology_edges or reverse_edge in topology_edges:
        return "connected"
    return None


def run_dual_space_suite() -> Dict[str, Any]:
    cognition = SpatialCognition()
    scenarios = [
        {
            "name": "cluster_contains_plaza",
            "features": {
                "clusters": [{"id": 0, "count": 8, "density": 0.82, "centroid": (0.0, 0.0), "radius": 90.0}],
                "open_spaces": [{"type": "plaza", "area": 1200, "centroid": (45.0, 0.0), "shape_type": "square"}],
                "connectivity": {"average_degree": 2.2},
                "roads": {"dominant_orientation": 0, "orientation_entropy": 0.1},
                "spatial_patterns": {"grid_regularity": 0.4, "building_clustering": 0.7},
            },
            "expected_relation": "contains",
            "baseline_nodes": [
                {"id": "cluster_0", "coordinates": (0.0, 0.0)},
                {"id": "openspace_0", "coordinates": (45.0, 0.0)},
            ],
            "topology_edges": [],
        },
        {
            "name": "aligned_junctions",
            "features": {
                "junctions": [
                    {"id": "j0", "degree": 4, "coordinates": (0.0, 0.0), "road_types": ["primary"]},
                    {"id": "j1", "degree": 3, "coordinates": (0.0, 180.0), "road_types": ["primary"]},
                ],
                "connectivity": {"average_degree": 3.5},
                "roads": {"dominant_orientation": 90, "orientation_entropy": 0.2},
                "spatial_patterns": {"grid_regularity": 0.8, "building_clustering": 0.2},
            },
            "expected_relation": "aligned",
            "baseline_nodes": [
                {"id": "junction_0", "coordinates": (0.0, 0.0)},
                {"id": "junction_1", "coordinates": (0.0, 180.0)},
            ],
            "topology_edges": [("junction_0", "junction_1")],
        },
        {
            "name": "barrier_separation",
            "features": {
                "junctions": [{"id": "j0", "degree": 4, "coordinates": (0.0, 0.0), "road_types": ["primary"]}],
                "barriers": [{"type": "river", "description": "River barrier", "coordinates": (40.0, 0.0), "strength": 1.0}],
                "connectivity": {"average_degree": 2.0},
                "roads": {"dominant_orientation": 0, "orientation_entropy": 0.4},
                "spatial_patterns": {"grid_regularity": 0.3, "building_clustering": 0.1},
            },
            "expected_relation": "separated",
            "baseline_nodes": [
                {"id": "junction_0", "coordinates": (0.0, 0.0)},
                {"id": "barrier_0", "coordinates": (40.0, 0.0)},
            ],
            "topology_edges": [],
        },
        {
            "name": "adjacent_junctions",
            "features": {
                "junctions": [
                    {"id": "j0", "degree": 4, "coordinates": (0.0, 0.0), "road_types": ["primary"]},
                    {"id": "j1", "degree": 4, "coordinates": (70.0, 20.0), "road_types": ["secondary"]},
                ],
                "connectivity": {"average_degree": 3.0},
                "roads": {"dominant_orientation": 20, "orientation_entropy": 0.3},
                "spatial_patterns": {"grid_regularity": 0.7, "building_clustering": 0.2},
            },
            "expected_relation": "adjacent",
            "baseline_nodes": [
                {"id": "junction_0", "coordinates": (0.0, 0.0)},
                {"id": "junction_1", "coordinates": (70.0, 20.0)},
            ],
            "topology_edges": [("junction_0", "junction_1")],
        },
        {
            "name": "connected_junctions",
            "features": {
                "junctions": [
                    {"id": "j0", "degree": 3, "coordinates": (0.0, 0.0), "road_types": ["primary"]},
                    {"id": "j1", "degree": 3, "coordinates": (220.0, 10.0), "road_types": ["secondary"]},
                ],
                "connectivity": {"average_degree": 2.8},
                "roads": {"dominant_orientation": 5, "orientation_entropy": 0.2},
                "spatial_patterns": {"grid_regularity": 0.5, "building_clustering": 0.2},
            },
            "expected_relation": "connected",
            "baseline_nodes": [
                {"id": "junction_0", "coordinates": (0.0, 0.0)},
                {"id": "junction_1", "coordinates": (220.0, 10.0)},
            ],
            "topology_edges": [("junction_0", "junction_1")],
        },
    ]

    rows = []
    full_correct = 0
    vector_correct = 0
    topo_correct = 0
    full_mapping = 0

    for scenario in scenarios:
        result = cognition.understand(SyntheticContext(scenario["features"]), scenario["name"])
        relations = [relation["type"] for relation in result["topological_graph"]["relations"]]
        predicted_full = scenario["expected_relation"] if scenario["expected_relation"] in relations else None
        predicted_vector = _vector_only_relation(*scenario["baseline_nodes"])
        predicted_topology = _topology_only_relation(*scenario["baseline_nodes"], scenario["topology_edges"])
        mapping_complete = len(result["vector_mapping"]["relation_geometries"]) > 0

        full_correct += int(predicted_full == scenario["expected_relation"])
        vector_correct += int(predicted_vector == scenario["expected_relation"])
        topo_correct += int(predicted_topology == scenario["expected_relation"])
        full_mapping += int(mapping_complete)

        rows.append({
            "scenario": scenario["name"],
            "expected_relation": scenario["expected_relation"],
            "dual_space_prediction": predicted_full,
            "vector_only_prediction": predicted_vector,
            "topology_only_prediction": predicted_topology,
            "mapping_complete": mapping_complete,
            "relation_types": relations,
        })

    total = len(scenarios)
    return {
        "suite": "dual_space_cognition",
        "summary": {
            "dual_space_accuracy": round(full_correct / total, 4),
            "vector_only_accuracy": round(vector_correct / total, 4),
            "topology_only_accuracy": round(topo_correct / total, 4),
            "mapping_completeness": round(full_mapping / total, 4),
        },
        "rows": rows,
    }


async def run_memory_suite() -> Dict[str, Any]:
    memory = MemoryModule(config={"short_term_size": 10})
    reasoning = ReasoningModule(config={"mode": "enhanced"})

    experiences = [
        {
            "task": {
                "task_type": "mobility_prediction",
                "city": "Tokyo",
                "target_stay": ("09:00 AM", "Saturday", None),
            },
            "perception": {"type": "trajectory", "city": "Tokyo"},
            "reasoning": {"predicted_location": 36153},
            "action": {"predicted_location": 36153},
        },
        {
            "task": {
                "task_type": "outdoor_navigation",
                "start": "Beijing route start",
                "end": "Beijing route destination",
            },
            "perception": {"type": "text", "city": "Beijing"},
            "reasoning": {"route_actions": ["forward", "left", "forward", "stop"]},
            "action": {"route_actions": ["forward", "left", "forward", "stop"]},
        },
        {
            "task": {
                "task_type": "urban_exploration",
                "city": "Paris",
            },
            "perception": {"type": "text", "city": "Paris"},
            "reasoning": {"selected_destination": "Rue Mehul nearby"},
            "action": {"selected_option": "A", "selected_destination": "Rue Mehul nearby"},
        },
    ]

    for experience in experiences:
        await memory.store(experience)

    cases = [
        {
            "name": "mobility_memory_transfer",
            "perception": {"flow_patterns": {}},
            "task": {
                "task_type": "mobility_prediction",
                "city": "Tokyo",
                "historical_data": [],
                "context_stay": [],
                "target_stay": ("09:00 AM", "Saturday", None),
            },
            "expected": 36153,
            "extractor": lambda result: result.get("predicted_location"),
        },
        {
            "name": "navigation_memory_transfer",
            "perception": {"road_network": {}, "topology": {}},
            "task": {
                "task_type": "outdoor_navigation",
                "start": "Beijing route start",
                "end": "Beijing route destination",
                "steps": [],
            },
            "expected": ["forward", "left", "forward", "stop"],
            "extractor": lambda result: result.get("route_actions"),
        },
        {
            "name": "exploration_memory_transfer",
            "perception": {"poi_categories": {}},
            "task": {
                "task_type": "urban_exploration",
                "city": "Paris",
                "candidates": [
                    {"option": "A", "des_name": "Rue Mehul nearby", "completion": 1.0, "average_step": 4.0, "success_time": 12.0},
                    {"option": "B", "des_name": "Rue Alpha", "completion": 1.0, "average_step": 6.0, "success_time": 18.0},
                    {"option": "C", "des_name": "Rue Beta", "completion": 1.0, "average_step": 5.0, "success_time": 14.0},
                ],
            },
            "expected": "Rue Mehul nearby",
            "extractor": lambda result: result.get("exploration_plan", {}).get("selected_destination"),
        },
    ]

    rows = []
    with_memory_correct = 0
    without_memory_correct = 0

    for case in cases:
        without_memory = await reasoning.infer(case["perception"], {}, case["task"])
        memory_context = await memory.retrieve(case["task"])
        with_memory = await reasoning.infer(case["perception"], memory_context, case["task"])

        plain_value = case["extractor"](without_memory)
        memory_value = case["extractor"](with_memory)
        without_memory_correct += int(plain_value == case["expected"])
        with_memory_correct += int(memory_value == case["expected"])

        rows.append({
            "case": case["name"],
            "expected": case["expected"],
            "without_memory": plain_value,
            "with_memory": memory_value,
            "memory_query_summary": memory_context.get("query_summary", {}),
        })

    total = len(cases)
    return {
        "suite": "memory_enabled_reasoning",
        "summary": {
            "without_memory_accuracy": round(without_memory_correct / total, 4),
            "with_memory_accuracy": round(with_memory_correct / total, 4),
            "memory_gain": round((with_memory_correct - without_memory_correct) / total, 4),
        },
        "rows": rows,
    }


async def main() -> None:
    dual_space = run_dual_space_suite()
    memory_suite = await run_memory_suite()
    report = {
        "timestamp": datetime.now().isoformat(),
        "benchmark": "urbanagent_design_ablation",
        "suites": [dual_space, memory_suite],
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"urbanagent_design_ablation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output_path": str(output_path),
        "dual_space": dual_space["summary"],
        "memory": memory_suite["summary"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())