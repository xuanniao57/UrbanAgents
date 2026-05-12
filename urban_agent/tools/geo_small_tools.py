from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .spatial_diagnostics import align_loaded_layers_to_aoi, build_aoi_context_buffer

try:
    import geopandas as gpd
    HAS_GEOPANDAS = True
except ImportError:  # pragma: no cover
    gpd = None
    HAS_GEOPANDAS = False


def discover_urban_data_sources_tool(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Small tool: discover and classify available urban data sources."""
    from .geo_tools import discover_urban_data_sources

    return discover_urban_data_sources(arguments)


def build_aoi_context_buffer_tool(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Small tool: build only the AOI-centered context buffer diagnostics."""
    if not HAS_GEOPANDAS:
        return {"status": "unavailable", "reason": "geopandas is not installed"}
    paths = _paths(arguments)
    boundary_path = paths.get("boundary")
    if not boundary_path:
        return {"status": "unavailable", "reason": "no boundary layer found"}
    boundary = gpd.read_file(boundary_path)
    context, diagnostics = build_aoi_context_buffer(
        boundary,
        width_factor=float(arguments.get("context_buffer_width_factor", 3.0)),
        height_factor=float(arguments.get("context_buffer_height_factor", 3.0)),
    )
    return {
        "status": diagnostics.get("status", "unknown"),
        "context_buffer": context.to_json() if context is not None and len(context) else None,
        "diagnostics": diagnostics,
    }


def validate_source_extent_against_context(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Small tool: compute source-vs-context extent ratios without applying policy thresholds."""
    if not HAS_GEOPANDAS:
        return {"status": "unavailable", "reason": "geopandas is not installed"}
    paths = _paths(arguments)
    loaded: Dict[str, Any] = {}
    for role in ("boundary", "roads", "buildings", "function_buildings", "function_poi", "source_extent", "roads_source_extent", "buildings_source_extent"):
        path_text = paths.get(role)
        if not path_text:
            continue
        try:
            loaded[role] = gpd.read_file(path_text)
        except Exception as error:
            loaded.setdefault("_load_errors", {})[role] = str(error)
    aligned, diagnostics = align_loaded_layers_to_aoi(
        {key: value for key, value in loaded.items() if key != "_load_errors"},
        context_width_factor=float(arguments.get("context_buffer_width_factor", 3.0)),
        context_height_factor=float(arguments.get("context_buffer_height_factor", 3.0)),
    )
    return {
        "status": diagnostics.get("status", "unknown"),
        "alignment_diagnostics": diagnostics,
        "aligned_layer_names": sorted(aligned),
        "load_errors": loaded.get("_load_errors", {}),
    }


def fetch_osm_overpass_tool(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Small tool: fetch OSM roads/buildings for an AOI or context buffer."""
    from .osm_overpass_tool import fetch_osm_overpass

    return fetch_osm_overpass(arguments)


def export_gis_layer_stack(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Small tool facade: export GIS layers after diagnostics and policy-ready metadata are computed."""
    from .geo_tools import build_gis_artifact_bundle

    return build_gis_artifact_bundle(arguments)


def _paths(arguments: Dict[str, Any]) -> Dict[str, str]:
    if isinstance(arguments.get("paths"), dict):
        return {str(key): str(value) for key, value in arguments["paths"].items() if value}
    from .geo_tools import discover_urban_data_sources

    return discover_urban_data_sources(arguments).get("paths", {})

