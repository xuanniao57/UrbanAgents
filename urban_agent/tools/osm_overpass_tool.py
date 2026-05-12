from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable

try:
    import geopandas as gpd
    import osmnx as ox
    from shapely.geometry import box

    HAS_OSM_STACK = True
except ImportError:  # pragma: no cover
    gpd = None
    ox = None
    box = None
    HAS_OSM_STACK = False


def fetch_osm_overpass(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch OSM roads/buildings for an AOI or AOI-centered context buffer.

    This is intentionally a small, generic tool: it knows how to retrieve OSM
    layers and write provenance metadata, but it does not encode any case-study
    decision about which AOI is authoritative.
    """

    if not HAS_OSM_STACK:
        return {
            "status": "unavailable",
            "reason": "geopandas/osmnx are not installed",
        }

    aoi_path = arguments.get("aoi_path") or arguments.get("boundary_path")
    if not aoi_path:
        return {"status": "failed", "reason": "missing aoi_path"}

    output_dir = Path(arguments.get("output_dir") or "artifacts/osm_overpass")
    output_dir.mkdir(parents=True, exist_ok=True)

    layers = set(_as_list(arguments.get("layers") or ["roads", "buildings"]))
    width_factor = float(arguments.get("context_width_factor", arguments.get("width_factor", 1.0)))
    height_factor = float(arguments.get("context_height_factor", arguments.get("height_factor", 1.0)))
    network_type = str(arguments.get("network_type") or "all")
    endpoints = _as_list(arguments.get("overpass_endpoints"))
    if endpoints:
        ox.settings.overpass_endpoint = str(endpoints[0])
    timeout = arguments.get("timeout")
    if timeout:
        ox.settings.requests_timeout = int(timeout)

    aoi = gpd.read_file(aoi_path)
    query = _context_polygon(aoi, width_factor=width_factor, height_factor=height_factor)
    query_wgs84 = query.to_crs("EPSG:4326")
    polygon = query_wgs84.unary_union

    outputs: Dict[str, str] = {}
    counts: Dict[str, int] = {}
    errors: Dict[str, str] = {}

    if "roads" in layers:
        try:
            graph = ox.graph_from_polygon(
                polygon,
                network_type=network_type,
                simplify=True,
                retain_all=True,
                truncate_by_edge=False,
            )
            _, roads = ox.graph_to_gdfs(graph, nodes=True, edges=True)
            roads = roads.reset_index(drop=True)
            roads_out = output_dir / "osm_roads_context.geojson"
            roads.to_file(roads_out, driver="GeoJSON")
            outputs["roads"] = str(roads_out)
            counts["roads"] = int(len(roads))
        except Exception as error:  # pragma: no cover - network dependent
            errors["roads"] = str(error)

    if "buildings" in layers:
        try:
            buildings = ox.features_from_polygon(polygon, tags={"building": True})
            geom_type = buildings.geometry.geom_type
            buildings = buildings[geom_type.isin(["Polygon", "MultiPolygon"])].copy()
            buildings = buildings.reset_index(drop=True)
            buildings_out = output_dir / "osm_buildings_context.geojson"
            buildings.to_file(buildings_out, driver="GeoJSON")
            outputs["buildings"] = str(buildings_out)
            counts["buildings"] = int(len(buildings))
        except Exception as error:  # pragma: no cover - network dependent
            errors["buildings"] = str(error)

    extent_out = output_dir / "source_extent.geojson"
    query_wgs84.to_file(extent_out, driver="GeoJSON")
    outputs["source_extent"] = str(extent_out)

    metadata = {
        "status": "completed" if outputs.keys() - {"source_extent"} else "failed",
        "tool": "fetch_osm_overpass",
        "aoi_path": str(aoi_path),
        "output_dir": str(output_dir),
        "layers_requested": sorted(layers),
        "network_type": network_type,
        "context_width_factor": width_factor,
        "context_height_factor": height_factor,
        "acquired_at": datetime.now().isoformat(timespec="seconds"),
        "provider": "OpenStreetMap via Overpass API / OSMnx",
        "outputs": outputs,
        "feature_counts": counts,
        "errors": errors,
    }
    metadata_out = output_dir / "overpass_metadata.json"
    metadata_out.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    outputs["metadata"] = str(metadata_out)
    metadata["outputs"] = outputs
    return metadata


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _context_polygon(aoi: Any, *, width_factor: float, height_factor: float) -> Any:
    source = aoi
    if source.crs is None:
        source = source.set_crs("EPSG:4326")
    try:
        metric_crs = source.estimate_utm_crs()
    except Exception:
        metric_crs = "EPSG:3857"
    metric = source.to_crs(metric_crs)
    minx, miny, maxx, maxy = metric.total_bounds
    width = max(maxx - minx, 1.0)
    height = max(maxy - miny, 1.0)
    cx = (minx + maxx) / 2.0
    cy = (miny + maxy) / 2.0
    context = gpd.GeoDataFrame(
        {"role": ["osm_query_context"], "width_factor": [width_factor], "height_factor": [height_factor]},
        geometry=[box(cx - width * width_factor / 2.0, cy - height * height_factor / 2.0, cx + width * width_factor / 2.0, cy + height * height_factor / 2.0)],
        crs=metric_crs,
    )
    return context
