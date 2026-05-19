"""Manifest loading and normalization helpers for GIS backend adapters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path: str | Path, payload: dict[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return target


def resolve_manifest_path(run_dir: str | Path, explicit: str | Path | None = None) -> Path:
    if explicit:
        path = Path(explicit)
        if path.exists():
            return path
    base = Path(run_dir)
    candidates = [
        base / "spatial_reasoning_manifest.json",
        base / "manifests" / "spatial_reasoning_manifest.json",
        base / "qgis_workspace" / "manifests" / "spatial_reasoning_manifest.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"spatial_reasoning_manifest.json not found under {base}")


def normalize_manifest(manifest: dict[str, Any], *, run_dir: str | Path | None = None) -> dict[str, Any]:
    normalized = dict(manifest)
    normalized.setdefault("manifest_version", "gis-backend-v1")
    normalized.setdefault("task_id", normalized.get("project_name") or normalized.get("case_id") or "urban_gis_task")
    normalized.setdefault("case_id", normalized.get("project_name") or normalized.get("task_id") or "urban_gis_case")
    normalized.setdefault("coordinate_reference_system", normalized.get("crs") or "EPSG:4326")
    normalized["spatial_scope"] = _normalize_spatial_scope(normalized)
    normalized["layers"] = _normalize_layers(normalized.get("layers", []), run_dir=run_dir)
    normalized.setdefault("tables", [])
    normalized.setdefault("maps", [])
    normalized.setdefault("known_limits", normalized.get("limitations") or [])
    return normalized


def _normalize_spatial_scope(manifest: dict[str, Any]) -> dict[str, Any]:
    scope = dict(manifest.get("spatial_scope") or {})
    scope.setdefault("crs", manifest.get("coordinate_reference_system") or manifest.get("crs") or "EPSG:4326")
    if "aoi" in manifest and "study_area" not in scope:
        scope["study_area"] = manifest["aoi"]
    if scope.get("study_area"):
        scope.setdefault("scope_kind", "explicit_study_area")
    else:
        scope.setdefault("scope_kind", "layer_derived_or_task_defined")
        scope.setdefault("description", "No authoritative AOI is required by the protocol; backend uses declared layer extents or task-specific scope metadata.")
    return scope


def _normalize_layers(raw_layers: Any, *, run_dir: str | Path | None) -> list[dict[str, Any]]:
    if isinstance(raw_layers, dict):
        layer_items = []
        for layer_id, layer in raw_layers.items():
            if isinstance(layer, dict):
                item = dict(layer)
            else:
                item = {"path": str(layer)}
            item.setdefault("id", str(layer_id))
            item.setdefault("name", str(layer_id))
            layer_items.append(item)
    elif isinstance(raw_layers, list):
        layer_items = [dict(layer) for layer in raw_layers if isinstance(layer, dict)]
    else:
        layer_items = []

    normalized = []
    for index, layer in enumerate(layer_items):
        layer_id = str(layer.get("id") or layer.get("name") or f"layer_{index + 1}")
        layer.setdefault("id", layer_id)
        layer.setdefault("name", layer.get("label") or layer_id)
        layer.setdefault("role", _infer_role(layer))
        layer.setdefault("type", "vector")
        if "metric_fields" not in layer:
            metrics = layer.get("metrics") or layer.get("metric") or []
            if isinstance(metrics, str):
                metrics = [metrics]
            layer["metric_fields"] = list(metrics) if isinstance(metrics, list) else []
        renderer = layer.get("renderer") if isinstance(layer.get("renderer"), dict) else {}
        renderer_field = layer.get("renderer_field") or layer.get("classAttribute") or renderer.get("field")
        if renderer_field:
            layer["renderer"] = {"type": renderer.get("type") or "graduated", "field": renderer_field}
            if renderer_field not in layer["metric_fields"]:
                layer["metric_fields"].append(renderer_field)
        if layer.get("path"):
            layer["path"] = _resolve_layer_path(str(layer["path"]), run_dir=run_dir)
        normalized.append(layer)
    return normalized


def _infer_role(layer: dict[str, Any]) -> str:
    if layer.get("metric_fields") or layer.get("metrics") or layer.get("renderer_field"):
        return "metric_layer"
    name = str(layer.get("id") or layer.get("name") or "").lower()
    if "aoi" in name or "boundary" in name or "scope" in name:
        return "scope_layer"
    return "context_or_source_layer"


def _resolve_layer_path(path_text: str, *, run_dir: str | Path | None) -> str:
    if path_text.startswith(("http://", "https://", "type=xyz")):
        return path_text
    path = Path(path_text)
    if not path.is_absolute() and run_dir:
        path = Path(run_dir) / path
    return str(path)