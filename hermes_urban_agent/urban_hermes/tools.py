"""Hermes tool registrations for the UrbanAgent dogfood adapter."""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .paths import ensure_paths


TOOLSET = "urban"


def register_all_urban_tools() -> list[str]:
    """Register all urban tools with Hermes' registry."""
    ensure_paths()
    from tools.registry import registry

    specs = [
        ("urban_capabilities", CAPABILITIES_SCHEMA, _handle_capabilities),
        ("urban_fetch_osm", FETCH_OSM_SCHEMA, _handle_fetch_osm),
        ("urban_analyze_connectivity", CONNECTIVITY_SCHEMA, _handle_connectivity),
        ("urban_measure_accessibility", ACCESSIBILITY_SCHEMA, _handle_accessibility),
        ("urban_calculate_density", DENSITY_SCHEMA, _handle_density),
        ("urban_generate_svg_overlay", SVG_SCHEMA, _handle_svg),
        ("urban_export_geojson", GEOJSON_SCHEMA, _handle_geojson),
        ("urban_build_topology", TOPOLOGY_SCHEMA, _handle_topology),
        ("urban_ground_task", GROUND_TASK_SCHEMA, _handle_ground_task),
        ("urban_review", REVIEW_SCHEMA, _handle_review),
        ("urban_quality_control", QUALITY_SCHEMA, _handle_quality),
        ("urban_record_feedback", RECORD_FEEDBACK_SCHEMA, _handle_record_feedback),
        ("urban_research_memory", RESEARCH_MEMORY_SCHEMA, _handle_research_memory),
        ("urban_host_fs", HOST_FS_SCHEMA, _handle_host_fs),
        ("urban_host_python", HOST_PYTHON_SCHEMA, _handle_host_python),
        ("urban_qgis_workspace", QGIS_WORKSPACE_SCHEMA, _handle_qgis_workspace),
        ("urban_qgis_process", QGIS_PROCESS_SCHEMA, _handle_qgis_process),
    ]
    names: list[str] = []
    for name, schema, handler in specs:
        names.append(name)
        if registry.get_entry(name):
            continue
        registry.register(
            name=name,
            toolset=TOOLSET,
            schema=schema,
            handler=handler,
            check_fn=lambda: True,
            description=schema.get("description", ""),
            emoji="U",
        )
    return names


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _ok(result: Any, **meta: Any) -> str:
    payload = {"success": True, "result": result}
    payload.update(meta)
    return _json(payload)


def _fail(error: str, **meta: Any) -> str:
    payload = {"success": False, "error": error}
    payload.update(meta)
    return _json(payload)


def _host_path(value: Any) -> Path:
    text = str(value or ".").strip()
    if text.startswith("file:///"):
        text = text[8:]
    match = re.match(r"^/mnt/([a-zA-Z])/(.*)$", text)
    if match:
        text = f"{match.group(1).upper()}:/{match.group(2)}"
    else:
        match = re.match(r"^/([a-zA-Z])/(.*)$", text)
        if match:
            text = f"{match.group(1).upper()}:/{match.group(2)}"
    return Path(text).expanduser()


def _decode_bytes(data: bytes, encoding: str | None = None) -> tuple[str, str]:
    candidates = [encoding] if encoding else []
    candidates.extend(["utf-8-sig", "utf-8", "utf-16", "gbk"])
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            return data.decode(candidate), candidate
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace"), "utf-8-replace"


def _read_host_text(path: Path, *, encoding: str | None = None, max_bytes: int | None = None) -> tuple[str, str, bool]:
    data = path.read_bytes()
    truncated = False
    if max_bytes is not None and max_bytes >= 0 and len(data) > max_bytes:
        data = data[:max_bytes]
        truncated = True
    text, used_encoding = _decode_bytes(data, encoding)
    return text, used_encoding, truncated


def _host_entry(path: Path) -> dict[str, Any]:
    try:
        stat = path.stat()
    except OSError:
        stat = None
    return {
        "name": path.name,
        "path": str(path),
        "exists": path.exists(),
        "is_file": path.is_file(),
        "is_dir": path.is_dir(),
        "suffix": path.suffix,
        "size": stat.st_size if stat else None,
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds") if stat else None,
    }


def _json_summary(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        summary: dict[str, Any] = {"type": "object", "keys": list(value.keys())[:30], "key_count": len(value)}
        if value.get("type") == "FeatureCollection":
            features = value.get("features") or []
            summary["geojson_type"] = "FeatureCollection"
            summary["feature_count"] = len(features) if isinstance(features, list) else None
            if isinstance(features, list) and features:
                geom_types = Counter((feature.get("geometry") or {}).get("type", "unknown") for feature in features if isinstance(feature, dict))
                summary["geometry_types"] = dict(geom_types)
                first_props = features[0].get("properties") if isinstance(features[0], dict) else None
                if isinstance(first_props, dict):
                    summary["sample_property_keys"] = list(first_props.keys())[:30]
        return summary
    if isinstance(value, list):
        return {"type": "array", "length": len(value), "sample_type": type(value[0]).__name__ if value else None}
    return {"type": type(value).__name__, "repr": repr(value)[:200]}


def _handle_host_fs(args: dict[str, Any], **_: Any) -> str:
    action = str(args.get("action") or "stat")
    path = _host_path(args.get("path") or ".")
    limit = max(1, min(int(args.get("limit") or 100), 1000))

    try:
        if action in {"stat", "exists"}:
            return _ok(_host_entry(path), action=action, host=os.name)

        if action == "list":
            if not path.exists():
                return _fail(f"path does not exist: {path}", action=action)
            if not path.is_dir():
                return _fail(f"path is not a directory: {path}", action=action)
            entries = sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
            return _ok({"path": str(path), "entries": [_host_entry(item) for item in entries[:limit]], "truncated": len(entries) > limit}, action=action, host=os.name)

        if action == "glob":
            pattern = str(args.get("pattern") or "*")
            base = path if path.is_dir() else path.parent
            matches = sorted(base.glob(pattern), key=lambda item: str(item).lower())
            return _ok({"base": str(base), "pattern": pattern, "matches": [_host_entry(item) for item in matches[:limit]], "truncated": len(matches) > limit}, action=action, host=os.name)

        if action == "read_text":
            max_chars = max(1, int(args.get("max_chars") or 20000))
            max_bytes = max_chars * 4
            text, used_encoding, truncated = _read_host_text(path, encoding=args.get("encoding"), max_bytes=max_bytes)
            if len(text) > max_chars:
                text = text[:max_chars]
                truncated = True
            return _ok({"path": str(path), "encoding": used_encoding, "chars": len(text), "truncated": truncated, "text": text}, action=action, host=os.name)

        if action in {"read_json", "json_summary", "geojson_summary"}:
            max_bytes = max(1, int(args.get("max_bytes") or 25_000_000))
            text, used_encoding, truncated = _read_host_text(path, encoding=args.get("encoding"), max_bytes=max_bytes)
            if truncated:
                return _fail(f"JSON file exceeds max_bytes={max_bytes}: {path}", action=action)
            data = json.loads(text)
            result = {"path": str(path), "encoding": used_encoding, "summary": _json_summary(data)}
            if action == "read_json":
                result["data"] = data
            return _ok(result, action=action, host=os.name)

        return _fail(f"unsupported action: {action}", supported_actions=["stat", "exists", "list", "glob", "read_text", "read_json", "json_summary", "geojson_summary"])
    except Exception as exc:
        return _fail(str(exc), action=action, path=str(path), host=os.name)


def _handle_host_python(args: dict[str, Any], **_: Any) -> str:
    python_executable = str(args.get("python") or sys.executable)
    timeout = max(1, int(args.get("timeout") or 300))
    argv = [str(item) for item in args.get("argv") or []]
    workdir = _host_path(args.get("workdir") or os.getcwd())
    output_dir = args.get("output_dir")
    script_path_arg = args.get("script_path")
    code = args.get("code")
    keep_script = bool(args.get("keep_script", False) or output_dir)
    script_path: Path | None = None
    temporary_script = False

    try:
        workdir.mkdir(parents=True, exist_ok=True)
        if script_path_arg:
            script_path = _host_path(script_path_arg)
        else:
            if not code:
                return _fail("code or script_path is required")
            if output_dir:
                out_dir = _host_path(output_dir)
                out_dir.mkdir(parents=True, exist_ok=True)
                script_path = out_dir / f"urban_host_python_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.py"
            else:
                handle = tempfile.NamedTemporaryFile(prefix="urban_host_python_", suffix=".py", delete=False, mode="w", encoding="utf-8")
                script_path = Path(handle.name)
                temporary_script = True
                handle.close()
            script_path.write_text(str(code), encoding="utf-8")

        env = os.environ.copy()
        for key, value in (args.get("env") or {}).items():
            env[str(key)] = str(value)

        cmd = [python_executable, str(script_path), *argv]
        started = time.time()
        proc = subprocess.run(
            cmd,
            cwd=str(workdir),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
        )
        duration = round(time.time() - started, 3)
        stdout_tail = proc.stdout[-20000:]
        stderr_tail = proc.stderr[-20000:]
        result = {
            "command": cmd,
            "workdir": str(workdir),
            "returncode": proc.returncode,
            "duration_s": duration,
            "stdout_tail": stdout_tail,
            "stderr_tail": stderr_tail,
            "script_path": str(script_path) if keep_script or script_path_arg else None,
            "windows_native": os.name == "nt",
        }
        if temporary_script and not keep_script:
            try:
                script_path.unlink(missing_ok=True)
            except OSError:
                result["cleanup_warning"] = f"could not remove temporary script: {script_path}"
        return _ok(result, host=os.name) if proc.returncode == 0 else _fail("host python script failed", result=result, host=os.name)
    except subprocess.TimeoutExpired as exc:
        return _fail(f"host python script timed out after {timeout}s", stdout=exc.stdout, stderr=exc.stderr, host=os.name)
    except Exception as exc:
        return _fail(str(exc), host=os.name, script_path=str(script_path) if script_path else None)


def _handle_capabilities(args: dict[str, Any], **_: Any) -> str:
    task = args.get("task") or args.get("query") or "urban spatial analysis"
    limit = int(args.get("limit") or 6)
    try:
        from urban_agent.capabilities import get_default_capability_registry

        registry = get_default_capability_registry()
        selected = registry.select_for_task(str(task), limit=limit)
        return _ok(selected, source="urban_agent.capability_registry")
    except Exception as exc:
        fallback = _fallback_capabilities(str(task), limit=limit)
        return _ok(fallback, source="fallback", warning=str(exc))


def _handle_fetch_osm(args: dict[str, Any], **_: Any) -> str:
    location = str(args.get("location") or "sample district")
    radius = float(args.get("radius") or 500)
    data_types = [str(item) for item in args.get("data_types") or ["roads", "buildings", "pois"]]
    use_mock = bool(args.get("mock", False))
    if not use_mock:
        try:
            return _ok(_fetch_osmnx(location, radius, data_types), source="osmnx")
        except Exception as exc:
            synthetic = _synthetic_osm(location, radius, data_types)
            synthetic["warning"] = f"osmnx unavailable or fetch failed: {exc}"
            return _ok(synthetic, source="synthetic_fallback")
    return _ok(_synthetic_osm(location, radius, data_types), source="synthetic")


def _handle_connectivity(args: dict[str, Any], **_: Any) -> str:
    graph = args.get("road_graph") or args.get("graph") or {}
    if hasattr(graph, "degree"):
        degrees = [degree for _, degree in graph.degree()]
        node_count = len(graph.nodes())
        edge_count = len(graph.edges())
    else:
        nodes = graph.get("nodes", []) if isinstance(graph, dict) else []
        edges = graph.get("edges", []) if isinstance(graph, dict) else []
        degree_counter: Counter[str] = Counter()
        for edge in edges:
            u = str(edge.get("u") or edge.get("source") or "")
            v = str(edge.get("v") or edge.get("target") or "")
            if u:
                degree_counter[u] += 1
            if v:
                degree_counter[v] += 1
        node_ids = [str(node.get("id")) for node in nodes if isinstance(node, dict)]
        for node_id in node_ids:
            degree_counter.setdefault(node_id, 0)
        degrees = list(degree_counter.values())
        node_count = len(node_ids) or len(degree_counter)
        edge_count = len(edges)
    average_degree = sum(degrees) / len(degrees) if degrees else 0.0
    density = (2 * edge_count / (node_count * (node_count - 1))) if node_count > 1 else 0.0
    isolated = sum(1 for degree in degrees if degree == 0)
    return _ok(
        {
            "average_degree": average_degree,
            "max_degree": max(degrees) if degrees else 0,
            "node_count": node_count,
            "edge_count": edge_count,
            "density": density,
            "isolated_nodes": isolated,
            "connectivity_class": "high" if average_degree >= 2.5 else "moderate" if average_degree >= 1.5 else "low",
        }
    )


def _handle_accessibility(args: dict[str, Any], **_: Any) -> str:
    buildings = _feature_list(args.get("buildings") or args.get("origins") or [])
    target_points = [_point_like(item) for item in args.get("target_points") or args.get("targets") or []]
    target_points = [item for item in target_points if item is not None]
    max_distance = float(args.get("max_distance") or args.get("threshold") or 500)
    if not buildings or not target_points:
        return _fail("buildings and target_points are required")
    distances: list[float] = []
    for feature in buildings:
        centroid = _feature_centroid(feature)
        if centroid is None:
            continue
        distances.append(min(_distance_m(centroid, target) for target in target_points))
    if not distances:
        return _fail("no valid building centroids found")
    distances_sorted = sorted(distances)
    return _ok(
        {
            "origin_count": len(distances),
            "target_count": len(target_points),
            "average_distance_m": sum(distances) / len(distances),
            "median_distance_m": distances_sorted[len(distances_sorted) // 2],
            "coverage_ratio": sum(1 for item in distances if item <= max_distance) / len(distances),
            "within_100m": sum(1 for item in distances if item <= 100) / len(distances),
            "within_300m": sum(1 for item in distances if item <= 300) / len(distances),
        }
    )


def _handle_density(args: dict[str, Any], **_: Any) -> str:
    features = _feature_list(args.get("buildings") or args.get("features") or [])
    grid_size = float(args.get("grid_size") or 100)
    if not features:
        return _fail("features or buildings are required")
    bbox = _features_bbox(features)
    if bbox is None:
        return _fail("could not derive feature bounds")
    width_m = max(1.0, _distance_m((bbox[0], bbox[1]), (bbox[2], bbox[1])))
    height_m = max(1.0, _distance_m((bbox[0], bbox[1]), (bbox[0], bbox[3])))
    x_cells = max(1, math.ceil(width_m / grid_size))
    y_cells = max(1, math.ceil(height_m / grid_size))
    cells = [0.0 for _ in range(x_cells * y_cells)]
    for feature in features:
        centroid = _feature_centroid(feature)
        if centroid is None:
            continue
        x_ratio = (centroid[0] - bbox[0]) / max(bbox[2] - bbox[0], 1e-12)
        y_ratio = (centroid[1] - bbox[1]) / max(bbox[3] - bbox[1], 1e-12)
        x_idx = min(x_cells - 1, max(0, int(x_ratio * x_cells)))
        y_idx = min(y_cells - 1, max(0, int(y_ratio * y_cells)))
        cells[y_idx * x_cells + x_idx] += _feature_area_m2(feature)
    mean_density = sum(cells) / len(cells)
    variance = sum((cell - mean_density) ** 2 for cell in cells) / len(cells)
    uniformity = 1.0 / ((math.sqrt(variance) / (mean_density + 1e-9)) + 1.0)
    return _ok(
        {
            "grid_shape": [y_cells, x_cells],
            "mean_density": mean_density,
            "max_density": max(cells) if cells else 0.0,
            "uniformity": uniformity,
            "bbox": bbox,
        }
    )


def _handle_svg(args: dict[str, Any], **_: Any) -> str:
    base_features = args.get("base_features") or args.get("features") or {}
    interventions = args.get("interventions") or args.get("intervention_areas") or []
    bbox = [float(item) for item in args.get("bbox") or _infer_bbox(base_features) or [0, 0, 1, 1]]
    width = int(args.get("width") or 800)
    height = int(args.get("height") or max(300, width * 0.65))
    svg = _make_svg(base_features, interventions, bbox, width, height)
    return _ok({"svg_content": svg, "format": "svg", "size": len(svg), "bbox": bbox})


def _handle_geojson(args: dict[str, Any], **_: Any) -> str:
    features = args.get("features") or []
    crs = str(args.get("crs") or "EPSG:4326")
    collection = _feature_collection(features, crs=crs)
    return _ok({"geojson": collection, "feature_count": len(collection["features"])})


def _handle_topology(args: dict[str, Any], **_: Any) -> str:
    features = _feature_list(args.get("features") or args.get("base_features") or [])
    threshold = float(args.get("relation_threshold") or 100)
    nodes = []
    for index, feature in enumerate(features):
        centroid = _feature_centroid(feature)
        if centroid is None:
            continue
        nodes.append(
            {
                "id": str(feature.get("id") or feature.get("properties", {}).get("id") or f"node_{index + 1}"),
                "type": _infer_feature_type(feature),
                "centroid": list(centroid),
                "properties": dict(feature.get("properties") or {}),
            }
        )
    relations = []
    for left_index, left in enumerate(nodes):
        for right in nodes[left_index + 1 :]:
            distance = _distance_m(tuple(left["centroid"]), tuple(right["centroid"]))
            if distance <= threshold:
                relations.append(
                    {
                        "source": left["id"],
                        "target": right["id"],
                        "relation": "adjacent" if distance <= threshold / 2 else "connected",
                        "distance_m": distance,
                    }
                )
    return _ok({"nodes": nodes, "relations": relations, "threshold_m": threshold})


def _handle_ground_task(args: dict[str, Any], **_: Any) -> str:
    task_data = args.get("task_data") if isinstance(args.get("task_data"), dict) else dict(args)
    task_text = str(args.get("task") or task_data.get("task") or task_data.get("question") or task_data)
    capability_pack = json.loads(_handle_capabilities({"task": task_text, "limit": args.get("capability_limit", 6)}))["result"]
    research_memory = _search_research_memory(task_text, limit=int(args.get("research_memory_limit") or 4))
    evidence = _build_evidence_manifest(task_data, task_text)
    gaps = _evidence_gaps(evidence, task_text)
    dataset_cards = _dataset_cards(task_data, evidence)
    plan = _execution_plan(task_text, capability_pack, evidence, gaps, research_memory=research_memory)
    grounding = {
        "status": "grounded_with_gaps" if gaps else "grounded",
        "task": task_text,
        "capability_context": capability_pack,
        "research_design_memory": research_memory,
        "dataset_cards": dataset_cards,
        "evidence_manifest": evidence,
        "grounding_gaps": gaps,
        "execution_plan": plan,
        "quality_gate": {
            "mode": "configurator",
            "passed": not any(item.get("severity") == "critical" for item in gaps),
            "checked_at": datetime.now().isoformat(),
        },
    }
    return _ok(grounding)


def _handle_review(args: dict[str, Any], **_: Any) -> str:
    results = args.get("results") or args.get("analysis") or args
    evidence = args.get("evidence_manifest") or _find_evidence(results)
    policy_scores = {
        "spatial_structural_review": _score_spatial(evidence, results),
        "temporal_consistency_review": _score_temporal(evidence, results),
        "population_and_stakeholder_review": _score_population(evidence, results),
        "evidence_and_governance_review": _score_governance(evidence, results),
    }
    applicable_scores = [item["score"] for item in policy_scores.values() if item.get("applicable", True)]
    validity = sum(applicable_scores) / len(applicable_scores) if applicable_scores else 1.0
    issues = [issue for item in policy_scores.values() for issue in item.get("issues", [])]
    hard_failures = [name for name, item in policy_scores.items() if item["score"] < 0.55 and item.get("applicable", True)]
    passed = validity >= float(args.get("threshold") or 0.70) and not hard_failures
    return _ok(
        {
            "urban_validity_score": validity,
            "quality_score": validity,
            "passed": passed,
            "policy_scores": policy_scores,
            "issues": issues,
            "hard_failures": hard_failures,
            "recommendation": "accept" if passed and not issues else "accept_with_warnings" if passed else "revise",
            "reviewed_at": datetime.now().isoformat(),
        }
    )


def _handle_quality(args: dict[str, Any], **_: Any) -> str:
    output = args.get("output") or args.get("results") or args
    required = [str(item) for item in args.get("required_fields") or []]
    issues = []
    if not isinstance(output, dict):
        issues.append("output is not a JSON object")
    for field in required:
        if isinstance(output, dict) and field not in output:
            issues.append(f"missing required field: {field}")
    confidence = 1.0 if not issues else max(0.0, 1.0 - 0.25 * len(issues))
    return _ok(
        {
            "confidence_score": confidence,
            "passed": not issues,
            "issues": issues,
            "recommendation": "accept" if not issues else "reject",
            "dimension_scores": {"syntax": 1.0 if isinstance(output, dict) else 0.0, "required_fields": 1.0 if not issues else confidence},
        }
    )


def _handle_record_feedback(args: dict[str, Any], **_: Any) -> str:
    from .memory_provider import UrbanMemoryProvider

    provider = UrbanMemoryProvider()
    provider.initialize(session_id=str(args.get("session_id") or "tool-call"))
    return provider.handle_tool_call("urban_memory_record", args)


def _handle_research_memory(args: dict[str, Any], **_: Any) -> str:
    """Search or record reusable urban research-design lessons."""
    from .memory_provider import UrbanMemoryProvider

    provider = UrbanMemoryProvider()
    provider.initialize(session_id=str(args.get("session_id") or "tool-call"))
    return provider.handle_tool_call("urban_research_memory", args)


def _handle_qgis_workspace(args: dict[str, Any], **_: Any) -> str:
    """Package GIS outputs into a QGIS project plus agent-readable manifest."""
    from .paths import PAPER4_ROOT

    workspace_type = str(args.get("workspace_type") or "case1_nanjing_200m")
    run_dir_raw = args.get("run_dir")
    if not run_dir_raw:
        return _fail("run_dir is required so the workspace packager does not guess which experiment to package")
    run_dir = _host_path(run_dir_raw)
    if not run_dir.exists():
        return _fail(f"run_dir does not exist: {run_dir}")

    if args.get("packager_script"):
        packager_script = _host_path(args["packager_script"])
    elif workspace_type == "case1_nanjing_200m":
        packager_script = PAPER4_ROOT / "scripts" / "package_case1_qgis_workspace.py"
    else:
        return _fail(
            f"unsupported workspace_type: {workspace_type}",
            hint="Author a workspace packager with urban_host_python, then call this tool with packager_script.",
        )
    if not packager_script.exists():
        return _fail(
            f"packager script does not exist: {packager_script}",
            hint="Use urban_host_python to create a task-specific QGIS workspace packager, then record the pattern with urban_research_memory.",
        )

    qgis_python = _resolve_qgis_python(args.get("qgis_python"))
    timeout = int(args.get("timeout") or 600)
    command = [sys.executable, str(packager_script), "--run-dir", str(run_dir)]
    if qgis_python:
        command.extend(["--qgis-python", qgis_python])
    started = datetime.now().isoformat()
    try:
        completed = subprocess.run(
            command,
            cwd=str(PAPER4_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        return _fail("qgis workspace packager timed out", command=command, timeout_s=timeout, stdout=exc.stdout, stderr=exc.stderr)
    except Exception as exc:
        return _fail(f"qgis workspace packager failed to start: {exc}", command=command)

    parsed_stdout = None
    stdout = completed.stdout or ""
    for start in [idx for idx, char in enumerate(stdout) if char == "{"]:
        try:
            parsed_stdout = json.loads(stdout[start:])
            break
        except Exception:
            continue

    workspace = run_dir / "qgis_workspace"
    manifest_path = workspace / "manifests" / "spatial_reasoning_manifest.json"
    manifest = None
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            manifest = {"read_warning": str(exc), "path": str(manifest_path)}
    project_qgz = Path(str(manifest.get("project_qgz"))) if isinstance(manifest, dict) and manifest.get("project_qgz") else workspace / "project" / "case1_nanjing_road_200m_grid_workspace.qgz"
    result = {
        "workspace_type": workspace_type,
        "command": command,
        "returncode": completed.returncode,
        "stdout_tail": stdout[-4000:],
        "stderr_tail": (completed.stderr or "")[-4000:],
        "parsed_stdout": parsed_stdout,
        "workspace": str(workspace),
        "manifest_path": str(manifest_path),
        "manifest_exists": manifest_path.exists(),
        "project_qgz": str(project_qgz),
        "project_qgz_exists": project_qgz.exists(),
        "layer_count": len(manifest.get("layers", [])) if isinstance(manifest, dict) else None,
        "started_at": started,
        "finished_at": datetime.now().isoformat(),
    }
    success = completed.returncode == 0 and result["manifest_exists"] and result["project_qgz_exists"]
    return _json({"success": success, "result": result, "error": None if success else "workspace packager did not complete cleanly"})


def _handle_qgis_process(args: dict[str, Any], **_: Any) -> str:
    """Run qgis_process directly from the Hermes-Urban Python process."""
    algorithm = str(args.get("algorithm") or "").strip()
    if not algorithm:
        return _fail("algorithm is required, e.g. native:fixgeometries")
    parameters = args.get("parameters") if isinstance(args.get("parameters"), dict) else {}
    if not parameters:
        return _fail("parameters are required")

    qgis_path = _resolve_qgis_process(args.get("qgis_process"))
    if not qgis_path:
        return _fail(
            "qgis_process was not found",
            searched=_candidate_qgis_process_paths(),
            hint="Pass qgis_process explicitly, or install QGIS 3.x in a standard location.",
        )

    command = _qgis_command(qgis_path, algorithm, parameters, verbose=bool(args.get("verbose", False)))
    timeout = int(args.get("timeout") or 300)
    started = datetime.now().isoformat()
    try:
        completed = subprocess.run(
            command,
            cwd=str(args.get("workdir") or Path.cwd()),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        _write_qgis_log(args, command, started, returncode=None, stdout=exc.stdout, stderr=exc.stderr, timed_out=True)
        return _fail("qgis_process timed out", command=command, timeout_s=timeout)
    except Exception as exc:
        _write_qgis_log(args, command, started, returncode=None, stdout="", stderr=str(exc), timed_out=False)
        return _fail(f"qgis_process failed to start: {exc}", command=command)

    outputs = _qgis_outputs(parameters)
    verification = [_verify_spatial_output(path) for path in outputs]
    log_path = _write_qgis_log(
        args,
        command,
        started,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        timed_out=False,
        outputs=verification,
    )
    success = completed.returncode == 0 and all(item.get("exists") for item in verification)
    return _json(
        {
            "success": success,
            "result": {
                "algorithm": algorithm,
                "command": command,
                "returncode": completed.returncode,
                "stdout_tail": (completed.stdout or "")[-4000:],
                "stderr_tail": (completed.stderr or "")[-4000:],
                "outputs": verification,
                "log_path": log_path,
                "started_at": started,
                "finished_at": datetime.now().isoformat(),
            },
            "error": None if success else "qgis_process returned nonzero or one or more outputs were not created",
        }
    )


def _candidate_qgis_process_paths() -> list[str]:
    env_path = os.getenv("QGIS_PROCESS") or os.getenv("QGIS_PROCESS_PATH")
    candidates = [env_path] if env_path else []
    candidates.extend(
        [
            r"C:\Program Files\QGIS 3.40.11\bin\qgis_process-qgis-ltr.bat",
            r"C:\Program Files\QGIS 3.40\bin\qgis_process-qgis-ltr.bat",
            r"C:\Program Files\QGIS 3.40.11\apps\qgis-ltr\bin\qgis_process.exe",
            r"C:\Program Files\QGIS 3.40\apps\qgis-ltr\bin\qgis_process.exe",
            "qgis_process",
        ]
    )
    return [item for item in candidates if item]


def _candidate_qgis_python_paths() -> list[str]:
    env_path = os.getenv("QGIS_PYTHON") or os.getenv("QGIS_PYTHON_PATH")
    candidates = [env_path] if env_path else []
    candidates.extend(
        [
            r"C:\Program Files\QGIS 3.40.11\bin\python-qgis-ltr.bat",
            r"C:\Program Files\QGIS 3.40\bin\python-qgis-ltr.bat",
            r"C:\Program Files\QGIS 3.40.11\bin\python.exe",
            r"C:\Program Files\QGIS 3.40\bin\python.exe",
        ]
    )
    return [item for item in candidates if item]


def _resolve_qgis_python(value: Any = None) -> str | None:
    candidates = [str(value)] if value else []
    candidates.extend(_candidate_qgis_python_paths())
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.exists():
            return str(path)
    return None


def _resolve_qgis_process(value: Any = None) -> str | None:
    candidates = [str(value)] if value else []
    candidates.extend(_candidate_qgis_process_paths())
    for candidate in candidates:
        if not candidate:
            continue
        if candidate == "qgis_process":
            return candidate
        path = Path(candidate)
        if path.exists():
            return str(path)
    return None


def _qgis_command(qgis_path: str, algorithm: str, parameters: dict[str, Any], *, verbose: bool) -> list[str]:
    args: list[str] = []
    if os.name == "nt" and qgis_path.lower().endswith((".bat", ".cmd")):
        args.extend(["cmd.exe", "/c", qgis_path])
    else:
        args.append(qgis_path)
    if verbose:
        args.append("--verbose")
    args.extend(["run", algorithm, "--"])
    for key, value in parameters.items():
        if value is None:
            continue
        if isinstance(value, list):
            for item in value:
                args.append(f"{key}={item}")
        else:
            args.append(f"{key}={value}")
    return args


def _qgis_outputs(parameters: dict[str, Any]) -> list[str]:
    outputs = []
    for key, value in parameters.items():
        if "OUTPUT" not in str(key).upper():
            continue
        values = value if isinstance(value, list) else [value]
        for item in values:
            text = str(item)
            if text and not text.lower().startswith("memory:") and text.upper() != "TEMPORARY_OUTPUT":
                outputs.append(text)
    return outputs


def _verify_spatial_output(path: str) -> dict[str, Any]:
    item: dict[str, Any] = {"path": path, "exists": Path(path).exists()}
    if not item["exists"]:
        return item
    item["size_bytes"] = Path(path).stat().st_size
    if path.lower().endswith((".geojson", ".json")):
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
            features = data.get("features") if isinstance(data, dict) else None
            if isinstance(features, list):
                item["feature_count"] = len(features)
                types = Counter(str((feature.get("geometry") or {}).get("type")) for feature in features if isinstance(feature, dict))
                item["geometry_types"] = dict(types)
        except Exception as exc:
            item["read_warning"] = str(exc)
    return item


def _write_qgis_log(
    args: dict[str, Any],
    command: list[str],
    started: str,
    *,
    returncode: int | None,
    stdout: Any,
    stderr: Any,
    timed_out: bool,
    outputs: list[dict[str, Any]] | None = None,
) -> str | None:
    log_path_raw = args.get("log_path")
    if not log_path_raw and args.get("output_dir"):
        log_path_raw = str(Path(str(args["output_dir"])) / "qgis_process_log.jsonl")
    if not log_path_raw:
        return None
    path = Path(str(log_path_raw))
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "started_at": started,
        "finished_at": datetime.now().isoformat(),
        "command": command,
        "returncode": returncode,
        "timed_out": timed_out,
        "stdout": stdout or "",
        "stderr": stderr or "",
        "outputs": outputs or [],
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    return str(path)


def _fallback_capabilities(task: str, *, limit: int) -> dict[str, Any]:
    catalog = [
        _capability("osm_acquisition", "OpenStreetMap acquisition", "data", "Fetch roads, buildings, POIs, land use", ["location"], ["osm_features"], ["osm", "open-data"]),
        _capability("network_connectivity", "Network connectivity", "analysis", "Measure node degree, density, isolated nodes", ["road_graph"], ["connectivity_metrics"], ["network", "topology"]),
        _capability("accessibility", "Accessibility measurement", "analysis", "Measure origin-to-target access distances", ["origins", "targets"], ["coverage", "distance_metrics"], ["walkability"]),
        _capability("density", "Urban density", "analysis", "Compute grid density and uniformity", ["features"], ["density_grid"], ["morphology"]),
        _capability("svg_overlay", "SVG overlay", "cartography", "Generate reviewable map artifact", ["features", "bbox"], ["svg"], ["cartography", "artifact"]),
        _capability("review_hub", "Urban Review Hub", "review", "Review spatial, temporal, population and governance evidence", ["analysis", "evidence_manifest"], ["review_report"], ["review", "governance"]),
    ]
    terms = set(_tokens(task))
    ranked = sorted(catalog, key=lambda item: -len(terms & set(item["tags"] + [item["name"]])))[:limit]
    return {
        "disclosure_policy": "progressive",
        "level0_index_size": len(catalog),
        "selected_names": [item["name"] for item in ranked],
        "selected_level0": [{key: item[key] for key in ("name", "title", "family", "summary", "tags")} for item in ranked],
        "level1_cards": ranked,
    }


def _capability(name: str, title: str, family: str, summary: str, inputs: list[str], outputs: list[str], tags: list[str]) -> dict[str, Any]:
    return {"name": name, "title": title, "family": family, "type": "urban_method", "summary": summary, "inputs": inputs, "outputs": outputs, "tags": tags, "backend_names": [f"urban_{name}"], "constraints": []}


def _fetch_osmnx(location: str, radius: float, data_types: list[str]) -> dict[str, Any]:
    import osmnx as ox

    result: dict[str, Any] = {"location": location, "radius_m": radius, "data_types": data_types}
    if "roads" in data_types:
        graph = ox.graph_from_address(location, dist=radius, network_type="all")
        result["road_graph"] = _summarize_networkx_graph(graph)
    tags = {}
    if "buildings" in data_types:
        tags["building"] = True
    if "pois" in data_types:
        tags.update({"amenity": True, "shop": True})
    if tags:
        gdf = ox.features_from_address(location, tags=tags, dist=radius)
        try:
            gdf = gdf.to_crs(epsg=4326)
        except Exception:
            pass
        collection = json.loads(gdf.head(200).to_json())
        if "buildings" in data_types:
            result["buildings"] = [feature for feature in collection.get("features", []) if feature.get("properties", {}).get("building")]
        if "pois" in data_types:
            result["pois"] = [feature for feature in collection.get("features", []) if feature not in result.get("buildings", [])]
    result["bbox"] = _infer_bbox(result)
    return result


def _summarize_networkx_graph(graph: Any, *, limit: int = 500) -> dict[str, Any]:
    nodes = []
    for node_id, data in list(graph.nodes(data=True))[:limit]:
        nodes.append({"id": str(node_id), "x": data.get("x"), "y": data.get("y")})
    edges = []
    for u, v, data in list(graph.edges(data=True))[:limit]:
        edges.append({"u": str(u), "v": str(v), "length_m": data.get("length")})
    return {"nodes": nodes, "edges": edges, "node_count_total": len(graph.nodes()), "edge_count_total": len(graph.edges())}


def _synthetic_osm(location: str, radius: float, data_types: list[str]) -> dict[str, Any]:
    center = _synthetic_center(location)
    lon, lat = center
    delta = max(radius, 100) / 111_320
    nodes = [
        {"id": "n1", "x": lon - delta * 0.45, "y": lat - delta * 0.20},
        {"id": "n2", "x": lon, "y": lat - delta * 0.05},
        {"id": "n3", "x": lon + delta * 0.40, "y": lat + delta * 0.10},
        {"id": "n4", "x": lon - delta * 0.20, "y": lat + delta * 0.35},
    ]
    edges = [
        {"u": "n1", "v": "n2", "length_m": 130},
        {"u": "n2", "v": "n3", "length_m": 145},
        {"u": "n2", "v": "n4", "length_m": 115},
        {"u": "n4", "v": "n3", "length_m": 160},
    ]
    buildings = [
        _square_feature("b1", lon - delta * 0.25, lat - delta * 0.15, 35, {"type": "building", "area_m2": 1225}),
        _square_feature("b2", lon + delta * 0.12, lat - delta * 0.08, 42, {"type": "building", "area_m2": 1764}),
        _square_feature("b3", lon - delta * 0.05, lat + delta * 0.20, 55, {"type": "building", "area_m2": 3025}),
    ]
    pois = [
        _point_feature("p1", lon + delta * 0.20, lat + delta * 0.15, {"type": "poi", "amenity": "cafe"}),
        _point_feature("p2", lon - delta * 0.32, lat + delta * 0.22, {"type": "poi", "amenity": "park"}),
    ]
    result: dict[str, Any] = {"location": location, "radius_m": radius, "center": [lon, lat], "bbox": [lon - delta, lat - delta, lon + delta, lat + delta]}
    if "roads" in data_types:
        result["road_graph"] = {"nodes": nodes, "edges": edges}
    if "buildings" in data_types:
        result["buildings"] = buildings
    if "pois" in data_types:
        result["pois"] = pois
    return result


def _build_evidence_manifest(task_data: dict[str, Any], task_text: str) -> dict[str, Any]:
    bbox = task_data.get("bbox") or _infer_bbox(task_data)
    location = task_data.get("location") or task_data.get("place")
    spatial = {
        "bbox": bbox,
        "crs": task_data.get("crs") or "EPSG:4326" if bbox or location else None,
        "admin_level": task_data.get("admin_level"),
        "scale_band": task_data.get("scale_band") or _infer_scale(task_text),
        "spatial_relation_frame": task_data.get("spatial_relation_frame") or "network+metric" if _mentions(task_text, ["walk", "route", "access", "connect", "topology"]) else None,
    }
    temporal = {
        "timestamp": task_data.get("timestamp") or datetime.now().isoformat(),
        "time_window": task_data.get("time_window") or task_data.get("temporal_range"),
        "granularity": task_data.get("granularity"),
        "forecast_horizon": task_data.get("forecast_horizon"),
        "freshness": task_data.get("freshness"),
    }
    population = {
        "target_group": task_data.get("target_group") or "pedestrians" if _mentions(task_text, ["walk", "pedestrian", "accessibility"]) else task_data.get("target_group"),
        "observed_group": task_data.get("observed_group"),
        "affected_group": task_data.get("affected_group"),
        "sampling_bias": task_data.get("sampling_bias"),
        "stakeholder_source": task_data.get("stakeholder_source"),
    }
    governance = {
        "provenance": task_data.get("provenance") or "OpenStreetMap/synthetic fixture" if task_data.get("mock") or location else task_data.get("provenance"),
        "license": task_data.get("license") or "ODbL or fixture-only" if task_data.get("mock") or location else task_data.get("license"),
        "collection_method": task_data.get("collection_method") or "tool-mediated acquisition",
        "uncertainty": task_data.get("uncertainty"),
        "missing_layers": list(task_data.get("missing_layers") or []),
    }
    tags = ["urban", "hermes", "grounding"]
    if _mentions(task_text, ["walk", "access"]):
        tags.append("walkability")
    if _mentions(task_text, ["mobility", "trajectory", "traffic"]):
        tags.append("mobility")
    return {"spatial": spatial, "temporal": temporal, "population": population, "governance": governance, "tags": tags, "data_sources": _data_sources(task_data)}


def _evidence_gaps(evidence: dict[str, Any], task_text: str) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    spatial = evidence.get("spatial", {})
    temporal = evidence.get("temporal", {})
    population = evidence.get("population", {})
    governance = evidence.get("governance", {})
    if not spatial.get("bbox"):
        gaps.append({"dimension": "spatial", "field": "bbox", "severity": "warning", "message": "No explicit spatial extent was supplied."})
    if not spatial.get("crs"):
        gaps.append({"dimension": "spatial", "field": "crs", "severity": "warning", "message": "CRS is not declared."})
    if _mentions(task_text, ["mobility", "temporal", "trajectory", "traffic", "forecast"]) and not temporal.get("time_window"):
        gaps.append({"dimension": "temporal", "field": "time_window", "severity": "warning", "message": "Temporal workflow lacks observation window."})
    if _mentions(task_text, ["people", "pedestrian", "population", "stakeholder", "walk"]) and not population.get("affected_group"):
        gaps.append({"dimension": "population", "field": "affected_group", "severity": "warning", "message": "Affected group is not explicit."})
    for field in ("provenance", "license", "uncertainty"):
        if not governance.get(field):
            gaps.append({"dimension": "governance", "field": field, "severity": "warning", "message": f"Governance field {field} is missing."})
    return gaps


def _dataset_cards(task_data: dict[str, Any], evidence: dict[str, Any]) -> list[dict[str, Any]]:
    cards = task_data.get("dataset_cards")
    if isinstance(cards, list) and cards:
        return cards
    sources = evidence.get("data_sources") or ["task_context"]
    return [
        {
            "resource_id": f"dataset_{index + 1}",
            "name": str(source),
            "role": "primary_evidence" if index == 0 else "supporting_evidence",
            "spatial": evidence.get("spatial", {}),
            "temporal": evidence.get("temporal", {}),
            "governance": evidence.get("governance", {}),
            "known_limits": evidence.get("governance", {}).get("missing_layers") or ["coverage and freshness should be verified before final claims"],
        }
        for index, source in enumerate(sources)
    ]


def _search_research_memory(task_text: str, *, limit: int = 4) -> list[dict[str, Any]]:
    try:
        from .memory_provider import UrbanMemoryProvider

        provider = UrbanMemoryProvider()
        provider.initialize(session_id="ground-task")
        raw = provider.handle_tool_call("urban_research_memory", {"action": "search", "query": task_text, "limit": limit})
        payload = json.loads(raw)
        result = payload.get("result") if isinstance(payload, dict) else {}
        records = result.get("records") if isinstance(result, dict) else []
        return records if isinstance(records, list) else []
    except Exception:
        return []


def _execution_plan(
    task_text: str,
    capability_pack: dict[str, Any],
    evidence: dict[str, Any],
    gaps: list[dict[str, str]],
    *,
    research_memory: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    names = capability_pack.get("selected_names", []) if isinstance(capability_pack, dict) else []
    return {
        "plan_id": f"urban_{int(time.time())}",
        "workflow_profile": "hermes_urban_gap_harness",
        "task": task_text,
        "selected_capabilities": names,
        "research_design_cues": [
            {
                "record_id": item.get("record_id"),
                "summary": item.get("summary"),
                "method_hint": item.get("method_hint"),
                "caveats": item.get("caveats"),
            }
            for item in (research_memory or [])[:4]
        ],
        "steps": [
            {"id": "ground", "tool": "urban_ground_task", "purpose": "make data/method/evidence requirements explicit"},
            {"id": "recall", "tool": "urban_research_memory", "purpose": "retrieve reusable research-design cues when the task is still under-specified"},
            {"id": "acquire", "tool": "urban_fetch_osm", "purpose": "collect open spatial evidence when needed"},
            {"id": "analyze", "tool": "urban_analyze_connectivity|urban_measure_accessibility|urban_calculate_density", "purpose": "run reviewable operators"},
            {"id": "review", "tool": "urban_review", "purpose": "score spatial/temporal/population/governance assumptions"},
            {"id": "reuse", "tool": "urban_record_feedback", "purpose": "store human corrections as reusable memory"},
        ],
        "known_gaps": gaps,
        "evidence_manifest": evidence,
    }


def _score_spatial(evidence: dict[str, Any], results: Any) -> dict[str, Any]:
    spatial = (evidence or {}).get("spatial", {}) if isinstance(evidence, dict) else {}
    issues = []
    score = 1.0
    if not spatial.get("bbox"):
        issues.append("missing bbox")
        score -= 0.25
    if not spatial.get("crs"):
        issues.append("missing CRS")
        score -= 0.20
    if _result_mentions(results, ["route", "connect", "access", "walk"]) and not spatial.get("spatial_relation_frame"):
        issues.append("missing spatial relation frame for network/access reasoning")
        score -= 0.15
    return {"score": max(0.0, score), "issues": issues, "applicable": True}


def _score_temporal(evidence: dict[str, Any], results: Any) -> dict[str, Any]:
    temporal = (evidence or {}).get("temporal", {}) if isinstance(evidence, dict) else {}
    applicable = _result_mentions(results, ["mobility", "trajectory", "traffic", "forecast", "temporal"])
    if not applicable and not any(value for value in temporal.values()):
        return {"score": 1.0, "issues": [], "applicable": False}
    issues = []
    score = 1.0
    if applicable and not temporal.get("time_window"):
        issues.append("missing time_window")
        score -= 0.25
    if applicable and not temporal.get("freshness"):
        issues.append("missing freshness declaration")
        score -= 0.15
    return {"score": max(0.0, score), "issues": issues, "applicable": True}


def _score_population(evidence: dict[str, Any], results: Any) -> dict[str, Any]:
    population = (evidence or {}).get("population", {}) if isinstance(evidence, dict) else {}
    applicable = _result_mentions(results, ["walk", "people", "pedestrian", "stakeholder", "population", "access"])
    if not applicable and not any(value for value in population.values()):
        return {"score": 1.0, "issues": [], "applicable": False}
    issues = []
    score = 1.0
    if not population.get("target_group"):
        issues.append("missing target_group")
        score -= 0.20
    if applicable and not population.get("affected_group"):
        issues.append("missing affected_group")
        score -= 0.25
    if not population.get("stakeholder_source"):
        issues.append("missing stakeholder_source")
        score -= 0.10
    return {"score": max(0.0, score), "issues": issues, "applicable": True}


def _score_governance(evidence: dict[str, Any], results: Any) -> dict[str, Any]:
    governance = (evidence or {}).get("governance", {}) if isinstance(evidence, dict) else {}
    tags = (evidence or {}).get("tags", []) if isinstance(evidence, dict) else []
    issues = []
    score = 1.0
    for field in ("provenance", "license", "collection_method", "uncertainty"):
        if not governance.get(field):
            issues.append(f"missing governance field {field}")
            score -= 0.12
    if governance.get("missing_layers"):
        issues.append(f"missing evidence layers: {governance.get('missing_layers')}")
        score -= 0.10
    if not tags:
        issues.append("evidence manifest has no tags")
        score -= 0.05
    return {"score": max(0.0, score), "issues": issues, "applicable": True}


def _find_evidence(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        if isinstance(value.get("evidence_manifest"), dict):
            return value["evidence_manifest"]
        for item in value.values():
            found = _find_evidence(item)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_evidence(item)
            if found:
                return found
    return {}


def _tokens(text: str) -> list[str]:
    import re

    return re.findall(r"[a-z0-9_\-]+", text.lower())


def _mentions(text: str, terms: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def _result_mentions(value: Any, terms: Iterable[str]) -> bool:
    return _mentions(json.dumps(value, ensure_ascii=False, default=str), terms)


def _data_sources(task_data: dict[str, Any]) -> list[str]:
    sources = task_data.get("data_sources") or task_data.get("sources") or []
    if isinstance(sources, str):
        sources = [sources]
    if task_data.get("location"):
        sources = list(sources) + [f"open-data:{task_data['location']}"]
    return [str(item) for item in sources] or ["task_context"]


def _infer_scale(task_text: str) -> str:
    if _mentions(task_text, ["street", "block", "walk"]):
        return "street_to_neighborhood"
    if _mentions(task_text, ["city", "metropolitan"]):
        return "city"
    return "district"


def _synthetic_center(location: str) -> tuple[float, float]:
    lowered = location.lower()
    if "marais" in lowered or "paris" in lowered:
        return (2.361, 48.858)
    if "pudong" in lowered or "shanghai" in lowered:
        return (121.544, 31.221)
    return (0.0, 0.0)


def _feature_collection(features: Any, *, crs: str = "EPSG:4326") -> dict[str, Any]:
    if isinstance(features, dict) and features.get("type") == "FeatureCollection":
        collection = dict(features)
        collection.setdefault("crs", {"type": "name", "properties": {"name": crs}})
        return collection
    return {"type": "FeatureCollection", "crs": {"type": "name", "properties": {"name": crs}}, "features": _feature_list(features)}


def _feature_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        if value.get("type") == "FeatureCollection":
            return [item for item in value.get("features", []) if isinstance(item, dict)]
        if value.get("type") == "Feature":
            return [value]
        features = []
        for key in ("buildings", "pois", "features"):
            features.extend(_feature_list(value.get(key, [])))
        return features
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _point_like(value: Any) -> tuple[float, float] | None:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return (float(value[0]), float(value[1]))
    if isinstance(value, dict):
        if "lon" in value and "lat" in value:
            return (float(value["lon"]), float(value["lat"]))
        if "x" in value and "y" in value:
            return (float(value["x"]), float(value["y"]))
        return _feature_centroid(value)
    return None


def _feature_centroid(feature: dict[str, Any]) -> tuple[float, float] | None:
    props = feature.get("properties") or {}
    if isinstance(props.get("centroid"), (list, tuple)) and len(props["centroid"]) >= 2:
        return (float(props["centroid"][0]), float(props["centroid"][1]))
    geom = feature.get("geometry") or {}
    coords = geom.get("coordinates")
    if geom.get("type") == "Point" and isinstance(coords, (list, tuple)) and len(coords) >= 2:
        return (float(coords[0]), float(coords[1]))
    points = list(_iter_coords(coords))
    if points:
        return (sum(point[0] for point in points) / len(points), sum(point[1] for point in points) / len(points))
    bbox = feature.get("bbox") or props.get("bbox")
    if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
        return ((float(bbox[0]) + float(bbox[2])) / 2, (float(bbox[1]) + float(bbox[3])) / 2)
    return None


def _iter_coords(value: Any):
    if isinstance(value, (list, tuple)):
        if len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
            yield (float(value[0]), float(value[1]))
        else:
            for item in value:
                yield from _iter_coords(item)


def _features_bbox(features: list[dict[str, Any]]) -> list[float] | None:
    points = []
    for feature in features:
        points.extend(_iter_coords((feature.get("geometry") or {}).get("coordinates")))
        centroid = _feature_centroid(feature)
        if centroid:
            points.append(centroid)
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def _infer_bbox(value: Any) -> list[float] | None:
    if isinstance(value, dict):
        if isinstance(value.get("bbox"), list) and len(value["bbox"]) >= 4:
            return [float(item) for item in value["bbox"][:4]]
        features = _feature_list(value)
        if features:
            return _features_bbox(features)
    return None


def _distance_m(left: tuple[float, float], right: tuple[float, float]) -> float:
    lon1, lat1 = left
    lon2, lat2 = right
    avg_lat = math.radians((lat1 + lat2) / 2)
    dx = (lon2 - lon1) * 111_320 * math.cos(avg_lat)
    dy = (lat2 - lat1) * 110_574
    return math.sqrt(dx * dx + dy * dy)


def _feature_area_m2(feature: dict[str, Any]) -> float:
    props = feature.get("properties") or {}
    if props.get("area_m2") is not None:
        return float(props["area_m2"])
    bbox = _features_bbox([feature])
    if not bbox:
        return 1.0
    return max(1.0, _distance_m((bbox[0], bbox[1]), (bbox[2], bbox[1])) * _distance_m((bbox[0], bbox[1]), (bbox[0], bbox[3])))


def _infer_feature_type(feature: dict[str, Any]) -> str:
    props = feature.get("properties") or {}
    return str(props.get("type") or props.get("amenity") or props.get("building") or "feature")


def _square_feature(feature_id: str, lon: float, lat: float, size_m: float, properties: dict[str, Any]) -> dict[str, Any]:
    dx = size_m / 111_320
    dy = size_m / 110_574
    coords = [[lon - dx / 2, lat - dy / 2], [lon + dx / 2, lat - dy / 2], [lon + dx / 2, lat + dy / 2], [lon - dx / 2, lat + dy / 2], [lon - dx / 2, lat - dy / 2]]
    return {"type": "Feature", "id": feature_id, "geometry": {"type": "Polygon", "coordinates": [coords]}, "properties": {"id": feature_id, **properties}}


def _point_feature(feature_id: str, lon: float, lat: float, properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "Feature", "id": feature_id, "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": {"id": feature_id, **properties}}


def _make_svg(base_features: Any, interventions: list[Any], bbox: list[float], width: int, height: int) -> str:
    minx, miny, maxx, maxy = bbox
    sx = width / max(maxx - minx, 1e-12)
    sy = height / max(maxy - miny, 1e-12)

    def project(point: tuple[float, float]) -> tuple[float, float]:
        return ((point[0] - minx) * sx, height - (point[1] - miny) * sy)

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">', '<rect width="100%" height="100%" fill="#f7f7f3"/>']
    graph = base_features.get("road_graph") if isinstance(base_features, dict) else None
    if isinstance(graph, dict):
        node_lookup = {str(node.get("id")): (float(node.get("x", 0)), float(node.get("y", 0))) for node in graph.get("nodes", []) if isinstance(node, dict)}
        for edge in graph.get("edges", []):
            left = node_lookup.get(str(edge.get("u")))
            right = node_lookup.get(str(edge.get("v")))
            if not left or not right:
                continue
            x1, y1 = project(left)
            x2, y2 = project(right)
            parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#8a8a8a" stroke-width="2"/>')
    for feature in _feature_list(base_features):
        geom = feature.get("geometry") or {}
        if geom.get("type") == "Point":
            center = _feature_centroid(feature)
            if center:
                x, y = project(center)
                parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="#2b7a78"/>')
            continue
        points = list(_iter_coords(geom.get("coordinates")))
        if points:
            path = " ".join(f"{project(point)[0]:.1f},{project(point)[1]:.1f}" for point in points)
            parts.append(f'<polygon points="{path}" fill="#d8c99b" stroke="#816c3a" stroke-width="1" opacity="0.75"/>')
    for item in interventions:
        if isinstance(item, dict) and isinstance(item.get("bbox"), list) and len(item["bbox"]) >= 4:
            x1, y1 = project((float(item["bbox"][0]), float(item["bbox"][1])))
            x2, y2 = project((float(item["bbox"][2]), float(item["bbox"][3])))
            parts.append(f'<rect x="{min(x1, x2):.1f}" y="{min(y1, y2):.1f}" width="{abs(x2-x1):.1f}" height="{abs(y2-y1):.1f}" fill="#d1495b" opacity="0.25" stroke="#d1495b"/>')
    parts.append("</svg>")
    return "".join(parts)


CAPABILITIES_SCHEMA = {
    "name": "urban_capabilities",
    "description": "Select UrbanAgent method-level capabilities for an urban analysis task.",
    "parameters": {"type": "object", "properties": {"task": {"type": "string"}, "limit": {"type": "integer", "default": 6}}, "required": ["task"]},
}
FETCH_OSM_SCHEMA = {
    "name": "urban_fetch_osm",
    "description": "Fetch or synthesize OSM-like roads, buildings, and POIs for a location.",
    "parameters": {"type": "object", "properties": {"location": {"type": "string"}, "radius": {"type": "number", "default": 500}, "data_types": {"type": "array", "items": {"type": "string"}}, "mock": {"type": "boolean", "default": False}}, "required": ["location"]},
}
CONNECTIVITY_SCHEMA = {"name": "urban_analyze_connectivity", "description": "Analyze road graph connectivity.", "parameters": {"type": "object", "properties": {"road_graph": {"type": "object"}}, "required": ["road_graph"]}}
ACCESSIBILITY_SCHEMA = {"name": "urban_measure_accessibility", "description": "Measure accessibility from building origins to target points.", "parameters": {"type": "object", "properties": {"buildings": {"type": "array"}, "target_points": {"type": "array"}, "max_distance": {"type": "number", "default": 500}}, "required": ["buildings", "target_points"]}}
DENSITY_SCHEMA = {"name": "urban_calculate_density", "description": "Calculate simple grid density from urban features.", "parameters": {"type": "object", "properties": {"buildings": {"type": "array"}, "features": {"type": "array"}, "grid_size": {"type": "number", "default": 100}}, "required": []}}
SVG_SCHEMA = {"name": "urban_generate_svg_overlay", "description": "Generate a reviewable SVG overlay from features and interventions.", "parameters": {"type": "object", "properties": {"base_features": {"type": "object"}, "interventions": {"type": "array"}, "bbox": {"type": "array"}, "width": {"type": "integer", "default": 800}, "height": {"type": "integer"}}, "required": ["base_features"]}}
GEOJSON_SCHEMA = {"name": "urban_export_geojson", "description": "Export features as GeoJSON FeatureCollection.", "parameters": {"type": "object", "properties": {"features": {"type": "array"}, "crs": {"type": "string", "default": "EPSG:4326"}}, "required": ["features"]}}
TOPOLOGY_SCHEMA = {"name": "urban_build_topology", "description": "Build a lightweight topology graph from urban features.", "parameters": {"type": "object", "properties": {"features": {"type": "array"}, "relation_threshold": {"type": "number", "default": 100}}, "required": ["features"]}}
GROUND_TASK_SCHEMA = {"name": "urban_ground_task", "description": "Ground an urban question in capabilities, dataset cards, research-design memory, evidence manifest, and explicit gaps.", "parameters": {"type": "object", "properties": {"task": {"type": "string"}, "location": {"type": "string"}, "bbox": {"type": "array"}, "task_data": {"type": "object"}, "capability_limit": {"type": "integer", "default": 6}, "research_memory_limit": {"type": "integer", "default": 4}}, "required": ["task"]}}
REVIEW_SCHEMA = {"name": "urban_review", "description": "Review an urban analysis under spatial, temporal, population, and governance policies.", "parameters": {"type": "object", "properties": {"analysis": {"type": "object"}, "results": {"type": "object"}, "evidence_manifest": {"type": "object"}, "threshold": {"type": "number", "default": 0.7}}, "required": []}}
QUALITY_SCHEMA = {"name": "urban_quality_control", "description": "Run lightweight configurator-style quality checks on an urban output.", "parameters": {"type": "object", "properties": {"output": {"type": "object"}, "required_fields": {"type": "array", "items": {"type": "string"}}}, "required": ["output"]}}
RECORD_FEEDBACK_SCHEMA = {"name": "urban_record_feedback", "description": "Record a human correction or review finding into the Urban Hermes memory store.", "parameters": {"type": "object", "properties": {"summary": {"type": "string"}, "triggers": {"type": "array", "items": {"type": "string"}}, "place": {"type": "string"}, "correction": {"type": "string"}, "session_id": {"type": "string"}}, "required": ["summary"]}}
RESEARCH_MEMORY_SCHEMA = {
    "name": "urban_research_memory",
    "description": "Search, list, or record reusable urban research-design lessons such as spatial-unit choice, AOI/context-buffer conventions, and X/Y variable alignment.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["search", "record", "list"], "default": "search"},
            "query": {"type": "string"},
            "task": {"type": "string"},
            "summary": {"type": "string"},
            "method_hint": {"type": "string"},
            "domain": {"type": "string"},
            "triggers": {"type": "array", "items": {"type": "string"}},
            "caveats": {"type": "array", "items": {"type": "string"}},
            "limit": {"type": "integer", "default": 5},
            "session_id": {"type": "string"},
        },
        "required": [],
    },
}
HOST_FS_SCHEMA = {
    "name": "urban_host_fs",
    "description": "Use native host Python to inspect Windows/host files and folders, including D:/... paths. Prefer this over generic read_file/search_files/terminal on Windows so paths do not go through Git Bash or WSL.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["stat", "exists", "list", "glob", "read_text", "read_json", "json_summary", "geojson_summary"],
                "default": "stat",
            },
            "path": {"type": "string", "description": "Native host path such as D:/data/file.geojson or C:/Users/..."},
            "pattern": {"type": "string", "description": "Glob pattern used when action=glob, relative to path when path is a directory."},
            "encoding": {"type": "string", "description": "Optional text encoding override."},
            "limit": {"type": "integer", "default": 100},
            "max_chars": {"type": "integer", "default": 20000},
            "max_bytes": {"type": "integer", "default": 25000000},
        },
        "required": [],
    },
}
HOST_PYTHON_SCHEMA = {
    "name": "urban_host_python",
    "description": "Run a Python script with native host paths and shell=False. Use this for Windows-local data preparation or artifact checks when generic terminal would enter Git Bash/WSL. Use urban_qgis_process for QGIS Processing algorithms.",
    "parameters": {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Python code to run. The adapter writes it to a native temporary/script file before execution."},
            "script_path": {"type": "string", "description": "Optional existing Python script path to run instead of inline code."},
            "python": {"type": "string", "description": "Optional Python executable. Defaults to the interpreter running Hermes-Urban."},
            "workdir": {"type": "string", "description": "Native host working directory."},
            "output_dir": {"type": "string", "description": "Optional directory where the generated script is preserved for provenance."},
            "argv": {"type": "array", "items": {"type": "string"}},
            "env": {"type": "object"},
            "timeout": {"type": "integer", "default": 300},
            "keep_script": {"type": "boolean", "default": False},
        },
        "required": [],
    },
}
QGIS_WORKSPACE_SCHEMA = {
    "name": "urban_qgis_workspace",
    "description": "Package completed GIS analysis outputs into a QGIS workspace: source/derived layers, .qgz/.qgs project, visual styles, README, and spatial_reasoning_manifest.json for later agent reasoning. Use this after generating GIS layers instead of leaving only loose GeoJSON/CSV files.",
    "parameters": {
        "type": "object",
        "properties": {
            "workspace_type": {
                "type": "string",
                "enum": ["case1_nanjing_200m", "custom"],
                "default": "case1_nanjing_200m",
                "description": "Known reusable workspace packager. For custom tasks, pass packager_script.",
            },
            "run_dir": {"type": "string", "description": "Experiment run directory containing outputs/ and receiving qgis_workspace/."},
            "packager_script": {"type": "string", "description": "Optional task-specific Python packager authored during the run."},
            "qgis_python": {"type": "string", "description": "Optional QGIS Python .bat/.exe path for writing .qgz/.qgs projects."},
            "timeout": {"type": "integer", "default": 600},
        },
        "required": ["run_dir"],
    },
}
QGIS_PROCESS_SCHEMA = {
    "name": "urban_qgis_process",
    "description": "Run a QGIS Processing algorithm with qgis_process and return command logs plus output verification. Use this for real GIS intermediate artifacts instead of merely drafting scripts.",
    "parameters": {
        "type": "object",
        "properties": {
            "algorithm": {"type": "string", "description": "QGIS algorithm id, e.g. native:fixgeometries or native:lineintersections."},
            "parameters": {"type": "object", "description": "QGIS PARAMETER=VALUE map, including OUTPUT paths."},
            "qgis_process": {"type": "string", "description": "Optional explicit qgis_process executable or .bat path."},
            "output_dir": {"type": "string", "description": "Optional directory for qgis_process_log.jsonl."},
            "log_path": {"type": "string", "description": "Optional explicit JSONL command log path."},
            "workdir": {"type": "string"},
            "timeout": {"type": "integer", "default": 300},
            "verbose": {"type": "boolean", "default": False},
        },
        "required": ["algorithm", "parameters"],
    },
}
