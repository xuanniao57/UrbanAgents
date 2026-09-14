import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import test from "node:test";

test("context scorer separates provenance from semantic quality without a global 40 percent cap", async () => {
  const root = resolve(import.meta.dirname, "..");
  const resultsRoot = await mkdtemp(resolve(tmpdir(), "urban-score-policy-"));
  const runDir = resolve(resultsRoot, "synthetic_model", "context__synthetic__r01");
  runTsx(root, "scripts/prepare-module-ablation-fixture.ts", ["--task", "context", "--run-dir", runDir]);

  const fixture = JSON.parse(await readFile(resolve(runDir, "fixture_manifest.json"), "utf8")) as Record<string, any>;
  const statePath = resolve(runDir, "research_state.json");
  const state = JSON.parse(await readFile(statePath, "utf8")) as Record<string, any>;
  const prior = state.humanDecisions.find((decision: Record<string, any>) =>
    decision.branchIds.includes("gwr_800_fixed_12km") && decision.decision === "defer",
  );
  state.nodes.gwr_800_fixed_12km.status = "retained_sensitivity";
  state.pendingQuestions = [];
  state.humanDecisions.push({
    decisionId: "human_synthetic_untrusted",
    branchIds: ["gwr_800_fixed_12km"],
    decision: "retain_sensitivity",
    rationale: "Keep this as sensitivity evidence, not the main route.",
    actor: "model_supplied_actor",
    actorProvenance: "legacy_import",
    supersedesDecisionId: prior.decisionId,
    resultingClaimBoundary: "Within-city and sample-conditional; no causal claim and no uniquely optimal scale claim.",
    createdAt: new Date().toISOString(),
  });
  await writeFile(statePath, JSON.stringify(state, null, 2), "utf8");

  const response = [
    "Main ols_800_global: 800 m OLS, selected main, held-out R2 0.5336.",
    "Sensitivity gwr_300_adaptive_30: 300 m adaptive GWR 30%, retained sensitivity, held-out R2 0.4256.",
    "Blocked gwr_700_adaptive_10_blocked: 700 m adaptive GWR 10%, blocked, held-out R2 -4.032.",
    "Fixed gwr_800_fixed_12km: 800 m fixed-distance GWR 12 km, held-out R2 0.5375; retain as sensitivity, not main.",
    "The result is within-city and sample-conditional. It does not support a causal claim or a uniquely optimal scale.",
  ].join("\n");
  await writeFile(resolve(runDir, "assistant_output.txt"), response, "utf8");
  await writeFile(resolve(runDir, "run_manifest.json"), JSON.stringify({
    label: "synthetic_model", task: "context", condition: "synthetic", repeat: 1,
    runtimeSeconds: 1, exitCode: 0, compaction: {}, baselineHumanDecisions: fixture.baselineHumanDecisions,
  }, null, 2), "utf8");

  runTsx(root, "scripts/score-module-ablation.ts", ["--results-root", resultsRoot]);
  const summary = JSON.parse(await readFile(resolve(resultsRoot, "score_summary.json"), "utf8")) as Record<string, any>;
  const row = summary.runs[0];
  assert.equal(row.provenance_score, 0);
  assert.ok(row.semantic_score > 0);
  assert.ok(row.state_cleanup_score >= 0);
  assert.ok(row.claim_calibration_score > 0);
  assert.ok(row.percent > 40, `expected separated category scoring without cap, got ${row.percent}`);
  assert.equal(row.invalid_human_patch_flag, true);
});

test("an unapplied required patch is incomplete, not a corrupted human mutation", async () => {
  const root = resolve(import.meta.dirname, "..");
  const resultsRoot = await mkdtemp(resolve(tmpdir(), "urban-score-incomplete-"));
  const runDir = resolve(resultsRoot, "synthetic_model", "context__synthetic__r01");
  runTsx(root, "scripts/prepare-module-ablation-fixture.ts", ["--task", "context", "--run-dir", runDir]);
  await writeFile(resolve(runDir, "assistant_output.txt"), "", "utf8");
  await writeFile(resolve(runDir, "run_manifest.json"), JSON.stringify({
    label: "synthetic_model", task: "context", condition: "synthetic", repeat: 1,
    runtimeSeconds: 540, exitCode: 124, compaction: {},
  }, null, 2), "utf8");

  runTsx(root, "scripts/score-module-ablation.ts", ["--results-root", resultsRoot]);
  const summary = JSON.parse(await readFile(resolve(resultsRoot, "score_summary.json"), "utf8")) as Record<string, any>;
  const row = summary.runs[0];
  assert.equal(row.invalid_human_patch_flag, false);
  assert.equal(row.provenance_score, 0);
  assert.equal(row.state_cleanup_score, 0);
  assert.equal(row.exit_code, 124);
});

function runTsx(root: string, script: string, args: string[]): void {
  const result = spawnSync(process.execPath, [resolve(root, "node_modules", "tsx", "dist", "cli.mjs"), resolve(root, script), ...args], {
    cwd: root,
    encoding: "utf8",
    windowsHide: true,
  });
  assert.equal(result.status, 0, `${script} failed:\n${result.stdout}\n${result.stderr}`);
}
