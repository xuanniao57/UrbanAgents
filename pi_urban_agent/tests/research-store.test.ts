import assert from "node:assert/strict";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { parseExplicitHumanPatch } from "../src/core/human-patch.js";
import { ResearchStore } from "../src/core/research-store.js";
import { CONTRACT } from "./fixtures.js";

test('omitted optional contract fields survive serialization without false tamper alarms',async()=>{
  const runDir=await mkdtemp(join(tmpdir(),'urban-optional-contract-'));
  const store=await ResearchStore.initialize(runDir,{...CONTRACT,crs:undefined,gridOrigin:undefined,validationGeography:undefined});
  const state=await store.load();
  assert.equal(state.contract.crs,undefined);
  const disk=JSON.parse(await readFile(store.statePath,'utf8'));
  disk.contract.outcome='actually modified';await writeFile(store.statePath,JSON.stringify(disk));
  await assert.rejects(store.load(),/immutable research contract/);
});

test("ResearchStore completes a reviewed human-governed route and locks it", async () => {
  const runDir = await mkdtemp(join(tmpdir(), "urban-pi-store-"));
  const store = await ResearchStore.initialize(runDir, CONTRACT);
  const branch = await store.openBranch({
    nodeId: "gwr_300_adaptive_30",
    nodeType: "model_route",
    title: "300 m adaptive GWR at 30% neighbours",
    decisionQuestion: "Does this local route transfer without unstable local fits?",
    parameters: { model: "GWR", analysis_support_m: 300, bandwidth_type: "adaptive", bandwidth_fraction: 0.30 },
    claimBoundary: "Sensitivity evidence only; no universal optimal-scale claim.",
  });
  await store.setPhase("execute", branch.nodeId);
  const evidencePath = join(runDir, "gwr_metrics.json");
  await writeFile(evidencePath, JSON.stringify({ oof_r2: 0.4256, condition_number_max: 24.1 }), "utf8");
  const artifact = await store.attachEvidence({
    branchId: branch.nodeId,
    role: "held_out_metrics",
    path: evidencePath,
    summary: "Shared-region out-of-fold metrics for the 300 m adaptive GWR route.",
    metrics: { oof_r2: 0.4256, bandwidth_fraction: 0.30 },
  });
  assert.equal(artifact.sha256.length, 64);
  await store.setPhase("review", branch.nodeId);
  await store.recordReview({
    branchId: branch.nodeId,
    decision: "proceed",
    checks: { common_contract: "pass", held_out_evidence: "pass", local_stability: "pass" },
    rationale: "Comparable and stable enough to retain as local sensitivity evidence.",
    affectedClaims: ["local sensitivity"],
  });
  await store.setPhase("human", branch.nodeId);
  await store.recordHumanDecision({
    branchIds: [branch.nodeId],
    decision: "retain_sensitivity",
    rationale: "Retain alongside the global main route.",
    actor: "human_expert",
    resultingClaimBoundary: "Local route is sensitivity evidence, not the unique optimum.",
  });
  await store.recordHumanDecision({
    branchIds: [branch.nodeId],
    decision: "approve_claim",
    rationale: "The bounded claim matches reviewed evidence.",
    actor: "human_expert",
    resultingClaimBoundary: "Within-city, sample-conditional association only.",
  });
  await store.persistPendingHumanPatch({ actorId: "human_expert", source: "rpc", sourceMessageHash: "ordinary-message", rawTextDigest: "What evidence supports the conclusion?" });
  const finalized = await store.finalize("Results vary across analysis supports and model-process scales within the observed setting.");
  const submission = JSON.parse(await readFile(finalized.submissionPath, "utf8"));
  assert.equal(submission.checkpoints.C1_research_object, true);
  assert.equal(submission.checkpoints.C3_common_holdout, true);
  assert.equal(submission.checkpoints.C5_bandwidth_reasoning, true);
  assert.equal(submission.checkpoints.C7_persistent_state, true);
  await assert.rejects(() => store.openBranch({
    nodeType: "model_route",
    title: "late branch",
    decisionQuestion: "should fail",
    claimBoundary: "none",
  }), /finalized and immutable/);
});

test("ordinary messages do not block phases, but explicit pending decisions still do", async () => {
  const store = await ResearchStore.initialize(await mkdtemp(join(tmpdir(), "urban-phase-patch-")), CONTRACT);
  await store.persistPendingHumanPatch({ actorId: "expert", source: "rpc", sourceMessageHash: "question", rawTextDigest: "Plan this research question.", targetBranchIds: ["research_object"] });
  await store.setPhase("execute", "research_object");
  await store.persistPendingHumanPatch({ actorId: "expert", source: "rpc", sourceMessageHash: "choice", rawTextDigest: "Defer research_object.", targetBranchIds: ["research_object"], proposedDecision: "defer" });
  await assert.rejects(store.setPhase("review"), /must be applied/);
  await assert.rejects(store.finalize("Not yet authorized"), /human patch/);
});

test("ordinary human ingress is closed after the turn without consuming an explicit decision", async () => {
  const store = await ResearchStore.initialize(await mkdtemp(join(tmpdir(), "urban-consume-ingress-")), CONTRACT);
  const ordinary = await store.persistPendingHumanPatch({ actorId: "expert", source: "rpc", sourceMessageHash: "ordinary", rawTextDigest: "Please explain the result." });
  const explicit = await store.persistPendingHumanPatch({ actorId: "expert", source: "rpc", sourceMessageHash: "explicit", rawTextDigest: "Defer this route.", targetBranchIds: ["research_object"], proposedDecision: "defer" });
  const consumed = await store.consumeUnclassifiedHumanPatch("ordinary", "expert");
  assert.equal(consumed?.patchId, ordinary.patchId);
  const state = await store.load();
  assert.equal(state.pendingHumanPatches?.find((patch) => patch.patchId === ordinary.patchId)?.status, "consumed_no_patch");
  assert.equal(state.pendingHumanPatches?.find((patch) => patch.patchId === explicit.patchId)?.status, "pending");
  assert.equal(await store.consumeUnclassifiedHumanPatch("ordinary", "expert"), undefined);
});

test("ResearchStore rejects a cycle-like missing dependency and contract mutation", async () => {
  const runDir = await mkdtemp(join(tmpdir(), "urban-pi-invariant-"));
  const store = await ResearchStore.initialize(runDir, CONTRACT);
  await assert.rejects(() => store.openBranch({
    nodeId: "invalid",
    nodeType: "analysis_support",
    title: "invalid",
    parentIds: ["missing"],
    decisionQuestion: "invalid",
    claimBoundary: "invalid",
  }), /Unknown parent node/);
  const state = await store.load();
  state.contract.outcome = "silently changed outcome";
  await writeFile(store.statePath, JSON.stringify(state, null, 2), "utf8");
  await assert.rejects(() => store.load(), /immutable research contract has changed/);
});

test("ResearchStore rejects contradictory or multi-target route adjudication", async () => {
  const runDir = await mkdtemp(join(tmpdir(), "urban-pi-human-guard-"));
  const store = await ResearchStore.initialize(runDir, CONTRACT);
  for (const nodeId of ["route_a", "route_b"]) {
    await store.openBranch({
      nodeId,
      nodeType: "model_route",
      title: nodeId,
      decisionQuestion: "What role should this route have?",
      claimBoundary: "Association only.",
    });
  }
  await assert.rejects(() => store.recordHumanDecision({
    branchIds: ["route_a", "route_b"],
    decision: "select_main",
    rationale: "Select all routes.",
    actor: "human_expert",
  }), /exactly one target branch/);
  await assert.rejects(() => store.recordHumanDecision({
    branchIds: ["route_a"],
    decision: "select_main",
    rationale: "Retain this only as sensitivity evidence; do not promote it to main.",
    actor: "human_expert",
  }), /sensitivity evidence cannot be written as select_main/);

  const deferred = await store.recordHumanDecision({
    branchIds: ["route_b"],
    decision: "defer",
    rationale: "Leave unresolved for later expert interpretation.",
    actor: "human_expert",
  });
  await assert.rejects(() => store.recordHumanDecision({
    branchIds: ["route_b"],
    decision: "defer",
    rationale: "Repeat the same unresolved status.",
    actor: "human_expert",
  }), /Duplicate human decision/);
  await assert.rejects(() => store.recordHumanDecision({
    branchIds: ["route_b"],
    decision: "retain_sensitivity",
    rationale: "The human now retains it as sensitivity evidence.",
    actor: "human_expert",
  }), /requires supersedes_decision_id/);
  const retained = await store.recordHumanDecision({
    branchIds: ["route_b"],
    decision: "retain_sensitivity",
    rationale: "The human now retains it as sensitivity evidence.",
    actor: "human_expert",
    supersedesDecisionId: deferred.decisionId,
  });
  assert.equal(retained.supersedesDecisionId, deferred.decisionId);
});

test("ResearchStore serializes concurrent mutations across store instances", async () => {
  const runDir = await mkdtemp(join(tmpdir(), "urban-pi-concurrent-"));
  await ResearchStore.initialize(runDir, CONTRACT);
  const stores = Array.from({ length: 12 }, () => new ResearchStore(runDir));
  await Promise.all(stores.map((store, index) => store.openBranch({
    nodeId: `concurrent_${index}`,
    nodeType: "analysis_support",
    title: `Concurrent support ${index}`,
    parentIds: ["research_object"],
    decisionQuestion: `Should support ${index} be retained?`,
    parameters: { analysis_support_m: 200 + index * 50 },
    claimBoundary: "Sensitivity evidence only.",
  })));

  const raw = await readFile(join(runDir, "research_state.json"), "utf8");
  const parsed = JSON.parse(raw);
  for (let index = 0; index < stores.length; index += 1) {
    assert.ok(parsed.nodes[`concurrent_${index}`], `missing concurrent_${index}`);
  }
  const events = (await readFile(join(runDir, "research_events.jsonl"), "utf8"))
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line));
  assert.equal(events.filter((event) => event.type === "branch_opened").length, stores.length);
});

test("runtime-authenticated human patch survives before inference and invalidates stale claim approval", async () => {
  const runDir = await mkdtemp(join(tmpdir(), "urban-pi-auth-patch-"));
  const store = await ResearchStore.initialize(runDir, CONTRACT);
  await store.openBranch({
    nodeId: "gwr_800_fixed_12km",
    nodeType: "model_route",
    title: "800 m fixed-distance GWR at 12 km",
    decisionQuestion: "What evidential role should this route have?",
    claimBoundary: "Sensitivity evidence only.",
  });
  const deferred = await store.recordHumanDecision({
    branchIds: ["gwr_800_fixed_12km"], decision: "defer", rationale: "Await interpretation.", actor: "legacy_human",
  });
  const approval = await store.recordHumanDecision({
    branchIds: ["gwr_800_fixed_12km"], decision: "approve_claim", rationale: "Approve old bounded claim.", actor: "legacy_human",
  });
  const text = "Keep the executed 800 m fixed-distance GWR at 12 km as sensitivity evidence only; do not promote it to the main route.";
  const parsed = parseExplicitHumanPatch(text, await store.load());
  assert.ok(parsed);
  assert.deepEqual(parsed.targetBranchIds, ["gwr_800_fixed_12km"]);
  assert.equal(parsed.expectedSupersedesDecisionId, deferred.decisionId);
  const pending = await store.persistPendingHumanPatch({
    actorId: "signed_user_17", source: "rpc", sourceMessageHash: parsed.sourceMessageHash,
    targetBranchIds: parsed.targetBranchIds, proposedDecision: parsed.proposedDecision,
    expectedSupersedesDecisionId: parsed.expectedSupersedesDecisionId, rawTextDigest: parsed.rawTextDigest,
  });
  await assert.rejects(() => store.setPhase("finalize", "gwr_800_fixed_12km"), /human patch|pending/);
  await assert.rejects(() => store.setPhase("plan", "gwr_800_fixed_12km"), /before leaving the human phase/);
  await assert.rejects(() => store.finalize("Premature claim."), /blocked by authenticated human patch/);
  await assert.rejects(() => store.recordHumanDecision({
    branchIds: ["gwr_800_fixed_12km"], decision: "retain_sensitivity", rationale: text,
    actor: pending.actorId, actorProvenance: "runtime_authenticated", sourcePatchId: pending.patchId,
    sourceMessageHash: pending.sourceMessageHash,
  }), /requires supersedes_decision_id|must supersede/);
  const retained = await store.recordHumanDecision({
    branchIds: ["gwr_800_fixed_12km"], decision: "retain_sensitivity", rationale: text,
    actor: pending.actorId, actorProvenance: "runtime_authenticated", sourcePatchId: pending.patchId,
    sourceMessageHash: pending.sourceMessageHash, supersedesDecisionId: deferred.decisionId,
  });
  const state = await store.load();
  assert.equal(retained.actor, "signed_user_17");
  assert.equal(retained.actorProvenance, "runtime_authenticated");
  assert.equal(state.pendingHumanPatches?.[0]?.status, "applied");
  assert.equal(state.humanDecisions.find((decision) => decision.decisionId === approval.decisionId)?.invalidatedByDecisionId, retained.decisionId);
  assert.equal(state.humanDecisions.some((decision) => decision.decision === "approve_claim" && !decision.invalidatedAt), false);
  await assert.rejects(() => store.finalize("Still premature."), /Reviewer decision|current claim approval/);
});

test("runtime human decision rejects actor or target tampering", async () => {
  const runDir = await mkdtemp(join(tmpdir(), "urban-pi-auth-tamper-"));
  const store = await ResearchStore.initialize(runDir, CONTRACT);
  await store.openBranch({ nodeId: "route_a", nodeType: "model_route", title: "A", decisionQuestion: "Role?", claimBoundary: "Association." });
  const patch = await store.persistPendingHumanPatch({
    actorId: "signed_user", source: "test", sourceMessageHash: "abc", targetBranchIds: ["route_a"],
    proposedDecision: "retain_sensitivity", rawTextDigest: "retain route_a",
  });
  await assert.rejects(() => store.recordHumanDecision({
    branchIds: ["route_a"], decision: "retain_sensitivity", rationale: "retain", actor: "model_claimed_human",
    actorProvenance: "runtime_authenticated", sourcePatchId: patch.patchId, sourceMessageHash: "abc",
  }), /actor does not match/);
});
