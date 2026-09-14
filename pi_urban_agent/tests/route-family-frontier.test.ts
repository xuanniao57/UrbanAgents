import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { ResearchStore, type CommitRouteFamilyInput } from "../src/core/research-store.js";
import { CONTRACT } from "./fixtures.js";

const FAMILY: CommitRouteFamilyInput = {
  title: "Bounded initial model roles",
  decisionDimension: "model_role",
  decisionQuestion: "Which route should execute first?",
  sharedParameters: { supports_m: [200, 300, 400, 500, 600, 700, 800], predictors: "fixed_eight" },
  candidates: [
    { label: "OLS global baseline", nodeType: "model_route", parameters: { model: "OLS" } },
    { label: "Adaptive GWR comparison", nodeType: "model_route", parameters: { model: "GWR", bandwidth_mode: "adaptive" } },
    { label: "Fixed GWR comparison", nodeType: "model_route", parameters: { model: "GWR", bandwidth_mode: "fixed" } },
  ],
  activeCandidate: "OLS global baseline",
  stopCondition: "Commit one seven-scale OLS result table and its script.",
  expectedArtifacts: ["analysis script", "seven-scale result table"],
};

test("route-family commit is atomic, inherited, bounded and idempotent", async () => {
  const run = await mkdtemp(join(tmpdir(), "urban-route-family-"));
  const store = await ResearchStore.initialize(run, CONTRACT);
  const first = await store.commitRouteFamily(FAMILY);
  const state = await store.load();
  assert.equal(first.idempotent, false);
  assert.equal(Object.keys(state.nodes).length, 5, "root + family + three candidates");
  assert.equal(state.activeBranchId, first.active.nodeId);
  assert.equal(state.activeFrontier?.familyId, first.family.nodeId);
  assert.equal(state.activeFrontier?.branchId, first.active.nodeId);
  assert.equal(state.activeFrontier?.status, "ready");
  assert.equal(state.phase, "execute");
  assert.equal(state.activeFrontier?.stopCondition, FAMILY.stopCondition);
  assert.deepEqual(first.candidates.map((candidate) => candidate.parentIds), [[first.family.nodeId], [first.family.nodeId], [first.family.nodeId]]);
  assert.ok(first.candidates.every((candidate) => candidate.parameters.inherited_contract_hash === state.contractHash));
  assert.equal(Object.values(state.nodes).filter((node) => node.status === "active").length, 1);

  const version = state.stateVersion;
  const second = await store.commitRouteFamily(FAMILY);
  const after = await store.load();
  assert.equal(second.idempotent, true);
  assert.equal(after.stateVersion, version, "idempotent retry must not mutate state");
  assert.equal(Object.keys(after.nodes).length, 5);
});

test("invalid family leaves the Research Tree unchanged", async () => {
  const run = await mkdtemp(join(tmpdir(), "urban-route-invalid-"));
  const store = await ResearchStore.initialize(run, CONTRACT);
  const before = await store.load();
  await assert.rejects(() => store.commitRouteFamily({
    ...FAMILY,
    candidates: [FAMILY.candidates[0], { ...FAMILY.candidates[0] }],
  }), /labels must be unique/);
  await assert.rejects(() => store.commitRouteFamily({
    ...FAMILY,
    candidates: [200, 300, 400, 500, 600, 700, 800].map((scale) => ({
      label: `scale_${scale}m`,
      nodeType: "parameter_route" as const,
      parameters: { grid_resolution_m: scale },
    })),
    activeCandidate: "scale_200m",
  }), /Do not materialize a repeated scale\/bandwidth sweep/);
  await assert.rejects(() => store.commitRouteFamily({
    ...FAMILY,
    candidates: [
      FAMILY.candidates[0],
      ...[200, 300, 400, 500].map((bandwidth) => ({
        label: `fixed_${bandwidth}m`,
        nodeType: "parameter_route" as const,
        parameters: { bandwidth_distance_m: bandwidth },
      })),
      FAMILY.candidates[2],
    ],
  }), /Do not materialize a repeated scale\/bandwidth sweep/);
  await assert.rejects(() => store.commitRouteFamily({
    ...FAMILY,
    candidates: [
      { ...FAMILY.candidates[0], parameters: { model: "OLS", features: ["wrong_subset"] } },
      FAMILY.candidates[1],
    ],
  }), /repeats immutable contract fields/);
  const after = await store.load();
  assert.deepEqual(after.nodes, before.nodes);
  assert.equal(after.stateVersion, before.stateVersion);
});

test("run commit requires real code and nonempty results before review", async () => {
  const run = await mkdtemp(join(tmpdir(), "urban-run-commit-"));
  const store = await ResearchStore.initialize(run, CONTRACT);
  const family = await store.commitRouteFamily(FAMILY);
  const script = join(run, "analysis.py");
  const emptyCsv = join(run, "empty.csv");
  const resultCsv = join(run, "results.csv");
  await writeFile(script, "print('ok')\n", "utf8");
  await writeFile(emptyCsv, "scale_m,r2\n", "utf8");
  await writeFile(resultCsv, "scale_m,r2\n200,0.1\n", "utf8");

  await assert.rejects(() => store.commitRun({
    branchId: family.active.nodeId,
    artifacts: [
      { role: "analysis_script", path: script, summary: "code" },
      { role: "result_table", path: emptyCsv, summary: "empty" },
    ],
  }), /header and at least one data row/);
  let state = await store.load();
  assert.equal(Object.keys(state.artifacts).length, 0, "failed transaction must attach nothing");
  assert.equal(state.phase, "execute");

  await assert.rejects(() => store.recordReview({
    branchId: family.active.nodeId,
    decision: "proceed",
    checks: { integrity: "pass" },
    rationale: "No committed result yet.",
  }), /before a valid run artifact is committed/);

  const artifacts = await store.commitRun({
    branchId: family.active.nodeId,
    artifacts: [
      { role: "analysis_script", path: script, summary: "code" },
      { role: "result_table", path: resultCsv, summary: "result" },
    ],
  });
  assert.equal(artifacts.length, 2);
  state = await store.load();
  assert.equal(state.phase, "review");
  assert.equal(state.activeFrontier?.status, "committed");
  assert.equal(state.nodes[family.active.nodeId].status, "executed");

  await store.recordReview({
    branchId: family.active.nodeId,
    decision: "proceed",
    checks: { integrity: "pass" },
    rationale: "Committed artifacts are reviewable.",
  });
  state = await store.load();
  assert.equal(state.activeFrontier?.status, "reviewed");
  assert.equal(state.phase, "human");
});

test("coefficient routes cannot commit a collapsed or incomplete coefficient table", async () => {
  const run = await mkdtemp(join(tmpdir(), "urban-coefficient-contract-"));
  const store = await ResearchStore.initialize(run, CONTRACT);
  const family = await store.commitRouteFamily({
    ...FAMILY,
    stopCondition: "Commit coefficients for every contract covariate across the scale sweep.",
  });
  const script = join(run, "analysis.py");
  const incomplete = join(run, "incomplete.csv");
  const extra = join(run, "extra.csv");
  const complete = join(run, "complete.csv");
  await writeFile(script, "print('ok')\n", "utf8");
  await writeFile(incomplete, "scale_m,n_samples,r2,coef_building_density\n200,10,0.2,0.1\n", "utf8");
  await assert.rejects(() => store.commitRun({
    branchId: family.active.nodeId,
    artifacts: [
      { role: "analysis_script", path: script, summary: "code" },
      { role: "result_table", path: incomplete, summary: "collapsed" },
    ],
  }), /lacks one scalar coefficient column/);
  const coefficientHeader = CONTRACT.covariates.map((name) => `coef_${name}`).join(",");
  await writeFile(extra, `scale_m,n_samples,r2,${coefficientHeader},coef_uncontracted_predictor\n200,10,0.2,${CONTRACT.covariates.map(() => "0.1").join(",")},0.9\n`, "utf8");
  await assert.rejects(() => store.commitRun({
    branchId: family.active.nodeId,
    artifacts: [
      { role: "analysis_script", path: script, summary: "code" },
      { role: "result_table", path: extra, summary: "extra predictor" },
    ],
  }), /outside the fixed covariate contract/);
  await writeFile(complete, `scale_m,n_samples,r2,${coefficientHeader}\n200,10,0.2,${CONTRACT.covariates.map(() => "0.1").join(",")}\n`, "utf8");
  const committed = await store.commitRun({
    branchId: family.active.nodeId,
    artifacts: [
      { role: "analysis_script", path: script, summary: "code" },
      { role: "result_table", path: complete, summary: "complete coefficients" },
    ],
  });
  assert.equal(committed.length, 2);
});
