const DEFAULT_PATHS = {
  state: "../../submissions/urban_cup_2026/process_evidence/route_tree_state.json",
  summary: "../../experiments/urbanworkflowbench_60tasks_20260524/condition_traces/all60_design_gate_20260524/condition_trace_score_summary.json",
  decisions: "../../experiments/urbanworkflowbench_60tasks_20260524/condition_traces/all60_design_gate_20260524/full/all60_design_gate_decisions.csv",
  findings: "../../submissions/urban_cup_2026/outputs/case_findings.json",
  manifest: "../../submissions/urban_cup_2026/reproducibility_manifest.json",
  modelSummary: "../../submissions/urban_cup_2026/outputs/model_validation_summary.csv",
  temporalSummary: "../../submissions/urban_cup_2026/outputs/temporal_cohort_summary.csv",
  predictions: "../../submissions/urban_cup_2026/outputs/combined_rf_oof_predictions.csv",
  reviews: [
    "../../submissions/urban_cup_2026/process_evidence/step_reviews/S1_review.json",
    "../../submissions/urban_cup_2026/process_evidence/step_reviews/S2_review.json",
    "../../submissions/urban_cup_2026/process_evidence/step_reviews/S3_review.json",
    "../../submissions/urban_cup_2026/process_evidence/step_reviews/S4_review.json",
    "../../submissions/urban_cup_2026/process_evidence/step_reviews/S5_review.json",
    "../../submissions/urban_cup_2026/process_evidence/step_reviews/S6_review.json"
  ]
};

const CASE_ARTIFACTS = {
  results: "../../submissions/urban_cup_2026/outputs/outcome_grounded_case_results.png",
  process: "../../submissions/urban_cup_2026/outputs/human_ai_fit_trap_process.png"
};

const fallbackFindings = {
  analysis_status: "exploratory; sample-conditional; outcome-grounded",
  best_spatial_model_by_scale: [
    { scale: "200m", train_r2: 0.609, r2_mean: 0.282 },
    { scale: "500m", train_r2: 0.731, r2_mean: 0.360 }
  ],
  weekday_weekend: {
    "500m": { weekday_weekend_spatial_spearman_rho: 0.950 },
    "200m": { weekday_weekend_spatial_spearman_rho: 0.894 }
  },
  spatial_oof_residual_moran: {
    "500m": { moran_i: 0.270, permutation_p: 0.001, k: 8 },
    "200m": { moran_i: 0.182, permutation_p: 0.001, k: 8 }
  },
  claim_boundaries: [
    "The LBS sample represents observed device users, not the resident population.",
    "Predictive associations are not causal effects.",
    "The observation window is seven days, so long-term stability is untested.",
    "Spatial-block validation estimates within-city transfer, not cross-city generalization."
  ]
};

const fallback = {
  schema_version: "fallback",
  tree: {
    meta: { task: "Street-vitality route workspace fallback" },
    nodes: [
      n("RO-A", "research_object", "500 m grid with all-week aggregate activity.", [], "completed"),
      n("RO-B", "research_object", "500 m grid with weekday/weekend or day-period activity.", [], "suggested"),
      n("FP-1", "feature_package", "Built-environment, POI, and road indicators.", ["RO-A"], "completed"),
      n("SV-1", "feature_package", "Street-view alignment and coverage readiness.", ["RO-A"], "suggested"),
      n("ME-1A", "model_execution", "Global fitted model for aggregate vitality.", ["FP-1"], "completed"),
      n("ME-2B", "model_execution", "Time-stratified fitted models.", ["RO-B", "FP-1"], "suggested"),
      n("ME-3A", "model_execution", "Spatial heterogeneity model with bandwidth and kernel.", ["ME-1A"], "suggested"),
      n("MX-1", "model_explanation", "SHAP, PDP, importance, and residual diagnostics.", ["ME-1A"], "completed"),
      n("RC-1", "route_comparison", "Compare completed route outputs and report options.", ["ME-1A", "MX-1"], "waiting_choice"),
      n("CS-1", "claim_synthesis", "Calibrate final claims and write the selected report.", ["RC-1"], "pending")
    ],
    edges: [],
    branch_tree: { active: ["RO-A", "FP-1", "ME-1A", "MX-1"], suggested: ["RO-B", "SV-1", "ME-2B", "ME-3A"], deferred: [], blocked: [] },
    active_path: ["RO-A", "FP-1", "ME-1A", "MX-1", "RC-1"]
  },
  workflow: {
    planner_todo: [
      { step_id: "S1", title: "Research object", status: "completed" },
      { step_id: "S2", title: "Variable package", status: "completed" },
      { step_id: "S3", title: "Model route", status: "active" },
      { step_id: "S4", title: "Explanation and diagnostics", status: "pending" },
      { step_id: "S5", title: "Route comparison and report options", status: "waiting_choice" },
      { step_id: "S6", title: "Claim synthesis and calibrated report", status: "pending" }
    ],
    patch_events: [],
    human_choices: [],
    artifact_index: [],
    current_choice_request: null
  },
  validation: { issues: [] }
};

const state = {
  data: fallback,
  selectedNodeId: null,
  tasks: [],
  findings: fallbackFindings,
  analytics: { modelSummary: [], temporalSummary: [], predictions: [] },
  reviews: [],
  manifest: null,
  localMessages: [],
  controlActions: {},
  refreshTimer: null,
  treeZoom: 0.78,
  panning: null,
  didInitialFit: false
};

const ROUTE_STAGES = [
  { step: 1, label: "research object" },
  { step: 2, label: "variable package" },
  { step: 3, label: "model route" },
  { step: 4, label: "explanation review" },
  { step: 5, label: "route comparison" },
  { step: 6, label: "claim synthesis" }
];

const MIN_TREE_ZOOM = 0.42;
const MAX_TREE_ZOOM = 1.85;

function n(node_id, node_type, question, depends_on, status) {
  return {
    node_id,
    node_type,
    question,
    depends_on,
    status,
    required_inputs: [],
    expected_outputs: [],
    required_parameters: {},
    time_space_people: {
      time: "Time meaning is recorded by planner review.",
      space: "Spatial unit and boundary assumptions are recorded by planner review.",
      people: "People or activity interpretation is recorded as a claim boundary."
    },
    claim_boundary: "Claims must match available evidence."
  };
}

async function loadText(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`${response.status} ${path}`);
  return response.text();
}

async function loadJson(path) {
  return JSON.parse(await loadText(path));
}

function resolveStatePath(path) {
  if (/^(https?:)?\/\//.test(path) || path.startsWith("/") || path.startsWith("../")) return path;
  if (path.startsWith("experiments/") || path.startsWith("frontend/") || path.startsWith("paper_draft/")) return `../../${path}`;
  return path;
}

async function loadData() {
  const params = new URLSearchParams(window.location.search);
  const stateParam = params.get("state");
  const statePath = resolveStatePath(stateParam || DEFAULT_PATHS.state);
  try {
    const [routeState, summary, decisionsText, findings, manifest, reviews, modelSummaryText, temporalSummaryText, predictionsText] = await Promise.all([
      loadJson(statePath),
      loadJson(DEFAULT_PATHS.summary).catch(() => null),
      loadText(DEFAULT_PATHS.decisions).catch(() => ""),
      loadJson(DEFAULT_PATHS.findings).catch(() => fallbackFindings),
      loadJson(DEFAULT_PATHS.manifest).catch(() => null),
      Promise.all(DEFAULT_PATHS.reviews.map(path => loadJson(path).catch(() => null))),
      loadText(DEFAULT_PATHS.modelSummary).catch(() => ""),
      loadText(DEFAULT_PATHS.temporalSummary).catch(() => ""),
      loadText(DEFAULT_PATHS.predictions).catch(() => "")
    ]);
    return {
      routeState,
      summary,
      tasks: decisionsText ? parseCsv(decisionsText) : [],
      findings,
      manifest,
      reviews: reviews.filter(Boolean),
      analytics: {
        modelSummary: modelSummaryText ? parseCsv(modelSummaryText) : [],
        temporalSummary: temporalSummaryText ? parseCsv(temporalSummaryText) : [],
        predictions: predictionsText ? parseCsv(predictionsText) : []
      },
      mode: stateParam ? `live route state: ${stateParam}` : "default live route state"
    };
  } catch (error) {
    return {
      routeState: fallback,
      summary: fallback.summary || null,
      tasks: fallback.tasks || [],
      findings: fallbackFindings,
      manifest: null,
      reviews: [],
      analytics: { modelSummary: [], temporalSummary: [], predictions: [] },
      mode: `embedded fallback: ${error.message}`
    };
  }
}

function normalizeRouteState(routeState) {
  if (routeState.tree) return routeState;
  return {
    schema_version: routeState.schema_version,
    generated_at: routeState.updated_at || routeState.generated_at,
    frontend_url: routeState.frontend_url,
    tree: {
      meta: routeState.meta || {},
      nodes: routeState.nodes || [],
      edges: routeState.edges || [],
      branch_tree: routeState.branch_tree || {},
      active_path: routeState.active_path || []
    },
    workflow: {
      planner_todo: routeState.planner_todo || [],
      patch_events: routeState.patch_events || [],
      human_choices: routeState.human_choices || [],
      current_choice_request: routeState.current_choice_request || null,
      artifact_index: routeState.artifact_index || collectNodeArtifacts(routeState.nodes || []),
      claim_options: routeState.claim_options || [],
      dialogue: routeState.dialogue || routeState.transcript || [],
      cli_trace: routeState.cli_trace || routeState.terminal_lines || []
    },
    validation: routeState.validation || { issues: [] }
  };
}

function nodeId(node) {
  return node.node_id || node.id || "";
}

function nodeQuestion(node) {
  return node.question || node.label || node.title || node.name || nodeId(node);
}

function nodeType(node) {
  return node.node_type || node.type || "route_node";
}

function nodeDeps(node) {
  return node.depends_on || node.dependencies || node.parent_nodes || [];
}

function nodeStatus(node) {
  return node.status || "candidate";
}

function nodeArtifacts(node, data) {
  const own = Array.isArray(node.artifacts) ? node.artifacts : [];
  const index = data.workflow?.artifact_index || [];
  const id = nodeId(node);
  return dedupeArtifacts([
    ...own,
    ...index.filter(item => item.node_id === id || item.branch_id === id)
  ]);
}

function collectNodeArtifacts(nodes = []) {
  return nodes.flatMap(node => (node.artifacts || []).map(artifact => ({
    ...artifact,
    node_id: artifact.node_id || nodeId(node)
  })));
}

function workflowArtifacts(data) {
  const index = data.workflow?.artifact_index || [];
  if (index.length) return dedupeArtifacts(index);
  return dedupeArtifacts(collectNodeArtifacts(data.tree?.nodes || []));
}

function dedupeArtifacts(artifacts = []) {
  const seen = new Set();
  return artifacts.filter(artifact => {
    const key = [
      artifact.node_id || artifact.branch_id || "",
      artifact.path || artifact.href || "",
      artifact.title || artifact.artifact_id || ""
    ].join("::");
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function asArray(value) {
  if (Array.isArray(value)) return value;
  if (!value) return [];
  return [value];
}

function nodeMeaning(node) {
  const tsp = node.time_space_people || {};
  return {
    time: tsp.time || node.time,
    space: tsp.space || node.space,
    people: tsp.people || node.people
  };
}

function branchState(node, tree) {
  const id = nodeId(node);
  const branch = tree.branch_tree || {};
  if ((branch.merged || []).includes(id) || ["merged", "merge"].includes(nodeStatus(node))) return "merge";
  if ((branch.blocked || []).includes(id) || nodeStatus(node) === "blocked") return "blocked";
  if ((branch.deferred || []).includes(id) || nodeStatus(node) === "deferred") return "deferred";
  if ((branch.active || []).includes(id) || (branch.main || []).includes(id) || (tree.main_path || tree.active_path || []).includes(id)) return "selected";
  if ((branch.completed_branch || []).includes(id) || node.route_role === "completed_branch") return "suggested";
  if (["selected", "approved", "active"].includes(nodeStatus(node))) return "selected";
  return "suggested";
}

function stepOf(node) {
  const step = node.step_id || "";
  const type = nodeType(node);
  if (type === "claim_synthesis" || /S6/i.test(step)) return 6;
  if (["route_comparison", "report_option"].includes(type) || /S5/i.test(step)) return 5;
  if (/S1/i.test(step) || type === "research_object") return 1;
  if (/S2/i.test(step) || ["feature_package", "data_preparation"].includes(type)) return 2;
  if (/S3/i.test(step) || type === "model_execution") return 3;
  if (/S4/i.test(step) || ["model_explanation", "diagnostic"].includes(type)) return 4;
  return 6;
}

function visualStepMap(tree) {
  const nodes = new Map(tree.nodes.map(node => [nodeId(node), node]));
  const steps = new Map(tree.nodes.map(node => [nodeId(node), stepOf(node)]));
  let changed = true;
  for (let pass = 0; pass < 8 && changed; pass++) {
    changed = false;
    for (const node of tree.nodes) {
      const id = nodeId(node);
      let nextStep = steps.get(id) || stepOf(node);
      for (const dep of nodeDeps(node)) {
        if (!nodes.has(dep)) continue;
        const depStep = steps.get(dep) || stepOf(nodes.get(dep));
        if (depStep >= nextStep && nodeType(node) !== "claim_synthesis") {
          nextStep = Math.min(ROUTE_STAGES.length, depStep + 1);
        }
      }
      if (nextStep !== steps.get(id)) {
        steps.set(id, nextStep);
        changed = true;
      }
    }
  }
  return steps;
}

function buildLayout(tree) {
  const stage = document.querySelector(".tree-stage");
  const visualSteps = visualStepMap(tree);
  const stageWidth = stage?.clientWidth || window.innerWidth || 1200;
  const maxColumnSize = Math.max(
    1,
    ...ROUTE_STAGES.map(stageItem => tree.nodes.filter(node => (visualSteps.get(nodeId(node)) || stepOf(node)) === stageItem.step).length)
  );
  const width = Math.max(1180, Math.round(stageWidth / Math.max(state.treeZoom, 0.78)), ROUTE_STAGES.length * 196);
  const height = Math.max(430, 150 + maxColumnSize * 100);
  const margin = { left: 64, right: 220, top: 72, bottom: 44 };
  const stepX = step => margin.left + (step - 1) * ((width - margin.left - margin.right) / (ROUTE_STAGES.length - 1));
  const columns = new Map();
  tree.nodes.forEach(node => {
    const step = visualSteps.get(nodeId(node)) || stepOf(node);
    if (!columns.has(step)) columns.set(step, []);
    columns.get(step).push(node);
  });
  const yMap = new Map();
  for (const [step, nodes] of columns.entries()) {
    nodes.sort((a, b) => orderWeight(a, tree) - orderWeight(b, tree) || nodeId(a).localeCompare(nodeId(b)));
    const usable = height - margin.top - margin.bottom;
    const gap = usable / Math.max(nodes.length, 1);
    nodes.forEach((node, idx) => {
      yMap.set(nodeId(node), margin.top + gap * idx + gap / 2);
    });
  }
  const positions = new Map();
  tree.nodes.forEach(node => positions.set(nodeId(node), { x: stepX(visualSteps.get(nodeId(node)) || stepOf(node)), y: yMap.get(nodeId(node)), node }));
  return { width, height, margin, positions };
}

function orderWeight(node, tree) {
  const stateName = branchState(node, tree);
  const weights = { selected: 0, merge: 1, suggested: 2, deferred: 3, blocked: 4 };
  return weights[stateName] ?? 2;
}

function renderTree() {
  const data = state.data;
  const tree = data.tree;
  const svg = document.getElementById("routeSvg");
  const layout = buildLayout(tree);
  svg.setAttribute("viewBox", `0 0 ${layout.width} ${layout.height}`);
  svg.style.width = `${Math.round(layout.width * state.treeZoom)}px`;
  svg.style.height = `${Math.round(layout.height * state.treeZoom)}px`;
  svg.innerHTML = "";
  const zoomValue = document.getElementById("zoomValue");
  if (zoomValue) zoomValue.textContent = `${Math.round(state.treeZoom * 100)}%`;

  const defs = el("defs");
  defs.appendChild(marker("arrow", "#111"));
  svg.appendChild(defs);

  ROUTE_STAGES.forEach(stageItem => {
    const step = stageItem.step;
    const x = layout.positions.size
      ? layout.margin.left + (step - 1) * ((layout.width - layout.margin.left - layout.margin.right) / (ROUTE_STAGES.length - 1))
      : 0;
    if (!x) return;
    const label = stageItem.label;
    const line = el("line", { x1: x, x2: x, y1: 38, y2: layout.height - 28, class: "step-guide" });
    const text = el("text", { x, y: 28, class: "step-label", "text-anchor": "middle" });
    text.textContent = `Step ${step}: ${label}`;
    svg.appendChild(line);
    svg.appendChild(text);
  });

  const edgeSet = new Set();
  visualTreeEdges(tree, layout).forEach(edge => drawEdge(edge.source, edge.target, edge.relation || "route_step", edgeSet));

  function drawEdge(sourceId, targetId, relation, edgeSetRef) {
    if (!sourceId || !targetId) return;
    const key = `${sourceId}->${targetId}`;
    if (edgeSetRef.has(key)) return;
    edgeSetRef.add(key);
    const source = layout.positions.get(sourceId);
    const target = layout.positions.get(targetId);
    if (!source || !target) return;
    const dx = Math.max(42, Math.abs(target.x - source.x) * 0.48);
    const path = `M ${source.x + 12} ${source.y} C ${source.x + dx} ${source.y}, ${target.x - dx} ${target.y}, ${target.x - 12} ${target.y}`;
    const sourceState = branchState(source.node, tree);
    const targetState = branchState(target.node, tree);
    const relationClass = String(relation || "dependency").replace(/[^a-z0-9_-]/gi, "_");
    const cls = ["edge", sourceState, targetState, relationClass, relation === "future" ? "future" : ""].join(" ");
    svg.appendChild(el("path", { d: path, class: cls, "marker-end": "url(#arrow)" }));
  }

  for (const { x, y, node } of layout.positions.values()) {
    const id = nodeId(node);
    const g = el("g", { class: `route-node ${branchState(node, tree)} ${state.selectedNodeId === id ? "is-focused" : ""}`, tabindex: "0", role: "button" });
    g.dataset.nodeId = id;
    g.addEventListener("keydown", event => {
      if (event.key === "Enter" || event.key === " ") selectNode(id);
    });
    const circle = el("circle", { cx: x, cy: y, r: 14 });
    const textX = x + 22;
    const textAnchor = "start";
    const label = el("text", { x: textX, y: y - 5, class: "node-label", "text-anchor": textAnchor });
    label.textContent = id;
    const title = el("text", { x: textX, y: y + 13, class: "node-caption", "text-anchor": textAnchor });
    title.textContent = shorten(nodeQuestion(node), 30);
    g.appendChild(circle);
    if (branchState(node, tree) === "blocked") {
      g.appendChild(el("line", { x1: x - 7, y1: y - 7, x2: x + 7, y2: y + 7 }));
      g.appendChild(el("line", { x1: x + 7, y1: y - 7, x2: x - 7, y2: y + 7 }));
    }
    if (branchState(node, tree) === "merge") {
      g.appendChild(el("circle", { cx: x, cy: y, r: 20, class: "outer-ring" }));
    }
    g.appendChild(label);
    g.appendChild(title);
    svg.appendChild(g);
  }
}

function visualTreeEdges(tree, layout) {
  const explicit = Array.isArray(tree.visual_edges) ? tree.visual_edges : null;
  const raw = explicit || tree.edges || [];
  const positions = layout.positions;
  const mainPath = tree.main_path || tree.active_path || [];
  const mainPairs = new Set(mainPath.slice(0, -1).map((id, index) => `${id}->${mainPath[index + 1]}`));

  const normalized = raw
    .map(edge => ({
      ...edge,
      source: edge.source || edge.from,
      target: edge.target || edge.to
    }))
    .filter(edge => edge.source && edge.target && positions.has(edge.source) && positions.has(edge.target));

  if (explicit) return normalized;

  const adjacent = normalized.filter(edge => {
    const source = positions.get(edge.source);
    const target = positions.get(edge.target);
    if (!source || !target) return false;
    const sourceStep = stepOf(source.node);
    const targetStep = stepOf(target.node);
    const stepDelta = targetStep - sourceStep;
    const key = `${edge.source}->${edge.target}`;

    // The main route should stay visibly continuous, even where a step contains
    // two approved nodes of the same type. Cross-stage methodological
    // dependencies remain available in the node detail panel rather than being
    // drawn as route-lineage edges.
    if (mainPairs.has(key)) return true;
    if (stepDelta !== 1) return false;
    if (/comparison|claim|diagnostic|explanation/i.test(edge.operation || edge.relation || "")) return true;

    return true;
  });

  // If a state has no usable visual edges, fall back to the selected route
  // lineage rather than drawing every depends_on relationship as a tree edge.
  if (adjacent.length) return adjacent;
  return mainPath.slice(0, -1).map((id, index) => ({
    source: id,
    target: mainPath[index + 1],
    relation: "main_path",
    operation: "selected route lineage"
  }));
}

function marker(id, color) {
  const markerEl = el("marker", { id, viewBox: "0 0 10 10", refX: "9", refY: "5", markerWidth: "5", markerHeight: "5", orient: "auto-start-reverse" });
  markerEl.appendChild(el("path", { d: "M 0 0 L 10 5 L 0 10 z", fill: color }));
  return markerEl;
}

function selectNode(id) {
  state.selectedNodeId = id;
  renderTree();
  renderNodeDetail();
  renderRouteRail();
  activateWorkbenchTab("artifacts");
}

function renderNodeDetail() {
  const data = state.data;
  const node = data.tree.nodes.find(item => nodeId(item) === state.selectedNodeId) || data.tree.nodes[0];
  if (!node) return;
  state.selectedNodeId = nodeId(node);
  document.getElementById("nodeTitle").textContent = `${nodeId(node)} / ${nodeType(node)}`;
  document.getElementById("nodeStatus").textContent = `${branchState(node, data.tree)} / ${nodeStatus(node)}`;
  const tsp = nodeMeaning(node);
  const params = node.required_parameters || {};
  const artifacts = nodeArtifacts(node, data);
  const edges = nodeEdgeOperations(node, data);
  document.getElementById("nodeDetail").innerHTML = `
    <section class="detail-section">
      <h3>Research meaning</h3>
      <p>${escapeHtml(nodeQuestion(node))}</p>
      <p><strong>Claim boundary:</strong> ${escapeHtml(node.claim_boundary || "not recorded")}</p>
    </section>
    <section class="detail-section artifact-section">
      <h3>Node artifacts</h3>
      ${artifactGallery(artifacts)}
    </section>
    <section class="detail-section">
      <h3>Required inputs</h3>
      ${listPills(node.required_inputs, "input")}
      <h3>Expected outputs</h3>
      ${listPills(node.expected_outputs, "output")}
    </section>
    <section class="detail-section three-grid">
      ${meaningCard("Time", tsp.time)}
      ${meaningCard("Space", tsp.space)}
      ${meaningCard("People", tsp.people)}
    </section>
    <section class="detail-section">
      <h3>Method parameters and dependencies</h3>
      ${paramTable(params)}
      <p class="small">Depends on: ${escapeHtml(nodeDeps(node).join(", ") || "root")}</p>
    </section>
    <section class="detail-section">
      <h3>Edge operations</h3>
      ${edgeOperationList(edges, nodeId(node))}
    </section>
  `;
}

function meaningCard(title, text) {
  return `<article class="meaning-card"><strong>${escapeHtml(title)}</strong><p>${escapeHtml(text || "not recorded")}</p></article>`;
}

function listPills(values = [], label) {
  if (!values.length) return `<p class="small">No ${label} list recorded.</p>`;
  return `<div class="pill-row">${values.map(v => `<span class="pill">${escapeHtml(v)}</span>`).join("")}</div>`;
}

function paramTable(params) {
  const entries = Object.entries(params || {});
  if (!entries.length) return "<p class=\"small\">No method parameters recorded.</p>";
  return `<table class="mini-table"><tbody>${entries.map(([key, value]) => `
    <tr><th>${escapeHtml(key)}</th><td>${escapeHtml(Array.isArray(value) ? value.join(", ") : value)}</td></tr>
  `).join("")}</tbody></table>`;
}

function nodeEdgeOperations(node, data) {
  const id = nodeId(node);
  return (data.tree.edges || [])
    .filter(edge => edge.source === id || edge.target === id)
    .map(edge => ({
      ...edge,
      direction: edge.source === id ? "outgoing" : "incoming"
    }));
}

function edgeOperationList(edges, currentId) {
  if (!edges.length) return "<p class=\"small\">No edge operation recorded yet.</p>";
  return `<div class="edge-operation-list">${edges.map(edge => {
    const other = edge.direction === "outgoing" ? edge.target : edge.source;
    return `<article class="edge-operation-card">
      <header><strong>${escapeHtml(edge.direction === "outgoing" ? `${currentId} -> ${other}` : `${other} -> ${currentId}`)}</strong><span>${escapeHtml(edge.relation || "dependency")}</span></header>
      <p><strong>Operation:</strong> ${escapeHtml(edge.operation || edge.edge_explanation || "not recorded")}</p>
      <p><strong>Dependency:</strong> ${escapeHtml(edge.dependency_reason || "not recorded")}</p>
      <p><strong>Claim boundary:</strong> ${escapeHtml(edge.claim_boundary_effect || "not recorded")}</p>
    </article>`;
  }).join("")}</div>`;
}

function artifactGallery(artifacts) {
  if (!artifacts.length) return "<p class=\"small\">No artifact attached yet.</p>";
  const groups = [
    ["Visual outputs", artifacts.filter(artifact => artifactKind(artifact) === "visual")],
    ["Tables and manifests", artifacts.filter(artifact => artifactKind(artifact) === "data")],
    ["Trace and review records", artifacts.filter(artifact => artifactKind(artifact) === "trace")],
    ["Other files", artifacts.filter(artifact => artifactKind(artifact) === "other")]
  ].filter(([, items]) => items.length);

  return `<div class="artifact-stack">${groups.map(([title, items]) => {
    const sorted = [...items].sort((a, b) => imageRank(b) - imageRank(a) || artifactTitle(a).localeCompare(artifactTitle(b)));
    return `<section class="artifact-group">
      <h4>${escapeHtml(title)} <span>${sorted.length}</span></h4>
      <div class="artifact-gallery">${sorted.map((artifact, index) => artifactCard(artifact, index)).join("")}</div>
    </section>`;
  }).join("")}</div>`;
}

function artifactCard(artifact, index) {
  const path = artifact.path || artifact.href || "";
  const url = pathToUrl(path);
  const title = artifactTitle(artifact);
  const type = artifact.artifact_type || artifact.type || artifact.role || fileExt(path) || "file";
  const status = artifact.review_status || artifact.status || "";
  const image = /\.(png|jpg|jpeg|gif|svg)$/i.test(path) ? `<img src="${escapeAttr(url)}" alt="${escapeAttr(title)}">` : "";
  return `<article class="artifact-card ${index === 0 && image ? "primary-artifact" : ""}">
    ${image}
    <div class="artifact-meta">
      <strong>${escapeHtml(title)}</strong>
      <span>${escapeHtml([type, status].filter(Boolean).join(" / "))}</span>
    </div>
    ${url ? `<a href="${escapeAttr(url)}" target="_blank" rel="noreferrer">open artifact</a>` : ""}
  </article>`;
}

function artifactTitle(artifact) {
  const path = artifact.path || artifact.href || "";
  return artifact.title || artifact.artifact_id || fileName(path) || "artifact";
}

function artifactKind(artifact) {
  const path = artifact.path || artifact.href || "";
  const ext = fileExt(path).toLowerCase();
  const text = `${artifact.artifact_type || ""} ${artifact.type || ""} ${artifact.role || ""} ${artifact.title || ""} ${path}`.toLowerCase();
  if (/^(png|jpg|jpeg|gif|svg)$/.test(ext)) return "visual";
  if (/^(csv|json|geojson|parquet)$/.test(ext)) return "data";
  if (/(map|plot|figure|heatmap|pdp|shap)/.test(text)) return "visual";
  if (/(table|manifest|matrix|stats|data)/.test(text)) return "data";
  if (/(log|md|txt|trace|review|claim|report|event)/.test(`${ext} ${text}`)) return "trace";
  return "other";
}

function imageRank(artifact) {
  const path = artifact.path || artifact.href || "";
  if (!/\.(png|jpg|jpeg|gif|svg)$/i.test(path)) return 0;
  const type = `${artifact.artifact_type || ""} ${artifact.type || ""} ${artifact.title || ""}`.toLowerCase();
  if (/map|coverage|spatial|gis/.test(type)) return 4;
  if (/profile|temporal|heatmap|histogram|pdp|shap|figure/.test(type)) return 3;
  return 2;
}

function pathToUrl(path) {
  if (!path) return "";
  if (/^(https?:)?\/\//.test(path)) return path;
  let cleaned = path.replace(/\\/g, "/");
  const markerText = "paper4_urban_svgagent/";
  const idx = cleaned.indexOf(markerText);
  if (idx >= 0) cleaned = cleaned.slice(idx + markerText.length);
  if (cleaned.startsWith("experiments/") || cleaned.startsWith("figures/") || cleaned.startsWith("paper_draft/")) return `../../${cleaned}`;
  if (cleaned.startsWith("../") || cleaned.startsWith("./")) return cleaned;
  return cleaned;
}

function renderLegacyTerminalMirror() {
  const data = state.data;
  const terminal = document.getElementById("cliTerminal");
  terminal.innerHTML = `<pre class="terminal-raw">${escapeHtml(terminalText(data))}</pre>`;
  terminal.scrollTop = terminal.scrollHeight;
}

function terminalText(data) {
  const workflow = data.workflow || {};
  const explicit = workflow.cli_trace || workflow.terminal_lines || workflow.dialogue || workflow.transcript;
  if (Array.isArray(explicit) && explicit.length) {
    return explicit.map(terminalLineText).join("\n");
  }
  return terminalLines(data).map(terminalLineText).join("\n");
}

function terminalLineText(line) {
  if (typeof line === "string") return line;
  const raw = line.raw || line.line || line.ansi || "";
  if (raw) return raw;
  const role = line.role || line.actor || "cli";
  const text = line.text || line.content || line.message || "";
  return `${String(role).padEnd(10, " ")} ${text}`;
}

function terminalLines(data) {
  const workflow = data.workflow || {};
  const explicit = workflow.cli_trace || workflow.terminal_lines || workflow.dialogue || workflow.transcript;
  if (Array.isArray(explicit) && explicit.length) {
    return explicit.map(item => typeof item === "string"
      ? { role: "cli", text: item, kind: "system" }
      : { role: item.role || item.actor || "cli", text: item.text || item.content || item.message || JSON.stringify(item), kind: item.kind || item.role || "system" }
    );
  }
  const lines = [];
  const task = data.tree.meta?.task || "Assess an urban-analysis question.";
  const toolsets = "urban, todo, memory, delegation";
  const session = data.tree.meta?.state_id || data.tree.meta?.session_id || "active";
  lines.push(" _   _ ____  ____    _    _   _        _    ____ _____ _   _ _____ ____");
  lines.push("| | | |  _ \\| __ )  / \\  | \\ | |      / \\  / ___| ____| \\ | |_   _/ ___|");
  lines.push("| |_| | |_) |  _ \\ / _ \\ |  \\| |     / _ \\| |  _|  _| |  \\| | | | \\___ \\");
  lines.push("|  _  |  __/| |_) / ___ \\| |\\  |    / ___ \\ |_| | |___| |\\  | | |  ___) |");
  lines.push("|_| |_|_|   |____/_/   \\_\\_| \\_|   /_/   \\_\\____|_____|_| \\_| |_| |____/");
  lines.push("");
  lines.push(`Urban Agents runtime | toolsets: ${toolsets}`);
  lines.push(`Session: ${session}`);
  lines.push("Welcome to Urban Agents / Urban-Hermes. Type your message or /help for commands.");
  lines.push("");
  lines.push("────────────────────────────────────────────────");
  lines.push(`● ${task}`);
  lines.push("╭─ Hermes ──────────────────────────────────────╮");
  lines.push(`  route state loaded: ${data.tree.nodes.length} nodes, ${(data.tree.edges || []).length} links`);
  lines.push("╰────────────────────────────────────────────────╯");
  for (const item of displayPlannerTodo(asArray(workflow.planner_todo), data.tree)) {
    lines.push(`  ┊ todo   ${item.step_id || ""}  ${item.title || item.step || ""}  [${item.status || "pending"}]`);
  }
  const choice = workflow.current_choice_request;
  if (choice) {
    lines.push(`  ┊ choice ${choice.message || choice.question || "Human choice requested before next step."}`);
    for (const option of asArray(choice.choices)) {
      lines.push(`  ┊ option ${option.label || option.node_id || option.branch_id || "recorded option"}`);
    }
  } else {
    lines.push("  ┊ choice No active human choice request.");
  }
  for (const choiceItem of asArray(workflow.human_choices)) {
    lines.push(`  ┊ human  ${choiceItem.node_id || choiceItem.branch_id || choiceItem.choice_id || "choice"} -> ${choiceItem.decision || choiceItem.choice || "recorded"}${choiceItem.reason ? ` | ${choiceItem.reason}` : ""}`);
  }
  for (const artifact of workflowArtifacts(data).slice(0, 9)) {
    lines.push(`  ┊ artifact ${artifact.node_id || artifact.branch_id || "node"} <= ${artifact.title || fileName(artifact.path || "")} (${artifact.artifact_type || artifact.type || artifact.role || "artifact"})`);
  }
  for (const event of asArray(workflow.patch_events)) {
    lines.push(`  ┊ patch  ${event.patch_type || "patch"}${event.details ? ` | ${event.details}` : ""}${event.reason ? ` | ${event.reason}` : ""}`);
  }
  const validation = data.validation || {};
  if (validation.issues?.length) {
    lines.push(`  ┊ review ${validation.issues.length} validation issue(s): ${validation.issues.join("; ")}`);
  } else {
    lines.push("  ┊ review route state validation: no recorded issues");
  }
  return lines;
}

function displayPlannerTodo(todo, tree) {
  const items = (todo || []).map(item => ({ ...item }));
  const hasClaimNode = (tree.nodes || []).some(node => nodeType(node) === "claim_synthesis");
  const hasS6 = items.some(item => /S6/i.test(item.step_id || ""));
  const legacyIndex = items.findIndex(item =>
    /S5_route_comparison_claim/i.test(item.step_id || "") ||
    /route comparison.*claim/i.test(item.title || "")
  );
  if (hasClaimNode && !hasS6 && legacyIndex >= 0) {
    const legacy = items[legacyIndex];
    items.splice(
      legacyIndex,
      1,
      {
        ...legacy,
        step_id: "S5_route_comparison",
        title: "Route comparison and report-option selection",
        status: legacy.status || "completed"
      },
      {
        ...legacy,
        step_id: "S6_claim_synthesis",
        title: "Claim synthesis and calibrated report",
        status: legacy.status || "completed"
      }
    );
  }
  return items;
}

function reviewFor(stepPrefix) {
  return state.reviews.find(review => String(review.step_id || "").startsWith(stepPrefix)) || {};
}

function scaleFinding(scale) {
  return (state.findings?.best_spatial_model_by_scale || []).find(item => item.scale === scale) || {};
}

function metric(value, digits = 3) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(digits) : "n/a";
}

function researchThread(data) {
  const workflow = data.workflow || {};
  const f500 = scaleFinding("500m");
  const f200 = scaleFinding("200m");
  const s1 = reviewFor("S1");
  const s3 = reviewFor("S3");
  const s4 = reviewFor("S4");
  const s6 = reviewFor("S6");
  const approved = asArray(workflow.human_choices).filter(choice => choice.decision === "approve");
  const activeCount = (data.tree.active_path || data.tree.branch_tree?.active || []).length;
  const candidateCount = data.tree.nodes.length;

  return [
    {
      role: "human",
      stage: "Research brief",
      body: data.tree.meta?.task || "Assess scale-dependent street vitality with reviewable urban evidence.",
      points: ["Compare 500 m and 200 m analytical units", "Separate apparent fit from spatial transfer", "Keep claims auditable and sample-conditional"]
    },
    {
      role: "planner",
      stage: "S1–S3 / route construction",
      body: `I represented the study as a typed route graph with ${candidateCount} candidate nodes and ${activeCount} nodes on the selected path.`,
      points: ["Two research objects: 500 m and 200 m grids", "Two feature packages: built form and activity opportunity", "Matched model and validation branches"]
    },
    {
      role: "human",
      stage: "Human choice",
      body: approved.length
        ? `Approved ${approved.map(choice => choice.node_id || choice.branch_id).filter(Boolean).join(", ")} and retained alternative scales for comparison.`
        : "Approved the two-scale comparison and the matched feature packages.",
      points: ["Alternatives remain visible rather than being overwritten"]
    },
    {
      role: "worker",
      stage: "S2–S3 / execution",
      body: "Executed 11 of 12 matched OLS, random-forest, and GWR routes. The failed 200 m GWR route remains visible; GWRF stays deferred until its own method gate is satisfied.",
      points: ["Every output is bound to a route node", "Validation results are stored separately from training fit", shorten(s3.claim_impact || "Model-specific limitations are carried forward to claim review.", 180)]
    },
    {
      role: "reviewer",
      failure: "passive",
      stage: "Data-regime checkpoint",
      body: s1.reviewer_correction || "The observed device-user sample is not a resident-population estimate.",
      points: [s1.people_implications || "Coverage is inherited from the LBS data regime.", s1.time_implications || "The observation window is short."]
    },
    {
      role: "worker",
      stage: "Outcome-grounded validation",
      body: `The strongest spatial-block result is R² ${metric(f500.r2_mean)} at 500 m versus ${metric(f200.r2_mean)} at 200 m. Training fit alone would report ${metric(f500.train_r2)} at 500 m.`,
      points: ["Five repeated five-fold validation", "Contiguous spatial-block holdouts", "Scale-specific results retained"],
      attachments: [
        { title: "Outcome-grounded results", type: "figure", href: CASE_ARTIFACTS.results },
        { title: "Human–AI process", type: "process trace", href: CASE_ARTIFACTS.process }
      ]
    },
    {
      role: "reviewer",
      failure: "active",
      stage: "Parameter & validation checkpoint",
      body: s3.reviewer_correction || "Model and validation choices materially change the apparent strength of the result.",
      points: [`500 m RF: train R² ${metric(f500.train_r2)} → spatial R² ${metric(f500.r2_mean)}`, `200 m RF: train R² ${metric(f200.train_r2)} → spatial R² ${metric(f200.r2_mean)}`, "Do not select a route from training fit alone"]
    },
    {
      role: "reviewer",
      failure: "active",
      stage: "Spatial diagnostic checkpoint",
      body: s4.reviewer_correction || "Residual spatial autocorrelation remains and constrains inference.",
      points: [s4.space_implications || "Spatial residual structure remains significant.", s4.claim_impact || "Local and causal claims must be downgraded."]
    },
    {
      role: "planner",
      stage: "S6 / claim gate",
      body: s6.reviewer_correction || "Claims are admitted only at the strength supported by the reviewed evidence.",
      points: ["Allow: descriptive, sample-conditional association", "Qualify: predictive transfer and local interpretation", "Block: causal, census-representative, and cross-city claims"]
    }
  ];
}

function renderThreadMessage(message, index) {
  const avatars = { human: "H", planner: "P", worker: "W", reviewer: "R" };
  const labels = { human: "Human", planner: "Planner", worker: "Worker", reviewer: "Reviewer" };
  const role = message.role || "planner";
  const failure = message.failure || "";
  const attachments = asArray(message.attachments);
  const points = asArray(message.points).filter(Boolean);
  return `<article class="thread-turn" data-role="${escapeAttr(role)}" data-failure="${escapeAttr(failure)}" data-local="${message.local ? "true" : "false"}">
    <div class="thread-avatar" aria-hidden="true">${escapeHtml(avatars[role] || "A")}</div>
    <div class="thread-card">
      <div class="thread-meta">
        <div><strong>${escapeHtml(labels[role] || role)}</strong>${failure ? ` <span class="thread-tag ${escapeAttr(failure)}">${escapeHtml(failure)} failure</span>` : ""}</div>
        <time>${escapeHtml(message.stage || `turn ${index + 1}`)}</time>
      </div>
      <p>${escapeHtml(message.body || "")}</p>
      ${points.length ? `<ul class="thread-points">${points.map(point => `<li>${escapeHtml(point)}</li>`).join("")}</ul>` : ""}
      ${attachments.length ? `<div class="thread-attachments">${attachments.map(item => `<a class="thread-attachment" href="${escapeAttr(item.href)}" target="_blank" rel="noreferrer"><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.type || "artifact")}</span></a>`).join("")}</div>` : ""}
    </div>
  </article>`;
}

function renderTodoAndDialogue() {
  const data = state.data;
  const messages = [...researchThread(data), ...state.localMessages];
  const timeline = document.getElementById("dialogueTimeline");
  timeline.innerHTML = messages.map(renderThreadMessage).join("");
  if (state.localMessages.length) timeline.scrollTop = timeline.scrollHeight;

  const terminal = document.getElementById("cliTerminal");
  terminal.innerHTML = `<pre class="terminal-raw">${escapeHtml(cleanTerminalText(data))}</pre>`;
}

function cleanTerminalText(data) {
  const workflow = data.workflow || {};
  const explicit = workflow.cli_trace || workflow.terminal_lines || workflow.dialogue || workflow.transcript;
  if (Array.isArray(explicit) && explicit.length) return explicit.map(terminalLineText).join("\n");
  const task = data.tree.meta?.task || "Assess an urban-analysis question.";
  const lines = [
    "URBAN-HERMES / REVIEWABLE RESEARCH RUNTIME",
    `session   ${data.tree.meta?.state_id || data.tree.meta?.session_id || "active"}`,
    `question  ${task}`,
    `route     ${data.tree.nodes.length} nodes / ${(data.tree.edges || []).length} dependencies`,
    ""
  ];
  for (const item of displayPlannerTodo(asArray(workflow.planner_todo), data.tree)) {
    lines.push(`[${String(item.status || "pending").padEnd(14, " ")}] ${item.step_id || "step"}  ${item.title || item.step || ""}`);
  }
  lines.push("");
  for (const choice of asArray(workflow.human_choices)) {
    lines.push(`human     ${choice.node_id || choice.branch_id || "choice"} -> ${choice.decision || choice.choice || "recorded"}`);
  }
  for (const artifact of workflowArtifacts(data).slice(0, 12)) {
    lines.push(`artifact  ${artifact.node_id || artifact.branch_id || "node"} <= ${artifact.title || fileName(artifact.path || "")}`);
  }
  lines.push(`review    ${(data.validation?.issues || []).length ? data.validation.issues.join("; ") : "route state validation passed"}`);
  return lines.join("\n");
}

function epistemicCards() {
  const f500 = scaleFinding("500m");
  const f200 = scaleFinding("200m");
  const moran500 = state.findings?.spatial_oof_residual_moran?.["500m"] || {};
  const moran200 = state.findings?.spatial_oof_residual_moran?.["200m"] || {};
  const sampling = state.manifest?.data_governance?.sampling || "Deterministic 10% UUID sample of observed LBS device users";
  return [
    {
      id: "population-coverage",
      failure: "passive",
      severity: "high",
      gate: "QUALIFY",
      title: "Population coverage",
      source: sampling,
      consequence: "Activity is observed only for sampled devices; excluded or unobserved residents cannot enter the outcome.",
      preventable: "Not by tuning the current model. It requires a redesigned data regime or external population validation.",
      action: "Keep every claim sample-conditional",
      button: "Qualify claim"
    },
    {
      id: "validation-regime",
      failure: "active",
      severity: "high",
      gate: "BLOCK",
      title: "Validation regime",
      source: `500 m random forest: training R² ${metric(f500.train_r2)}; spatial-block R² ${metric(f500.r2_mean)}`,
      consequence: "A train-only result overstates transfer to held-out urban zones and creates a fit-trap narrative.",
      preventable: "Yes. Rank routes by repeated spatial validation, not training fit.",
      action: "Block train-only superiority claims",
      button: "Block claim"
    },
    {
      id: "scale-choice",
      failure: "active",
      severity: "medium",
      gate: "COMPARE",
      title: "Spatial scale choice",
      source: `Spatial-block R²: ${metric(f500.r2_mean)} at 500 m versus ${metric(f200.r2_mean)} at 200 m`,
      consequence: "The analytical unit changes apparent predictability and the geography of residual error.",
      preventable: "Yes. Preserve both branches and report scale sensitivity before selecting a claim.",
      action: "Compare alternatives side by side",
      button: "Record comparison"
    },
    {
      id: "residual-geography",
      failure: "active",
      severity: "medium",
      gate: "DOWNGRADE",
      title: "Residual geography",
      source: `Moran's I ${metric(moran500.moran_i)} at 500 m and ${metric(moran200.moran_i)} at 200 m; p = ${metric(moran500.permutation_p)}`,
      consequence: "Prediction error remains spatially clustered, so local mechanisms and independent-error inference remain unsupported.",
      preventable: "Partly. Re-specify spatial structure and rerun diagnostics; otherwise weaken the claim.",
      action: "Downgrade local and causal inference",
      button: "Downgrade claim"
    }
  ];
}

function renderEpistemicControl() {
  const cards = epistemicCards();
  const passive = cards.filter(card => card.failure === "passive").length;
  const active = cards.filter(card => card.failure === "active").length;
  const recorded = Object.keys(state.controlActions).length;
  document.getElementById("gateSummary").innerHTML = [
    [passive, "passive"], [active, "active"], [recorded, "recorded"]
  ].map(([value, label]) => `<span class="gate-chip"><strong>${value}</strong><span>${label}</span></span>`).join("");

  document.getElementById("epistemicLedger").innerHTML = cards.map(card => {
    const recordedAction = state.controlActions[card.id];
    return `<article class="failure-card" data-failure="${escapeAttr(card.failure)}">
      <div class="failure-card-head">
        <div><span class="failure-tag ${escapeAttr(card.failure)}">${escapeHtml(card.failure.toUpperCase())}</span><h3>${escapeHtml(card.title)}</h3></div>
        <span class="failure-tag">${escapeHtml(card.gate)}</span>
      </div>
      <dl class="failure-body">
        <dt>source</dt><dd>${escapeHtml(card.source)}</dd>
        <dt>consequence</dt><dd>${escapeHtml(card.consequence)}</dd>
        <dt>preventable?</dt><dd>${escapeHtml(card.preventable)}</dd>
        <dt>human control</dt><dd>${escapeHtml(card.action)}</dd>
      </dl>
      <div class="failure-actions">
        <button type="button" data-control-id="${escapeAttr(card.id)}" aria-pressed="${recordedAction ? "true" : "false"}">${escapeHtml(recordedAction ? "Recorded ✓" : card.button)}</button>
        <button type="button" data-open-evidence="${escapeAttr(card.id)}">Inspect evidence</button>
      </div>
    </article>`;
  }).join("");

  document.querySelectorAll("[data-control-id]").forEach(button => {
    button.addEventListener("click", () => recordControlAction(button.dataset.controlId));
  });
  document.querySelectorAll("[data-open-evidence]").forEach(button => {
    button.addEventListener("click", () => {
      const target = document.getElementById(`metric-${button.dataset.openEvidence}`);
      target?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  });
  renderCheckpointQueue(cards);
}

function recordControlAction(cardId) {
  const card = epistemicCards().find(item => item.id === cardId);
  if (!card || state.controlActions[cardId]) return;
  state.controlActions[cardId] = { action: card.action, recordedAt: new Date().toISOString() };
  state.localMessages.push({
    role: "human",
    stage: "Human checkpoint / local preview",
    body: `Control recorded: ${card.action}.`,
    points: [`${card.title}: ${card.gate}`, "This preview is not written back to the runtime route state."],
    local: true
  });
  renderEpistemicControl();
  renderTodoAndDialogue();
}

function renderCheckpointQueue(cards = epistemicCards()) {
  const queue = cards.filter(card => !state.controlActions[card.id]);
  document.getElementById("checkpointCount").textContent = String(queue.length);
  document.getElementById("checkpointQueue").innerHTML = queue.length
    ? queue.map(card => `<article class="checkpoint-card" data-severity="${escapeAttr(card.severity)}"><strong>${escapeHtml(card.gate)} / ${escapeHtml(card.title)}</strong><p>${escapeHtml(card.action)}</p></article>`).join("")
    : "<p class=\"small\">All visible checkpoints have a recorded local decision.</p>";
}

function visualEvidenceMarkup() {
  return `<article class="viz-hero" id="metric-residual-geography">
    <div class="viz-hero-head">
      <div><p class="eyebrow">spatial.residual.linked</p><h3>Where the model misses—and whether the miss is systematic</h3></div>
      <p>500 m / random forest / spatial-block OOF</p>
    </div>
    <div id="vizSpatialLinked" class="viz-frame" aria-label="Linked residual map, prediction plot, and residual histogram"></div>
  </article>
  <div class="viz-grid">
    <article class="viz-card" id="metric-scale-choice">
      <div class="viz-card-head"><div><p class="eyebrow">compare.packages</p><h3>Spatial transfer by evidence package</h3></div></div>
      <div id="vizValidation" class="viz-frame" aria-label="Spatial validation comparison"></div>
    </article>
    <article class="viz-card" id="metric-validation-regime">
      <div class="viz-card-head"><div><p class="eyebrow">compare.regimes</p><h3>Training fit versus held-out geography</h3></div></div>
      <div id="vizFitGap" class="viz-frame" aria-label="Training and spatial validation fit gap"></div>
    </article>
    <article class="viz-card" id="metric-population-coverage">
      <div class="viz-card-head"><div><p class="eyebrow">compare.cohorts</p><h3>Observed activity is not population coverage</h3></div></div>
      <div id="vizCohorts" class="viz-frame" aria-label="Weekend weekday activity by age cohort"></div>
    </article>
    <article class="viz-card">
      <div class="viz-card-head"><div><p class="eyebrow">diagnose.meaning</p><h3>Stable ranking, structured error</h3></div></div>
      <div id="vizDiagnostics" class="viz-frame" aria-label="Temporal stability and residual geography diagnostics"></div>
    </article>
  </div>
  <div class="viz-caption">
    <span><strong>Visible evidence:</strong> repeated 5×5 spatial-block validation, out-of-fold grid predictions, residual Moran tests, and cohort-level weekday/weekend counts.</span>
    <span><strong>Claim boundary:</strong> device-user activity over seven days; predictive association, not resident-population prevalence or causal effect.</span>
    <span><a href="${escapeAttr(CASE_ARTIFACTS.results)}" target="_blank" rel="noreferrer">case figure</a> · <a href="${escapeAttr(CASE_ARTIFACTS.process)}" target="_blank" rel="noreferrer">research trace</a></span>
  </div>`;
}

async function embedVisualSkill(target, spec) {
  return window.vegaEmbed(target, spec, {
    renderer: "svg",
    actions: { export: true, source: false, compiled: false, editor: false },
    tooltip: true
  });
}

async function renderVisualEvidence() {
  const host = document.getElementById("visualEvidence");
  const skills = window.URBAN_VIS_SKILLS;
  const analytics = state.analytics || {};
  host.innerHTML = visualEvidenceMarkup();

  if (!window.vegaEmbed || !skills || !analytics.predictions?.length) {
    host.innerHTML = `<div class="visual-fallback"><h3>Interactive evidence unavailable</h3><p>The Vega runtime or analytical CSV files could not be loaded. Static results remain available below.</p><p><a href="${escapeAttr(CASE_ARTIFACTS.results)}" target="_blank" rel="noreferrer">Open the outcome-grounded case figure</a></p></div>`;
    return;
  }

  try {
    const viewPromises = [
      embedVisualSkill("#vizSpatialLinked", skills.render("spatial.residual.linked", analytics.predictions)),
      embedVisualSkill("#vizValidation", skills.render("validation.packages.compare", analytics.modelSummary)),
      embedVisualSkill("#vizFitGap", skills.render("validation.fit_gap", analytics.modelSummary)),
      embedVisualSkill("#vizCohorts", skills.render("population.cohort_retention", analytics.temporalSummary)),
      embedVisualSkill("#vizDiagnostics", skills.render("diagnostic.epistemic_summary", state.findings))
    ];
    const runtime = { viewPromises, views: [], renderedAt: new Date().toISOString() };
    window.URBAN_VIS_RUNTIME = runtime;
    viewPromises.forEach((promise, index) => {
      promise.then(result => {
        runtime.views[index] = result.view;
        if (index !== 0) return;
        result.view?.addSignalListener("spatialBrush", (_name, value) => {
          const active = value && Object.keys(value).length > 0;
          document.getElementById("selectionStatus").textContent = active
            ? "Spatial filter active. The observed–predicted plot and residual distribution now show only the selected geography; double-click the map to reset."
            : "All 500 m spatial-block predictions are visible. Drag across the map to inspect a subset.";
        });
      }).catch(error => console.error(`Visual skill ${index} failed`, error));
    });
  } catch (error) {
    console.error("Visual skill rendering failed", error);
    host.innerHTML = `<div class="visual-fallback"><h3>Interactive evidence could not be rendered</h3><p>${escapeHtml(error.message || String(error))}</p><p><a href="${escapeAttr(CASE_ARTIFACTS.results)}" target="_blank" rel="noreferrer">Open the static case figure</a></p></div>`;
  }
}

function renderRouteRail() {
  const tree = state.data.tree;
  const todo = displayPlannerTodo(asArray(state.data.workflow?.planner_todo), tree);
  const selectedStep = stepOf(tree.nodes.find(node => nodeId(node) === state.selectedNodeId) || tree.nodes[0] || {});
  const selectedNodeCount = (tree.active_path || tree.branch_tree?.active || []).length;
  document.getElementById("stageRail").innerHTML = ROUTE_STAGES.map(stage => {
    const nodes = tree.nodes.filter(node => stepOf(node) === stage.step);
    const completed = nodes.filter(node => ["completed", "approved", "selected", "active", "merged"].includes(nodeStatus(node))).length;
    const todoItem = todo.find(item => String(item.step_id || "").startsWith(`S${stage.step}`));
    const stageState = completed === nodes.length && nodes.length ? "reviewed" : completed ? "in review" : (todoItem?.status || "pending");
    const progress = nodes.length ? (completed / nodes.length) * 100 : 0;
    return `<button type="button" class="rail-step ${selectedStep === stage.step ? "is-active" : ""}" data-route-step="${stage.step}">
      <span class="rail-index">0${stage.step}</span>
      <span class="rail-copy"><strong>${escapeHtml(stage.label)}</strong><span>${escapeHtml(stageState)}</span><small>${completed}/${nodes.length} reviewed or selected</small><span class="stage-progress"><i style="width:${progress}%"></i></span></span>
    </button>`;
  }).join("");
  document.getElementById("routeProgress").textContent = `${selectedNodeCount}/${tree.nodes.length}`;
  document.querySelectorAll("[data-route-step]").forEach(button => {
    button.addEventListener("click", () => {
      const step = Number(button.dataset.routeStep);
      const candidates = tree.nodes.filter(node => stepOf(node) === step);
      const target = candidates.find(node => ["completed", "selected", "active", "approved"].includes(nodeStatus(node))) || candidates[0];
      if (target) selectNode(nodeId(target));
    });
  });
}

function activateWorkbenchTab(name) {
  document.querySelectorAll("[data-workbench-tab]").forEach(button => {
    const active = button.dataset.workbenchTab === name;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll("[data-workbench-view]").forEach(view => {
    view.hidden = view.dataset.workbenchView !== name;
  });
  if (name === "route") window.requestAnimationFrame(() => {
    renderTree();
    fitTreeToStage();
  });
}

function setupWorkspaceInteractions() {
  document.querySelectorAll("[data-workbench-tab]").forEach(button => {
    button.addEventListener("click", () => activateWorkbenchTab(button.dataset.workbenchTab));
  });
  document.querySelectorAll("[data-thread-view]").forEach(button => {
    button.addEventListener("click", () => {
      const raw = button.dataset.threadView === "raw";
      document.getElementById("dialogueTimeline").hidden = raw;
      document.getElementById("cliTerminal").hidden = !raw;
      document.querySelectorAll("[data-thread-view]").forEach(item => item.classList.toggle("is-active", item === button));
    });
  });
  document.getElementById("researchNoteForm").addEventListener("submit", event => {
    event.preventDefault();
    const input = document.getElementById("researchNote");
    const note = input.value.trim();
    if (!note) return;
    state.localMessages.push({ role: "human", stage: "Local research note", body: note, points: ["Not written back to the runtime route state"], local: true });
    input.value = "";
    renderTodoAndDialogue();
  });
}

function renderWorkflowRail() {
  const data = state.data;
  const tree = data.tree;
  const active = tree.active_path?.length ? tree.active_path : tree.branch_tree?.active || [];
  const selected = active.map(id => tree.nodes.find(node => nodeId(node) === id)).filter(Boolean);
  document.getElementById("workflowRail").innerHTML = selected.map((node, index) => {
    const tsp = nodeMeaning(node);
    const artifacts = nodeArtifacts(node, data).slice(0, 3);
    return `<article class="workflow-step" data-node="${escapeAttr(nodeId(node))}">
      <button type="button" class="step-dot" title="Open node">${index + 1}</button>
      <div class="workflow-copy">
        <h3>${escapeHtml(nodeId(node))}: ${escapeHtml(shorten(nodeQuestion(node), 92))}</h3>
        <p><strong>Input:</strong> ${escapeHtml((node.required_inputs || []).slice(0, 3).join("; ") || "not recorded")}</p>
        <p><strong>Output:</strong> ${escapeHtml((node.expected_outputs || []).slice(0, 3).join("; ") || "not recorded")}</p>
        <div class="mini-meaning">
          <span>time: ${escapeHtml(shorten(tsp.time || "", 72))}</span>
          <span>space: ${escapeHtml(shorten(tsp.space || "", 72))}</span>
          <span>people: ${escapeHtml(shorten(tsp.people || "", 72))}</span>
        </div>
        ${artifacts.length ? `<div class="pill-row">${artifacts.map(a => `<span class="pill">${escapeHtml(a.title || fileName(a.path || ""))}</span>`).join("")}</div>` : ""}
      </div>
    </article>`;
  }).join("");
  document.querySelectorAll(".workflow-step").forEach(item => {
    item.addEventListener("click", () => selectNode(item.dataset.node));
  });
}

function renderConditions(summary) {
  const variants = summary?.variants || summary?.design_gate_ablation || fallback.summary?.variants || [];
  document.getElementById("conditions").innerHTML = variants.map(variant => {
    const max = variant.max_score || 18;
    const score = variant.total_score || 0;
    const pct = Math.max(0, Math.min(100, Math.round(score / max * 100)));
    const decisions = Object.entries(variant.decision_counts || {});
    return `<article class="condition">
      <div class="condition-head">
        <h3>${escapeHtml(variant.variant)}</h3>
        <span class="score">${score}/${max}</span>
      </div>
      <div class="bar"><span style="width:${pct}%"></span></div>
      <p><span class="pill">rows ${variant.row_count ?? 0}</span> <span class="pill">${escapeHtml(variant.status || "recorded")}</span></p>
      ${decisions.map(([key, value]) => `<div class="decision-line"><span>${escapeHtml(key)}</span><strong>${value}</strong></div>`).join("") || "<p>No machine-readable decision distribution.</p>"}
    </article>`;
  }).join("");
}

let allTasks = [];

function setupFilters(tasks) {
  allTasks = tasks || [];
  const domains = ["all", ...new Set(allTasks.map(t => t.domain).filter(Boolean))];
  const decisions = ["all", ...new Set(allTasks.map(t => t.decision).filter(Boolean))];
  fillSelect("domainFilter", domains);
  fillSelect("decisionFilter", decisions);
  document.getElementById("domainFilter").addEventListener("change", renderTasks);
  document.getElementById("decisionFilter").addEventListener("change", renderTasks);
  renderTasks();
}

function fillSelect(id, values) {
  document.getElementById(id).innerHTML = values.map(v => `<option value="${escapeAttr(v)}">${escapeHtml(v)}</option>`).join("");
}

function renderTasks() {
  const domain = document.getElementById("domainFilter").value;
  const decision = document.getElementById("decisionFilter").value;
  const rows = allTasks.filter(task =>
    (domain === "all" || task.domain === domain) &&
    (decision === "all" || task.decision === decision)
  );
  const missing = rows.filter(task => (task.missing_data || "").trim()).length;
  const blocked = rows.filter(task => /blocked|missing|defer/.test(task.decision || "")).length;
  document.getElementById("taskStats").innerHTML = [
    ["visible rows", rows.length],
    ["missing-data rows", missing],
    ["stop/defer/block rows", blocked],
    ["source rows", allTasks.length]
  ].map(([key, value]) => `<div class="metric"><strong>${value}</strong>${key}</div>`).join("");
  document.getElementById("taskRows").innerHTML = rows.map(task => `<tr>
    <td>${escapeHtml(task.task_id)}</td>
    <td>${escapeHtml(task.domain)}</td>
    <td><span class="pill">${escapeHtml(task.decision)}</span></td>
    <td>${escapeHtml(task.missing_data || "none recorded")}</td>
    <td>${escapeHtml(task.claim_boundary || "not recorded")}</td>
  </tr>`).join("");
}

function parseCsv(text) {
  const rows = [];
  let row = [], cell = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i], next = text[i + 1];
    if (ch === '"' && quoted && next === '"') { cell += '"'; i++; continue; }
    if (ch === '"') { quoted = !quoted; continue; }
    if (ch === "," && !quoted) { row.push(cell); cell = ""; continue; }
    if ((ch === "\n" || ch === "\r") && !quoted) {
      if (ch === "\r" && next === "\n") i++;
      row.push(cell); cell = "";
      if (row.some(v => v !== "")) rows.push(row);
      row = [];
      continue;
    }
    cell += ch;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  const header = rows.shift() || [];
  return rows.map(values => Object.fromEntries(header.map((h, i) => [h, values[i] || ""])));
}

function el(name, attrs = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attrs).forEach(([key, value]) => {
    if (key === "class") node.setAttribute("class", value);
    else node.setAttribute(key, value);
  });
  return node;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}

function escapeAttr(value) {
  return escapeHtml(value).replace(/`/g, "&#96;");
}

function shorten(value, limit) {
  const text = String(value ?? "");
  return text.length > limit ? `${text.slice(0, limit - 1)}...` : text;
}

function fileName(path) {
  return String(path || "").replace(/\\/g, "/").split("/").filter(Boolean).pop() || "";
}

function fileExt(path) {
  const name = fileName(path);
  const idx = name.lastIndexOf(".");
  return idx >= 0 ? name.slice(idx + 1) : "";
}

async function refresh() {
  const loaded = await loadData();
  state.data = normalizeRouteState(loaded.routeState);
  state.summary = loaded.summary;
  state.tasks = loaded.tasks;
  state.findings = loaded.findings || fallbackFindings;
  state.reviews = loaded.reviews || [];
  state.manifest = loaded.manifest || null;
  state.analytics = loaded.analytics || { modelSummary: [], temporalSummary: [], predictions: [] };
  if (!state.selectedNodeId || !state.data.tree.nodes.some(node => nodeId(node) === state.selectedNodeId)) {
    state.selectedNodeId = state.data.tree.active_path?.[0] || state.data.tree.branch_tree?.active?.[0] || nodeId(state.data.tree.nodes[0]);
  }
  renderTree();
  renderNodeDetail();
  renderTodoAndDialogue();
  renderRouteRail();
  renderEpistemicControl();
  renderVisualEvidence();
  renderWorkflowRail();
  renderConditions(loaded.summary);
  setupFilters(loaded.tasks);
  document.getElementById("dataMode").textContent = loaded.mode;
  const artifacts = workflowArtifacts(state.data);
  document.getElementById("artifactCount").textContent = `${artifacts.length + 2} artifacts`;
}

function setupControls() {
  setupWorkspaceInteractions();
  document.getElementById("refreshButton").addEventListener("click", refresh);
  document.getElementById("zoomOut").addEventListener("click", () => setTreeZoom(state.treeZoom - 0.12));
  document.getElementById("zoomIn").addEventListener("click", () => setTreeZoom(state.treeZoom + 0.12));
  document.getElementById("zoomFit").addEventListener("click", fitTreeToStage);
  document.getElementById("autoRefresh").addEventListener("change", event => {
    if (state.refreshTimer) window.clearInterval(state.refreshTimer);
    state.refreshTimer = event.target.checked ? window.setInterval(refresh, 7000) : null;
  });
  setupTreePanAndWheel();
  window.addEventListener("resize", () => renderTree());
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function setTreeZoom(value, anchor = null) {
  const stage = document.querySelector(".tree-stage");
  const oldZoom = state.treeZoom;
  state.treeZoom = clamp(value, MIN_TREE_ZOOM, MAX_TREE_ZOOM);
  if (!stage || oldZoom === state.treeZoom) {
    renderTree();
    return;
  }
  const focus = anchor || { x: stage.clientWidth / 2, y: stage.clientHeight / 2 };
  const contentX = (stage.scrollLeft + focus.x) / oldZoom;
  const contentY = (stage.scrollTop + focus.y) / oldZoom;
  renderTree();
  stage.scrollLeft = contentX * state.treeZoom - focus.x;
  stage.scrollTop = contentY * state.treeZoom - focus.y;
}

function fitTreeToStage() {
  const stage = document.querySelector(".tree-stage");
  if (!stage) return;
  const oldZoom = state.treeZoom;
  state.treeZoom = 1;
  const layout = buildLayout(state.data.tree);
  state.treeZoom = oldZoom;
  const fit = Math.min((stage.clientWidth - 24) / layout.width, (stage.clientHeight - 24) / layout.height);
  setTreeZoom(clamp(fit, MIN_TREE_ZOOM, 1.05));
  stage.scrollLeft = 0;
  stage.scrollTop = 0;
}

function setupTreePanAndWheel() {
  const stage = document.querySelector(".tree-stage");
  if (!stage) return;

  // Global click handler — uses elementsFromPoint to find the route-node
  // regardless of SVG pointer-events quirks or scroll position.
  document.addEventListener("click", event => {
    if (state.panning) return; // was a drag, not a click
    // Only handle clicks that land inside the tree stage
    const stageRect = stage.getBoundingClientRect();
    if (event.clientX < stageRect.left || event.clientX > stageRect.right ||
        event.clientY < stageRect.top || event.clientY > stageRect.bottom) return;
    const elements = document.elementsFromPoint(event.clientX, event.clientY);
    for (const el of elements) {
      const routeNode = el.closest?.(".route-node");
      if (routeNode && routeNode.dataset?.nodeId) {
        selectNode(routeNode.dataset.nodeId);
        return;
      }
    }
  });

  stage.addEventListener("pointerdown", event => {
    if (event.button !== 0) return;
    if (event.target.closest?.("button, a, input, select, [role='button'], .route-node")) return;
    state.panning = {
      x: event.clientX,
      y: event.clientY,
      left: stage.scrollLeft,
      top: stage.scrollTop
    };
    stage.classList.add("is-panning");
    stage.setPointerCapture?.(event.pointerId);
  });
  stage.addEventListener("pointermove", event => {
    if (!state.panning) return;
    stage.scrollLeft = state.panning.left - (event.clientX - state.panning.x);
    stage.scrollTop = state.panning.top - (event.clientY - state.panning.y);
  });
  const stopPan = event => {
    if (!state.panning) return;
    state.panning = null;
    stage.classList.remove("is-panning");
    stage.releasePointerCapture?.(event.pointerId);
  };
  stage.addEventListener("pointerup", stopPan);
  stage.addEventListener("pointercancel", stopPan);
  stage.addEventListener("wheel", event => {
    if (!(event.ctrlKey || event.metaKey)) return;
    event.preventDefault();
    const rect = stage.getBoundingClientRect();
    const anchor = { x: event.clientX - rect.left, y: event.clientY - rect.top };
    setTreeZoom(state.treeZoom + (event.deltaY > 0 ? -0.08 : 0.08), anchor);
  }, { passive: false });
}

setupControls();
refresh();
