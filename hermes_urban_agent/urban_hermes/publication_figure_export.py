"""Deterministic publication renderer for Urban-Hermes visual evidence.

The browser workspace uses deck.gl for spatial exploration and Vega-Lite for
linked statistical views. This module consumes the same tabular evidence and
produces fixed-size vector/raster artwork for manuscripts. It intentionally
does not screenshot the browser canvas.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm


MM_PER_INCH = 25.4
ELSEVIER_WIDTHS_MM = (90, 140, 190)
BLUE = "#0072B2"
SKY = "#56B4E9"
ORANGE = "#E69F00"
VERMILLION = "#D55E00"
INK = "#111111"
MUTED = "#666666"
GRID = "#D9D9D9"


def configure_style() -> None:
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
            "font.size": 8,
            "axes.labelsize": 8,
            "axes.titlesize": 9,
            "axes.titleweight": "semibold",
            "xtick.labelsize": 7,
            "ytick.labelsize": 7,
            "legend.fontsize": 7,
            "axes.edgecolor": INK,
            "axes.linewidth": 0.7,
            "xtick.color": INK,
            "ytick.color": INK,
            "axes.labelcolor": INK,
            "text.color": INK,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
            "savefig.facecolor": "white",
            "savefig.bbox": "tight",
        }
    )


def load_residuals(path: Path, scale: str, scheme: str) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {
        "grid_id",
        "lon",
        "lat",
        "observed_log_stays",
        "predicted_log_stays",
        "residual",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    if "scale" in frame.columns:
        frame = frame.loc[frame["scale"].astype(str) == scale]
    if "scheme" in frame.columns:
        frame = frame.loc[frame["scheme"].astype(str) == scheme]
    numeric = ["lon", "lat", "observed_log_stays", "predicted_log_stays", "residual"]
    frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="coerce")
    frame = frame.dropna(subset=numeric).copy()
    if frame.empty:
        raise ValueError("No valid rows remain after scale/scheme filtering")
    return frame


def add_panel_label(axis: mpl.axes.Axes, label: str) -> None:
    axis.text(
        -0.13,
        1.06,
        label,
        transform=axis.transAxes,
        fontsize=10,
        fontweight="bold",
        va="top",
        ha="left",
    )


def add_scale_bar(axis: mpl.axes.Axes, latitude: float, length_km: float = 5.0) -> None:
    longitude_degrees = length_km / (111.32 * math.cos(math.radians(latitude)))
    xmin, xmax = axis.get_xlim()
    ymin, ymax = axis.get_ylim()
    x0 = xmin + 0.06 * (xmax - xmin)
    y0 = ymin + 0.07 * (ymax - ymin)
    axis.plot([x0, x0 + longitude_degrees], [y0, y0], color=INK, lw=1.5, solid_capstyle="butt")
    axis.text(x0 + longitude_degrees / 2, y0 + 0.018 * (ymax - ymin), f"{length_km:g} km", ha="center", va="bottom", fontsize=7)


def render_figure(frame: pd.DataFrame, width_mm: int) -> mpl.figure.Figure:
    if width_mm not in ELSEVIER_WIDTHS_MM:
        raise ValueError(f"width_mm must be one of {ELSEVIER_WIDTHS_MM}")
    configure_style()
    width_in = width_mm / MM_PER_INCH
    height_in = width_in * 0.46
    figure = plt.figure(figsize=(width_in, height_in), layout="constrained")
    grid = figure.add_gridspec(1, 3, width_ratios=[1.25, 1.0, 0.9], wspace=0.08)
    map_axis = figure.add_subplot(grid[0, 0])
    fit_axis = figure.add_subplot(grid[0, 1])
    hist_axis = figure.add_subplot(grid[0, 2])

    limit = max(float(np.nanquantile(np.abs(frame["residual"]), 0.98)), 0.5)
    residual_map = LinearSegmentedColormap.from_list(
        "urban_residual",
        [BLUE, SKY, "#F7F7F7", ORANGE, VERMILLION],
    )
    norm = TwoSlopeNorm(vmin=-limit, vcenter=0.0, vmax=limit)
    points = map_axis.scatter(
        frame["lon"],
        frame["lat"],
        c=frame["residual"],
        cmap=residual_map,
        norm=norm,
        s=7,
        linewidths=0,
        rasterized=True,
    )
    mean_latitude = float(frame["lat"].mean())
    map_axis.set_aspect(1 / math.cos(math.radians(mean_latitude)))
    map_axis.set_xlabel("Longitude (°E)")
    map_axis.set_ylabel("Latitude (°N)")
    map_axis.set_title("Residual geography", loc="left", pad=5)
    map_axis.grid(color=GRID, linewidth=0.35, alpha=0.7)
    map_axis.ticklabel_format(style="plain", useOffset=False)
    add_scale_bar(map_axis, mean_latitude)
    map_axis.text(0.98, 0.98, "N\n↑", transform=map_axis.transAxes, ha="right", va="top", fontsize=7, linespacing=0.8)
    colorbar = figure.colorbar(points, ax=map_axis, orientation="horizontal", location="bottom", shrink=0.76, pad=0.14, aspect=28)
    colorbar.set_label("Observed − predicted (log stays)", fontsize=7)
    colorbar.ax.tick_params(labelsize=6, length=2)

    observed = frame["observed_log_stays"].to_numpy()
    predicted = frame["predicted_log_stays"].to_numpy()
    low = float(min(observed.min(), predicted.min()))
    high = float(max(observed.max(), predicted.max()))
    fit_axis.scatter(observed, predicted, s=8, color=BLUE, alpha=0.62, linewidths=0)
    fit_axis.plot([low, high], [low, high], color=INK, linewidth=0.8, linestyle=(0, (4, 3)))
    fit_axis.set_xlim(low, high)
    fit_axis.set_ylim(low, high)
    fit_axis.set_aspect("equal", adjustable="box")
    fit_axis.set_xlabel("Observed log stays")
    fit_axis.set_ylabel("Predicted log stays")
    fit_axis.set_title("Spatial-block calibration", loc="left", pad=5)
    fit_axis.grid(color=GRID, linewidth=0.35, alpha=0.7)

    hist_axis.hist(frame["residual"], bins=28, color=INK, edgecolor="white", linewidth=0.25)
    hist_axis.axvline(0, color=VERMILLION, linewidth=0.9, linestyle=(0, (3, 2)))
    hist_axis.set_xlabel("Residual (log stays)")
    hist_axis.set_ylabel("Grid cells")
    hist_axis.set_title("Error distribution", loc="left", pad=5)
    hist_axis.grid(axis="y", color=GRID, linewidth=0.35, alpha=0.7)

    for label, axis in zip("ABC", (map_axis, fit_axis, hist_axis)):
        add_panel_label(axis, label)
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)

    figure.suptitle(
        f"Out-of-fold predictive error across {len(frame):,} spatial units",
        x=0.006,
        ha="left",
        fontsize=10,
        fontweight="semibold",
    )
    return figure


def export_figure(frame: pd.DataFrame, output_prefix: Path, width_mm: int, dpi: int) -> list[Path]:
    figure = render_figure(frame, width_mm)
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    outputs = [output_prefix.with_suffix(suffix) for suffix in (".svg", ".pdf", ".tif")]
    figure.savefig(outputs[0])
    figure.savefig(outputs[1])
    figure.savefig(outputs[2], dpi=dpi, pil_kwargs={"compression": "tiff_lzw"})
    plt.close(figure)
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="CSV containing held-out spatial predictions")
    parser.add_argument("--output-prefix", type=Path, required=True, help="Output path without extension")
    parser.add_argument("--scale", default="500m")
    parser.add_argument("--scheme", default="spatial_block")
    parser.add_argument("--width-mm", type=int, choices=ELSEVIER_WIDTHS_MM, default=190)
    parser.add_argument("--dpi", type=int, default=500)
    args = parser.parse_args()

    frame = load_residuals(args.input, args.scale, args.scheme)
    outputs = export_figure(frame, args.output_prefix, args.width_mm, args.dpi)
    manifest = {
        "schema_version": "1.0",
        "renderer": "Urban-Hermes deterministic publication renderer",
        "input": str(args.input.resolve()),
        "filters": {"scale": args.scale, "scheme": args.scheme},
        "rows": int(len(frame)),
        "width_mm": args.width_mm,
        "minimum_normal_text_pt": 7,
        "tiff_dpi": args.dpi,
        "formats": [path.suffix.lstrip(".") for path in outputs],
        "outputs": [str(path.resolve()) for path in outputs],
        "claim_boundary": "Predictive association under spatial-block validation; the residual map does not identify causal mechanisms.",
    }
    manifest_path = args.output_prefix.with_name(f"{args.output_prefix.name}_manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
