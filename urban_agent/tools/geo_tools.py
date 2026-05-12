"""
Geospatial Tools
地理空间数据处理工具集
"""

import json
import logging
import math
import re
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
import numpy as np

# 数据处理库
try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

# 地理空间库
try:
    import geopandas as gpd
    from shapely.geometry import Point, Polygon, LineString, box
    from shapely.ops import unary_union
    HAS_GEOPANDAS = True
except ImportError:
    HAS_GEOPANDAS = False
    logging.warning("geopandas未安装，部分功能受限")

try:
    import rasterio
    from rasterio.plot import reshape_as_image
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False
    logging.warning("rasterio未安装，遥感影像处理受限")

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

logger = logging.getLogger(__name__)

from .spatial_diagnostics import align_loaded_layers_to_aoi as _governed_align_loaded_layers_to_aoi

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = Path(__file__).resolve().parents[3]


def resolve_urban_path(value: Any) -> Optional[Path]:
    """Resolve a user-provided urban data path without assuming one workspace root."""
    if not isinstance(value, str):
        return None
    raw = value.strip().strip("'\"`").rstrip("，,。；;：:")
    if not raw:
        return None
    path = Path(raw)
    candidates = [path]
    if not path.is_absolute():
        candidates.extend([Path.cwd() / path, PACKAGE_ROOT / path, WORKSPACE_ROOT / path])
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved.exists():
            return resolved
    return None


def discover_urban_data_sources(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Discover reusable urban data layers from arbitrary task/perception payloads."""
    raw_paths: list[Path] = []
    _collect_existing_paths(payload, raw_paths)

    paths_by_role: Dict[str, str] = {}
    for path in raw_paths:
        role = _classify_urban_path(path)
        if role and role not in paths_by_role:
            paths_by_role[role] = str(path)

    if "streetview_dir" in paths_by_role and "streetview_points" not in paths_by_role:
        points = Path(paths_by_role["streetview_dir"]) / "points_used.csv"
        if points.exists():
            paths_by_role["streetview_points"] = str(points)

    if "function_root" in paths_by_role and "function_counts" not in paths_by_role:
        match = _find_matching_sinobf_dir(Path(paths_by_role["function_root"]), paths_by_role)
        if match:
            paths_by_role.setdefault("function_counts", str(match / "sinobf_function_counts.csv"))
            paths_by_role.setdefault("function_buildings", str(match / "sinobf_buildings.geojson"))
            paths_by_role.setdefault("function_poi", str(match / "sinobf_building_poi.geojson"))

    if "roads" not in paths_by_role or "buildings" not in paths_by_role:
        for raw_path in raw_paths:
            match = _find_matching_osm_cache_dir(raw_path, paths_by_role)
            if not match:
                continue
            roads = match / "osm_roads_aoi.geojson"
            buildings = match / "osm_buildings_aoi.geojson"
            if roads.exists():
                paths_by_role.setdefault("roads", str(roads))
            if buildings.exists():
                paths_by_role.setdefault("buildings", str(buildings))
            if "roads" in paths_by_role and "buildings" in paths_by_role:
                break

    resources = [_describe_resource(role, Path(path)) for role, path in sorted(paths_by_role.items())]
    bbox = None
    crs = None
    for role in ("boundary", "buildings", "roads", "function_buildings", "function_poi"):
        path_text = paths_by_role.get(role)
        if not path_text or not HAS_GEOPANDAS:
            continue
        try:
            gdf = gpd.read_file(path_text)
            if bbox is None and len(gdf) > 0:
                bbox = [float(value) for value in gdf.total_bounds]
            if crs is None and gdf.crs is not None:
                crs = str(gdf.crs)
        except Exception:
            continue

    return {
        "paths": paths_by_role,
        "resources": resources,
        "bbox": bbox,
        "crs": crs,
        "data_sources": sorted(paths_by_role),
        "governance": _summarize_governance(resources),
        "temporal": _summarize_temporal(resources),
        "legend": default_gis_legend(),
    }


def compute_built_form_metrics(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Compute generic building-footprint, height-proxy, road-density, and D/H metrics."""
    if not HAS_GEOPANDAS:
        return {"status": "unavailable", "reason": "geopandas is not installed"}
    context = discover_urban_data_sources(arguments)
    paths = context.get("paths", {})
    buildings_path = paths.get("buildings")
    if not buildings_path:
        return {"status": "unavailable", "reason": "no building footprint layer found", "capability": "urban_density_morphology"}

    buildings = gpd.read_file(buildings_path)
    buildings_m, metric_crs = _to_metric_crs(buildings)
    boundary_m = _boundary_metric_layer(paths, metric_crs)
    analysis_buildings_m = _clip_to_boundary(buildings_m, boundary_m)
    aoi_area_m2 = _aoi_area_m2(paths, buildings_m, boundary_m=boundary_m)
    footprint_area_m2 = float(analysis_buildings_m.geometry.area.sum()) if len(analysis_buildings_m) else 0.0
    coverage_ratio = footprint_area_m2 / aoi_area_m2 if aoi_area_m2 else None

    height_info = _height_proxy_series(analysis_buildings_m)
    height_series = height_info["height_m"]
    height_values = height_series.dropna()
    mean_height = float(height_values.mean()) if not height_values.empty else None
    median_height = float(height_values.median()) if not height_values.empty else None

    roads_path = paths.get("roads")
    road_length_m = None
    road_density = None
    street_width_proxy_m = None
    dh_ratio_proxy = None
    if roads_path:
        roads = gpd.read_file(roads_path)
        roads_m, _ = _to_metric_crs(roads, target_crs=metric_crs)
        roads_m = _clip_to_boundary(roads_m, boundary_m)
        road_length_m = float(roads_m.geometry.length.sum()) if len(roads_m) else 0.0
        road_density = road_length_m / 1000.0 / (aoi_area_m2 / 1_000_000.0) if aoi_area_m2 else None
        street_width_proxy_m = _street_width_proxy(roads_m, analysis_buildings_m)
        if street_width_proxy_m and mean_height and mean_height > 0:
            dh_ratio_proxy = street_width_proxy_m / mean_height

    metric_rows = [
        _metric_row("built_form", "source_building_count", len(buildings_m), "count", "source OSM building footprints before AOI clipping"),
        _metric_row("built_form", "aoi_intersecting_building_count", len(analysis_buildings_m), "count", "OSM buildings intersecting AOI boundary"),
        _metric_row("built_form", "building_footprint_area_m2", footprint_area_m2, "m2", "projected footprint area clipped to AOI boundary"),
        _metric_row("built_form", "building_coverage_ratio", coverage_ratio, "ratio", "footprint area / AOI area"),
        _metric_row("built_form", "mean_footprint_area_m2", footprint_area_m2 / len(analysis_buildings_m) if len(analysis_buildings_m) else None, "m2/building", "projected footprint area clipped to AOI boundary"),
        _metric_row("built_form", "height_proxy_coverage_ratio", height_info["proxy_count"] / len(analysis_buildings_m) if len(analysis_buildings_m) else None, "ratio", "height or building:levels * floor_height"),
        _metric_row("built_form", "mean_height_proxy_m", mean_height, "m", "height when present; otherwise building:levels * floor_height"),
        _metric_row("built_form", "median_height_proxy_m", median_height, "m", "height when present; otherwise building:levels * floor_height"),
        _metric_row("built_form", "street_width_proxy_m", street_width_proxy_m, "m", "2 * median positive road-centerline to nearest building distance"),
        _metric_row("built_form", "dh_ratio_proxy", dh_ratio_proxy, "ratio", "street_width_proxy_m / mean_height_proxy_m"),
        _metric_row("network", "road_length_m", road_length_m, "m", "projected road centerline length"),
        _metric_row("network", "road_density_km_per_km2", road_density, "km/km2", "road length / AOI area"),
    ]
    metric_rows = [row for row in metric_rows if row["value"] is not None]

    limitations = []
    if height_info["direct_count"] == 0 and height_info["proxy_count"] > 0:
        limitations.append("OSM height is absent; height metrics use building:levels multiplied by the configured floor height.")
    if height_info["proxy_count"] < len(analysis_buildings_m):
        limitations.append(f"Height/D-H metrics cover {height_info['proxy_count']} of {len(analysis_buildings_m)} AOI-intersecting buildings with usable height or level attributes.")
    if dh_ratio_proxy is None:
        limitations.append("D/H ratio is unavailable because either road spacing or height proxy is missing.")
    if boundary_m is not None and len(analysis_buildings_m) < len(buildings_m):
        limitations.append(f"Building cache is broader than AOI; footprint and road-density metrics use {len(analysis_buildings_m)} AOI-intersecting buildings after boundary clipping.")

    return {
        "status": "computed",
        "capability": "urban_density_morphology",
        "method": "geopandas_projected_building_and_road_metrics",
        "crs_metric": metric_crs,
        "paths": {key: paths.get(key) for key in ("boundary", "buildings", "roads") if paths.get(key)},
        "summary": {
            "building_count": len(buildings_m),
            "aoi_intersecting_building_count": len(analysis_buildings_m),
            "aoi_area_m2": aoi_area_m2,
            "building_coverage_ratio": coverage_ratio,
            "mean_height_proxy_m": mean_height,
            "height_proxy_coverage_ratio": height_info["proxy_count"] / len(analysis_buildings_m) if len(analysis_buildings_m) else None,
            "street_width_proxy_m": street_width_proxy_m,
            "dh_ratio_proxy": dh_ratio_proxy,
            "road_density_km_per_km2": road_density,
        },
        "metric_rows": metric_rows,
        "limitations": limitations,
    }


def compute_function_mix_entropy(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Compute Shannon entropy for POI/building-function categories."""
    context = discover_urban_data_sources(arguments)
    paths = context.get("paths", {})
    counts: Dict[str, int] = {}
    source_path = None

    counts_path = paths.get("function_counts")
    if counts_path and HAS_PANDAS:
        df = pd.read_csv(counts_path)
        function_col = _first_existing_column(df.columns, ["function", "Function", "category", "type"])
        count_col = _first_existing_column(df.columns, ["building_count", "count", "n"])
        if function_col and count_col:
            counts = {str(row[function_col]): int(row[count_col]) for _, row in df.iterrows() if not pd.isna(row[function_col])}
            source_path = counts_path

    if not counts and paths.get("function_buildings") and HAS_GEOPANDAS:
        gdf = gpd.read_file(paths["function_buildings"])
        function_col = _first_existing_column(gdf.columns, ["Function", "function", "category", "type"])
        if function_col:
            counts = {str(key): int(value) for key, value in gdf[function_col].value_counts(dropna=False).items()}
            source_path = paths["function_buildings"]

    if not counts:
        return {"status": "unavailable", "reason": "no POI/building function category layer found", "capability": "function_mix_entropy"}

    total = sum(counts.values())
    proportions = {name: value / total for name, value in counts.items() if total > 0}
    entropy = -sum(p * math.log(p) for p in proportions.values() if p > 0)
    normalized = entropy / math.log(len(proportions)) if len(proportions) > 1 else 0.0
    dominant = max(proportions.items(), key=lambda item: item[1]) if proportions else (None, None)
    commercial_share = sum(p for name, p in proportions.items() if "commercial" in name.lower() or "retail" in name.lower())

    metric_rows = [
        _metric_row("function_mix", "function_category_count", len(proportions), "count", "count of distinct function labels"),
        _metric_row("function_mix", "function_entropy", entropy, "nat", "Shannon entropy over function categories"),
        _metric_row("function_mix", "function_entropy_normalized", normalized, "0-1", "entropy / log(category_count)"),
        _metric_row("function_mix", "dominant_function_share", dominant[1], "ratio", f"dominant function: {dominant[0]}"),
        _metric_row("function_mix", "commercial_share", commercial_share, "ratio", "share of commercial/retail function labels"),
    ]

    return {
        "status": "computed",
        "capability": "function_mix_entropy",
        "method": "shannon_entropy_from_function_category_counts",
        "path": source_path,
        "counts": counts,
        "summary": {
            "total_features": total,
            "function_category_count": len(proportions),
            "function_entropy": entropy,
            "function_entropy_normalized": normalized,
            "dominant_function": dominant[0],
            "dominant_function_share": dominant[1],
            "commercial_share": commercial_share,
        },
        "metric_rows": metric_rows,
        "limitations": ["Function entropy reflects the available function-label layer and should be interpreted with its model/source uncertainty."],
    }


def compute_streetview_visual_consistency(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Compute a transparent street-view style-consistency proxy from image color histograms."""
    if not HAS_PIL:
        return {"status": "unavailable", "reason": "Pillow is not installed", "capability": "streetview_visual_consistency"}
    context = discover_urban_data_sources(arguments)
    paths = context.get("paths", {})
    streetview_dir = paths.get("streetview_dir")
    if not streetview_dir:
        return {"status": "unavailable", "reason": "no street-view image directory found", "capability": "streetview_visual_consistency"}

    image_paths = _sample_streetview_images(Path(streetview_dir), limit=int(arguments.get("streetview_sample_limit", 60)))
    if not image_paths:
        return {"status": "unavailable", "reason": "street-view directory contains no readable images", "capability": "streetview_visual_consistency"}

    histograms = []
    mean_rgbs = []
    for path in image_paths:
        try:
            image = Image.open(path).convert("RGB").resize((64, 64))
            arr = np.asarray(image, dtype=np.float32)
            mean_rgbs.append(arr.reshape(-1, 3).mean(axis=0))
            hist = []
            for channel in range(3):
                channel_hist, _ = np.histogram(arr[:, :, channel], bins=8, range=(0, 255), density=True)
                hist.extend(channel_hist.tolist())
            histograms.append(np.asarray(hist, dtype=np.float32))
        except Exception:
            continue

    if not histograms:
        return {"status": "unavailable", "reason": "no street-view images could be decoded", "capability": "streetview_visual_consistency"}

    consistency = _mean_cosine_similarity(histograms)
    mean_rgb = np.vstack(mean_rgbs).mean(axis=0)
    rgb_std = np.vstack(mean_rgbs).std(axis=0)
    palette_score, delta_e, palette_name = _traditional_palette_score(mean_rgb)
    points_count = _streetview_point_count(paths.get("streetview_points"))

    metric_rows = [
        _metric_row("streetview", "streetview_sampled_image_count", len(histograms), "count", "sampled decoded street-view images"),
        _metric_row("streetview", "streetview_style_consistency", consistency, "0-1", "mean pairwise cosine similarity of RGB histograms"),
        _metric_row("streetview", "traditional_palette_match_score", palette_score, "0-1", f"nearest palette color: {palette_name}"),
        _metric_row("streetview", "traditional_palette_delta_e", delta_e, "deltaE", "CIELAB distance to nearest traditional palette color"),
        _metric_row("streetview", "mean_rgb_std", float(rgb_std.mean()), "RGB std", "dispersion of image-level mean RGB values"),
    ]

    return {
        "status": "computed",
        "capability": "streetview_visual_consistency",
        "method": "rgb_histogram_consistency_and_palette_distance_proxy",
        "path": streetview_dir,
        "summary": {
            "streetview_point_count": points_count,
            "sampled_image_count": len(histograms),
            "style_consistency_score": consistency,
            "traditional_palette_match_score": palette_score,
            "traditional_palette_delta_e": delta_e,
            "nearest_palette_color": palette_name,
            "mean_color_hex": _rgb_to_hex(mean_rgb),
            "mean_rgb_std": float(rgb_std.mean()),
        },
        "metric_rows": metric_rows,
        "limitations": [
            "This is a transparent color-distribution proxy, not a facade-material or signboard segmentation model.",
            "Use VLM/manual labels for material visibility and signboard occlusion before treating those sub-indicators as direct measurements.",
        ],
    }


def build_gis_artifact_bundle(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Create formal GIS layers, projected map figures, charts, and street-view grids."""
    if not HAS_GEOPANDAS:
        return {"status": "unavailable", "reason": "geopandas is not installed", "capability": "gis_layer_stack_export"}
    artifact_dir = Path(arguments.get("artifact_dir") or arguments.get("output_dir") or "artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    context = discover_urban_data_sources(arguments)
    paths = context.get("paths", {})
    artifacts: list[Dict[str, Any]] = []
    layer_paths: Dict[str, str] = {}
    loaded: Dict[str, Any] = {}

    for role in ("boundary", "roads", "buildings", "function_buildings", "function_poi"):
        path_text = paths.get(role)
        if not path_text:
            continue
        try:
            loaded[role] = gpd.read_file(path_text)
        except Exception as error:
            logger.warning("Could not load %s layer %s: %s", role, path_text, error)

    metric_rows = _collect_metric_rows(arguments)
    aligned_loaded, alignment_diagnostics = _governed_align_loaded_layers_to_aoi(
        loaded,
        metric_rows=metric_rows,
        context_width_factor=float(arguments.get("context_buffer_width_factor", 3.0)),
        context_height_factor=float(arguments.get("context_buffer_height_factor", 3.0)),
    )
    alignment_path = artifact_dir / "spatial_alignment_diagnostics.json"
    alignment_path.write_text(json.dumps(alignment_diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")
    artifacts.append(_artifact("spatial_alignment_diagnostics", "Spatial Alignment Diagnostics", alignment_path, "application/json", {"artifact_role": "review_diagnostics"}))

    gpkg_path = artifact_dir / "urbanagent_gis_layers.gpkg"
    if aligned_loaded:
        if gpkg_path.exists():
            gpkg_path.unlink()
        for role, gdf in aligned_loaded.items():
            try:
                gdf.to_file(gpkg_path, layer=role, driver="GPKG")
                layer_paths[role] = f"{gpkg_path}|layername={role}"
            except Exception as error:
                fallback = artifact_dir / f"{role}.geojson"
                gdf.to_file(fallback, driver="GeoJSON")
                layer_paths[role] = str(fallback)
                logger.warning("GPKG write failed for %s, wrote GeoJSON: %s", role, error)
        artifacts.append(_artifact("gis_layer_package", "Formal GIS Layer Package", gpkg_path, "application/geopackage+sqlite3", {"layers": sorted(aligned_loaded), "alignment_policy": alignment_diagnostics.get("policy")}))
        metric_layer_names = [name for name in aligned_loaded if name.endswith("metric_summary") or name.startswith("metric_")]
        if metric_layer_names:
            artifacts.append(_artifact("metric_result_layers", "Spatialized Metric Result Layers", gpkg_path, "application/geopackage+sqlite3", {"layers": metric_layer_names, "artifact_role": "spatialized_analysis_results"}))

    map_png, map_pdf = _plot_gis_overlay(aligned_loaded, artifact_dir)
    if map_png:
        artifacts.append(_artifact("map_png", "Projected GIS Overlay Map", map_png, "image/png", {"artifact_role": "formal_gis"}))
    if map_pdf:
        artifacts.append(_artifact("map_pdf", "Projected GIS Overlay Map PDF", map_pdf, "application/pdf", {"artifact_role": "formal_gis"}))

    if metric_rows:
        metrics_csv = artifact_dir / "urban_metrics.csv"
        _write_metric_rows(metrics_csv, metric_rows)
        artifacts.append(_artifact("metric_csv", "Urban Metric Table", metrics_csv, "text/csv", {"row_count": len(metric_rows)}))
        chart_png = _plot_metric_chart(metric_rows, artifact_dir)
        if chart_png:
            artifacts.append(_artifact("chart_png", "Urban Metric Chart", chart_png, "image/png", {"artifact_role": "analysis_chart"}))

    grid_png = _build_streetview_grid(paths.get("streetview_dir"), artifact_dir)
    if grid_png:
        artifacts.append(_artifact("streetview_grid_png", "Street-view Thumbnail Grid", grid_png, "image/png", {"artifact_role": "visual_evidence_grid"}))

    return {
        "status": "visualization_complete",
        "capability": "gis_layer_stack_export",
        "outputs": [artifact["type"] for artifact in artifacts],
        "artifacts": artifacts,
        "layer_stack": layer_paths,
        "legend": context.get("legend", default_gis_legend()),
        "symbology": default_gis_legend(),
        "artifact_role": "formal_gis",
        "paths": paths,
        "alignment_diagnostics": alignment_diagnostics,
        "metric_result_layers": {name: path for name, path in layer_paths.items() if name.endswith("metric_summary") or name.startswith("metric_")},
    }


def default_gis_legend() -> Dict[str, Any]:
    return {
        "aoi": {"geometry": "polygon boundary", "stroke": "#111827", "fill": "none", "label": "AOI boundary"},
        "context_buffer": {"geometry": "polygon boundary", "stroke": "#64748b", "fill": "none", "label": "3x by 3x AOI-centered context buffer"},
        "context_roads": {"geometry": "line", "stroke": "#94a3b8", "label": "Context road centerlines"},
        "context_buildings": {"geometry": "polygon", "fill": "#e5e7eb", "stroke": "#cbd5e1", "label": "Context building footprints"},
        "context_function_poi": {"geometry": "point", "marker": "circle", "label": "Context function POIs"},
        "aoi_metric_summary": {"geometry": "polygon", "fill": "#fde68a", "stroke": "#92400e", "label": "AOI metric result summary"},
        "roads": {"geometry": "line", "stroke": "#475569", "label": "Road centerlines"},
        "buildings": {"geometry": "polygon", "fill": "#d8c7aa", "stroke": "#8a7a63", "label": "Building footprints"},
        "function_buildings": {"geometry": "polygon", "fill": "categorical", "label": "Building function labels"},
        "streetview_points": {"geometry": "point", "marker": "circle", "label": "Street-view sample points"},
    }


def _collect_existing_paths(value: Any, paths: list[Path]) -> None:
    if isinstance(value, dict):
        for key in ("path", "file", "filepath", "input_path"):
            resolved = resolve_urban_path(value.get(key))
            if resolved and resolved not in paths:
                paths.append(resolved)
        for key in ("declared_paths", "resources", "resource_catalog"):
            items = value.get(key)
            if isinstance(items, list):
                for item in items:
                    _collect_existing_paths(item, paths)
        for item in value.values():
            _collect_existing_paths(item, paths)
    elif isinstance(value, list):
        for item in value:
            _collect_existing_paths(item, paths)
    elif isinstance(value, str):
        for token in _extract_path_tokens(value):
            resolved = resolve_urban_path(token)
            if resolved and resolved not in paths:
                paths.append(resolved)


def _extract_path_tokens(text: str) -> list[str]:
    tokens: list[str] = [match.group(1) for match in re.finditer(r"`([^`]+)`", text)]
    patterns = [
        r"[A-Za-z]:[\\/][^\n\r，,。；;`|]+",
        r"(?:\.\.[\\/])?paper[0-9A-Za-z_\-]+[\\/][^\n\r，,。；;\s`|]+",
    ]
    for pattern in patterns:
        tokens.extend(match.group(0) for match in re.finditer(pattern, text))
    return tokens


def _classify_urban_path(path: Path) -> Optional[str]:
    norm = path.as_posix().lower()
    name = path.name.lower()
    if path.is_dir() and ("streetview" in norm or (path / "points_used.csv").exists()):
        return "streetview_dir"
    if name == "points_used.csv":
        return "streetview_points"
    if "sinobf" in norm:
        if name == "sinobf_function_counts.csv":
            return "function_counts"
        if name == "sinobf_buildings.geojson":
            return "function_buildings"
        if name == "sinobf_building_poi.geojson":
            return "function_poi"
        if path.is_dir():
            return "function_root"
    if name.endswith(('.geojson', '.gpkg', '.shp')):
        if "road" in name or "roads" in name:
            return "roads"
        if "building" in name and "poi" not in name:
            return "buildings"
        if "boundary" in name or "aoi" in name:
            return "boundary"
    if name == "district_metrics.csv":
        return "district_metrics"
    return None



def _find_matching_osm_cache_dir(root: Path, paths_by_role: Dict[str, str]) -> Optional[Path]:
    if not root.exists() or not root.is_dir():
        return None
    candidates: list[Path] = []
    if (root / "osm_roads_aoi.geojson").exists() or (root / "osm_buildings_aoi.geojson").exists():
        candidates.append(root)
    search_root = root / "districts" if (root / "districts").exists() else root
    candidates.extend(path.parent for path in search_root.rglob("osm_roads_aoi.geojson"))
    candidates.extend(path.parent for path in search_root.rglob("osm_buildings_aoi.geojson"))
    unique_candidates = list(dict.fromkeys(candidates))
    if not unique_candidates:
        return None

    hints = " ".join(Path(path).as_posix() for path in paths_by_role.values()).lower()
    best_score = -1
    best_dir = unique_candidates[0]
    for folder in unique_candidates:
        folder_text = folder.as_posix().lower()
        tokens = [token for token in re.split(r"[_\-\s/\\]+", folder_text) if token]
        score = sum(1 for token in tokens if token in hints)
        prefix = folder.name.split("_")[0]
        if prefix and prefix in hints:
            score += 5
        if "??" in hints and "??" in folder.name:
            score += 2
        if "???" in hints and "???" in folder.name:
            score += 3
        if score > best_score:
            best_score = score
            best_dir = folder
    return best_dir


def _find_matching_sinobf_dir(root: Path, paths_by_role: Dict[str, str]) -> Optional[Path]:
    search_root = root / "extracted" if (root / "extracted").exists() else root
    count_files = list(search_root.rglob("sinobf_function_counts.csv"))
    if not count_files:
        return None
    hints = " ".join(Path(path).as_posix() for key, path in paths_by_role.items() if key != "function_root").lower()
    best_score = -1
    best_dir = count_files[0].parent
    for count_file in count_files:
        folder = count_file.parent
        tokens = re.split(r"[_\-\s/\\]+", folder.as_posix().lower())
        score = sum(1 for token in tokens if token and token in hints)
        prefix = folder.name.split("_")[0]
        if prefix and prefix in hints:
            score += 3
        if score > best_score:
            best_score = score
            best_dir = folder
    return best_dir


def _describe_resource(role: str, path: Path) -> Dict[str, Any]:
    stat = path.stat() if path.exists() else None
    resource = {
        "role": role,
        "path": str(path),
        "exists": path.exists(),
        "is_dir": path.is_dir(),
        "format": _resource_format(path),
        "license": _resource_license(role),
        "collection_method": _resource_collection_method(role),
        "uncertainty": _resource_uncertainty(role),
        "time_window": _resource_time_window(role, stat),
        "freshness": _resource_freshness(role, stat),
    }
    if stat:
        resource["modified_time"] = datetime.fromtimestamp(stat.st_mtime).date().isoformat()
    if path.is_dir():
        resource["item_count"] = len(list(path.iterdir()))
    elif HAS_GEOPANDAS and path.suffix.lower() in {".geojson", ".gpkg", ".shp"}:
        try:
            gdf = gpd.read_file(path)
            resource.update({
                "feature_count": len(gdf),
                "crs": str(gdf.crs) if gdf.crs else None,
                "geometry_types": gdf.geometry.geom_type.value_counts().to_dict() if len(gdf) else {},
            })
        except Exception:
            pass
    elif HAS_PANDAS and path.suffix.lower() == ".csv":
        try:
            df = pd.read_csv(path, nrows=5)
            resource["columns"] = list(df.columns)
        except Exception:
            pass
    return resource


def _resource_format(path: Path) -> str:
    if path.is_dir():
        return "directory"
    if path.suffix:
        return path.suffix.lower().lstrip(".")
    return "unknown"


def _resource_license(role: str) -> str:
    if role in {"roads", "buildings"}:
        return "OpenStreetMap contributors, ODbL 1.0"
    if role.startswith("function"):
        return "SinoBF-1 dataset metadata; verify dataset license before redistribution"
    if role.startswith("streetview"):
        return "street-view provider terms; local research cache, redistribution restricted"
    if role == "boundary":
        return "project-derived AOI boundary; cite generation/verification record"
    return "source-specific license recorded in resource metadata when available"


def _resource_collection_method(role: str) -> str:
    methods = {
        "roads": "local OSM road-centerline cache",
        "buildings": "local OSM building-footprint cache",
        "boundary": "project AOI boundary GeoJSON",
        "streetview_dir": "street-view batch image cache",
        "streetview_points": "street-view sample-point metadata",
        "function_counts": "building-function label aggregation",
        "function_buildings": "building-function polygon layer",
        "function_poi": "building-function point layer",
    }
    return methods.get(role, "local data resource inspection")


def _resource_uncertainty(role: str) -> str:
    uncertainties = {
        "roads": "OSM completeness and cache freshness vary by street class",
        "buildings": "OSM footprints may miss recent edits; height attributes are often incomplete",
        "boundary": "AOI boundary should be checked against authoritative planning boundary where available",
        "streetview_dir": "viewpoint, season, lighting, and provider capture time affect visual proxies",
        "streetview_points": "sample spacing may miss fine-grained facade/signboard variation",
        "function_counts": "function labels inherit the source model/data uncertainty",
        "function_buildings": "function labels inherit the source model/data uncertainty",
        "function_poi": "point representation may not align perfectly with footprint geometry",
    }
    return uncertainties.get(role, "source uncertainty should be reviewed before publication")


def _resource_time_window(role: str, stat: Any) -> str:
    if role.startswith("streetview"):
        return "street-view observation window from local cache metadata or file timestamps"
    if role in {"roads", "buildings"}:
        return "OSM cache snapshot inferred from local file timestamp"
    if role.startswith("function"):
        return "function-label dataset release/cache snapshot inferred from local file timestamp"
    return "observation window inferred from local metadata or file timestamp"


def _resource_freshness(role: str, stat: Any) -> str:
    if stat is None:
        return "unknown"
    return f"local file modified {datetime.fromtimestamp(stat.st_mtime).date().isoformat()}"


def _summarize_governance(resources: list[Dict[str, Any]]) -> Dict[str, str]:
    return {
        "provenance": "; ".join(f"{r['role']}={r['path']}" for r in resources[:8]),
        "license": "; ".join(sorted({r.get("license", "") for r in resources if r.get("license")})),
        "collection_method": "; ".join(sorted({r.get("collection_method", "") for r in resources if r.get("collection_method")})),
        "uncertainty": "; ".join(sorted({r.get("uncertainty", "") for r in resources if r.get("uncertainty")})),
    }


def _summarize_temporal(resources: list[Dict[str, Any]]) -> Dict[str, str]:
    modified = [r.get("modified_time") for r in resources if r.get("modified_time")]
    if modified:
        time_window = f"local evidence files modified {min(modified)} to {max(modified)}"
    else:
        time_window = "observation window inferred from source metadata"
    return {
        "time_window": time_window,
        "granularity": "feature-level vector layers and/or street-view sample points",
        "freshness": "; ".join(sorted({r.get("freshness", "") for r in resources if r.get("freshness")})),
    }


def _to_metric_crs(gdf: Any, target_crs: Any = None) -> Tuple[Any, str]:
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326", allow_override=True)
    crs = target_crs
    if crs is None:
        try:
            crs = gdf.estimate_utm_crs()
        except Exception:
            crs = None
    if crs is None:
        crs = "EPSG:3857"
    return gdf.to_crs(crs), str(crs)


def _boundary_metric_layer(paths: Dict[str, str], target_crs: Any) -> Optional[Any]:
    boundary_path = paths.get("boundary")
    if not boundary_path:
        return None
    try:
        boundary = gpd.read_file(boundary_path)
        boundary_m, _ = _to_metric_crs(boundary, target_crs=target_crs)
        return boundary_m
    except Exception:
        return None


def _clip_to_boundary(gdf: Any, boundary_m: Any) -> Any:
    if boundary_m is None or len(gdf) == 0:
        return gdf
    try:
        boundary_union = boundary_m.geometry.unary_union
        clipped = gdf.copy()
        clipped["geometry"] = clipped.geometry.intersection(boundary_union)
        clipped = clipped[clipped.geometry.notna() & ~clipped.geometry.is_empty]
        return clipped
    except Exception:
        return gdf


def _align_loaded_layers_to_aoi(
    loaded: Dict[str, Any],
    *,
    metric_rows: Optional[list[Dict[str, Any]]] = None,
    context_width_factor: float = 3.0,
    context_height_factor: float = 3.0,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Clip AOI analysis layers, preserve AOI-centered context layers, and record diagnostics."""
    diagnostics: Dict[str, Any] = {
        "policy": "aoi_analysis_layers_clipped_context_layers_use_aoi_centered_buffer",
        "status": "no_layers",
        "layers": {},
        "context_buffer": {},
        "metric_spatialization": {},
        "issues": [],
    }
    if not loaded:
        return {}, diagnostics

    boundary = loaded.get("boundary")
    if boundary is None or len(boundary) == 0:
        diagnostics.update({
            "status": "no_boundary",
            "issues": ["No AOI boundary was available; formal GIS layers were exported without AOI clipping."],
        })
        return dict(loaded), diagnostics

    boundary = boundary.copy()
    if boundary.crs is None:
        boundary = boundary.set_crs("EPSG:4326", allow_override=True)
    aligned: Dict[str, Any] = {}
    context_buffer, context_diag = _build_aoi_context_buffer(
        boundary,
        width_factor=context_width_factor,
        height_factor=context_height_factor,
    )
    diagnostics["context_buffer"] = context_diag
    if context_buffer is not None and len(context_buffer):
        aligned["context_buffer"] = context_buffer
    aligned["boundary"] = boundary.copy()

    ctx_width_m = float(context_diag.get("context_width_m") or 0.0)
    ctx_height_m = float(context_diag.get("context_height_m") or 0.0)

    try:
        boundary_union = boundary.geometry.unary_union
    except Exception:
        diagnostics.update({
            "status": "invalid_boundary",
            "issues": ["AOI boundary geometry could not be unified; formal GIS layers were exported without AOI clipping."],
        })
        return dict(loaded), diagnostics

    context_union = None
    if context_buffer is not None and len(context_buffer):
        try:
            context_union = context_buffer.geometry.unary_union
        except Exception:
            context_union = None

    any_warning = False
    any_failure = False
    for role, source in loaded.items():
        if role == "boundary":
            diagnostics["layers"][role] = {
                "source_feature_count": int(len(source)),
                "exported_feature_count": int(len(source)),
                "output_clipped_to_aoi": False,
                "geometry_type": _geometry_type_summary(source),
            }
            continue

        layer_diag: Dict[str, Any] = {
            "source_feature_count": int(len(source)),
            "source_crs": str(source.crs) if getattr(source, "crs", None) else None,
            "target_crs": str(boundary.crs) if getattr(boundary, "crs", None) else None,
            "geometry_type": _geometry_type_summary(source),
            "output_clipped_to_aoi": True,
            "output_clipped_to_context_buffer": context_union is not None,
        }
        try:
            working = source.copy()
            if working.crs is None and boundary.crs is not None:
                working = working.set_crs(boundary.crs, allow_override=True)
            elif boundary.crs is not None and working.crs != boundary.crs:
                working = working.to_crs(boundary.crs)

            valid_geom = working.geometry.notna() & ~working.geometry.is_empty
            intersects = valid_geom & working.geometry.intersects(boundary_union)
            intersecting_count = int(intersects.sum())
            clipped = working.loc[intersects].copy()
            if len(clipped):
                if _is_point_layer(clipped):
                    clipped = clipped[clipped.geometry.within(boundary_union) | clipped.geometry.intersects(boundary_union)]
                else:
                    clipped["geometry"] = clipped.geometry.intersection(boundary_union)
                    clipped = clipped[clipped.geometry.notna() & ~clipped.geometry.is_empty]
            exported_count = int(len(clipped))
            context_clipped = None
            context_intersecting_count = None
            outside_context_count = None
            outside_context_ratio = None
            if context_union is not None:
                context_intersects = valid_geom & working.geometry.intersects(context_union)
                context_intersecting_count = int(context_intersects.sum())
                context_clipped = working.loc[context_intersects].copy()
                if len(context_clipped):
                    if _is_point_layer(context_clipped):
                        context_clipped = context_clipped[context_clipped.geometry.within(context_union) | context_clipped.geometry.intersects(context_union)]
                    else:
                        context_clipped["geometry"] = context_clipped.geometry.intersection(context_union)
                        context_clipped = context_clipped[context_clipped.geometry.notna() & ~context_clipped.geometry.is_empty]
                aligned[f"context_{role}"] = context_clipped
                outside_context_count = max(0, int(len(working)) - context_intersecting_count)
                outside_context_ratio = outside_context_count / int(len(working)) if len(working) else 0.0
            outside_count = max(0, int(len(working)) - intersecting_count)
            outside_ratio = outside_count / int(len(working)) if len(working) else 0.0
            layer_diag.update({
                "aoi_intersecting_feature_count": intersecting_count,
                "exported_feature_count": exported_count,
                "context_intersecting_feature_count": context_intersecting_count,
                "context_exported_feature_count": int(len(context_clipped)) if context_clipped is not None else None,
                "source_outside_aoi_feature_count": outside_count,
                "source_outside_aoi_feature_ratio": round(float(outside_ratio), 4),
                "source_outside_context_buffer_feature_count": outside_context_count,
                "source_outside_context_buffer_feature_ratio": round(float(outside_context_ratio), 4) if outside_context_ratio is not None else None,
                "source_bounds": _bounds_list(working),
                "exported_bounds": _bounds_list(clipped),
                "context_exported_bounds": _bounds_list(context_clipped) if context_clipped is not None else None,
            })
            aligned[role] = clipped

            if exported_count == 0 and len(working) > 0:
                issue = f"{role}: no source features intersect the AOI boundary; layer may be from a mismatched place or CRS."
                diagnostics["issues"].append(issue)
                layer_diag["severity"] = "error"
                any_failure = True
            elif outside_context_ratio is not None and outside_context_ratio > 0.25:
                issue = f"{role}: {outside_context_ratio:.1%} of source features fall outside the AOI-centered context buffer; source cache may still be broader than the intended analysis context."
                diagnostics["issues"].append(issue)
                layer_diag["severity"] = "warning"
                any_warning = True
            elif outside_ratio > 0.25:
                layer_diag["severity"] = "context_only"
                layer_diag["note"] = "Source layer extends beyond AOI as expected for context loading; AOI analysis output is clipped and context output is clipped to the AOI-centered buffer."
            else:
                layer_diag["severity"] = "ok"
        except Exception as error:
            aligned[role] = source
            layer_diag.update({
                "exported_feature_count": int(len(source)),
                "output_clipped_to_aoi": False,
                "severity": "error",
                "error": str(error),
            })
            diagnostics["issues"].append(f"{role}: AOI clipping failed ({error}); raw layer was preserved.")
            any_failure = True
        diagnostics["layers"][role] = layer_diag

    # --- Source-to-buffer extent coverage ---
    if ctx_width_m > 0 and ctx_height_m > 0:
        for role, layer_diag in diagnostics["layers"].items():
            if role == "boundary" or not isinstance(layer_diag, dict):
                continue
            src_bounds = layer_diag.get("source_bounds")
            ctx_exp_bounds = layer_diag.get("context_exported_bounds")
            if not src_bounds or len(src_bounds) != 4 or not ctx_exp_bounds or len(ctx_exp_bounds) != 4:
                continue
            src_w = max(0.0, float(src_bounds[2]) - float(src_bounds[0]))
            src_h = max(0.0, float(src_bounds[3]) - float(src_bounds[1]))
            ctx_w = max(0.0, float(ctx_exp_bounds[2]) - float(ctx_exp_bounds[0]))
            ctx_h = max(0.0, float(ctx_exp_bounds[3]) - float(ctx_exp_bounds[1]))
            w_cov = round(src_w / ctx_w, 4) if ctx_w > 0 else None
            h_cov = round(src_h / ctx_h, 4) if ctx_h > 0 else None
            layer_diag["buffer_extent_width_coverage_ratio"] = w_cov
            layer_diag["buffer_extent_height_coverage_ratio"] = h_cov
            if (w_cov is not None and w_cov < 0.55) or (h_cov is not None and h_cov < 0.55):
                issue = (
                    f"{role}: source data extent covers only {w_cov:.0%}×{h_cov:.0%} of the context buffer "
                    f"(WGS84 degrees); source data was likely pre-clipped at AOI scale — "
                    f"re-fetch from OSM at buffer scale"
                )
                diagnostics["issues"].append(issue)
                if layer_diag.get("severity") == "ok":
                    layer_diag["severity"] = "context_only"
                    layer_diag["note"] = str(layer_diag.get("note") or "") + " " + issue

    metric_layer, metric_diag = _build_aoi_metric_summary_layer(boundary, metric_rows or [])
    diagnostics["metric_spatialization"] = metric_diag
    if metric_layer is not None and len(metric_layer):
        aligned["aoi_metric_summary"] = metric_layer

    diagnostics["status"] = "failed" if any_failure else ("aligned_with_warnings" if any_warning else "aligned_with_context_buffer")
    return aligned, diagnostics


def _build_aoi_context_buffer(boundary: Any, *, width_factor: float = 3.0, height_factor: float = 3.0) -> Tuple[Optional[Any], Dict[str, Any]]:
    """Build an AOI-centered rectangular context buffer with configurable width/height factors."""
    diagnostics: Dict[str, Any] = {
        "policy": "aoi_centered_rectangular_context_buffer",
        "width_factor": width_factor,
        "height_factor": height_factor,
        "area_ratio_to_aoi_bbox": None,
        "centered_on_aoi": False,
    }
    if boundary is None or len(boundary) == 0 or not HAS_GEOPANDAS:
        diagnostics["status"] = "unavailable"
        return None, diagnostics
    try:
        boundary_m, metric_crs = _to_metric_crs(boundary)
        min_x, min_y, max_x, max_y = [float(value) for value in boundary_m.total_bounds]
        width = max(max_x - min_x, 1.0)
        height = max(max_y - min_y, 1.0)
        center_x = (min_x + max_x) / 2.0
        center_y = (min_y + max_y) / 2.0
        context_width = width * width_factor
        context_height = height * height_factor
        context_geom = box(
            center_x - context_width / 2.0,
            center_y - context_height / 2.0,
            center_x + context_width / 2.0,
            center_y + context_height / 2.0,
        )
        context_m = gpd.GeoDataFrame(
            {
                "layer_role": ["aoi_context_buffer"],
                "width_factor": [width_factor],
                "height_factor": [height_factor],
                "area_ratio": [width_factor * height_factor],
            },
            geometry=[context_geom],
            crs=metric_crs,
        )
        context = context_m.to_crs(boundary.crs) if boundary.crs is not None else context_m
        diagnostics.update({
            "status": "generated",
            "metric_crs": metric_crs,
            "aoi_bounds_metric": [min_x, min_y, max_x, max_y],
            "context_bounds_metric": [float(value) for value in context_m.total_bounds],
            "aoi_center_metric": [center_x, center_y],
            "context_center_metric": [center_x, center_y],
            "aoi_bbox_width_m": width,
            "aoi_bbox_height_m": height,
            "context_width_m": context_width,
            "context_height_m": context_height,
            "area_ratio_to_aoi_bbox": width_factor * height_factor,
            "centered_on_aoi": True,
        })
        return context, diagnostics
    except Exception as error:
        diagnostics.update({"status": "failed", "error": str(error)})
        return None, diagnostics


def _build_aoi_metric_summary_layer(boundary: Any, metric_rows: list[Dict[str, Any]]) -> Tuple[Optional[Any], Dict[str, Any]]:
    """Spatialize scalar AOI-level metrics as attributes on an AOI result polygon."""
    diagnostics: Dict[str, Any] = {
        "status": "not_applicable",
        "spatialization_scope": "aoi_polygon",
        "metric_count": 0,
        "numeric_metric_count": 0,
    }
    if boundary is None or len(boundary) == 0 or not metric_rows or not HAS_GEOPANDAS:
        return None, diagnostics
    numeric_rows = [row for row in metric_rows if isinstance(row.get("value"), (int, float)) and row.get("metric")]
    if not numeric_rows:
        diagnostics["status"] = "no_numeric_metrics"
        diagnostics["metric_count"] = len(metric_rows)
        return None, diagnostics
    try:
        geometry = boundary.geometry.unary_union
        payload: Dict[str, Any] = {
            "layer_role": "aoi_metric_summary",
            "metric_count": len(metric_rows),
            "numeric_metric_count": len(numeric_rows),
        }
        used_fields: set[str] = set(payload)
        metric_manifest = []
        for row in numeric_rows[:40]:
            field_name = _safe_metric_field_name(str(row.get("metric")), used_fields)
            payload[field_name] = float(row.get("value"))
            metric_manifest.append({
                "field": field_name,
                "metric": row.get("metric"),
                "group": row.get("group"),
                "unit": row.get("unit"),
                "method": row.get("method"),
            })
        payload["metric_manifest"] = json.dumps(metric_manifest, ensure_ascii=False)[:8000]
        layer = gpd.GeoDataFrame(payload, index=[0], geometry=[geometry], crs=boundary.crs)
        diagnostics.update({
            "status": "spatialized",
            "metric_count": len(metric_rows),
            "numeric_metric_count": len(numeric_rows),
            "layer": "aoi_metric_summary",
            "fields": [item["field"] for item in metric_manifest],
        })
        return layer, diagnostics
    except Exception as error:
        diagnostics.update({"status": "failed", "error": str(error), "metric_count": len(metric_rows), "numeric_metric_count": len(numeric_rows)})
        return None, diagnostics


def _safe_metric_field_name(metric: str, used_fields: set[str]) -> str:
    base = re.sub(r"[^0-9A-Za-z_]+", "_", metric.lower()).strip("_") or "metric"
    if base[0].isdigit():
        base = f"m_{base}"
    base = base[:48]
    name = base
    suffix = 2
    while name in used_fields:
        tail = f"_{suffix}"
        name = base[: 48 - len(tail)] + tail
        suffix += 1
    used_fields.add(name)
    return name


def _geometry_type_summary(gdf: Any) -> Dict[str, int]:
    try:
        return {str(key): int(value) for key, value in gdf.geometry.geom_type.value_counts().to_dict().items()}
    except Exception:
        return {}


def _is_point_layer(gdf: Any) -> bool:
    try:
        geom_types = {str(value).lower() for value in gdf.geometry.geom_type.dropna().unique()}
        return bool(geom_types) and geom_types.issubset({"point", "multipoint"})
    except Exception:
        return False


def _bounds_list(gdf: Any) -> Optional[list[float]]:
    try:
        if len(gdf) == 0:
            return None
        return [float(value) for value in gdf.total_bounds]
    except Exception:
        return None


def _aoi_area_m2(paths: Dict[str, str], fallback_buildings_m: Any, boundary_m: Any = None) -> Optional[float]:
    if boundary_m is not None:
        try:
            return float(boundary_m.geometry.area.sum())
        except Exception:
            pass
    if len(fallback_buildings_m):
        return float(fallback_buildings_m.unary_union.convex_hull.area)
    return None


def _height_proxy_series(buildings: Any, floor_height_m: float = 3.2) -> Dict[str, Any]:
    direct = _numeric_column(buildings, ["height", "Height", "HEIGHT"])
    levels = _numeric_column(buildings, ["building:levels", "building_levels", "levels", "floors"])
    proxy = direct.copy() if direct is not None else None
    if proxy is None:
        proxy = levels * floor_height_m if levels is not None else np.nan
    elif levels is not None:
        proxy = proxy.fillna(levels * floor_height_m)
    if not hasattr(proxy, "dropna"):
        proxy = pd.Series([np.nan] * len(buildings)) if HAS_PANDAS else proxy
    return {
        "height_m": proxy,
        "direct_count": int(direct.dropna().shape[0]) if direct is not None else 0,
        "level_count": int(levels.dropna().shape[0]) if levels is not None else 0,
        "proxy_count": int(proxy.dropna().shape[0]) if hasattr(proxy, "dropna") else 0,
    }


def _numeric_column(frame: Any, candidates: list[str]) -> Any:
    if not HAS_PANDAS:
        return None
    column = _first_existing_column(frame.columns, candidates)
    if not column:
        return None
    return frame[column].map(_parse_number)


def _parse_number(value: Any) -> Optional[float]:
    if value is None or (HAS_PANDAS and pd.isna(value)):
        return np.nan
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    return float(match.group(0)) if match else np.nan


def _street_width_proxy(roads_m: Any, buildings_m: Any) -> Optional[float]:
    if len(roads_m) == 0 or len(buildings_m) == 0:
        return None
    try:
        building_union = buildings_m.geometry.boundary.unary_union
        distances = []
        for geom in roads_m.geometry:
            if geom is None or geom.is_empty:
                continue
            point = geom.interpolate(0.5, normalized=True) if hasattr(geom, "interpolate") else geom.representative_point()
            distance = float(point.distance(building_union))
            if distance > 0:
                distances.append(distance)
        if not distances:
            return None
        return float(np.median(distances) * 2.0)
    except Exception:
        return None


def _metric_row(group: str, metric: str, value: Any, unit: str, method: str) -> Dict[str, Any]:
    return {"group": group, "metric": metric, "value": _json_number(value), "unit": unit, "method": method}


def _json_number(value: Any) -> Any:
    if value is None:
        return None
    try:
        if np.isnan(value):
            return None
    except Exception:
        pass
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value)
    return value


def _first_existing_column(columns: Any, candidates: list[str]) -> Optional[str]:
    column_set = {str(column).lower(): column for column in columns}
    for candidate in candidates:
        if candidate.lower() in column_set:
            return column_set[candidate.lower()]
    return None


def _sample_streetview_images(streetview_dir: Path, limit: int = 60) -> list[Path]:
    folders = sorted([p for p in streetview_dir.iterdir() if p.is_dir()])
    images: list[Path] = []
    for folder in folders:
        preferred = folder / "streetview_erp.jpg"
        if preferred.exists():
            images.append(preferred)
        else:
            images.extend(sorted(p for p in folder.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"})[:1])
    if len(images) <= limit:
        return images
    indices = np.linspace(0, len(images) - 1, limit).astype(int)
    return [images[int(index)] for index in indices]


def _streetview_point_count(points_path: Optional[str]) -> Optional[int]:
    if points_path and HAS_PANDAS:
        try:
            return int(pd.read_csv(points_path).shape[0])
        except Exception:
            return None
    return None


def _mean_cosine_similarity(vectors: list[np.ndarray]) -> float:
    matrix = np.vstack(vectors)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-12
    matrix = matrix / norms
    sims = matrix @ matrix.T
    if len(vectors) <= 1:
        return 1.0
    upper = sims[np.triu_indices(len(vectors), k=1)]
    return float(np.clip(upper.mean(), 0.0, 1.0))


def _traditional_palette_score(rgb: np.ndarray) -> Tuple[float, float, str]:
    palette = {
        "brick_red": np.array([156, 68, 52], dtype=np.float32),
        "blue_gray": np.array([112, 125, 128], dtype=np.float32),
        "warm_white": np.array([229, 219, 196], dtype=np.float32),
        "wood_brown": np.array([116, 80, 48], dtype=np.float32),
    }
    lab = _rgb_to_lab(rgb)
    distances = {name: float(np.linalg.norm(lab - _rgb_to_lab(value))) for name, value in palette.items()}
    nearest, delta_e = min(distances.items(), key=lambda item: item[1])
    score = max(0.0, min(1.0, 1.0 - delta_e / 100.0))
    return score, delta_e, nearest


def _rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    rgb = np.asarray(rgb, dtype=np.float32) / 255.0
    mask = rgb > 0.04045
    rgb = np.where(mask, ((rgb + 0.055) / 1.055) ** 2.4, rgb / 12.92)
    xyz = np.array([
        rgb[0] * 0.4124 + rgb[1] * 0.3576 + rgb[2] * 0.1805,
        rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722,
        rgb[0] * 0.0193 + rgb[1] * 0.1192 + rgb[2] * 0.9505,
    ])
    xyz = xyz / np.array([0.95047, 1.00000, 1.08883])
    epsilon = 0.008856
    kappa = 903.3
    f = np.where(xyz > epsilon, np.cbrt(xyz), (kappa * xyz + 16) / 116)
    return np.array([116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])])


def _rgb_to_hex(rgb: np.ndarray) -> str:
    values = [int(max(0, min(255, round(float(v))))) for v in rgb]
    return "#" + "".join(f"{value:02x}" for value in values)


def _collect_metric_rows(arguments: Dict[str, Any]) -> list[Dict[str, Any]]:
    rows: list[Dict[str, Any]] = []
    for key in ("metric_rows",):
        if isinstance(arguments.get(key), list):
            rows.extend(arguments[key])
    for container_key in ("analysis_data", "capability_results", "results"):
        container = arguments.get(container_key)
        if isinstance(container, dict):
            if isinstance(container.get("metric_rows"), list):
                rows.extend(container["metric_rows"])
            for value in container.values():
                if isinstance(value, dict) and isinstance(value.get("metric_rows"), list):
                    rows.extend(value["metric_rows"])
    return rows


def _write_metric_rows(path: Path, rows: list[Dict[str, Any]]) -> None:
    if not HAS_PANDAS:
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        return
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")


def _plot_gis_overlay(loaded: Dict[str, Any], artifact_dir: Path) -> Tuple[Optional[Path], Optional[Path]]:
    if not loaded:
        return None, None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.lines import Line2D
        from matplotlib.patches import Patch
    except Exception as error:
        logger.warning("matplotlib unavailable for GIS overlay: %s", error)
        return None, None

    target_crs = None
    projected = {}
    for role, gdf in loaded.items():
        projected[role], target_crs = _to_metric_crs(gdf, target_crs=target_crs)

    fig, ax = plt.subplots(figsize=(9, 6), dpi=180)
    if "context_buffer" in projected:
        projected["context_buffer"].boundary.plot(ax=ax, color="#64748b", linewidth=1.0, linestyle="--", alpha=0.85)
    if "context_buildings" in projected:
        projected["context_buildings"].plot(ax=ax, color="#e5e7eb", edgecolor="#cbd5e1", linewidth=0.12, alpha=0.45)
    if "context_function_buildings" in projected:
        projected["context_function_buildings"].plot(ax=ax, color="#c7d2fe", edgecolor="#a5b4fc", linewidth=0.10, alpha=0.30)
    if "context_roads" in projected:
        projected["context_roads"].plot(ax=ax, color="#94a3b8", linewidth=0.35, alpha=0.45)
    if "context_function_poi" in projected:
        projected["context_function_poi"].plot(ax=ax, color="#86efac", markersize=3, alpha=0.35)
    if "buildings" in projected:
        projected["buildings"].plot(ax=ax, color="#d8c7aa", edgecolor="#8a7a63", linewidth=0.25, alpha=0.9)
    if "function_buildings" in projected:
        projected["function_buildings"].plot(ax=ax, column="Function" if "Function" in projected["function_buildings"].columns else None, categorical=True, alpha=0.35, legend=False)
    if "roads" in projected:
        projected["roads"].plot(ax=ax, color="#475569", linewidth=0.55, alpha=0.85)
    if "function_poi" in projected:
        projected["function_poi"].plot(ax=ax, color="#0f766e", markersize=5, alpha=0.65)
    if "boundary" in projected:
        projected["boundary"].boundary.plot(ax=ax, color="#111827", linewidth=1.4)
    if "aoi_metric_summary" in projected:
        projected["aoi_metric_summary"].plot(ax=ax, color="#fde68a", edgecolor="#92400e", linewidth=0.5, alpha=0.18)
        _annotate_metric_summary(ax, projected["aoi_metric_summary"])

    ax.set_aspect("equal")
    ax.set_axis_off()
    ax.set_title("Projected GIS Overlay", fontsize=11, loc="left")
    handles = [
        Line2D([0], [0], color="#64748b", lw=1.2, linestyle="--", label="3x context buffer"),
        Patch(facecolor="#e5e7eb", edgecolor="#cbd5e1", label="Context buildings"),
        Patch(facecolor="#d8c7aa", edgecolor="#8a7a63", label="Building footprints"),
        Line2D([0], [0], color="#475569", lw=1.5, label="Road centerlines"),
        Patch(facecolor="#fde68a", edgecolor="#92400e", alpha=0.35, label="Metric result layer"),
        Line2D([0], [0], color="#111827", lw=1.5, label="AOI boundary"),
    ]
    ax.legend(handles=handles, loc="lower left", frameon=True, fontsize=7)
    _add_scale_bar(ax)
    fig.tight_layout(pad=0.2)
    png_path = artifact_dir / "projected_gis_overlay.png"
    pdf_path = artifact_dir / "projected_gis_overlay.pdf"
    fig.savefig(png_path, bbox_inches="tight")
    fig.savefig(pdf_path, bbox_inches="tight")
    plt.close(fig)
    return png_path, pdf_path


def _annotate_metric_summary(ax: Any, metric_layer: Any) -> None:
    try:
        if len(metric_layer) == 0:
            return
        row = metric_layer.iloc[0]
        manifest = json.loads(row.get("metric_manifest") or "[]")
        lines = []
        for item in manifest[:4]:
            field = item.get("field")
            value = row.get(field)
            if isinstance(value, float):
                value_text = f"{value:.3g}"
            else:
                value_text = str(value)
            unit = item.get("unit") or ""
            lines.append(f"{item.get('metric')}: {value_text} {unit}".strip())
        if not lines:
            return
        point = metric_layer.geometry.representative_point().iloc[0]
        ax.text(
            point.x,
            point.y,
            "\n".join(lines),
            fontsize=6.5,
            color="#111827",
            ha="center",
            va="center",
            bbox={"facecolor": "white", "edgecolor": "#92400e", "alpha": 0.75, "boxstyle": "round,pad=0.25"},
        )
    except Exception:
        return


def _add_scale_bar(ax: Any) -> None:
    try:
        x0, x1 = ax.get_xlim()
        y0, y1 = ax.get_ylim()
        length = _nice_scale_length((x1 - x0) / 5)
        x = x0 + (x1 - x0) * 0.06
        y = y0 + (y1 - y0) * 0.06
        ax.plot([x, x + length], [y, y], color="#111827", linewidth=2)
        ax.text(x + length / 2, y + (y1 - y0) * 0.015, f"{int(length)} m", ha="center", va="bottom", fontsize=7)
    except Exception:
        return


def _nice_scale_length(value: float) -> float:
    if value <= 0:
        return 100.0
    exponent = math.floor(math.log10(value))
    base = value / (10 ** exponent)
    if base < 2:
        nice = 1
    elif base < 5:
        nice = 2
    else:
        nice = 5
    return nice * (10 ** exponent)


def _plot_metric_chart(rows: list[Dict[str, Any]], artifact_dir: Path) -> Optional[Path]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as error:
        logger.warning("matplotlib unavailable for metric chart: %s", error)
        return None
    numeric = [row for row in rows if isinstance(row.get("value"), (int, float)) and row.get("metric")]
    if not numeric:
        return None
    selected = numeric[:12]
    labels = [row["metric"] for row in selected]
    values = [float(row["value"]) for row in selected]
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=180)
    ax.barh(range(len(values)), values, color="#0f766e")
    ax.set_yticks(range(len(values)), labels=labels, fontsize=7)
    ax.invert_yaxis()
    ax.set_title("Computed Urban Metrics", fontsize=11, loc="left")
    ax.grid(axis="x", alpha=0.2)
    fig.tight_layout()
    path = artifact_dir / "urban_metrics_chart.png"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def _build_streetview_grid(streetview_dir: Optional[str], artifact_dir: Path) -> Optional[Path]:
    if not streetview_dir or not HAS_PIL:
        return None
    images = _sample_streetview_images(Path(streetview_dir), limit=12)
    if not images:
        return None
    thumb_w, thumb_h = 180, 120
    cols = 4
    rows = math.ceil(len(images) / cols)
    canvas = Image.new("RGB", (cols * thumb_w, rows * thumb_h), "white")
    for idx, path in enumerate(images):
        try:
            image = Image.open(path).convert("RGB")
            image.thumbnail((thumb_w, thumb_h))
            x = (idx % cols) * thumb_w + (thumb_w - image.width) // 2
            y = (idx // cols) * thumb_h + (thumb_h - image.height) // 2
            canvas.paste(image, (x, y))
        except Exception:
            continue
    out = artifact_dir / "streetview_thumbnail_grid.png"
    canvas.save(out)
    return out


def _artifact(artifact_type: str, title: str, path: Path, mime_type: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "id": path.stem,
        "type": artifact_type,
        "title": title,
        "path": str(path),
        "mime_type": mime_type,
        "metadata": metadata or {},
    }


class GeoDataLoader:
    """地理数据加载器"""
    
    @staticmethod
    def load_shapefile(filepath: str) -> Optional[gpd.GeoDataFrame]:
        """加载Shapefile"""
        if not HAS_GEOPANDAS:
            logger.error("geopandas未安装，无法加载Shapefile")
            return None
        
        try:
            gdf = gpd.read_file(filepath)
            logger.info(f"成功加载Shapefile: {filepath}, 记录数: {len(gdf)}")
            return gdf
        except Exception as e:
            logger.error(f"加载Shapefile失败: {e}")
            return None
    
    @staticmethod
    def load_geojson(filepath: str) -> Optional[Dict]:
        """加载GeoJSON"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data
        except Exception as e:
            logger.error(f"加载GeoJSON失败: {e}")
            return None
    
    @staticmethod
    def load_remote_sensing_image(filepath: str) -> Optional[np.ndarray]:
        """加载遥感影像"""
        if not HAS_RASTERIO:
            # 使用PIL作为备选
            if HAS_PIL:
                try:
                    img = Image.open(filepath)
                    return np.array(img)
                except Exception as e:
                    logger.error(f"PIL加载影像失败: {e}")
                    return None
            return None
        
        try:
            with rasterio.open(filepath) as src:
                image = src.read()
                # 转换为HWC格式
                if image.shape[0] in [1, 3, 4]:  # CHW格式
                    image = reshape_as_image(image)
                logger.info(f"成功加载遥感影像: {filepath}, 形状: {image.shape}")
                return image
        except Exception as e:
            logger.error(f"加载遥感影像失败: {e}")
            return None
    
    @staticmethod
    def load_citybench_remote_sensing(city: str, image_id: str, base_path: str) -> Optional[np.ndarray]:
        """加载CityBench遥感影像"""
        filepath = Path(base_path) / "citydata" / "remote_sensing" / city / f"{image_id}.png"
        if filepath.exists():
            return GeoDataLoader.load_remote_sensing_image(str(filepath))
        return None


class SpatialAnalyzer:
    """空间分析器"""
    
    @staticmethod
    def calculate_area(geometry) -> float:
        """计算面积"""
        if HAS_GEOPANDAS and geometry:
            return geometry.area
        return 0.0
    
    @staticmethod
    def calculate_distance(point1: Tuple[float, float], point2: Tuple[float, float]) -> float:
        """计算两点间距离（米）"""
        import math
        
        lat1, lon1 = point1
        lat2, lon2 = point2
        
        # Haversine公式
        R = 6371000  # 地球半径（米）
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        
        a = math.sin(delta_phi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return R * c
    
    @staticmethod
    def extract_bounding_box(gdf: gpd.GeoDataFrame) -> Dict:
        """提取边界框"""
        if not HAS_GEOPANDAS or gdf is None or gdf.empty:
            return {}
        
        bounds = gdf.total_bounds
        return {
            "min_x": bounds[0],
            "min_y": bounds[1],
            "max_x": bounds[2],
            "max_y": bounds[3],
            "center_x": (bounds[0] + bounds[2]) / 2,
            "center_y": (bounds[1] + bounds[3]) / 2
        }
    
    @staticmethod
    def analyze_road_network(gdf: gpd.GeoDataFrame) -> Dict:
        """分析道路网络"""
        if not HAS_GEOPANDAS or gdf is None:
            return {}
        
        # 计算总长度
        total_length = gdf.geometry.length.sum()
        
        # 道路类型统计
        road_types = {}
        if 'highway' in gdf.columns:
            road_types = gdf['highway'].value_counts().to_dict()
        
        return {
            "road_count": len(gdf),
            "total_length": float(total_length),
            "road_types": road_types,
            "avg_length": float(total_length / len(gdf)) if len(gdf) > 0 else 0
        }
    
    @staticmethod
    def analyze_buildings(gdf: gpd.GeoDataFrame) -> Dict:
        """分析建筑物"""
        if not HAS_GEOPANDAS or gdf is None:
            return {}
        
        # 计算总面积
        total_area = gdf.geometry.area.sum()
        
        # 建筑密度估算
        bounds = SpatialAnalyzer.extract_bounding_box(gdf)
        if bounds:
            bbox_area = (bounds["max_x"] - bounds["min_x"]) * (bounds["max_y"] - bounds["min_y"])
            density = total_area / bbox_area if bbox_area > 0 else 0
        else:
            density = 0
        
        return {
            "building_count": len(gdf),
            "total_area": float(total_area),
            "density": float(density),
            "avg_area": float(total_area / len(gdf)) if len(gdf) > 0 else 0
        }


class CityBenchDataLoader:
    """CityBench数据加载器"""
    
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.cities = ["Beijing", "London", "Paris", "Tokyo", "NewYork", "Mumbai", "Sydney", "Moscow", "Shanghai"]
    
    def load_city_shapefile(self, city: str) -> Optional[gpd.GeoDataFrame]:
        """加载城市Shapefile"""
        filepath = self.base_path / "citydata" / "EXP_ORIG_DATA" / city / f"{city}.shp"
        return GeoDataLoader.load_shapefile(str(filepath))
    
    def load_remote_sensing_dataset(self, city: str = "Paris") -> Dict:
        """加载遥感影像数据集"""
        # 加载标签文件
        label_file = self.base_path / "citydata" / "remote_sensing" / "all_city_img_object_set.json"
        
        if not label_file.exists():
            logger.warning(f"标签文件不存在: {label_file}")
            return {}
        
        try:
            with open(label_file, 'r') as f:
                labels = json.load(f)
            
            # 获取该城市的影像
            image_dir = self.base_path / "citydata" / "remote_sensing" / city
            if not image_dir.exists():
                logger.warning(f"影像目录不存在: {image_dir}")
                return {}
            
            images = list(image_dir.glob("*.png"))
            
            return {
                "city": city,
                "image_count": len(images),
                "labels": labels,
                "image_dir": str(image_dir)
            }
        except Exception as e:
            logger.error(f"加载遥感数据集失败: {e}")
            return {}
    
    def load_exploration_tasks(self, city: str) -> Optional[Any]:
        """加载城市探索任务"""
        if not HAS_PANDAS:
            return None
        
        filepath = self.base_path / "citydata" / "exploration_tasks" / f"case_{city}.csv"
        
        try:
            df = pd.read_csv(filepath)
            logger.info(f"成功加载探索任务: {city}, 任务数: {len(df)}")
            return df
        except Exception as e:
            logger.error(f"加载探索任务失败: {e}")
            return None
    
    def get_sample_task(self, task_type: str, city: str = "Paris") -> Dict:
        """获取示例任务"""
        if task_type == "remote_sensing":
            return self._get_remote_sensing_task(city)
        elif task_type == "urban_exploration":
            return self._get_exploration_task(city)
        else:
            return {}
    
    def _get_remote_sensing_task(self, city: str) -> Dict:
        """获取遥感任务"""
        dataset = self.load_remote_sensing_dataset(city)
        
        if not dataset:
            return {}
        
        # 获取第一张影像
        image_dir = Path(dataset["image_dir"])
        images = list(image_dir.glob("*.png"))
        
        if not images:
            return {}
        
        image_path = images[0]
        image_id = image_path.stem
        
        # 获取标签
        labels = dataset["labels"].get(image_id, {})
        
        return {
            "task_type": "object_detection",
            "image_path": str(image_path),
            "image_id": image_id,
            "ground_truth": labels,
            "city": city
        }
    
    def _get_exploration_task(self, city: str) -> Dict:
        """获取探索任务"""
        df = self.load_exploration_tasks(city)
        
        if df is None or df.empty:
            return {}
        
        # 获取第一个任务
        task = df.iloc[0]
        
        return {
            "task_type": "urban_exploration",
            "city": city,
            "start_location": task.get("start", ""),
            "target_categories": task.get("categories", []),
            "ground_truth": task.to_dict()
        }


class ImageProcessor:
    """图像处理器"""
    
    @staticmethod
    def preprocess_for_vlm(image: np.ndarray, target_size: Tuple[int, int] = (512, 512)) -> np.ndarray:
        """预处理图像用于VLM"""
        if not HAS_PIL:
            return image
        
        try:
            img = Image.fromarray(image)
            img = img.resize(target_size, Image.Resampling.LANCZOS)
            return np.array(img)
        except Exception as e:
            logger.error(f"图像预处理失败: {e}")
            return image
    
    @staticmethod
    def encode_for_api(image: np.ndarray) -> str:
        """编码图像用于API传输"""
        import base64
        from io import BytesIO
        
        try:
            img = Image.fromarray(image)
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            return base64.b64encode(buffered.getvalue()).decode()
        except Exception as e:
            logger.error(f"图像编码失败: {e}")
            return ""
    
    @staticmethod
    def analyze_image_statistics(image: np.ndarray) -> Dict:
        """分析图像统计信息"""
        return {
            "shape": image.shape,
            "dtype": str(image.dtype),
            "min": float(np.min(image)),
            "max": float(np.max(image)),
            "mean": float(np.mean(image)),
            "std": float(np.std(image))
        }


# 工具注册表
GEO_TOOLS = {
    "load_shapefile": GeoDataLoader.load_shapefile,
    "load_geojson": GeoDataLoader.load_geojson,
    "load_remote_sensing": GeoDataLoader.load_remote_sensing_image,
    "calculate_distance": SpatialAnalyzer.calculate_distance,
    "calculate_area": SpatialAnalyzer.calculate_area,
    "analyze_road_network": SpatialAnalyzer.analyze_road_network,
    "analyze_buildings": SpatialAnalyzer.analyze_buildings,
    "preprocess_image": ImageProcessor.preprocess_for_vlm,
    "encode_image": ImageProcessor.encode_for_api
}

