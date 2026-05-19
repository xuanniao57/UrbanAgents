#!/usr/bin/env python
"""Validate a protocol-driven QGIS Desktop workspace.

This file must be executed with QGIS Python, not a regular conda Python.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from qgis.core import QgsApplication, QgsGraduatedSymbolRenderer, QgsProject, QgsVectorLayer


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


def _source_file_exists(source: str) -> bool:
    if source.startswith(("type=xyz", "http://", "https://")):
        return True
    candidate = source.split("|")[0]
    if not candidate:
        return True
    return Path(candidate).exists()


def _project_paths(workspace_dir: Path, manifest: dict[str, Any]) -> list[Path]:
    declared = ((manifest.get("backend_workspaces") or {}).get("qgis_desktop") or {}).get("project_path")
    paths = []
    if declared:
        paths.append(Path(declared))
    project_dir = workspace_dir / "project"
    paths.extend(sorted(project_dir.glob("*.qgs")))
    paths.extend(sorted(project_dir.glob("*.qgz")))
    deduped = []
    seen = set()
    for path in paths:
        key = str(path)
        if key not in seen:
            seen.add(key)
            deduped.append(path)
    return deduped


def _manifest_metric_requirements(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    requirements = {}
    for layer in manifest.get("layers", []):
        name = str(layer.get("name") or layer.get("id") or "")
        renderer = layer.get("renderer") if isinstance(layer.get("renderer"), dict) else {}
        requirements[name] = {
            "metric_fields": list(layer.get("metric_fields") or []),
            "renderer_field": renderer.get("field") or layer.get("renderer_field"),
            "path": layer.get("path"),
        }
    return requirements


def _read_project(project_path: Path, requirements: dict[str, dict[str, Any]]) -> dict[str, Any]:
    project = QgsProject.instance()
    project.clear()
    read_ok = bool(project.read(str(project_path)))
    layers = list(project.mapLayers().values()) if read_ok else []
    layer_records = []
    invalid_layers = []
    missing_datasources = []
    missing_metric_fields = []
    renderer_checks = []

    for layer in layers:
        renderer = layer.renderer() if hasattr(layer, "renderer") else None
        renderer_type = renderer.__class__.__name__ if renderer else None
        class_attribute = renderer.classAttribute() if hasattr(renderer, "classAttribute") else None
        source = layer.source() if hasattr(layer, "source") else ""
        fields = [field.name() for field in layer.fields()] if isinstance(layer, QgsVectorLayer) else []
        requirement = requirements.get(layer.name(), {})

        if not layer.isValid():
            invalid_layers.append({"layer_name": layer.name(), "source": source})
        if isinstance(layer, QgsVectorLayer) and source and not _source_file_exists(source):
            missing_datasources.append({"layer_name": layer.name(), "source": source})

        for metric_field in requirement.get("metric_fields") or []:
            if metric_field not in fields:
                missing_metric_fields.append({"layer_name": layer.name(), "field": metric_field})
        expected_renderer = requirement.get("renderer_field")
        if expected_renderer:
            renderer_checks.append(
                {
                    "layer_name": layer.name(),
                    "expected_field": expected_renderer,
                    "actual_field": class_attribute,
                    "renderer_type": renderer_type,
                    "ok": class_attribute == expected_renderer and isinstance(renderer, QgsGraduatedSymbolRenderer),
                }
            )

        layer_records.append(
            {
                "layer_name": layer.name(),
                "valid": bool(layer.isValid()),
                "source": source,
                "fields": fields,
                "renderer_type": renderer_type,
                "classAttribute": class_attribute,
                "feature_count": int(layer.featureCount()) if isinstance(layer, QgsVectorLayer) and layer.isValid() else None,
            }
        )

    return {
        "project_path": str(project_path),
        "exists": project_path.exists(),
        "read_ok": read_ok,
        "layer_count": len(layers),
        "layers": layer_records,
        "invalid_layers": invalid_layers,
        "missing_datasources": missing_datasources,
        "missing_metric_fields": missing_metric_fields,
        "renderer_checks": renderer_checks,
    }


def _manifest_consistency(manifest_path: Path | None, manifest: dict[str, Any]) -> dict[str, Any]:
    missing_paths = []
    if not manifest_path:
        return {"ok": False, "missing_paths": [], "schema_errors": ["manifest not found"]}
    for layer in manifest.get("layers", []):
        path = layer.get("path")
        if path and not str(path).startswith(("http://", "https://", "type=xyz")) and not Path(path).exists():
            missing_paths.append(str(path))
    for item in manifest.get("maps", []):
        path = item.get("path")
        if path and not Path(path).exists():
            missing_paths.append(str(path))
    return {"ok": not missing_paths, "missing_paths": missing_paths, "schema_errors": []}


def validate_workspace(workspace_dir: Path) -> dict[str, Any]:
    manifest_path, manifest = _load_manifest(workspace_dir)
    requirements = _manifest_metric_requirements(manifest)
    project_results = [_read_project(path, requirements) for path in _project_paths(workspace_dir, manifest)]
    invalid_layers = [item for result in project_results for item in result.get("invalid_layers", [])]
    missing_datasources = [item for result in project_results for item in result.get("missing_datasources", [])]
    missing_metric_fields = [item for result in project_results for item in result.get("missing_metric_fields", [])]
    renderer_checks = [item for result in project_results for item in result.get("renderer_checks", [])]
    bad_renderer_checks = [item for item in renderer_checks if not item.get("ok")]
    manifest_check = _manifest_consistency(manifest_path, manifest)
    preview_path = ((manifest.get("backend_workspaces") or {}).get("qgis_desktop") or {}).get("preview_path")
    exported_maps = []
    if preview_path:
        exported_maps.append({"path": preview_path, "exists": Path(preview_path).exists(), "type": "png"})

    blocking_errors = []
    if not project_results:
        blocking_errors.append("no QGIS project found")
    if any(not result.get("read_ok") for result in project_results):
        blocking_errors.append("one or more QGIS projects failed to read")
    if invalid_layers:
        blocking_errors.append("invalid QGIS layers found")
    if missing_datasources:
        blocking_errors.append("missing layer datasources found")
    if missing_metric_fields:
        blocking_errors.append("declared metric fields missing from QGIS layers")
    if bad_renderer_checks:
        blocking_errors.append("renderer field checks failed")
    if not manifest_check.get("ok"):
        blocking_errors.append("manifest consistency failed")

    return {
        "backend": "qgis_desktop",
        "runtime": {"available": True, "executable": "qgis_python"},
        "workspace_dir": str(workspace_dir),
        "manifest_path": str(manifest_path) if manifest_path else None,
        "project_read_ok": bool(project_results) and all(result.get("read_ok") for result in project_results),
        "layer_count": sum(result.get("layer_count", 0) for result in project_results),
        "project_results": project_results,
        "layers": [layer for result in project_results for layer in result.get("layers", [])],
        "missing_datasources": missing_datasources,
        "invalid_layers": invalid_layers,
        "missing_metric_fields": missing_metric_fields,
        "renderer_checks": renderer_checks,
        "exported_maps": exported_maps,
        "manifest_consistency": manifest_check,
        "known_limits": list(manifest.get("known_limits") or []),
        "needs_correction": bool(blocking_errors),
        "blocking_errors": blocking_errors,
        "warnings": [],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a protocol-driven QGIS workspace.")
    parser.add_argument("workspace_dir", type=Path)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    qgs = QgsApplication([], False)
    qgs.initQgis()
    try:
        result = validate_workspace(args.workspace_dir)
    finally:
        qgs.exitQgis()

    output = args.output or args.workspace_dir / "manifests" / "qgis_validation_report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()