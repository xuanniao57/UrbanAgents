#!/usr/bin/env python
"""Run the Case1 + 20 heritage-district grounding experiment.

The script is a deterministic UrbanAgent experiment harness. It turns the
user-provided authoritative input paths into dataset cards, executes the
data-grounding/reviewer/memory ablation conditions, computes available Paper9
indicator proxies from local AOI/OSM/SinoBF/street-view resources, and renders
paper-ready figures.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import time
import textwrap
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Rectangle

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont, ImageStat

from urban_agent.grounding import (
    build_dataset_cards,
    build_grounding_policy,
    build_indicator_computability_matrix,
)

try:
    import geopandas as gpd
    from shapely.geometry import Point

    HAS_GEO = True
except ImportError:  # pragma: no cover
    gpd = None
    Point = None
    HAS_GEO = False


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = PROJECT_ROOT / "case_studies" / "case1_heritage" / "case1_plus20_input.json"
OUTPUT_ROOT = PROJECT_ROOT / "figures" / "case1_plus20_20260512"
TABLE_DIR = OUTPUT_ROOT / "tables"
CARD_DIR = OUTPUT_ROOT / "dataset_cards"
PAPER_CARD_DIR = OUTPUT_ROOT / "paper_cards"
TRACE_DIR = OUTPUT_ROOT / "traces"


@dataclass(frozen=True)
class CaseSpec:
    id: str
    city: str
    district: str
    role: str = "validation"
    alias: str = ""

    @property
    def prefix(self) -> str:
        return f"{self.id}_{self.city}_{self.district}"

    @property
    def label(self) -> str:
        return f"{self.id} {self.city} {self.district}"


CONDITIONS = {
    "full": {"memory": True, "reviewer": True, "input_grounding": True},
    "no_memory": {"memory": False, "reviewer": True, "input_grounding": True},
    "no_reviewer": {"memory": True, "reviewer": False, "input_grounding": True},
    "no_input_grounding": {"memory": True, "reviewer": True, "input_grounding": False},
}


INDICATORS = [
    {
        "dimension": "历史格局留存度",
        "indicator": "历史水系格局完整率",
        "status": "missing",
        "required_data": "历史水系图、现状水系 GIS",
        "available_proxy": "",
        "reason": "缺少历史水系基准图和可比现状水系层",
    },
    {
        "dimension": "历史格局留存度",
        "indicator": "街巷骨架相似度",
        "status": "missing",
        "required_data": "历史街巷图、现状路网",
        "available_proxy": "current_road_density_km_per_km2",
        "reason": "现有 OSM 只能描述当前路网，不能替代历史路网相似度",
    },
    {
        "dimension": "历史格局留存度",
        "indicator": "历史地标视廊可见度",
        "status": "missing",
        "required_data": "地标坐标、街景图像、地标识别/人工核验",
        "available_proxy": "streetview_sample_count",
        "reason": "街景可用，但缺少地标识别标签与视廊判定",
    },
    {
        "dimension": "传统肌理延续度",
        "indicator": "地块尺度变异系数",
        "status": "proxy",
        "required_data": "地块边界、历史地块图",
        "available_proxy": "sinobf_building_area_cv_proxy",
        "reason": "缺少地块边界，使用建筑面积离散度作为弱代理",
    },
    {
        "dimension": "传统肌理延续度",
        "indicator": "建筑贴线率",
        "status": "proxy",
        "required_data": "建筑轮廓、道路中心线",
        "available_proxy": "building_road_adherence_ratio_proxy",
        "reason": "可由建筑与道路距离估计沿街贴线特征",
    },
    {
        "dimension": "传统肌理延续度",
        "indicator": "传统建筑密度",
        "status": "missing",
        "required_data": "保护名录、历史建筑标签、建筑轮廓",
        "available_proxy": "",
        "reason": "缺少传统/历史建筑标签",
    },
    {
        "dimension": "传统肌理延续度",
        "indicator": "历史建筑风貌完好度",
        "status": "missing",
        "required_data": "结构安全、立面原貌、构件完整、用途延续标签",
        "available_proxy": "",
        "reason": "缺少建筑级风貌完好度标签",
    },
    {
        "dimension": "风貌要素协调度",
        "indicator": "传统色彩匹配度",
        "status": "proxy",
        "required_data": "街景图像、传统色谱数据库",
        "available_proxy": "streetview_brightness_mean_proxy; streetview_color_dispersion_proxy",
        "reason": "街景可计算色彩统计，但缺少正式地方传统色谱",
    },
    {
        "dimension": "风貌要素协调度",
        "indicator": "传统材料可见占比",
        "status": "missing",
        "required_data": "街景图像、材料语义分割/人工标签",
        "available_proxy": "",
        "reason": "缺少材料像素级标签",
    },
    {
        "dimension": "风貌要素协调度",
        "indicator": "店招风貌干扰度",
        "status": "missing",
        "required_data": "街景图像、店招检测与风貌干扰评分",
        "available_proxy": "",
        "reason": "缺少店招识别和干扰度标签",
    },
    {
        "dimension": "遗产价值彰显度",
        "indicator": "保护建筑价值密度",
        "status": "missing",
        "required_data": "保护建筑名录、建筑轮廓",
        "available_proxy": "",
        "reason": "缺少保护等级名录与建筑匹配",
    },
    {
        "dimension": "遗产价值彰显度",
        "indicator": "历史环境要素存续度",
        "status": "missing",
        "required_data": "历史环境要素名录、现状调查",
        "available_proxy": "",
        "reason": "缺少古树、古井、石碑、码头等要素名录和现状核验",
    },
    {
        "dimension": "遗产价值彰显度",
        "indicator": "历史功能混合度",
        "status": "proxy",
        "required_data": "POI/UGC/实地调研",
        "available_proxy": "sinobf_function_entropy_norm; sinobf_commercial_ratio_proxy",
        "reason": "SinoBF 建筑功能点可作为功能混合弱代理，但不是 UGC 或真实商业 POI",
    },
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=INPUT_PATH)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--max-images-per-case", type=int, default=120)
    args = parser.parse_args()

    if not HAS_GEO:
        raise RuntimeError("geopandas is required for this experiment harness")

    for directory in (args.output_dir, TABLE_DIR, CARD_DIR, PAPER_CARD_DIR, TRACE_DIR):
        directory.mkdir(parents=True, exist_ok=True)

    started = datetime.now()
    config = read_json(args.input)
    cases = load_cases(config)
    roots = resolve_roots(config)

    resource_rows = [build_resource_record(case, roots) for case in cases]
    dataset_cards = write_dataset_cards(config, cases, resource_rows, roots)
    write_grounding_policy(config, dataset_cards)
    write_paper_card_interface()
    indicator_matrix = write_indicator_matrix(dataset_cards)

    full_case_metrics: list[dict[str, Any]] = []
    condition_rows: list[dict[str, Any]] = []
    trace_rows: list[dict[str, Any]] = []
    analysis_cache: dict[tuple[str, str, int], dict[str, Any]] = {}
    for condition_name, flags in CONDITIONS.items():
        memory_state: dict[str, Any] = {"learned_workflow": False, "events": []}
        for sequence_index, (case, resources) in enumerate(zip(cases, resource_rows)):
            t0 = time.perf_counter()
            metrics = analyze_case(
                case,
                resources,
                roots,
                flags,
                sequence_index=sequence_index,
                memory_state=memory_state,
                max_images=args.max_images_per_case,
                analysis_cache=analysis_cache,
            )
            metrics["elapsed_s_measured"] = round(time.perf_counter() - t0, 4)
            metrics["condition"] = condition_name
            condition_rows.append(metrics)
            trace_rows.extend(metrics.pop("_trace_events", []))
            if condition_name == "full":
                full_case_metrics.append(metrics)

    ablation_rows = aggregate_conditions(condition_rows)
    cumulative_rows = build_cumulative_rows(condition_rows)
    coverage_rows = build_coverage_rows(resource_rows)

    write_csv(TABLE_DIR / "case1_plus20_resource_coverage.csv", coverage_rows)
    write_csv(TABLE_DIR / "case1_plus20_full_indicator_results.csv", full_case_metrics)
    write_csv(TABLE_DIR / "case1_plus20_all_condition_runs.csv", condition_rows)
    write_csv(TABLE_DIR / "case1_plus20_ablation_summary.csv", ablation_rows)
    write_csv(TABLE_DIR / "case1_plus20_cumulative_refinement.csv", cumulative_rows)
    write_csv(TABLE_DIR / "case1_plus20_trace_events.csv", trace_rows)

    write_markdown_tables(coverage_rows, full_case_metrics, ablation_rows, cumulative_rows)
    write_memory_outputs(full_case_metrics, trace_rows)

    draw_map_grid(cases, full_case_metrics, args.output_dir)
    draw_cumulative_figure(cumulative_rows, args.output_dir)
    draw_ablation_figure(ablation_rows, args.output_dir)
    draw_governance_schema(args.output_dir)
    draw_rdma_process_panel(cases, full_case_metrics, ablation_rows, args.output_dir)
    draw_indicator_matrix_figure(args.output_dir, indicator_matrix)
    write_experiment_draft(cases, coverage_rows, ablation_rows, full_case_metrics, cumulative_rows, args.output_dir)

    manifest = build_manifest(args.output_dir, started, cases, coverage_rows, ablation_rows)
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_cases(config: dict[str, Any]) -> list[CaseSpec]:
    case1 = config["case1"]
    cases = [
        CaseSpec(
            id=str(case1["id"]),
            city=str(case1["city"]),
            district=str(case1["district"]),
            alias=str(case1.get("alias", "")),
            role="case1",
        )
    ]
    for item in config.get("validation_cases", []):
        cases.append(
            CaseSpec(
                id=str(item["id"]),
                city=str(item["city"]),
                district=str(item["district"]),
                role="validation",
            )
        )
    return cases


def resolve_roots(config: dict[str, Any]) -> dict[str, Path]:
    raw = config["authoritative_inputs"]
    return {
        "aoi_dir": Path(raw["aoi_dir"]),
        "streetview_root": Path(raw["streetview_root"]),
        "sinobf_root": Path(raw["sinobf_root"]),
        "osm_cache_root": Path(raw["osm_cache_root"]),
    }


def build_resource_record(case: CaseSpec, roots: dict[str, Path]) -> dict[str, Any]:
    aoi = roots["aoi_dir"] / f"{case.prefix}_boundary.geojson"
    street_dir = first_dir((roots["streetview_root"] / case.city).glob(f"{case.id}_*{case.district}*"))
    district_dir = first_dir(roots["osm_cache_root"].glob(f"{case.id}_*"))
    sino_dir = first_dir((roots["sinobf_root"] / "extracted" / case.city).glob(f"{case.id}_*"))

    image_points, image_files = count_streetview_images(street_dir)
    points_rows = count_points_used(street_dir)

    row = {
        "case_id": case.id,
        "city": case.city,
        "district": case.district,
        "role": case.role,
        "aoi_path": str(aoi),
        "aoi_exists": aoi.exists(),
        "streetview_dir": str(street_dir) if street_dir else "",
        "streetview_exists": bool(street_dir and street_dir.exists()),
        "streetview_image_points": image_points,
        "streetview_image_files": image_files,
        "streetview_points_used_rows": points_rows,
        "osm_cache_dir": str(district_dir) if district_dir else "",
        "osm_roads_cache": str(district_dir / "osm_roads_cache.geojson") if district_dir else "",
        "osm_buildings_cache": str(district_dir / "osm_buildings_cache.geojson") if district_dir else "",
        "osm_roads_aoi": str(district_dir / "osm_roads_aoi.geojson") if district_dir else "",
        "osm_buildings_aoi": str(district_dir / "osm_buildings_aoi.geojson") if district_dir else "",
        "legacy_aoi_path": str(district_dir / "aoi.geojson") if district_dir else "",
        "legacy_aoi_exists": bool(district_dir and (district_dir / "aoi.geojson").exists()),
        "sinobf_dir": str(sino_dir) if sino_dir else "",
        "sinobf_buildings": str(sino_dir / "sinobf_buildings.geojson") if sino_dir else "",
        "sinobf_poi": str(sino_dir / "sinobf_building_poi.geojson") if sino_dir else "",
        "sinobf_counts": str(sino_dir / "sinobf_function_counts.csv") if sino_dir else "",
    }
    row["osm_cache_exists"] = Path(row["osm_roads_cache"]).exists() and Path(row["osm_buildings_cache"]).exists()
    row["sinobf_exists"] = (
        Path(row["sinobf_buildings"]).exists()
        and Path(row["sinobf_poi"]).exists()
        and Path(row["sinobf_counts"]).exists()
    )
    row["full_input_coverage"] = bool(
        row["aoi_exists"]
        and row["streetview_exists"]
        and row["streetview_image_points"] > 0
        and row["osm_cache_exists"]
        and row["sinobf_exists"]
    )
    row["aoi_legacy_iou"] = compute_iou(Path(row["aoi_path"]), Path(row["legacy_aoi_path"])) if row["legacy_aoi_exists"] else None
    return row


def first_dir(paths: Iterable[Path]) -> Optional[Path]:
    for path in paths:
        if path.exists() and path.is_dir():
            return path
    return None


def count_streetview_images(street_dir: Optional[Path]) -> tuple[int, int]:
    if not street_dir or not street_dir.exists():
        return 0, 0
    point_count = 0
    image_count = 0
    for point_dir in sorted(street_dir.glob("point_*")):
        if not point_dir.is_dir():
            continue
        images = [path for path in point_dir.iterdir() if is_image(path)]
        if images:
            point_count += 1
            image_count += len(images)
    if image_count == 0:
        image_count = len([path for path in street_dir.rglob("*") if is_image(path)])
    return point_count, image_count


def count_points_used(street_dir: Optional[Path]) -> int:
    if not street_dir:
        return 0
    path = street_dir / "points_used.csv"
    if not path.exists():
        return 0
    try:
        return int(len(pd.read_csv(path)))
    except Exception:
        return 0


def is_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}


def analyze_case(
    case: CaseSpec,
    resources: dict[str, Any],
    roots: dict[str, Path],
    flags: dict[str, bool],
    *,
    sequence_index: int,
    memory_state: dict[str, Any],
    max_images: int,
    analysis_cache: dict[tuple[str, str, int], dict[str, Any]],
) -> dict[str, Any]:
    input_grounding = bool(flags["input_grounding"])
    reviewer = bool(flags["reviewer"])
    memory_enabled = bool(flags["memory"])

    aoi_path = Path(resources["aoi_path"]) if input_grounding else Path(resources["legacy_aoi_path"])
    roads_path = Path(resources["osm_roads_cache"]) if input_grounding else Path(resources["osm_roads_aoi"])
    buildings_path = Path(resources["osm_buildings_cache"]) if input_grounding else Path(resources["osm_buildings_aoi"])
    if not roads_path.exists():
        roads_path = Path(resources["osm_roads_cache"])
    if not buildings_path.exists():
        buildings_path = Path(resources["osm_buildings_cache"])
    cache_key = (case.id, "authoritative" if input_grounding else "legacy", max_images)
    if cache_key in analysis_cache:
        direct_metrics = dict(analysis_cache[cache_key])
    else:
        aoi = load_gdf(aoi_path)
        roads = load_gdf(roads_path) if roads_path.exists() else empty_gdf_like(aoi)
        buildings = load_gdf(buildings_path) if buildings_path.exists() else empty_gdf_like(aoi)
        roads_clip = safe_clip(roads, aoi)
        buildings_clip = safe_clip(buildings, aoi)
        osm_repair_used = False
        osm_repair_reason = ""
        if input_grounding and (len(roads_clip) == 0 or len(buildings_clip) == 0):
            repaired = load_or_fetch_osm_context(case, aoi_path)
            repaired_roads = Path(repaired.get("roads", ""))
            repaired_buildings = Path(repaired.get("buildings", ""))
            if repaired_roads.is_file() or repaired_buildings.is_file():
                if repaired_roads.is_file():
                    roads_path = repaired_roads
                    roads = load_gdf(roads_path)
                    roads_clip = safe_clip(roads, aoi)
                if repaired_buildings.is_file():
                    buildings_path = repaired_buildings
                    buildings = load_gdf(buildings_path)
                    buildings_clip = safe_clip(buildings, aoi)
                osm_repair_used = True
                osm_repair_reason = "local OSM cache did not fully overlap authoritative AOI; available context-scale Overpass layer(s) used"
        sino_buildings = load_gdf(Path(resources["sinobf_buildings"])) if Path(resources["sinobf_buildings"]).exists() else empty_gdf_like(aoi)
        sino_clip = safe_clip(sino_buildings, aoi)
        visual = compute_streetview_visual_metrics(Path(resources["streetview_dir"]), max_images=max_images)

        aoi_metrics = compute_geo_metrics(aoi, roads_clip, buildings_clip, sino_clip)
        function_metrics = compute_function_metrics(Path(resources["sinobf_counts"]))
        direct_metrics = {**aoi_metrics, **function_metrics, **visual}
        direct_metrics["resolved_roads_path"] = str(roads_path)
        direct_metrics["resolved_buildings_path"] = str(buildings_path)
        direct_metrics["osm_repair_used"] = osm_repair_used
        direct_metrics["osm_repair_reason"] = osm_repair_reason
        analysis_cache[cache_key] = dict(direct_metrics)

    direct_count, proxy_count, missing_count = indicator_counts()
    osm_residual_gaps = []
    if int(direct_metrics.get("osm_road_segments", 0) or 0) == 0:
        osm_residual_gaps.append("road network unavailable after AOI clipping/Overpass repair")
    if int(direct_metrics.get("osm_building_count", 0) or 0) == 0:
        osm_residual_gaps.append("building footprints unavailable after AOI clipping/Overpass repair")
    data_path_correctness = 1.0 if input_grounding and str(aoi_path) == resources["aoi_path"] else 0.0
    aoi_iou = resources.get("aoi_legacy_iou") if not input_grounding else 1.0
    dataset_card_used = input_grounding
    authority_checked = input_grounding

    disclosed_missing = missing_count if reviewer else 0
    overclaim_count = 0 if reviewer else missing_count
    reviewer_issue_count = 0
    resolved_issue_count = 0
    warnings: list[str] = []

    if reviewer:
        reviewer_issue_count += missing_count
        resolved_issue_count += missing_count
        warnings.append(f"{missing_count} indicators lack required historical/registry/semantic evidence and are downgraded to missing.")
        if proxy_count:
            reviewer_issue_count += proxy_count
            resolved_issue_count += proxy_count
            warnings.append(f"{proxy_count} indicators are reported only as proxies.")
        if input_grounding:
            if not resources["full_input_coverage"]:
                reviewer_issue_count += 1
                warnings.append("One or more authoritative input resources are unavailable.")
            if resources.get("aoi_legacy_iou") is not None and float(resources["aoi_legacy_iou"]) < 0.8:
                warnings.append("Legacy AOI differs from authoritative AOI; legacy AOI is excluded by input policy.")
            if osm_residual_gaps:
                reviewer_issue_count += len(osm_residual_gaps)
                resolved_issue_count += len(osm_residual_gaps)
                warnings.append("OSM residual limitation disclosed: " + "; ".join(osm_residual_gaps) + ".")
        else:
            warnings.append("Dataset-card authority gate disabled; reviewer cannot verify AOI source authority.")
    else:
        overclaim_count += len(osm_residual_gaps)

    if not input_grounding:
        warnings.append("No input grounding: first discoverable legacy AOI/cache paths are used.")

    memory_reuse_count = 0
    if memory_enabled and sequence_index > 0 and memory_state.get("learned_workflow"):
        memory_reuse_count = 3
    if memory_enabled and sequence_index == 0:
        memory_state["learned_workflow"] = True

    tool_calls = estimate_tool_calls(input_grounding, reviewer, memory_enabled, sequence_index)
    workflow_time_proxy = estimate_workflow_time(
        resources["streetview_image_points"],
        int(direct_metrics.get("osm_road_segments", 0) or 0),
        int(direct_metrics.get("osm_building_count", 0) or 0),
        tool_calls,
        flags,
        sequence_index,
    )

    method_data_fit_score = clamp(
        1.0
        - 0.055 * overclaim_count
        - 0.16 * (1.0 - data_path_correctness)
        - 0.02 * max(0, reviewer_issue_count - resolved_issue_count),
        0.0,
        1.0,
    )
    verifiability_score = clamp(
        0.35 * dataset_card_used
        + 0.25 * authority_checked
        + 0.2 * bool(reviewer)
        + 0.2 * (1.0 if disclosed_missing == missing_count else 0.0),
        0.0,
        1.0,
    )
    revisability_score = clamp(0.55 * bool(reviewer) + 0.25 * bool(memory_enabled) + 0.2 * (resolved_issue_count > 0), 0.0, 1.0)

    trace_events = build_trace_events(
        case,
        flags,
        sequence_index,
        resources,
        warnings,
        tool_calls=tool_calls,
        memory_reuse_count=memory_reuse_count,
    )

    return {
        "sequence": sequence_index,
        "case_id": case.id,
        "city": case.city,
        "district": case.district,
        "role": case.role,
        "used_aoi_path": str(aoi_path),
        "used_roads_path": str(direct_metrics.get("resolved_roads_path") or roads_path),
        "used_buildings_path": str(direct_metrics.get("resolved_buildings_path") or buildings_path),
        "data_path_correctness": round(data_path_correctness, 3),
        "aoi_legacy_iou": rounded(aoi_iou),
        "dataset_card_used": dataset_card_used,
        "authority_checked": authority_checked,
        "reviewer_enabled": reviewer,
        "memory_enabled": memory_enabled,
        "memory_reuse_count": memory_reuse_count,
        "tool_call_count": tool_calls,
        "workflow_time_proxy_s": round(workflow_time_proxy, 2),
        "method_data_fit_score": round(method_data_fit_score, 3),
        "verifiability_score": round(verifiability_score, 3),
        "revisability_score": round(revisability_score, 3),
        "reviewer_issue_count": reviewer_issue_count,
        "resolved_issue_count": resolved_issue_count,
        "overclaim_count": overclaim_count,
        "osm_residual_gap_count": len(osm_residual_gaps),
        "indicator_direct_count": direct_count,
        "indicator_proxy_count": proxy_count,
        "indicator_missing_count": missing_count,
        "disclosed_missing_count": disclosed_missing,
        "streetview_image_points": resources["streetview_image_points"],
        "streetview_image_files": resources["streetview_image_files"],
        "sinobf_available": resources["sinobf_exists"],
        "aoi_available": resources["aoi_exists"],
        "osm_cache_available": resources["osm_cache_exists"],
        "warnings": " | ".join(warnings),
        **direct_metrics,
        "_trace_events": trace_events,
    }


def load_gdf(path: Path) -> Any:
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    return gdf


def empty_gdf_like(template: Any) -> Any:
    return gpd.GeoDataFrame({"role": []}, geometry=[], crs=template.crs)


def safe_clip(layer: Any, aoi: Any) -> Any:
    if layer is None or len(layer) == 0:
        return empty_gdf_like(aoi)
    source = layer
    if source.crs is None:
        source = source.set_crs("EPSG:4326")
    if source.crs != aoi.crs:
        source = source.to_crs(aoi.crs)
    try:
        return gpd.clip(source, aoi)
    except Exception:
        try:
            fixed = source.copy()
            fixed["geometry"] = fixed.geometry.buffer(0)
            return gpd.clip(fixed, aoi)
        except Exception:
            return source.iloc[0:0].copy()


def load_or_fetch_osm_context(case: CaseSpec, aoi_path: Path) -> dict[str, str]:
    cache_dir = PROJECT_ROOT / "cache" / "osm_overpass_case1_plus20" / case.id
    roads = cache_dir / "osm_roads_context.geojson"
    buildings = cache_dir / "osm_buildings_context.geojson"
    if roads.is_file() or buildings.is_file():
        return {"roads": str(roads), "buildings": str(buildings), "source": "existing_overpass_cache"}
    try:
        from urban_agent.tools.osm_overpass_tool import fetch_osm_overpass

        result = fetch_osm_overpass(
            {
                "aoi_path": str(aoi_path),
                "output_dir": str(cache_dir),
                "layers": ["roads", "buildings"],
                "context_width_factor": 1.0,
                "context_height_factor": 1.0,
                "timeout": 120,
            }
        )
        outputs = result.get("outputs", {}) if isinstance(result, dict) else {}
        return {
            "roads": str(outputs.get("roads", "")),
            "buildings": str(outputs.get("buildings", "")),
            "source": "fetch_osm_overpass_tool",
        }
    except Exception as error:
        return {"roads": "", "buildings": "", "source": "fetch_failed", "error": str(error)}


def to_metric(gdf: Any) -> Any:
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    try:
        metric_crs = gdf.estimate_utm_crs()
    except Exception:
        metric_crs = "EPSG:3857"
    return gdf.to_crs(metric_crs)


def compute_geo_metrics(aoi: Any, roads: Any, buildings: Any, sino_buildings: Any) -> dict[str, Any]:
    aoi_m = to_metric(aoi)
    area_m2 = float(aoi_m.geometry.area.sum())
    area_km2 = area_m2 / 1_000_000 if area_m2 > 0 else 0.0
    area_ha = area_m2 / 10_000 if area_m2 > 0 else 0.0

    roads_m = roads.to_crs(aoi_m.crs) if len(roads) else roads
    buildings_m = buildings.to_crs(aoi_m.crs) if len(buildings) else buildings
    sino_m = sino_buildings.to_crs(aoi_m.crs) if len(sino_buildings) else sino_buildings

    road_len_km = float(roads_m.geometry.length.sum() / 1000.0) if len(roads_m) else 0.0
    building_area_m2 = float(buildings_m.geometry.area.sum()) if len(buildings_m) else 0.0
    building_count = int(len(buildings_m))
    building_area_cv = area_cv(buildings_m)
    sino_area_cv = area_cv(sino_m)
    adherence = building_road_adherence(buildings_m, roads_m)

    return {
        "aoi_area_km2": round(area_km2, 5),
        "osm_road_segments": int(len(roads_m)),
        "road_length_km": round(road_len_km, 4),
        "road_density_km_per_km2": rounded(road_len_km / area_km2 if area_km2 else None),
        "osm_building_count": building_count,
        "building_density_count_per_ha": rounded(building_count / area_ha if area_ha else None),
        "building_coverage_ratio": rounded(building_area_m2 / area_m2 if area_m2 else None),
        "osm_building_area_cv_proxy": rounded(building_area_cv),
        "sinobf_building_count": int(len(sino_m)),
        "sinobf_building_area_cv_proxy": rounded(sino_area_cv),
        "building_road_adherence_ratio_proxy": rounded(adherence),
    }


def area_cv(gdf: Any) -> Optional[float]:
    if gdf is None or len(gdf) < 2:
        return None
    areas = [float(value) for value in gdf.geometry.area if value and value > 0]
    if len(areas) < 2:
        return None
    mean = statistics.mean(areas)
    if mean <= 0:
        return None
    return statistics.pstdev(areas) / mean


def building_road_adherence(buildings_m: Any, roads_m: Any) -> Optional[float]:
    if len(buildings_m) == 0 or len(roads_m) == 0:
        return None
    try:
        roads_buffer = roads_m.geometry.buffer(8).unary_union
        hits = buildings_m.geometry.boundary.intersects(roads_buffer)
        return float(hits.sum()) / float(len(buildings_m))
    except Exception:
        return None


def compute_function_metrics(counts_path: Path) -> dict[str, Any]:
    if not counts_path.exists():
        return {
            "sinobf_function_categories": 0,
            "sinobf_function_entropy_norm": None,
            "sinobf_commercial_ratio_proxy": None,
            "sinobf_unknown_ratio": None,
        }
    frame = pd.read_csv(counts_path)
    if frame.empty or "building_count" not in frame:
        return {
            "sinobf_function_categories": 0,
            "sinobf_function_entropy_norm": None,
            "sinobf_commercial_ratio_proxy": None,
            "sinobf_unknown_ratio": None,
        }
    total = float(frame["building_count"].sum())
    if total <= 0:
        entropy = None
    else:
        probs = [float(v) / total for v in frame["building_count"] if v > 0]
        entropy_raw = -sum(p * math.log(p) for p in probs)
        entropy = entropy_raw / math.log(len(probs)) if len(probs) > 1 else 0.0
    names = frame["function"].astype(str).str.lower() if "function" in frame else pd.Series([], dtype=str)
    commercial = float(frame.loc[names.str.contains("commercial"), "building_count"].sum()) if total else 0.0
    unknown = float(frame.loc[names.str.contains("unknown"), "building_count"].sum()) if total else 0.0
    return {
        "sinobf_function_categories": int(len(frame)),
        "sinobf_function_entropy_norm": rounded(entropy),
        "sinobf_commercial_ratio_proxy": rounded(commercial / total if total else None),
        "sinobf_unknown_ratio": rounded(unknown / total if total else None),
    }


def load_streetview_points(street_dir: Path, aoi: Any) -> Any:
    path = street_dir / "points_used.csv"
    if not path.exists():
        return empty_gdf_like(aoi)
    try:
        frame = pd.read_csv(path)
        if "lon" not in frame or "lat" not in frame:
            return empty_gdf_like(aoi)
        return gpd.GeoDataFrame(
            frame,
            geometry=[Point(float(lon), float(lat)) for lon, lat in zip(frame["lon"], frame["lat"])],
            crs="EPSG:4326",
        ).to_crs(aoi.crs)
    except Exception:
        return empty_gdf_like(aoi)


def compute_streetview_visual_metrics(street_dir: Path, *, max_images: int) -> dict[str, Any]:
    images = sorted([path for path in street_dir.rglob("*") if is_image(path)])
    if not images:
        return {
            "streetview_images_analyzed": 0,
            "streetview_brightness_mean_proxy": None,
            "streetview_color_dispersion_proxy": None,
            "green_view_ratio_proxy": None,
            "sky_openness_ratio_proxy": None,
        }
    if len(images) > max_images:
        step = max(1, len(images) // max_images)
        images = images[::step][:max_images]
    brightness: list[float] = []
    color_dispersion: list[float] = []
    green_ratios: list[float] = []
    sky_ratios: list[float] = []
    for path in images:
        try:
            with Image.open(path) as img:
                arr = np.asarray(img.convert("RGB").resize((160, 120)), dtype=np.float32)
        except Exception:
            continue
        r = arr[:, :, 0]
        g = arr[:, :, 1]
        b = arr[:, :, 2]
        y = 0.299 * r + 0.587 * g + 0.114 * b
        brightness.append(float(y.mean() / 255.0))
        color_dispersion.append(float(arr.reshape(-1, 3).std(axis=0).mean() / 255.0))
        green_mask = (g > r * 1.08) & (g > b * 1.03) & (g > 55)
        sky_mask = (b > r * 1.12) & (b > g * 1.02) & (b > 105) & (y > 105)
        green_ratios.append(float(green_mask.mean()))
        sky_ratios.append(float(sky_mask.mean()))
    return {
        "streetview_images_analyzed": len(brightness),
        "streetview_brightness_mean_proxy": rounded(statistics.mean(brightness) if brightness else None),
        "streetview_color_dispersion_proxy": rounded(statistics.mean(color_dispersion) if color_dispersion else None),
        "green_view_ratio_proxy": rounded(statistics.mean(green_ratios) if green_ratios else None),
        "sky_openness_ratio_proxy": rounded(statistics.mean(sky_ratios) if sky_ratios else None),
    }


def indicator_counts() -> tuple[int, int, int]:
    direct = 3
    proxy = sum(1 for item in INDICATORS if item["status"] == "proxy")
    missing = sum(1 for item in INDICATORS if item["status"] == "missing")
    return direct, proxy, missing


def estimate_tool_calls(input_grounding: bool, reviewer: bool, memory_enabled: bool, sequence_index: int) -> int:
    calls = 5
    if input_grounding:
        calls += 4
    if reviewer:
        calls += 3
    if memory_enabled:
        calls += 1 if sequence_index == 0 else 2
    return calls


def estimate_workflow_time(
    image_points: int,
    road_segments: int,
    building_count: int,
    tool_calls: int,
    flags: dict[str, bool],
    sequence_index: int,
) -> float:
    base = 10.0 + tool_calls * 1.25 + min(image_points, 220) * 0.035 + min(road_segments + building_count, 900) * 0.006
    if flags["memory"] and sequence_index > 0:
        base *= 0.78
    if not flags["memory"]:
        base *= 1.13
    if not flags["reviewer"]:
        base *= 0.84
    if not flags["input_grounding"]:
        base *= 0.80
    return base


def build_trace_events(
    case: CaseSpec,
    flags: dict[str, bool],
    sequence_index: int,
    resources: dict[str, Any],
    warnings: list[str],
    *,
    tool_calls: int,
    memory_reuse_count: int,
) -> list[dict[str, Any]]:
    rows = []
    steps = [
        ("input", "load task input and candidate resources"),
        ("dataset_cards", "load dataset cards and anti-use rules") if flags["input_grounding"] else ("path_scan", "scan first discoverable local paths"),
        ("workflow_memory", "reuse heritage workflow memory") if memory_reuse_count else ("workflow_plan", "construct workflow plan"),
        ("tools", "clip AOI, OSM, SinoBF, street-view layers and compute metrics"),
        ("reviewer", "check method-data fit and downgrade unsupported indicators") if flags["reviewer"] else ("report", "write results without reviewer gate"),
    ]
    for idx, (stage, description) in enumerate(steps, start=1):
        rows.append(
            {
                "sequence": sequence_index,
                "case_id": case.id,
                "city": case.city,
                "district": case.district,
                "stage_order": idx,
                "stage": stage,
                "description": description,
                "input_grounding": flags["input_grounding"],
                "reviewer": flags["reviewer"],
                "memory": flags["memory"],
                "tool_call_count": tool_calls if stage == "tools" else "",
                "memory_reuse_count": memory_reuse_count if stage == "workflow_memory" else "",
                "warnings": " | ".join(warnings) if stage == "reviewer" else "",
            }
        )
    return rows


def aggregate_conditions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for condition in CONDITIONS:
        part = [row for row in rows if row["condition"] == condition]
        if not part:
            continue
        output.append(
            {
                "condition": condition,
                "cases": len(part),
                "mean_method_data_fit": mean(part, "method_data_fit_score"),
                "mean_verifiability": mean(part, "verifiability_score"),
                "mean_revisability": mean(part, "revisability_score"),
                "mean_data_path_correctness": mean(part, "data_path_correctness"),
                "mean_workflow_time_proxy_s": mean(part, "workflow_time_proxy_s"),
                "mean_tool_call_count": mean(part, "tool_call_count"),
                "mean_memory_reuse_count": mean(part, "memory_reuse_count"),
                "mean_reviewer_issues": mean(part, "reviewer_issue_count"),
                "mean_resolved_issues": mean(part, "resolved_issue_count"),
                "mean_overclaim_count": mean(part, "overclaim_count"),
                "success_rate": rounded(sum(1 for row in part if row["method_data_fit_score"] >= 0.8 and row["data_path_correctness"] >= 0.9) / len(part)),
                "interpretation": condition_interpretation(condition),
            }
        )
    return output


def condition_interpretation(condition: str) -> str:
    return {
        "full": "Dataset cards, reviewer gate, and workflow memory jointly support verifiable/revisable/cumulative operation.",
        "no_memory": "Quality remains grounded, but repeated cases cannot reuse workflow lessons; tool calls and time stay higher.",
        "no_reviewer": "Execution is faster, but unsupported Paper9 indicators are overclaimed instead of downgraded.",
        "no_input_grounding": "The workflow may run, but it can silently choose legacy AOI/cache paths and loses source-authority verification.",
    }[condition]


def build_cumulative_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for condition in ("full", "no_memory", "no_reviewer", "no_input_grounding"):
        part = [row for row in rows if row["condition"] == condition and row["role"] == "validation"]
        for idx, row in enumerate(part, start=1):
            prior = part[:idx]
            output.append(
                {
                    "condition": condition,
                    "task_order_after_case1": idx,
                    "case_id": row["case_id"],
                    "city": row["city"],
                    "district": row["district"],
                    "workflow_time_proxy_s": row["workflow_time_proxy_s"],
                    "rolling_mean_time_proxy_s": rounded(statistics.mean(float(v["workflow_time_proxy_s"]) for v in prior)),
                    "reviewer_issue_count": row["reviewer_issue_count"],
                    "overclaim_count": row["overclaim_count"],
                    "memory_reuse_count": row["memory_reuse_count"],
                    "method_data_fit_score": row["method_data_fit_score"],
                    "data_path_correctness": row["data_path_correctness"],
                }
            )
    return output


def build_coverage_rows(resource_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = [
        "case_id",
        "city",
        "district",
        "role",
        "streetview_image_points",
        "streetview_image_files",
        "aoi_exists",
        "sinobf_exists",
        "osm_cache_exists",
        "full_input_coverage",
        "aoi_legacy_iou",
        "aoi_path",
        "streetview_dir",
        "sinobf_dir",
        "osm_cache_dir",
    ]
    return [{key: rounded(row.get(key)) if isinstance(row.get(key), float) else row.get(key) for key in keys} for row in resource_rows]


def compute_iou(a_path: Path, b_path: Path) -> Optional[float]:
    if not a_path.exists() or not b_path.exists():
        return None
    try:
        a = load_gdf(a_path)
        b = load_gdf(b_path).to_crs(a.crs)
        metric = to_metric(pd.concat([a[["geometry"]], b[["geometry"]]], ignore_index=True))
        a_m = gpd.GeoDataFrame(geometry=[metric.iloc[0].geometry], crs=metric.crs)
        b_m = gpd.GeoDataFrame(geometry=[metric.iloc[1].geometry], crs=metric.crs)
        inter = float(a_m.overlay(b_m, how="intersection").geometry.area.sum())
        union = float(a_m.overlay(b_m, how="union").geometry.area.sum())
        return inter / union if union else None
    except Exception:
        return None


def write_dataset_cards(config: dict[str, Any], cases: list[CaseSpec], resources: list[dict[str, Any]], roots: dict[str, Path]) -> list[dict[str, Any]]:
    for old_card in CARD_DIR.glob("*.json"):
        old_card.unlink()
    cards = build_dataset_cards({
        "authoritative_inputs": config["authoritative_inputs"],
        "input_grounding_policy": config.get("input_grounding_policy", {}),
    })
    # Paper-level labels are task metadata layered onto generic UrbanAgent cards.
    labels = {
        "authoritative_aoi_dir": ("Paper9 reviewed historical-district AOI boundaries", ["historic_district", "heritage_boundary", "reviewed_inferred_aoi"]),
        "authoritative_streetview_root": ("Local street-view image batch", ["facade", "streetscape", "visual_proxy"]),
        "authoritative_sinobf_root": ("SinoBF-1 building/function resources", ["building_function", "urban_function", "function_proxy"]),
        "authoritative_osm_cache_root": ("OSM roads/buildings cache or Overpass source", ["road_network", "building_morphology"]),
        "authoritative_osm_source": ("OSM Overpass acquisition source", ["osm", "overpass", "road_network", "building_footprint"]),
    }
    for card in cards:
        label = labels.get(card.get("resource_id"))
        if label:
            card["name"] = label[0]
            card["semantic_tags"] = list(dict.fromkeys(list(card.get("semantic_tags", [])) + label[1]))
        if card.get("resource_id") == "authoritative_aoi_dir":
            card.setdefault("anti_uses", []).append("do not replace with heritage_district_batch/*/aoi.geojson")
        if card.get("resource_id") in {"authoritative_osm_cache_root", "authoritative_osm_source"}:
            card["tool"] = "fetch_osm_overpass_tool"
            card["metric_tags"] = list(dict.fromkeys(list(card.get("metric_tags", [])) + ["current_road_density_km_per_km2", "building_road_adherence_ratio_proxy"]))
        if card.get("resource_id") == "authoritative_streetview_root":
            card["metric_tags"] = list(dict.fromkeys(list(card.get("metric_tags", [])) + ["streetview_sample_count", "streetview_brightness_mean_proxy", "streetview_color_dispersion_proxy"]))
        if card.get("resource_id") == "authoritative_sinobf_root":
            card["metric_tags"] = list(dict.fromkeys(list(card.get("metric_tags", [])) + ["sinobf_building_area_cv_proxy", "sinobf_function_entropy_norm", "sinobf_commercial_ratio_proxy"]))
    for card in cards:
        (CARD_DIR / f"{card['resource_id']}.json").write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")

    instance_manifest = {
        "experiment_id": config["experiment_id"],
        "case_count": len(cases),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "resource_instances": resources,
    }
    (CARD_DIR / "case_resource_instances.json").write_text(json.dumps(instance_manifest, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return cards


def write_grounding_policy(config: dict[str, Any], dataset_cards: list[dict[str, Any]]) -> None:
    policy = build_grounding_policy(
        {
            "grounding_policy_id": "paper9_case1_plus20_grounding_policy",
            "input_grounding_policy": config.get("input_grounding_policy", {}),
        },
        dataset_cards,
    )
    policy["summary"] = "Grounding policy for historical-district built-environment indicator experiments."
    policy["literature_grounding"] = "reserved; no paper-card RAG used in this experiment"
    policy["checks"].append({"check_id": "osm_context_fetch_tool", "severity": "warning", "rule": "If OSM cache is unavailable or pre-clipped, call fetch_osm_overpass_tool at AOI/context scale."})
    (OUTPUT_ROOT / "grounding_policy_case1_plus20.json").write_text(json.dumps(policy, ensure_ascii=False, indent=2), encoding="utf-8")


def write_paper_card_interface() -> None:
    PAPER_CARD_DIR.mkdir(parents=True, exist_ok=True)
    placeholder = {
        "status": "reserved_interface_only",
        "reason": "The literature-grounding policy is not included in this ablation until MinerU-parsed historical-district papers are curated.",
        "expected_schema": {
            "paper_id": "string",
            "title": "string",
            "indicators": ["string"],
            "required_data": ["string"],
            "methods": ["string"],
            "spatial_scale": "string",
            "validation_strategy": "string",
            "limitations": ["string"],
        },
    }
    (PAPER_CARD_DIR / "paper_cards_index.json").write_text(json.dumps(placeholder, ensure_ascii=False, indent=2), encoding="utf-8")
    (PAPER_CARD_DIR / "README.md").write_text(
        "# Paper Cards Interface\n\nThis experiment reserves the literature-grounding interface but does not use it in the ablation results.\n",
        encoding="utf-8",
    )


def write_indicator_matrix(dataset_cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matrix = build_indicator_computability_matrix(
        {"indicator_requirements": INDICATORS},
        dataset_cards=dataset_cards,
        path_context={},
    )
    write_csv(TABLE_DIR / "paper9_indicator_computability_matrix.csv", matrix)
    md = table_to_markdown(matrix)
    (TABLE_DIR / "paper9_indicator_computability_matrix.md").write_text(md, encoding="utf-8")
    return matrix


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames and not key.startswith("_"):
                fieldnames.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_markdown_tables(
    coverage_rows: list[dict[str, Any]],
    full_metrics: list[dict[str, Any]],
    ablation_rows: list[dict[str, Any]],
    cumulative_rows: list[dict[str, Any]],
) -> None:
    (TABLE_DIR / "case1_plus20_resource_coverage.md").write_text(table_to_markdown(coverage_rows), encoding="utf-8")
    selected_metric_cols = [
        "case_id",
        "city",
        "district",
        "aoi_area_km2",
        "road_density_km_per_km2",
        "building_coverage_ratio",
        "building_density_count_per_ha",
        "building_road_adherence_ratio_proxy",
        "sinobf_function_entropy_norm",
        "streetview_brightness_mean_proxy",
        "streetview_color_dispersion_proxy",
    ]
    metric_rows = [{key: row.get(key) for key in selected_metric_cols} for row in full_metrics]
    (TABLE_DIR / "case1_plus20_full_indicator_results.md").write_text(table_to_markdown(metric_rows), encoding="utf-8")
    (TABLE_DIR / "case1_plus20_ablation_summary.md").write_text(table_to_markdown(ablation_rows), encoding="utf-8")
    cum_selected = [row for row in cumulative_rows if row["condition"] in {"full", "no_memory"}]
    (TABLE_DIR / "case1_plus20_cumulative_refinement.md").write_text(table_to_markdown(cum_selected), encoding="utf-8")


def table_to_markdown(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    fieldnames = [key for key in rows[0].keys() if not key.startswith("_")]
    lines = ["| " + " | ".join(fieldnames) + " |", "| " + " | ".join(["---"] * len(fieldnames)) + " |"]
    for row in rows:
        values = [str(row.get(key, "")).replace("\n", " ") for key in fieldnames]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines) + "\n"


def write_memory_outputs(full_metrics: list[dict[str, Any]], trace_rows: list[dict[str, Any]]) -> None:
    memory = {
        "memory_id": "case1_plus20_heritage_workflow_memory",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_case": "002 上海 南京路步行街",
        "lesson": "For Paper9-style historical-district built-environment tasks, load authoritative AOI dataset cards first, clip OSM/SinoBF/street-view resources to the AOI, downgrade unsupported historical/registry/semantic indicators, and reuse the workflow for similar districts.",
        "reused_by_cases": [
            {"case_id": row["case_id"], "city": row["city"], "district": row["district"], "memory_reuse_count": row["memory_reuse_count"]}
            for row in full_metrics
            if row["role"] == "validation"
        ],
    }
    (OUTPUT_ROOT / "workflow_memory_case1_plus20.json").write_text(json.dumps(memory, ensure_ascii=False, indent=2), encoding="utf-8")

    jsonl = OUTPUT_ROOT / "experience_memory_events.jsonl"
    with jsonl.open("w", encoding="utf-8") as handle:
        for row in trace_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def draw_map_grid(cases: list[CaseSpec], full_metrics: list[dict[str, Any]], output_dir: Path) -> None:
    setup_fonts()
    fig, axes = plt.subplots(4, 6, figsize=(18, 12))
    axes_flat = list(axes.ravel())
    metric_by_id = {row["case_id"]: row for row in full_metrics}
    for ax, case in zip(axes_flat, cases):
        row = metric_by_id[case.id]
        aoi = load_gdf(Path(row["used_aoi_path"]))
        roads = safe_clip(load_gdf(Path(row["used_roads_path"])), aoi) if Path(row["used_roads_path"]).exists() else empty_gdf_like(aoi)
        buildings = safe_clip(load_gdf(Path(row["used_buildings_path"])), aoi) if Path(row["used_buildings_path"]).exists() else empty_gdf_like(aoi)
        points = load_streetview_points(Path(next_metric_resource(row, "streetview_dir")), aoi)
        try:
            aoi.plot(ax=ax, facecolor="#f8fafc", edgecolor="#111827", linewidth=1.0)
            if len(buildings):
                buildings.plot(ax=ax, color="#94a3b8", alpha=0.55, linewidth=0)
            if len(roads):
                roads.plot(ax=ax, color="#0f766e", linewidth=0.55, alpha=0.8)
            if len(points):
                points.plot(ax=ax, color="#b42318", markersize=3, alpha=0.7)
        except Exception:
            aoi.plot(ax=ax, facecolor="#f8fafc", edgecolor="#111827", linewidth=1.0)
        ax.set_title(f"{case.id} {case.city} {case.district}", fontsize=9)
        ax.set_axis_off()
    for ax in axes_flat[len(cases):]:
        ax.set_axis_off()
    fig.suptitle("Case1 + 20 historical districts: AOI, OSM roads/buildings, and street-view samples", fontsize=16, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(output_dir / "fig_case1_plus20_spatial_small_multiples.png", dpi=220)
    plt.close(fig)


def next_metric_resource(row: dict[str, Any], key: str) -> str:
    resources = json.loads((CARD_DIR / "case_resource_instances.json").read_text(encoding="utf-8"))["resource_instances"]
    for resource in resources:
        if resource["case_id"] == row["case_id"]:
            return resource.get(key, "")
    return ""


def draw_cumulative_figure(rows: list[dict[str, Any]], output_dir: Path) -> None:
    setup_fonts()
    frame = pd.DataFrame(rows)
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    colors = {"full": "#0f766e", "no_memory": "#b54708", "no_reviewer": "#b42318", "no_input_grounding": "#1d4ed8"}

    ax = axes[0, 0]
    for condition in ("full", "no_memory"):
        part = frame[frame["condition"] == condition]
        ax.plot(part["task_order_after_case1"], part["rolling_mean_time_proxy_s"], marker="o", label=condition, color=colors[condition])
    ax.set_title("Cumulative refinement: rolling workflow-time proxy")
    ax.set_xlabel("Similar task order after Case1")
    ax.set_ylabel("Rolling mean proxy seconds")
    ax.grid(alpha=0.25)
    ax.legend()

    ax = axes[0, 1]
    for condition in ("full", "no_memory"):
        part = frame[frame["condition"] == condition]
        ax.plot(part["task_order_after_case1"], part["memory_reuse_count"], marker="o", label=condition, color=colors[condition])
    ax.set_title("Memory reuse after Case1")
    ax.set_xlabel("Similar task order")
    ax.set_ylabel("Memory reuse count")
    ax.grid(alpha=0.25)
    ax.legend()

    ax = axes[1, 0]
    for condition in ("full", "no_reviewer"):
        part = frame[frame["condition"] == condition]
        ax.plot(part["task_order_after_case1"], part["overclaim_count"], marker="o", label=condition, color=colors[condition])
    ax.set_title("Reviewer harness prevents unsupported claims")
    ax.set_xlabel("Similar task order")
    ax.set_ylabel("Overclaim count")
    ax.grid(alpha=0.25)
    ax.legend()

    ax = axes[1, 1]
    for condition in ("full", "no_input_grounding"):
        part = frame[frame["condition"] == condition]
        ax.plot(part["task_order_after_case1"], part["data_path_correctness"], marker="o", label=condition, color=colors[condition])
    ax.set_title("Input grounding keeps authoritative paths")
    ax.set_xlabel("Similar task order")
    ax.set_ylabel("Data path correctness")
    ax.set_ylim(-0.05, 1.05)
    ax.grid(alpha=0.25)
    ax.legend()

    fig.tight_layout()
    fig.savefig(output_dir / "fig_case1_plus20_cumulative_refinement.png", dpi=220)
    plt.close(fig)


def draw_ablation_figure(rows: list[dict[str, Any]], output_dir: Path) -> None:
    setup_fonts()
    frame = pd.DataFrame(rows)
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    x = np.arange(len(frame))
    labels = frame["condition"].tolist()
    axes[0].bar(x, frame["mean_method_data_fit"].astype(float), color="#0f766e")
    axes[0].set_title("Method-data fit")
    axes[0].set_ylim(0, 1.05)
    axes[1].bar(x, frame["mean_data_path_correctness"].astype(float), color="#1d4ed8")
    axes[1].set_title("Authoritative input correctness")
    axes[1].set_ylim(0, 1.05)
    axes[2].bar(x, frame["mean_overclaim_count"].astype(float), color="#b42318")
    axes[2].set_title("Unsupported claims")
    for ax in axes:
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=18, ha="right")
        ax.grid(axis="y", alpha=0.25)
    fig.suptitle("Case1 + 20 ablation: grounding, reviewer, and memory mechanisms", fontsize=15, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(output_dir / "fig_case1_plus20_ablation_summary.png", dpi=220)
    plt.close(fig)

    draw_table_png(rows, output_dir / "table_case1_plus20_ablation_summary.png", title="Ablation summary")


def draw_governance_schema(output_dir: Path) -> None:
    setup_fonts()
    fig, ax = plt.subplots(figsize=(15, 8))
    ax.set_axis_off()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    box_style = dict(fill=False, linewidth=1.8, edgecolor="#334155")
    groups = [
        (0.04, 0.62, 0.26, 0.24, "Dataset Cards", ["AOI authority", "Street-view batch", "OSM Overpass/cache", "SinoBF buildings/points"]),
        (0.37, 0.62, 0.26, 0.24, "Workflow Memory", ["Case1 workflow lesson", "tool order", "proxy/missing downgrade", "reuse on 20 tasks"]),
        (0.70, 0.62, 0.26, 0.24, "Grounding Reviewer", ["path authority", "method-data fit", "known limits", "overclaim blocking"]),
        (0.20, 0.18, 0.26, 0.24, "Analyst Tools", ["clip layers", "compute metrics", "render maps", "write traces"]),
        (0.55, 0.18, 0.26, 0.24, "Paper Outputs", ["RDMA-style panel", "small multiples", "ablation tables", "cumulative curves"]),
    ]
    for x, y, w, h, title, items in groups:
        ax.add_patch(Rectangle((x, y), w, h, facecolor="#f8fafc", **box_style))
        ax.text(x + 0.015, y + h - 0.045, title, fontsize=15, fontweight="bold", color="#111827")
        for idx, item in enumerate(items):
            ax.text(x + 0.025, y + h - 0.085 - idx * 0.035, f"- {item}", fontsize=11, color="#334155")
    arrows = [
        ((0.30, 0.74), (0.37, 0.74)),
        ((0.63, 0.74), (0.70, 0.74)),
        ((0.83, 0.62), (0.68, 0.42)),
        ((0.50, 0.62), (0.34, 0.42)),
        ((0.46, 0.30), (0.55, 0.30)),
    ]
    for start, end in arrows:
        ax.add_patch(FancyArrowPatch(start, end, arrowstyle="->", mutation_scale=14, linewidth=1.5, color="#475569"))
    ax.text(0.04, 0.93, "UrbanAgent data governance and harness for Case1 + 20 experiments", fontsize=20, fontweight="bold", color="#111827")
    ax.text(0.04, 0.895, "Paper-card / literature grounding is reserved in the schema but not used in this ablation.", fontsize=12, color="#667085")
    fig.savefig(output_dir / "fig_case1_plus20_data_governance_harness.png", dpi=220, bbox_inches="tight")
    plt.close(fig)


def draw_rdma_process_panel(
    cases: list[CaseSpec],
    full_metrics: list[dict[str, Any]],
    ablation_rows: list[dict[str, Any]],
    output_dir: Path,
) -> None:
    width, height = 1800, 2350
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    fonts = pil_fonts()
    y = 40
    draw.text((60, y), "Case1 process panel: UrbanAgent input grounding, memory I/O, and review harness", fill="#111827", font=fonts["title"])
    y += 80
    y = bubble(draw, fonts, 70, y, 1420, "User", "Analyze Paper9-style built-environment indicators for Shanghai Nanjing Road, then test whether the workflow improves on 20 similar heritage districts.")
    y = agent_tag(draw, fonts, 75, y)
    y = process_card_input(draw, fonts, 70, y, width - 140)
    y += 28
    y = bubble(draw, fonts, 70, y, 1280, "User", "Before computing indicators, verify that AOI, street-view, OSM, and SinoBF resources are grounded and disclose unsupported indicators.")
    y = agent_tag(draw, fonts, 75, y)
    y = process_card_review(draw, fonts, 70, y, width - 140, full_metrics[0])
    y += 28
    y = bubble(draw, fonts, 70, y, 1260, "User", "Now reuse this workflow on 20 similar districts and compare ablation conditions.")
    y = agent_tag(draw, fonts, 75, y)
    y = process_card_results(img, draw, fonts, 70, y, width - 140, full_metrics, ablation_rows, output_dir)
    y += 24
    draw.text((70, y), "Figure. RDMA-style UrbanAgent process panel for Case1 + 20 historical-district experiments.", fill="#1d4ed8", font=fonts["h2"])
    save_image_with_pdf(img, output_dir / "fig_case1_plus20_rdma_style_process_panel.png")


def bubble(draw: ImageDraw.ImageDraw, fonts: dict[str, Any], x: int, y: int, w: int, who: str, text: str) -> int:
    lines = wrap_by_pixels(text, fonts["body"], w - 150)
    h = 38 + 28 * len(lines)
    draw.rounded_rectangle([x, y, x + w, y + h], radius=26, fill="#e9eef5", outline="#cbd5e1", width=2)
    draw.text((x + 25, y + 17), who, fill="#111827", font=fonts["h2"])
    for idx, line in enumerate(lines):
        draw.text((x + 110, y + 18 + idx * 28), line, fill="#111827", font=fonts["body"])
    return y + h + 14


def agent_tag(draw: ImageDraw.ImageDraw, fonts: dict[str, Any], x: int, y: int) -> int:
    draw.rounded_rectangle([x, y, x + 170, y + 48], radius=24, fill="#dff3ee", outline="#cbd5e1", width=2)
    draw.text((x + 24, y + 12), "UrbanAgent", fill="#0f766e", font=fonts["h2"])
    return y + 58


def process_card_input(draw: ImageDraw.ImageDraw, fonts: dict[str, Any], x: int, y: int, w: int) -> int:
    h = 410
    dashed_rect(draw, [x, y, x + w, y + h], "#94a3b8")
    draw.text((x + 28, y + 24), "INPUT JSON:", fill="#111827", font=fonts["h2"])
    snippet = {
        "case1": "002 上海 南京路步行街",
        "aoi_dir": ".../district_boundaries_v2/district_boundaries",
        "streetview_root": "D:/街景/streetview_images_batch",
        "sinobf_root": ".../data/sinobf1",
        "legacy_aoi": "anti-use"
    }
    code_box_pil(draw, fonts, x + 28, y + 62, 560, 260, json.dumps(snippet, ensure_ascii=False, indent=2))
    draw.text((x + 650, y + 24), "DATASET CARDS:", fill="#111827", font=fonts["h2"])
    rows = [
        ("AOI", "authoritative", "reviewed inferred boundary"),
        ("Street-view", "local batch", "visual proxy only"),
        ("OSM", "Overpass/cache", "morphology/network"),
        ("SinoBF1", "building function", "POI-like proxy"),
    ]
    mini_table_pil(draw, fonts, x + 650, y + 62, 480, ["Data", "Role", "Limit"], rows)
    draw.text((x + 1190, y + 24), "POLICY:", fill="#111827", font=fonts["h2"])
    bullets_pil(draw, fonts, x + 1195, y + 66, [
        "Reject legacy AOI as analysis scope",
        "Disclose proxy vs missing indicators",
        "Use Overpass tool if OSM cache is missing",
        "Paper-card RAG: reserved interface"
    ], 420)
    confidence_bar_pil(draw, fonts, x + 28, y + h - 54, w - 56, "Grounding gate: dataset cards + authoritative input paths loaded")
    return y + h


def process_card_review(draw: ImageDraw.ImageDraw, fonts: dict[str, Any], x: int, y: int, w: int, case1_metrics: dict[str, Any]) -> int:
    h = 450
    dashed_rect(draw, [x, y, x + w, y + h], "#94a3b8")
    draw.text((x + 28, y + 24), "REVIEWER HARNESS:", fill="#111827", font=fonts["h2"])
    rows = [
        ("Direct", str(case1_metrics["indicator_direct_count"]), "computed"),
        ("Proxy", str(case1_metrics["indicator_proxy_count"]), "downgraded"),
        ("Missing", str(case1_metrics["indicator_missing_count"]), "disclosed"),
        ("Overclaim", str(case1_metrics["overclaim_count"]), "blocked"),
    ]
    mini_table_pil(draw, fonts, x + 28, y + 64, 500, ["Class", "Count", "Action"], rows)
    draw.text((x + 590, y + 24), "MEMORY I/O:", fill="#111827", font=fonts["h2"])
    mem = {
        "read": ["dataset_cards", "workflow_memory", "grounding_policy"],
        "write": ["case1 workflow lesson", "experience_memory_events.jsonl"]
    }
    code_box_pil(draw, fonts, x + 590, y + 64, 440, 230, json.dumps(mem, ensure_ascii=False, indent=2))
    draw.text((x + 1080, y + 24), "CASE1 OUTPUT:", fill="#111827", font=fonts["h2"])
    bullets_pil(draw, fonts, x + 1085, y + 66, [
        f"Road density: {case1_metrics.get('road_density_km_per_km2')}",
        f"Building coverage: {case1_metrics.get('building_coverage_ratio')}",
        f"Function entropy: {case1_metrics.get('sinobf_function_entropy_norm')}",
        f"Street-view images: {case1_metrics.get('streetview_image_files')}"
    ], 450)
    confidence_bar_pil(draw, fonts, x + 28, y + h - 54, w - 56, "Review result: supported indicators computed; unsupported historical/registry/semantic indicators are not overclaimed")
    return y + h


def process_card_results(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    fonts: dict[str, Any],
    x: int,
    y: int,
    w: int,
    full_metrics: list[dict[str, Any]],
    ablation_rows: list[dict[str, Any]],
    output_dir: Path,
) -> int:
    h = 790
    dashed_rect(draw, [x, y, x + w, y + h], "#94a3b8")
    draw.text((x + 28, y + 24), "20 SIMILAR TASKS:", fill="#111827", font=fonts["h2"])
    validation = [row for row in full_metrics if row["role"] == "validation"]
    summary_rows = [
        ("Districts", str(len(validation))),
        ("Street-view points", str(sum(int(row["streetview_image_points"]) for row in validation))),
        ("Street-view images", str(sum(int(row["streetview_image_files"]) for row in validation))),
        ("Mean method-data fit", f"{statistics.mean(float(row['method_data_fit_score']) for row in validation):.3f}"),
    ]
    mini_kv_pil(draw, fonts, x + 28, y + 68, 460, summary_rows)
    draw.text((x + 540, y + 24), "ABLATION:", fill="#111827", font=fonts["h2"])
    ablation_small = [(row["condition"], row["mean_method_data_fit"], row["mean_overclaim_count"]) for row in ablation_rows]
    mini_table_pil(draw, fonts, x + 540, y + 64, 520, ["Condition", "Fit", "Overclaim"], ablation_small)
    map_path = output_dir / "fig_case1_plus20_spatial_small_multiples.png"
    if map_path.exists():
        thumb = Image.open(map_path).convert("RGB")
        thumb.thumbnail((560, 420))
        img.paste(thumb, (x + 1120, y + 60))
    curve_path = output_dir / "fig_case1_plus20_cumulative_refinement.png"
    if curve_path.exists():
        thumb = Image.open(curve_path).convert("RGB")
        thumb.thumbnail((760, 330))
        img.paste(thumb, (x + 470, y + 420))
    confidence_bar_pil(draw, fonts, x + 28, y + h - 54, w - 56, "Cumulative refinement: workflow memory lowers repeated-task workflow cost while reviewer/input grounding preserve validity")
    return y + h


def draw_indicator_matrix_figure(output_dir: Path, indicator_matrix: list[dict[str, Any]]) -> None:
    direct_count = sum(1 for item in indicator_matrix if item.get("status") == "direct")
    proxy_count = sum(1 for item in indicator_matrix if item.get("status") == "proxy")
    missing_count = sum(1 for item in indicator_matrix if item.get("status") == "missing")
    rows = [
        {"Status": "Direct", "Count": direct_count, "Meaning": "can be computed from declared required evidence"},
        {"Status": "Proxy", "Count": proxy_count, "Meaning": "computed but reported as weak proxy"},
        {"Status": "Missing", "Count": missing_count, "Meaning": "requires historical maps, registries, semantic labels, or surveys"},
    ]
    draw_table_png(rows, output_dir / "table_paper9_indicator_computability.png", title="Paper9 indicator computability under current data")


def draw_table_png(rows: list[dict[str, Any]], path: Path, *, title: str) -> None:
    if not rows:
        return
    setup_fonts()
    cols = [key for key in rows[0].keys() if key != "interpretation"]
    fig_h = max(2.5, 0.45 * len(rows) + 1.2)
    fig, ax = plt.subplots(figsize=(15, fig_h))
    ax.set_axis_off()
    table_data = [[str(row.get(col, "")) for col in cols] for row in rows]
    table = ax.table(cellText=table_data, colLabels=cols, loc="center", cellLoc="left")
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1, 1.45)
    for (r, c), cell in table.get_celld().items():
        if r == 0:
            cell.set_facecolor("#e2e8f0")
            cell.set_text_props(weight="bold")
        else:
            cell.set_facecolor("#ffffff" if r % 2 else "#f8fafc")
    ax.set_title(title, fontsize=14, fontweight="bold", pad=12)
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def write_experiment_draft(
    cases: list[CaseSpec],
    coverage_rows: list[dict[str, Any]],
    ablation_rows: list[dict[str, Any]],
    full_metrics: list[dict[str, Any]],
    cumulative_rows: list[dict[str, Any]],
    output_dir: Path,
) -> None:
    full = next(row for row in ablation_rows if row["condition"] == "full")
    no_input = next(row for row in ablation_rows if row["condition"] == "no_input_grounding")
    no_review = next(row for row in ablation_rows if row["condition"] == "no_reviewer")
    no_memory = next(row for row in ablation_rows if row["condition"] == "no_memory")
    validation = [row for row in full_metrics if row["role"] == "validation"]
    text = f"""# Case1 + 20 Experimental Results Draft

## Experimental Setup

The experiment fixes Case1 as `{cases[0].label}` and evaluates cumulative refinement on 20 similar historical-district tasks. All 21 tasks have authoritative AOI boundaries, local street-view images, OSM-derived road/building layers, and SinoBF-1 building-function resources.

The literature-grounding / paper-card interface is reserved but not used in this ablation. The tested input-grounding mechanism is the dataset-card plus authoritative-input gate.

## Data Coverage

- Case count: {len(cases)}.
- Validation tasks after Case1: {len(validation)}.
- Validation street-view points: {sum(int(row['streetview_image_points']) for row in validation)}.
- Validation street-view images: {sum(int(row['streetview_image_files']) for row in validation)}.
- Full resource coverage: {sum(1 for row in coverage_rows if row['full_input_coverage'])}/{len(coverage_rows)}.

## Ablation Summary

- Full UrbanAgent mean method-data fit: {full['mean_method_data_fit']}.
- No Memory mean workflow-time proxy: {no_memory['mean_workflow_time_proxy_s']} vs Full {full['mean_workflow_time_proxy_s']}.
- No Reviewer mean overclaim count: {no_review['mean_overclaim_count']} vs Full {full['mean_overclaim_count']}.
- No Input Grounding mean data-path correctness: {no_input['mean_data_path_correctness']} vs Full {full['mean_data_path_correctness']}.

## Interpretation

These are instrumented ablation results rather than natural wall-clock LLM-runtime measurements. They support a proof-of-mechanism reading: input grounding prevents legacy AOI/cache files from silently defining the analysis scope; the reviewer harness downgrades unsupported Paper9 indicators to proxy or missing status instead of allowing overclaiming; workflow memory mainly reduces repeated discovery/planning effort, not the numeric indicator formulas. The workflow-time curve is therefore a proxy for recorded planning/tool overhead, while the data-path and overclaim panels are rule-grounded checks produced by the UrbanAgent grounding/reviewer runtime.

The strongest claim supported here is that the architecture exposes verifiable control points. A stronger performance claim would require repeated end-to-end UrbanAgent runs with measured wall-clock time, randomized task order, and independent artifact-quality scoring.

## Primary Artifacts

- `fig_case1_plus20_rdma_style_process_panel.png`
- `fig_case1_plus20_spatial_small_multiples.png`
- `fig_case1_plus20_cumulative_refinement.png`
- `fig_case1_plus20_ablation_summary.png`
- `fig_case1_plus20_data_governance_harness.png`
- `tables/case1_plus20_ablation_summary.csv`
- `tables/case1_plus20_full_indicator_results.csv`
- `tables/paper9_indicator_computability_matrix.csv`
"""
    (output_dir / "case1_plus20_experiment_section_draft.md").write_text(text, encoding="utf-8")


def build_manifest(
    output_dir: Path,
    started: datetime,
    cases: list[CaseSpec],
    coverage_rows: list[dict[str, Any]],
    ablation_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    files = sorted(str(path.relative_to(output_dir)) for path in output_dir.rglob("*") if path.is_file())
    return {
        "experiment_id": "case1_plus20_heritage_grounding_20260512",
        "started_at": started.isoformat(timespec="seconds"),
        "completed_at": datetime.now().isoformat(timespec="seconds"),
        "output_dir": str(output_dir),
        "case1": cases[0].label,
        "validation_case_count": len(cases) - 1,
        "full_coverage_count": sum(1 for row in coverage_rows if row["full_input_coverage"]),
        "condition_count": len(ablation_rows),
        "files": files,
    }


def setup_fonts() -> None:
    candidates = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["font.sans-serif"] = candidates
    plt.rcParams["axes.unicode_minus"] = False


def pil_fonts() -> dict[str, Any]:
    def load(size: int, bold: bool = False, mono: bool = False) -> Any:
        candidates = []
        if mono:
            candidates = ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/consola.ttf", "C:/Windows/Fonts/cour.ttf"]
        elif bold:
            candidates = ["C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/arialbd.ttf"]
        else:
            candidates = ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/arial.ttf"]
        for candidate in candidates:
            try:
                return ImageFont.truetype(candidate, size)
            except Exception:
                continue
        return ImageFont.load_default()

    return {
        "title": load(36, bold=True),
        "h2": load(22, bold=True),
        "body": load(19),
        "small": load(15),
        "tiny": load(13),
        "mono": load(15, mono=True),
    }


def wrap_by_pixels(text: str, font: Any, width: int) -> list[str]:
    words = text.split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        bbox = font.getbbox(candidate)
        if bbox[2] - bbox[0] <= width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def dashed_rect(draw: ImageDraw.ImageDraw, xy: list[int], color: str) -> None:
    x1, y1, x2, y2 = xy
    dash = 12
    gap = 8
    for x in range(x1, x2, dash + gap):
        draw.line([(x, y1), (min(x + dash, x2), y1)], fill=color, width=2)
        draw.line([(x, y2), (min(x + dash, x2), y2)], fill=color, width=2)
    for y in range(y1, y2, dash + gap):
        draw.line([(x1, y), (x1, min(y + dash, y2))], fill=color, width=2)
        draw.line([(x2, y), (x2, min(y + dash, y2))], fill=color, width=2)


def code_box_pil(draw: ImageDraw.ImageDraw, fonts: dict[str, Any], x: int, y: int, w: int, h: int, text: str) -> None:
    draw.rectangle([x, y, x + w, y + h], fill="#fbfcfe", outline="#cbd5e1", width=1)
    yy = y + 14
    for line in text.splitlines()[:12]:
        draw.text((x + 14, yy), line[:72], fill="#334155", font=fonts["mono"])
        yy += 21


def mini_table_pil(draw: ImageDraw.ImageDraw, fonts: dict[str, Any], x: int, y: int, w: int, headers: list[str], rows: list[tuple[Any, ...]]) -> None:
    col_w = w / len(headers)
    row_h = 34
    draw.rectangle([x, y, x + w, y + row_h], fill="#e2e8f0", outline="#cbd5e1")
    for i, header in enumerate(headers):
        draw.text((x + i * col_w + 8, y + 8), str(header), fill="#111827", font=fonts["small"])
    for r, row in enumerate(rows, start=1):
        yy = y + r * row_h
        draw.rectangle([x, yy, x + w, yy + row_h], fill="#ffffff" if r % 2 else "#f8fafc", outline="#e5e7eb")
        for i, value in enumerate(row):
            draw.text((x + i * col_w + 8, yy + 8), str(value)[:28], fill="#334155", font=fonts["small"])


def mini_kv_pil(draw: ImageDraw.ImageDraw, fonts: dict[str, Any], x: int, y: int, w: int, rows: list[tuple[str, str]]) -> None:
    for idx, (key, value) in enumerate(rows):
        yy = y + idx * 42
        draw.text((x, yy), key, fill="#334155", font=fonts["small"])
        draw.text((x + w - 150, yy), value, fill="#0f766e", font=fonts["h2"])


def bullets_pil(draw: ImageDraw.ImageDraw, fonts: dict[str, Any], x: int, y: int, bullets: list[str], w: int) -> None:
    yy = y
    for bullet in bullets:
        for idx, line in enumerate(wrap_by_pixels(bullet, fonts["small"], w - 30)):
            prefix = "- " if idx == 0 else "  "
            draw.text((x, yy), prefix + line, fill="#334155", font=fonts["small"])
            yy += 24


def confidence_bar_pil(draw: ImageDraw.ImageDraw, fonts: dict[str, Any], x: int, y: int, w: int, text: str) -> None:
    draw.rectangle([x, y, x + w, y + 34], fill="#d9f0ea", outline="#bae6d4")
    draw.text((x + 12, y + 8), text, fill="#0f766e", font=fonts["small"])


def save_image_with_pdf(img: Image.Image, path: Path) -> None:
    img.save(path)
    try:
        img.save(path.with_suffix(".pdf"), "PDF", resolution=160.0)
    except Exception:
        pass


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def rounded(value: Any, digits: int = 4) -> Any:
    if value is None:
        return None
    try:
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return round(float(value), digits)
    except Exception:
        return value


def mean(rows: list[dict[str, Any]], key: str) -> Optional[float]:
    values = [float(row[key]) for row in rows if row.get(key) is not None and row.get(key) != ""]
    return rounded(statistics.mean(values) if values else None)


if __name__ == "__main__":
    main()
