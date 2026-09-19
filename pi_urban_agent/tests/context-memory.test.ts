import assert from "node:assert/strict";
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { buildRecoveryCapsule, recallResearchState } from "../src/core/context-memory.js";
import { resolveCompactionSettings } from "../src/core/model-context.js";
import { ResearchStore } from "../src/core/research-store.js";
import { CONTRACT } from "./fixtures.js";

test("recovery capsule pins active route and non-proceed review decisions", async () => {
  const runDir = await mkdtemp(join(tmpdir(), "urban-recovery-"));
  const store = await ResearchStore.initialize(runDir, CONTRACT);
  const branch = await store.openBranch({
    nodeId: "gwr_300",
    nodeType: "model_route",
    title: "300 m adaptive GWR sensitivity",
    decisionQuestion: "Is the local route stable across held-out areas?",
    parameters: { model: "GWR", bandwidth_fraction: 0.3 },
    claimBoundary: "Sensitivity evidence only.",
    summary: "Local comparison route.",
  });
  await store.setPhase("execute", branch.nodeId);
  const artifactPath = join(runDir, "gwr.csv");
  await writeFile(artifactPath, "bandwidth,oof_r2\n0.3,0.42\n", "utf8");
  await store.attachEvidence({ branchId: branch.nodeId, role: "metrics", path: artifactPath, summary: "OOF evidence", metrics: { oof_r2: 0.42 } });
  await store.setPhase("review", branch.nodeId);
  await store.recordReview({
    branchId: branch.nodeId,
    decision: "repair",
    checks: { held_out_transfer: "pass", local_stability: "fail" },
    rationale: "Narrow bandwidth is unstable.",
    requiredAction: "Compare a wider bandwidth.",
  });
  const state = await store.load();
  const capsule = buildRecoveryCapsule(state, state.activeBranchId, "minimal");
  assert.deepEqual(capsule.activePathIds, ["research_object", "gwr_300"]);
  assert.equal(capsule.reviewConstraints[0]?.decision, "repair");
  assert.match(capsule.openLoops.join(" "), /wider bandwidth/i);
});

test("urban recall retrieves exact structured records rather than guessing from summaries", async () => {
  const runDir = await mkdtemp(join(tmpdir(), "urban-recall-"));
  const store = await ResearchStore.initialize(runDir, CONTRACT);
  await store.openBranch({
    nodeId: "ols_800",
    nodeType: "model_route",
    title: "800 m OLS baseline",
    decisionQuestion: "Does the global baseline transfer?",
    parameters: { support_m: 800, model: "OLS" },
    claimBoundary: "Association only.",
    summary: "Primary candidate.",
  });
  const state = await store.load();
  const recalled = recallResearchState(state, { scope: "branch", ids: ["ols_800"], detail: "card", dependencyDepth: 1, tokenLimit: 1_000 });
  assert.equal(recalled.records.length, 2);
  assert.match(JSON.stringify(recalled.records), /support_m/);
  assert.equal(recalled.stateVersion, state.stateVersion);
});

test("batch branch recall de-duplicates shared ancestors across repeated calls", async () => {
  const runDir = await mkdtemp(join(tmpdir(), "urban-recall-dedupe-"));
  const store = await ResearchStore.initialize(runDir, CONTRACT);
  for (const id of ["route_a", "route_b"]) await store.openBranch({
    nodeId: id, nodeType: "model_route", title: id, parentIds: ["research_object"],
    decisionQuestion: "Compare route.", parameters: { id }, claimBoundary: "Association only.",
  });
  const state = await store.load();
  const first = recallResearchState(state, { scope: "branch", ids: ["route_a"], dependencyDepth: 1, tokenLimit: 1_000 });
  const ids = (first.records as Array<{ nodeId?: string }>).map((record) => record.nodeId).filter(Boolean) as string[];
  const second = recallResearchState(state, { scope: "branch", ids: ["route_b"], dependencyDepth: 1, tokenLimit: 1_000, excludeIds: ids });
  assert.deepEqual((second.records as Array<{ nodeId?: string }>).map((record) => record.nodeId), ["route_b"]);
});

test("four adjudicated route cards fit a micro-model batch recall budget", async () => {
  const runDir = await mkdtemp(join(tmpdir(), "urban-recall-micro-batch-"));
  const store = await ResearchStore.initialize(runDir, CONTRACT);
  const ids = ["ols_800_global", "gwr_300_adaptive_30", "gwr_700_adaptive_10_blocked", "gwr_800_fixed_12km"];
  for (const [index, id] of ids.entries()) await store.openBranch({
    nodeId: id, nodeType: "model_route", title: id, parentIds: ["research_object"],
    decisionQuestion: "Compare route.",
    parameters: { model: index === 0 ? "OLS" : "GWR", analysis_support_m: index === 1 ? 300 : index === 0 ? 800 : 700, bandwidth_fraction: index === 1 ? 0.3 : undefined, bandwidth_distance_m: index === 3 ? 12_000 : undefined },
    claimBoundary: "Within-city, sample-conditional sensitivity evidence only; no causal or universal optimum.",
  });
  const deferred = await store.recordHumanDecision({
    branchIds: ["gwr_800_fixed_12km"], decision: "defer", rationale: "Await expert interpretation.", actor: "human_expert",
  });
  await store.persistPendingHumanPatch({
    actorId: "signed_user", source: "test", sourceMessageHash: "msg-hash",
    targetBranchIds: ["gwr_800_fixed_12km"], proposedDecision: "retain_sensitivity",
    expectedSupersedesDecisionId: deferred.decisionId, rawTextDigest: "retain the fixed route",
  });
  const recalled = recallResearchState(await store.load(), { scope: "branch", ids, detail: "card", dependencyDepth: 0, tokenLimit: 655 });
  assert.equal(recalled.records.length, 4);
  assert.equal(recalled.omittedRecords, 0);
  assert.equal(recalled.actionSatisfied, true);
  assert.match(recalled.nextAction ?? "", /Do not recall these routes again/);
  assert.match(recalled.nextAction ?? "", new RegExp(deferred.decisionId));
});

test("tree recall remains a bounded pointer index even when full detail is requested", async () => {
  const runDir = await mkdtemp(join(tmpdir(), "urban-tree-index-"));
  const store = await ResearchStore.initialize(runDir, CONTRACT);
  for (let index = 0; index < 24; index += 1) {
    await store.openBranch({
      nodeId: `route_${index}`,
      nodeType: "model_route",
      title: `Route ${index}`,
      decisionQuestion: "Locate this route by stable ID.",
      parameters: { large_payload: "x".repeat(1_000) },
      claimBoundary: "Association only.",
      summary: `Compact route ${index} digest.`,
    });
  }
  const state = await store.load();
  const recalled = recallResearchState(state, { scope: "tree", detail: "full", tokenLimit: 8_000 });
  assert.equal(recalled.request.detail, "pointer");
  assert.equal(recalled.request.tokenLimit, 480);
  assert.ok(recalled.hasMore);
  assert.doesNotMatch(JSON.stringify(recalled.records), /large_payload/);
});

test("Pi compaction settings scale down for small models without fixed 16k/20k reserves", () => {
  for (const [window, output] of [[4096,1024],[8192,2048],[16384,4096],[131072,16384]]) {
    const settings = resolveCompactionSettings(window, output);
    assert.equal(settings.reserveTokens, output + Math.max(256, Math.ceil(window * .06)));
    assert.equal(settings.keepRecentTokens, Math.min(12000, Math.floor(window * .2)));
    assert.ok(settings.reserveTokens < window);
  }
});

test("pointer recovery keeps human-selected routes and their exact evidence ahead of blocked distractors", async () => {
  const runDir = await mkdtemp(join(tmpdir(), "urban-pinned-recovery-"));
  const store = await ResearchStore.initialize(runDir, CONTRACT);
  await store.openBranch({
    nodeId: "ols_800_global",
    nodeType: "model_route",
    title: "800 m OLS global baseline",
    decisionQuestion: "Retain the global route?",
    parameters: { model: "OLS", analysis_support_m: 800 },
    claimBoundary: "Within-city association only.",
    summary: "OOF R2 0.5336; candidate main global route.",
  });
  await store.recordHumanDecision({
    branchIds: ["ols_800_global"],
    decision: "select_main",
    rationale: "Retain the reviewed global route.",
    actor: "human_expert",
  });
  for (let index = 0; index < 12; index += 1) {
    const id = `blocked_distractor_${index}`;
    await store.openBranch({
      nodeId: id,
      nodeType: "model_route",
      title: `Blocked distractor ${index}`,
      decisionQuestion: "Archived alternative.",
      parameters: { model: "GWR", analysis_support_m: 200 + index * 10 },
      claimBoundary: "No downstream claim.",
      summary: "Rejected provisional route.",
    });
    await store.recordHumanDecision({
      branchIds: [id],
      decision: "block",
      rationale: "Rejected provisional route.",
      actor: "human_expert",
    });
  }
  const state = await store.load();
  const capsule = buildRecoveryCapsule(state, state.activeBranchId, "pointer");
  const selected = capsule.treeOutline.find((node) => node.nodeId === "ols_800_global");
  assert.ok(selected, "human-selected route should survive pointer reduction");
  assert.match(selected.digest ?? "", /0\.5336/);
  assert.deepEqual(capsule.adjudicatedRoutes.map(({ branchId, role }) => ({ branchId, role })), [
    { branchId: "ols_800_global", role: "main" },
    ...capsule.adjudicatedRoutes
      .filter((route) => route.branchId !== "ols_800_global")
      .map(({ branchId, role }) => ({ branchId, role })),
  ]);
  assert.match(capsule.adjudicatedRoutes[0]?.evidenceDigest ?? "", /0\.5336/);
});
