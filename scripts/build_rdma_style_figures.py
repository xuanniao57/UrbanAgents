#!/usr/bin/env python
"""Build RDMA-style evidence packs from UrbanAgent run outputs.

The script is intentionally generic: it reads UrbanAgent `outputs/cli_runs/*`
directories, extracts confidence scores, agent traces, GIS/chart artifacts, and
ablation CSVs, then writes reviewable tables and an HTML interaction panel.
"""

from __future__ import annotations

import argparse
import csv
import glob
import html
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RUNS_GLOB = PROJECT_ROOT / "outputs" / "cli_runs" / "*"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "figures" / "rdma_style"


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def discover_runs(pattern: str) -> List[Path]:
    runs = []
    for item in glob.glob(pattern):
        path = Path(item)
        if path.is_dir() and (path / "summary.json").exists():
            runs.append(path)
    return sorted(runs)


def extract_confidence_rows(runs: Iterable[Path]) -> List[Dict[str, Any]]:
    rows = []
    for run_dir in runs:
        summary = read_json(run_dir / "summary.json")
        qc = summary.get("quality_control", {})
        exec_qc = qc.get("exec_qc", {}) if isinstance(qc, dict) else {}
        dims = exec_qc.get("dimension_scores", {}) if isinstance(exec_qc, dict) else {}
        review = summary.get("review", {}) if isinstance(summary.get("review"), dict) else {}
        rows.append({
            "run_dir": str(run_dir),
            "status": summary.get("status"),
            "workflow_profile": summary.get("workflow_profile"),
            "total_latency_s": summary.get("total_latency_s"),
            "exec_confidence": exec_qc.get("confidence_score"),
            "semantic_relevance": dims.get("semantic_relevance"),
            "historical_reliability": dims.get("historical_reliability"),
            "metadata_completeness": dims.get("metadata_completeness"),
            "context_alignment": dims.get("context_alignment"),
            "review_score": review.get("urban_validity_score"),
            "review_recommendation": review.get("recommendation"),
            "warning_count": review.get("warning_count"),
            "hard_failures": "; ".join(review.get("hard_failures", []) or []),
        })
    return rows


def extract_run_cards(runs: Iterable[Path]) -> List[Dict[str, Any]]:
    cards = []
    for run_dir in runs:
        summary = read_json(run_dir / "summary.json")
        result = read_json(run_dir / "result.json")
        subtask_results = result.get("results", {}).get("subtask_results", {}) if isinstance(result, dict) else {}
        artifacts = collect_artifacts(subtask_results)
        metric_rows = collect_metric_rows(subtask_results)
        cards.append({
            "run_dir": str(run_dir),
            "title": run_dir.name,
            "status": summary.get("status"),
            "agent_plan": summary.get("agent_plan", []),
            "confidence": summary.get("quality_control", {}).get("exec_qc", {}).get("confidence_score"),
            "review": summary.get("review", {}),
            "artifacts": artifacts,
            "metric_rows": metric_rows,
            "final_answer_preview": summary.get("final_answer_preview", ""),
        })
    return cards


def collect_artifacts(subtask_results: Dict[str, Any]) -> List[Dict[str, Any]]:
    artifacts: List[Dict[str, Any]] = []
    for item in subtask_results.values():
        result = item.get("result", {}) if isinstance(item, dict) else {}
        if isinstance(result, dict) and isinstance(result.get("artifacts"), list):
            artifacts.extend(result["artifacts"])
    return artifacts


def collect_metric_rows(subtask_results: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in subtask_results.values():
        result = item.get("result", {}) if isinstance(item, dict) else {}
        if isinstance(result, dict) and isinstance(result.get("metric_rows"), list):
            rows.extend(result["metric_rows"])
    return rows


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8-sig")
        return
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def copy_ablation_tables(output_dir: Path, ablation_csv: Optional[str]) -> List[Path]:
    copied = []
    candidates = []
    if ablation_csv:
        candidates.append(Path(ablation_csv))
    candidates.extend(PROJECT_ROOT.glob("case_studies/*/runs/ablation_table3*.csv"))
    for src in candidates:
        if not src.exists() or not src.is_file():
            continue
        dst = output_dir / src.name
        dst.write_bytes(src.read_bytes())
        copied.append(dst)
    return copied


def write_interaction_panel(path: Path, cards: List[Dict[str, Any]], ablation_tables: List[Path]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    card_html = "\n".join(render_card(card) for card in cards)
    table_links = "".join(f"<li>{html.escape(str(table))}</li>" for table in ablation_tables) or "<li>No ablation CSV found.</li>"
    path.write_text(f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>UrbanAgent RDMA-Style Evidence Pack</title>
  <style>
    body {{ margin: 0; padding: 24px; font-family: Arial, sans-serif; color: #17202a; background: #f7f8fa; }}
    h1 {{ margin: 0 0 8px; font-size: 24px; }}
    h2 {{ margin: 22px 0 10px; font-size: 18px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 16px; }}
    .card {{ background: white; border: 1px solid #d9dee7; border-radius: 8px; padding: 14px; box-shadow: 0 8px 20px rgba(20, 32, 48, 0.06); }}
    .meta {{ color: #667085; font-size: 12px; line-height: 1.5; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 8px; }}
    th, td {{ border-top: 1px solid #e5e7eb; padding: 6px; text-align: left; vertical-align: top; }}
    .pill {{ display: inline-block; padding: 2px 7px; border-radius: 999px; background: #e6f2ef; color: #0f766e; font-size: 12px; margin-right: 6px; }}
    .artifact {{ font-family: Consolas, monospace; font-size: 11px; word-break: break-all; }}
  </style>
</head>
<body>
  <h1>UrbanAgent RDMA-Style Evidence Pack</h1>
  <div class=\"meta\">Generated from UrbanAgent run directories. Formal map evidence should use GIS layer packages, PNG/PDF maps, and metric tables; SVG previews are treated as secondary inspection artifacts.</div>
  <h2>Ablation Tables</h2>
  <ul>{table_links}</ul>
  <h2>Run Panels</h2>
  <div class=\"grid\">{card_html}</div>
</body>
</html>""", encoding="utf-8")


def write_interaction_panel_png(path: Path, cards: List[Dict[str, Any]]) -> Optional[Path]:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    width = 1800
    card_width = 860
    margin = 32
    gap = 24
    card_height = 520
    rows = max(1, (len(cards) + 1) // 2)
    height = margin * 2 + rows * card_height + (rows - 1) * gap
    image = Image.new("RGB", (width, height), "#f7f8fa")
    draw = ImageDraw.Draw(image)
    title_font = _load_font(22, bold=True)
    body_font = _load_font(17)
    small_font = _load_font(14)
    for idx, card in enumerate(cards):
        col = idx % 2
        row = idx // 2
        x = margin + col * (card_width + gap)
        y = margin + row * (card_height + gap)
        draw.rounded_rectangle([x, y, x + card_width, y + card_height], radius=8, fill="white", outline="#d9dee7", width=2)
        title = _truncate(card.get("title", "run"), 72)
        draw.text((x + 20, y + 18), title, fill="#17202a", font=title_font)
        draw.text((x + 20, y + 50), _truncate(card.get("run_dir", ""), 110), fill="#667085", font=small_font)
        review = card.get("review", {}) or {}
        meta = f"status={card.get('status')}  confidence={format_value(card.get('confidence'))}  review={format_value(review.get('urban_validity_score'))}"
        draw.text((x + 20, y + 82), meta, fill="#0f766e", font=body_font)
        cursor = y + 122
        draw.text((x + 20, cursor), "Agent Trace", fill="#17202a", font=body_font)
        cursor += 28
        for item in card.get("agent_plan", [])[:5]:
            line = f"{item.get('step')}. {item.get('agent')} - {item.get('status')}"
            draw.text((x + 28, cursor), _truncate(line, 92), fill="#344054", font=small_font)
            cursor += 22
        cursor += 10
        draw.text((x + 20, cursor), "Metrics", fill="#17202a", font=body_font)
        cursor += 28
        for row_data in card.get("metric_rows", [])[:8]:
            line = f"{row_data.get('metric')}: {format_value(row_data.get('value'))} {row_data.get('unit', '')}"
            draw.text((x + 28, cursor), _truncate(line, 92), fill="#344054", font=small_font)
            cursor += 22
        cursor += 10
        draw.text((x + 20, cursor), "Artifacts", fill="#17202a", font=body_font)
        cursor += 28
        for artifact in card.get("artifacts", [])[:5]:
            line = f"{artifact.get('type')}: {Path(str(artifact.get('path', ''))).name}"
            draw.text((x + 28, cursor), _truncate(line, 92), fill="#344054", font=small_font)
            cursor += 22
    image.save(path)
    return path


def _load_font(size: int, bold: bool = False):
    from PIL import ImageFont
    font_candidates = [
        "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for candidate in font_candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _truncate(value: Any, limit: int) -> str:
    text = str(value)
    return text if len(text) <= limit else text[: max(0, limit - 1)] + "..."


def render_card(card: Dict[str, Any]) -> str:
    agents = "".join(
        f"<tr><td>{html.escape(str(item.get('step')))}</td><td>{html.escape(str(item.get('agent')))}</td><td>{html.escape(str(item.get('status')))}</td></tr>"
        for item in card.get("agent_plan", [])
    ) or "<tr><td colspan=\"3\">No agent plan</td></tr>"
    artifacts = "".join(
        f"<li><span class=\"pill\">{html.escape(str(artifact.get('type')))}</span><span class=\"artifact\">{html.escape(str(artifact.get('path')))}</span></li>"
        for artifact in card.get("artifacts", [])[:10]
    ) or "<li>No artifacts recorded</li>"
    metrics = "".join(
        f"<tr><td>{html.escape(str(row.get('metric')))}</td><td>{html.escape(format_value(row.get('value')))}</td><td>{html.escape(str(row.get('unit', '')))}</td></tr>"
        for row in card.get("metric_rows", [])[:12]
    ) or "<tr><td colspan=\"3\">No metric rows</td></tr>"
    review = card.get("review", {}) or {}
    return f"""<section class=\"card\">
      <h2>{html.escape(card.get('title', 'run'))}</h2>
      <div class=\"meta\">{html.escape(card.get('run_dir', ''))}</div>
      <p><span class=\"pill\">{html.escape(str(card.get('status')))}</span><span class=\"pill\">confidence {html.escape(format_value(card.get('confidence')))}</span><span class=\"pill\">review {html.escape(format_value(review.get('urban_validity_score')))}</span></p>
      <table><thead><tr><th>Step</th><th>Agent</th><th>Status</th></tr></thead><tbody>{agents}</tbody></table>
      <h2>Metrics</h2>
      <table><thead><tr><th>Metric</th><th>Value</th><th>Unit</th></tr></thead><tbody>{metrics}</tbody></table>
      <h2>Artifacts</h2>
      <ul>{artifacts}</ul>
      <h2>Answer Preview</h2>
      <div class=\"meta\">{html.escape(str(card.get('final_answer_preview', ''))[:700])}</div>
    </section>"""


def format_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4g}"
    if value is None:
        return ""
    return str(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build RDMA-style UrbanAgent evidence pack")
    parser.add_argument("--runs-glob", default=str(DEFAULT_RUNS_GLOB), help="Glob for run directories")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Output directory")
    parser.add_argument("--ablation-csv", default=None, help="Optional ablation Table 3 CSV to include")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    runs = discover_runs(args.runs_glob)
    confidence_rows = extract_confidence_rows(runs)
    cards = extract_run_cards(runs)
    confidence_csv = output_dir / "confidence_four_scores.csv"
    write_csv(confidence_csv, confidence_rows)
    ablation_tables = copy_ablation_tables(output_dir, args.ablation_csv)
    panel_html = output_dir / "rdma_interaction_panels.html"
    write_interaction_panel(panel_html, cards, ablation_tables)
    panel_png = write_interaction_panel_png(output_dir / "rdma_interaction_panels.png", cards)
    manifest = {
        "runs_scanned": len(runs),
        "confidence_csv": str(confidence_csv),
        "ablation_tables": [str(path) for path in ablation_tables],
        "interaction_panel_html": str(panel_html),
        "interaction_panel_png": str(panel_png) if panel_png else None,
    }
    (output_dir / "rdma_evidence_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()