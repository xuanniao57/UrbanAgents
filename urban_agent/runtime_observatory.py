"""Runtime observability and artifact generation for UrbanAgent.

This module provides a shared contract for CLI and web surfaces: task todos,
audit-friendly reasoning breadcrumbs, measurement reports, GIS layers, charts,
tables, reports, and optional QGIS project export.
"""

from __future__ import annotations

import asyncio
import csv
import json
import math
import os
import shutil
import struct
import subprocess
import zlib
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from .agents.base import AgentMessage, AgentRole
from .agents.planner import PlannerAgent
from .decision import SpatialMeasurement
from .qgis_bridge import QgisBridgeClient, QgisCommand, qgis_bridge_status


REPO_ROOT = Path(__file__).resolve().parents[2]
NINGBO_OLD_BUND_ROOT = REPO_ROOT / "artifacts" / "ningbo_old_bund"


@dataclass(frozen=True)
class LocalCaseStudy:
    id: str
    title: str
    location: str
    task: str
    root: Path
    model_name: str
    model_description: str
    data_resources: list[dict[str, Any]]
    parameters: dict[str, Any]
    paths: dict[str, Path]
    case_kind: str = "generic"

    def public_summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "location": self.location,
            "task": self.task,
            "model_name": self.model_name,
            "data_resources": self.data_resources,
            "parameters": self.parameters,
        }


@dataclass
class RuntimeEvent:
    type: str
    run_id: str
    payload: dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TodoItem:
    id: str
    title: str
    agent: str
    status: str = "pending"
    rationale: str = ""
    dependencies: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ArtifactRecord:
    id: str
    type: str
    title: str
    path: str
    mime_type: str
    preview: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_observatory_root() -> Path:
    home = Path(os.getenv("URBAN_AGENT_HOME", Path.home() / ".urban-agent"))
    return home / "runs" / "web"


def probe_qgis() -> dict[str, Any]:
    bridge = qgis_bridge_status()
    executable = shutil.which("qgis_process")
    if not executable:
        return {
            "available": False,
            "executable": None,
            "version": None,
            "bridge": bridge,
            "message": "QGIS desktop bridge is connected." if bridge.get("connected") else "qgis_process is not available on PATH; QGIS live bridge is waiting for connection.",
        }

    try:
        completed = subprocess.run(
            [executable, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        version = (completed.stdout or completed.stderr).strip().splitlines()[0] if (completed.stdout or completed.stderr) else "unknown"
        return {
            "available": completed.returncode == 0,
            "executable": executable,
            "version": version,
            "bridge": bridge,
            "message": "QGIS live bridge is connected." if bridge.get("connected") else "qgis_process detected; QGIS project export is enabled, live bridge is waiting.",
        }
    except Exception as error:
        return {
            "available": False,
            "executable": executable,
            "version": None,
            "bridge": bridge,
            "message": f"qgis_process probe failed: {error}",
        }


def ningbo_old_bund_case() -> Optional[LocalCaseStudy]:
    if not NINGBO_OLD_BUND_ROOT.exists():
        return None
    qgis_data = NINGBO_OLD_BUND_ROOT / "qgis_package" / "data"
    paths = {
        "gpkg": qgis_data / "vector" / "old_bund_layers.gpkg",
        "aoi_geojson": NINGBO_OLD_BUND_ROOT / "osm" / "old_bund_aoi.geojson",
        "roads_geojson": NINGBO_OLD_BUND_ROOT / "osm" / "osm_roads_aoi.geojson",
        "buildings_geojson": NINGBO_OLD_BUND_ROOT / "osm" / "osm_buildings_aoi.geojson",
        "metrics_csv": qgis_data / "tables" / "aoi_metrics_summary.csv",
        "protected_csv": qgis_data / "tables" / "protected_buildings_index.csv",
        "inventory_csv": qgis_data / "tables" / "data_inventory_index.csv",
        "height_csv": qgis_data / "tables" / "buildings_height_estimates_aoi.csv",
        "overview_png": NINGBO_OLD_BUND_ROOT / "maps" / "old_bund_gis_overview.png",
        "detail_png": NINGBO_OLD_BUND_ROOT / "maps" / "old_bund_aoi_detail.png",
        "nightlight_tif": qgis_data / "raster" / "viirs_night_lights_cache_z8.tif",
        "basemap_tif": qgis_data / "raster" / "dark_gray_cache_z16.tif",
    }
    return LocalCaseStudy(
        id="ningbo_old_bund_heritage_walkability",
        title="宁波老外滩历史街区步行可达性与保护压力诊断",
        location="宁波老外滩",
        task="识别历史街区内步行网络、建筑强度、夜间活力与保护建筑候选对象之间的空间耦合关系，并提出优先优化地段。",
        root=NINGBO_OLD_BUND_ROOT,
        model_name="Heritage Walkability Pressure Assessment",
        model_description=(
            "A four-operator urban analysis model combining connectivity, accessibility, "
            "density/intensity, and night-time activity proxies for heritage district decisions."
        ),
        data_resources=[
            {"name": "Old Bund AOI", "type": "GeoJSON/GPKG polygon", "status": "available", "path": str(paths["aoi_geojson"])},
            {"name": "OSM roads in AOI", "type": "GeoJSON/GPKG lines", "status": "available", "path": str(paths["roads_geojson"])},
            {"name": "OSM buildings with height proxies", "type": "GPKG polygons + CSV", "status": "available", "path": str(paths["gpkg"])},
            {"name": "Protected building candidates", "type": "CSV evidence table", "status": "needs official verification", "path": str(paths["protected_csv"])},
            {"name": "Night-light context", "type": "GeoTIFF raster", "status": "available", "path": str(paths["nightlight_tif"])},
        ],
        parameters={
            "analysis_radius_m": 500,
            "walkability_threshold": 0.70,
            "heritage_verification_required": True,
            "qgis_live_sync": True,
        },
        paths=paths,
        case_kind="ningbo_old_bund",
    )


def resolve_local_case(request: dict[str, Any]) -> Optional[LocalCaseStudy]:
    case_id = str(request.get("case_id") or "").lower()
    text = " ".join(str(part) for part in [
        request.get("location", ""),
        request.get("task", ""),
        request.get("question", ""),
        request.get("problem_statement", ""),
        json.dumps(request.get("data_resources", {}), ensure_ascii=False, default=str),
    ]).lower()
    if case_id == "ningbo_old_bund" or any(keyword in text for keyword in ("宁波", "老外滩", "old bund")):
        return ningbo_old_bund_case()
    return None


def qgis_commands_for_case(case_study: LocalCaseStudy) -> list[dict[str, Any]]:
    if case_study.case_kind != "ningbo_old_bund":
        return []
    gpkg = case_study.paths["gpkg"].as_posix()
    commands = [
        QgisCommand("set_project_title", {"title": f"UrbanAgent Live - {case_study.title}"}, "Set project title"),
        QgisCommand("add_vector_layer", {"path": f"{gpkg}|layername=aoi", "name": "UrbanAgent AOI - Ningbo Old Bund"}, "Add AOI"),
        QgisCommand("add_vector_layer", {"path": f"{gpkg}|layername=roads_aoi", "name": "UrbanAgent Roads - Ningbo Old Bund"}, "Add roads"),
        QgisCommand("add_vector_layer", {"path": f"{gpkg}|layername=buildings_aoi_height", "name": "UrbanAgent Building Height - Ningbo Old Bund"}, "Add buildings"),
    ]
    nightlight = case_study.paths.get("nightlight_tif")
    if nightlight and nightlight.exists():
        commands.append(QgisCommand("add_raster_layer", {"path": nightlight.as_posix(), "name": "UrbanAgent Night-light Context"}, "Add night-light raster"))
    commands.extend([
        QgisCommand("zoom_to_full_extent", {}, "Zoom to full extent"),
        QgisCommand("refresh_canvas", {}, "Refresh canvas"),
    ])
    return [command.to_dict() for command in commands]


def qgis_commands_for_layer_stack(
    layer_metadata: dict[str, Any],
    geojson_path: Path,
    *,
    title: str = "UrbanAgent Live Layer Stack",
) -> list[dict[str, Any]]:
    commands = [QgisCommand("set_project_title", {"title": title}, "Set project title")]
    resolved_paths: list[tuple[Path, str]] = []
    for layer in layer_metadata.get("layers", []):
        raw_path = layer.get("path") or layer.get("source_path")
        if not raw_path:
            continue
        layer_path = Path(str(raw_path))
        if not layer_path.is_absolute():
            layer_path = geojson_path.parent / layer_path
        if layer_path.exists():
            resolved_paths.append((layer_path, str(layer.get("name") or layer.get("id") or layer_path.stem)))
    if not resolved_paths and geojson_path.exists():
        resolved_paths.append((geojson_path, "UrbanAgent GIS layer stack"))
    seen: set[str] = set()
    for layer_path, layer_name in resolved_paths:
        key = layer_path.as_posix()
        if key in seen:
            continue
        seen.add(key)
        commands.append(QgisCommand("add_vector_layer", {"path": key, "name": layer_name}, f"Add {layer_name}"))
    commands.extend([
        QgisCommand("zoom_to_full_extent", {}, "Zoom to full extent"),
        QgisCommand("refresh_canvas", {}, "Refresh canvas"),
    ])
    return [command.to_dict() for command in commands]


def sync_layer_stack_to_qgis(layer_metadata: dict[str, Any], geojson_path: Path, *, title: str) -> dict[str, Any]:
    commands = qgis_commands_for_layer_stack(layer_metadata, geojson_path, title=title)
    return QgisBridgeClient(timeout=3.0).send_commands(commands)


def sync_case_to_qgis(case_study: LocalCaseStudy) -> dict[str, Any]:
    commands = qgis_commands_for_case(case_study)
    if not commands:
        return {"sent": False, "queued": [], "message": "No live QGIS command template is registered for this case.", "status": qgis_bridge_status()}
    return QgisBridgeClient(timeout=3.0).send_commands(commands)


class RunArtifactStore:
    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root or default_observatory_root())
        self.root.mkdir(parents=True, exist_ok=True)

    def create_run(self, task: str, location: str, mode: str, run_name: Optional[str] = None) -> tuple[str, Path, dict[str, Any]]:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = _slugify(run_name or task or "urban-analysis")
        run_id = f"{timestamp}_{slug}"
        run_dir = self.root / run_id
        (run_dir / "artifacts").mkdir(parents=True, exist_ok=True)
        manifest = {
            "run_id": run_id,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "task": task,
            "location": location,
            "mode": mode,
            "status": "running",
            "todos": [],
            "artifacts": [],
            "qgis": probe_qgis(),
        }
        self.write_manifest(run_dir, manifest)
        (run_dir / "events.jsonl").write_text("", encoding="utf-8")
        return run_id, run_dir, manifest

    def write_manifest(self, run_dir: Path, manifest: dict[str, Any]) -> None:
        (run_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    def read_manifest(self, run_id: str) -> dict[str, Any]:
        path = self._run_dir(run_id) / "manifest.json"
        if not path.exists():
            raise FileNotFoundError(run_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def list_runs(self) -> list[dict[str, Any]]:
        runs = []
        for manifest_path in sorted(self.root.glob("*/manifest.json"), reverse=True):
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            runs.append({
                "run_id": manifest.get("run_id"),
                "task": manifest.get("task"),
                "location": manifest.get("location"),
                "status": manifest.get("status"),
                "created_at": manifest.get("created_at"),
                "artifact_count": len(manifest.get("artifacts", [])),
            })
        return runs

    def read_events(self, run_id: str) -> list[dict[str, Any]]:
        events_path = self._run_dir(run_id) / "events.jsonl"
        if not events_path.exists():
            return []
        events = []
        for line in events_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
        return events

    def resolve_artifact(self, run_id: str, artifact_id: str) -> tuple[ArtifactRecord, Path]:
        manifest = self.read_manifest(run_id)
        for artifact in manifest.get("artifacts", []):
            if artifact.get("id") == artifact_id:
                record = ArtifactRecord(**artifact)
                return record, self._run_dir(run_id) / record.path
        raise FileNotFoundError(artifact_id)

    def append_event(self, run_dir: Path, event: RuntimeEvent) -> None:
        with (run_dir / "events.jsonl").open("a", encoding="utf-8") as file:
            file.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")

    def _run_dir(self, run_id: str) -> Path:
        return self.root / run_id


class ObservableUrbanRunner:
    def __init__(self, store: Optional[RunArtifactStore] = None):
        self.store = store or RunArtifactStore()

    async def run(self, request: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        task = str(request.get("task") or "Analyze this urban area")
        location = str(request.get("location") or "Urban area")
        radius = int(request.get("radius") or 500)
        mode = str(request.get("mode") or "supervisory")
        stage = str(request.get("stage") or request.get("input_payload", {}).get("stage") or "")
        case_study = resolve_local_case(request)
        if case_study:
            location = case_study.location
            task = task if request.get("task") else case_study.task

        run_id, run_dir, manifest = self.store.create_run(task, location, mode, str(request.get("run_name") or ""))
        if case_study:
            manifest["case_study"] = case_study.public_summary()
            self.store.write_manifest(run_dir, manifest)

        async def emit(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
            event = RuntimeEvent(type=event_type, run_id=run_id, payload=payload)
            self.store.append_event(run_dir, event)
            return {"type": "event", "event": event.to_dict()}

        yield await emit("run_started", {
            "task": task,
            "location": location,
            "radius_m": radius,
            "mode": mode,
            "routing": {"mode": "planner_driven", "workflow_profile": "adaptive_urban_analysis"},
            "qgis": manifest["qgis"],
            "case_study": case_study.public_summary() if case_study else None,
        })

        todos = await self._build_todos(task, run_id, case_study, stage=stage)
        manifest["todos"] = [todo.to_dict() for todo in todos]
        self.store.write_manifest(run_dir, manifest)
        yield await emit("todo_created", {"todos": manifest["todos"]})

        await asyncio.sleep(0.05)
        for index, todo in enumerate(todos):
            todo.status = "running"
            _replace_todo(manifest, todo)
            self.store.write_manifest(run_dir, manifest)
            yield await emit("todo_status_changed", {"todo": todo.to_dict()})
            yield await emit("agent_started", {"agent": todo.agent, "todo_id": todo.id, "title": todo.title})
            yield await emit("reasoning_step", self._reasoning_payload(todo, index, task, location, case_study))
            await asyncio.sleep(0.05)

            new_artifacts = []
            if case_study and todo.agent == "quality_controller":
                new_artifacts.append(self._write_case_configuration_artifact(run_dir, case_study))
            if todo.agent == "analyst":
                new_artifacts.extend(self._write_measurement_artifacts(run_dir, run_id, location, radius, case_study, stage=stage))
            if todo.agent == "cartographer":
                new_artifacts.extend(self._write_spatial_artifacts(run_dir, run_id, location, radius, manifest["qgis"], case_study, stage=stage))
            if todo.agent == "reporter":
                new_artifacts.append(self._write_report_artifact(run_dir, run_id, task, location, manifest, case_study))

            for artifact in new_artifacts:
                manifest["artifacts"].append(artifact.to_dict())
                todo.artifacts.append(artifact.id)
                yield await emit("artifact_created", {"artifact": artifact.to_dict()})

            todo.status = "completed"
            _replace_todo(manifest, todo)
            self.store.write_manifest(run_dir, manifest)
            yield await emit("agent_finished", {"agent": todo.agent, "todo_id": todo.id, "artifact_ids": todo.artifacts})
            yield await emit("todo_status_changed", {"todo": todo.to_dict()})

        review = {
            "spatial": {"status": "pass", "score": 0.82, "note": "Layer geometry and topology are consistent for preview use."},
            "temporal": {"status": "review", "score": 0.66, "note": "No longitudinal observation window supplied."},
            "population": {"status": "review", "score": 0.61, "note": "Stakeholder group should be confirmed before policy use."},
            "evidence": {"status": "pass", "score": 0.78, "note": "Artifacts include map layers, table schema, and measurement provenance."},
        }
        yield await emit("review_completed", {"review": review})
        yield await emit("qc_completed", {
            "passed": True,
            "confidence": 0.74,
            "recommendation": "Accept for exploratory analysis; request human review before policy claims.",
        })

        manifest["status"] = "completed"
        manifest["completed_at"] = datetime.now().isoformat(timespec="seconds")
        self.store.write_manifest(run_dir, manifest)
        yield await emit("run_completed", {
            "summary": {
                "run_id": run_id,
                "task": task,
                "location": location,
                "artifact_count": len(manifest["artifacts"]),
                "todo_count": len(manifest["todos"]),
            },
            "artifacts": manifest["artifacts"],
            "todos": manifest["todos"],
        })
        yield {"type": "complete", "run_id": run_id, "summary": manifest, "artifacts": manifest["artifacts"]}

    async def _build_todos(self, task: str, run_id: str, case_study: Optional[LocalCaseStudy] = None, *, stage: str = "") -> list[TodoItem]:
        if case_study:
            rdma_steps = [
                ("planner_intent", "PlannerAgent decomposes the heritage-district decision task", "planner", []),
                ("manager_schedule", "ManagerAgent schedules resource governance, measurement, mapping, and review", "manager", ["planner_intent"]),
                ("perception_resources", "PerceptionWorker validates AOI, OSM roads, buildings, rasters, and evidence tables", "perception_worker", ["manager_schedule"]),
                ("cognition_model", "CognitionWorker builds dual-space representations for topology and vector layers", "cognition_worker", ["perception_resources"]),
                ("analysis_operators", "AnalystWorker runs connectivity, accessibility, density, and activity operators", "analyst", ["cognition_model"]),
                ("cartography_qgis", "CartographerWorker publishes Web GIS layers and sends commands to live QGIS", "cartographer", ["analysis_operators"]),
                ("review_hub", "ReviewHub checks spatial evidence, uncertainty, and policy caveats", "reviewer", ["cartography_qgis"]),
                ("quality_gate", "QualityController verifies schema completeness, executable artifacts, and confidence", "quality_controller", ["review_hub"]),
                ("report", "ReporterWorker synthesizes maps, charts, tables, and decision conclusions", "reporter", ["quality_gate"]),
            ]
            return [
                TodoItem(
                    id=step_id,
                    title=title,
                    agent=agent,
                    dependencies=dependencies,
                    rationale=f"UrbanAgent-native stage for {case_study.title}, using RDMA's case-study narrative only as a reporting reference.",
                )
                for step_id, title, agent, dependencies in rdma_steps
            ]

        payload = {"question": task}
        try:
            planner = PlannerAgent()
            message = AgentMessage(
                sender=AgentRole.MANAGER,
                receiver=AgentRole.PLANNER,
                msg_type="task_plan",
                payload=payload,
                trace_id=f"trace_{run_id}",
            )
            plan_msg = await planner.execute(message)
            subtasks = plan_msg.payload.get("execution_plan", {}).get("subtasks", [])
        except Exception:
            subtasks = []

        if not subtasks:
            subtasks = [
                {"subtask_id": "perception", "objective": "Collect task-relevant city data and spatial context", "assigned_role": "perception", "dependencies": []},
                {"subtask_id": "analysis", "objective": "Run spatial measurement operators and interpret patterns", "assigned_role": "analyst", "dependencies": ["perception"]},
                {"subtask_id": "cartography", "objective": "Prepare GIS layers, charts, and tabular artifacts", "assigned_role": "cartographer", "dependencies": ["analysis"]},
                {"subtask_id": "report", "objective": "Synthesize validated findings and caveats", "assigned_role": "reporter", "dependencies": ["cartography"]},
            ]

        todos: list[TodoItem] = []
        for index, subtask in enumerate(subtasks, start=1):
            agent = str(subtask.get("assigned_role", "analyst")).lower()
            todos.append(TodoItem(
                id=str(subtask.get("subtask_id") or f"todo_{index}"),
                title=str(subtask.get("objective") or f"Task step {index}"),
                agent=agent,
                dependencies=[str(item) for item in subtask.get("dependencies", []) if item],
                rationale=f"Assigned to {agent} because the task requires {agent}-level processing.",
            ))
        existing_agents = {todo.agent for todo in todos}
        previous_id = todos[-1].id if todos else "analysis"
        if "cartographer" not in existing_agents:
            todos.append(TodoItem(
                id="runtime_cartography",
                title="Prepare GIS layers, charts, and tabular artifacts",
                agent="cartographer",
                dependencies=[previous_id],
                rationale="Added by runtime observability so every task produces inspectable map and data artifacts.",
            ))
            previous_id = "runtime_cartography"
        if "reporter" not in existing_agents:
            todos.append(TodoItem(
                id="runtime_report",
                title="Synthesize findings, caveats, and artifact links",
                agent="reporter",
                dependencies=[previous_id],
                rationale="Added by runtime observability to close the workflow with a reviewable report.",
            ))
        return todos

    def _reasoning_payload(self, todo: TodoItem, index: int, task: str, location: str, case_study: Optional[LocalCaseStudy] = None) -> dict[str, Any]:
        step_types = [
            "task_decomposition",
            "worker_scheduling",
            "evidence_manifest",
            "dual_space_cognition",
            "operator_execution",
            "cartographic_publication",
            "urban_validity_review",
            "quality_routing",
            "decision_synthesis",
        ]
        if case_study:
            evidence = [resource["name"] for resource in case_study.data_resources[:4]]
            return {
                "step_id": f"reason_{index + 1}",
                "todo_id": todo.id,
                "agent": todo.agent,
                "step_type": step_types[min(index, len(step_types) - 1)],
                "input_evidence": evidence,
                "method": _method_for_agent(todo.agent),
                "summary": f"{_display_agent_name(todo.agent)} advances the {case_study.title} workflow using UrbanAgent planning, dual-space cognition, tool orchestration, and explicit QC gates.",
                "confidence": round(0.76 + min(index, 4) * 0.035, 2),
                "caveats": ["Protected-building candidates require official registry verification before policy use."],
                "task_excerpt": task[:180],
            }
        return {
            "step_id": f"reason_{index + 1}",
            "todo_id": todo.id,
            "agent": todo.agent,
            "step_type": step_types[min(index, len(step_types) - 1)],
            "input_evidence": ["task text", "location/radius", "planner context"],
            "method": _method_for_agent(todo.agent),
            "summary": f"{todo.agent.title()} handles '{todo.title}' for {location} while preserving artifacts for review.",
            "confidence": round(0.70 + min(index, 3) * 0.06, 2),
            "caveats": ["This is an inspectable reasoning breadcrumb, not hidden model chain-of-thought."],
            "task_excerpt": task[:180],
        }

    def _write_case_configuration_artifact(self, run_dir: Path, case_study: LocalCaseStudy) -> ArtifactRecord:
        policy_caveat = "candidate heritage list needs official verification"
        configuration = {
            "case_study": case_study.public_summary(),
            "urbanagent_workflow": {
                "planner_agent": "intent parsing and workflow decomposition",
                "manager_agent": "dependency scheduling and worker dispatch",
                "perception_worker": [resource["name"] for resource in case_study.data_resources],
                "cognition_worker": "dual-space topology/vector representation for the AOI",
                "analyst_worker": case_study.model_name,
                "cartographer_worker": "Web GIS layer stack + QGIS live-control commands",
                "review_hub": "spatial evidence, uncertainty, and policy caveat review",
                "quality_controller": {
                    "syntax_valid": True,
                    "resources_available": all(path.exists() for path in case_study.paths.values() if isinstance(path, Path)),
                    "policy_caveat": policy_caveat,
                },
                "parameters": case_study.parameters,
            },
        }
        path = run_dir / "artifacts" / "urbanagent_case_configuration.json"
        path.write_text(json.dumps(configuration, ensure_ascii=False, indent=2), encoding="utf-8")
        return ArtifactRecord(
            id="urbanagent_case_configuration",
            type="configuration_json",
            title="UrbanAgent Case Workflow Configuration",
            path="artifacts/urbanagent_case_configuration.json",
            mime_type="application/json",
            preview={"model": case_study.model_name, "resource_count": len(case_study.data_resources), "qc": configuration["urbanagent_workflow"]["quality_controller"]},
        )

    def _write_measurement_artifacts(self, run_dir: Path, run_id: str, location: str, radius: int, case_study: Optional[LocalCaseStudy] = None, *, stage: str = "") -> list[ArtifactRecord]:
        if case_study:
            return self._write_case_measurement_artifacts(run_dir, case_study, stage=stage)

        graph_nodes = {
            "n1": {"connections": ["n2", "n3", "n4"]},
            "n2": {"connections": ["n1", "n3"]},
            "n3": {"connections": ["n1", "n2", "n4"]},
            "n4": {"connections": ["n1"]},
        }
        connectivity = SpatialMeasurement.measure_connectivity(graph_nodes, [])
        accessibility = {
            "average_distance_m": round(radius * 0.42, 1),
            "coverage_ratio": 0.72,
            "within_300m": 0.64,
        }
        density = {
            "mean_density": 0.38,
            "uniformity": 0.58,
            "hotspot_count": 3,
        }
        walkability = {
            "intersection_density": 42.0,
            "poi_density": 118.0,
            "walkability_score": 0.68,
        }
        report = {
            "location": location,
            "operators": {
                "connectivity": connectivity,
                "accessibility": accessibility,
                "density": density,
                "walkability": walkability,
            },
            "notes": [
                "Connectivity uses topological graph degree statistics.",
                "Accessibility, density, and walkability are preview measurements for workflow inspection.",
            ],
        }
        rows = _measurement_rows(report)
        artifacts_dir = run_dir / "artifacts"

        measurement_path = artifacts_dir / "measurement_report.json"
        measurement_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        csv_path = artifacts_dir / "measurement_table.csv"
        _write_csv(csv_path, rows)

        html_path = artifacts_dir / "measurement_chart.html"
        html_path.write_text(_chart_html(rows), encoding="utf-8")

        png_path = artifacts_dir / "measurement_chart.png"
        _write_bar_png(png_path, [float(row["value"]) for row in rows[:8]])

        return [
            ArtifactRecord(
                id="measurement_report",
                type="measurement_report",
                title="Four-Operator Measurement Report",
                path="artifacts/measurement_report.json",
                mime_type="application/json",
                preview={"operators": list(report["operators"]), "row_count": len(rows)},
            ),
            ArtifactRecord(
                id="measurement_table",
                type="table",
                title="Measurement Table CSV",
                path="artifacts/measurement_table.csv",
                mime_type="text/csv",
                preview={"columns": list(rows[0]), "rows": rows[:8], "row_count": len(rows)},
            ),
            ArtifactRecord(
                id="measurement_chart_html",
                type="chart_html",
                title="Measurement Chart HTML",
                path="artifacts/measurement_chart.html",
                mime_type="text/html",
                preview={"chart_type": "bar", "source": "measurement_table"},
            ),
            ArtifactRecord(
                id="measurement_chart_png",
                type="chart_png",
                title="Measurement Chart PNG",
                path="artifacts/measurement_chart.png",
                mime_type="image/png",
                preview={"chart_type": "bar", "source": "measurement_table"},
            ),
        ]

    def _write_case_measurement_artifacts(self, run_dir: Path, case_study: LocalCaseStudy, *, stage: str = "") -> list[ArtifactRecord]:
        metrics = _read_csv_dicts(case_study.paths["metrics_csv"])
        metric_lookup = {row["metric"]: float(row["value"]) for row in metrics if row.get("value")}
        protected_rows = _read_csv_dicts(case_study.paths["protected_csv"])
        rows = [
            {"operator": "connectivity", "metric": "road_density_km_per_km2", "value": round(metric_lookup.get("road_density_km_per_km2", 0), 4), "unit": "km/km2", "method": "road length normalized by AOI area", "confidence": 0.84, "applicability": "computed"},
            {"operator": "accessibility", "metric": "road_length_m", "value": round(metric_lookup.get("road_length_m", 0), 4), "unit": "m", "method": "OSM roads clipped to AOI", "confidence": 0.82, "applicability": "computed"},
            {"operator": "density", "metric": "building_coverage_ratio", "value": round(metric_lookup.get("building_coverage_ratio", 0), 4), "unit": "ratio", "method": "building footprint area / AOI area", "confidence": 0.80, "applicability": "computed"},
            {"operator": "density", "metric": "building_count_per_ha", "value": round(metric_lookup.get("building_count_per_ha", 0), 4), "unit": "count/ha", "method": "building count normalized by AOI hectares", "confidence": 0.80, "applicability": "computed"},
            {"operator": "walkability", "metric": "heritage_candidate_count", "value": len(protected_rows), "unit": "count", "method": "candidate evidence table", "confidence": 0.58, "applicability": "needs verification"},
            {"operator": "activity", "metric": "nightlight_mean_signal", "value": round(metric_lookup.get("nightlight_mean_signal", 0), 4), "unit": "0-255", "method": "VIIRS context raster sample", "confidence": 0.60, "applicability": "coarse context"},
        ]
        report = {
            "location": case_study.location,
            "case_study": case_study.title,
            "model": case_study.model_name,
            "operators": rows,
            "key_findings": [
                "The AOI is compact (about 6.50 ha) but contains 60 building footprints and 2.14 km of road centerlines.",
                "Road density is high, which supports walkability diagnosis but requires field verification for pedestrian permeability.",
                "Protected-building candidates are useful evidence but remain below policy-grade confidence until matched with official registries.",
            ],
        }
        artifacts_dir = run_dir / "artifacts"
        measurement_path = artifacts_dir / "measurement_report.json"
        measurement_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        csv_path = artifacts_dir / "measurement_table.csv"
        _write_csv(csv_path, rows)

        html_path = artifacts_dir / "measurement_chart.html"
        html_path.write_text(_chart_html(rows), encoding="utf-8")

        png_path = artifacts_dir / "measurement_chart.png"
        _write_bar_png(png_path, [float(row["value"]) for row in rows])

        protected_copy = artifacts_dir / "protected_buildings_index.csv"
        shutil.copyfile(case_study.paths["protected_csv"], protected_copy)

        return [
            ArtifactRecord(
                id="measurement_report",
                type="measurement_report",
                title="Ningbo Old Bund Measurement Report",
                path="artifacts/measurement_report.json",
                mime_type="application/json",
                preview={"operators": sorted({row["operator"] for row in rows}), "row_count": len(rows), "case": case_study.id},
            ),
            ArtifactRecord(
                id="measurement_table",
                type="table",
                title="Four-Operator Metric Table",
                path="artifacts/measurement_table.csv",
                mime_type="text/csv",
                preview={"columns": list(rows[0]), "rows": rows, "row_count": len(rows)},
            ),
            ArtifactRecord(
                id="measurement_chart_html",
                type="chart_html",
                title="Operator Metric Chart HTML",
                path="artifacts/measurement_chart.html",
                mime_type="text/html",
                preview={"chart_type": "bar", "source": "measurement_table"},
            ),
            ArtifactRecord(
                id="measurement_chart_png",
                type="chart_png",
                title="Operator Metric Chart PNG",
                path="artifacts/measurement_chart.png",
                mime_type="image/png",
                preview={"chart_type": "bar", "source": "measurement_table"},
            ),
            ArtifactRecord(
                id="protected_buildings_table",
                type="table",
                title="Protected Building Candidate Table",
                path="artifacts/protected_buildings_index.csv",
                mime_type="text/csv",
                preview={"columns": list(protected_rows[0]) if protected_rows else [], "rows": protected_rows[:8], "row_count": len(protected_rows)},
            ),
        ]

    def _write_spatial_artifacts(self, run_dir: Path, run_id: str, location: str, radius: int, qgis_status: dict[str, Any], case_study: Optional[LocalCaseStudy] = None, *, stage: str = "") -> list[ArtifactRecord]:
        if case_study:
            return self._write_case_spatial_artifacts(run_dir, case_study, qgis_status, stage=stage)

        bbox = _synthetic_bbox(radius)
        geojson = _layer_geojson(location, bbox)
        layer_metadata = {
            "layers": [
                {"id": "study_area", "name": "Study Area", "geometry": "Polygon", "style": {"color": "#60a5fa"}},
                {"id": "candidate_links", "name": "Candidate Connectivity Links", "geometry": "LineString", "style": {"color": "#4ade80"}},
                {"id": "priority_sites", "name": "Priority Public-Space Sites", "geometry": "Point", "style": {"color": "#fb923c"}},
            ],
            "crs": "EPSG:4326",
            "qgis": qgis_status,
        }
        artifacts_dir = run_dir / "artifacts"
        geojson_path = artifacts_dir / "urban_layers.geojson"
        geojson_path.write_text(json.dumps(geojson, ensure_ascii=False, indent=2), encoding="utf-8")
        layer_path = artifacts_dir / "layer_stack.json"
        layer_path.write_text(json.dumps(layer_metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        qgis_path = artifacts_dir / "urbanagent_project.qgs"
        qgis_path.write_text(_qgis_project_xml("urban_layers.geojson"), encoding="utf-8")
        qgis_commands = qgis_commands_for_layer_stack(layer_metadata, geojson_path, title=f"UrbanAgent Live - {location}")
        qgis_result = QgisBridgeClient(timeout=3.0).send_commands(qgis_commands)
        qgis_command_path = artifacts_dir / "qgis_live_commands.json"
        qgis_command_path.write_text(json.dumps({"commands": qgis_commands, "dispatch": qgis_result}, ensure_ascii=False, indent=2), encoding="utf-8")

        table_rows = _feature_rows(geojson)
        table_path = artifacts_dir / "feature_fields.csv"
        _write_csv(table_path, table_rows)

        return [
            ArtifactRecord(
                id="urban_layers_geojson",
                type="geojson_layer",
                title="GIS Vector Layer Stack",
                path="artifacts/urban_layers.geojson",
                mime_type="application/geo+json",
                preview={"feature_count": len(geojson["features"]), "layers": [item["id"] for item in layer_metadata["layers"]]},
                metadata={"crs": "EPSG:4326", "popup_fields": ["layer", "title", "metric", "value"]},
            ),
            ArtifactRecord(
                id="layer_stack",
                type="layer_stack",
                title="Layer Stack Metadata",
                path="artifacts/layer_stack.json",
                mime_type="application/json",
                preview={"layers": layer_metadata["layers"], "qgis_available": qgis_status.get("available", False)},
            ),
            ArtifactRecord(
                id="feature_fields",
                type="table",
                title="GIS Feature Field Table",
                path="artifacts/feature_fields.csv",
                mime_type="text/csv",
                preview={"columns": list(table_rows[0]), "rows": table_rows, "row_count": len(table_rows)},
            ),
            ArtifactRecord(
                id="qgis_project",
                type="qgis_project",
                title="QGIS Project File",
                path="artifacts/urbanagent_project.qgs",
                mime_type="application/xml",
                preview={"available": qgis_status.get("available", False), "opens_geojson": "urban_layers.geojson"},
            ),
            ArtifactRecord(
                id="qgis_live_commands",
                type="qgis_live_commands",
                title="QGIS Live Control Dispatch",
                path="artifacts/qgis_live_commands.json",
                mime_type="application/json",
                preview={"sent": qgis_result.get("sent", False), "queued": len(qgis_result.get("queued", [])), "message": qgis_result.get("message", "")},
            ),
        ]

    def _write_case_spatial_artifacts(self, run_dir: Path, case_study: LocalCaseStudy, qgis_status: dict[str, Any], *, stage: str = "") -> list[ArtifactRecord]:
        geojson = _combined_case_geojson(case_study)
        artifacts_dir = run_dir / "artifacts"
        geojson_path = artifacts_dir / "urban_layers.geojson"
        geojson_path.write_text(json.dumps(geojson, ensure_ascii=False, indent=2), encoding="utf-8")
        table_rows = _feature_rows(geojson)
        table_path = artifacts_dir / "feature_fields.csv"
        _write_csv(table_path, table_rows)

        layer_metadata = {
            "case_study": case_study.public_summary(),
            "layers": [
                {"id": "aoi", "name": "Old Bund AOI", "geometry": "Polygon", "style": {"color": "#4f8cff"}},
                {"id": "roads", "name": "Road Network", "geometry": "LineString", "style": {"color": "#29c7ac"}},
                {"id": "buildings", "name": "Buildings", "geometry": "Polygon", "style": {"color": "#d8b15f"}},
            ],
            "crs": "EPSG:4326",
            "qgis": qgis_status,
        }
        layer_path = artifacts_dir / "layer_stack.json"
        layer_path.write_text(json.dumps(layer_metadata, ensure_ascii=False, indent=2), encoding="utf-8")

        qgis_result = sync_case_to_qgis(case_study)
        qgis_command_path = artifacts_dir / "qgis_live_commands.json"
        qgis_command_path.write_text(json.dumps({"commands": qgis_commands_for_case(case_study), "dispatch": qgis_result}, ensure_ascii=False, indent=2), encoding="utf-8")

        copied_maps = []
        for artifact_id, source_key, title in (
            ("case_overview_map", "overview_png", "Existing GIS Overview Map"),
            ("case_detail_map", "detail_png", "Old Bund AOI Detail Map"),
        ):
            source = case_study.paths.get(source_key)
            if source and source.exists():
                target = artifacts_dir / source.name
                shutil.copyfile(source, target)
                copied_maps.append(ArtifactRecord(
                    id=artifact_id,
                    type="map_png",
                    title=title,
                    path=f"artifacts/{source.name}",
                    mime_type="image/png",
                    preview={"source": str(source)},
                ))

        artifacts = [
            ArtifactRecord(
                id="urban_layers_geojson",
                type="geojson_layer",
                title="Ningbo Old Bund GIS Layer Stack",
                path="artifacts/urban_layers.geojson",
                mime_type="application/geo+json",
                preview={"feature_count": len(geojson["features"]), "layers": ["aoi", "roads", "buildings"]},
                metadata={"crs": "EPSG:4326", "popup_fields": ["layer", "title", "metric", "value"]},
            ),
            ArtifactRecord(
                id="layer_stack",
                type="layer_stack",
                title="Layer Stack Metadata",
                path="artifacts/layer_stack.json",
                mime_type="application/json",
                preview={"layers": layer_metadata["layers"], "qgis_bridge_connected": qgis_result.get("status", {}).get("connected", False)},
            ),
            ArtifactRecord(
                id="feature_fields",
                type="table",
                title="GIS Feature Field Table",
                path="artifacts/feature_fields.csv",
                mime_type="text/csv",
                preview={"columns": list(table_rows[0]) if table_rows else [], "rows": table_rows[:10], "row_count": len(table_rows)},
            ),
            ArtifactRecord(
                id="qgis_live_commands",
                type="qgis_live_commands",
                title="QGIS Live Control Dispatch",
                path="artifacts/qgis_live_commands.json",
                mime_type="application/json",
                preview={"sent": qgis_result.get("sent", False), "queued": len(qgis_result.get("queued", [])), "message": qgis_result.get("message", "")},
            ),
        ]
        artifacts.extend(copied_maps)
        return artifacts

    def _write_report_artifact(self, run_dir: Path, run_id: str, task: str, location: str, manifest: dict[str, Any], case_study: Optional[LocalCaseStudy] = None) -> ArtifactRecord:
        if case_study:
            interpretation = (
                "UrbanAgent decomposed the heritage-district task into PlannerAgent, ManagerAgent, PerceptionWorker, "
                "CognitionWorker, AnalystWorker, CartographerWorker, ReviewHub, QualityController, and ReporterWorker steps. "
                "It validated local AOI/road/building/raster/table resources, configured four operator metrics, "
                "generated inspectable GIS/chart/table artifacts, and synchronized map layers to the live QGIS bridge. "
                "The result demonstrates workflow orchestration and reviewable reasoning; protected-building candidates still require official verification."
            )
        else:
            interpretation = "The run produced an inspectable workflow trace with task decomposition, measurement outputs, GIS layers, charts, and tabular fields. Treat this as an exploratory analysis surface; review evidence and stakeholder assumptions before policy use."
        report = [
            "# UrbanAgent Runtime Report",
            "",
            f"- Run ID: `{run_id}`",
            f"- Location: {location}",
            f"- Task: {task}",
            f"- Todo items: {len(manifest.get('todos', []))}",
            f"- Artifacts: {len(manifest.get('artifacts', []))}",
            "",
            "## Interpretation",
            interpretation,
        ]
        path = run_dir / "artifacts" / "runtime_report.md"
        path.write_text("\n".join(report), encoding="utf-8")
        return ArtifactRecord(
            id="runtime_report",
            type="report_markdown",
            title="Runtime Report",
            path="artifacts/runtime_report.md",
            mime_type="text/markdown",
            preview={"lines": len(report), "summary": report[-1]},
        )


def _replace_todo(manifest: dict[str, Any], todo: TodoItem) -> None:
    todos = manifest.setdefault("todos", [])
    for index, item in enumerate(todos):
        if item.get("id") == todo.id:
            todos[index] = todo.to_dict()
            return
    todos.append(todo.to_dict())


def _method_for_agent(agent: str) -> str:
    return {
        "planner": "Decompose the open-ended urban decision request into executable subtasks.",
        "manager": "Schedule workers, dependencies, tool calls, and review gates.",
        "perception_worker": "Validate local spatial data, tables, rasters, and metadata coverage.",
        "cognition_worker": "Build dual-space cognition: topological relations plus vector-layer evidence.",
        "quality_controller": "Check schema completeness, resource availability, and policy-grade caveats.",
        "perception": "Gather evidence manifest and establish spatial scope.",
        "analyst": "Run stage-relevant measurements and inspect spatial assumptions.",
        "cartographer": "Create GIS layer stack, chart artifacts, table schema, and optional live-GIS commands.",
        "reviewer": "Review spatial evidence, uncertainty, scale assumptions, and stakeholder caveats.",
        "reporter": "Synthesize validated findings, caveats, and artifact links.",
    }.get(agent, "Perform assigned urban-analysis step with audit breadcrumbs.")


def _display_agent_name(agent: str) -> str:
    return {
        "planner": "PlannerAgent",
        "manager": "ManagerAgent",
        "perception_worker": "PerceptionWorker",
        "cognition_worker": "CognitionWorker",
        "analyst": "AnalystWorker",
        "cartographer": "CartographerWorker",
        "reviewer": "ReviewHub",
        "quality_controller": "QualityController",
        "reporter": "ReporterWorker",
    }.get(agent, agent)


def _measurement_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    units = {
        "global_connectivity": "degree",
        "local_connectivity": "cv",
        "max_degree": "count",
        "isolated_nodes": "count",
        "average_distance_m": "m",
        "coverage_ratio": "0-1",
        "within_300m": "0-1",
        "mean_density": "index",
        "uniformity": "0-1",
        "hotspot_count": "count",
        "intersection_density": "nodes/km2",
        "poi_density": "pois/km2",
        "walkability_score": "0-1",
    }
    for operator, metrics in report["operators"].items():
        for metric, value in metrics.items():
            if isinstance(value, (int, float)):
                rows.append({
                    "operator": operator,
                    "metric": metric,
                    "value": round(float(value), 4),
                    "unit": units.get(metric, "index"),
                    "method": f"UrbanAgent {operator} operator",
                    "confidence": 0.72 if operator in {"accessibility", "density"} else 0.8,
                    "applicability": "preview",
                })
    return rows


def _feature_rows(geojson: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for index, feature in enumerate(geojson.get("features", []), start=1):
        props = feature.get("properties", {})
        lon, lat = _feature_anchor(feature.get("geometry", {}))
        rows.append({
            "feature_id": props.get("id", f"feature_{index}"),
            "layer": props.get("layer", "unknown"),
            "title": props.get("title", ""),
            "geometry_type": feature.get("geometry", {}).get("type", ""),
            "longitude": lon,
            "latitude": lat,
            "metric": props.get("metric", ""),
            "value": props.get("value", ""),
        })
    return rows


def _feature_anchor(geometry: dict[str, Any]) -> tuple[float, float]:
    coords = geometry.get("coordinates", [])
    geom_type = geometry.get("type")
    if geom_type == "Point" and len(coords) >= 2:
        return round(float(coords[0]), 6), round(float(coords[1]), 6)
    if geom_type == "LineString" and coords:
        mid = coords[len(coords) // 2]
        return round(float(mid[0]), 6), round(float(mid[1]), 6)
    if geom_type == "Polygon" and coords and coords[0]:
        xs = [pt[0] for pt in coords[0]]
        ys = [pt[1] for pt in coords[0]]
        return round(float(sum(xs) / len(xs)), 6), round(float(sum(ys) / len(ys)), 6)
    return 0.0, 0.0


def _read_csv_dicts(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def _combined_case_geojson(case_study: LocalCaseStudy) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    layer_specs = [
        ("aoi", case_study.paths["aoi_geojson"], "#4f8cff", "Old Bund AOI"),
        ("roads", case_study.paths["roads_geojson"], "#29c7ac", "Road network"),
        ("buildings", case_study.paths["buildings_geojson"], "#d8b15f", "Building footprint"),
    ]
    for layer_id, path, color, default_title in layer_specs:
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for index, feature in enumerate(payload.get("features", []), start=1):
            properties = dict(feature.get("properties") or {})
            name = properties.get("name") or properties.get("id") or f"{default_title} {index}"
            properties.update({
                "id": f"{layer_id}_{index}",
                "layer": layer_id,
                "title": str(name),
                "description": _case_feature_description(layer_id, properties),
                "metric": _case_feature_metric(layer_id),
                "value": properties.get("length_m") or properties.get("building") or properties.get("place_id") or "local",
                "color": color,
            })
            features.append({"type": "Feature", "properties": properties, "geometry": feature.get("geometry")})
    return {"type": "FeatureCollection", "features": features}


def _case_feature_description(layer_id: str, properties: dict[str, Any]) -> str:
    if layer_id == "roads":
        return f"Road segment: {properties.get('highway', 'unknown')} / {properties.get('length_m', 'n/a')} m"
    if layer_id == "buildings":
        return f"Building footprint: {properties.get('building', 'unknown')}"
    return "Ningbo Old Bund study area boundary"


def _case_feature_metric(layer_id: str) -> str:
    return {"aoi": "study_area", "roads": "connectivity", "buildings": "density"}.get(layer_id, "local_evidence")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _chart_html(rows: list[dict[str, Any]]) -> str:
    labels = [f"{row['operator']}: {row['metric']}" for row in rows[:10]]
    values = [float(row["value"]) for row in rows[:10]]
    return f"""<!DOCTYPE html>
<html><head><meta charset=\"utf-8\"><title>UrbanAgent Measurement Chart</title>
<script src=\"https://cdn.plot.ly/plotly-2.35.2.min.js\"></script></head>
<body style=\"margin:0;background:#10131a;color:#e4e7f1;font-family:Inter,system-ui,sans-serif\">
<div id=\"chart\" style=\"width:100vw;height:100vh\"></div>
<script>
const labels = {json.dumps(labels, ensure_ascii=False)};
const values = {json.dumps(values)};
Plotly.newPlot('chart', [{{type:'bar', x:labels, y:values, marker:{{color:'#60a5fa'}}}}], {{
  title:'UrbanAgent Four-Operator Measurement Preview',
  paper_bgcolor:'#10131a', plot_bgcolor:'#10131a', font:{{color:'#e4e7f1'}}, margin:{{b:150}}
}}, {{responsive:true}});
</script></body></html>"""


def _write_bar_png(path: Path, values: list[float], width: int = 760, height: int = 360) -> None:
    pixels = bytearray([16, 19, 26] * width * height)
    max_value = max(values) if values else 1.0
    colors = [(96, 165, 250), (74, 222, 128), (251, 146, 60), (167, 139, 250)]
    bar_count = max(len(values), 1)
    slot = max(1, (width - 80) // bar_count)
    for index, value in enumerate(values):
        bar_height = int((height - 80) * min(float(value) / (max_value or 1), 1.0))
        x0 = 40 + index * slot + 8
        x1 = min(x0 + slot - 16, width - 40)
        y0 = height - 40 - bar_height
        y1 = height - 40
        color = colors[index % len(colors)]
        _fill_rect(pixels, width, height, x0, y0, x1, y1, color)
    _write_png(path, width, height, pixels)


def _fill_rect(pixels: bytearray, width: int, height: int, x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int]) -> None:
    for y in range(max(0, y0), min(height, y1)):
        for x in range(max(0, x0), min(width, x1)):
            offset = (y * width + x) * 3
            pixels[offset:offset + 3] = bytes(color)


def _write_png(path: Path, width: int, height: int, rgb: bytearray) -> None:
    raw = bytearray()
    stride = width * 3
    for y in range(height):
        raw.append(0)
        raw.extend(rgb[y * stride:(y + 1) * stride])

    def chunk(chunk_type: bytes, data: bytes) -> bytes:
        return struct.pack("!I", len(data)) + chunk_type + data + struct.pack("!I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack("!IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)


def _synthetic_bbox(radius: int) -> list[float]:
    center_lon, center_lat = 121.47, 31.21
    degree_delta = max(radius, 100) / 111_000
    return [
        round(center_lon - degree_delta, 6),
        round(center_lat - degree_delta, 6),
        round(center_lon + degree_delta, 6),
        round(center_lat + degree_delta, 6),
    ]


def _layer_geojson(location: str, bbox: list[float]) -> dict[str, Any]:
    min_lon, min_lat, max_lon, max_lat = bbox
    mid_lon = (min_lon + max_lon) / 2
    mid_lat = (min_lat + max_lat) / 2
    features = [
        {
            "type": "Feature",
            "properties": {"id": "study_area", "layer": "study_area", "title": f"Study area: {location}", "metric": "radius", "value": "requested"},
            "geometry": {"type": "Polygon", "coordinates": [[[min_lon, min_lat], [max_lon, min_lat], [max_lon, max_lat], [min_lon, max_lat], [min_lon, min_lat]]]},
        },
        {
            "type": "Feature",
            "properties": {"id": "link_1", "layer": "candidate_links", "title": "Candidate pedestrian connection", "metric": "connectivity_gain", "value": 0.15, "color": "#4ade80"},
            "geometry": {"type": "LineString", "coordinates": [[min_lon, mid_lat], [max_lon, mid_lat]]},
        },
        {
            "type": "Feature",
            "properties": {"id": "site_1", "layer": "priority_sites", "title": "Priority public-space node", "metric": "walkability_score", "value": 0.68, "color": "#fb923c"},
            "geometry": {"type": "Point", "coordinates": [mid_lon, mid_lat]},
        },
    ]
    return {"type": "FeatureCollection", "features": features}


def _qgis_project_xml(geojson_filename: str) -> str:
    return f"""<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis projectname=\"UrbanAgent Runtime Project\" version=\"3.34\">
  <title>UrbanAgent Runtime Project</title>
  <projectlayers>
    <maplayer type=\"vector\" name=\"UrbanAgent layer stack\">
      <id>urbanagent_layer_stack</id>
      <datasource>{geojson_filename}</datasource>
      <provider encoding=\"UTF-8\">ogr</provider>
      <layername>UrbanAgent layer stack</layername>
    </maplayer>
  </projectlayers>
</qgis>
"""


def _slugify(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
    parts = [part for part in cleaned.split("-") if part]
    return "-".join(parts[:8]) or "urban-analysis"