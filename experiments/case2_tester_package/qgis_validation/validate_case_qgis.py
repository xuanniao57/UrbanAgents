#!/usr/bin/env python
"""Independent QGIS validator — must be run with QGIS Python, not conda Python.

Usage:
    & 'C:\Program Files\QGIS 3.40.11\bin\python-qgis-ltr.bat' validate_case_qgis.py <CASE_DIR> [--output <OUTPUT_JSON>]

Checks:
    - .qgs/.qgz project readability
    - invalid layers
    - missing datasources
    - renderer field bindings (graduated symbol renderers)
    - basemap layer ordering
    - metric CSV file row counts
    - manifest consistency
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from qgis.core import QgsApplication, QgsGraduatedSymbolRenderer, QgsProject, QgsVectorLayer


CORE_RENDERER_FIELDS = {
    "building_coverage_ratio",
    "road_density_m_per_ha",
    "heritage_proxy_score",
    "accessibility_score",
}


def _source_file_exists(source: str) -> bool:
    if source.startswith("type=xyz") or source.startswith("http"):
        return True
    candidate = source.split("|")[0]
    if not candidate:
        return True
    return Path(candidate).exists()


def _project_layers(project_path: Path) -> dict:
    project = QgsProject.instance()
    project.clear()
    read_ok = project.read(str(project_path))
    layers = list(project.mapLayers().values()) if read_ok else []
    tree_layers = project.layerTreeRoot().findLayers() if read_ok else []

    layer_records = []
    invalid_layers = []
    missing_datasources = []
    renderer_bound_fields = []
    graduated_metric_layers = []

    for layer in layers:
        renderer = layer.renderer() if hasattr(layer, "renderer") else None
        renderer_type = renderer.__class__.__name__ if renderer else None
        class_attribute = renderer.classAttribute() if hasattr(renderer, "classAttribute") else None
        source = layer.source() if hasattr(layer, "source") else ""

        if class_attribute:
            renderer_bound_fields.append(class_attribute)
        if isinstance(renderer, QgsGraduatedSymbolRenderer):
            graduated_metric_layers.append(
                {"layer_name": layer.name(), "field": class_attribute, "renderer_type": renderer_type}
            )
        if not layer.isValid():
            invalid_layers.append({"layer_name": layer.name(), "source": source})
        if isinstance(layer, QgsVectorLayer) and source and not _source_file_exists(source):
            missing_datasources.append({"layer_name": layer.name(), "source": source})

        layer_records.append(
            {
                "layer_name": layer.name(),
                "valid": layer.isValid(),
                "source": source,
                "renderer_type": renderer_type,
                "classAttribute": class_attribute,
                "fields": [field.name() for field in layer.fields()] if isinstance(layer, QgsVectorLayer) else [],
            }
        )

    tree_order = [tree_layer.layer().name() for tree_layer in tree_layers if tree_layer.layer()]
    basemap_last = bool(tree_order) and any(
        token in tree_order[-1].lower() for token in ["openstreetmap", "osm", "basemap"]
    )

    return {
        "project_path": str(project_path),
        "exists": project_path.exists(),
        "read_ok": read_ok,
        "layer_count": len(layers),
        "layer_tree_order_top_to_bottom": tree_order,
        "basemap_last": basemap_last,
        "invalid_layers": invalid_layers,
        "missing_datasources": missing_datasources,
        "renderer_bound_fields": sorted(set(renderer_bound_fields)),
        "graduated_metric_layers": graduated_metric_layers,
        "layers": layer_records,
    }


def _csv_summaries(case_dir: Path) -> list[dict]:
    summaries = []
    for csv_path in sorted(case_dir.rglob("*.csv")):
        try:
            with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
                reader = csv.DictReader(csv_file)
                row_count = 0
                for row_count, _row in enumerate(reader, start=1):
                    pass
                summaries.append(
                    {"path": str(csv_path), "exists": True, "row_count": row_count, "fields": reader.fieldnames or []}
                )
        except Exception as exc:
            summaries.append({"path": str(csv_path), "exists": csv_path.exists(), "error": str(exc)})
    return summaries


def _manifest_summary(case_dir: Path) -> dict:
    manifest_path = case_dir / "spatial_reasoning_manifest.json"
    alt_path = case_dir / "qgis_workspace" / "manifests" / "spatial_reasoning_manifest.json"
    for path in (manifest_path, alt_path):
        if path.exists():
            manifest_path = path
            break

    summary = {"path": str(manifest_path), "exists": manifest_path.exists(), "missing_paths": []}
    if not manifest_path.exists():
        return summary

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        summary["error"] = str(exc)
        return summary

    layer_count = 0
    metric_layer_count = 0
    for layer in manifest.get("layers", []):
        layer_count += 1
        if layer.get("metric_fields"):
            metric_layer_count += 1
        layer_path = layer.get("path")
        if layer_path and not Path(layer_path).exists():
            summary["missing_paths"].append(layer_path)
    summary["layer_count"] = layer_count
    summary["metric_layer_count"] = metric_layer_count
    summary["known_limits"] = manifest.get("known_limits", [])
    return summary


def validate_case(case_dir: Path) -> dict:
    project_dir = case_dir / "qgis_workspace" / "project"
    if not project_dir.exists():
        project_dir = case_dir / "qgis_workspace"
    project_paths = sorted(project_dir.glob("*.qgs")) + sorted(project_dir.glob("*.qgz"))
    if not project_paths:
        project_paths = sorted(project_dir.rglob("*.qgs")) + sorted(project_dir.rglob("*.qgz"))

    project_results = [_project_layers(project_path) for project_path in project_paths]
    all_renderer_fields = {
        field for project_result in project_results for field in project_result.get("renderer_bound_fields", [])
    }
    missing_core_renderer_fields = sorted(CORE_RENDERER_FIELDS - all_renderer_fields)
    invalid_layers = [item for result in project_results for item in result.get("invalid_layers", [])]
    missing_datasources = [item for result in project_results for item in result.get("missing_datasources", [])]

    csv_summaries = _csv_summaries(case_dir)
    csv_has_rows = any(summary.get("row_count", 0) > 0 for summary in csv_summaries)
    csv_fields = {field for summary in csv_summaries for field in summary.get("fields", [])}

    needs_correction = any(
        [
            not project_results,
            any(not result.get("read_ok") for result in project_results),
            bool(invalid_layers),
            bool(missing_datasources),
            bool(missing_core_renderer_fields),
            not csv_has_rows,
            not CORE_RENDERER_FIELDS.intersection(csv_fields),
        ]
    )

    return {
        "case_dir": str(case_dir),
        "project_results": project_results,
        "qgis_read_ok": bool(project_results) and all(result.get("read_ok") for result in project_results),
        "invalid_layers": invalid_layers,
        "missing_datasources": missing_datasources,
        "renderer_bound_fields": sorted(all_renderer_fields),
        "missing_core_renderer_fields": missing_core_renderer_fields,
        "csv_summaries": csv_summaries,
        "manifest": _manifest_summary(case_dir),
        "needs_correction": needs_correction,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate one Urban-Hermes QGIS case package.")
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    qgs = QgsApplication([], False)
    qgs.initQgis()
    try:
        result = validate_case(args.case_dir)
    finally:
        qgs.exitQgis()

    output_path = args.output or args.case_dir / "artifact_validation_independent.json"
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
