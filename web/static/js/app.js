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
let latestCognitionResult = null;
let currentRunId = null;
let runtimeTodos = new Map();
let runtimeArtifacts = new Map();

const WS_URL = `ws://${location.host}/ws/analysis`;

// ── Initialise Map ──────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  map = L.map("map", {
    center: [29.8791, 121.5564],
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

  refreshQgisStatus();
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
  resetRuntimeWorkbench();
  document.getElementById("resultsPanel").classList.add("hidden");
  document.getElementById("checkpointDialog").classList.add("hidden");
  topoLayer.clearLayers();
  proposalLayer.clearLayers();

  addChatMessage("user", `${location} | ${radius}m\n${task}`);

  try {
    await connectWS();
  } catch {
    addChatMessage("system", "❌ 无法连接到 UrbanAgent 后端，请确认服务已启动 (python app.py)");
    return;
  }

  document.getElementById("btnStart").disabled = true;

  const caseId = /宁波|老外滩|old bund|heritage|历史街区|保护/i.test(`${location} ${task}`) ? "ningbo_old_bund" : undefined;
  ws.send(JSON.stringify({ type: "start", location, task, radius, mode, case_id: caseId }));
  addChatMessage("agent", "分析已启动，UrbanAgent 正在执行多智能体流水线...");
}

// ── Handle server messages ──────────────────────────────────
function handleServerMessage(msg) {
  switch (msg.type) {
    case "event":
      handleRuntimeEvent(msg.event);
      break;
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

function handleRuntimeEvent(event) {
  if (!event || !event.type) return;
  const payload = event.payload || {};
  currentRunId = event.run_id || currentRunId;

  const pipelineBridge = {
    run_started: "dp-1",
    todo_created: "dp-1",
    reasoning_step: "dp-3",
    artifact_created: "dp-6",
    review_completed: "dp-6",
    qc_completed: "dp-6",
    run_completed: "dp-6",
  };
  const step = event.type === "agent_started" ? pipelineStepForAgent(payload.agent) : pipelineBridge[event.type];
  if (step) markPipelineStep(step, event.type === "run_completed" ? "done" : "running");

  if (event.type === "run_started") {
    const caseText = payload.case_study ? `，case=${payload.case_study.title}` : "";
    addChatMessage("agent", `UrbanAgent 已接收任务，routing=${payload.routing?.mode || "adaptive"}，run=${event.run_id}${caseText}`);
    renderQgisStatus(payload.qgis || {});
  }

  if (event.type === "todo_created") {
    (payload.todos || []).forEach((todo) => runtimeTodos.set(todo.id, todo));
    renderTodos();
  }

  if (event.type === "todo_status_changed") {
    if (payload.todo) runtimeTodos.set(payload.todo.id, payload.todo);
    renderTodos();
  }

  if (event.type === "reasoning_step") {
    appendReasoningStep(payload);
  }

  if (event.type === "artifact_created") {
    addArtifact(payload.artifact);
  }

  if (event.type === "review_completed") {
    renderReviewPanel(payload.review || {});
  }

  if (event.type === "qc_completed") {
    renderQcPanel(payload);
  }

  if (event.type === "run_completed") {
    markAllPipelineDone();
    document.getElementById("btnStart").disabled = false;
    addChatMessage("agent", `分析完成：${payload.summary?.artifact_count || 0} 个 artifacts 已生成。`);
  }

  if (event.type === "run_failed") {
    document.getElementById("btnStart").disabled = false;
    addChatMessage("system", `运行失败：${payload.error || "unknown error"}`);
  }
}

function pipelineStepForAgent(agent) {
  const mapping = {
    planner: "dp-1",
    manager: "dp-1",
    perception_worker: "dp-2",
    cognition_worker: "dp-3",
    reviewer: "dp-4",
    quality_controller: "dp-4",
    analyst: "dp-3",
    cartographer: "dp-5",
    reporter: "dp-6",
  };
  return mapping[agent] || "dp-3";
}

function markPipelineStep(stepId, status) {
  const stepEl = document.querySelector(`.step[data-step="${stepId}"]`);
  if (!stepEl) return;
  if (status === "done") {
    stepEl.className = "step done";
    stepEl.querySelector(".step-status").textContent = "完成";
  } else {
    stepEl.className = "step running";
    stepEl.querySelector(".step-status").textContent = "执行中";
  }
}

function markAllPipelineDone() {
  document.querySelectorAll(".step").forEach((el) => {
    el.className = "step done";
    el.querySelector(".step-status").textContent = "完成";
  });
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
  const modEl = document.getElementById("checkpointModifications");
  modEl.value = "";
  modEl.placeholder = msg.checkpoint_id === "dp-3"
    ? '{"selected_modules":["scale_alignment","stakeholder_equity"],"scale":{"preferred_scale":"street_block","maup_like_risk":"high","notes":"Inspect distribution before reasoning."},"stakeholder_feedback":[{"group":"pedestrians","concern":"crossing feels unsafe at night"}]}'
    : '{"notes":"Optional structured modifications"}';

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
    latestCognitionResult = msg.data;
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

  let modifications = undefined;
  const rawMods = document.getElementById("checkpointModifications").value.trim();
  if (action === "modify" && rawMods) {
    try {
      modifications = JSON.parse(rawMods);
    } catch {
      addChatMessage("system", "⚠️ 修改内容不是有效 JSON，请修正后再提交。");
      return;
    }
  }

  ws.send(JSON.stringify({
    type: "checkpoint_response",
    checkpoint_id: currentCheckpointId,
    action: action,
    modifications: modifications,
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

  if (msg.stage === "correction") {
    renderAlignment(msg.data.alignment_diagnostics || {});
    renderDistribution(msg.data.distribution_preview || {});
    renderAudit(msg.data.audit || []);
    addChatMessage("agent", `🛠️ 已应用 ${msg.data.audit?.length || 0} 条 correction audit 记录。`);
  }
}

function handleComplete(msg) {
  addChatMessage("agent", "分析完成，请查看右侧工作台。 ");
  document.getElementById("btnStart").disabled = false;

  if (msg.geojson) {
    analysisGeoJSON = msg.geojson;
    showResults(msg.summary || {});
  }
}

// ── Runtime workbench rendering ────────────────────────────
function showWorkbenchTab(tabId, button) {
  document.querySelectorAll(".workbench-tab").forEach((el) => el.classList.remove("active"));
  document.querySelectorAll(".tab-button").forEach((el) => el.classList.remove("active"));
  document.getElementById(tabId)?.classList.add("active");
  button?.classList.add("active");
}

function resetRuntimeWorkbench() {
  currentRunId = null;
  runtimeTodos = new Map();
  runtimeArtifacts = new Map();
  setEmpty("todoList", "等待任务规划...");
  setEmpty("reasoningTrace", "等待 agent 推理摘要...");
  setEmpty("artifactList", "等待产物...");
  setEmpty("tablePreview", "等待字段表...");
  document.getElementById("reviewPanel").className = "review-panel empty-state";
  document.getElementById("reviewPanel").textContent = "等待审查结果...";
  document.getElementById("chartFrame").classList.add("hidden");
  document.getElementById("chartImage").classList.add("hidden");
}

function setEmpty(id, text) {
  const el = document.getElementById(id);
  el.className = el.className.split(" ").filter((name) => name !== "empty-state").join(" ") + " empty-state";
  el.textContent = text;
}

function renderTodos() {
  const el = document.getElementById("todoList");
  const todos = Array.from(runtimeTodos.values());
  if (!todos.length) {
    setEmpty("todoList", "等待任务规划...");
    return;
  }
  el.className = "todo-list";
  el.innerHTML = todos.map((todo) => `
    <div class="todo-item ${todo.status}">
      <div class="todo-head">
        <span class="status-dot"></span>
        <strong>${escapeHtml(todo.title)}</strong>
      </div>
      <div class="todo-meta">
        <span>${escapeHtml(formatAgentName(todo.agent))}</span>
        <span>${escapeHtml(todo.status)}</span>
        <span>${(todo.artifacts || []).length} artifacts</span>
      </div>
      <div class="todo-rationale">${escapeHtml(todo.rationale || "")}</div>
    </div>
  `).join("");
}

function appendReasoningStep(step) {
  const el = document.getElementById("reasoningTrace");
  if (el.classList.contains("empty-state")) {
    el.className = "reasoning-trace";
    el.innerHTML = "";
  }
  const div = document.createElement("div");
  div.className = "reasoning-step";
  div.innerHTML = `
    <div class="reasoning-head">
      <strong>${escapeHtml(formatAgentName(step.agent || "agent"))}</strong>
      <span>${escapeHtml(step.step_type || "step")}</span>
      <span>${escapeHtml(String(step.confidence || ""))}</span>
    </div>
    <div>${escapeHtml(step.summary || "")}</div>
    <div class="detail-meta">${escapeHtml(step.method || "")}</div>
  `;
  el.prepend(div);
}

function formatAgentName(agent) {
  const names = {
    planner: "PlannerAgent",
    manager: "ManagerAgent",
    perception_worker: "PerceptionWorker",
    cognition_worker: "CognitionWorker",
    analyst: "AnalystWorker",
    cartographer: "CartographerWorker",
    reviewer: "ReviewHub",
    quality_controller: "QualityController",
    reporter: "ReporterWorker",
  };
  return names[agent] || agent;
}

function addArtifact(artifact) {
  if (!artifact) return;
  runtimeArtifacts.set(artifact.id, artifact);
  renderArtifacts();

  if (artifact.type === "geojson_layer") {
    fetchArtifact(artifact.id).then((geojson) => {
      analysisGeoJSON = geojson;
      proposalLayer.clearLayers();
      drawGeoJSON(geojson);
      fitBounds();
    });
  }

  if (artifact.type === "chart_html") {
    const frame = document.getElementById("chartFrame");
    frame.src = artifactUrl(artifact.id);
    frame.classList.remove("hidden");
  }

  if (artifact.type === "chart_png") {
    const image = document.getElementById("chartImage");
    image.src = artifactUrl(artifact.id);
    image.classList.remove("hidden");
  }

  if (artifact.type === "table") {
    renderTablePreview(artifact.preview || {});
  }

  if (artifact.type === "qgis_live_commands") {
    renderQgisCommandPanel(artifact.preview || {});
  }
}

function renderArtifacts() {
  const el = document.getElementById("artifactList");
  const artifacts = Array.from(runtimeArtifacts.values());
  if (!artifacts.length) {
    setEmpty("artifactList", "等待产物...");
    return;
  }
  el.className = "artifact-list";
  el.innerHTML = artifacts.map((artifact) => `
    <div class="artifact-row">
      <div>
        <strong>${escapeHtml(artifact.title)}</strong>
        <div class="detail-meta">${escapeHtml(artifact.type)} · ${escapeHtml(artifact.mime_type)}</div>
      </div>
      <a href="${artifactDownloadUrl(artifact.id)}" target="_blank" rel="noreferrer">Open</a>
    </div>
  `).join("");
}

function renderTablePreview(preview) {
  const el = document.getElementById("tablePreview");
  const rows = preview.rows || [];
  const columns = preview.columns || Object.keys(rows[0] || {});
  if (!rows.length || !columns.length) return;
  el.className = "table-preview";
  el.innerHTML = `
    <table>
      <thead><tr>${columns.map((col) => `<th>${escapeHtml(col)}</th>`).join("")}</tr></thead>
      <tbody>${rows.map((row) => `<tr>${columns.map((col) => `<td>${escapeHtml(String(row[col] ?? ""))}</td>`).join("")}</tr>`).join("")}</tbody>
    </table>
  `;
}

function renderReviewPanel(review) {
  const el = document.getElementById("reviewPanel");
  const entries = Object.entries(review || {});
  if (!entries.length) return;
  el.className = "review-panel";
  el.innerHTML = entries.map(([key, item]) => `
    <div class="review-row">
      <strong>${escapeHtml(key)}</strong>
      <span>${escapeHtml(item.status || "review")}</span>
      <div class="detail-meta">score ${escapeHtml(String(item.score ?? ""))} · ${escapeHtml(item.note || "")}</div>
    </div>
  `).join("");
}

function renderQcPanel(qc) {
  const el = document.getElementById("reviewPanel");
  el.className = "review-panel";
  el.innerHTML += `
    <div class="review-row qc-row">
      <strong>quality control</strong>
      <span>${qc.passed ? "pass" : "review"}</span>
      <div class="detail-meta">confidence ${escapeHtml(String(qc.confidence || ""))} · ${escapeHtml(qc.recommendation || "")}</div>
    </div>
  `;
}

function artifactUrl(artifactId) {
  return `/api/runs/${encodeURIComponent(currentRunId)}/artifacts/${encodeURIComponent(artifactId)}`;
}

function artifactDownloadUrl(artifactId) {
  return `/api/runs/${encodeURIComponent(currentRunId)}/artifacts/${encodeURIComponent(artifactId)}/download`;
}

async function fetchArtifact(artifactId) {
  const response = await fetch(artifactUrl(artifactId));
  if (!response.ok) throw new Error(`Artifact fetch failed: ${artifactId}`);
  return response.json();
}

async function refreshQgisStatus() {
  try {
    const response = await fetch("/api/qgis/status");
    if (response.ok) renderQgisStatus(await response.json());
  } catch {
    renderQgisStatus({ available: false, message: "QGIS status endpoint unavailable." });
  }
}

function renderQgisStatus(status) {
  const el = document.getElementById("qgisStatus");
  if (!el) return;
  const bridge = status.bridge || status;
  const connected = Boolean(bridge.connected || status.connected);
  el.innerHTML = `
    <div class="qgis-badge ${connected ? "available" : "missing"}">${connected ? "live connected" : "waiting"}</div>
    <div>${escapeHtml(status.message || bridge.message || "No QGIS probe result")}</div>
    <div class="detail-meta">${escapeHtml(bridge.base_url || status.executable || "http://127.0.0.1:8766")}</div>
  `;
}

function renderQgisCommandPanel(preview) {
  const el = document.getElementById("qgisCommandPanel");
  if (!el) return;
  el.innerHTML = `QGIS dispatch: ${preview.sent ? "sent" : "queued"} · queued ${preview.queued || 0}${preview.message ? " · " + escapeHtml(preview.message) : ""}`;
}

async function syncNingboToQgis() {
  const el = document.getElementById("qgisCommandPanel");
  if (el) el.textContent = "Sending Ningbo Old Bund layers to QGIS...";
  try {
    const response = await fetch("/api/qgis/bridge/sync/ningbo-old-bund", { method: "POST" });
    const payload = await response.json();
    renderQgisCommandPanel({ sent: payload.sent, queued: (payload.queued || []).length, message: payload.message || "" });
    await refreshQgisStatus();
  } catch (error) {
    if (el) el.textContent = `QGIS sync failed: ${error.message}`;
  }
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
        .bindPopup(`<b>${n.name || n.label || n.id}</b><br/>类型: ${n.type}${n.degree ? '<br/>度: ' + n.degree : ''}${n.trace?.length ? '<br/>Trace: ' + n.trace.map((t) => t.explanation).join(' | ') : ''}`)
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
        .bindPopup(`${e.type} | ${e.distance_m}m${e.trace?.length ? '<br/>Trace: ' + e.trace.map((t) => t.explanation).join(' | ') : ''}`)
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

  renderAlignment(summary.alignment_diagnostics || {});
  renderDistribution(summary.distribution_preview || {});
  renderAudit(summary.correction_audit || []);
}

function renderAlignment(alignment) {
  const el = document.getElementById("resultAlignment");
  const prompts = (alignment.human_review_prompts || [])
    .map((item) => `<span class="detail-pill">${item}</span>`)
    .join("");
  el.innerHTML = `
    <h4>Alignment Diagnostics</h4>
    <div class="detail-meta">Preferred scale: ${alignment.preferred_scale || "unknown"}</div>
    <div class="detail-meta">Scale span: ${alignment.scale_span_m || 0}</div>
    <div class="detail-meta">MAUP-like risk: ${alignment.maup_like_risk || "unknown"}</div>
    <div class="detail-pill-row">${prompts || '<span class="detail-meta">No prompts</span>'}</div>
  `;
}

function renderDistribution(distribution) {
  const el = document.getElementById("resultDistribution");
  const questions = (distribution.review_questions || [])
    .map((item) => `<li>${item}</li>`)
    .join("");
  el.innerHTML = `
    <h4>Distribution Preview</h4>
    <div class="detail-meta">Dominant layer: ${distribution.dominant_layer || "unknown"}</div>
    <div class="detail-meta">Missing layers: ${(distribution.missing_layers || []).join(", ") || "none"}</div>
    <div class="detail-meta">Counts: ${JSON.stringify(distribution.feature_counts || {})}</div>
    <ul>${questions || '<li>No review questions</li>'}</ul>
  `;
}

function renderAudit(audit) {
  const el = document.getElementById("resultAudit");
  if (!audit.length) {
    el.innerHTML = `<h4>Correction Audit</h4><div class="detail-meta">No corrections recorded.</div>`;
    return;
  }
  el.innerHTML = `
    <h4>Correction Audit</h4>
    ${audit.map((item) => `
      <div class="audit-row">
        <strong>${item.module || "module"}</strong>
        <span>${item.status || "unknown"}</span>
        <div class="detail-meta">${item.notes || ""}</div>
      </div>
    `).join("")}
  `;
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
