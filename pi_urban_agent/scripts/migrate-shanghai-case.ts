import { access, copyFile, mkdir, readFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { ResearchStore } from "../src/core/research-store.js";

const projectRoot = resolve(process.cwd(), "..");
const caseRoot = resolve(projectRoot, "experiments", "case2_multiscale_gwr_20260815");
const outputRoot = join(caseRoot, "outputs");
const fixedRoot = join(caseRoot, "outputs_fixed_distance");
const runDir = resolve(process.argv[2] || join(caseRoot, `pi_runtime_v2_${new Date().toISOString().replaceAll(/[-:.TZ]/g, "").slice(0, 14)}`));

try {
  await access(join(runDir, "research_state.json"));
  throw new Error(`Refusing to overwrite existing Pi research state: ${runDir}`);
} catch (error) {
  if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
}

const rows = parseCsv(await readFile(join(outputRoot, "scale_bandwidth_model_results.csv"), "utf8"));
const fixedRows = parseCsv(await readFile(join(fixedRoot, "fixed_distance_gwr_results.csv"), "utf8"));
const find = (source: Record<string, string>[], predicate: (row: Record<string, string>) => boolean) => {
  const row = source.find(predicate);
  if (!row) throw new Error("Expected result row was not found.");
  return row;
};
const ols800 = find(rows, (row) => row.scale_m === "800" && row.model === "OLS");
const adaptive300 = find(rows, (row) => row.scale_m === "300" && row.model === "GWR adaptive 30%");
const narrow700 = find(rows, (row) => row.scale_m === "700" && row.model === "GWR adaptive 10%");
const fixed800 = find(fixedRows, (row) => row.scale_m === "800" && row.bandwidth_m === "12000");

const store = await ResearchStore.initialize(runDir, {
  researchQuestion: "How can Urban Agent structure and audit spatial-scale sensitivity in a Shanghai street-vitality analysis?",
  boundary: "Shanghai inner-ring study area",
  observationWindow: "fixed two-day device-event sample used by the multiscale experiment",
  population: "observed anonymized device users; not the resident population",
  outcome: "log-transformed grid-level stay intensity reconstructed at each support",
  covariates: [
    "building_density", "building_coverage_ratio", "mean_building_height", "building_volume_proxy",
    "building_function_entropy", "poi_density", "poi_type_entropy", "road_density",
  ],
  candidateSupports: ["200 m", "300 m", "400 m", "500 m", "600 m", "700 m", "800 m"],
  intendedClaim: "Scale-conditioned predictive associations and reviewed model roles within the observed Shanghai setting.",
  prohibitedClaims: ["causal effect", "universal optimal scale", "population-wide representativeness", "complete MAUP solution"],
  crs: "EPSG:32651",
  gridOrigin: "shared 100 m-aligned origin",
  validationGeography: "five shared macro-regions held out consistently across supports",
});

await store.openBranch({
  nodeId: "ols_800_global",
  nodeType: "model_route",
  title: "800 m OLS global baseline",
  parentIds: ["research_object"],
  decisionQuestion: "Which global route provides the strongest held-out transfer under the common scale contract?",
  parameters: { model: "OLS", role: "global_baseline", analysis_support_m: 800, validation: "shared_five_macro_regions" },
  claimBoundary: "Global, within-city association; not a local or causal mechanism.",
  summary: `OOF R2 ${Number(ols800.oof_r2).toFixed(4)}; candidate main global route.`,
});
await store.openBranch({
  nodeId: "gwr_300_adaptive_30",
  nodeType: "model_route",
  title: "300 m adaptive GWR at 30% neighbours",
  parentIds: ["research_object"],
  decisionQuestion: "Does a local model provide stable scale-sensitivity evidence?",
  parameters: { model: "GWR", role: "local_sensitivity", analysis_support_m: 300, kernel: "adaptive_bisquare", bandwidth_fraction: 0.30 },
  claimBoundary: "Local sensitivity evidence only; not the unique correct bandwidth or mechanism.",
  summary: `OOF R2 ${Number(adaptive300.oof_r2).toFixed(4)}; p90 condition number max ${Number(adaptive300.p90_local_condition_number_max).toFixed(2)}.`,
});
await store.openBranch({
  nodeId: "gwr_700_adaptive_10_blocked",
  nodeType: "parameter_route",
  title: "700 m adaptive GWR at 10% neighbours",
  parentIds: ["research_object"],
  decisionQuestion: "Should a narrow adaptive neighbourhood be admitted?",
  parameters: { model: "GWR", role: "instability_probe", analysis_support_m: 700, kernel: "adaptive_bisquare", bandwidth_fraction: 0.10 },
  claimBoundary: "No downstream claim if held-out transfer is negative or local conditioning is unstable.",
  summary: `OOF R2 ${Number(narrow700.oof_r2).toFixed(4)}; p90 condition number max ${Number(narrow700.p90_local_condition_number_max).toFixed(2)}.`,
});
await store.openBranch({
  nodeId: "gwr_800_fixed_12km",
  nodeType: "parameter_route",
  title: "800 m fixed-distance GWR at 12 km",
  parentIds: ["research_object"],
  decisionQuestion: "Does a fixed physical-distance neighbourhood change the local-model judgement?",
  parameters: { model: "GWR", role: "requested_comparison", analysis_support_m: 800, kernel: "fixed_distance_bisquare", bandwidth_m: 12000 },
  claimBoundary: "Comparison evidence pending substantive human interpretation.",
  summary: `OOF R2 ${Number(fixed800.oof_r2).toFixed(4)}; fixed-distance comparison executed after expert request.`,
});

await store.setPhase("execute", "ols_800_global");
const adaptiveMatrix = join(outputRoot, "scale_bandwidth_model_results.csv");
const predictions = join(outputRoot, "scale_bandwidth_oof_predictions.csv");
const fixedMatrix = join(fixedRoot, "fixed_distance_gwr_results.csv");
const evidenceDir = join(runDir, "evidence");
await mkdir(evidenceDir, { recursive: true });
const portableAdaptiveMatrix = join(evidenceDir, "scale_bandwidth_model_results.csv");
const portablePredictions = join(evidenceDir, "scale_bandwidth_oof_predictions.csv");
const portableFixedMatrix = join(evidenceDir, "fixed_distance_gwr_results.csv");
await copyFile(adaptiveMatrix, portableAdaptiveMatrix);
await copyFile(predictions, portablePredictions);
await copyFile(fixedMatrix, portableFixedMatrix);
await store.attachEvidence({ branchId: "ols_800_global", role: "held_out_model_matrix", path: portableAdaptiveMatrix, summary: "Full OLS and adaptive-GWR matrix across 200--800 m using common macro folds.", metrics: { oof_r2: Number(ols800.oof_r2), scale_m: 800 } });
await store.attachEvidence({ branchId: "gwr_300_adaptive_30", role: "held_out_model_matrix", path: portableAdaptiveMatrix, summary: "Adaptive-GWR scale-by-bandwidth evidence matrix.", metrics: { oof_r2: Number(adaptive300.oof_r2), scale_m: 300, bandwidth_fraction: 0.30 } });
await store.attachEvidence({ branchId: "gwr_300_adaptive_30", role: "out_of_fold_predictions", path: portablePredictions, summary: "Out-of-fold predictions used for transfer and residual diagnostics." });
await store.attachEvidence({ branchId: "gwr_700_adaptive_10_blocked", role: "instability_evidence", path: portableAdaptiveMatrix, summary: "Narrow-bandwidth route with negative transfer and high condition number.", metrics: { oof_r2: Number(narrow700.oof_r2), p90_condition_number_max: Number(narrow700.p90_local_condition_number_max) } });
await store.attachEvidence({ branchId: "gwr_800_fixed_12km", role: "fixed_distance_comparison", path: portableFixedMatrix, summary: "Fixed physical-distance GWR comparison requested by the human expert.", metrics: { oof_r2: Number(fixed800.oof_r2), bandwidth_m: 12000 } });

await store.setPhase("review", "ols_800_global");
await store.recordReview({ branchId: "ols_800_global", decision: "proceed", checks: { common_contract: "pass", shared_holdout: "pass", model_role: "pass" }, rationale: "Admit as the global main-route candidate because its role and held-out evidence are explicit.", affectedClaims: ["global association"] });
await store.recordReview({ branchId: "gwr_300_adaptive_30", decision: "proceed", checks: { common_contract: "pass", shared_holdout: "pass", conditioning: "pass" }, rationale: "Retain as local scale-sensitivity evidence; do not rank it as a universal optimum.", affectedClaims: ["local sensitivity"] });
await store.recordReview({ branchId: "gwr_700_adaptive_10_blocked", decision: "block", checks: { held_out_transfer: "fail", conditioning: "fail" }, rationale: "Negative held-out R2 and elevated local condition numbers block downstream synthesis.", affectedClaims: ["narrow-bandwidth local interpretation"], requiredAction: "Widen the neighbourhood or retain the route as a documented negative result." });
await store.recordReview({ branchId: "gwr_800_fixed_12km", decision: "escalate", checks: { executed: "pass", shared_holdout: "pass", substantive_scale_meaning: "unknown" }, rationale: "The fixed-distance route is technically competitive, but its 12 km process scale requires human urban-theory interpretation.", affectedClaims: ["local-process scale"], requiredAction: "Human expert should decide whether to retain the fixed-distance result as sensitivity evidence." });

await store.setPhase("human", "ols_800_global");
await store.recordHumanDecision({ branchIds: ["ols_800_global"], decision: "select_main", rationale: "Use the transparent global baseline as the main route for the current claim.", actor: "human_expert", resultingClaimBoundary: "Global, within-city predictive association only." });
await store.recordHumanDecision({ branchIds: ["gwr_300_adaptive_30"], decision: "retain_sensitivity", rationale: "Retain the stable adaptive local route to show model-process-scale sensitivity.", actor: "human_expert", resultingClaimBoundary: "Sensitivity evidence, not the unique bandwidth." });
await store.recordHumanDecision({ branchIds: ["gwr_700_adaptive_10_blocked"], decision: "block", rationale: "Preserve the failed narrow-bandwidth route as negative evidence.", actor: "human_expert", resultingClaimBoundary: "No local interpretation from this route." });
await store.recordHumanDecision({ branchIds: ["gwr_800_fixed_12km"], decision: "defer", rationale: "The executed fixed-distance comparison remains available, but substantive adoption needs further expert discussion.", actor: "human_expert", resultingClaimBoundary: "Do not use it to claim a uniquely preferred process scale." });
await store.recordHumanDecision({ branchIds: ["ols_800_global", "gwr_300_adaptive_30", "gwr_800_fixed_12km"], decision: "approve_claim", rationale: "Approve the bounded cross-scale synthesis while retaining disagreement and deferred evidence.", actor: "human_expert", resultingClaimBoundary: "Sample-conditional, within-city scale sensitivity; no causal, population-wide, or universal-optimum claim." });

const final = await store.finalize(
  "Under a common data and held-out-geography contract, estimated street-vitality associations and transfer performance vary across analysis supports and model-process scales. The 800 m OLS route is retained as the global main route, the 300 m adaptive GWR route as local sensitivity evidence, unstable narrow-bandwidth routes are blocked, and the competitive 12 km fixed-distance route remains deferred for substantive expert interpretation.",
);
console.log(JSON.stringify({ success: true, runDir, submissionPath: final.submissionPath, frontendPath: final.frontendPath, viewerPath: final.viewerPath, manifestPath: final.manifestPath }, null, 2));

function parseCsv(text: string): Record<string, string>[] {
  const [headerLine, ...lines] = text.trim().split(/\r?\n/);
  const headers = headerLine.split(",");
  return lines.map((line) => {
    const values = line.split(",");
    return Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""]));
  });
}
