import assert from "node:assert/strict";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { callPython } from "../src/bridge/python-bridge.js";
import { ContextCompiler } from "../src/core/context-compiler.js";
import { makeReviewerPacket, makeWorkerPacket } from "../src/core/packets.js";
import { ResearchStore } from "../src/core/research-store.js";

const runDir = await mkdtemp(join(tmpdir(), "urban-pi-smoke-"));
const repositoryRoot = process.cwd();
const store = await ResearchStore.initialize(runDir, {
  researchQuestion: "Can comparable scale branches support a bounded spatial-scale judgement?",
  boundary: "test AOI",
  observationWindow: "fixed test window",
  population: "observed sample",
  outcome: "grid activity",
  covariates: ["building_density", "poi_density"],
  candidateSupports: ["200 m", "500 m", "800 m"],
  intendedClaim: "Scale-conditioned association",
  prohibitedClaims: ["causality", "universal optimal scale"],
  validationGeography: "shared macro-regions",
});
const branch = await store.openBranch({
  nodeId: "ols_800",
  nodeType: "model_route",
  title: "800 m OLS",
  decisionQuestion: "Does the global baseline transfer?",
  parameters: { model: "OLS", analysis_support_m: 800, role: "global_baseline" },
  claimBoundary: "Observed AOI only.",
});
const worker = makeWorkerPacket(await store.load(), { branchId: branch.nodeId, assignment: "Inspect held-out results", expectedArtifacts: ["metrics.csv"] });
assert.equal(worker.branchId, branch.nodeId);
await store.setPhase("execute", branch.nodeId);
const csvPath = join(runDir, "metrics.csv");
await writeFile(csvPath, "support,model,oof_r2\n800,OLS,0.5336\n", "utf8");
const bridge = await callPython("inspect_csv", { path: csvPath }, { repositoryRoot, runDir });
assert.equal(bridge.success, true);
await store.attachEvidence({ branchId: branch.nodeId, role: "held_out_metrics", path: csvPath, summary: "800 m OLS OOF R2 0.5336", metrics: { oof_r2: 0.5336 } });
await store.setPhase("review", branch.nodeId);
const reviewer = makeReviewerPacket(await store.load(), { branchId: branch.nodeId });
assert.equal(reviewer.evidenceManifest.length, 1);
await store.recordReview({ branchId: branch.nodeId, decision: "proceed", checks: { held_out: "pass" }, rationale: "Eligible for human selection." });
await store.setPhase("human", branch.nodeId);
await store.recordHumanDecision({ branchIds: [branch.nodeId], decision: "select_main", rationale: "Best global baseline under the shared contract.", actor: "smoke_test", resultingClaimBoundary: "Observed AOI only." });
await store.recordHumanDecision({ branchIds: [branch.nodeId], decision: "approve_claim", rationale: "Approved bounded claim.", actor: "smoke_test", resultingClaimBoundary: "No causal or universal scale claim." });
const result = await store.finalize("The selected global baseline is retained for this observed setting.");
const packet = new ContextCompiler().compile(result.state);
assert.equal(packet.phase, "complete");
assert.equal(JSON.parse(await readFile(result.submissionPath, "utf8")).checkpoints.C7_persistent_state, true);
console.log(JSON.stringify({ success: true, runDir, submissionPath: result.submissionPath, estimatedContextTokens: packet.estimatedTokens }, null, 2));
