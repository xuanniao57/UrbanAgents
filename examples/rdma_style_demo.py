"""
Multi-turn Guided UrbanAgent CLI — RDMA Figure 13 alignment.

Pattern:
  Turn 1: Task understanding + data gap prompting
  Turn 2: Perception rerun (human provides data paths)
  Turn 3: Analyst outputs metrics (human provides parameters)
  Turn 4: Cartographer outputs GIS visuals (human approves/rejects)

Each turn produces a GIS visual output (GPKG + QGIS project + PNG map).
Confidence four-dimension scores are traced to specific evidence.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


async def run_multiturn(
    task: str,
    run_name: Optional[str] = None,
    *,
    llm_provider: str = "deepseek",
    output_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Run a full multi-turn UrbanAgent session with human-in-the-loop."""
    from urban_agent.cli import _build_planner_llm_client, _build_exec_llm_client
    from urban_agent.core import PerceptionModule, ReasoningModule
    from urban_agent.agents.orchestrator import MultiAgentOrchestrator

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_label = run_name or f"multiturn_{ts}"
    output_root = output_root or PACKAGE_ROOT / "outputs" / "cli_runs" / run_label
    output_root.mkdir(parents=True, exist_ok=True)

    planner_client = _build_planner_llm_client()
    exec_client = _build_exec_llm_client()

    all_turns = []

    # ========== TURN 1: Task Understanding ==========
    print("\n" + "=" * 60)
    print("  TURN 1 — Task Understanding & Data Gap Prompting")
    print("=" * 60)
    turn1_dir = output_root / "turn1_understand"
    turn1_dir.mkdir(parents=True, exist_ok=True)

    orch1 = MultiAgentOrchestrator(
        llm_client=exec_client, planner_llm_client=planner_client,
        perception_module=PerceptionModule(llm_client=exec_client),
        reasoning_module=ReasoningModule(llm_client=exec_client),
        interaction_mode="supervisory",
        enable_planning=True, enable_review=True, enable_quality_control=True,
    )
    t1_result = await orch1.run({"question": task, "artifact_dir": str(turn1_dir / "artifacts"), "run_dir": str(turn1_dir)})
    all_turns.append({"turn": 1, "stage": "understand", "result": t1_result})

    _print_turn_summary(1, "Task Understanding", t1_result)
    _print_confidence(t1_result)
    _print_data_gaps(t1_result)

    # Human feedback: provide data paths
    print("\n--- HUMAN INPUT REQUIRED ---")
    print("Provide data paths (boundary/roads/buildings/streetview/function) in JSON format.")
    print('Example: {"boundary": "path/to/boundary.geojson", "streetview_dir": "path/to/streetview/"}')
    print("Or type 'skip' to continue with auto-discovery.")
    human_data = input("\nData paths > ").strip()

    data_context = {}
    if human_data and human_data.lower() != "skip":
        try:
            data_context = json.loads(human_data)
        except json.JSONDecodeError:
            data_context = {"user_paths": human_data}

    # ========== TURN 2: Perception Rerun ==========
    print("\n" + "=" * 60)
    print("  TURN 2 — Perception with Provided Data")
    print("=" * 60)
    turn2_dir = output_root / "turn2_perception"
    turn2_dir.mkdir(parents=True, exist_ok=True)

    t2_task = {"question": task, "artifact_dir": str(turn2_dir / "artifacts"), "run_dir": str(turn2_dir)}
    if data_context:
        t2_task["user_data_paths"] = data_context
        enhanced_question = task + "\n\nDeclared data paths:\n" + json.dumps(data_context, ensure_ascii=False, indent=2)
        t2_task["question"] = enhanced_question

    orch2 = MultiAgentOrchestrator(
        llm_client=exec_client, planner_llm_client=planner_client,
        perception_module=PerceptionModule(llm_client=exec_client),
        reasoning_module=ReasoningModule(llm_client=exec_client),
        interaction_mode="supervisory",
        enable_planning=True, enable_review=True, enable_quality_control=True,
    )
    t2_result = await orch2.run(t2_task)
    all_turns.append({"turn": 2, "stage": "perception", "result": t2_result})

    _print_turn_summary(2, "Perception", t2_result)
    # Try QGIS render for Turn 2
    _try_qgis_render(t2_result, turn2_dir)

    # Human feedback: provide analysis parameters
    print("\n--- HUMAN INPUT REQUIRED ---")
    print("Provide analysis parameters or indicator preferences.")
    print("Example: {\"indicators\": [\"building_coverage\", \"function_entropy\", \"visual_consistency\"]}")
    print("Or type 'auto' to let the agent decide.")
    human_params = input("\nParameters > ").strip()

    param_context = {}
    if human_params and human_params.lower() != "auto":
        try:
            param_context = json.loads(human_params)
        except json.JSONDecodeError:
            param_context = {"user_params": human_params}

    # ========== TURN 3: Analyst Outputs Metrics ==========
    print("\n" + "=" * 60)
    print("  TURN 3 — Analyst with User Parameters")
    print("=" * 60)
    turn3_dir = output_root / "turn3_analyst"
    turn3_dir.mkdir(parents=True, exist_ok=True)

    t3_question = task
    if param_context:
        t3_question = task + "\n\nUser-specified indicators:\n" + json.dumps(param_context, ensure_ascii=False, indent=2)

    t3_task = {"question": t3_question, "artifact_dir": str(turn3_dir / "artifacts"), "run_dir": str(turn3_dir)}
    if data_context:
        t3_task["user_data_paths"] = data_context

    orch3 = MultiAgentOrchestrator(
        llm_client=exec_client, planner_llm_client=planner_client,
        perception_module=PerceptionModule(llm_client=exec_client),
        reasoning_module=ReasoningModule(llm_client=exec_client),
        interaction_mode="supervisory",
        enable_planning=True, enable_review=True, enable_quality_control=True,
    )
    t3_result = await orch3.run(t3_task)
    all_turns.append({"turn": 3, "stage": "analyst", "result": t3_result})

    _print_turn_summary(3, "Analyst", t3_result)
    _print_confidence(t3_result)
    _print_metrics(t3_result)

    # Human feedback: review metrics, approve/reject
    print("\n--- HUMAN INPUT REQUIRED ---")
    print("Review the metrics above. Type 'approve' to continue, or provide corrections.")
    human_review = input("\nReview > ").strip()

    # ========== TURN 4: Cartographer Outputs GIS ==========
    print("\n" + "=" * 60)
    print("  TURN 4 — Cartographer GIS Output")
    print("=" * 60)
    turn4_dir = output_root / "turn4_cartographer"
    turn4_dir.mkdir(parents=True, exist_ok=True)

    t4_task = {"question": task, "artifact_dir": str(turn4_dir / "artifacts"), "run_dir": str(turn4_dir)}
    if data_context:
        t4_task["user_data_paths"] = data_context
    if human_review.lower() != "approve":
        t4_task["human_review_feedback"] = human_review

    orch4 = MultiAgentOrchestrator(
        llm_client=exec_client, planner_llm_client=planner_client,
        perception_module=PerceptionModule(llm_client=exec_client),
        reasoning_module=ReasoningModule(llm_client=exec_client),
        interaction_mode="supervisory",
        enable_planning=True, enable_review=True, enable_quality_control=True,
    )
    t4_result = await orch4.run(t4_task)
    all_turns.append({"turn": 4, "stage": "cartographer", "result": t4_result})

    _print_turn_summary(4, "Cartographer", t4_result)
    _print_gis_artifacts(t4_result)
    _try_qgis_render(t4_result, turn4_dir, launch_qgis=True)

    # ========== FINAL SUMMARY ==========
    print("\n" + "=" * 60)
    print("  MULTI-TURN SESSION COMPLETE")
    print("=" * 60)
    print(f"Output directory: {output_root}")
    print(f"Turn directories: turn1_understand, turn2_perception, turn3_analyst, turn4_cartographer")

    manifest_path = output_root / "multiturn_manifest.json"
    manifest = {
        "run_name": run_label,
        "timestamp": ts,
        "turns": [
            {
                "turn": t["turn"],
                "stage": t["stage"],
                "trace_id": t["result"].get("trace_id"),
                "status": t["result"].get("status"),
                "confidence": _get_confidence(t["result"]),
                "review_passed": t["result"].get("review", {}).get("passed"),
            }
            for t in all_turns
        ],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Manifest: {manifest_path}")

    return manifest


def _print_turn_summary(turn: int, stage: str, result: Dict[str, Any]) -> None:
    rev = result.get("review", {})
    qc = result.get("quality_control", {})
    eff = result.get("efficiency", {})
    print(f"\nTurn {turn} ({stage}): status={result.get('status')}")
    print(f"  Latency: {eff.get('total_latency_s', 'N/A')}s")
    print(f"  Review: passed={rev.get('passed')}, validity={rev.get('urban_validity_score', 'N/A')}")
    exec_qc = qc.get("exec_qc", {})
    if isinstance(exec_qc, dict):
        print(f"  Exec confidence: {exec_qc.get('confidence_score', 'N/A')}")


def _print_confidence(result: Dict[str, Any]) -> None:
    qc = result.get("quality_control", {})
    exec_qc = qc.get("exec_qc", {})
    dims = exec_qc.get("dimension_scores", {}) if isinstance(exec_qc, dict) else {}
    if dims:
        print(f"  Confidence 4-Dim: semantic={dims.get('semantic_relevance', 'N/A')}, "
              f"historical={dims.get('historical_reliability', 'N/A')}, "
              f"metadata={dims.get('metadata_completeness', 'N/A')}, "
              f"context={dims.get('context_alignment', 'N/A')}")


def _print_data_gaps(result: Dict[str, Any]) -> None:
    plan = result.get("plan", {})
    caps = plan.get("capability_context", {}).get("selected_names", [])
    print(f"  Selected capabilities: {caps}")
    sub = result.get("results", {}).get("subtask_results", {})
    for sid, sdata in sub.items():
        rd = sdata.get("result", {}) if isinstance(sdata, dict) else {}
        paths = rd.get("accessible_paths", {})
        resources = rd.get("resource_catalog", [])
        if resources:
            print(f"  Data resources found ({len(resources)}):")
            for res in resources[:8]:
                print(f"    {res.get('role')}: {res.get('path', '?')} (exists={res.get('exists')})")
        if paths:
            missing = [k for k in ["buildings", "roads", "streetview_dir", "function_counts"] if k not in paths]
            if missing:
                print(f"  ⚠ Missing data: {missing}")


def _print_metrics(result: Dict[str, Any]) -> None:
    sub = result.get("results", {}).get("subtask_results", {})
    for sid, sdata in sub.items():
        rd = sdata.get("result", {}) if isinstance(sdata, dict) else {}
        cr = rd.get("capability_results", {})
        for cname, cdata in cr.items():
            if cdata.get("status") == "computed":
                print(f"  [{cname}] computed:")
                for k, v in cdata.get("summary", {}).items():
                    print(f"    {k}: {v}")


def _print_gis_artifacts(result: Dict[str, Any]) -> None:
    sub = result.get("results", {}).get("subtask_results", {})
    for sid, sdata in sub.items():
        rd = sdata.get("result", {}) if isinstance(sdata, dict) else {}
        artifacts = rd.get("artifacts", [])
        if artifacts:
            print(f"  GIS Artifacts ({len(artifacts)}):")
            for a in artifacts:
                print(f"    [{a.get('type')}] {a.get('path', '?')}")


def _get_confidence(result: Dict[str, Any]) -> float:
    qc = result.get("quality_control", {})
    exec_qc = qc.get("exec_qc", {})
    return float(exec_qc.get("confidence_score", 0.0)) if isinstance(exec_qc, dict) else 0.0


def _try_qgis_render(result: Dict[str, Any], turn_dir: Path, launch_qgis: bool = False) -> None:
    """Attempt QGIS rendering if GPKG artifacts exist."""
    sub = result.get("results", {}).get("subtask_results", {})
    gpkg_path = None
    for sid, sdata in sub.items():
        rd = sdata.get("result", {}) if isinstance(sdata, dict) else {}
        for a in rd.get("artifacts", []):
            if a.get("type") == "gis_layer_package":
                gpkg_path = a.get("path")
                break

    if not gpkg_path:
        # Check for auto-generated GPKG
        candidate = turn_dir / "artifacts" / "urbanagent_gis_layers.gpkg"
        if candidate.exists():
            gpkg_path = str(candidate)

    if gpkg_path:
        print(f"\n  Attempting QGIS render from: {gpkg_path}")
        try:
            from plugins.qgis.qgis_tools import render_with_qgis, launch_qgis_project
            if launch_qgis:
                qr = launch_qgis_project(gpkg_path, str(turn_dir / "artifacts"))
            else:
                qr = render_with_qgis(gpkg_path, str(turn_dir / "artifacts"))
            if qr.get("qgis_launched"):
                print("  ✅ QGIS launched with project")
            for qa in qr.get("artifacts", []):
                print(f"  QGIS artifact: [{qa.get('type')}] {qa.get('path')}")
        except Exception as e:
            print(f"  QGIS render unavailable: {e}")
    else:
        print("  (No GPKG found for QGIS render)")


if __name__ == "__main__":
    import sys
    task_text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else input("Task > ")
    asyncio.run(run_multiturn(task_text))
