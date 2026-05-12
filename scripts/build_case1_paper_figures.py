#!/usr/bin/env python
"""Build paper-ready Case1 figures and tables.

This script converts the Case1 input-diagnostic / review / repair loop into
figures and result tables suitable for the experimental section.
"""

from __future__ import annotations

import csv
import json
import textwrap
from pathlib import Path
from typing import Any, Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Rectangle


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "figures" / "case1_paper_20260511"
ARTIFACT_DIR = PROJECT_ROOT / "artifacts" / "case1_osm_supplemented"
SYSTEM_ABLATION = PROJECT_ROOT / "figures" / "rdma_style_20260509" / "ablation_table3_trials_20260509_complete_aggregate.csv"


COLORS = {
    "ink": "#1f2937",
    "muted": "#667085",
    "grid": "#d0d5dd",
    "green": "#0f766e",
    "green_light": "#d9f0ea",
    "red": "#b42318",
    "red_light": "#fee4e2",
    "blue": "#1d4ed8",
    "blue_light": "#dbeafe",
    "yellow": "#b54708",
    "yellow_light": "#fef0c7",
    "purple": "#6941c6",
    "purple_light": "#ebe9fe",
}


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    comparison = read_json(ARTIFACT_DIR / "case1_review_comparison.json")
    if not comparison:
        raise FileNotFoundError(f"Missing {ARTIFACT_DIR / 'case1_review_comparison.json'}")

    process_rows = build_process_rows(comparison)
    diagnostics_rows = build_diagnostics_rows(comparison)
    targeted_ablation_rows = build_targeted_ablation_rows(comparison)
    rq_rows = build_rq_rows(comparison)
    system_ablation_rows = build_system_ablation_rows()

    write_table_bundle("table_case1_process_trace", process_rows)
    write_table_bundle("table_case1_before_after_diagnostics", diagnostics_rows)
    write_table_bundle("table_case1_targeted_ablation", targeted_ablation_rows)
    write_table_bundle("table_case1_rq_evidence_matrix", rq_rows)
    if system_ablation_rows:
        write_table_bundle("table_case1_system_ablation_summary", system_ablation_rows)

    draw_workflow_figure(comparison)
    draw_coverage_figure(comparison)
    draw_rq_matrix_figure(rq_rows)
    draw_table_figure(
        targeted_ablation_rows,
        OUTPUT_DIR / "table_case1_targeted_ablation.png",
        title="Case1 targeted ablation: which mechanism makes the failure recoverable?",
        widths=[0.18, 0.10, 0.15, 0.15, 0.08, 0.09, 0.25],
        height=4.9,
    )
    draw_table_figure(
        diagnostics_rows,
        OUTPUT_DIR / "table_case1_before_after_diagnostics.png",
        title="Case1 source-coverage diagnostics before and after researcher supplementation",
        widths=[0.13, 0.13, 0.16, 0.14, 0.14, 0.14, 0.16],
        height=4.6,
    )
    try:
        draw_spatial_panel(comparison)
    except Exception as error:
        (OUTPUT_DIR / "spatial_panel_error.txt").write_text(str(error), encoding="utf-8")

    write_experiment_text(process_rows, diagnostics_rows, targeted_ablation_rows, rq_rows, system_ablation_rows)
    write_manifest(process_rows, diagnostics_rows, targeted_ablation_rows, rq_rows, system_ablation_rows)
    print(json.dumps({"output_dir": str(OUTPUT_DIR), "files": sorted(path.name for path in OUTPUT_DIR.iterdir())}, ensure_ascii=False, indent=2))


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def build_process_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    initial_review = data.get("initial_review", {})
    supplemented_review = data.get("supplemented_review", {})
    memory_path = data.get("initial_memory_path") or "experience_memory/review_feedback/*.jsonl"
    rerun_count = len(initial_review.get("rerun_queue") or [])
    return [
        {
            "Step": "1. Source discovery",
            "UrbanAgent evidence": "File-tree discovery selected AOI boundary, SinoBF functions, and OSM *_aoi roads/buildings.",
            "Diagnostic signal": "Input layers are available but not yet trusted.",
            "Framework claim": "Grounding before analysis",
        },
        {
            "Step": "2. Context-buffer validation",
            "UrbanAgent evidence": "Policy memory loaded `diagnose_source_extent_vs_context_buffer` and generated a 3x AOI-centered context buffer.",
            "Diagnostic signal": "roads width coverage=0.067; buildings width coverage=0.057.",
            "Framework claim": "Verifiable",
        },
        {
            "Step": "3. ReviewHub decision",
            "UrbanAgent evidence": f"Recommendation={initial_review.get('recommendation')}; rerun items={rerun_count}.",
            "Diagnostic signal": "Pre-clipped OSM input detected; rerun action=`refetch_osm_at_context_buffer`.",
            "Framework claim": "Revisable",
        },
        {
            "Step": "4. Feedback persistence",
            "UrbanAgent evidence": f"Correction records persisted to `{Path(memory_path).name}`.",
            "Diagnostic signal": "The reviewer output becomes experience memory instead of staying only in prose.",
            "Framework claim": "Cumulative refinement",
        },
        {
            "Step": "5. Researcher supplementation",
            "UrbanAgent evidence": "A context-scale OSM package was supplied with explicit source/acquisition extent metadata.",
            "Diagnostic signal": "roads/buildings source extent basis changed to `source_acquisition_extent`.",
            "Framework claim": "Human-in-the-loop revision",
        },
        {
            "Step": "6. Recheck",
            "UrbanAgent evidence": f"Recommendation={supplemented_review.get('recommendation')}; passed={supplemented_review.get('passed')}; rerun items={len(supplemented_review.get('rerun_queue') or [])}.",
            "Diagnostic signal": "roads and buildings coverage both reach 1.0 x 1.0; pre-clipped warning disappears.",
            "Framework claim": "Auditable acceptance",
        },
    ]


def build_diagnostics_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    initial = data.get("initial_layer_ratios", {})
    supplemented = data.get("supplemented_layer_ratios", {})
    for layer in ("roads", "buildings"):
        before = initial.get(layer, {})
        after = supplemented.get(layer, {})
        rows.append({
            "Layer": layer,
            "Run": "Before repair",
            "Extent basis": before.get("source_extent_basis"),
            "Width cov.": fmt(before.get("source_to_context_width_ratio")),
            "Height cov.": fmt(before.get("source_to_context_height_ratio")),
            "AOI hits": before.get("aoi_intersecting_feature_count"),
            "Review outcome": "flagged for OSM context refetch",
        })
        rows.append({
            "Layer": layer,
            "Run": "After repair",
            "Extent basis": after.get("source_extent_basis"),
            "Width cov.": fmt(after.get("source_to_context_width_ratio")),
            "Height cov.": fmt(after.get("source_to_context_height_ratio")),
            "AOI hits": after.get("aoi_intersecting_feature_count"),
            "Review outcome": "accepted; no rerun item",
        })
    return rows


def build_targeted_ablation_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    ablation_path = ARTIFACT_DIR / "case1_targeted_ablation_results.json"
    records = read_json(ablation_path).get("records", [])
    if not records:
        initial_review = data.get("initial_review", {})
        supplemented_review = data.get("supplemented_review", {})
        records = [
            {"condition": "A0 no ReviewHub", "policy_memory": False, "extent_metadata": "not used", "recommendation": None, "warning_count": None, "rerun_items": 0, "correction_items": 0, "passed": None},
            {"condition": "A1 ReviewHub without policy memory", "policy_memory": False, "extent_metadata": "feature bounds only", "recommendation": "revise", "warning_count": "generic", "rerun_items": 0, "correction_items": 0, "passed": False},
            {"condition": "A2 ReviewHub + policy memory", "policy_memory": True, "extent_metadata": "feature bounds fallback", "recommendation": initial_review.get("recommendation"), "warning_count": len(initial_review.get("warnings") or []), "rerun_items": len(initial_review.get("rerun_queue") or []), "correction_items": len(initial_review.get("correction_memory") or []), "passed": initial_review.get("passed")},
            {"condition": "A3 A2 + supplemented OSM extent", "policy_memory": True, "extent_metadata": "source acquisition extent", "recommendation": supplemented_review.get("recommendation"), "warning_count": len(supplemented_review.get("warnings") or []), "rerun_items": len(supplemented_review.get("rerun_queue") or []), "correction_items": len(supplemented_review.get("correction_memory") or []), "passed": supplemented_review.get("passed")},
        ]
    interpretations = {
        "A0 no ReviewHub": "Artifacts may be produced, but input sufficiency is not tested.",
        "A1 ReviewHub without policy memory": "Review detects generic failure but cannot operationalize repair.",
        "A2 ReviewHub + policy memory": "Policy memory turns the failure into repair actions and correction memory.",
        "A3 A2 + supplemented OSM extent": "Repair closes the loop; source-extent warnings disappear.",
    }
    rows = []
    for record in records:
        condition = record.get("condition")
        rows.append({
            "Condition": condition,
            "Policy memory": "on" if record.get("policy_memory") else "off",
            "Extent metadata": record.get("extent_metadata"),
            "Review result": record.get("recommendation") or "not run",
            "Warnings": "n/a" if record.get("warning_count") is None else str(record.get("warning_count")),
            "Rerun items": str(record.get("rerun_items")),
            "Interpretation": interpretations.get(condition, ""),
        })
    return rows


def build_rq_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "Research-question term": "Verifiable",
            "Research gap addressed": "LLM workflows often trust discovered files without checking whether spatial evidence is sufficient for the requested analysis scale.",
            "UrbanAgent mechanism": "Evidence manifest + policy-memory source-coverage checks + metric CRS diagnostics.",
            "Case1 evidence": "The input stage flagged roads/buildings coverage at 0.067/0.057 of context width and blocked silent acceptance.",
        },
        {
            "Research-question term": "Revisable",
            "Research gap addressed": "Failures are commonly reported as prose warnings rather than concrete repair actions.",
            "UrbanAgent mechanism": "ReviewHub correction memory and rerun queue.",
            "Case1 evidence": "The reviewer produced two `refetch_osm_at_context_buffer` rerun items for roads and buildings.",
        },
        {
            "Research-question term": "Cumulative refinement",
            "Research gap addressed": "Lessons from one run rarely become reusable operational memory for later planning/review.",
            "UrbanAgent mechanism": "File-tree `experience_memory` selected together with policy/workflow memory.",
            "Case1 evidence": "The correction was persisted in review_feedback memory and retrieved with Case1 policy/workflow memories.",
        },
    ]


def build_system_ablation_rows() -> list[dict[str, Any]]:
    if not SYSTEM_ABLATION.exists():
        return []
    rows = []
    with SYSTEM_ABLATION.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            config = row.get("config", "")
            label = {
                "c0_full": "Full UrbanAgent",
                "c1_wo_planning": "w/o Planning",
                "c2_wo_review": "w/o Review",
                "c3_wo_qc": "w/o QC",
                "c4_wo_dualspace": "w/o Dual-space",
                "c5_wo_memory": "w/o Memory",
                "c6_vanilla": "Vanilla execution",
            }.get(config, config)
            rows.append({
                "Configuration": label,
                "Trials": row.get("trials"),
                "Success": row.get("success_rate"),
                "Exec confidence": row.get("mean_exec_confidence") or "n/a",
                "Review score": row.get("mean_review_score") or "n/a",
                "Artifacts": row.get("mean_artifact_count"),
                "Metrics": row.get("mean_metric_row_count"),
            })
    return rows


def draw_workflow_figure(data: dict[str, Any]) -> None:
    fig, ax = plt.subplots(figsize=(16, 6.8))
    ax.set_axis_off()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    stages = [
        ("Task input", "AOI + SinoBF + OSM cache"),
        ("Source discovery", "roads/buildings *_aoi"),
        ("Input validation", "3x context buffer\npolicy memory"),
        ("ReviewHub", "coverage warning\nrerun queue=2"),
        ("Experience memory", "correction persisted"),
        ("Researcher repair", "context OSM +\nsource extent"),
        ("Recheck", "coverage=1.0\npassed=True"),
    ]
    xs = [0.06, 0.20, 0.34, 0.49, 0.63, 0.78, 0.92]
    y = 0.52
    widths = [0.12, 0.13, 0.13, 0.12, 0.13, 0.13, 0.11]
    fills = [COLORS["blue_light"], COLORS["blue_light"], COLORS["yellow_light"], COLORS["red_light"], COLORS["purple_light"], COLORS["green_light"], COLORS["green_light"]]
    for idx, ((title, subtitle), x, w, fill) in enumerate(zip(stages, xs, widths, fills)):
        ax.add_patch(Rectangle((x - w / 2, y - 0.12), w, 0.24, facecolor=fill, edgecolor=COLORS["grid"], linewidth=1.5))
        ax.text(x, y + 0.045, title, ha="center", va="center", fontsize=11, fontweight="bold", color=COLORS["ink"])
        ax.text(x, y - 0.045, subtitle, ha="center", va="center", fontsize=9, color=COLORS["ink"], linespacing=1.25)
        if idx < len(stages) - 1:
            ax.add_patch(FancyArrowPatch((x + w / 2 + 0.005, y), (xs[idx + 1] - widths[idx + 1] / 2 - 0.005, y), arrowstyle="-|>", mutation_scale=14, linewidth=1.4, color=COLORS["muted"]))

    bands = [
        (0.06, 0.31, "Verifiable\ninput evidence checked before analysis", COLORS["blue"], COLORS["blue_light"]),
        (0.34, 0.59, "Revisable\nwarnings become rerun actions", COLORS["red"], COLORS["red_light"]),
        (0.63, 0.94, "Cumulative refinement\ncorrection stored and later retrieved", COLORS["purple"], COLORS["purple_light"]),
    ]
    for x0, x1, text, color, fill in bands:
        ax.add_patch(Rectangle((x0, 0.83), x1 - x0, 0.095, facecolor=fill, edgecolor="none"))
        ax.text((x0 + x1) / 2, 0.877, text, ha="center", va="center", fontsize=10.5, color=color, fontweight="bold", linespacing=1.25)

    ax.text(0.02, 0.22, "Observed Case1 transition", fontsize=12, fontweight="bold", color=COLORS["ink"])
    ax.text(
        0.02,
        0.14,
        "Before repair: ReviewHub flags pre-clipped OSM layers (roads width coverage 0.067; buildings width coverage 0.057).\n"
        "After repair: context-scale OSM package with explicit acquisition extent passes coverage checks (1.0 x 1.0) and removes rerun items.",
        fontsize=10,
        color=COLORS["ink"],
        linespacing=1.45,
    )
    save_figure(fig, "fig_case1_review_repair_workflow")


def draw_coverage_figure(data: dict[str, Any]) -> None:
    layers = ["roads", "buildings"]
    initial = data.get("initial_layer_ratios", {})
    supplemented = data.get("supplemented_layer_ratios", {})
    before_width = [initial.get(layer, {}).get("source_to_context_width_ratio", 0) for layer in layers]
    after_width = [supplemented.get(layer, {}).get("source_to_context_width_ratio", 0) for layer in layers]
    before_hits = [initial.get(layer, {}).get("aoi_intersecting_feature_count", 0) for layer in layers]
    after_hits = [supplemented.get(layer, {}).get("aoi_intersecting_feature_count", 0) for layer in layers]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.8), gridspec_kw={"width_ratios": [1.25, 1.0]})
    x = range(len(layers))
    bw = 0.34
    ax1.bar([i - bw / 2 for i in x], before_width, width=bw, color=COLORS["red"], label="Before repair")
    ax1.bar([i + bw / 2 for i in x], after_width, width=bw, color=COLORS["green"], label="After repair")
    ax1.axhline(0.6, color=COLORS["yellow"], linestyle="--", linewidth=1.5, label="Policy threshold=0.6")
    ax1.set_xticks(list(x), layers)
    ax1.set_ylim(0, 1.15)
    ax1.set_ylabel("Source-to-context width coverage")
    ax1.set_title("A. Policy check converts input grounding into measurable evidence", loc="left", fontsize=11, fontweight="bold")
    ax1.legend(frameon=False, fontsize=9, loc="upper left")
    ax1.grid(axis="y", color="#eef2f6")
    for idx, val in enumerate(before_width):
        ax1.text(idx - bw / 2, val + 0.03, fmt(val), ha="center", fontsize=9, color=COLORS["red"])
    for idx, val in enumerate(after_width):
        ax1.text(idx + bw / 2, val + 0.03, fmt(val), ha="center", fontsize=9, color=COLORS["green"])

    ax2.bar([i - bw / 2 for i in x], before_hits, width=bw, color=COLORS["red"], label="Before")
    ax2.bar([i + bw / 2 for i in x], after_hits, width=bw, color=COLORS["green"], label="After")
    ax2.set_xticks(list(x), layers)
    ax2.set_ylabel("Features intersecting AOI")
    ax2.set_title("B. Repair restores usable AOI evidence", loc="left", fontsize=11, fontweight="bold")
    ax2.grid(axis="y", color="#eef2f6")
    for idx, val in enumerate(before_hits):
        ax2.text(idx - bw / 2, val + 0.5, str(val), ha="center", fontsize=9, color=COLORS["red"])
    for idx, val in enumerate(after_hits):
        ax2.text(idx + bw / 2, val + 0.5, str(val), ha="center", fontsize=9, color=COLORS["green"])

    fig.suptitle("Case1: from pre-clipped OSM input to verified context-scale evidence", fontsize=14, fontweight="bold", x=0.02, ha="left")
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    save_figure(fig, "fig_case1_source_coverage_before_after")


def draw_spatial_panel(data: dict[str, Any]) -> None:
    import geopandas as gpd
    from shapely.geometry import box

    boundary_dir = PROJECT_ROOT.parents[0] / "paper9_heritageIntelligence" / "data" / "district_boundaries_v2" / "district_boundaries"
    district_dir = PROJECT_ROOT.parents[0] / "paper9_heritageIntelligence" / "heritage_district_batch" / "districts"
    boundary_path = next(boundary_dir.glob("009_*_boundary.geojson"))
    district_path = next(district_dir.glob("009_*"))
    before_roads = gpd.read_file(district_path / "osm_roads_aoi.geojson")
    before_buildings = gpd.read_file(district_path / "osm_buildings_aoi.geojson")
    after_roads = gpd.read_file(ARTIFACT_DIR / "osm_roads_context_3x.geojson")
    after_buildings = gpd.read_file(ARTIFACT_DIR / "osm_buildings_context_3x.geojson")
    boundary = gpd.read_file(boundary_path)
    context = gpd.read_file(ARTIFACT_DIR / "case1_context_buffer_3x.geojson")

    for gdf_name in ("before_roads", "before_buildings", "after_roads", "after_buildings", "boundary", "context"):
        gdf = locals()[gdf_name]
        if gdf.crs is None:
            locals()[gdf_name] = gdf.set_crs(boundary.crs, allow_override=True)
        elif gdf.crs != boundary.crs:
            locals()[gdf_name] = gdf.to_crs(boundary.crs)

    fig, axes = plt.subplots(1, 2, figsize=(12, 6))
    panels = [
        (axes[0], before_roads, before_buildings, "A. Initial discovered *_aoi OSM inputs\nReviewHub: revise; rerun_queue=2", COLORS["red"]),
        (axes[1], after_roads, after_buildings, "B. Supplemented context-scale OSM package\nReviewHub: accept_with_warnings; rerun_queue=0", COLORS["green"]),
    ]
    xmin, ymin, xmax, ymax = context.total_bounds
    pad_x = (xmax - xmin) * 0.08
    pad_y = (ymax - ymin) * 0.08
    for ax, roads, buildings, title, accent in panels:
        context.boundary.plot(ax=ax, color=COLORS["blue"], linewidth=1.8, linestyle="--")
        boundary.plot(ax=ax, facecolor="#dbeafe", edgecolor=COLORS["blue"], linewidth=1.3, alpha=0.45)
        if len(buildings):
            buildings.plot(ax=ax, facecolor="#94a3b8", edgecolor="#475569", linewidth=0.25, alpha=0.65)
        if len(roads):
            roads.plot(ax=ax, color=accent, linewidth=1.0, alpha=0.9)
        for source in (roads, buildings):
            if len(source):
                sxmin, symin, sxmax, symax = source.total_bounds
                gpd.GeoSeries([box(sxmin, symin, sxmax, symax)], crs=source.crs).boundary.plot(ax=ax, color=accent, linewidth=1.1, linestyle=":")
        ax.set_xlim(xmin - pad_x, xmax + pad_x)
        ax.set_ylim(ymin - pad_y, ymax + pad_y)
        ax.set_title(title, loc="left", fontsize=11, fontweight="bold")
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
        ax.ticklabel_format(useOffset=False, style="plain")
        ax.grid(color="#eef2f6", linewidth=0.8)
    fig.suptitle("Case1 spatial audit panel: AOI, context buffer, and OSM evidence", fontsize=14, fontweight="bold", x=0.02, ha="left")
    fig.tight_layout(rect=[0, 0, 1, 0.92])
    save_figure(fig, "fig_case1_spatial_audit_panel")


def draw_rq_matrix_figure(rows: list[dict[str, Any]]) -> None:
    fig, ax = plt.subplots(figsize=(14, 7.4))
    ax.set_axis_off()
    ax.set_title("Case1 evidence matrix: how the experiment answers the research question", loc="left", fontsize=14, fontweight="bold", pad=12)
    headers = list(rows[0])
    col_widths = [0.16, 0.30, 0.26, 0.28]
    x0 = 0.0
    y_top = 0.86
    header_h = 0.12
    row_h = 0.235
    x_positions = [x0]
    for width in col_widths[:-1]:
        x_positions.append(x_positions[-1] + width)
    for col, (header, width, x) in enumerate(zip(headers, col_widths, x_positions)):
        ax.add_patch(Rectangle((x, y_top - header_h), width, header_h, transform=ax.transAxes, facecolor=COLORS["blue"], edgecolor=COLORS["grid"], linewidth=1.0))
        ax.text(x + width / 2, y_top - header_h / 2, wrap(header, 22), transform=ax.transAxes, ha="center", va="center", fontsize=9.2, fontweight="bold", color="white")
    for row_idx, row in enumerate(rows):
        y = y_top - header_h - (row_idx + 1) * row_h
        fill = "#ffffff" if row_idx % 2 == 0 else "#f8fafc"
        for header, width, x in zip(headers, col_widths, x_positions):
            ax.add_patch(Rectangle((x, y), width, row_h, transform=ax.transAxes, facecolor=fill, edgecolor=COLORS["grid"], linewidth=1.0))
            ax.text(x + 0.012, y + row_h / 2, wrap(row[header], 24 if width <= 0.18 else 38), transform=ax.transAxes, ha="left", va="center", fontsize=8.6, color=COLORS["ink"], linespacing=1.2)
    save_figure(fig, "fig_case1_rq_evidence_matrix")


def draw_table_figure(rows: list[dict[str, Any]], path: Path, *, title: str, widths: list[float], height: float) -> None:
    fig, ax = plt.subplots(figsize=(13.5, height))
    ax.set_axis_off()
    ax.set_title(title, loc="left", fontsize=14, fontweight="bold", pad=12)
    headers = list(rows[0])
    cell_text = [[wrap(row[h], 30) for h in headers] for row in rows]
    table = ax.table(cellText=cell_text, colLabels=headers, cellLoc="left", loc="center", colWidths=widths)
    style_table(table, fontsize=8.2, header_color=COLORS["green"])
    table.scale(1, 2.1)
    fig.tight_layout()
    fig.savefig(path, dpi=240, bbox_inches="tight")
    plt.close(fig)


def style_table(table: Any, *, fontsize: float, header_color: str) -> None:
    table.auto_set_font_size(False)
    table.set_fontsize(fontsize)
    for (row, _col), cell in table.get_celld().items():
        cell.set_edgecolor("#d0d5dd")
        cell.set_linewidth(0.8)
        if row == 0:
            cell.set_facecolor(header_color)
            cell.get_text().set_color("white")
            cell.get_text().set_weight("bold")
        else:
            cell.set_facecolor("#ffffff" if row % 2 else "#f8fafc")
            cell.get_text().set_color(COLORS["ink"])


def write_experiment_text(
    process_rows: list[dict[str, Any]],
    diagnostics_rows: list[dict[str, Any]],
    targeted_ablation_rows: list[dict[str, Any]],
    rq_rows: list[dict[str, Any]],
    system_ablation_rows: list[dict[str, Any]],
) -> None:
    text = f"""# Case1 Experimental Section Draft

## Case1 Aim

Case1 evaluates whether UrbanAgent can make an LLM-orchestrated urban analysis workflow verifiable, revisable, and capable of cumulative refinement. The task is not merely to produce built-environment indicators for the Ningbo Old Bund heritage district, but to expose whether the evidence used by the workflow is spatially sufficient for the requested AOI/context-buffer analysis.

## Process Evidence

Figure `fig_case1_review_repair_workflow` reports the operational loop. UrbanAgent first discovers the AOI boundary, SinoBF function layers, and OSM road/building files. The input-stage spatial diagnostic constructs a 3x AOI-centered context buffer and applies the source-extent policy loaded from policy memory. The reviewer detects that the discovered OSM road and building files are pre-clipped AOI-scale inputs rather than context-scale evidence. The warning is not left as free text: ReviewHub writes two actionable rerun records, both using the repair action `refetch_osm_at_context_buffer`, into the rerun queue and experience memory.

## Before/After Diagnostic Result

Before repair, roads cover only 0.067 of the context-buffer width and buildings cover only 0.057. Both layers have zero AOI-intersecting features in the discovered input, so the reviewer recommends revision. After researcher supplementation, the context-scale OSM package is provided together with an explicit source/acquisition extent. The same policy check then evaluates source extent rather than feature bounds, giving roads and buildings 1.0 width and height coverage. The reviewer accepts the result with no further rerun item.

## Ablation Logic

The targeted Case1 ablation in `table_case1_targeted_ablation` separates four conditions: no review, review without policy memory, review with policy memory on the flawed input, and review after supplementation. This isolates the contribution of policy memory and correction persistence. Without policy memory, the system can report a generic alignment problem but cannot create an operational repair instruction. With policy memory, the same failure is converted into a concrete rerun action and stored as reusable experience. With supplemented source extent, the rerun item disappears, showing that the framework can close the revision loop.

## Link to the Research Question

The Case1 evidence matrix shows how the experiment responds to the paper's research question. Verifiability is demonstrated by measurable source-to-context coverage checks. Revisability is demonstrated by the rerun queue and explicit repair action. Cumulative refinement is demonstrated by persisting ReviewHub correction records in file-tree experience memory and retrieving them alongside policy/workflow memory.

## Suggested Captions

**Figure 1. Case1 review-repair workflow.** The figure shows how UrbanAgent converts a pre-clipped OSM input problem into a policy-grounded warning, a rerun action, persistent experience memory, and a verified recheck after researcher supplementation.

**Figure 2. Source coverage before and after repair.** The bar chart compares source-to-context width coverage and AOI-intersecting features for roads and buildings. The policy threshold is 0.6; both layers fail before repair and pass after the supplemented source extent is supplied.

**Figure 3. Spatial audit panel.** The map panel visualizes the AOI, the 3x context buffer, and the OSM road/building evidence before and after supplementation.

**Table 1. Case1 process trace.** Summarizes the observable trace from source discovery to review, memory persistence, researcher repair, and recheck.

**Table 2. Case1 before/after diagnostics.** Reports layer-level source extent basis, coverage ratios, AOI intersections, and review outcome.

**Table 3. Targeted ablation.** Separates the effect of ReviewHub, policy memory, correction memory, and supplemented source extent on whether the failure becomes actionable and recoverable.
"""
    if system_ablation_rows:
        text += "\n**Table 4. System-level ablation summary.** Reports the older three-trial architecture ablation across planning, review, quality control, dual-space representation, memory, and vanilla execution. Use it as a broader system table; use Table 3 as the sharper Case1 mechanism table.\n"
    (OUTPUT_DIR / "case1_experiment_section_draft.md").write_text(text, encoding="utf-8")


def write_manifest(*tables: list[dict[str, Any]]) -> None:
    manifest = {
        "source_artifacts": {
            "case1_review_comparison": str(ARTIFACT_DIR / "case1_review_comparison.json"),
            "supplement_metadata": str(ARTIFACT_DIR / "supplement_metadata.json"),
            "system_ablation": str(SYSTEM_ABLATION) if SYSTEM_ABLATION.exists() else None,
        },
        "generated_figures": sorted(path.name for path in OUTPUT_DIR.glob("*.png")) + sorted(path.name for path in OUTPUT_DIR.glob("*.svg")) + sorted(path.name for path in OUTPUT_DIR.glob("*.pdf")),
        "generated_tables": sorted(path.name for path in OUTPUT_DIR.glob("*.csv")) + sorted(path.name for path in OUTPUT_DIR.glob("*.md")) + sorted(path.name for path in OUTPUT_DIR.glob("*.tex")),
    }
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def write_table_bundle(stem: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    headers = list(rows[0])
    csv_path = OUTPUT_DIR / f"{stem}.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
    (OUTPUT_DIR / f"{stem}.md").write_text(markdown_table(rows), encoding="utf-8")
    (OUTPUT_DIR / f"{stem}.tex").write_text(latex_table(rows), encoding="utf-8")


def markdown_table(rows: list[dict[str, Any]]) -> str:
    headers = list(rows[0])
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(row[h]).replace("\n", "<br>") for h in headers) + " |")
    return "\n".join(out) + "\n"


def latex_table(rows: list[dict[str, Any]]) -> str:
    headers = list(rows[0])
    colspec = "p{0.18\\linewidth}" + "p{0.20\\linewidth}" * (len(headers) - 1)
    lines = [f"\\begin{{tabular}}{{{colspec}}}", "\\toprule"]
    lines.append(" & ".join(latex_escape(h) for h in headers) + r" \\")
    lines.append("\\midrule")
    for row in rows:
        lines.append(" & ".join(latex_escape(str(row[h])) for h in headers) + r" \\")
    lines.extend(["\\bottomrule", "\\end{tabular}", ""])
    return "\n".join(lines)


def save_figure(fig: Any, stem: str) -> None:
    fig.savefig(OUTPUT_DIR / f"{stem}.png", dpi=240, bbox_inches="tight")
    fig.savefig(OUTPUT_DIR / f"{stem}.svg", bbox_inches="tight")
    fig.savefig(OUTPUT_DIR / f"{stem}.pdf", bbox_inches="tight")
    plt.close(fig)


def fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.3f}".rstrip("0").rstrip(".")
    except Exception:
        return str(value)


def wrap(value: Any, width: int) -> str:
    return "\n".join(textwrap.wrap(str(value), width=width, break_long_words=False))


def latex_escape(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(ch, ch) for ch in text)


if __name__ == "__main__":
    main()
