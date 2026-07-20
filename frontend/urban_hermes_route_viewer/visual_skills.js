(function registerUrbanVisualSkills(global) {
  "use strict";

  const COLORS = {
    ink: "#111111",
    muted: "#686868",
    grid: "#dedede",
    paper: "#ffffff",
    blue: "#0072B2",
    sky: "#56B4E9",
    orange: "#E69F00",
    vermillion: "#D55E00",
    green: "#009E73",
    purple: "#CC79A7"
  };

  const BASE_CONFIG = {
    background: COLORS.paper,
    font: "Arial",
    view: { stroke: null },
    axis: {
      domainColor: COLORS.ink,
      domainWidth: 1,
      gridColor: COLORS.grid,
      gridOpacity: 0.7,
      labelColor: COLORS.ink,
      labelFont: "Arial",
      labelFontSize: 11,
      tickColor: COLORS.ink,
      titleColor: COLORS.ink,
      titleFont: "Arial",
      titleFontSize: 11,
      titleFontWeight: 600,
      titlePadding: 8
    },
    legend: {
      labelColor: COLORS.ink,
      labelFont: "Arial",
      labelFontSize: 11,
      symbolStrokeColor: COLORS.ink,
      titleColor: COLORS.ink,
      titleFont: "Arial",
      titleFontSize: 11,
      titleFontWeight: 600
    },
    title: {
      anchor: "start",
      color: COLORS.ink,
      font: "Arial",
      fontSize: 13,
      fontWeight: 600,
      subtitleColor: COLORS.muted,
      subtitleFont: "Arial",
      subtitleFontSize: 11,
      offset: 10
    }
  };

  function number(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function cleanRows(rows, fields) {
    return (rows || []).map(row => {
      const next = { ...row };
      fields.forEach(field => { next[field] = number(row[field]); });
      return next;
    }).filter(row => fields.every(field => row[field] !== null));
  }

  function withBase(spec) {
    return {
      $schema: "https://vega.github.io/schema/vega-lite/v6.json",
      config: BASE_CONFIG,
      ...spec
    };
  }

  function spatialResidualLinked(rows) {
    const values = cleanRows(
      (rows || []).filter(row => row.scale === "500m" && row.scheme === "spatial_block"),
      ["lon", "lat", "observed_log_stays", "predicted_log_stays", "residual"]
    );

    const selection = {
      name: "spatialBrush",
      select: { type: "interval", encodings: ["x", "y"], clear: "dblclick" }
    };

    const tooltip = [
      { field: "grid_id", type: "nominal", title: "Grid" },
      { field: "observed_log_stays", type: "quantitative", title: "Observed log stays", format: ".2f" },
      { field: "predicted_log_stays", type: "quantitative", title: "Predicted log stays", format: ".2f" },
      { field: "residual", type: "quantitative", title: "Residual", format: ".2f" }
    ];

    return withBase({
      data: { values },
      vconcat: [
        {
          hconcat: [
            {
              width: 430,
              height: 315,
              title: {
                text: "Residual geography",
                subtitle: "Drag to inspect a district-sized subset; double-click to clear."
              },
              params: [selection],
              mark: { type: "square", size: 86, opacity: 0.92, stroke: "#ffffff", strokeWidth: 0.25 },
              encoding: {
                x: { field: "lon", type: "quantitative", title: "Longitude (°E)", scale: { zero: false, nice: false } },
                y: { field: "lat", type: "quantitative", title: "Latitude (°N)", scale: { zero: false, nice: false } },
                color: {
                  field: "residual",
                  type: "quantitative",
                  title: "Observed − predicted",
                  scale: { scheme: "redblue", domainMid: 0, reverse: true }
                },
                opacity: { condition: { param: "spatialBrush", value: 1 }, value: 0.42 },
                tooltip
              }
            },
            {
              width: 310,
              height: 315,
              title: {
                text: "Observed vs predicted",
                subtitle: "Linked to the spatial selection. Dashed line is perfect agreement."
              },
              layer: [
                {
                  transform: [{ filter: { param: "spatialBrush", empty: true } }],
                  mark: { type: "point", filled: true, size: 34, opacity: 0.72, color: COLORS.blue },
                  encoding: {
                    x: { field: "observed_log_stays", type: "quantitative", title: "Observed log stays", scale: { zero: false } },
                    y: { field: "predicted_log_stays", type: "quantitative", title: "Predicted log stays", scale: { zero: false } },
                    tooltip
                  }
                },
                {
                  data: { values: [{ x: 3, y: 3 }, { x: 13, y: 13 }] },
                  mark: { type: "line", color: COLORS.ink, strokeDash: [5, 4], opacity: 0.65 },
                  encoding: {
                    x: { field: "x", type: "quantitative" },
                    y: { field: "y", type: "quantitative" }
                  }
                }
              ]
            }
          ],
          spacing: 22
        },
        {
          width: 772,
          height: 105,
          title: { text: "Residual distribution", subtitle: "A centered, narrow distribution is preferable." },
          transform: [{ filter: { param: "spatialBrush", empty: true } }, { bin: { maxbins: 34 }, field: "residual", as: ["bin0", "bin1"] }],
          mark: { type: "bar", color: COLORS.ink },
          encoding: {
            x: { field: "bin0", bin: "binned", type: "quantitative", title: "Residual (log stays)" },
            x2: { field: "bin1" },
            y: { aggregate: "count", type: "quantitative", title: "Grid cells" },
            tooltip: [
              { field: "bin0", type: "quantitative", title: "From", format: ".2f" },
              { field: "bin1", type: "quantitative", title: "To", format: ".2f" },
              { aggregate: "count", type: "quantitative", title: "Grid cells" }
            ]
          }
        }
      ],
      spacing: 18,
      resolve: { scale: { color: "independent" } }
    });
  }

  function validationComparison(rows) {
    const packageLabels = {
      built_form: "Built form",
      activity_opportunity: "Activity opportunity",
      combined: "Combined"
    };
    const values = cleanRows(
      (rows || []).filter(row => row.model === "random_forest" && row.scheme === "spatial_block"),
      ["r2_mean", "r2_sd", "train_r2"]
    ).map(row => ({
      ...row,
      package_label: packageLabels[row.package] || row.package,
      scale_label: row.scale === "500m" ? "500 m" : "200 m"
    }));

    return withBase({
      data: { values },
      width: 285,
      height: 180,
      title: {
        text: "What survives spatial validation?",
        subtitle: "Repeated five-by-five spatial blocks; RF mean R² ± SD."
      },
      layer: [
        {
          mark: { type: "bar", cornerRadiusEnd: 0 },
          encoding: {
            x: { field: "package_label", type: "nominal", title: null, sort: ["Built form", "Activity opportunity", "Combined"], axis: { labelAngle: 0, labelLimit: 95 } },
            xOffset: { field: "scale_label", sort: ["200 m", "500 m"] },
            y: { field: "r2_mean", type: "quantitative", title: "Spatial-block R²", scale: { domain: [0, 0.42] } },
            color: {
              field: "scale_label",
              type: "nominal",
              title: "Grid",
              scale: { domain: ["200 m", "500 m"], range: [COLORS.sky, COLORS.blue] }
            },
            tooltip: [
              { field: "package_label", type: "nominal", title: "Feature package" },
              { field: "scale_label", type: "nominal", title: "Grid" },
              { field: "r2_mean", type: "quantitative", title: "Spatial-block R²", format: ".3f" },
              { field: "r2_sd", type: "quantitative", title: "SD", format: ".3f" }
            ]
          }
        },
        {
          mark: { type: "errorbar", ticks: true, color: COLORS.ink },
          encoding: {
            x: { field: "package_label", type: "nominal", sort: ["Built form", "Activity opportunity", "Combined"] },
            xOffset: { field: "scale_label", sort: ["200 m", "500 m"] },
            y: { field: "r2_mean", type: "quantitative" },
            yError: { field: "r2_sd" }
          }
        }
      ]
    });
  }

  function fitGap(rows) {
    const values = cleanRows(
      (rows || []).filter(row => row.model === "random_forest" && row.scheme === "spatial_block" && row.package === "combined"),
      ["r2_mean", "train_r2"]
    ).flatMap(row => [
      { scale: row.scale === "500m" ? "500 m" : "200 m", regime: "Training fit", value: row.train_r2 },
      { scale: row.scale === "500m" ? "500 m" : "200 m", regime: "Spatial validation", value: row.r2_mean }
    ]);

    return withBase({
      data: { values },
      width: 285,
      height: 180,
      title: {
        text: "The fit trap",
        subtitle: "The same model looks different when nearby zones cannot leak across folds."
      },
      layer: [
        {
          mark: { type: "line", color: "#9a9a9a", strokeWidth: 2 },
          encoding: {
            x: { field: "value", type: "quantitative", title: "R²", scale: { domain: [0, 0.8] } },
            y: { field: "scale", type: "nominal", title: "Grid", sort: ["500 m", "200 m"] },
            detail: { field: "scale" }
          }
        },
        {
          mark: { type: "point", filled: true, size: 90 },
          encoding: {
            x: { field: "value", type: "quantitative" },
            y: { field: "scale", type: "nominal", sort: ["500 m", "200 m"] },
            color: {
              field: "regime",
              type: "nominal",
              title: null,
              scale: { domain: ["Training fit", "Spatial validation"], range: [COLORS.vermillion, COLORS.blue] }
            },
            tooltip: [
              { field: "scale", type: "nominal", title: "Grid" },
              { field: "regime", type: "nominal", title: "Evaluation" },
              { field: "value", type: "quantitative", title: "R²", format: ".3f" }
            ]
          }
        }
      ]
    });
  }

  function cohortRetention(rows) {
    const labels = {
      adult: "Adult",
      middle_aged: "Middle-aged",
      older_adult: "Older adult",
      young_adult: "Young adult"
    };
    const values = cleanRows(
      (rows || []).filter(row => row.scale === "500m" && row.cohort_variable === "age_cohort_5class"),
      ["weekend_weekday_per_day_ratio"]
    ).map(row => ({ ...row, cohort_label: labels[row.cohort] || row.cohort }));

    return withBase({
      data: { values },
      width: 285,
      height: 180,
      title: {
        text: "Whose activity persists on weekends?",
        subtitle: "Weekend/weekday stays per day, 500 m grid. One means parity."
      },
      layer: [
        {
          mark: { type: "rule", color: COLORS.vermillion, strokeDash: [4, 3] },
          encoding: { x: { datum: 1 } }
        },
        {
          mark: { type: "bar", color: COLORS.ink },
          encoding: {
            y: { field: "cohort_label", type: "nominal", title: null, sort: "-x" },
            x: { field: "weekend_weekday_per_day_ratio", type: "quantitative", title: "Weekend / weekday per-day ratio", scale: { domain: [0, 1.05] } },
            tooltip: [
              { field: "cohort_label", type: "nominal", title: "Cohort" },
              { field: "weekend_weekday_per_day_ratio", type: "quantitative", title: "Ratio", format: ".3f" }
            ]
          }
        }
      ]
    });
  }

  function epistemicDiagnostics(findings) {
    const temporal = findings?.weekday_weekend || {};
    const moran = findings?.spatial_oof_residual_moran || {};
    const values = ["500m", "200m"].flatMap(scale => [
      {
        scale: scale === "500m" ? "500 m" : "200 m",
        metric: "Weekday–weekend rank ρ",
        value: number(temporal[scale]?.weekday_weekend_spatial_spearman_rho)
      },
      {
        scale: scale === "500m" ? "500 m" : "200 m",
        metric: "Residual Moran's I",
        value: number(moran[scale]?.moran_i)
      }
    ]).filter(row => row.value !== null);

    return withBase({
      data: { values },
      width: 285,
      height: 180,
      title: {
        text: "Two signals, two meanings",
        subtitle: "Temporal stability can coexist with spatially structured error."
      },
      mark: { type: "bar" },
      encoding: {
        x: { field: "scale", type: "nominal", title: "Grid", sort: ["500 m", "200 m"] },
        xOffset: { field: "metric" },
        y: { field: "value", type: "quantitative", title: "Coefficient", scale: { domain: [0, 1] } },
        color: {
          field: "metric",
          type: "nominal",
          title: null,
          scale: { domain: ["Weekday–weekend rank ρ", "Residual Moran's I"], range: [COLORS.green, COLORS.orange] }
        },
        tooltip: [
          { field: "scale", type: "nominal", title: "Grid" },
          { field: "metric", type: "nominal", title: "Diagnostic" },
          { field: "value", type: "quantitative", title: "Value", format: ".3f" }
        ]
      }
    });
  }

  const REGISTRY = Object.freeze({
    "spatial.residual.linked": { renderer: spatialResidualLinked, dataKey: "predictions" },
    "validation.packages.compare": { renderer: validationComparison, dataKey: "modelSummary" },
    "validation.fit_gap": { renderer: fitGap, dataKey: "modelSummary" },
    "population.cohort_retention": { renderer: cohortRetention, dataKey: "temporalSummary" },
    "diagnostic.epistemic_summary": { renderer: epistemicDiagnostics, dataKey: "findings" }
  });

  function render(skillId, payload) {
    const entry = REGISTRY[skillId];
    if (!entry) throw new Error(`Unknown visualization skill: ${skillId}`);
    return entry.renderer(payload);
  }

  global.URBAN_VIS_SKILLS = Object.freeze({
    colors: COLORS,
    registry: REGISTRY,
    render,
    spatialResidualLinked,
    validationComparison,
    fitGap,
    cohortRetention,
    epistemicDiagnostics
  });
})(window);
