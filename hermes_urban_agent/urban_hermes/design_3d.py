"""Staged LOD1/LOD2/LOD3 urban design generation with local GeoJSON and Blender."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
from shapely.geometry import MultiPolygon, Polygon


DEFAULT_BLENDER_CANDIDATES = (
    r"C:\Program Files\Blender Foundation\Blender 5.0\blender.exe",
    r"C:\Program Files\Blender Foundation\Blender 4.4\blender.exe",
    r"C:\Program Files\Blender Foundation\Blender 4.3\blender.exe",
    r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
)

LOD_LEVELS = ("LOD1", "LOD2", "LOD3")


@dataclass(frozen=True)
class LocalFrame:
    origin: tuple[float, float]
    ux: tuple[float, float]
    uy: tuple[float, float]

    def to_world(self, x: float, y: float) -> tuple[float, float]:
        ox, oy = self.origin
        return (ox + self.ux[0] * x + self.uy[0] * y, oy + self.ux[1] * x + self.uy[1] * y)

    def to_local(self, x: float, y: float) -> tuple[float, float]:
        dx = x - self.origin[0]
        dy = y - self.origin[1]
        return (dx * self.ux[0] + dy * self.ux[1], dx * self.uy[0] + dy * self.uy[1])


def _resolve_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def _largest_polygon(geometry: Any) -> Polygon | None:
    if geometry is None or geometry.is_empty:
        return None
    if isinstance(geometry, Polygon):
        return geometry
    if isinstance(geometry, MultiPolygon):
        parts = [part for part in geometry.geoms if not part.is_empty]
        return max(parts, key=lambda part: part.area) if parts else None
    if hasattr(geometry, "geoms"):
        polygons = [_largest_polygon(part) for part in geometry.geoms]
        polygons = [part for part in polygons if part is not None]
        return max(polygons, key=lambda part: part.area) if polygons else None
    return None


def _safe_crs(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if gdf.crs is None:
        return gdf.set_crs("EPSG:4326")
    return gdf


def _estimate_metric_crs(gdf: gpd.GeoDataFrame) -> Any:
    try:
        crs = gdf.estimate_utm_crs()
        if crs is not None:
            return crs
    except Exception:
        pass
    return "EPSG:3857"


def _find_blender(explicit: str | None = None) -> str | None:
    if explicit:
        path = Path(explicit)
        if path.exists():
            return str(path)
    command = shutil.which("blender")
    if command:
        return command
    for candidate in DEFAULT_BLENDER_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None


def _normalize_lod_level(value: str | None) -> str:
    text = str(value or "LOD2").strip().upper().replace("LD", "LOD")
    if text not in LOD_LEVELS:
        raise ValueError(f"unsupported lod_level={value!r}; expected one of {', '.join(LOD_LEVELS)}")
    return text


def _lod_features(lod_level: str) -> list[str]:
    features = [
        "selected local parcel or grid cell",
        "existing buildings intersecting the selected parcel exported as cleared audit layer",
        "coarse extruded building massing with height and floor metadata",
    ]
    if lod_level in {"LOD2", "LOD3"}:
        features.extend(
            [
                "explicit roof type per building",
                "stepped/gable/green-flat roof geometry",
                "public-realm polygons for plaza, green spine, and shared street",
                "context buildings retained outside cleared parcel",
            ]
        )
    if lod_level == "LOD3":
        features.extend(
            [
                "procedural facade openings and entrance markers",
                "residential balcony slabs where applicable",
                "roof equipment and parapet/detail markers",
                "building-level program semantics carried in GeoJSON and Blender object names",
            ]
        )
    return features


def _select_parcel(
    parcels: gpd.GeoDataFrame,
    *,
    parcel_id: str | None,
    parcel_id_field: str,
    metrics_path: Path | None,
) -> tuple[gpd.GeoSeries, dict[str, Any], str]:
    if parcel_id:
        if parcel_id_field not in parcels.columns:
            raise ValueError(f"parcel_id_field not found in parcels: {parcel_id_field}")
        matches = parcels[parcels[parcel_id_field].astype(str) == str(parcel_id)]
        if matches.empty:
            raise ValueError(f"parcel_id not found: {parcel_id}")
        row = matches.iloc[0]
        return row, dict(row.drop(labels=["geometry"], errors="ignore")), str(parcel_id)

    if metrics_path and metrics_path.exists():
        metrics = _safe_crs(gpd.read_file(metrics_path))
        if parcel_id_field not in metrics.columns:
            raise ValueError(f"parcel_id_field not found in metrics: {parcel_id_field}")
        score = []
        for _, row in metrics.iterrows():
            count = float(row.get("cmab_building_count") or 0)
            coverage = float(row.get("cmab_building_coverage_ratio") or 0)
            vitality = float(row.get("lbs_vitality_index_log_stays") or 0)
            pois = float(row.get("osm_poi_count") or 0)
            score.append(count + coverage * 180.0 + vitality * 6.0 + min(pois, 80.0) * 0.25)
        metrics = metrics.assign(_design_score=score).sort_values("_design_score", ascending=False)
        for _, metric_row in metrics.iterrows():
            candidate_id = str(metric_row[parcel_id_field])
            matches = parcels[parcels[parcel_id_field].astype(str) == candidate_id]
            if not matches.empty:
                props = dict(metric_row.drop(labels=["geometry"], errors="ignore"))
                return matches.iloc[0], props, candidate_id

    areas = parcels.geometry.area
    idx = areas.sort_values(ascending=False).index[0]
    row = parcels.loc[idx]
    chosen_id = str(row.get(parcel_id_field) or row.get("id") or idx)
    return row, dict(row.drop(labels=["geometry"], errors="ignore")), chosen_id


def _frame_from_polygon(polygon: Polygon) -> LocalFrame:
    rect = _largest_polygon(polygon.minimum_rotated_rectangle)
    if rect is None:
        raise ValueError("could not derive oriented frame from parcel")
    coords = list(rect.exterior.coords)[:4]
    edges = []
    for i in range(4):
        x0, y0 = coords[i]
        x1, y1 = coords[(i + 1) % 4]
        dx = x1 - x0
        dy = y1 - y0
        edges.append((math.hypot(dx, dy), dx, dy))
    _, dx, dy = max(edges, key=lambda item: item[0])
    length = math.hypot(dx, dy) or 1.0
    ux = (dx / length, dy / length)
    uy = (-ux[1], ux[0])
    centroid = polygon.centroid
    return LocalFrame((centroid.x, centroid.y), ux, uy)


def _local_bounds(polygon: Polygon, frame: LocalFrame) -> tuple[float, float, float, float]:
    points = [frame.to_local(x, y) for x, y in polygon.exterior.coords]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def _local_box(frame: LocalFrame, cx: float, cy: float, width: float, depth: float) -> Polygon:
    half_w = width / 2.0
    half_d = depth / 2.0
    points = [
        frame.to_world(cx - half_w, cy - half_d),
        frame.to_world(cx + half_w, cy - half_d),
        frame.to_world(cx + half_w, cy + half_d),
        frame.to_world(cx - half_w, cy + half_d),
    ]
    return Polygon(points)


def _clip_polygon(geometry: Any, mask: Polygon, *, min_area: float = 80.0) -> Polygon | None:
    clipped = geometry.intersection(mask)
    polygon = _largest_polygon(clipped)
    if polygon is None or polygon.area < min_area:
        return None
    return polygon.buffer(0)


def _polygon_local_xy(polygon: Polygon, frame: LocalFrame, *, simplify_m: float = 0.75) -> list[list[float]]:
    if simplify_m > 0:
        polygon = polygon.simplify(simplify_m, preserve_topology=True)
    exterior = list(polygon.exterior.coords)
    if len(exterior) > 1 and exterior[0] == exterior[-1]:
        exterior = exterior[:-1]
    return [[round(x, 3), round(y, 3)] for x, y in (frame.to_local(px, py) for px, py in exterior)]


def _make_design_geometries(parcel: Polygon, frame: LocalFrame, *, lod_level: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    minx, miny, maxx, maxy = _local_bounds(parcel, frame)
    width = maxx - minx
    depth = maxy - miny
    setback = max(14.0, min(width, depth) * 0.035)
    buildable = _largest_polygon(parcel.buffer(-setback)) or parcel

    specs = [
        ("B01", "mixed-use northern podium", "mixed_use_podium", 22.0, 5, "flat_green", 0.00, 0.33, 0.58, 0.14),
        ("B02", "residential slab west", "residential", 54.0, 15, "gable", -0.29, 0.02, 0.13, 0.45),
        ("B03", "residential slab east", "residential", 48.0, 13, "gable", 0.30, -0.03, 0.13, 0.38),
        ("B04", "innovation tower", "office_research", 96.0, 26, "stepped", -0.10, 0.05, 0.17, 0.17),
        ("B05", "community pavilion", "civic_cultural", 15.0, 3, "gable", 0.06, -0.31, 0.30, 0.13),
        ("B06", "southern active edge", "retail_podium", 18.0, 4, "flat_green", -0.08, -0.43, 0.48, 0.10),
    ]

    buildings: list[dict[str, Any]] = []
    for design_id, name, program, height, floors, roof_type, rx, ry, rw, rd in specs:
        geom = _local_box(frame, rx * width, ry * depth, rw * width, rd * depth)
        clipped = _clip_polygon(geom, buildable)
        if clipped is None:
            continue
        effective_roof_type = "flat" if lod_level == "LOD1" else roof_type
        buildings.append(
            {
                "design_id": design_id,
                "name": name,
                "program": program,
                "height_m": height,
                "floors": floors,
                "roof_type": effective_roof_type,
                "lod": lod_level,
                "geometry": clipped,
            }
        )

    if lod_level == "LOD1":
        return buildings, []

    realm_specs = [
        ("P01", "central civic plaza", "plaza", 0.00, -0.04, 0.24, 0.22),
        ("P02", "north-south pedestrian spine", "green_spine", 0.00, -0.08, 0.075, 0.74),
        ("P03", "east-west slow street", "shared_street", 0.00, 0.17, 0.72, 0.060),
    ]
    public_realm: list[dict[str, Any]] = []
    for realm_id, name, kind, rx, ry, rw, rd in realm_specs:
        geom = _local_box(frame, rx * width, ry * depth, rw * width, rd * depth)
        clipped = _clip_polygon(geom, parcel.buffer(-4.0), min_area=50.0)
        if clipped is None:
            continue
        public_realm.append({"realm_id": realm_id, "name": name, "kind": kind, "geometry": clipped})

    return buildings, public_realm


def _feature_collection_from_records(records: list[dict[str, Any]], crs: Any) -> gpd.GeoDataFrame:
    rows = []
    for record in records:
        item = {key: value for key, value in record.items() if key != "geometry"}
        item["geometry"] = record["geometry"]
        rows.append(item)
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=crs)


def _write_geojson(gdf: gpd.GeoDataFrame, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(path, driver="GeoJSON")
    return str(path)


def _context_buildings(
    buildings_path: Path,
    parcel_proj: Polygon,
    frame: LocalFrame,
    metric_crs: Any,
    *,
    context_buffer_m: float,
    max_context_buildings: int,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, list[dict[str, Any]]]:
    buffered_proj = parcel_proj.buffer(context_buffer_m)
    bbox_gdf = gpd.GeoDataFrame([{"geometry": buffered_proj}], crs=metric_crs).to_crs("EPSG:4326")
    minx, miny, maxx, maxy = bbox_gdf.geometry.iloc[0].bounds
    buildings = _safe_crs(gpd.read_file(buildings_path, bbox=(minx, miny, maxx, maxy)))
    if buildings.empty:
        empty = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
        return empty, empty, []

    buildings_proj = buildings.to_crs(metric_crs)
    inside_mask = buildings_proj.geometry.intersects(parcel_proj)
    removed = buildings_proj.loc[inside_mask].copy()
    context = buildings_proj.loc[~inside_mask & buildings_proj.geometry.intersects(buffered_proj)].copy()
    if not context.empty:
        center = parcel_proj.centroid
        context["_dist"] = context.geometry.centroid.distance(center)
        context = context.sort_values("_dist").head(max_context_buildings).drop(columns=["_dist"], errors="ignore")

    payload_context: list[dict[str, Any]] = []
    for idx, row in context.iterrows():
        polygon = _largest_polygon(row.geometry)
        if polygon is None or polygon.area < 25:
            continue
        local_xy = _polygon_local_xy(polygon, frame, simplify_m=1.5)
        if len(local_xy) < 3:
            continue
        height = row.get("Height", row.get("height", 18.0))
        try:
            height_m = float(height)
        except Exception:
            height_m = 18.0
        payload_context.append(
            {
                "id": str(row.get("merged_id", idx)),
                "height_m": max(6.0, min(height_m, 120.0)),
                "footprint_xy": local_xy,
            }
        )

    return removed.to_crs("EPSG:4326"), context.to_crs("EPSG:4326"), payload_context


def _payload_polygon(geometry: Polygon, frame: LocalFrame, *, simplify_m: float = 1.0) -> list[list[float]]:
    return _polygon_local_xy(geometry, frame, simplify_m=simplify_m)


def _color_for_program(program: str) -> list[float]:
    palette = {
        "mixed_use_podium": [0.62, 0.55, 0.47, 1.0],
        "residential": [0.86, 0.72, 0.52, 1.0],
        "office_research": [0.46, 0.62, 0.76, 1.0],
        "civic_cultural": [0.78, 0.45, 0.34, 1.0],
        "retail_podium": [0.58, 0.50, 0.42, 1.0],
    }
    return palette.get(program, [0.70, 0.67, 0.60, 1.0])


def _write_blender_runner(path: Path) -> None:
    path.write_text(BLENDER_RUNNER, encoding="utf-8")


def generate_urban_design_3d(
    *,
    parcels_geojson_path: str | Path,
    buildings_geojson_path: str | Path,
    output_dir: str | Path,
    lod_level: str = "LOD2",
    metrics_geojson_path: str | Path | None = None,
    parcel_id: str | None = None,
    parcel_id_field: str = "grid_id",
    blender_executable: str | None = None,
    context_buffer_m: float = 180.0,
    max_context_buildings: int = 220,
    run_blender: bool = True,
) -> dict[str, Any]:
    lod_level = _normalize_lod_level(lod_level)
    lod_token = lod_level.lower()
    parcels_path = _resolve_path(parcels_geojson_path)
    buildings_path = _resolve_path(buildings_geojson_path)
    metrics_path = _resolve_path(metrics_geojson_path) if metrics_geojson_path else None
    out_dir = _resolve_path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    parcels = _safe_crs(gpd.read_file(parcels_path))
    row, selection_metrics, selected_id = _select_parcel(
        parcels,
        parcel_id=parcel_id,
        parcel_id_field=parcel_id_field,
        metrics_path=metrics_path,
    )
    selected_wgs = _largest_polygon(gpd.GeoSeries([row.geometry], crs=parcels.crs).to_crs("EPSG:4326").iloc[0])
    if selected_wgs is None:
        raise ValueError("selected parcel has no polygon geometry")

    selected_gdf = gpd.GeoDataFrame([{parcel_id_field: selected_id, **selection_metrics, "geometry": selected_wgs}], crs="EPSG:4326")
    metric_crs = _estimate_metric_crs(selected_gdf)
    selected_proj = _largest_polygon(selected_gdf.to_crs(metric_crs).geometry.iloc[0])
    if selected_proj is None:
        raise ValueError("selected parcel could not be projected")
    selected_proj = selected_proj.buffer(0)
    frame = _frame_from_polygon(selected_proj)

    design_records, realm_records = _make_design_geometries(selected_proj, frame, lod_level=lod_level)
    if not design_records:
        raise ValueError("design generator produced no buildings inside the selected parcel")

    design_gdf = _feature_collection_from_records(design_records, metric_crs).to_crs("EPSG:4326")
    realm_gdf = _feature_collection_from_records(realm_records, metric_crs).to_crs("EPSG:4326") if realm_records else gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    removed_wgs, context_wgs, context_payload = _context_buildings(
        buildings_path,
        selected_proj,
        frame,
        metric_crs,
        context_buffer_m=context_buffer_m,
        max_context_buildings=max_context_buildings,
    )

    selected_parcel_path = out_dir / "selected_parcel.geojson"
    design_buildings_path = out_dir / f"design_buildings_{lod_token}.geojson"
    public_realm_path = out_dir / "design_public_realm.geojson"
    removed_path = out_dir / "cleared_existing_buildings.geojson"
    context_path = out_dir / "context_buildings_after_clear.geojson"

    _write_geojson(selected_gdf, selected_parcel_path)
    _write_geojson(design_gdf, design_buildings_path)
    _write_geojson(realm_gdf, public_realm_path)
    _write_geojson(removed_wgs, removed_path)
    _write_geojson(context_wgs, context_path)

    design_payload = []
    for record in design_records:
        polygon = _largest_polygon(record["geometry"])
        if polygon is None:
            continue
        design_payload.append(
            {
                "design_id": record["design_id"],
                "name": record["name"],
                "program": record["program"],
                "height_m": record["height_m"],
                "floors": record["floors"],
                "roof_type": record["roof_type"],
                "lod": record["lod"],
                "color": _color_for_program(record["program"]),
                "footprint_xy": _payload_polygon(polygon, frame, simplify_m=0.5),
            }
        )

    realm_payload = []
    for record in realm_records:
        polygon = _largest_polygon(record["geometry"])
        if polygon is None:
            continue
        realm_payload.append(
            {
                "realm_id": record["realm_id"],
                "name": record["name"],
                "kind": record["kind"],
                "footprint_xy": _payload_polygon(polygon, frame, simplify_m=0.5),
            }
        )

    parcel_boundary = _payload_polygon(selected_proj, frame, simplify_m=2.0)
    local_points = parcel_boundary + [point for item in design_payload for point in item["footprint_xy"]]
    xs = [point[0] for point in local_points]
    ys = [point[1] for point in local_points]

    payload = {
        "schema": "urban_hermes.staged_lod_blender_payload.v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "lod_level": lod_level,
        "selected_parcel_id": selected_id,
        "parcel_id_field": parcel_id_field,
        "source_layers": {
            "parcels_geojson": str(parcels_path),
            "buildings_geojson": str(buildings_path),
            "metrics_geojson": str(metrics_path) if metrics_path else None,
        },
        "selection_metrics": {key: _jsonable(value) for key, value in selection_metrics.items() if key != "geometry"},
        "clearing": {
            "removed_building_count": int(len(removed_wgs)),
            "context_building_count": int(len(context_wgs)),
            "rule": "Existing building footprints intersecting the selected parcel are omitted from the 3D scene and exported as cleared_existing_buildings.geojson.",
        },
        "design_summary": {
            "new_building_count": len(design_payload),
            "public_realm_count": len(realm_payload),
            "total_new_floor_area_proxy_m2": round(sum(_largest_polygon(item["geometry"]).area * float(item["floors"]) for item in design_records if _largest_polygon(item["geometry"]) is not None), 2),
            "lod_features": _lod_features(lod_level),
        },
        "model_bounds_xy": [min(xs), min(ys), max(xs), max(ys)],
        "parcel_boundary_xy": parcel_boundary,
        "design_buildings": design_payload,
        "public_realm": realm_payload,
        "context_buildings": context_payload,
    }

    payload_path = out_dir / "blender_scene_payload.json"
    payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    blender_script_path = out_dir / f"render_{lod_token}_urban_design_blender.py"
    _write_blender_runner(blender_script_path)

    blender_result: dict[str, Any] = {"status": "skipped", "reason": "run_blender is false"}
    blend_path = out_dir / f"urban_design_{lod_token}.blend"
    glb_path = out_dir / f"urban_design_{lod_token}.glb"
    obj_path = out_dir / f"urban_design_{lod_token}.obj"
    preview_path = out_dir / f"urban_design_{lod_token}_preview.png"
    blender_path = _find_blender(blender_executable)
    if run_blender:
        if not blender_path:
            blender_result = {"status": "skipped", "reason": "Blender executable not found"}
        else:
            cmd = [blender_path, "-b", "--python", str(blender_script_path), "--", str(payload_path), str(out_dir)]
            started = datetime.now()
            proc = subprocess.run(cmd, cwd=str(out_dir), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=420)
            blender_result = {
                "status": "ok" if proc.returncode == 0 else "failed",
                "command": cmd,
                "returncode": proc.returncode,
                "started_at": started.isoformat(timespec="seconds"),
                "stdout_tail": proc.stdout[-8000:],
                "stderr_tail": proc.stderr[-8000:],
            }
            if proc.returncode != 0:
                raise RuntimeError(f"Blender generation failed with code {proc.returncode}: {proc.stderr[-1200:]}")

    manifest = {
        "success": True,
        "tool": "urban_generate_3d_design",
        "lod_level": lod_level,
        "selected_parcel_id": selected_id,
        "output_dir": str(out_dir),
        "outputs": {
            "selected_parcel_geojson": str(selected_parcel_path),
            "cleared_existing_buildings_geojson": str(removed_path),
            "context_buildings_after_clear_geojson": str(context_path),
            "design_buildings_geojson": str(design_buildings_path),
            f"design_buildings_{lod_token}_geojson": str(design_buildings_path),
            "design_public_realm_geojson": str(public_realm_path),
            "blender_payload_json": str(payload_path),
            "blender_script": str(blender_script_path),
            "blend": str(blend_path) if blend_path.exists() else None,
            "glb": str(glb_path) if glb_path.exists() else None,
            "obj": str(obj_path) if obj_path.exists() else None,
            "preview_png": str(preview_path) if preview_path.exists() else None,
        },
        "clearing": payload["clearing"],
        "design_summary": payload["design_summary"],
        "blender": blender_result,
    }
    manifest_path = out_dir / f"urban_design_{lod_token}_manifest.json"
    manifest["outputs"]["manifest_json"] = str(manifest_path)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return manifest


def _jsonable(value: Any) -> Any:
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


BLENDER_RUNNER = r'''
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def reset_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def make_mat(name, color, roughness=0.62):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
    return mat


def mesh_obj(name, verts, faces, mat):
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    if mat:
        obj.data.materials.append(mat)
    return obj


def extrude_flat(name, footprint, height, mat):
    n = len(footprint)
    verts = [(x, y, 0.0) for x, y in footprint] + [(x, y, height) for x, y in footprint]
    faces = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
    for i in range(n):
        faces.append((i, (i + 1) % n, n + (i + 1) % n, n + i))
    return mesh_obj(name, verts, faces, mat)


def extrude_gable(name, footprint, height, mat, roof_mat):
    if len(footprint) != 4:
        return extrude_flat(name, footprint, height, mat)
    roof_h = max(3.0, min(height * 0.16, 9.0))
    eave_h = max(2.8, height - roof_h)
    p = [(x, y, 0.0) for x, y in footprint]
    top = [(x, y, eave_h) for x, y in footprint]
    edge01 = math.dist(footprint[0], footprint[1])
    edge12 = math.dist(footprint[1], footprint[2])
    if edge01 >= edge12:
        r0 = ((footprint[0][0] + footprint[3][0]) / 2, (footprint[0][1] + footprint[3][1]) / 2, height)
        r1 = ((footprint[1][0] + footprint[2][0]) / 2, (footprint[1][1] + footprint[2][1]) / 2, height)
        verts = p + top + [r0, r1]
        wall_faces = [(0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
        roof_faces = [(4, 5, 9, 8), (7, 8, 9, 6), (4, 8, 7), (5, 6, 9)]
    else:
        r0 = ((footprint[0][0] + footprint[1][0]) / 2, (footprint[0][1] + footprint[1][1]) / 2, height)
        r1 = ((footprint[3][0] + footprint[2][0]) / 2, (footprint[3][1] + footprint[2][1]) / 2, height)
        verts = p + top + [r0, r1]
        wall_faces = [(0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
        roof_faces = [(4, 8, 9, 7), (5, 6, 9, 8), (4, 5, 8), (7, 9, 6)]
    body = mesh_obj(name + "_walls", verts, [tuple(range(3, -1, -1)), *wall_faces], mat)
    roof = mesh_obj(name + "_gable_roof", verts, roof_faces, roof_mat)
    return body


def scale_footprint(footprint, factor):
    cx = sum(x for x, _ in footprint) / len(footprint)
    cy = sum(y for _, y in footprint) / len(footprint)
    return [(cx + (x - cx) * factor, cy + (y - cy) * factor) for x, y in footprint]


def extrude_stepped(name, footprint, height, mat, roof_mat):
    base_h = height * 0.70
    extrude_flat(name + "_podium", footprint, base_h, mat)
    top = scale_footprint(footprint, 0.58)
    upper = extrude_flat(name + "_setback_tower", top, height, mat)
    cap = scale_footprint(top, 0.72)
    cap_obj = extrude_flat(name + "_roof_cap", cap, height + min(5.0, height * 0.05), roof_mat)
    return upper


def add_plane_polygon(name, footprint, z, mat):
    verts = [(x, y, z) for x, y in footprint]
    faces = [tuple(range(len(verts)))]
    return mesh_obj(name, verts, faces, mat)


def add_tree(x, y, height, trunk_mat, canopy_mat):
    bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=0.7, depth=height * 0.35, location=(x, y, height * 0.18))
    trunk = bpy.context.object
    trunk.name = "tree_trunk"
    trunk.data.materials.append(trunk_mat)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=height * 0.18, location=(x, y, height * 0.48))
    canopy = bpy.context.object
    canopy.name = "tree_canopy"
    canopy.scale.z = 1.25
    canopy.data.materials.append(canopy_mat)


def polygon_signed_area(footprint):
    area = 0.0
    for i, (x0, y0) in enumerate(footprint):
        x1, y1 = footprint[(i + 1) % len(footprint)]
        area += x0 * y1 - x1 * y0
    return area / 2.0


def oriented_box(name, cx, cy, cz, length, depth, height, ux, uy, mat):
    hx = length / 2
    hy = depth / 2
    hz = height / 2
    verts = []
    for sx, sy, sz in [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1), (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]:
        x = cx + ux[0] * hx * sx + uy[0] * hy * sy
        y = cy + ux[1] * hx * sx + uy[1] * hy * sy
        z = cz + hz * sz
        verts.append((x, y, z))
    faces = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    return mesh_obj(name, verts, faces, mat)


def add_lod3_details(item, footprint, height, glass_mat, door_mat, balcony_mat, equipment_mat):
    if len(footprint) < 4:
        return
    signed_area = polygon_signed_area(footprint)
    floors = max(1, int(item.get("floors") or max(1, height // 3.6)))
    detail_rows = min(max(floors, 2), 12)
    program = item.get("program", "")
    design_id = item.get("design_id", "building")

    edges = []
    for i, (x0, y0) in enumerate(footprint):
        x1, y1 = footprint[(i + 1) % len(footprint)]
        dx = x1 - x0
        dy = y1 - y0
        length = math.hypot(dx, dy)
        if length < 12:
            continue
        ux = (dx / length, dy / length)
        outward = (dy / length, -dx / length) if signed_area >= 0 else (-dy / length, dx / length)
        mx = (x0 + x1) / 2
        my = (y0 + y1) / 2
        edges.append({"start": (x0, y0), "length": length, "ux": ux, "out": outward, "mid": (mx, my)})

    for edge_index, edge in enumerate(edges):
        bays = min(max(int(edge["length"] // 12), 2), 9)
        window_width = min(3.4, edge["length"] / (bays * 2.2))
        for bay in range(bays):
            t = (bay + 1) / (bays + 1)
            base_x = edge["start"][0] + edge["ux"][0] * edge["length"] * t
            base_y = edge["start"][1] + edge["ux"][1] * edge["length"] * t
            for row in range(1, detail_rows):
                z = 2.7 + row * max(3.1, (height - 4.0) / max(detail_rows, 1))
                if z > height - 1.8:
                    continue
                cx = base_x + edge["out"][0] * 0.22
                cy = base_y + edge["out"][1] * 0.22
                oriented_box(f"{design_id}_window_{edge_index}_{bay}_{row}", cx, cy, z, window_width, 0.18, 1.7, edge["ux"], edge["out"], glass_mat)
                if program == "residential" and edge_index % 2 == 0 and row % 3 == 0:
                    bx = base_x + edge["out"][0] * 1.15
                    by = base_y + edge["out"][1] * 1.15
                    oriented_box(f"{design_id}_balcony_{edge_index}_{bay}_{row}", bx, by, z - 1.0, window_width * 1.35, 1.7, 0.22, edge["ux"], edge["out"], balcony_mat)

    front = min(edges, key=lambda edge: edge["mid"][1], default=None)
    if front:
        cx = front["mid"][0] + front["out"][0] * 0.32
        cy = front["mid"][1] + front["out"][1] * 0.32
        oriented_box(f"{design_id}_main_entrance", cx, cy, 1.65, min(7.0, front["length"] * 0.18), 0.32, 3.3, front["ux"], front["out"], door_mat)

    cx = sum(x for x, _ in footprint) / len(footprint)
    cy = sum(y for _, y in footprint) / len(footprint)
    oriented_box(f"{design_id}_roof_equipment", cx, cy, height + 1.4, 6.0, 4.0, 2.8, (1, 0), (0, 1), equipment_mat)


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def main():
    payload_path = Path(sys.argv[sys.argv.index("--") + 1])
    out_dir = Path(sys.argv[sys.argv.index("--") + 2])
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    lod_level = payload.get("lod_level", "LOD2")
    lod_token = lod_level.lower()
    reset_scene()

    mat_context = make_mat("context existing buildings retained", (0.50, 0.53, 0.55, 1))
    mat_roof = make_mat("warm roof material", (0.55, 0.19, 0.12, 1))
    mat_green_roof = make_mat("green roof and landscape", (0.25, 0.46, 0.28, 1))
    mat_ground = make_mat("parcel ground", (0.38, 0.43, 0.37, 1))
    mat_plaza = make_mat("civic plaza paving", (0.70, 0.68, 0.61, 1))
    mat_shared = make_mat("shared street paving", (0.48, 0.49, 0.47, 1))
    mat_spine = make_mat("linear green spine", (0.21, 0.48, 0.30, 1))
    mat_trunk = make_mat("tree trunks", (0.28, 0.17, 0.09, 1))
    mat_canopy = make_mat("tree canopies", (0.18, 0.42, 0.22, 1))
    mat_glass = make_mat("lod3 blue glass openings", (0.30, 0.55, 0.72, 1), 0.28)
    mat_door = make_mat("lod3 entry markers", (0.18, 0.12, 0.08, 1))
    mat_balcony = make_mat("lod3 balcony slabs", (0.74, 0.73, 0.68, 1))
    mat_equipment = make_mat("lod3 roof equipment", (0.42, 0.43, 0.40, 1))

    material_cache = {}
    for item in payload["design_buildings"]:
        color = tuple(item.get("color") or [0.72, 0.68, 0.58, 1.0])
        material_cache[item["program"]] = make_mat(item["program"], color)

    add_plane_polygon("selected parcel cleared ground", payload["parcel_boundary_xy"], -0.05, mat_ground)

    for context in payload.get("context_buildings", []):
        footprint = context.get("footprint_xy") or []
        if len(footprint) >= 3:
            extrude_flat("context_" + str(context.get("id", "building")), footprint, float(context.get("height_m") or 18), mat_context)

    for realm in payload.get("public_realm", []):
        footprint = realm.get("footprint_xy") or []
        if len(footprint) < 3:
            continue
        kind = realm.get("kind")
        mat = mat_spine if kind == "green_spine" else mat_shared if kind == "shared_street" else mat_plaza
        add_plane_polygon(realm.get("name", "public realm"), footprint, 0.03, mat)

    for item in payload["design_buildings"]:
        footprint = item["footprint_xy"]
        name = item["design_id"] + "_" + item["program"]
        height = float(item["height_m"])
        mat = material_cache[item["program"]]
        roof_type = item.get("roof_type", "flat")
        if lod_level == "LOD1":
            extrude_flat(name, footprint, height, mat)
        elif roof_type == "gable":
            extrude_gable(name, footprint, height, mat, mat_roof)
        elif roof_type == "stepped":
            extrude_stepped(name, footprint, height, mat, mat_roof)
        else:
            extrude_flat(name, footprint, height, mat)
            roof = add_plane_polygon(name + "_green_roof", scale_footprint(footprint, 0.88), height + 0.08, mat_green_roof)
        if lod_level == "LOD3":
            add_lod3_details(item, footprint, height, mat_glass, mat_door, mat_balcony, mat_equipment)

    minx, miny, maxx, maxy = payload["model_bounds_xy"]
    span = max(maxx - minx, maxy - miny)
    if lod_level in {"LOD2", "LOD3"}:
        for i in range(18):
            t = (i + 1) / 19
            x = minx * (1 - t) + maxx * t
            y = miny * 0.72
            add_tree(x, y, max(8.0, span * 0.025), mat_trunk, mat_canopy)

    bpy.ops.object.light_add(type="SUN", location=(0, 0, span))
    sun = bpy.context.object
    sun.name = "design review sun"
    sun.data.energy = 2.7
    sun.rotation_euler = (math.radians(48), 0, math.radians(35))

    center_x = (minx + maxx) / 2
    center_y = (miny + maxy) / 2
    bpy.ops.object.camera_add(location=(center_x + span * 0.58, center_y - span * 0.72, span * 1.05))
    camera = bpy.context.object
    look_at(camera, (center_x, center_y, 18))
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = span * 0.95
    bpy.context.scene.camera = camera

    engines = {item.identifier for item in bpy.context.scene.render.bl_rna.properties["engine"].enum_items}
    bpy.context.scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"
    bpy.context.scene.render.resolution_x = 1800
    bpy.context.scene.render.resolution_y = 1200
    bpy.context.scene.world.color = (0.78, 0.86, 0.93)
    bpy.context.scene.view_settings.view_transform = "Filmic"
    bpy.context.scene.view_settings.look = "Medium High Contrast"

    bpy.ops.wm.save_as_mainfile(filepath=str(out_dir / f"urban_design_{lod_token}.blend"))
    bpy.ops.export_scene.gltf(filepath=str(out_dir / f"urban_design_{lod_token}.glb"), export_format="GLB", export_apply=True)
    try:
        bpy.ops.wm.obj_export(filepath=str(out_dir / f"urban_design_{lod_token}.obj"), export_materials=True)
    except Exception:
        pass
    bpy.context.scene.render.filepath = str(out_dir / f"urban_design_{lod_token}_preview.png")
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
'''


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a staged LOD1/LOD2/LOD3 urban design with Blender.")
    parser.add_argument("--parcels", required=True, help="Parcel or grid GeoJSON path.")
    parser.add_argument("--buildings", required=True, help="Existing building GeoJSON path.")
    parser.add_argument("--output-dir", required=True, help="Output directory.")
    parser.add_argument("--lod-level", choices=LOD_LEVELS, default="LOD2", help="LOD1 coarse massing, LOD2 roof/public realm, or LOD3 facade/detail generation.")
    parser.add_argument("--metrics", help="Optional metric GeoJSON used for auto parcel selection.")
    parser.add_argument("--parcel-id", help="Optional parcel id. If omitted, the generator selects a dense parcel.")
    parser.add_argument("--parcel-id-field", default="grid_id")
    parser.add_argument("--blender", help="Optional Blender executable path.")
    parser.add_argument("--no-blender", action="store_true", help="Only write GeoJSON and Blender payload.")
    parser.add_argument("--context-buffer-m", type=float, default=180.0)
    parser.add_argument("--max-context-buildings", type=int, default=220)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    manifest = generate_urban_design_3d(
        parcels_geojson_path=args.parcels,
        buildings_geojson_path=args.buildings,
        output_dir=args.output_dir,
        lod_level=args.lod_level,
        metrics_geojson_path=args.metrics,
        parcel_id=args.parcel_id,
        parcel_id_field=args.parcel_id_field,
        blender_executable=args.blender,
        context_buffer_m=args.context_buffer_m,
        max_context_buildings=args.max_context_buildings,
        run_blender=not args.no_blender,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
