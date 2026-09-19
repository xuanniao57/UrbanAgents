import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { ResearchStore, type CommitRouteFamilyInput } from "../src/core/research-store.js";
import { CONTRACT } from "./fixtures.js";
import extension from "../src/pi-extension.js";

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

test("opening a GWR follow-up clears the old frontier and allows evidence registration", async () => {
  const run = await mkdtemp(join(tmpdir(), "urban-gwr-followup-"));
  const store = await ResearchStore.initialize(run, CONTRACT);
  const family = await store.commitRouteFamily(FAMILY);
  const branch = await store.openBranch({
    nodeType: "parameter_route", title: "Fixed GWR 7 and 8 km",
    parentIds: [family.family.nodeId], decisionQuestion: "Does bandwidth change local associations?",
    claimBoundary: "Association only", parameters: { bandwidths_m: [7000, 8000] },
  });
  const opened = await store.load();
  assert.equal(opened.activeBranchId, branch.nodeId);
  assert.equal(opened.activeFrontier, undefined);
  await writeFile(join(run, "gwr.py"), "print('GWR')\n");
  await writeFile(join(run, "gwr.csv"), "scale_m,bandwidth_m,beta\n200,7000,0.3\n");
  const artifacts = [
    { role: "script", path: "gwr.py", summary: "GWR code" },
    { role: "result_table", path: "gwr.csv", summary: "Local coefficients" },
  ];
  await assert.rejects(() => store.commitRun({ branchId: family.active.nodeId, artifacts }), /current route/);
  await store.commitRun({ branchId: branch.nodeId, artifacts });
  const committed = await store.load();
  assert.equal(committed.nodes[branch.nodeId].artifactIds.length, 2);
  assert.equal(committed.nodes[family.active.nodeId].artifactIds.length, 0);
  assert.equal(committed.nodes[branch.nodeId].status, "executed");
  assert.equal(committed.reviews.length, 0);
});

test("switching focus never transfers the previous route's stop condition", async () => {
  const run = await mkdtemp(join(tmpdir(), "urban-focus-switch-"));
  const store = await ResearchStore.initialize(run, CONTRACT);
  const family = await store.commitRouteFamily(FAMILY);
  await store.setPhase("execute", family.active.nodeId);
  assert.equal((await store.load()).activeFrontier?.stopCondition, FAMILY.stopCondition);
  await store.setPhase("execute", family.candidates[1].nodeId);
  const switched = await store.load();
  assert.equal(switched.activeBranchId, family.candidates[1].nodeId);
  assert.equal(switched.activeFrontier, undefined);
});

test("public commit tool registers a standalone GWR route without a synthetic family", async () => {
  const run = await mkdtemp(join(tmpdir(), "urban-gwr-public-tool-"));
  const keys = ["URBAN_PI_RUN_DIR", "URBAN_PI_WORKSPACE_ROOT"] as const;
  const previous = keys.map(key => process.env[key]);
  try {
    process.env.URBAN_PI_RUN_DIR = run;
    process.env.URBAN_PI_WORKSPACE_ROOT = run;
    const store = await ResearchStore.initialize(run, CONTRACT);
    await store.commitRouteFamily(FAMILY);
    const route = await store.openBranch({ nodeType: "parameter_route", title: "GWR follow-up", decisionQuestion: "Compare 7 and 8 km", claimBoundary: "Association" });
    await writeFile(join(run, "gwr.py"), "print('done')\n");
    await writeFile(join(run, "gwr.csv"), "scale_m,beta\n200,0.1\n");
    const registered: any[] = [];
    extension({ on() {}, registerTool(t: any) { registered.push(t); }, appendEntry() {}, setActiveTools() {}, setSessionName() {} } as any);
    const receipt = await registered.find(t => t.name === "urban_commit_run").execute("regression", {
      script_path: "gwr.py", result_path: "gwr.csv", summary: "Saved local coefficients",
    });
    assert.ok(!receipt.isError);
    const state = await store.load();
    assert.equal(state.nodes[route.nodeId].artifactIds.length, 2);
    assert.equal(state.phase, "review");
    assert.equal(state.reviews.length, 0);
  } finally {
    keys.forEach((key, i) => { if (previous[i] === undefined) delete process.env[key]; else process.env[key] = previous[i]; });
  }
});

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

  const zeroByteCsv = join(run, "zero.csv");
  await writeFile(zeroByteCsv, "", "utf8");
  for (const invalid of [join(run, "missing.csv"), zeroByteCsv]) {
    await assert.rejects(() => store.commitRun({
      branchId: family.active.nodeId,
      artifacts: [
        { role: "analysis_script", path: script, summary: "code" },
        { role: "result_table", path: invalid, summary: "invalid" },
      ],
    }), /ENOENT|missing or empty/);
  }

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

test("coefficient routes accept different table layouts without approving their science", async () => {
  const run = await mkdtemp(join(tmpdir(), "urban-coefficient-contract-"));
  const store = await ResearchStore.initialize(run, {
    ...CONTRACT,
    covariates: CONTRACT.covariates.map((name) => `${name}：研究变量的定义说明`),
  });
  const family = await store.commitRouteFamily({
    ...FAMILY,
    stopCondition: "Commit coefficients for every contract covariate across the scale sweep.",
  });
  const script = join(run, "analysis.py");
  const longTable = join(run, "ols_coefficients.csv");
  const localTable = join(run, "gwr_coefficients.csv");
  const metrics = join(run, "metrics.csv");
  await writeFile(script, "print('ok')\n", "utf8");
  await writeFile(longTable, `scale_m,variable,coefficient\n${CONTRACT.covariates.map((name) => `200,${name},0.1`).join("\n")}\n`, "utf8");
  await writeFile(localTable, `cell_id,scale_m,bandwidth_m,intercept,${CONTRACT.covariates.join(",")}\n1,200,7000,0.2,${CONTRACT.covariates.map(() => "0.1").join(",")}\n`, "utf8");
  await writeFile(metrics, "scale_m,n_samples,r2\n200,10,0.2\n", "utf8");
  const committed = await store.commitRun({
    branchId: family.active.nodeId,
    artifacts: [
      { role: "analysis_script", path: script, summary: "code" },
      { role: "result_table", path: longTable, summary: "OLS long-form coefficients" },
      { role: "result_table", path: localTable, summary: "Local coefficients by cell" },
      { role: "metrics_table", path: metrics, summary: "Auxiliary fit statistics" },
    ],
  });
  assert.equal(committed.length, 4);
  assert.ok(committed.every((artifact) => /^[a-f0-9]{64}$/.test(artifact.sha256)));
  const state = await store.load();
  assert.equal(state.nodes[family.active.nodeId].status, "executed");
  assert.equal(state.phase, "review");
  assert.equal(state.activeFrontier?.status, "committed");
  assert.equal(state.reviews.length, 0, "Registration must not imply scientific approval");
});
