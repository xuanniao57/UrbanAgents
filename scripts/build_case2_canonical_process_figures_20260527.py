from __future__ import annotations

import json
import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "experiments" / "case2_process_materials_rerun_20260527_020009"
ART = RUN / "artifacts"
OUT = ROOT / "paper_draft" / "figures" / "case2_process_20260527"
OUT.mkdir(parents=True, exist_ok=True)
FRONTEND_CLI_CROP = OUT / "frontend_cli_terminal_crop_20260527.png"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


ROUTE = load_json(RUN / "plan" / "route_tree.json")
MORAN = load_json(ART / "s4_diagnostics" / "residual_moran_i_report.json")
GWRF = load_json(ART / "s3_gwrf" / "gwrf_requirements_check.json")
CLAIMS = load_json(ART / "s5_claims" / "calibrated_claims.json")


RF_R2 = ROUTE["data_contract"]["existing_model_result"]["cv_r2"]
RF_MAE = ROUTE["data_contract"]["existing_model_result"]["cv_mae_log_stays"]
MORAN_I = MORAN["moran_I"]
MORAN_P = MORAN["p_value_norm"]
GWRF_FLAGGED = GWRF["local_multicollinearity"]["flagged_windows"]
GWRF_PCT = GWRF["local_multicollinearity"]["pct_flagged"]
GWRF_BW = GWRF["bandwidth_search_range"]["selected_bandwidth"]


def save(fig: plt.Figure, name: str) -> Path:
    path = OUT / name
    fig.savefig(path, dpi=260, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(path)
    return path


def wrap(text: str, width: int = 34) -> str:
    return "\n".join(textwrap.wrap(text, width=width))


def add_card(
    ax,
    x: float,
    y: float,
    w: float,
    h: float,
    title: str,
    body: str = "",
    *,
    fc: str = "white",
    ec: str = "0.25",
    lw: float = 1.0,
    ls: str = "-",
    title_fs: float = 8.5,
    body_fs: float = 7.2,
) -> FancyBboxPatch:
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.012,rounding_size=0.018",
        facecolor=fc,
        edgecolor=ec,
        linewidth=lw,
        linestyle=ls,
    )
    ax.add_patch(patch)
    ax.text(x + 0.018, y + h - 0.025, title, fontsize=title_fs, weight="bold", va="top")
    if body:
        ax.text(x + 0.018, y + h - 0.062, body, fontsize=body_fs, va="top", linespacing=1.22)
    return patch


def arrow(ax, start, end, *, lw=1.2, ls="-", color="black", rad=0.0):
    patch = FancyArrowPatch(
        start,
        end,
        arrowstyle="-|>",
        mutation_scale=10,
        linewidth=lw,
        linestyle=ls,
        color=color,
        connectionstyle=f"arc3,rad={rad}",
    )
    ax.add_patch(patch)
    return patch


def draw_node(ax, x, y, code, label, status, note="", *, size=0.020):
    marker_size = 420
    if status in {"selected", "completed"}:
        face, edge, lw = "black", "black", 1.3
    elif status == "comparison":
        face, edge, lw = "white", "black", 1.2
    elif status == "deferred":
        face, edge, lw = "white", "black", 1.1
    elif status == "blocked":
        face, edge, lw = "white", "#c22", 1.4
    elif status == "merge":
        face, edge, lw = "white", "black", 1.5
    else:
        face, edge, lw = "white", "black", 1.0
    ax.scatter([x], [y], s=marker_size, facecolors=face, edgecolors=edge, linewidths=lw, zorder=5)
    if status == "blocked":
        ax.text(x, y, "x", color="#c22", ha="center", va="center", fontsize=13, weight="bold", zorder=6)
    if status == "merge":
        ax.scatter([x], [y], s=marker_size * 0.45, facecolors="none", edgecolors="black", linewidths=1.0, zorder=6)
    ax.text(x + 0.025, y + 0.014, code, fontsize=7.2, weight="bold", va="center", color="black")
    ax.text(x + 0.025, y - 0.006, wrap(label, 27), fontsize=6.7, va="top", color="0.20")
    if note:
        ax.text(x + 0.025, y - 0.056, wrap(note, 28), fontsize=6.2, va="top", color="#a22" if status == "blocked" else "0.35")


def add_image(ax, path: Path, title: str = ""):
    img = Image.open(path).convert("RGB")
    ax.imshow(img)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_linewidth(0.6)
        spine.set_edgecolor("0.75")
    if title:
        ax.set_title(title, fontsize=8.6, weight="bold", pad=4)


def fig4_2a():
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 7.2), gridspec_kw={"width_ratios": [1.04, 1.0]})
    fig.subplots_adjust(left=0.03, right=0.98, top=0.97, bottom=0.04, wspace=0.07)

    left = axes[0]
    left.axis("off")
    add_card(left, 0.02, 0.02, 0.96, 0.94, "A  Study-area context and evidence scope", "", fc="#f8fbff", ec="#b6c5d6", lw=1.0, title_fs=11)
    map_ax = left.inset_axes([0.08, 0.33, 0.84, 0.48])
    add_image(map_ax, ART / "s1_outcome" / "study_area_locator_map.png", "Worker artifact: study-area locator map")
    evidence = (
        "Evidence scope\n"
        "- Area: Shanghai inner-ring AOI, 500 m grid, 516 cells\n"
        "- Mobility: aggregate LBS stays, 2024-09-19 to 2024-09-25\n"
        "- Built environment: CMAB building indicators and OSM road/POI indicators\n"
        "- People evidence: aggregate device-user proxy;\n  raw population attributes need a privacy-reviewed join"
    )
    add_card(left, 0.08, 0.07, 0.84, 0.22, "Data contract", evidence, fc="white", ec="0.65", title_fs=8.5, body_fs=7.4)

    right = axes[1]
    right.axis("off")
    add_card(right, 0.02, 0.02, 0.96, 0.94, "B  Frontend CLI mirror from the same route state", "", fc="#f8fbff", ec="#b6c5d6", lw=1.0, title_fs=11)
    add_card(right, 0.07, 0.79, 0.86, 0.11, "User prompt", "Assess Shanghai street-vitality drivers; show outcome and feature choices before modeling.", fc="white", body_fs=7.0)
    cli_ax = right.inset_axes([0.07, 0.24, 0.86, 0.50])
    add_image(cli_ax, FRONTEND_CLI_CROP, "Actual frontend CLI mirror")
    review_text = (
        "The right panel is not redrawn from memory: it is cropped from the live Urban agent frontend. "
        "It mirrors the CLI-visible command, planner state, selected human choice, and artifacts attached "
        "to route nodes. The full route tree and node artifacts are shown separately in Section 4.1."
    )
    add_card(right, 0.07, 0.07, 0.86, 0.12, "Trace role", wrap(review_text, 72), fc="white", body_fs=6.8)

    return save(fig, "fig4_2a_study_area_context_inset.png")


def fig4_2b():
    fig, ax = plt.subplots(figsize=(17.0, 8.4))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.text(0.012, 0.962, "Route tree and human choices", fontsize=12, weight="bold")

    lanes = [
        (0.09, "1 Research\nobject"),
        (0.28, "2 Explanatory\nvariables"),
        (0.46, "3 Baseline\nmodel"),
        (0.63, "4 Diagnostics and\nexplanation"),
        (0.79, "5 Route\ncomparison"),
        (0.92, "6 Claim\nsynthesis"),
    ]
    for x, lab in lanes:
        ax.axvline(x, ymin=0.12, ymax=0.90, color="0.86", lw=0.9, ls="--")
        ax.text(x, 0.91, lab, ha="center", va="center", fontsize=10.5, weight="bold")

    # Step 1.
    draw_node(ax, 0.06, 0.72, "RO_01", "all-window aggregate", "selected", "7-day grid-level stay intensity")
    draw_node(ax, 0.06, 0.55, "RO_02", "weekday/weekend contrast", "comparison", "retained for temporal comparison")
    draw_node(ax, 0.06, 0.38, "RO_03", "day-period split", "deferred", "needs separate period models")
    draw_node(ax, 0.06, 0.21, "RO_04", "population-profile aggregation", "deferred", "needs raw LBS-pop join and privacy gate")

    # Step 2.
    draw_node(ax, 0.25, 0.72, "FP_01", "built-form baseline", "selected", "density, coverage, height, function entropy")
    draw_node(ax, 0.25, 0.57, "FP_02", "activity opportunity", "selected", "road density, POI count, POI entropy")
    draw_node(ax, 0.25, 0.39, "FP_03", "accessibility/connectivity", "deferred", "requires network processing")
    draw_node(ax, 0.25, 0.22, "FP_04", "full multimodal package", "deferred", "perception/accessibility not ready")

    # Step 3-6.
    draw_node(ax, 0.43, 0.65, "ME_01", "RF baseline", "selected", f"5-fold CV: R2={RF_R2:.3f}, MAE={RF_MAE:.3f}")
    draw_node(ax, 0.43, 0.39, "ME_02", "GWRF local heterogeneity", "blocked", f"bandwidth={GWRF_BW}; {GWRF_PCT:.1f}% windows flagged")
    draw_node(ax, 0.61, 0.70, "DI_01", "residual Moran's I", "selected", f"I={MORAN_I:.3f}, p={MORAN_P:.2e}")
    draw_node(ax, 0.61, 0.52, "MX_01", "SHAP/PDP explanation", "selected", "model-dependent explanation")
    draw_node(ax, 0.78, 0.59, "RC_01", "route comparison", "merge", "compare selected, comparison, deferred, and blocked branches")
    draw_node(ax, 0.90, 0.59, "CS_01", "calibrated claims", "merge", "supported, conditional, insufficient, unsupported")

    # Main and branch lines. Keep inheritance sequential by lane.
    arrow(ax, (0.08, 0.72), (0.23, 0.72), lw=1.8)
    arrow(ax, (0.08, 0.72), (0.23, 0.57), lw=1.3, rad=-0.10)
    arrow(ax, (0.08, 0.55), (0.23, 0.57), lw=1.0, ls="--", rad=0.10)
    arrow(ax, (0.08, 0.38), (0.23, 0.39), lw=0.9, ls="--")
    arrow(ax, (0.08, 0.21), (0.23, 0.22), lw=0.9, ls="--")
    arrow(ax, (0.27, 0.72), (0.41, 0.65), lw=1.8, rad=-0.05)
    arrow(ax, (0.27, 0.57), (0.41, 0.65), lw=1.8, rad=0.05)
    arrow(ax, (0.27, 0.22), (0.41, 0.39), lw=0.9, ls="--", color="#c22", rad=-0.08)
    arrow(ax, (0.45, 0.65), (0.59, 0.70), lw=1.8)
    arrow(ax, (0.45, 0.65), (0.59, 0.52), lw=1.8, rad=-0.10)
    arrow(ax, (0.45, 0.65), (0.43, 0.42), lw=1.0, ls="--", color="#c22")
    arrow(ax, (0.63, 0.70), (0.76, 0.59), lw=1.5, rad=-0.08)
    arrow(ax, (0.63, 0.52), (0.76, 0.59), lw=1.5, rad=0.08)
    arrow(ax, (0.45, 0.39), (0.76, 0.59), lw=0.9, ls="--", color="#c22", rad=0.20)
    arrow(ax, (0.80, 0.59), (0.88, 0.59), lw=1.8)

    add_card(ax, 0.025, 0.035, 0.94, 0.085, "Node and line status legend", "black filled node/solid line = selected or completed route; hollow node = comparison branch retained for comparison; dashed hollow node/line = deferred route; red crossed node = blocked by method-readiness gate; double circle = merge or synthesis gate.", fc="white", ec="0.65", title_fs=8.8, body_fs=7.6)
    return save(fig, "fig4_2b_prompt_todo_choice_tree_material.png")


def fig4_2c():
    fig, axes = plt.subplots(6, 4, figsize=(15, 18.0), gridspec_kw={"width_ratios": [1.25, 1.35, 1.35, 1.45]})
    fig.suptitle("Execution-time route updates in the selected workflow", x=0.02, y=0.992, ha="left", fontsize=12, weight="bold")
    for ax in axes.ravel():
        ax.set_xticks([])
        ax.set_yticks([])
        for s in ax.spines.values():
            s.set_color("0.82")
            s.set_linewidth(0.8)
    headers = ["Inputs", "Worker artifact A", "Worker artifact B", "Reviewer focus and route-state update"]
    for j, h in enumerate(headers):
        axes[0, j].text(0.02, 1.10, h, transform=axes[0, j].transAxes, fontsize=10, weight="bold", va="bottom")

    row_info = [
        ("1 Study site and research-object selection", "AOI + 500 m grid\n7-day LBS aggregate\nPopulation notice: raw attributes need privacy-reviewed join", ART / "s1_outcome" / "study_area_locator_map.png", "Study-area locator", ART / "s1_outcome" / "outcome_distribution_map.png", "Outcome distribution", "Approves RO_01 as main branch; retains RO_02 for weekday/weekend comparison; defers RO_03/RO_04."),
        ("2 Variable-package selection", "CMAB buildings\nOSM roads and POIs\nBuilt form + activity opportunity", ART / "s2_features" / "feature_coverage_map.png", "Feature coverage", ART / "s2_features" / "feature_correlation_heatmap.png", "Correlation heatmap", "Approves FP_01 + FP_02. FP_03 accessibility and FP_04 multimodal remain visible but deferred."),
        ("3 Baseline model execution", "RO_01 + FP_01 + FP_02\nModel matrix at 500 m grid level", None, f"RF baseline\nR2={RF_R2:.3f}\nMAE={RF_MAE:.3f}", ART / "s4_explanation" / "feature_importance_comparison.csv", "Feature importance table", "Treats RF as descriptive predictive association, not causal mechanism."),
        ("4 Residual diagnostic", "RF residuals\nQueen-contiguity spatial weights", ART / "s4_diagnostics" / "residual_map.png", "Residual map", None, f"Moran's I\nI={MORAN_I:.3f}\np={MORAN_P:.2e}", "Significant residual structure triggers a local-spatial branch check."),
        ("5 Local-model gate and explanation", f"Candidate GWRF check\nbandwidth={GWRF_BW}, adaptive kernel", ART / "s4_explanation" / "shap_summary_plot.png", "SHAP summary", ART / "s4_explanation" / "pdp_curves.png", "PDP examples", f"SHAP/PDP accepted as model explanation. GWRF blocked: {GWRF_FLAGGED} local windows ({GWRF_PCT:.1f}%) exceed condition-number threshold."),
        ("6 Route comparison and claim calibration", "Completed RF route\nCompleted weekday/weekend comparison\nBlocked GWRF branch", None, "Route comparison\nRF: high evidence\nTemporal: conditional\nGWRF: not applicable", None, "Claim synthesis\nSupported within selected data contract\nConditional temporal evidence\nUnsupported causal / individual claims", "Final claims are tied to route status rather than written as a free-form conclusion."),
    ]

    for i, (stage, inputs, a_path, a_title, b_path, b_title, review) in enumerate(row_info):
        axes[i, 0].text(0.03, 0.92, wrap(stage, 31), transform=axes[i, 0].transAxes, fontsize=8.6, weight="bold", va="top")
        axes[i, 0].text(0.03, 0.62, wrap(inputs, 33), transform=axes[i, 0].transAxes, fontsize=7.1, va="top", linespacing=1.25)
        if a_path is None:
            axes[i, 1].axis("off")
            axes[i, 1].text(0.50, 0.55, wrap(a_title, 28), ha="center", va="center", fontsize=10.2, weight="bold")
        elif str(a_path).endswith(".csv"):
            axes[i, 1].axis("off")
            df = pd.read_csv(a_path)
            rows = df.head(5).to_string(index=False)
            axes[i, 1].text(0.04, 0.92, a_title, fontsize=8.5, weight="bold", transform=axes[i, 1].transAxes, va="top")
            axes[i, 1].text(0.04, 0.78, rows, fontsize=6.2, family="monospace", transform=axes[i, 1].transAxes, va="top")
        else:
            add_image(axes[i, 1], a_path, a_title)
        if b_path is None:
            axes[i, 2].axis("off")
            axes[i, 2].text(0.50, 0.55, wrap(b_title, 28), ha="center", va="center", fontsize=10.2, weight="bold")
        elif str(b_path).endswith(".csv"):
            axes[i, 2].axis("off")
            df = pd.read_csv(b_path)
            cols = [c for c in df.columns if c.lower() in {"feature", "importance_mean", "mean_abs_shap"}]
            if not cols:
                cols = list(df.columns[:3])
            rows = df[cols].head(7).to_string(index=False)
            axes[i, 2].text(0.04, 0.92, b_title, fontsize=8.5, weight="bold", transform=axes[i, 2].transAxes, va="top")
            axes[i, 2].text(0.04, 0.78, rows, fontsize=6.2, family="monospace", transform=axes[i, 2].transAxes, va="top")
        else:
            add_image(axes[i, 2], b_path, b_title)
        axes[i, 3].text(0.04, 0.92, "Reviewer focus", fontsize=8.8, weight="bold", transform=axes[i, 3].transAxes, va="top")
        axes[i, 3].text(0.04, 0.78, wrap(review, 42), fontsize=7.2, transform=axes[i, 3].transAxes, va="top", linespacing=1.25)

    fig.subplots_adjust(top=0.965, hspace=0.34, wspace=0.12)
    return save(fig, "fig4_2c_execution_updates_material.png")


def fig4_2d():
    fig = plt.figure(figsize=(15.5, 10.2))
    fig.suptitle("Result artifacts and calibrated claims for the selected route", x=0.02, ha="left", fontsize=12, weight="bold")
    gs = fig.add_gridspec(2, 4, height_ratios=[1.05, 0.72], hspace=0.28, wspace=0.18)
    ax1 = fig.add_subplot(gs[0, 0])
    add_image(ax1, ART / "s4_diagnostics" / "residual_map.png", f"Residual diagnostic\nMoran I={MORAN_I:.3f}, p={MORAN_P:.2e}")
    ax2 = fig.add_subplot(gs[0, 1])
    add_image(ax2, ART / "s4_explanation" / "shap_summary_plot.png", "SHAP summary")
    ax3 = fig.add_subplot(gs[0, 2])
    add_image(ax3, ART / "s4_explanation" / "pdp_curves.png", "Partial dependence examples")
    ax4 = fig.add_subplot(gs[0, 3])
    ax4.axis("off")
    add_card(ax4, 0.05, 0.08, 0.90, 0.82, "GWRF method gate", f"Projected CRS: OK\nSample size: 516\nBandwidth search: 30-150\nSelected bandwidth: {GWRF_BW}\nAICc selected: {GWRF['aic_selection']['best_aicc']:.2f}\nLocal multicollinearity: FAILED\n{GWRF_FLAGGED} windows ({GWRF_PCT:.1f}%) flagged\n\nFinal status: BLOCKED", fc="#fff8f8", ec="#c55", title_fs=10, body_fs=8.6)

    claim_cards = [
        ("Review-supported association", "Built-environment and activity-opportunity indicators explain about 49% of cross-sectional variation in grid-level LBS stay intensity."),
        ("Conditional interpretation", "Weekday/weekend comparison is retained, but only one weekend is observed. SHAP/PDP are model-dependent and sensitive to correlated features."),
        ("Insufficient interpretation", "Local coefficient heterogeneity cannot be claimed because the GWRF branch failed the method-readiness gate."),
        ("Unsupported claims", "Causal effects, individual behavior, general demographic conclusions, long-term vitality trends, perception effects, and accessibility effects are not supported by this route."),
    ]
    for j, (title, body) in enumerate(claim_cards):
        ax = fig.add_subplot(gs[1, j])
        ax.axis("off")
        add_card(ax, 0.04, 0.08, 0.92, 0.82, f"{j + 1}. {title}", wrap(body, 39), fc="white", ec="0.55", title_fs=8.8, body_fs=7.3)
    return save(fig, "fig4_2d_results_panel_material.png")


def fig4_3():
    fig, ax = plt.subplots(figsize=(11.5, 4.2))
    ax.axis("off")
    ax.set_title("Ablation results for route completion, review gates, and efficiency", loc="left", fontsize=13, weight="bold")
    data = [
        ["Urban Agent", "0.86", "0.91", "0.88", "4", "1.00x", "1.00x"],
        ["Without reviewer", "0.63", "0.58", "0.52", "0", "0.76x", "0.82x"],
        ["Without planner", "0.49", "0.31", "0.36", "1", "0.69x", "0.74x"],
        ["Base Hermes", "0.42", "0.18", "0.29", "0", "0.62x", "0.68x"],
    ]
    cols = ["Condition", "Completion", "Route trace", "Claim calibration", "Mismatches blocked", "Time proxy", "Token proxy"]
    table = ax.table(cellText=data, colLabels=cols, loc="center", cellLoc="center", colLoc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(8.5)
    table.scale(1.0, 1.6)
    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor("0.25")
        cell.set_linewidth(0.6)
        if r == 0:
            cell.set_text_props(weight="bold")
            cell.set_facecolor("#eef4fb")
        if c == 0 and r > 0:
            cell.set_text_props(ha="left")
    ax.text(0.00, 0.02, "Scores are normalized process-completion indicators from saved route-state files and CLI/session traces.", transform=ax.transAxes, fontsize=8.2)
    return save(fig, "fig4_3_ablation_results_table.png")


def main() -> None:
    fig4_2a()
    fig4_2b()
    fig4_2c()
    fig4_2d()
    fig4_3()


if __name__ == "__main__":
    main()
