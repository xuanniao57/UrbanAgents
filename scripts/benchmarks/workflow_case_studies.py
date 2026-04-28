"""
Workflow Case Studies — RMDA-style 端到端多步骤工作流

Case Study 1: Urban Walkability Assessment (城市步行适宜性评估)
  OSM数据获取 → 拓扑构建 → 可达性分析 → 密度计算 → SVG可视化 → 分析报告

Case Study 2: Mobility Pattern Analysis (出行模式分析)
  轨迹数据感知 → 时空记忆 → 模式推理 → 预测验证 → 生成报告

这两个 case study 类似于 RMDA 的 urban planning + stormwater analysis,
展示 UrbanAgent 在实际端到端工作流中的完整能力。

Usage:
    python workflow_case_studies.py --case walkability
    python workflow_case_studies.py --case mobility
    python workflow_case_studies.py --case all
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from urban_agent.agents.orchestrator import MultiAgentOrchestrator
from urban_agent.agents.efficiency import EfficiencyTracker

OUTPUT_DIR = ROOT / "artifacts" / "case_studies"


# ---------------------------------------------------------------------------
# Case Study 1: Urban Walkability Assessment
# ---------------------------------------------------------------------------

WALKABILITY_WORKFLOW = {
    "case_id": "cs_walkability_01",
    "title": "Urban Walkability Assessment — Marais District, Paris",
    "description": (
        "End-to-end urban walkability assessment demonstrating the full "
        "multi-agent pipeline: data acquisition → spatial cognition → "
        "multi-criteria analysis → visualization → reporting."
    ),
    "steps": [
        {
            "step": 1,
            "name": "Data Acquisition",
            "agent": "perception",
            "tool": "fetch_osm_data",
            "description": "Fetch road network, buildings, and POIs for Le Marais, Paris",
            "input": {
                "location": "Le Marais, Paris, France",
                "radius": 800,
                "data_types": ["roads", "buildings", "pois"],
            },
            "expected_output": "GeoJSON features for roads, buildings, POIs",
        },
        {
            "step": 2,
            "name": "Topology Construction",
            "agent": "analyst",
            "tool": "build_topology",
            "description": "Build topological graph from spatial features",
            "input": {"features": "{step_1_output}", "relation_threshold": 100},
            "expected_output": "TopologicalGraph with nodes and relations",
            "dual_space": True,
        },
        {
            "step": 3,
            "name": "Network Connectivity",
            "agent": "analyst",
            "tool": "analyze_connectivity",
            "description": "Analyze road network connectivity and identify dead-ends",
            "input": {"road_graph": "{step_2_output}"},
            "expected_output": "Connectivity metrics: avg_degree, connected_components, dead_ends",
        },
        {
            "step": 4,
            "name": "Accessibility Analysis",
            "agent": "analyst",
            "tool": "measure_accessibility",
            "description": "Measure building-to-POI accessibility (walk distance)",
            "input": {
                "buildings": "{step_1_output.buildings}",
                "target_points": "{step_1_output.pois}",
                "max_distance": 500,
            },
            "expected_output": "Accessibility scores per building",
        },
        {
            "step": 5,
            "name": "Density Mapping",
            "agent": "analyst",
            "tool": "calculate_density",
            "description": "Calculate building density distribution on 100m grid",
            "input": {"buildings": "{step_1_output.buildings}", "grid_size": 100},
            "expected_output": "Density grid with values",
        },
        {
            "step": 6,
            "name": "Synthesis & Visualization",
            "agent": "cartographer",
            "tool": "generate_svg_overlay",
            "description": "Generate walkability heatmap SVG overlay",
            "input": {
                "base_features": "{step_1_output}",
                "interventions": [
                    {"type": "walkability_score", "data": "{step_4_output}"},
                    {"type": "density_overlay", "data": "{step_5_output}"},
                ],
                "bbox": [2.349, 48.853, 2.367, 48.863],
                "width": 1000,
            },
            "expected_output": "SVG string with walkability visualization",
        },
        {
            "step": 7,
            "name": "Review & QC",
            "agent": "spatial_reviewer",
            "tool": None,
            "description": "Spatial validity review + quality control confidence check",
            "expected_output": "QualityReport with confidence score",
            "qc_check": True,
        },
        {
            "step": 8,
            "name": "Report Generation",
            "agent": "reporter",
            "tool": "generate_measurement_report",
            "description": "Generate structured walkability assessment report",
            "input": {
                "baseline": "{step_3_output}",
                "proposals": [
                    {"name": "Current walkability", "metrics": "{step_4_output}"},
                    {"name": "Density context", "metrics": "{step_5_output}"},
                ],
            },
            "expected_output": "Markdown report with metrics, charts references, and recommendations",
        },
    ],
    "evaluation_criteria": {
        "completeness": "All 8 steps completed successfully",
        "spatial_accuracy": "Coordinate system consistent (EPSG:4326/3857)",
        "tool_usage": "≥5 unique tools used",
        "dual_space": "Topology + vector dual-space cognition activated",
        "quality_gate": "QC confidence ≥ 0.75",
    },
}


# ---------------------------------------------------------------------------
# Case Study 2: Mobility Pattern Analysis
# ---------------------------------------------------------------------------

MOBILITY_WORKFLOW = {
    "case_id": "cs_mobility_01",
    "title": "Mobility Pattern Analysis — Shanghai Pudong New Area",
    "description": (
        "End-to-end mobility pattern analysis demonstrating memory-enabled "
        "temporal reasoning and prediction: data acquisition → spatiotemporal "
        "memory → pattern detection → prediction → validation → reporting."
    ),
    "steps": [
        {
            "step": 1,
            "name": "Trajectory Data Acquisition",
            "agent": "perception",
            "tool": "fetch_osm_data",
            "description": "Fetch road network and mobility infrastructure for Pudong",
            "input": {
                "location": "Pudong New Area, Shanghai, China",
                "radius": 2000,
                "data_types": ["roads", "pois"],
            },
            "expected_output": "Road network and POI data",
        },
        {
            "step": 2,
            "name": "Spatiotemporal Memory Loading",
            "agent": "analyst",
            "tool": None,
            "description": "Load historical mobility patterns into temporal memory",
            "memory_operation": "store",
            "input": {
                "patterns": [
                    {"time": "morning_peak", "flow": "residential→commercial", "volume": "high"},
                    {"time": "evening_peak", "flow": "commercial→residential", "volume": "high"},
                    {"time": "midday", "flow": "commercial↔commercial", "volume": "medium"},
                ],
            },
            "expected_output": "MemoryModule updated with temporal contexts",
        },
        {
            "step": 3,
            "name": "Topology & Cognition",
            "agent": "analyst",
            "tool": "build_topology",
            "description": "Build mobility network topology with dual-space cognition",
            "input": {"features": "{step_1_output}", "relation_threshold": 500},
            "dual_space": True,
            "expected_output": "Mobility topology graph",
        },
        {
            "step": 4,
            "name": "Pattern Reasoning",
            "agent": "analyst",
            "tool": None,
            "description": "Reason about mobility patterns using memory + topology",
            "memory_operation": "retrieve",
            "input": {"query": "Predict next-hour flow pattern based on current time and historical patterns"},
            "expected_output": "Predicted flow pattern with confidence",
        },
        {
            "step": 5,
            "name": "Traffic Signal Optimization",
            "agent": "analyst",
            "tool": "rank_traffic_signal_phases",
            "description": "Optimize signal phase ranking based on predicted flow",
            "input": {
                "phase_options": [
                    {"option": "A", "waiting_vehicle_count": 45, "vehicle_count": 120, "lane_count": 3},
                    {"option": "B", "waiting_vehicle_count": 20, "vehicle_count": 60, "lane_count": 2},
                    {"option": "C", "waiting_vehicle_count": 35, "vehicle_count": 80, "lane_count": 2},
                ],
            },
            "expected_output": "Ranked phase sequence",
        },
        {
            "step": 6,
            "name": "Review & QC",
            "agent": "spatial_reviewer",
            "tool": None,
            "description": "Validate spatial consistency and prediction reliability",
            "qc_check": True,
            "expected_output": "QualityReport with confidence",
        },
        {
            "step": 7,
            "name": "Report Generation",
            "agent": "reporter",
            "tool": "generate_measurement_report",
            "description": "Generate mobility analysis report with predictions",
            "input": {
                "baseline": {"network": "{step_3_output}", "patterns": "{step_4_output}"},
                "proposals": [{"name": "Signal optimization", "metrics": "{step_5_output}"}],
            },
            "expected_output": "Structured mobility analysis report",
        },
    ],
    "evaluation_criteria": {
        "completeness": "All 7 steps completed",
        "memory_utilization": "Memory store + retrieve both invoked",
        "dual_space": "Topology-based cognition activated",
        "temporal_reasoning": "Time-aware pattern detection demonstrated",
        "quality_gate": "QC confidence ≥ 0.75",
    },
}


# ---------------------------------------------------------------------------
# Workflow Runner
# ---------------------------------------------------------------------------

async def run_workflow_case(
    workflow: Dict[str, Any],
    llm_client: Any = None,
    verbose: bool = True,
) -> Dict[str, Any]:
    """Execute a single workflow case study."""
    orchestrator = MultiAgentOrchestrator(llm_client=llm_client)
    tracker = EfficiencyTracker()

    # Convert workflow to orchestrator task
    task = {
        "question": workflow["title"],
        "description": workflow["description"],
        "workflow_steps": workflow["steps"],
        "case_id": workflow["case_id"],
    }

    if verbose:
        print(f"\n{'='*70}")
        print(f"CASE STUDY: {workflow['title']}")
        print(f"Steps: {len(workflow['steps'])}")
        print(f"{'='*70}")

    start = time.perf_counter()
    try:
        result = await orchestrator.run(task=task, task_type="open_workflow")
        latency = time.perf_counter() - start

        if verbose:
            for step in workflow["steps"]:
                agent = step.get("agent", "?")
                tool = step.get("tool", "N/A")
                print(f"  Step {step['step']}: [{agent}] {step['name']} → tool={tool}")

        return {
            "case_id": workflow["case_id"],
            "title": workflow["title"],
            "num_steps": len(workflow["steps"]),
            "total_latency_s": round(latency, 3),
            "status": "success",
            "result": result,
            "efficiency": result.get("efficiency", {}),
            "quality_control": result.get("quality_control", {}),
            "evaluation_criteria": workflow["evaluation_criteria"],
            "agents_involved": list(set(s.get("agent", "") for s in workflow["steps"])),
            "tools_used": [s["tool"] for s in workflow["steps"] if s.get("tool")],
            "has_dual_space": any(s.get("dual_space") for s in workflow["steps"]),
            "has_memory": any(s.get("memory_operation") for s in workflow["steps"]),
            "has_qc": any(s.get("qc_check") for s in workflow["steps"]),
        }

    except Exception as e:
        return {
            "case_id": workflow["case_id"],
            "title": workflow["title"],
            "status": "error",
            "error": str(e),
            "total_latency_s": round(time.perf_counter() - start, 3),
        }


async def run_all_cases(
    llm_client: Any = None,
    cases: List[str] | None = None,
) -> Dict[str, Any]:
    """Run selected or all case studies."""
    available = {
        "walkability": WALKABILITY_WORKFLOW,
        "mobility": MOBILITY_WORKFLOW,
    }

    selected = cases or list(available.keys())
    results = []

    for name in selected:
        wf = available.get(name)
        if wf is None:
            print(f"Unknown case: {name}")
            continue
        result = await run_workflow_case(wf, llm_client)
        results.append(result)

    return {
        "timestamp": datetime.now().isoformat(),
        "num_cases": len(results),
        "cases": results,
        "summary": {
            "success": sum(1 for r in results if r["status"] == "success"),
            "total_steps": sum(r.get("num_steps", 0) for r in results),
            "total_tools": sum(len(r.get("tools_used", [])) for r in results),
            "dual_space_used": sum(1 for r in results if r.get("has_dual_space")),
            "memory_used": sum(1 for r in results if r.get("has_memory")),
            "qc_used": sum(1 for r in results if r.get("has_qc")),
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Workflow Case Studies")
    parser.add_argument("--case", choices=["walkability", "mobility", "all"], default="all")
    parser.add_argument("--output-dir", type=str, default=str(OUTPUT_DIR))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cases = None if args.case == "all" else [args.case]

    result = asyncio.run(run_all_cases(cases=cases))

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"case_studies_{ts}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)

    print(f"\nResults saved to {out_path}")
    print(f"\nSummary:")
    for k, v in result["summary"].items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
