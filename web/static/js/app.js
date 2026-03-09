/* ══════════════════════════════════════════════════════════════
   UrbanAgent — Frontend Application Logic
   ══════════════════════════════════════════════════════════════ */

// ── State ───────────────────────────────────────────────────
let ws = null;
let map = null;
let topoLayer = null;
let proposalLayer = null;
let currentCheckpointId = null;
let analysisGeoJSON = null;

const WS_URL = `ws://${location.host}/ws/analysis`;

// ── Initialise Map ──────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  map = L.map("map", {
    center: [31.21, 121.47],
    zoom: 16,
    zoomControl: true,
  });

  // Use a dark-themed basemap
  L.tileLayer(
    "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
    {
      attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
      maxZoom: 19,
    }
  ).addTo(map);

  topoLayer = L.layerGroup().addTo(map);
  proposalLayer = L.layerGroup().addTo(map);
});

// ── WebSocket lifecycle ─────────────────────────────────────
function connectWS() {
  return new Promise((resolve, reject) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      resolve(ws);
      return;
    }
    setConnectionStatus("connecting");
    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      setConnectionStatus("connected");
      resolve(ws);
    };

    ws.onmessage = (evt) => {
      const msg = JSON.parse(evt.data);
      handleServerMessage(msg);
    };

    ws.onerror = () => {
      setConnectionStatus("disconnected");
      reject(new Error("WebSocket connection failed"));
    };

    ws.onclose = () => {
      setConnectionStatus("disconnected");
      ws = null;
    };
  });
}

function setConnectionStatus(status) {
  const el = document.getElementById("connectionStatus");
  el.className = "connection-badge " + status;
  const labels = { connected: "已连接", disconnected: "未连接", connecting: "连接中…" };
  el.textContent = labels[status] || status;
}

// ── Start Analysis ──────────────────────────────────────────
async function startAnalysis() {
  const location = document.getElementById("locationInput").value.trim();
  const task = document.getElementById("taskInput").value.trim();
  const radius = parseInt(document.getElementById("radiusInput").value, 10);
  const mode = document.getElementById("modeSelect").value;

  if (!location || !task) {
    addChatMessage("system", "⚠️ 请填写位置和任务描述");
    return;
  }

  // Reset UI
  resetPipeline();
  document.getElementById("resultsPanel").classList.add("hidden");
  document.getElementById("checkpointDialog").classList.add("hidden");
  topoLayer.clearLayers();
  proposalLayer.clearLayers();

  addChatMessage("user", `📍 ${location}  |  📐 ${radius}m\n🎯 ${task}`);

  try {
    await connectWS();
  } catch {
    addChatMessage("system", "❌ 无法连接到 UrbanAgent 后端，请确认服务已启动 (python app.py)");
    return;
  }

  document.getElementById("btnStart").disabled = true;

  ws.send(JSON.stringify({ type: "start", location, task, radius, mode }));
  addChatMessage("agent", "🚀 分析已启动，Agent 正在执行流水线...");
}

// ── Handle server messages ──────────────────────────────────
function handleServerMessage(msg) {
  switch (msg.type) {
    case "stage":
      handleStage(msg);
      break;
    case "checkpoint":
      handleCheckpoint(msg);
      break;
    case "result":
      handleResult(msg);
      break;
    case "complete":
      handleComplete(msg);
      break;
    case "cancelled":
      addChatMessage("system", `⛔ ${msg.reason}`);
      document.getElementById("btnStart").disabled = false;
      break;
  }
}

function handleStage(msg) {
  const stageMap = {
    task_interpretation: "dp-1",
    perception: "dp-2",
    perception_exec: "dp-2",
    cognition: "dp-3",
    decision: "dp-4",
    parameters: "dp-5",
    visualization: "dp-6",
    interpretation: "dp-6",
  };

  const stepId = stageMap[msg.stage];
  if (!stepId) return;

  const stepEl = document.querySelector(`.step[data-step="${stepId}"]`);
  if (!stepEl) return;

  if (msg.status === "running") {
    stepEl.className = "step running";
    stepEl.querySelector(".step-status").textContent = "执行中...";
    if (msg.message) {
      addChatMessage("agent", msg.message);
    }
  } else if (msg.status === "done") {
    stepEl.className = "step done";
    stepEl.querySelector(".step-status").textContent = "✓ 完成";
  }
}

function handleCheckpoint(msg) {
  currentCheckpointId = msg.checkpoint_id;

  // Mark pipeline step as waiting
  const stepEl = document.querySelector(`.step[data-step="${msg.checkpoint_id}"]`);
  if (stepEl) {
    stepEl.className = "step waiting";
    stepEl.querySelector(".step-status").textContent = "等待确认...";
  }

  // Show checkpoint dialog
  const dialog = document.getElementById("checkpointDialog");
  dialog.classList.remove("hidden");
  document.getElementById("checkpointTitle").textContent = msg.title;
  document.getElementById("checkpointDesc").textContent = msg.description;
  document.getElementById("checkpointData").textContent = JSON.stringify(msg.data, null, 2);

  // If cognition checkpoint, draw topology on map
  if (msg.checkpoint_id === "dp-3" && msg.data.nodes) {
    drawTopology(msg.data);
  }

  // If proposal checkpoint, draw proposals on map
  if (msg.checkpoint_id === "dp-4" && msg.data.proposals) {
    drawProposals(msg.data.proposals);
  }

  addChatMessage("agent", `🔔 检查点 ${msg.title}\n${msg.description}`);
}

function respondCheckpoint(action) {
  if (!ws || !currentCheckpointId) return;

  ws.send(JSON.stringify({
    type: "checkpoint_response",
    checkpoint_id: currentCheckpointId,
    action: action,
  }));

  // Update UI
  const stepEl = document.querySelector(`.step[data-step="${currentCheckpointId}"]`);
  if (stepEl) {
    if (action === "approve") {
      stepEl.className = "step done";
      stepEl.querySelector(".step-status").textContent = "✓ 已确认";
    } else if (action === "reject") {
      stepEl.className = "step rejected";
      stepEl.querySelector(".step-status").textContent = "✗ 已拒绝";
    } else {
      stepEl.className = "step done";
      stepEl.querySelector(".step-status").textContent = "✎ 已修改确认";
    }
  }

  document.getElementById("checkpointDialog").classList.add("hidden");
  const labels = { approve: "确认", modify: "修改后确认", reject: "拒绝" };
  addChatMessage("user", `${currentCheckpointId.toUpperCase()}: ${labels[action]}`);
  currentCheckpointId = null;
}

function handleResult(msg) {
  if (msg.stage === "perception") {
    addChatMessage("agent",
      `📡 感知完成：获取 ${msg.data.stats.roads} 条道路、${msg.data.stats.buildings} 栋建筑、${msg.data.stats.pois} 个POI`);

    if (msg.data.center) {
      map.setView(msg.data.center, 16);
    }
  }

  if (msg.stage === "visualization" && msg.data.geojson) {
    drawGeoJSON(msg.data.geojson);
  }
}

function handleComplete(msg) {
  addChatMessage("agent", "🎉 分析完成！请查看右侧结果面板。");
  document.getElementById("btnStart").disabled = false;

  analysisGeoJSON = msg.geojson;
  showResults(msg.summary);
}

// ── Map drawing helpers ─────────────────────────────────────
function drawTopology(data) {
  topoLayer.clearLayers();

  // Draw nodes
  if (data.nodes) {
    data.nodes.forEach((n) => {
      const color = {
        junction: "#fb923c",
        plaza: "#60a5fa",
        landmark: "#fbbf24",
        barrier: "#f87171",
        cluster: "#a78bfa",
      }[n.type] || "#8b91a7";

      const radius = n.type === "landmark" ? 8 : n.type === "barrier" ? 10 : 6;

      L.circleMarker([n.lat, n.lng], {
        radius: radius,
        color: color,
        fillColor: color,
        fillOpacity: 0.7,
        weight: 2,
      })
        .bindPopup(`<b>${n.name || n.id}</b><br/>类型: ${n.type}${n.degree ? '<br/>度: ' + n.degree : ''}`)
        .addTo(topoLayer);
    });
  }

  // Draw edges
  if (data.edges) {
    data.edges.forEach((e) => {
      const fromNode = data.nodes.find((n) => n.id === e.from);
      const toNode = data.nodes.find((n) => n.id === e.to);
      if (!fromNode || !toNode) return;

      const edgeColor = {
        connected: "#4ade80",
        adjacent: "#60a5fa",
        separated: "#f87171",
      }[e.type] || "#8b91a7";

      const dashArray = e.type === "separated" ? "6 4" : null;

      L.polyline(
        [[fromNode.lat, fromNode.lng], [toNode.lat, toNode.lng]],
        { color: edgeColor, weight: 2, opacity: 0.7, dashArray }
      )
        .bindPopup(`${e.type} | ${e.distance_m}m`)
        .addTo(topoLayer);
    });
  }
}

function drawProposals(proposals) {
  proposalLayer.clearLayers();

  proposals.forEach((p) => {
    const geo = p.geometry;
    const color = p.color || "#5b6cf7";
    let layer;

    if (geo.type === "Point") {
      layer = L.circleMarker([geo.coordinates[1], geo.coordinates[0]], {
        radius: 12,
        color: color,
        fillColor: color,
        fillOpacity: 0.35,
        weight: 3,
      });
    } else if (geo.type === "LineString") {
      const latlngs = geo.coordinates.map((c) => [c[1], c[0]]);
      layer = L.polyline(latlngs, { color: color, weight: 4, opacity: 0.85 });
    } else if (geo.type === "Polygon") {
      const latlngs = geo.coordinates[0].map((c) => [c[1], c[0]]);
      layer = L.polygon(latlngs, { color: color, fillColor: color, fillOpacity: 0.25, weight: 2 });
    }

    if (layer) {
      layer
        .bindPopup(`<b>${p.title}</b><br/>${p.description}<br/><em>${p.impact}</em>`)
        .addTo(proposalLayer);
    }
  });
}

function drawGeoJSON(geojson) {
  if (!geojson) return;
  L.geoJSON(geojson, {
    style: (feature) => ({
      color: feature.properties.color || "#5b6cf7",
      weight: 3,
      fillOpacity: 0.2,
    }),
    pointToLayer: (feature, latlng) =>
      L.circleMarker(latlng, {
        radius: 10,
        color: feature.properties.color || "#5b6cf7",
        fillOpacity: 0.35,
      }),
    onEachFeature: (feature, layer) => {
      if (feature.properties) {
        layer.bindPopup(
          `<b>${feature.properties.title || ""}</b><br/>${feature.properties.description || ""}`
        );
      }
    },
  }).addTo(proposalLayer);
}

// ── Show results ────────────────────────────────────────────
function showResults(summary) {
  const panel = document.getElementById("resultsPanel");
  panel.classList.remove("hidden");

  // Metrics
  const metricsEl = document.getElementById("resultMetrics");
  const metrics = summary.metrics || {};
  metricsEl.innerHTML = Object.entries(metrics)
    .map(
      ([k, v]) => `
      <div class="metric-card">
        <div class="metric-value">${typeof v === 'number' ? v.toFixed(2) : v}</div>
        <div class="metric-label">${formatMetricName(k)}</div>
      </div>`
    )
    .join("");

  // Findings
  const findingsEl = document.getElementById("resultFindings");
  if (summary.key_findings) {
    findingsEl.innerHTML =
      "<ul>" + summary.key_findings.map((f) => `<li>${f}</li>`).join("") + "</ul>";
  }

  // Narrative
  const narrativeEl = document.getElementById("resultNarrative");
  narrativeEl.textContent = summary.narrative || "";
}

function formatMetricName(key) {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

// ── Chat helpers ────────────────────────────────────────────
function addChatMessage(role, text) {
  const container = document.getElementById("chatMessages");
  const div = document.createElement("div");
  div.className = `msg msg-${role}`;
  div.innerHTML = `<div class="msg-content">${escapeHtml(text).replace(/\n/g, "<br/>")}</div>`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.appendChild(document.createTextNode(str));
  return div.innerHTML;
}

// ── Pipeline reset ──────────────────────────────────────────
function resetPipeline() {
  document.querySelectorAll(".step").forEach((el) => {
    el.className = "step";
    el.querySelector(".step-status").textContent = "等待开始";
  });
}

// ── Layer toggles ───────────────────────────────────────────
function toggleLayer(name) {
  if (name === "topo") {
    if (map.hasLayer(topoLayer)) map.removeLayer(topoLayer);
    else map.addLayer(topoLayer);
  } else if (name === "proposals") {
    if (map.hasLayer(proposalLayer)) map.removeLayer(proposalLayer);
    else map.addLayer(proposalLayer);
  }
}

function fitBounds() {
  const bounds = L.latLngBounds([]);
  topoLayer.eachLayer((l) => {
    if (l.getLatLng) bounds.extend(l.getLatLng());
    if (l.getBounds) bounds.extend(l.getBounds());
  });
  proposalLayer.eachLayer((l) => {
    if (l.getLatLng) bounds.extend(l.getLatLng());
    if (l.getBounds) bounds.extend(l.getBounds());
  });
  if (bounds.isValid()) map.fitBounds(bounds, { padding: [30, 30] });
}

// ── Export helpers ───────────────────────────────────────────
function exportGeoJSON() {
  if (!analysisGeoJSON) {
    addChatMessage("system", "暂无可导出的 GeoJSON 数据");
    return;
  }
  const blob = new Blob([JSON.stringify(analysisGeoJSON, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "urbanagent_analysis.geojson";
  a.click();
  URL.revokeObjectURL(url);
  addChatMessage("system", "✅ GeoJSON 已导出");
}

function exportReport() {
  const findings = document.getElementById("resultFindings").textContent;
  const narrative = document.getElementById("resultNarrative").textContent;
  const report = `# UrbanAgent 分析报告\n\n## 关键发现\n${findings}\n\n## 分析叙述\n${narrative}`;
  const blob = new Blob([report], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "urbanagent_report.md";
  a.click();
  URL.revokeObjectURL(url);
  addChatMessage("system", "✅ 报告已导出");
}
