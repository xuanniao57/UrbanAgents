import assert from "node:assert/strict";
import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { ContextCompiler } from "../src/core/context-compiler.js";
import { recallResearchState } from "../src/core/context-memory.js";
import { resolveCompactionSettings } from "../src/core/model-context.js";
import { ResearchStore } from "../src/core/research-store.js";
import type { ResearchContract } from "../src/core/types.js";

const runDir = await mkdtemp(join(tmpdir(), "urban-context-stress-"));
const contract: ResearchContract = {
  researchQuestion: "How do spatial support and process scale change a held-out urban relationship?",
  boundary: "Synthetic common urban boundary",
  observationWindow: "Fixed two-day window",
  population: "Observed devices only",
  outcome: "Log activity intensity",
  covariates: ["building_density", "poi_density", "road_density", "function_entropy"],
  candidateSupports: ["200 m", "300 m", "400 m", "500 m", "600 m", "700 m", "800 m"],
  intendedClaim: "Within-city scale sensitivity under shared construction and held-out geography.",
  prohibitedClaims: ["causal effect", "universally optimal scale", "population-wide inference"],
  crs: "EPSG:32651",
  gridOrigin: "shared 100 m-aligned origin",
  validationGeography: "five common macro-regions",
};
const store = await ResearchStore.initialize(runDir, contract);
for (let index = 0; index < 48; index += 1) {
  await store.openBranch({
    nodeId: `route_${String(index).padStart(2, "0")}`,
    nodeType: "model_route",
    title: `${200 + (index % 7) * 100} m ${index % 3 === 0 ? "OLS" : "GWR"} route ${index}`,
    parentIds: ["research_object"],
    decisionQuestion: `Does route ${index} preserve comparable held-out evidence?`,
    parameters: {
      support_m: 200 + (index % 7) * 100,
      model: index % 3 === 0 ? "OLS" : "GWR",
      bandwidth_fraction: index % 3 === 0 ? null : 0.1 + (index % 5) * 0.05,
    },
    claimBoundary: "Synthetic sensitivity evidence only.",
    summary: "Repeated branch used to stress bounded context compilation without truncating authoritative state.",
  });
}
await store.setPhase("execute", "route_47");
const state = await store.load();
const compiler = new ContextCompiler();
const windows = [4_096, 8_192, 16_384, 32_768, 131_072];
const reports = windows.map((contextWindow) => {
  const maxOutputTokens = Math.max(1_024, Math.min(16_384, Math.floor(contextWindow * 0.2)));
  const packet = compiler.compile(state, { contextWindow, maxOutputTokens });
  assert.ok(packet.estimatedTokens <= packet.budget.stateBudget, `${contextWindow}: packet exceeded state budget`);
  assert.equal(packet.activePath.at(-1)?.nodeId, "route_47");
  return {
    contextWindow,
    maxOutputTokens,
    compaction: resolveCompactionSettings(contextWindow, maxOutputTokens),
    profile: packet.budget.profile,
    fidelity: packet.fidelity,
    estimatedTokens: packet.estimatedTokens,
    stateBudget: packet.budget.stateBudget,
    injectedTreeNodes: packet.recoveryCapsule.treeOutline.length,
    omittedTreeNodes: packet.recoveryCapsule.omittedTreeNodes,
  };
});

const omittedRecall = recallResearchState(state, {
  scope: "branch",
  ids: ["route_00"],
  detail: "card",
  dependencyDepth: 1,
  tokenLimit: 1_200,
});
assert.match(JSON.stringify(omittedRecall.records), /route_00/);
assert.match(JSON.stringify(omittedRecall.records), /support_m/);
const firstSummary = compiler.compactionSummary(state, { contextWindow: 8_192, maxOutputTokens: 2_048 });
const secondSummary = compiler.compactionSummary(state, { contextWindow: 8_192, maxOutputTokens: 2_048 });
assert.equal(firstSummary, secondSummary, "compaction must rebuild deterministically from state, not summarize a prior summary");

console.log(JSON.stringify({
  success: true,
  runDir,
  stateVersion: state.stateVersion,
  branchCount: Object.keys(state.nodes).length,
  reports,
  omittedRecallRecords: omittedRecall.records.length,
  deterministicSummary: true,
}, null, 2));
