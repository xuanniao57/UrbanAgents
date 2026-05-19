#!/usr/bin/env python
"""Validate a protocol-driven ArcGIS Pro workspace with ArcPy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import arcpy


def _load_manifest(workspace_dir: Path) -> tuple[Path | None, dict[str, Any]]:
    candidates = [
        workspace_dir / "manifests" / "spatial_reasoning_manifest.json",
        workspace_dir / "spatial_reasoning_manifest.json",
        workspace_dir.parent / "spatial_reasoning_manifest.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate, json.loads(candidate.read_text(encoding="utf-8-sig"))
    return None, {}


def _manifest_metric_requirements(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    requirements = {}
    for layer in manifest.get("layers", []):
        name = str(layer.get("name") or layer.get("id") or "")
        renderer = layer.get("renderer") if isinstance(layer.get("renderer"), dict) else {}
        requirements[name] = {
            "metric_fields": list(layer.get("metric_fields") or []),
            "renderer_field": renderer.get("field") or layer.get("renderer_field"),
        }
    return requirements


def _feature_class_records(gdb_path: Path, requirements: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records = []
    missing_metric_fields = []
    if not gdb_path.exists():
        return records, missing_metric_fields
    old_workspace = arcpy.env.workspace
    arcpy.env.workspace = str(gdb_path)
    try:
        names = arcpy.ListFeatureClasses() or []
        for name in names:
            path = str(gdb_path / name)
            fields = [field.name for field in arcpy.ListFields(path)]
            count = int(arcpy.management.GetCount(path)[0])
            spatial_reference = arcpy.Describe(path).spatialReference.name if hasattr(arcpy.Describe(path), "spatialReference") else None
            req = requirements.get(name) or requirements.get(name.lower()) or {}
            for metric_field in req.get("metric_fields") or []:
                if metric_field not in fields:
                    missing_metric_fields.append({"layer_name": name, "field": metric_field})
            records.append({"layer_name": name, "feature_class": path, "feature_count": count, "fields": fields, "spatial_reference": spatial_reference})
    finally:
        arcpy.env.workspace = old_workspace
    return records, missing_metric_fields


def _project_records(aprx_path: Path | None) -> tuple[bool | None, list[dict[str, Any]], list[dict[str, Any]]]:
    if not aprx_path or not aprx_path.exists():
        return None, [], []
    aprx = arcpy.mp.ArcGISProject(str(aprx_path))
    layers = []
    broken_layers = []
    for map_obj in aprx.listMaps():
        for layer in map_obj.listLayers():
            record = {"map_name": map_obj.name, "layer_name": layer.name, "is_broken": bool(layer.isBroken)}
            if hasattr(layer, "dataSource"):
                try:
                    record["data_source"] = layer.dataSource
                except Exception:
                    record["data_source"] = None
            if layer.isBroken:
                broken_layers.append(record)
            layers.append(record)
    return True, layers, broken_layers


def _manifest_consistency(manifest_path: Path | None, manifest: dict[str, Any]) -> dict[str, Any]:
    if not manifest_path:
        return {"ok": False, "missing_paths": [], "schema_errors": ["manifest not found"]}
    missing_paths = []
    for layer in manifest.get("layers", []):
        path = layer.get("path")
        if path and not str(path).startswith(("http://", "https://", "type=xyz")) and not Path(path).exists():
            missing_paths.append(str(path))
    workspace = (manifest.get("backend_workspaces") or {}).get("arcgis_pro") or {}
    gdb = workspace.get("gdb_path")
    if gdb and not Path(gdb).exists():
        missing_paths.append(str(gdb))
    return {"ok": not missing_paths, "missing_paths": missing_paths, "schema_errors": []}


def validate_workspace(workspace_dir: Path) -> dict[str, Any]:
    manifest_path, manifest = _load_manifest(workspace_dir)
    workspace = (manifest.get("backend_workspaces") or {}).get("arcgis_pro") or {}
    gdb_path = Path(workspace.get("gdb_path") or workspace_dir / "data" / "protocol_arcgis_workspace.gdb")
    declared_project = workspace.get("project_path")
    aprx_path = Path(declared_project) if declared_project and Path(declared_project).exists() else None
    requirements = _manifest_metric_requirements(manifest)
    feature_classes, missing_metric_fields = _feature_class_records(gdb_path, requirements)
    project_read_ok, project_layers, broken_layers = _project_records(aprx_path)
    manifest_check = _manifest_consistency(manifest_path, manifest)
    exported_maps = []
    for item in manifest.get("maps", []):
        path = item.get("path")
        if path:
            exported_maps.append({"path": path, "exists": Path(path).exists(), "type": item.get("type")})

    blocking_errors = []
    warnings = []
    if not gdb_path.exists():
        blocking_errors.append("file geodatabase missing")
    if not feature_classes:
        blocking_errors.append("no feature classes were validated")
    if missing_metric_fields:
        blocking_errors.append("declared metric fields missing from ArcGIS feature classes")
    if broken_layers:
        blocking_errors.append("broken ArcGIS Pro project layers found")
    if not manifest_check.get("ok"):
        blocking_errors.append("manifest consistency failed")
    if project_read_ok is None:
        warnings.append("no .aprx project was validated; automatic Blank.aprx discovery failed or template_aprx was unavailable")

    return {
        "backend": "arcgis_pro",
        "runtime": {"available": True, "executable": "arcgis_python", "install_info": arcpy.GetInstallInfo()},
        "workspace_dir": str(workspace_dir),
        "manifest_path": str(manifest_path) if manifest_path else None,
        "gdb_path": str(gdb_path),
        "gdb_exists": gdb_path.exists(),
        "project_path": str(aprx_path) if aprx_path else None,
        "project_read_ok": project_read_ok,
        "layer_count": len(feature_classes),
        "layers": feature_classes,
        "project_layers": project_layers,
        "broken_layers": broken_layers,
        "missing_datasources": [],
        "invalid_layers": broken_layers,
        "missing_metric_fields": missing_metric_fields,
        "renderer_checks": [],
        "exported_maps": exported_maps,
        "manifest_consistency": manifest_check,
        "known_limits": list(manifest.get("known_limits") or []),
        "needs_correction": bool(blocking_errors),
        "blocking_errors": blocking_errors,
        "warnings": warnings,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a protocol-driven ArcGIS Pro workspace.")
    parser.add_argument("workspace_dir", type=Path)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    result = validate_workspace(args.workspace_dir)
    output = args.output or args.workspace_dir / "manifests" / "arcgis_validation_report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()