#!/usr/bin/env python
"""Smoke-test the GIS backend protocol through the Urban-Hermes tool registry."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any


PAPER4_ROOT = Path(__file__).resolve().parents[1]
HERMES_ADAPTER = PAPER4_ROOT / "hermes_urban_agent"
for path in (HERMES_ADAPTER, PAPER4_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def _dispatch(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    from tools.registry import registry

    raw = registry.dispatch(tool_name, args)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{tool_name} returned non-JSON: {raw[:500]}") from exc
    return payload


def _write_geojson(path: Path, features: list[dict[str, Any]], geometry_type: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "type": "FeatureCollection",
        "name": path.stem,
        "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
        "features": features,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_fixture(run_dir: Path) -> Path:
    if run_dir.exists():
        shutil.rmtree(run_dir)
    data_dir = run_dir / "input_layers"
    data_dir.mkdir(parents=True, exist_ok=True)

    grid_features = []
    base_x, base_y = 121.480, 31.225
    cell = 0.002
    values = [0.25, 0.55, 0.72, 0.41]
    for idx, value in enumerate(values):
        col = idx % 2
        row = idx // 2
        x0 = base_x + col * cell
        y0 = base_y + row * cell
        x1 = x0 + cell * 0.85
        y1 = y0 + cell * 0.85
        grid_features.append(
            {
                "type": "Feature",
                "properties": {"cell_id": idx + 1, "vitality_score": value, "building_coverage_ratio": round(value * 0.6, 3)},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]],
                },
            }
        )
    _write_geojson(data_dir / "grid_metrics.geojson", grid_features, "Polygon")

    road_features = [
        {
            "type": "Feature",
            "properties": {"road_id": "r1", "road_density_m_per_ha": 120.0},
            "geometry": {"type": "LineString", "coordinates": [[base_x, base_y], [base_x + cell * 2, base_y + cell * 1.8]]},
        },
        {
            "type": "Feature",
            "properties": {"road_id": "r2", "road_density_m_per_ha": 85.0},
            "geometry": {"type": "LineString", "coordinates": [[base_x, base_y + cell], [base_x + cell * 1.8, base_y]]},
        },
    ]
    _write_geojson(data_dir / "road_edges.geojson", road_features, "LineString")

    node_features = [
        {
            "type": "Feature",
            "properties": {"node_id": "n1", "accessibility_score": 0.9},
            "geometry": {"type": "Point", "coordinates": [base_x + cell * 0.2, base_y + cell * 0.2]},
        },
        {
            "type": "Feature",
            "properties": {"node_id": "n2", "accessibility_score": 0.4},
            "geometry": {"type": "Point", "coordinates": [base_x + cell * 1.6, base_y + cell * 1.2]},
        },
    ]
    _write_geojson(data_dir / "road_nodes.geojson", node_features, "Point")

    manifest = {
        "manifest_version": "gis-backend-v1",
        "task_id": "gis_protocol_smoke_no_aoi",
        "case_id": "smoke_20260519",
        "coordinate_reference_system": "EPSG:4326",
        "spatial_scope": {
            "scope_kind": "layer_derived_or_task_defined",
            "description": "Smoke fixture intentionally has no authoritative AOI; map extent is derived from declared layers.",
            "crs": "EPSG:4326",
        },
        "layers": [
            {
                "id": "grid_metrics",
                "name": "grid_metrics",
                "role": "metric_layer",
                "path": str(data_dir / "grid_metrics.geojson"),
                "type": "vector",
                "geometry_type": "Polygon",
                "metric_fields": ["vitality_score", "building_coverage_ratio"],
                "renderer": {"type": "graduated", "field": "vitality_score"},
            },
            {
                "id": "road_edges",
                "name": "road_edges",
                "role": "context_or_source_layer",
                "path": str(data_dir / "road_edges.geojson"),
                "type": "vector",
                "geometry_type": "LineString",
                "metric_fields": ["road_density_m_per_ha"],
            },
            {
                "id": "road_nodes",
                "name": "road_nodes",
                "role": "metric_layer",
                "path": str(data_dir / "road_nodes.geojson"),
                "type": "vector",
                "geometry_type": "Point",
                "metric_fields": ["accessibility_score"],
                "renderer": {"type": "graduated", "field": "accessibility_score"},
            },
        ],
        "known_limits": ["Synthetic smoke fixture for protocol validation, not a substantive urban finding."],
    }
    manifest_path = run_dir / "spatial_reasoning_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a GIS backend protocol smoke test through Urban-Hermes.")
    parser.add_argument("--run-dir", default=str(PAPER4_ROOT / "experiments" / "gis_backend_protocol_smoke_20260519"))
    parser.add_argument("--backend", default="qgis_desktop", choices=["qgis_desktop", "arcgis_pro"])
    parser.add_argument("--qgis-python", default=None)
    parser.add_argument("--arcgis-python", default=None)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    from urban_hermes.bootstrap import bootstrap

    bootstrap()
    run_dir = Path(args.run_dir)
    manifest_path = build_fixture(run_dir)
    tool_args = {
        "backend": args.backend,
        "mode": "package_and_validate",
        "run_dir": str(run_dir),
        "artifact_manifest": str(manifest_path),
        "qgis_python": args.qgis_python,
        "arcgis_python": args.arcgis_python,
        "timeout": args.timeout,
    }
    payload = _dispatch("urban_gis_workspace", tool_args)
    result_path = run_dir / "urban_hermes_gis_dispatch_result.json"
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"run_dir": str(run_dir), "manifest": str(manifest_path), "dispatch_result": str(result_path), "payload": payload}, ensure_ascii=False, indent=2, default=str))
    if not payload.get("success"):
        sys.exit(1)


if __name__ == "__main__":
    main()