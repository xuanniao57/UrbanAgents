#!/usr/bin/env python
"""Build RDMA-style Case1 process panels.

The figures intentionally mimic the paper style of dialogue bubbles followed by
structured result cards, while replacing RDMA's model cards with UrbanAgent's
input JSON, memory I/O, review feedback, and map/result panels.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIG_DIR = PROJECT_ROOT / "figures" / "case1_paper_shanghai_nanjing_20260511"
ARTIFACT_DIR = PROJECT_ROOT / "artifacts" / "case1_shanghai_nanjing_supplemented"

OUT_DIALOGUE = FIG_DIR / "fig_case1_rdma_style_dialogue_panel.png"
OUT_DIALOGUE_PDF = FIG_DIR / "fig_case1_rdma_style_dialogue_panel.pdf"
OUT_MEMORY = FIG_DIR / "fig_case1_memory_io_schema.png"
OUT_MEMORY_PDF = FIG_DIR / "fig_case1_memory_io_schema.pdf"


COLORS = {
    "ink": "#1f2937",
    "muted": "#667085",
    "line": "#cbd5e1",
    "dash": "#94a3b8",
    "user": "#e9eef5",
    "agent": "#dff3ee",
    "card": "#ffffff",
    "bar": "#d9f0ea",
    "green": "#0f766e",
    "red": "#b42318",
    "red_light": "#fee4e2",
    "blue": "#1d4ed8",
    "blue_light": "#dbeafe",
    "yellow": "#b54708",
    "yellow_light": "#fef0c7",
    "purple": "#6941c6",
    "purple_light": "#ebe9fe",
    "code_bg": "#fbfcfe",
}


def main() -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    comparison = read_json(ARTIFACT_DIR / "case1_review_comparison.json")
    supplement = read_json(ARTIFACT_DIR / "supplement_metadata.json")
    target_ablation = read_json(ARTIFACT_DIR / "case1_targeted_ablation_results.json")
    task = {
        "case_id": "case1_shanghai_nanjing_road_style_harmony",
        "workflow_profile": "adaptive_urban_analysis",
    }
    experience = read_latest_experience()

    draw_dialogue_panel(comparison, supplement)
    draw_memory_schema(task, comparison, supplement, target_ablation, experience)
    print(json.dumps({
        "dialogue_panel": str(OUT_DIALOGUE),
        "memory_io_schema": str(OUT_MEMORY),
    }, ensure_ascii=False, indent=2))


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_latest_experience() -> dict[str, Any]:
    memory_path = PROJECT_ROOT / "urban_agent" / "memory" / "experience_memory" / "review_feedback" / "20260511_shanghai_nanjing.jsonl"
    if not memory_path.exists():
        return {}
    rows = [json.loads(line) for line in memory_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows[-1] if rows else {}


def load_font(size: int, *, bold: bool = False, mono: bool = False) -> ImageFont.FreeTypeFont:
    candidates = []
    if mono:
        candidates = ["C:/Windows/Fonts/consola.ttf", "C:/Windows/Fonts/cour.ttf"]
    elif bold:
        candidates = ["C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/msyhbd.ttc"]
    else:
        candidates = ["C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/msyh.ttc"]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            continue
    return ImageFont.load_default()


FONT_TITLE = load_font(38, bold=True)
FONT_H1 = load_font(26, bold=True)
FONT_H2 = load_font(20, bold=True)
FONT_BODY = load_font(18)
FONT_SMALL = load_font(15)
FONT_TINY = load_font(13)
FONT_MONO = load_font(14, mono=True)
FONT_MONO_SMALL = load_font(12, mono=True)


def draw_dialogue_panel(comparison: dict[str, Any], supplement: dict[str, Any]) -> None:
    width = 1700
    height = 2320
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    y = 35

    draw.text((60, y), "Case1 UrbanAgent process panel: reviewable, revisable urban analysis", fill=COLORS["ink"], font=FONT_TITLE)
    y += 72

    y = user_bubble(draw, 70, y, 1320, "I want to analyze Style Elements Harmony for Shanghai Nanjing Road Pedestrian Street. Please verify data feasibility before running the analysis.")
    y = agent_label(draw, 75, y, "UrbanAgent")
    y = result_card_initial(draw, 70, y, width - 140, comparison)

    y += 26
    y = user_bubble(draw, 70, y, 1120, "Can you confirm whether the available data are sufficient for the AOI and its context buffer?")
    y = agent_label(draw, 75, y, "UrbanAgent")
    y = result_card_warning(img, draw, 70, y, width - 140, comparison)

    y += 26
    y = user_bubble(draw, 70, y, 1180, "The reviewer recommends repair. Re-fetch roads and buildings at the context-buffer scale and recheck.")
    y = agent_label(draw, 75, y, "UrbanAgent")
    y = result_card_repair(img, draw, 70, y, width - 140, comparison, supplement)

    y += 26
    draw.text((80, y), "Figure. Dialogue-style Case1 evidence returned by UrbanAgent.", fill=COLORS["blue"], font=FONT_H2)
    y += 32
    draw.text(
        (80, y),
        "The panel follows RDMA-style process reporting: each response includes data, parameters, review state, confidence-like validity signals, and map evidence.",
        fill=COLORS["ink"],
        font=FONT_SMALL,
    )

    save_rgb(img, OUT_DIALOGUE, OUT_DIALOGUE_PDF)


def user_bubble(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, text: str) -> int:
    lines = wrap_text(text, FONT_BODY, w - 70)
    h = 34 + len(lines) * 24
    draw.rounded_rectangle([x, y, x + w, y + h], radius=26, fill=COLORS["user"], outline=COLORS["line"], width=2)
    draw.text((x + 24, y + 16), "User", fill=COLORS["ink"], font=FONT_H2)
    tx = x + 95
    for idx, line in enumerate(lines):
        draw.text((tx, y + 18 + idx * 24), line, fill=COLORS["ink"], font=FONT_BODY)
    return y + h + 12


def agent_label(draw: ImageDraw.ImageDraw, x: int, y: int, label: str) -> int:
    draw.rounded_rectangle([x, y, x + 132, y + 44], radius=22, fill=COLORS["agent"], outline=COLORS["line"], width=2)
    draw.text((x + 22, y + 11), label, fill=COLORS["green"], font=FONT_H2)
    return y + 54


def result_card_initial(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, data: dict[str, Any]) -> int:
    h = 360
    dashed_card(draw, x, y, w, h)
    draw.text((x + 28, y + 22), "MODEL:", fill=COLORS["ink"], font=FONT_H2)
    draw.text((x + 28, y + 52), "Style Elements Harmony indicator construction", fill=COLORS["ink"], font=FONT_BODY)
    draw.text((x + 28, y + 96), "DESCRIPTION:", fill=COLORS["ink"], font=FONT_H2)
    desc = "UrbanAgent first verifies whether street-view, AOI, OSM, and SinoBF files can support reviewable AOI + context-buffer analysis."
    draw_multiline(draw, desc, x + 28, y + 126, 500, FONT_SMALL)

    draw.text((x + 610, y + 22), "Data:", fill=COLORS["ink"], font=FONT_H2)
    data_rows = [
        ("Street-view images", "154 points"),
        ("AOI boundary", "002 Shanghai"),
        ("OSM roads", "*_aoi discovered"),
        ("OSM buildings", "*_aoi discovered"),
    ]
    simple_table(draw, x + 610, y + 55, 420, ["Name", "Status"], data_rows)

    draw.text((x + 1080, y + 22), "PARAMETERS:", fill=COLORS["ink"], font=FONT_H2)
    param_rows = [
        ("Context buffer", "3x AOI bbox"),
        ("Coverage threshold", "0.6"),
        ("Memory read", "policy + workflow"),
        ("Review gate", "enabled"),
    ]
    simple_table(draw, x + 1080, y + 55, 410, ["Name", "Value"], param_rows)
    confidence_bar(draw, x + 28, y + h - 50, w - 56, "Grounding state: discovered inputs only; evidence not yet trusted")
    return y + h


def result_card_warning(img: Image.Image, draw: ImageDraw.ImageDraw, x: int, y: int, w: int, data: dict[str, Any]) -> int:
    h = 560
    dashed_card(draw, x, y, w, h)
    ratios = data.get("initial_layer_ratios", {})
    review = data.get("initial_review", {})

    draw.text((x + 28, y + 22), "INPUT DIAGNOSTIC:", fill=COLORS["ink"], font=FONT_H2)
    diag_rows = [
        ("roads", fmt(min_cov(ratios.get("roads", {}))), str(ratios.get("roads", {}).get("aoi_intersecting_feature_count")), "source_feature_bounds"),
        ("buildings", fmt(min_cov(ratios.get("buildings", {}))), str(ratios.get("buildings", {}).get("aoi_intersecting_feature_count")), "source_feature_bounds"),
    ]
    simple_table(draw, x + 28, y + 58, 560, ["Layer", "Min cov.", "AOI hits", "Extent basis"], diag_rows, alert_cols={1})

    draw.text((x + 28, y + 238), "REVIEWHUB:", fill=COLORS["ink"], font=FONT_H2)
    bullets = [
        f"Recommendation: {review.get('recommendation')}",
        "Warning: OSM roads/buildings lack full context-buffer coverage.",
        "Repair action: refetch_osm_at_context_buffer",
        f"Rerun queue: {len(review.get('rerun_queue') or [])} actionable items",
    ]
    draw_bullets(draw, x + 40, y + 270, bullets, 520)

    draw.text((x + 650, y + 22), "Memory I/O:", fill=COLORS["ink"], font=FONT_H2)
    memory_text = {
        "read": ["policy_memory/diagnose_source_extent_vs_context_buffer", "workflow_memory/aoi_context_gis_audit"],
        "write": ["experience_memory/review_feedback/20260511_shanghai_nanjing.jsonl", "correction_memory: roads + buildings"],
    }
    code_box(draw, x + 650, y + 58, 420, 250, json.dumps(memory_text, indent=2))

    map_path = FIG_DIR / "fig_case1_spatial_audit_panel.png"
    if map_path.exists():
        thumb = crop_spatial_panel(map_path, left=True, size=(420, 260))
        img.paste(thumb, (x + 1090, y + 60))
        draw.text((x + 1090, y + 330), "Map preview: discovered *_aoi layers fail AOI/context check", fill=COLORS["muted"], font=FONT_SMALL)

    road_cov = fmt(min_cov(ratios.get("roads", {})))
    bldg_cov = fmt(min_cov(ratios.get("buildings", {})))
    confidence_bar(
        draw,
        x + 28,
        y + h - 50,
        w - 56,
        f"Review validity: revise | source coverage roads={road_cov}, buildings={bldg_cov} | rerun queue={len(review.get('rerun_queue') or [])}",
    )
    return y + h


def result_card_repair(img: Image.Image, draw: ImageDraw.ImageDraw, x: int, y: int, w: int, data: dict[str, Any], supplement: dict[str, Any]) -> int:
    h = 650
    dashed_card(draw, x, y, w, h)
    ratios = data.get("supplemented_layer_ratios", {})
    review = data.get("supplemented_review", {})

    draw.text((x + 28, y + 22), "DATA SUPPLEMENT:", fill=COLORS["ink"], font=FONT_H2)
    supplement_rows = [
        ("OSM roads", str(supplement.get("roads_feature_count", "n/a")), "Overpass context"),
        ("OSM buildings", str(supplement.get("buildings_feature_count", "n/a")), "Overpass context"),
        ("source_extent", "1", "3x context buffer"),
    ]
    simple_table(draw, x + 28, y + 58, 560, ["Layer", "Features", "Source"], supplement_rows)

    draw.text((x + 28, y + 246), "RECHECK:", fill=COLORS["ink"], font=FONT_H2)
    diag_rows = [
        ("roads", fmt(min_cov(ratios.get("roads", {}))), str(ratios.get("roads", {}).get("aoi_intersecting_feature_count")), "source_acquisition_extent"),
        ("buildings", fmt(min_cov(ratios.get("buildings", {}))), str(ratios.get("buildings", {}).get("aoi_intersecting_feature_count")), "source_acquisition_extent"),
    ]
    simple_table(draw, x + 28, y + 282, 620, ["Layer", "Min cov.", "AOI hits", "Extent basis"], diag_rows)

    draw.text((x + 700, y + 22), "Review output:", fill=COLORS["ink"], font=FONT_H2)
    review_obj = {
        "recommendation": review.get("recommendation"),
        "passed": review.get("passed"),
        "rerun_queue": len(review.get("rerun_queue") or []),
        "remaining_warning": (review.get("warnings") or [""])[0],
    }
    code_box(draw, x + 700, y + 58, 430, 220, json.dumps(review_obj, indent=2))

    map_path = FIG_DIR / "fig_case1_spatial_audit_panel.png"
    if map_path.exists():
        thumb = crop_spatial_panel(map_path, left=False, size=(430, 300))
        img.paste(thumb, (x + 1148, y + 58))
        draw.text((x + 1148, y + 368), "Map preview: context-scale OSM evidence after repair", fill=COLORS["muted"], font=FONT_SMALL)

    draw.text((x + 700, y + 326), "Targeted ablation result:", fill=COLORS["ink"], font=FONT_H2)
    ablation_rows = [
        ("No review", "n/a", "0"),
        ("Review only", "revise", "0"),
        ("+ policy", "revise", "2"),
        ("+ extent", "accept", "0"),
    ]
    simple_table(draw, x + 700, y + 362, 430, ["Condition", "Review", "Rerun"], ablation_rows, col_fracs=[0.52, 0.30, 0.18])

    confidence_bar(
        draw,
        x + 28,
        y + h - 50,
        w - 56,
        f"Review validity: {review.get('recommendation')} | source coverage=1.0 x 1.0 | rerun queue={len(review.get('rerun_queue') or [])}",
    )
    return y + h


def draw_memory_schema(task: dict[str, Any], comparison: dict[str, Any], supplement: dict[str, Any], ablation: dict[str, Any], experience: dict[str, Any]) -> None:
    width = 1800
    height = 940
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    draw.text((60, 35), "Case1 structured input and memory I/O schema", fill=COLORS["ink"], font=FONT_TITLE)
    draw.text((60, 88), "The schema makes the hidden context-management step visible: task JSON is compressed into a memory read pack; review output is written back as experience memory.", fill=COLORS["muted"], font=FONT_BODY)

    col_w = 520
    gap = 50
    x1 = 60
    x2 = x1 + col_w + gap
    x3 = x2 + col_w + gap
    y = 145
    h = 650

    input_snippet = {
        "case_id": task.get("case_id"),
        "workflow_profile": task.get("workflow_profile"),
        "data_resources": {
            "streetview_images": "154 sample points",
            "aoi_boundaries": "002 Shanghai Nanjing Road",
            "osm_roads_buildings": "prefetched *_aoi cache",
            "sinobf1_building_functions": "CSV/table + GeoJSON",
        },
        "evaluation_focus": [
            "data feasibility",
            "reviewable outputs",
            "evidence manifest",
        ],
    }
    memory_read = {
        "policy_memory": [
            "aoi_centered_context_buffer",
            "diagnose_source_extent_vs_context_buffer",
            "source_authority_before_cache",
        ],
        "workflow_memory": ["aoi_context_gis_audit"],
        "retrieval": {
            "mode": "file-tree keyword/context selection",
            "selected_count": 8,
        },
    }
    write_obj = {
        "review_feedback": {
            "trace_id": experience.get("trace_id", "case1_shanghai_initial_warning"),
            "recommendation": comparison.get("initial_review", {}).get("recommendation"),
            "rerun_queue": [
                "roads -> refetch_osm_at_context_buffer",
                "buildings -> refetch_osm_at_context_buffer",
            ],
        },
        "next_run_effect": {
            "source_extent_basis": "source_acquisition_extent",
            "coverage": "1.0 x 1.0",
            "rerun_queue": 0,
        },
    }

    schema_column(draw, x1, y, col_w, h, "Input JSON", "Task grounding and declared resources", json.dumps(input_snippet, indent=2))
    schema_column(draw, x2, y, col_w, h, "Memory read", "Policy + workflow memories dynamically loaded", json.dumps(memory_read, indent=2))
    schema_column(draw, x3, y, col_w, h, "Memory write / next read", "Review correction becomes reusable experience", json.dumps(write_obj, indent=2))

    arrow(draw, x1 + col_w + 8, y + 430, x2 - 12, y + 430, "select")
    arrow(draw, x2 + col_w + 8, y + 430, x3 - 12, y + 430, "write")
    arrow(draw, x3 + 260, y + h + 35, x2 + 260, y + h + 35, "retrieved in later planning/review")

    save_rgb(img, OUT_MEMORY, OUT_MEMORY_PDF)


def schema_column(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, title: str, subtitle: str, code: str) -> None:
    draw.rounded_rectangle([x, y, x + w, y + h], radius=16, fill=COLORS["card"], outline=COLORS["line"], width=2)
    draw.text((x + 24, y + 24), title, fill=COLORS["ink"], font=FONT_H1)
    draw.text((x + 24, y + 60), subtitle, fill=COLORS["muted"], font=FONT_SMALL)
    code_box(draw, x + 24, y + 105, w - 48, h - 135, code, small=True)


def dashed_card(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int) -> None:
    draw.rounded_rectangle([x, y, x + w, y + h], radius=6, fill=COLORS["card"], outline=COLORS["line"], width=2)
    dash = 12
    for xx in range(x + 8, x + w - 8, dash * 2):
        draw.line([(xx, y), (min(xx + dash, x + w), y)], fill=COLORS["dash"], width=1)
        draw.line([(xx, y + h), (min(xx + dash, x + w), y + h)], fill=COLORS["dash"], width=1)
    for yy in range(y + 8, y + h - 8, dash * 2):
        draw.line([(x, yy), (x, min(yy + dash, y + h))], fill=COLORS["dash"], width=1)
        draw.line([(x + w, yy), (x + w, min(yy + dash, y + h))], fill=COLORS["dash"], width=1)


def simple_table(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    w: int,
    headers: list[str],
    rows: list[tuple[Any, ...]],
    *,
    alert_cols: set[int] | None = None,
    col_fracs: list[float] | None = None,
) -> None:
    alert_cols = alert_cols or set()
    cols = len(headers)
    if col_fracs:
        widths = [int(w * frac) for frac in col_fracs]
        widths[-1] = w - sum(widths[:-1])
    else:
        widths = [w // cols] * cols
        widths[-1] = w - sum(widths[:-1])
    offsets = [x]
    for col_width in widths[:-1]:
        offsets.append(offsets[-1] + col_width)
    row_h = 34
    for idx, header in enumerate(headers):
        draw.text((offsets[idx], y), header, fill=COLORS["ink"], font=FONT_SMALL)
    draw.line([(x, y + 27), (x + w, y + 27)], fill=COLORS["line"], width=2)
    cy = y + 38
    for row in rows:
        for idx, value in enumerate(row):
            color = COLORS["red"] if idx in alert_cols else COLORS["ink"]
            draw.text((offsets[idx], cy), str(value), fill=color, font=FONT_SMALL)
        draw.line([(x, cy + 25), (x + w, cy + 25)], fill="#edf2f7", width=1)
        cy += row_h


def code_box(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, text: str, *, small: bool = False) -> None:
    font = FONT_MONO_SMALL if small else FONT_MONO
    draw.rounded_rectangle([x, y, x + w, y + h], radius=8, fill=COLORS["code_bg"], outline=COLORS["line"], width=1)
    max_chars = 58 if small else 42
    lines = []
    for raw in text.splitlines():
        lines.extend(textwrap.wrap(raw, width=max_chars, replace_whitespace=False, drop_whitespace=False) or [""])
    line_h = 17 if small else 20
    for idx, line in enumerate(lines[: max(1, (h - 20) // line_h)]):
        draw.text((x + 12, y + 12 + idx * line_h), line, fill=COLORS["ink"], font=font)


def draw_bullets(draw: ImageDraw.ImageDraw, x: int, y: int, bullets: list[str], w: int) -> None:
    cy = y
    for item in bullets:
        draw.text((x, cy), "-", fill=COLORS["ink"], font=FONT_SMALL)
        lines = wrap_text(item, FONT_SMALL, w - 24)
        for idx, line in enumerate(lines):
            color = COLORS["red"] if "Warning" in item or "refetch" in item else COLORS["ink"]
            draw.text((x + 22, cy + idx * 20), line, fill=color, font=FONT_SMALL)
        cy += max(1, len(lines)) * 20 + 8


def draw_multiline(draw: ImageDraw.ImageDraw, text: str, x: int, y: int, w: int, font: ImageFont.FreeTypeFont, *, fill: str = COLORS["ink"]) -> int:
    lines = wrap_text(text, font, w)
    for idx, line in enumerate(lines):
        draw.text((x, y + idx * 22), line, fill=fill, font=font)
    return y + len(lines) * 22


def confidence_bar(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, text: str) -> None:
    draw.rounded_rectangle([x, y, x + w, y + 34], radius=4, fill=COLORS["bar"], outline=None)
    draw.text((x + 12, y + 8), text, fill=COLORS["ink"], font=FONT_SMALL)


def arrow(draw: ImageDraw.ImageDraw, x0: int, y0: int, x1: int, y1: int, label: str, *, reverse: bool = False) -> None:
    color = COLORS["muted"]
    if reverse:
        x0, x1 = x1, x0
    draw.line([(x0, y0), (x1, y1)], fill=color, width=3)
    direction = 1 if x1 >= x0 else -1
    head = [(x1, y1), (x1 - direction * 12, y1 - 8), (x1 - direction * 12, y1 + 8)]
    draw.polygon(head, fill=color)
    draw.text(((x0 + x1) // 2 - text_width(label, FONT_SMALL) // 2, y0 - 28), label, fill=color, font=FONT_SMALL)


def crop_spatial_panel(path: Path, *, left: bool, size: tuple[int, int]) -> Image.Image:
    img = Image.open(path).convert("RGB")
    w, h = img.size
    # Crop lower map area and either left or right half.
    top = int(h * 0.33)
    bottom = int(h * 0.95)
    if left:
        box = (0, top, int(w * 0.50), bottom)
    else:
        box = (int(w * 0.50), top, w, bottom)
    return img.crop(box).resize(size, Image.LANCZOS)


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = str(text).split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if text_width(candidate, font) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def text_width(text: str, font: ImageFont.FreeTypeFont) -> int:
    box = font.getbbox(str(text))
    return int(box[2] - box[0])


def fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.3f}".rstrip("0").rstrip(".")
    except Exception:
        return str(value)


def min_cov(row: dict[str, Any]) -> Any:
    values = [
        row.get("source_to_context_width_ratio"),
        row.get("source_to_context_height_ratio"),
    ]
    nums = []
    for value in values:
        try:
            nums.append(float(value))
        except Exception:
            pass
    return min(nums) if nums else None


def save_rgb(img: Image.Image, png_path: Path, pdf_path: Path) -> None:
    png_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(png_path)
    img.save(pdf_path, "PDF", resolution=180.0)


if __name__ == "__main__":
    main()
