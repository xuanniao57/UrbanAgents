"""Advanced visual and 3D analysis tools for UrbanAgent."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

try:
    import geopandas as gpd
    HAS_GEOPANDAS = True
except ImportError:
    HAS_GEOPANDAS = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from .geo_tools import (
    _clip_to_boundary,
    _height_proxy_series,
    _metric_row,
    _sample_streetview_images,
    _to_metric_crs,
    discover_urban_data_sources,
)


PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)


def compute_streetview_semantic_segmentation(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Create transparent street-view semantic proxy masks and intermediate tables."""
    if not HAS_PIL:
        return {"status": "unavailable", "reason": "Pillow is not installed", "capability": "streetview_semantic_segmentation"}

    context = discover_urban_data_sources(arguments)
    paths = context.get("paths", {})
    streetview_dir = paths.get("streetview_dir")
    if not streetview_dir:
        return {"status": "unavailable", "reason": "no street-view image directory found", "capability": "streetview_semantic_segmentation"}

    artifact_dir = Path(arguments.get("artifact_dir") or arguments.get("output_dir") or "artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    sample_limit = int(arguments.get("streetview_semantic_sample_limit", 24))
    image_paths = _sample_streetview_images(Path(streetview_dir), limit=sample_limit)
    if not image_paths:
        return {"status": "unavailable", "reason": "street-view directory contains no readable images", "capability": "streetview_semantic_segmentation"}

    rows = []
    panels = []
    for image_path in image_paths:
        try:
            image = Image.open(image_path).convert("RGB").resize((192, 108))
            arr = np.asarray(image, dtype=np.uint8)
            masks = _streetview_semantic_proxy_masks(arr)
            overlay = _semantic_overlay_image(image, masks)
            panels.append(_make_pair_panel(image, overlay))
            ratios = {f"{name}_ratio": float(mask.mean()) for name, mask in masks.items()}
            rows.append({"image_path": str(image_path), **ratios})
        except Exception:
            continue

    if not rows:
        return {"status": "unavailable", "reason": "no street-view images could be segmented", "capability": "streetview_semantic_segmentation"}

    metrics_csv = artifact_dir / "streetview_semantic_proxy_metrics.csv"
    if HAS_PANDAS:
        pd.DataFrame(rows).to_csv(metrics_csv, index=False, encoding="utf-8-sig")
    else:
        metrics_csv.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    mask_panel = _write_panel_grid(panels, artifact_dir / "streetview_semantic_proxy_masks.png")
    summary = _aggregate_semantic_rows(rows)
    manifest = {
        "method": "traditional_color_position_edge_proxy_masks",
        "sampled_image_count": len(rows),
        "class_definitions": {
            "sky": "bright blue/low-red pixels in upper image regions",
            "vegetation": "green-dominant pixels",
            "road": "low-saturation lower-image gray pixels",
            "facade_proxy": "non-sky/non-vegetation/non-road vertical built-surface proxy",
            "signage_color_proxy": "high-saturation candidate signage/color patch pixels",
        },
        "summary": summary,
        "limitations": [
            "This is a deterministic semantic proxy, not a trained segmentation model.",
            "Use a trained segmentation model or MLLM labels before making material, signboard, or facade-condition claims.",
        ],
    }
    manifest_path = artifact_dir / "streetview_semantic_proxy_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    metric_rows = [
        _metric_row("streetview_semantics", key, value, "ratio", "mean proxy mask share across sampled street-view images")
        for key, value in summary.items()
        if key.endswith("_ratio_mean")
    ]

    artifacts = [
        _artifact("streetview_semantic_metrics_csv", metrics_csv, "text/csv", "Street-view semantic proxy metrics"),
        _artifact("streetview_semantic_masks_png", mask_panel, "image/png", "Street-view semantic proxy mask panel"),
        _artifact("streetview_semantic_manifest", manifest_path, "application/json", "Street-view semantic proxy manifest"),
    ]
    return {
        "status": "computed",
        "capability": "streetview_semantic_segmentation",
        "method": "traditional_semantic_proxy_masks",
        "path": streetview_dir,
        "summary": summary,
        "metric_rows": metric_rows,
        "artifacts": artifacts,
        "intermediate_results": {
            "per_image_metrics": str(metrics_csv),
            "mask_panel": str(mask_panel),
            "manifest": str(manifest_path),
        },
        "limitations": manifest["limitations"],
    }


def prepare_streetview_mllm_evaluation(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Prepare auditable image prompts for MLLM-based street-view assessment."""
    context = discover_urban_data_sources(arguments)
    paths = context.get("paths", {})
    streetview_dir = paths.get("streetview_dir")
    if not streetview_dir:
        return {"status": "unavailable", "reason": "no street-view image directory found", "capability": "streetview_mllm_evaluation"}

    artifact_dir = Path(arguments.get("artifact_dir") or arguments.get("output_dir") or "artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    image_paths = _sample_streetview_images(Path(streetview_dir), limit=int(arguments.get("streetview_mllm_sample_limit", 12)))
    prompt = (
        "Assess this street-view image for heritage streetscape harmony. Return JSON with: "
        "facade_material_visibility, signage_intrusion, vegetation_presence, sky_openness, pedestrian_realm_quality, "
        "confidence, and one sentence of visual evidence. Do not infer beyond visible image content."
    )
    jsonl_path = artifact_dir / "streetview_mllm_eval_requests.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for idx, image_path in enumerate(image_paths, start=1):
            handle.write(json.dumps({
                "id": f"streetview_{idx:03d}",
                "image_path": str(image_path),
                "prompt": prompt,
                "expected_schema": {
                    "facade_material_visibility": "0-1",
                    "signage_intrusion": "0-1",
                    "vegetation_presence": "0-1",
                    "sky_openness": "0-1",
                    "pedestrian_realm_quality": "0-1",
                    "confidence": "0-1",
                    "visual_evidence": "string",
                },
            }, ensure_ascii=False) + "\n")

    manifest_path = artifact_dir / "streetview_mllm_eval_manifest.json"
    manifest = {
        "status": "prepared",
        "sample_count": len(image_paths),
        "request_jsonl": str(jsonl_path),
        "network_policy": "no remote model call was made by this tool; downstream MLLM execution must record model, endpoint, and data policy",
        "intermediate_results_required": ["per-image JSON responses", "reviewable image list", "aggregate score table"],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "status": "prepared",
        "capability": "streetview_mllm_evaluation",
        "method": "mllm_prompt_pack_for_visible_evidence_assessment",
        "summary": {"sample_count": len(image_paths), "request_jsonl": str(jsonl_path)},
        "artifacts": [
            _artifact("streetview_mllm_requests_jsonl", jsonl_path, "application/jsonl", "MLLM street-view evaluation request pack"),
            _artifact("streetview_mllm_manifest", manifest_path, "application/json", "MLLM street-view evaluation manifest"),
        ],
        "limitations": ["This tool prepares auditable MLLM inputs only; it does not call a remote model."],
    }


def build_urban_3d_scene_package(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Build local 3D extrusion inputs for QGIS 3D and Rhino/Grasshopper."""
    if not HAS_GEOPANDAS:
        return {"status": "unavailable", "reason": "geopandas is not installed", "capability": "urban_3d_scene_generation"}

    context = discover_urban_data_sources(arguments)
    paths = context.get("paths", {})
    buildings_path = paths.get("buildings") or paths.get("function_buildings")
    if not buildings_path:
        return {"status": "unavailable", "reason": "no building polygon layer found", "capability": "urban_3d_scene_generation"}

    artifact_dir = Path(arguments.get("artifact_dir") or arguments.get("output_dir") or "artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)

    buildings = gpd.read_file(buildings_path)
    buildings_m, metric_crs = _to_metric_crs(buildings)
    boundary_m = None
    if paths.get("boundary"):
        try:
            boundary = gpd.read_file(paths["boundary"])
            boundary_m, _ = _to_metric_crs(boundary, target_crs=metric_crs)
        except Exception:
            boundary_m = None
    buildings_m = _clip_to_boundary(buildings_m, boundary_m)
    height_info = _height_proxy_series(buildings_m)
    buildings_m = buildings_m.copy()
    buildings_m["height_m"] = height_info["height_m"].fillna(float(arguments.get("default_building_height_m", 12.0)))
    buildings_m["extrusion_base_m"] = 0.0
    buildings_m["extrusion_source"] = "height_or_levels_proxy_with_default"

    gpkg_path = artifact_dir / "urban_3d_scene_layers.gpkg"
    if gpkg_path.exists():
        gpkg_path.unlink()
    buildings_m.to_file(gpkg_path, layer="building_extrusions", driver="GPKG")

    gh_inputs = _grasshopper_input_records(buildings_m)
    gh_path = artifact_dir / "grasshopper_building_extrusion_inputs.json"
    gh_path.write_text(json.dumps(gh_inputs, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest = {
        "status": "prepared",
        "metric_crs": metric_crs,
        "building_count": int(len(buildings_m)),
        "height_field": "height_m",
        "height_proxy_count": int(height_info.get("proxy_count", 0)),
        "qgis_3d": {
            "supported": True,
            "workflow": "Open the GPKG in QGIS, set layer 3D renderer to extrusion using height_m, or use QGIS 3D Map View for inspection.",
            "layer": f"{gpkg_path}|layername=building_extrusions",
        },
        "rhino_grasshopper": {
            "input_json": str(gh_path),
            "network_policy": "local_only_no_proxy",
            "recommended_components": ["Read JSON", "Boundary Surfaces", "Extrude", "Custom Preview"],
        },
    }
    manifest_path = artifact_dir / "urban_3d_scene_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "status": "prepared",
        "capability": "urban_3d_scene_generation",
        "method": "building_footprint_height_proxy_extrusion_package",
        "summary": {
            "building_count": int(len(buildings_m)),
            "height_proxy_count": int(height_info.get("proxy_count", 0)),
            "metric_crs": metric_crs,
            "qgis_3d_supported": True,
            "rhino_grasshopper_input_json": str(gh_path),
        },
        "artifacts": [
            _artifact("urban_3d_gpkg", gpkg_path, "application/geopackage+sqlite3", "3D extrusion-ready building layer"),
            _artifact("grasshopper_input_json", gh_path, "application/json", "Rhino/Grasshopper extrusion input records"),
            _artifact("urban_3d_manifest", manifest_path, "application/json", "3D scene manifest"),
        ],
        "limitations": ["3D scene uses available height attributes, building:levels proxy, or default height where missing."],
    }


def probe_rhino_grasshopper_environment(arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Probe local Rhino/Grasshopper availability without using network proxies."""
    arguments = arguments or {}
    candidates = []
    for root in (Path(os.environ.get("ProgramFiles", r"C:\Program Files")), Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))):
        candidates.extend(root.glob("Rhino */System/Rhino.exe"))
        candidates.extend(root.glob("Rhino*/System/Rhino.exe"))
    candidates.extend(Path(r"C:\Program Files").glob("**/Rhino.exe"))
    unique_candidates = sorted({str(path) for path in candidates if path.exists()})

    compute_candidates = []
    for root in (Path(os.environ.get("ProgramFiles", r"C:\Program Files")), Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))):
        compute_candidates.extend(root.glob("**/Compute.Geometry.exe"))
    unique_compute = sorted({str(path) for path in compute_candidates if path.exists()})

    proxy_present = {key: "set" for key in PROXY_ENV_KEYS if os.environ.get(key)}
    result = {
        "status": "available" if unique_candidates else "unavailable",
        "capability": "rhino_grasshopper_bridge",
        "rhino_executables": unique_candidates,
        "compute_executables": unique_compute,
        "grasshopper_note": "Grasshopper is bundled inside Rhino Desktop; launch Rhino locally and open Grasshopper without HTTP proxy.",
        "network_policy": "local_only_no_proxy",
        "proxy_env_would_be_removed": sorted(proxy_present),
        "launched": False,
    }

    if arguments.get("launch_rhino") and unique_candidates:
        env = _no_proxy_env()
        subprocess.Popen([unique_candidates[-1]], env=env)
        result["launched"] = True
        result["launched_executable"] = unique_candidates[-1]
    return result


def _streetview_semantic_proxy_masks(arr: np.ndarray) -> Dict[str, np.ndarray]:
    rgb = arr.astype(np.float32)
    red, green, blue = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    brightness = rgb.mean(axis=2)
    saturation = rgb.max(axis=2) - rgb.min(axis=2)
    height = arr.shape[0]
    y = np.arange(height)[:, None] / max(1, height - 1)

    sky = (y < 0.62) & (blue > red * 1.08) & (blue > green * 0.92) & (brightness > 105)
    vegetation = (green > red * 1.12) & (green > blue * 1.04) & (green > 70)
    road = (y > 0.48) & (saturation < 45) & (brightness > 45) & (brightness < 210)
    signage = (saturation > 95) & (brightness > 90) & (y > 0.18) & (y < 0.82) & ~vegetation
    facade = (y > 0.18) & (y < 0.92) & ~(sky | vegetation | road)
    return {
        "sky": sky,
        "vegetation": vegetation,
        "road": road,
        "facade_proxy": facade,
        "signage_color_proxy": signage,
    }


def _semantic_overlay_image(image: Image.Image, masks: Dict[str, np.ndarray]) -> Image.Image:
    colors = {
        "sky": np.array([80, 150, 255], dtype=np.uint8),
        "vegetation": np.array([60, 180, 90], dtype=np.uint8),
        "road": np.array([120, 120, 120], dtype=np.uint8),
        "facade_proxy": np.array([214, 180, 130], dtype=np.uint8),
        "signage_color_proxy": np.array([230, 80, 80], dtype=np.uint8),
    }
    base = np.asarray(image.convert("RGB"), dtype=np.uint8)
    overlay = base.copy()
    for name, mask in masks.items():
        overlay[mask] = (0.45 * overlay[mask] + 0.55 * colors[name]).astype(np.uint8)
    return Image.fromarray(overlay, mode="RGB")


def _make_pair_panel(left: Image.Image, right: Image.Image) -> Image.Image:
    panel = Image.new("RGB", (left.width + right.width, max(left.height, right.height)), "white")
    panel.paste(left, (0, 0))
    panel.paste(right, (left.width, 0))
    return panel


def _write_panel_grid(panels: list[Image.Image], output_path: Path) -> Path:
    cols = 2
    rows = int(np.ceil(len(panels) / cols))
    width = max(panel.width for panel in panels)
    height = max(panel.height for panel in panels)
    canvas = Image.new("RGB", (cols * width, rows * height), "white")
    for idx, panel in enumerate(panels):
        x = (idx % cols) * width
        y = (idx // cols) * height
        canvas.paste(panel, (x, y))
    canvas.save(output_path)
    return output_path


def _aggregate_semantic_rows(rows: list[Dict[str, Any]]) -> Dict[str, float]:
    keys = [key for key in rows[0] if key.endswith("_ratio")]
    summary = {}
    for key in keys:
        values = [float(row[key]) for row in rows if key in row]
        summary[f"{key}_mean"] = float(np.mean(values)) if values else 0.0
        summary[f"{key}_std"] = float(np.std(values)) if values else 0.0
    return summary


def _grasshopper_input_records(buildings_m: Any, limit: int = 500) -> Dict[str, Any]:
    records = []
    for idx, (_, row) in enumerate(buildings_m.head(limit).iterrows(), start=1):
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        records.append({
            "id": str(row.get("id") or row.get("osm_id") or idx),
            "footprint_wkt": geom.wkt,
            "height_m": float(row.get("height_m") or 12.0),
            "base_z_m": float(row.get("extrusion_base_m") or 0.0),
        })
    return {
        "schema": "urbanagent_grasshopper_extrusion_inputs/v1",
        "record_count": len(records),
        "records": records,
    }


def _no_proxy_env() -> Dict[str, str]:
    env = os.environ.copy()
    for key in PROXY_ENV_KEYS:
        env.pop(key, None)
    env.setdefault("NO_PROXY", "localhost,127.0.0.1")
    env.setdefault("no_proxy", "localhost,127.0.0.1")
    return env


def _artifact(artifact_type: str, path: Path, mime_type: str, title: str) -> Dict[str, Any]:
    return {
        "id": path.stem,
        "type": artifact_type,
        "title": title,
        "path": str(path),
        "mime_type": mime_type,
    }
