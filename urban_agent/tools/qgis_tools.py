"""QGIS integration tools for UrbanAgent."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional


def render_with_qgis(
    gpkg_path: str,
    output_dir: str,
    legend: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate a QGIS Desktop project using the validated QGIS API path."""
    from .qgis_project_gen import generate_qgs_project

    return generate_qgs_project(
        gpkg_path=str(gpkg_path),
        output_dir=str(output_dir),
        legend=legend or {},
        launch_qgis=False,
    )


def build_gis_artifact_bundle_with_qgis(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Capability entry point: build GIS artifact bundle AND render with QGIS."""
    from .geo_tools import build_gis_artifact_bundle as build_gis_bundle

    # First run the standard GeoPandas bundle (GPKG + chart + grid)
    result = build_gis_bundle(arguments)

    gpkg_path = None
    for artifact in result.get("artifacts", []):
        if artifact.get("type") == "gis_layer_package":
            gpkg_path = artifact["path"]
            break

    if not gpkg_path:
        # Try auto-find
        artifact_dir = arguments.get("artifact_dir") or arguments.get("output_dir", "artifacts")
        candidate = Path(artifact_dir) / "urbanagent_gis_layers.gpkg"
        if candidate.exists():
            gpkg_path = str(candidate)

    if gpkg_path:
        qgis_result = render_with_qgis(
            gpkg_path=gpkg_path,
            output_dir=str(Path(gpkg_path).parent),
            legend=arguments.get("legend"),
        )
        result["qgis_render"] = qgis_result
        for qa in qgis_result.get("artifacts", []):
            if not any(a.get("path") == qa.get("path") for a in result.get("artifacts", [])):
                result["artifacts"].append(qa)

    return result


def launch_qgis_project(gpkg_path: str, output_dir: str, legend: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Generate QGIS project and launch QGIS GUI (if available)."""
    from .qgis_project_gen import generate_qgs_project

    return generate_qgs_project(
        gpkg_path=str(gpkg_path),
        output_dir=str(output_dir),
        legend=legend or {},
        launch_qgis=True,
    )
