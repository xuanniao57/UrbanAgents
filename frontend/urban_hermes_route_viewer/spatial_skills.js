(function registerUrbanSpatialSkills(global) {
  "use strict";

  const MAP_STYLE = "https://basemaps.cartocdn.com/gl/positron-nolabels-gl-style/style.json";
  const NEGATIVE = [0, 114, 178, 218];
  const NEUTRAL = [247, 247, 247, 226];
  const POSITIVE = [213, 94, 0, 218];

  function number(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function interpolate(left, right, amount) {
    return left.map((value, index) => Math.round(value + (right[index] - value) * amount));
  }

  function residualColor(value, domain = 3) {
    const normalized = clamp(number(value) / domain, -1, 1);
    return normalized < 0
      ? interpolate(NEGATIVE, NEUTRAL, normalized + 1)
      : interpolate(NEUTRAL, POSITIVE, normalized);
  }

  function cleanRows(rows) {
    return (rows || []).map(row => ({
      ...row,
      lon: number(row.lon),
      lat: number(row.lat),
      residual: number(row.residual),
      observed_log_stays: number(row.observed_log_stays),
      predicted_log_stays: number(row.predicted_log_stays)
    })).filter(row => [row.lon, row.lat, row.residual].every(value => value !== null));
  }

  function initialViewState(rows) {
    const lons = rows.map(row => row.lon);
    const lats = rows.map(row => row.lat);
    const west = Math.min(...lons);
    const east = Math.max(...lons);
    const south = Math.min(...lats);
    const north = Math.max(...lats);
    const span = Math.max(east - west, (north - south) * 1.35, 0.01);
    return {
      longitude: (west + east) / 2,
      latitude: (south + north) / 2,
      zoom: clamp(Math.log2(360 / span) - 1.35, 8.5, 12.5),
      pitch: 0,
      bearing: 0
    };
  }

  function haversineKm(a, b) {
    const radians = value => value * Math.PI / 180;
    const dLat = radians(b.lat - a.lat);
    const dLon = radians(b.lon - a.lon);
    const lat1 = radians(a.lat);
    const lat2 = radians(b.lat);
    const h = Math.sin(dLat / 2) ** 2
      + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
    return 6371 * 2 * Math.atan2(Math.sqrt(h), Math.sqrt(1 - h));
  }

  function averageResidual(points) {
    if (!points?.length) return 0;
    return points.reduce((sum, point) => sum + (number(point.residual) || 0), 0) / points.length;
  }

  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  function renderResidualMap(target, inputRows, options = {}) {
    const host = typeof target === "string" ? document.querySelector(target) : target;
    const rows = cleanRows(inputRows);
    if (!host) throw new Error("deck.gl target was not found");
    if (!global.deck?.DeckGL) throw new Error("deck.gl standalone runtime is unavailable");
    if (!rows.length) throw new Error("No valid spatial residual rows were supplied");

    host.innerHTML = "";
    host.classList.add("deck-map-host");
    let mode = "points";
    let selectedIds = new Set();
    let deckInstance = null;
    const rowId = row => String(row.grid_id ?? `${row.lon},${row.lat}`);
    const isSelected = row => !selectedIds.size || selectedIds.has(rowId(row));

    const announce = (selectedRows, source) => {
      options.onSelectionChange?.(selectedRows, {
        source,
        selected: selectedRows.length,
        total: rows.length,
        mode
      });
    };

    const pointLayer = () => new global.deck.ScatterplotLayer({
      id: `residual-points-${selectedIds.size}`,
      data: rows,
      pickable: true,
      opacity: 0.94,
      stroked: true,
      filled: true,
      radiusUnits: "meters",
      getPosition: row => [row.lon, row.lat],
      getRadius: row => isSelected(row) ? 285 : 210,
      getFillColor: row => {
        const color = residualColor(row.residual);
        return isSelected(row) ? color : [...color.slice(0, 3), 55];
      },
      getLineColor: row => isSelected(row) ? [17, 17, 17, 230] : [255, 255, 255, 100],
      getLineWidth: row => isSelected(row) ? 1.4 : 0.5,
      lineWidthUnits: "pixels",
      updateTriggers: {
        getRadius: [selectedIds.size],
        getFillColor: [selectedIds.size],
        getLineColor: [selectedIds.size],
        getLineWidth: [selectedIds.size]
      }
    });

    const hexLayer = () => new global.deck.HexagonLayer({
      id: `residual-hexagons-${selectedIds.size}`,
      data: rows,
      pickable: true,
      extruded: false,
      gpuAggregation: false,
      radius: 650,
      coverage: 0.9,
      getPosition: row => [row.lon, row.lat],
      getColorValue: points => averageResidual(points),
      colorScaleType: "linear",
      colorDomain: [-3, 3],
      colorRange: [NEGATIVE, [86, 180, 233, 215], NEUTRAL, [230, 159, 0, 215], POSITIVE]
    });

    const setLayers = () => {
      deckInstance?.setProps({ layers: [mode === "hexagons" ? hexLayer() : pointLayer()] });
    };

    const selectRows = (selectedRows, source) => {
      selectedIds = new Set(selectedRows.map(rowId));
      setLayers();
      announce(selectedRows.length ? selectedRows : rows, source);
    };

    const handleClick = info => {
      if (!info?.object) return;
      if (mode === "hexagons") {
        const selectedRows = (info.object.points || []).map(point => point.source || point).filter(Boolean);
        selectRows(selectedRows, "hexagon");
        return;
      }
      const center = info.object;
      selectRows(rows.filter(row => haversineKm(center, row) <= 2), "2 km neighbourhood");
    };

    deckInstance = new global.deck.DeckGL({
      container: host,
      map: global.maplibregl || false,
      mapStyle: MAP_STYLE,
      mapOptions: { attributionControl: true },
      initialViewState: initialViewState(rows),
      controller: { dragRotate: false, touchRotate: false, doubleClickZoom: false },
      useDevicePixels: Math.min(global.devicePixelRatio || 1, 2),
      layers: [pointLayer()],
      getCursor: ({ isDragging, isHovering }) => isDragging ? "grabbing" : isHovering ? "pointer" : "grab",
      getTooltip: ({ object }) => {
        if (!object) return null;
        if (object.points) {
          return {
            html: `<strong>${object.points.length} grid cells</strong><br>Mean residual: ${averageResidual(object.points.map(point => point.source || point)).toFixed(2)}`,
            style: { backgroundColor: "#111", color: "#fff", fontFamily: "Arial", fontSize: "11px" }
          };
        }
        return {
          html: `<strong>${object.grid_id || "Grid cell"}</strong><br>Observed: ${number(object.observed_log_stays)?.toFixed(2) ?? "n/a"}<br>Predicted: ${number(object.predicted_log_stays)?.toFixed(2) ?? "n/a"}<br>Residual: ${number(object.residual)?.toFixed(2) ?? "n/a"}`,
          style: { backgroundColor: "#111", color: "#fff", fontFamily: "Arial", fontSize: "11px" }
        };
      },
      onClick: handleClick,
      onLoad: () => {
        const map = deckInstance?.getMapboxMap?.();
        if (map && global.maplibregl?.ScaleControl && !host.dataset.scaleAdded) {
          map.addControl(new global.maplibregl.ScaleControl({ maxWidth: 90, unit: "metric" }), "bottom-left");
          host.dataset.scaleAdded = "true";
        }
      }
    });

    return {
      deck: deckInstance,
      rows,
      setMode(nextMode) {
        mode = nextMode === "hexagons" ? "hexagons" : "points";
        selectedIds = new Set();
        setLayers();
        announce(rows, "mode change");
      },
      reset() {
        selectedIds = new Set();
        setLayers();
        announce(rows, "reset");
      },
      exportPng(filename = "urban-hermes-residual-map-preview.png", scale = 3) {
        const canvases = [...host.querySelectorAll("canvas")];
        if (!canvases.length) throw new Error("No map canvas is available for export");
        const bounds = host.getBoundingClientRect();
        const output = document.createElement("canvas");
        output.width = Math.round(bounds.width * scale);
        output.height = Math.round(bounds.height * scale);
        const context = output.getContext("2d");
        context.fillStyle = "#ffffff";
        context.fillRect(0, 0, output.width, output.height);
        canvases.forEach(canvas => context.drawImage(canvas, 0, 0, output.width, output.height));
        output.toBlob(blob => blob && downloadBlob(blob, filename), "image/png");
      },
      finalize() {
        deckInstance?.finalize();
        deckInstance = null;
      }
    };
  }

  global.URBAN_SPATIAL_SKILLS = Object.freeze({
    version: "1.0.0",
    renderer: "deck.gl 9.3.7 + MapLibre GL JS 5.24.0",
    renderResidualMap
  });
})(window);
