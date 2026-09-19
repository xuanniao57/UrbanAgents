import assert from "node:assert/strict";
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { ContextCompiler, allocateBudget } from "../src/core/context-compiler.js";
import { ResearchStore } from "../src/core/research-store.js";
import { CONTRACT } from "./fixtures.js";

test("ContextCompiler pins the active path and stores siblings as compact comparisons", async () => {
  const runDir = await mkdtemp(join(tmpdir(), "urban-pi-context-"));
  const store = await ResearchStore.initialize(runDir, CONTRACT);
  await store.openBranch({
    nodeId: "ols_800",
    nodeType: "model_route",
    title: "800 m OLS global baseline",
    decisionQuestion: "Which global route transfers best?",
    parameters: { model: "OLS", analysis_support_m: 800, role: "global_baseline" },
    claimBoundary: "Global association only.",
    summary: "Primary global baseline candidate.",
  });
  const gwr = await store.openBranch({
    nodeId: "gwr_300",
    nodeType: "model_route",
    title: "300 m adaptive GWR",
    parentIds: ["research_object"],
    decisionQuestion: "Does local weighting add stable sensitivity evidence?",
    parameters: { model: "GWR", bandwidth_fraction: 0.30, role: "local_sensitivity" },
    claimBoundary: "Local sensitivity, not causal mechanism.",
    summary: "Local sensitivity candidate.",
  });
  await store.setPhase("execute", gwr.nodeId);
  const artifactPath = join(runDir, "metrics.csv");
  await writeFile(artifactPath, "support,oof_r2\n300,0.4256\n", "utf8");
  const artifact = await store.attachEvidence({
    branchId: gwr.nodeId,
    role: "held_out_metrics",
    path: artifactPath,
    summary: "OOF R2 0.4256 on common held-out geography.",
    metrics: { oof_r2: 0.4256 },
  });
  const state = await store.load();
  const compiler = new ContextCompiler();
  const packet = compiler.compile(state, { contextWindow: 40_960 });
  assert.deepEqual(packet.activePath.map((node) => node.nodeId), ["research_object", "gwr_300"]);
  assert.equal(packet.siblingSummaries.some((node) => node.nodeId === "ols_800"), true);
  assert.equal(packet.evidence[0].sha256, artifact.sha256);
  assert.ok(packet.estimatedTokens < packet.budget.stateBudget);
  const rendered = compiler.render(packet);
  assert.match(rendered, /bandwidth_fraction/);
  assert.match(rendered, new RegExp(artifact.sha256));
  assert.match(compiler.compactionSummary(state), /authoritative and must not be inferred/);
});

test("Context budget preserves explicit finalization and state reserves", () => {
  const budget = allocateBudget(40_960);
  assert.equal(budget.contextWindow, 40_960);
  assert.ok(budget.responseReserve >= 4_096);
  assert.equal(
    budget.systemBudget + budget.toolBudget + budget.stateBudget + budget.recentDialogueBudget + budget.responseReserve + budget.safetyReserve,
    budget.contextWindow,
  );
});

test("Context budgets adapt to the declared model window instead of inflating small models", () => {
  const windows = [4_096, 8_192, 16_384, 40_960, 131_072, 262_144];
  const expectedProfiles = ["micro", "micro", "compact", "balanced", "spacious", "spacious"];
  windows.forEach((window, index) => {
    const budget = allocateBudget(window, Math.floor(window * 0.2));
    assert.equal(budget.contextWindow, window);
    assert.equal(budget.profile, expectedProfiles[index]);
    assert.ok(budget.stateBudget > 0);
    assert.ok(budget.recentDialogueBudget > 0);
    assert.equal(
      budget.systemBudget + budget.toolBudget + budget.stateBudget + budget.recentDialogueBudget + budget.responseReserve + budget.safetyReserve,
      budget.contextWindow,
    );
  });
});

test("ContextCompiler degrades fidelity deterministically for small windows", async () => {
  const runDir = await mkdtemp(join(tmpdir(), "urban-pi-small-context-"));
  const store = await ResearchStore.initialize(runDir, CONTRACT);
  for (let index = 0; index < 12; index += 1) {
    await store.openBranch({
      nodeId: `branch_${index}`,
      nodeType: "model_route",
      title: `Comparison branch ${index}`,
      parentIds: ["research_object"],
      decisionQuestion: `Should comparison route ${index} be retained?`,
      parameters: { model: index % 2 ? "GWR" : "OLS", support_m: 200 + index * 100, bandwidth_fraction: 0.1 + index * 0.01 },
      claimBoundary: "Within-city sensitivity evidence only.",
      summary: "A deliberately repeated comparison summary that makes the uncompressed state larger.",
    });
  }
  const state = await store.load();
  const compiler = new ContextCompiler();
  const micro = compiler.compile(state, { contextWindow: 4_096, maxOutputTokens: 1_024 });
  const compact = compiler.compile(state, { contextWindow: 16_384, maxOutputTokens: 4_096 });
  const spacious = compiler.compile(state, { contextWindow: 131_072, maxOutputTokens: 16_384 });
  assert.equal(micro.budget.profile, "micro");
  assert.ok(["minimal", "pointer"].includes(micro.fidelity));
  assert.ok(micro.estimatedTokens <= micro.budget.stateBudget);
  assert.equal(compact.budget.profile, "compact");
  assert.ok(["compact", "minimal", "pointer"].includes(compact.fidelity));
  assert.ok(compact.estimatedTokens <= compact.budget.stateBudget);
  assert.equal(spacious.budget.profile, "spacious");
  assert.equal(spacious.fidelity, "full");
  assert.ok(spacious.estimatedTokens <= spacious.budget.stateBudget);
  assert.match(compiler.render(micro), /authoritativeState/);
});

test("state bookmark is action-oriented and does not serialize the whole Research Tree", async () => {
  const runDir = await mkdtemp(join(tmpdir(), "urban-pi-bookmark-"));
  const store = await ResearchStore.initialize(runDir, CONTRACT);
  await store.openBranch({
    nodeId: "active_gwr",
    nodeType: "parameter_route",
    title: "Active fixed-distance GWR comparison",
    decisionQuestion: "Should the comparison be retained?",
    parameters: { model: "GWR", bandwidth_m: 12_000 },
    claimBoundary: "Sensitivity evidence only.",
    summary: "Awaiting a human choice.",
  });
  for (let index = 0; index < 20; index += 1) {
    await store.openBranch({
      nodeId: `archived_${index}`,
      nodeType: "model_route",
      title: `Archived route ${index}`,
      parentIds: ["research_object"],
      decisionQuestion: "Archived comparison.",
      parameters: { model: "OLS", support_m: 200 + index * 10 },
      claimBoundary: "No active claim.",
      summary: "External memory only.",
    });
  }
  await store.setPhase("execute", "active_gwr");
  await store.setPhase("review", "active_gwr");
  await store.setPhase("human", "active_gwr");
  const bookmark = new ContextCompiler().stateBookmark(await store.load());
  assert.match(bookmark, /latest user message is the active instruction/i);
  assert.match(bookmark, /urban_recall/);
  assert.match(bookmark, /active_gwr/);
  assert.doesNotMatch(bookmark, /archived_19/);
  assert.ok(Math.ceil(bookmark.length / 4) <= 360);
});
