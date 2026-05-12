from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple

try:
    import geopandas as gpd
    from shapely.geometry import box
    HAS_GEOPANDAS = True
except ImportError:  # pragma: no cover - tested through geo_tools skip markers
    gpd = None
    box = None
    HAS_GEOPANDAS = False


def align_loaded_layers_to_aoi(
    loaded: Dict[str, Any],
    *,
    metric_rows: Optional[list[Dict[str, Any]]] = None,
    context_width_factor: float = 3.0,
    context_height_factor: float = 3.0,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Clip AOI analysis layers, preserve context layers, and emit numeric diagnostics."""
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
    context_buffer, context_diag, context_buffer_m = build_aoi_context_buffer(
        boundary,
        width_factor=context_width_factor,
        height_factor=context_height_factor,
        return_metric=True,
    )
    diagnostics["context_buffer"] = context_diag
    if context_buffer is not None and len(context_buffer):
        aligned["context_buffer"] = context_buffer
    aligned["boundary"] = boundary.copy()

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

    any_failure = False
    source_extent_layers = {
        role: source for role, source in loaded.items()
        if role == "source_extent" or role.endswith("_source_extent")
    }

    for role, source in loaded.items():
        if role == "source_extent" or role.endswith("_source_extent"):
            continue
        if role == "boundary":
            diagnostics["layers"][role] = {
                "source_feature_count": int(len(source)),
                "exported_feature_count": int(len(source)),
                "output_clipped_to_aoi": False,
                "geometry_type": geometry_type_summary(source),
            }
            continue

        layer_diag: Dict[str, Any] = {
            "source_feature_count": int(len(source)),
            "source_crs": str(source.crs) if getattr(source, "crs", None) else None,
            "target_crs": str(boundary.crs) if getattr(boundary, "crs", None) else None,
            "geometry_type": geometry_type_summary(source),
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
                if is_point_layer(clipped):
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
                    if is_point_layer(context_clipped):
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
                "source_bounds": bounds_list(working),
                "exported_bounds": bounds_list(clipped),
                "context_exported_bounds": bounds_list(context_clipped) if context_clipped is not None else None,
            })
            extent_layer = source_extent_layers.get(f"{role}_source_extent") or source_extent_layers.get("source_extent")
            _attach_metric_extent_coverage(layer_diag, working, context_diag, context_buffer_m, acquisition_extent=extent_layer)
            aligned[role] = clipped

            if exported_count == 0 and len(working) > 0:
                diagnostics["issues"].append(f"{role}: no source features intersect the AOI boundary; layer may be from a mismatched place or CRS.")
                layer_diag["severity"] = "error"
                any_failure = True
            elif outside_ratio > 0:
                layer_diag["severity"] = "context_only" if outside_ratio > 0.25 else "ok"
                layer_diag["note"] = "Source layer extends beyond AOI; AOI analysis output is clipped and context output is clipped to the AOI-centered buffer."
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

    metric_layer, metric_diag = build_aoi_metric_summary_layer(boundary, metric_rows or [])
    diagnostics["metric_spatialization"] = metric_diag
    if metric_layer is not None and len(metric_layer):
        aligned["aoi_metric_summary"] = metric_layer

    diagnostics["status"] = "failed" if any_failure else "aligned_with_context_buffer"
    return aligned, diagnostics


def build_aoi_context_buffer(
    boundary: Any,
    *,
    width_factor: float = 3.0,
    height_factor: float = 3.0,
    return_metric: bool = False,
):
    """Build an AOI-centered rectangular context buffer with metric diagnostics."""
    diagnostics: Dict[str, Any] = {
        "policy": "aoi_centered_rectangular_context_buffer",
        "width_factor": width_factor,
        "height_factor": height_factor,
        "area_ratio_to_aoi_bbox": None,
        "centered_on_aoi": False,
    }
    if boundary is None or len(boundary) == 0 or not HAS_GEOPANDAS:
        diagnostics["status"] = "unavailable"
        return (None, diagnostics, None) if return_metric else (None, diagnostics)
    try:
        boundary_m, metric_crs = to_metric_crs(boundary)
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
            {"layer_role": ["aoi_context_buffer"], "width_factor": [width_factor], "height_factor": [height_factor], "area_ratio": [width_factor * height_factor]},
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
        return (context, diagnostics, context_m) if return_metric else (context, diagnostics)
    except Exception as error:
        diagnostics.update({"status": "failed", "error": str(error)})
        return (None, diagnostics, None) if return_metric else (None, diagnostics)


def build_aoi_metric_summary_layer(boundary: Any, metric_rows: list[Dict[str, Any]]) -> Tuple[Optional[Any], Dict[str, Any]]:
    diag: Dict[str, Any] = {"status": "not_applicable", "metric_count": 0, "layer": None}
    if boundary is None or len(boundary) == 0 or not metric_rows or not HAS_GEOPANDAS:
        if metric_rows:
            diag.update({"status": "failed", "reason": "boundary unavailable for spatial metric layer", "metric_count": len(metric_rows)})
        return None, diag
    numeric_rows = [row for row in metric_rows if isinstance(row.get("value"), (int, float)) and row.get("metric")]
    if not numeric_rows:
        diag.update({"status": "no_numeric_metrics", "metric_count": len(metric_rows)})
        return None, diag
    try:
        geom = boundary.geometry.unary_union
        fields: Dict[str, Any] = {"layer_role": ["aoi_metric_summary"], "metric_count": [len(numeric_rows)]}
        manifest = []
        used: set[str] = set(fields)
        for row in numeric_rows[:24]:
            field = safe_metric_field_name(str(row.get("metric")), used)
            used.add(field)
            fields[field] = [json_number(row.get("value"))]
            manifest.append({"field": field, "group": row.get("group"), "metric": row.get("metric"), "unit": row.get("unit"), "method": row.get("method")})
        fields["metric_manifest"] = [json.dumps(manifest, ensure_ascii=False)]
        layer = gpd.GeoDataFrame(fields, geometry=[geom], crs=boundary.crs)
        diag.update({"status": "spatialized", "metric_count": len(numeric_rows), "layer": "aoi_metric_summary", "field_count": len(manifest)})
        return layer, diag
    except Exception as error:
        diag.update({"status": "failed", "reason": str(error), "metric_count": len(metric_rows)})
        return None, diag


def to_metric_crs(gdf: Any, target_crs: Any = None) -> Tuple[Any, str]:
    if gdf is None or not HAS_GEOPANDAS:
        return gdf, str(target_crs or "EPSG:3857")
    working = gdf.copy()
    if target_crs is not None:
        if working.crs is None:
            working = working.set_crs(target_crs, allow_override=True)
        elif working.crs != target_crs:
            working = working.to_crs(target_crs)
        return working, str(target_crs)
    if working.crs is None:
        working = working.set_crs("EPSG:4326", allow_override=True)
    try:
        metric_crs = working.estimate_utm_crs()
    except Exception:
        metric_crs = None
    metric_crs = metric_crs or "EPSG:3857"
    return working.to_crs(metric_crs), str(metric_crs)


def geometry_type_summary(gdf: Any) -> Dict[str, int]:
    if gdf is None or len(gdf) == 0:
        return {}
    return {str(key): int(value) for key, value in gdf.geometry.geom_type.value_counts().items()}


def is_point_layer(gdf: Any) -> bool:
    if gdf is None or len(gdf) == 0:
        return False
    geom_types = set(str(value).lower() for value in gdf.geometry.geom_type.dropna().unique())
    return bool(geom_types) and geom_types.issubset({"point", "multipoint"})


def bounds_list(gdf: Any) -> Optional[list[float]]:
    if gdf is None or len(gdf) == 0:
        return None
    try:
        return [float(value) for value in gdf.total_bounds]
    except Exception:
        return None


def safe_metric_field_name(metric: str, used_fields: set[str]) -> str:
    import re

    base = re.sub(r"[^0-9A-Za-z_]+", "_", metric.lower()).strip("_") or "metric"
    if base and base[0].isdigit():
        base = f"m_{base}"
    base = base[:48]
    name = base
    idx = 2
    while name in used_fields:
        suffix = f"_{idx}"
        name = f"{base[:48 - len(suffix)]}{suffix}"
        idx += 1
    return name


def json_number(value: Any) -> Any:
    try:
        if value is None:
            return None
        number = float(value)
        if number != number or number in (float("inf"), float("-inf")):
            return None
        return number
    except Exception:
        return value


def _attach_metric_extent_coverage(
    layer_diag: Dict[str, Any],
    working: Any,
    context_diag: Dict[str, Any],
    context_buffer_m: Any,
    *,
    acquisition_extent: Any = None,
) -> None:
    ctx_width = float(context_diag.get("context_width_m") or 0.0)
    ctx_height = float(context_diag.get("context_height_m") or 0.0)
    metric_crs = context_diag.get("metric_crs")
    if ctx_width <= 0 or ctx_height <= 0 or context_buffer_m is None or not metric_crs:
        return
    try:
        working_m, _ = to_metric_crs(working, target_crs=metric_crs)
        feature_bounds_m = bounds_list(working_m)
        ctx_bounds_m = bounds_list(context_buffer_m)
        if not feature_bounds_m or not ctx_bounds_m:
            return
        feature_w = max(0.0, float(feature_bounds_m[2]) - float(feature_bounds_m[0]))
        feature_h = max(0.0, float(feature_bounds_m[3]) - float(feature_bounds_m[1]))
        src_bounds_m = feature_bounds_m
        extent_basis = "source_feature_bounds"
        if acquisition_extent is not None and len(acquisition_extent):
            extent_m, _ = to_metric_crs(acquisition_extent, target_crs=metric_crs)
            extent_bounds_m = bounds_list(extent_m)
            if extent_bounds_m:
                src_bounds_m = extent_bounds_m
                extent_basis = "source_acquisition_extent"
                layer_diag["acquisition_bounds_metric"] = extent_bounds_m
        src_w = max(0.0, float(src_bounds_m[2]) - float(src_bounds_m[0]))
        src_h = max(0.0, float(src_bounds_m[3]) - float(src_bounds_m[1]))
        layer_diag.update({
            "source_bounds_metric": src_bounds_m,
            "context_bounds_metric": ctx_bounds_m,
            "source_extent_basis": extent_basis,
            "source_extent_width_m": src_w,
            "source_extent_height_m": src_h,
            "source_to_context_width_ratio": round(src_w / ctx_width, 4) if ctx_width else None,
            "source_to_context_height_ratio": round(src_h / ctx_height, 4) if ctx_height else None,
            "feature_bounds_metric": feature_bounds_m,
            "feature_extent_width_m": feature_w,
            "feature_extent_height_m": feature_h,
            "feature_to_context_width_ratio": round(feature_w / ctx_width, 4) if ctx_width else None,
            "feature_to_context_height_ratio": round(feature_h / ctx_height, 4) if ctx_height else None,
        })
    except Exception as error:
        layer_diag["source_context_coverage_error"] = str(error)

