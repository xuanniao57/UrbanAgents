import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { createHash } from "node:crypto";
import { FAIR_PROTOCOL } from "../src/core/fair-module-evaluation.js";

import { ResearchStore } from "../src/core/research-store.js";
import type { ResearchNode, WorkflowState } from "../src/core/types.js";

const args = parseArgs(process.argv.slice(2));
if (!args.task || !args.runDir) {
  throw new Error("Usage: prepare-module-ablation-fixture.ts --task plan|reviewer|context --run-dir <path> [--source-run <completed-run>]");
}

const root = resolve(process.cwd());
const sourceRun = resolve(args.sourceRun ?? resolve(root, "..", "experiments", "case2_multiscale_gwr_20260815", "pi_runtime_v2_20260824_final"));
const runDir = resolve(args.runDir);
await mkdir(runDir, { recursive: true });
const sourceState = JSON.parse(await readFile(resolve(sourceRun, "research_state.json"), "utf8")) as WorkflowState;
const fair = args.protocol === FAIR_PROTOCOL;
let fairRoute: Record<string, string> | undefined;
let fairSource: string | undefined;
if (fair) {
  if (!["plan", "reviewer"].includes(args.task)) throw new Error("Fair protocol supports plan/reviewer only");
  const current = resolve(root, "..", "experiments", "case2_multiscale_aoi_corrected_20260830", "outputs");
  const currentManifest = JSON.parse(await readFile(resolve(current, "experiment_manifest.json"), "utf8"));
  sourceState.contract = {
    researchQuestion: "How do observed built-environment–activity relationships vary with spatial scale?",
    boundary: currentManifest.scope.aoi,
    observationWindow: currentManifest.scope.temporal_window,
    population: currentManifest.scope.population,
    outcome: currentManifest.scope.outcome,
    covariates: currentManifest.scope.covariates,
    candidateSupports: currentManifest.analysis_unit_scales_m.map((m: number) => `${m} m`),
    intendedClaim: "Sample-conditional spatial associations and scale sensitivity for human interpretation",
    prohibitedClaims: ["causal effects", "universal optimal scale", "resident-population representativeness"],
    crs: currentManifest.comparability_contract.crs,
    gridOrigin: JSON.stringify(currentManifest.comparability_contract.common_grid_origin_m),
    validationGeography: currentManifest.comparability_contract.validation,
  };
  fairSource = resolve(current, "scale_bandwidth_model_results.csv");
  const csv = await readFile(fairSource, "utf8");
  // This controlled numeric evidence table has no quoted fields. Fail rather than silently misparse another format.
  if (csv.includes('"')) throw new Error("Unsupported quoted CSV in fair fixture");
  const [header, ...rows] = csv.trim().split(/\r?\n/).map((line) => line.split(","));
  const matches = rows.map((row) => Object.fromEntries(header.map((key, i) => [key, row[i]])))
    .filter((row) => row.scale_m === "700" && row.kernel === "adaptive_bisquare" && Number(row.bandwidth_fraction) === 0.1);
  if (matches.length !== 1) throw new Error("Expected exactly one corrected 700m/10% evidence row");
  fairRoute = matches[0];
  await writeFile(resolve(runDir, "common_task_evidence.json"), JSON.stringify({
    contract: sourceState.contract,
    ...(args.task === "reviewer" ? {
      source: "AOI-corrected scale_bandwidth_model_results.csv, 700m adaptive 10% row",
      sourceSha256: createHash("sha256").update(csv).digest("hex"),
      route: fairRoute,
      evidenceScope: "OOF predictions and local numerical diagnostics across held-out regions. Full-sample coefficient maps and their stability are not provided in this task.",
    } : {}),
  }, null, 2), "utf8");
}

if (args.task === "plan") {
  await ResearchStore.initialize(runDir, sourceState.contract);
  await manifest({ task: args.task, baselineHumanDecisions: 0, expectedPhase: "plan" });
} else if (args.task === "reviewer") {
  const store = await ResearchStore.initialize(runDir, sourceState.contract);
  await store.openBranch({
    nodeId: "gwr_700_adaptive_10_review",
    nodeType: "model_route",
    parentIds: ["research_object"],
    title: "700 m adaptive GWR at 10% neighbours",
    decisionQuestion: fair ? "What does this evidence establish for predictive transfer and local relationship exploration?" : "Does the narrow adaptive neighbourhood support a stable held-out local interpretation?",
    parameters: {
      analysis_support_m: 700,
      model: "GWR",
      kernel: "adaptive_bisquare",
      bandwidth_fraction: 0.1,
      common_covariate_count: 8,
      validation_geography: "five shared held-out macro-regions",
    },
    claimBoundary: fair ? "Separate predictive-transfer claims from descriptive local relationships; human interpretation is pending." : "No local interpretation unless held-out transfer and local conditioning are adequate.",
    summary: "Route prepared for an independent Reviewer gate.",
  });
  await store.setPhase("execute", "gwr_700_adaptive_10_review");
  const evidence = resolve(root, "..", "deliverables", "UrbanAgent_Scale_Eval_20260821_v4", "evaluation", "data", "evidence", "adaptive", "scale_bandwidth_model_results.csv");
  await store.attachEvidence({
    branchId: "gwr_700_adaptive_10_review",
    role: "held_out_transfer_and_conditioning",
    path: fairSource ?? evidence,
    summary: "Route-specific adaptive GWR evidence for the 700 m, 10% neighbour specification.",
    mediaType: "text/csv",
    metrics: fairRoute ? Object.fromEntries(Object.entries(fairRoute).map(([key, value]) => [key, value !== "" && Number.isFinite(Number(value)) ? Number(value) : value])) : {
      oof_r2: -4.032080624027466,
      oof_rmse: 1.9147300661133793,
      median_local_condition_number: 45.5165110797794,
      p90_local_condition_number: 86.97569187089911,
      neighbour_count_median: 22,
    },
  });
  await store.setPhase("review", "gwr_700_adaptive_10_review");
  await manifest({ task: args.task, baselineHumanDecisions: 0, expectedPhase: "review" });
} else if (args.task === "context") {
  const state = structuredClone(sourceState);
  const timestamp = new Date().toISOString();
  state.runDir = runDir;
  state.runId = `${state.runId}_context_ablation`;
  state.phase = "human";
  state.activeBranchId = "gwr_800_fixed_12km";
  delete state.finalClaim;
  delete state.finalizedAt;
  state.nodes.research_object.status = "active";
  for (let index = 0; index < 44; index += 1) {
    const nodeId = `archived_route_${String(index).padStart(2, "0")}`;
    const support = 200 + (index % 7) * 100;
    const model = index % 3 === 0 ? "OLS" : "GWR";
    const node: ResearchNode = {
      nodeId,
      nodeType: "model_route",
      title: `${support} m ${model} archived comparison ${index}`,
      parentIds: ["research_object"],
      status: index % 5 === 0 ? "deferred" : "blocked",
      decisionQuestion: `Archived comparison ${index}: should this route be recalled?`,
      parameters: {
        analysis_support_m: support,
        model,
        bandwidth_fraction: model === "GWR" ? 0.1 + (index % 5) * 0.05 : null,
      },
      claimBoundary: "Archived comparison; do not use without indexed recall.",
      summary: "Distractor branch used to stress structure-aware context recovery.",
      artifactIds: [],
      createdAt: timestamp,
      updatedAt: timestamp,
    };
    state.nodes[nodeId] = node;
  }
  state.stateVersion = (state.stateVersion ?? 0) + 1;
  state.updatedAt = timestamp;
  await writeFile(resolve(runDir, "research_state.json"), JSON.stringify(state, null, 2), "utf8");
  await writeFile(resolve(runDir, "research_events.jsonl"), "", "utf8");
  await manifest({
    task: args.task,
    baselineHumanDecisions: state.humanDecisions.length,
    expectedPhase: "human",
    stressNodeCount: Object.keys(state.nodes).length,
  });
} else {
  throw new Error(`Unknown task: ${args.task}`);
}

console.log(JSON.stringify({ task: args.task, runDir, sourceRun }, null, 2));

async function manifest(extra: Record<string, unknown>): Promise<void> {
  await writeFile(resolve(runDir, "fixture_manifest.json"), JSON.stringify({ sourceRun: fairSource ?? sourceRun, protocol: args.protocol ?? "legacy", runDir, ...extra }, null, 2), "utf8");
}

function parseArgs(values: string[]): { task?: string; runDir?: string; sourceRun?: string; protocol?: string } {
  const parsed: Record<string, string> = {};
  for (let index = 0; index < values.length; index += 1) {
    const key = values[index];
    if (!key.startsWith("--")) continue;
    parsed[key.slice(2)] = values[index + 1] ?? "";
    index += 1;
  }
  return { task: parsed.task, runDir: parsed["run-dir"], sourceRun: parsed["source-run"], protocol: parsed.protocol };
}
