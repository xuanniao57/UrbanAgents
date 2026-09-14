import { readdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

import type { HumanDecisionRecord, ResearchNode, ReviewRecord, WorkflowState } from "../src/core/types.js";

const args = parseArgs(process.argv.slice(2));
if (!args.resultsRoot) throw new Error("Usage: score-module-ablation.ts --results-root <dir>");
const resultsRoot = resolve(args.resultsRoot);
const manifests = await findFiles(resultsRoot, "run_manifest.json");
const detailRows: Record<string, unknown>[] = [];
const summaryRows: Record<string, unknown>[] = [];

for (const manifestPath of manifests) {
  const runDir = resolve(manifestPath, "..");
  const manifest = JSON.parse(await readFile(manifestPath, "utf8")) as Record<string, any>;
  if (manifest.protocol === "task-semantic-v1") throw new Error("Refusing implementation-based scoring for task-semantic-v1. Use prepare-fair-module-judge.ts; primary quality scores require an independent judge.");
  const fixture = JSON.parse(await readFile(resolve(runDir, "fixture_manifest.json"), "utf8")) as Record<string, any>;
  const state = JSON.parse(await readFile(resolve(runDir, "research_state.json"), "utf8")) as WorkflowState;
  const output = (await readFile(resolve(runDir, "assistant_output.txt"), "utf8")).toLowerCase();
  const recallTrace = manifest.task === "context" ? await loadRecallTrace(runDir) : "";
  const tokenUsage = manifest.task === "context" ? await loadTokenUsage(runDir) : { input: 0, output: 0, total: 0 };
  const evidenceText = `${output}\n${recallTrace}`;
  const scores = manifest.task === "plan"
    ? scorePlan(state)
    : manifest.task === "reviewer"
      ? scoreReviewer(state, output)
      : scoreContext(state, output, evidenceText, Number(fixture.baselineHumanDecisions ?? 0));
  const possible = scores.length;
  const total = scores.reduce((sum, item) => sum + item.score, 0);
  const unknownRouteIds = [...output.matchAll(/\b(?:ols|gwr)_[a-z0-9_]+\b/g)]
    .map((match) => match[0])
    .filter((id) => !state.nodes[id] && !Object.keys(state.nodes).some((known) => known.startsWith(id)));
  const prohibitedClaim = hasUnqualifiedProhibitedClaim(output);
  const invalidHumanPatch = manifest.task === "context"
    ? humanPatchDiagnostics(state, Number(fixture.baselineHumanDecisions ?? 0)).severe
    : false;
  const hasIngressPatch = manifest.task === "context"
    && (state.pendingHumanPatches ?? []).some((patch) => ["pending_unclassified", "pending", "applied"].includes(patch.status));
  const failureStage = Number(manifest.exitCode) === 0 ? "completed"
    : Number(manifest.exitCode) === 124 && !manifest.compaction ? (hasIngressPatch ? "inference_or_tools" : "compaction")
      : Number(manifest.exitCode) === 124 ? "inference_or_tools"
        : "runtime_error";
  const categoryScore = (category: string) => scores
    .filter((item) => item.category === category)
    .reduce((sum, item) => sum + item.score, 0);
  const runId = runDir.slice(resultsRoot.length + 1).replaceAll("\\", "/");
  const authenticatedPatchSuccess = manifest.task === "context"
    ? hasAuthenticatedPatchSuccess(state, Number(fixture.baselineHumanDecisions ?? 0))
    : false;
  for (const item of scores) detailRows.push({ run_id: runId, model: manifest.label, task: manifest.task, condition: manifest.condition, ...item });
  summaryRows.push({
    run_id: runId,
    model: manifest.label,
    task: manifest.task,
    condition: manifest.condition,
    repeat: manifest.repeat ?? 1,
    score: total,
    possible,
    percent: possible ? 100 * total / possible : 0,
    semantic_score: categoryScore("semantic"),
    provenance_score: categoryScore("provenance"),
    state_cleanup_score: categoryScore("state_cleanup"),
    claim_calibration_score: categoryScore("claim_calibration"),
    runtime_seconds: manifest.runtimeSeconds,
    input_tokens: tokenUsage.input,
    output_tokens: tokenUsage.output,
    total_tokens: tokenUsage.total,
    exit_code: manifest.exitCode,
    failure_stage: failureStage,
    unknown_route_ids: [...new Set(unknownRouteIds)].join(";"),
    prohibited_claim_flag: prohibitedClaim,
    invalid_human_patch_flag: invalidHumanPatch,
    authenticated_patch_success: authenticatedPatchSuccess,
  });
}

await writeFile(resolve(resultsRoot, "checkpoint_scores.csv"), toCsv(detailRows), "utf8");
await writeFile(resolve(resultsRoot, "run_scores.csv"), toCsv(summaryRows), "utf8");
await writeFile(resolve(resultsRoot, "score_summary.json"), JSON.stringify({ generatedAt: new Date().toISOString(), runs: summaryRows }, null, 2), "utf8");
const groupSummary = aggregateGroups(summaryRows);
await writeFile(resolve(resultsRoot, "paper_table_group_summary.csv"), toCsv(groupSummary), "utf8");
await writeFile(resolve(resultsRoot, "paper_table_group_summary.json"), JSON.stringify({ generatedAt: new Date().toISOString(), groups: groupSummary }, null, 2), "utf8");
console.log(JSON.stringify({
  runs: summaryRows.length,
  groups: groupSummary.length,
  resultsRoot,
  summary: resolve(resultsRoot, "run_scores.csv"),
  paperTable: resolve(resultsRoot, "paper_table_group_summary.csv"),
}, null, 2));

function scorePlan(state: WorkflowState) {
  const nodes = Object.values(state.nodes).filter((node) => node.nodeId !== "research_object");
  const text = JSON.stringify(nodes).toLowerCase();
  const supports = new Set(nodes.map((node) => Number(node.parameters.analysis_support_m ?? node.parameters.support_m)).filter(Number.isFinite));
  const hasScaleLanguage = /scale|support|resolution|spatial unit/.test(text);
  const p1 = nodes.length > 0 && hasScaleLanguage ? 1 : nodes.length > 0 ? 0.5 : 0;
  const common = /common|shared|inherit|same/.test(text) && /covariate|holdout|macro|crs|origin/.test(text);
  const p2 = supports.size >= 2 && common ? 1 : supports.size >= 2 ? 0.5 : 0;
  const hasOls = nodes.some((node) => /ols/i.test(`${node.title} ${JSON.stringify(node.parameters)}`));
  const hasGwr = nodes.some((node) => /gwr/i.test(`${node.title} ${JSON.stringify(node.parameters)}`));
  const hasAdaptive = /adaptive|neighbou?r/.test(text);
  const hasFixed = /fixed.distance|distance_m|kilomet|km/.test(text);
  const p3 = hasOls && hasGwr && hasAdaptive && hasFixed ? 1 : hasOls && hasGwr ? 0.5 : 0;
  const executable = nodes.filter((node) => Object.keys(node.parameters ?? {}).length > 0 && node.claimBoundary?.length > 10).length;
  const p4 = executable > 0 && state.phase === "execute" ? 1 : executable > 0 ? 0.5 : 0;
  return rows([["P1", p1, `nodes=${nodes.length}; scale_language=${hasScaleLanguage}`], ["P2", p2, `supports=${[...supports].join("|")}; common_contract=${common}`], ["P3", p3, `OLS=${hasOls}; GWR=${hasGwr}; adaptive=${hasAdaptive}; fixed=${hasFixed}`], ["P4", p4, `executable_nodes=${executable}; phase=${state.phase}`]], "semantic");
}

function scoreReviewer(state: WorkflowState, output: string) {
  const branch = state.nodes.gwr_700_adaptive_10_review;
  const reviews = state.reviews.filter((review) => review.branchId === branch?.nodeId);
  const review = reviews.at(-1);
  const artifact = branch?.artifactIds.map((id) => state.artifacts[id]).find(Boolean);
  const preparedPacket = /reviewer packet|prepare.review|artifact.*sha|sha.?256/.test(output);
  const r1 = preparedPacket && artifact?.sha256 && typeof artifact.metrics?.oof_r2 === "number" ? 1 : preparedPacket && artifact ? 0.5 : 0;
  const reviewText = JSON.stringify(review ?? {}).toLowerCase();
  const r2 = /oof|out.of.fold|held.out|transfer/.test(reviewText) ? 1 : review ? 0.5 : 0;
  const catchesMetric = /-4\.03|negative/.test(reviewText);
  const catchesConditioning = /condition|ill.condition|unstable/.test(reviewText);
  const badDecision = review && ["block", "repair", "new_branch", "escalate"].includes(review.decision);
  const r3 = badDecision && catchesMetric && catchesConditioning ? 1 : badDecision && (catchesMetric || catchesConditioning) ? 0.5 : 0;
  const changed = branch && ["blocked", "needs_revision", "conditional"].includes(branch.status);
  const action = Boolean(review?.requiredAction && review.affectedClaims.length);
  const r4 = changed && action ? 1 : changed || action ? 0.5 : 0;
  return rows([["R1", r1, artifact ? `packet=${preparedPacket}; artifact=${artifact.artifactId}; sha256=${artifact.sha256.slice(0, 12)}` : "missing artifact"], ["R2", r2, review ? `review=${review.reviewId}` : "missing review"], ["R3", r3, `decision=${review?.decision ?? "missing"}; metric=${catchesMetric}; conditioning=${catchesConditioning}`], ["R4", r4, `status=${branch?.status}; required_action=${Boolean(review?.requiredAction)}; affected_claims=${review?.affectedClaims.length ?? 0}`]], "semantic");
}

function scoreContext(state: WorkflowState, output: string, evidenceText: string, baselineHumanDecisions: number) {
  const c1a = exactRoute(evidenceText, "ols_800_global", ["0.5336", "0.534"], ["main", "selected"]);
  const c1b = exactRoute(evidenceText, "gwr_300_adaptive_30", ["0.4256", "0.426"], ["sensitivity", "retained"]);
  const c1 = 0.5 * c1a + 0.5 * c1b;
  const c2a = exactRoute(evidenceText, "gwr_700_adaptive_10_blocked", ["-4.032", "-4.03"], ["block"]);
  const c2b = exactRoute(evidenceText, "gwr_800_fixed_12km", ["0.5375", "0.538"], ["defer", "fixed"]);
  const c2 = 0.5 * c2a + 0.5 * c2b;
  const added = state.humanDecisions.slice(baselineHumanDecisions);
  const patch = added.find((decision) => decision.branchIds.includes("gwr_800_fixed_12km"));
  const hp1 = patch?.decision === "retain_sensitivity" && patch.branchIds.length === 1 ? 1 : patch ? 0.5 : 0;
  const pendingPatch = patch?.sourcePatchId
    ? (state.pendingHumanPatches ?? []).find((candidate) => candidate.patchId === patch.sourcePatchId)
    : undefined;
  const hp2 = patch?.actorProvenance === "runtime_authenticated"
    && Boolean(patch.sourcePatchId && patch.sourceMessageHash)
    && pendingPatch?.status === "applied"
    && pendingPatch.actorId === patch.actor
    && pendingPatch.sourceMessageHash === patch.sourceMessageHash ? 1 : 0;
  const previousRouteDecision = state.humanDecisions.slice(0, baselineHumanDecisions).find((decision) =>
    decision.branchIds.includes("gwr_800_fixed_12km") && decision.decision === "defer",
  );
  const approvalInvalidated = state.humanDecisions.slice(0, baselineHumanDecisions)
    .filter((decision) => decision.decision === "approve_claim")
    .every((decision) => Boolean(decision.invalidatedAt && decision.invalidatedByDecisionId === patch?.decisionId));
  const noRelatedPendingQuestion = !state.pendingQuestions.some((question) => /gwr_800_fixed_12km|fixed.distance|12.?km/i.test(question));
  const sc1Parts = [
    Boolean(patch && previousRouteDecision && patch.supersedesDecisionId === previousRouteDecision.decisionId),
    pendingPatch?.status === "applied",
    approvalInvalidated,
    noRelatedPendingQuestion,
  ];
  const sc1 = sc1Parts.filter(Boolean).length / sc1Parts.length;
  const boundaryEvidence = `${output}\n${patch?.rationale ?? ""}\n${patch?.resultingClaimBoundary ?? ""}`.toLowerCase();
  const bounded = /within.city|within city|sample.conditional|sample conditional/.test(boundaryEvidence);
  const rejectsCausal = rejectsCausalClaim(boundaryEvidence);
  const rejectsUniversal = rejectsUniversalClaim(boundaryEvidence);
  const cc1 = bounded && rejectsCausal && rejectsUniversal ? 1 : [bounded, rejectsCausal, rejectsUniversal].filter(Boolean).length >= 2 ? 0.5 : 0;
  const adaptiveWindow = routeWindow(output, "gwr_300_adaptive_30");
  const blockedWindow = routeWindow(output, "gwr_700_adaptive_10_blocked");
  const fixedWindow = routeWindow(output, "gwr_800_fixed_12km");
  const semanticCorruption = /ordinance line service|ordinary line service/.test(output)
    || /all (?:four|five|\d+)?\s*(?:proposed )?(?:models?|routes?|candidates?|route evaluations?).{0,90}(?:failed|rejected|not admitted|rejection)/.test(output)
    || /14%|0\.14|5,?000.{0,12}8,?000/.test(adaptiveWindow)
    || /13%|0\.13|fixed bandwidth/.test(blockedWindow)
    || /(?:main route|main_route_selected)/.test(fixedWindow);
  // Absence of a final response is not positive evidence of semantic safety.
  const c5 = output.trim().length ? (semanticCorruption ? 0 : 1) : 0;
  return [
    ...rows([["C1", c1, `main=${c1a}; sensitivity=${c1b}`], ["C2", c2, `blocked=${c2a}; deferred=${c2b}`], ["C5", c5, `semantic_corruption=${semanticCorruption}`]], "semantic"),
    ...rows([["HP1", hp1, patch ? `decision=${patch.decision}; branches=${patch.branchIds.join("|")}` : "missing new human patch"]], "semantic"),
    ...rows([["HP2", hp2, `actor=${patch?.actor ?? "missing"}; provenance=${patch?.actorProvenance ?? "missing"}; source_patch=${patch?.sourcePatchId ?? "missing"}`]], "provenance"),
    ...rows([["SC1", sc1, `supersede=${sc1Parts[0]}; patch_applied=${sc1Parts[1]}; approval_invalidated=${sc1Parts[2]}; pending_cleared=${sc1Parts[3]}`]], "state_cleanup"),
    ...rows([["CC1", cc1, `bounded=${bounded}; rejects_causal=${rejectsCausal}; rejects_universal=${rejectsUniversal}`]], "claim_calibration"),
  ];
}

function hasUnqualifiedProhibitedClaim(output: string): boolean {
  const causal = /causal effect|causally/.test(output)
    && !rejectsCausalClaim(output);
  const universal = /universal(?:ly)? optimal|unique(?:ly)? (?:best|correct|optimal) scale/.test(output)
    && !rejectsUniversalClaim(output);
  return causal || universal;
}

function rejectsCausalClaim(output: string): boolean {
  return /no causal|not causal|without.{0,24}causal|avoid.{0,40}causal|does not (?:assert|establish|support).{0,24}causal|reject(?:s|ed|ing)? causal|causal.{0,80}(?:explicitly )?reject|causal (?:inference|claim|effect).{0,40}(?:not supported|not permitted)|cannot claim causal|do not claim causal/.test(output);
}

function rejectsUniversalClaim(output: string): boolean {
  return /no universal|not universal|without.{0,40}(?:universal|unique(?:ly)? optimal)|avoid.{0,50}(?:universal|unique(?:ly)? optimal)|does not (?:assert|establish|support).{0,50}(?:universal|unique(?:ly)? optimal)|reject(?:s|ed|ing)? universal|universal.{0,80}(?:explicitly )?reject|none.{0,40}universal(?:ly)? optimal|no unique|not unique|do not claim.{0,40}optimal|without.{0,40}unique(?:ly)? correct/.test(output);
}

function humanPatchDiagnostics(state: WorkflowState, baselineHumanDecisions: number): { severe: boolean } {
  const added = state.humanDecisions.slice(baselineHumanDecisions);
  const target = added.filter((decision) => decision.branchIds.includes("gwr_800_fixed_12km"));
  // Failure to complete the required patch is scored by HP1/SC1, but it is
  // not itself an *invalid* authenticated mutation. Reserve this severe flag
  // for a mutation that was actually written with contradictory semantics or
  // provenance. This keeps "incomplete" distinct from "state corrupted".
  if (!target.length) return { severe: false };
  return { severe: target.length !== 1
    || target[0]?.decision !== "retain_sensitivity"
    || target[0]?.branchIds.length !== 1
    || target[0]?.branchIds[0] !== "gwr_800_fixed_12km"
    || target[0]?.actorProvenance !== "runtime_authenticated" };
}

function hasAuthenticatedPatchSuccess(state: WorkflowState, baselineHumanDecisions: number): boolean {
  const added = state.humanDecisions.slice(baselineHumanDecisions);
  const decision = added.find((candidate) => candidate.branchIds.length === 1
    && candidate.branchIds[0] === "gwr_800_fixed_12km"
    && candidate.decision === "retain_sensitivity");
  if (!decision?.sourcePatchId || !decision.sourceMessageHash || decision.actorProvenance !== "runtime_authenticated") return false;
  const patch = (state.pendingHumanPatches ?? []).find((candidate) => candidate.patchId === decision.sourcePatchId);
  return patch?.status === "applied"
    && patch.actorId === decision.actor
    && patch.sourceMessageHash === decision.sourceMessageHash;
}

function aggregateGroups(rowsValue: Record<string, unknown>[]): Record<string, unknown>[] {
  const groups = new Map<string, Record<string, unknown>[]>();
  for (const row of rowsValue) {
    const key = `${row.model}|||${row.task}|||${row.condition}`;
    const rows = groups.get(key) ?? [];
    rows.push(row);
    groups.set(key, rows);
  }
  const out: Record<string, unknown>[] = [];
  for (const rows of groups.values()) {
    const first = rows[0];
    const stat = (field: string) => meanSd(rows.map((row) => Number(row[field])));
    const total = stat("percent");
    const semantic = stat("semantic_score");
    const provenance = stat("provenance_score");
    const cleanup = stat("state_cleanup_score");
    const claim = stat("claim_calibration_score");
    const tokens = stat("total_tokens");
    const runtime = stat("runtime_seconds");
    out.push({
      model: first.model,
      task: first.task,
      condition: first.condition,
      n: rows.length,
      exit0_n: rows.filter((row) => Number(row.exit_code) === 0).length,
      authenticated_patch_success_n: rows.filter((row) => row.authenticated_patch_success === true).length,
      rule_percent_mean: total.mean,
      rule_percent_sd: total.sd,
      semantic_mean: semantic.mean,
      semantic_sd: semantic.sd,
      provenance_mean: provenance.mean,
      provenance_sd: provenance.sd,
      state_cleanup_mean: cleanup.mean,
      state_cleanup_sd: cleanup.sd,
      claim_calibration_mean: claim.mean,
      claim_calibration_sd: claim.sd,
      total_tokens_mean: tokens.mean,
      total_tokens_sd: tokens.sd,
      runtime_seconds_mean: runtime.mean,
      runtime_seconds_sd: runtime.sd,
      compaction_timeout_n: rows.filter((row) => row.failure_stage === "compaction").length,
      inference_or_tools_timeout_n: rows.filter((row) => row.failure_stage === "inference_or_tools").length,
      runtime_error_n: rows.filter((row) => row.failure_stage === "runtime_error").length,
      invalid_human_patch_n: rows.filter((row) => row.invalid_human_patch_flag === true).length,
      prohibited_claim_n: rows.filter((row) => row.prohibited_claim_flag === true).length,
      unknown_route_id_run_n: rows.filter((row) => Boolean(row.unknown_route_ids)).length,
    });
  }
  return out.sort((a, b) => `${a.model}/${a.condition}`.localeCompare(`${b.model}/${b.condition}`));
}

function meanSd(values: number[]): { mean: number; sd: number } {
  const finite = values.filter(Number.isFinite);
  if (!finite.length) return { mean: Number.NaN, sd: Number.NaN };
  const mean = finite.reduce((sum, value) => sum + value, 0) / finite.length;
  const sd = finite.length > 1
    ? Math.sqrt(finite.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (finite.length - 1))
    : 0;
  return { mean, sd };
}

function exactRoute(output: string, id: string, metrics: string[], roles: string[]): number {
  const windows: string[] = [];
  let offset = 0;
  while (offset < output.length) {
    const idIndex = output.indexOf(id, offset);
    if (idIndex < 0) break;
    windows.push(output.slice(Math.max(0, idIndex - 240), idIndex + 4_000));
    offset = idIndex + id.length;
  }
  if (!windows.length) return 0;
  const window = windows.join("\n");
  const metric = metrics.some((value) => window.includes(value));
  const role = roles.some((value) => window.includes(value));
  return metric && role ? 1 : metric || role ? 0.5 : 0;
}

function routeWindow(output: string, id: string): string {
  const idIndex = output.indexOf(id);
  return idIndex < 0 ? "" : output.slice(Math.max(0, idIndex - 100), idIndex + 520);
}

async function loadRecallTrace(runDir: string): Promise<string> {
  const sessionDir = resolve(runDir, "prepared_session");
  let files: string[] = [];
  try {
    files = await findFilesBySuffix(sessionDir, ".jsonl");
  } catch {
    return "";
  }
  const recalled: string[] = [];
  for (const file of files) {
    for (const line of (await readFile(file, "utf8")).split(/\r?\n/)) {
      if (!line.trim()) continue;
      try {
        const entry = JSON.parse(line) as Record<string, any>;
        const message = entry.message;
        if (message?.role !== "toolResult" || message.toolName !== "urban_recall") continue;
        for (const item of message.content ?? []) if (item?.type === "text" && item.text) recalled.push(String(item.text).toLowerCase());
      } catch {
        // Ignore non-message JSONL records.
      }
    }
  }
  return recalled.join("\n");
}

async function loadTokenUsage(runDir: string): Promise<{ input: number; output: number; total: number }> {
  const sessionDir = resolve(runDir, "prepared_session");
  let files: string[] = [];
  try { files = await findFilesBySuffix(sessionDir, ".jsonl"); } catch { return { input: 0, output: 0, total: 0 }; }
  const sum = { input: 0, output: 0, total: 0 };
  for (const file of files) {
    for (const line of (await readFile(file, "utf8")).split(/\r?\n/)) {
      if (!line.trim()) continue;
      try {
        const entry = JSON.parse(line) as Record<string, any>;
        const usage = entry.type === "compaction" ? entry.usage : entry.message?.role === "assistant" ? entry.message.usage : undefined;
        if (!usage) continue;
        sum.input += Number(usage.input ?? 0);
        sum.output += Number(usage.output ?? 0);
        sum.total += Number(usage.totalTokens ?? usage.total ?? 0);
      } catch { /* Ignore malformed/non-message trace records. */ }
    }
  }
  return sum;
}

function rows(values: Array<[string, number, string]>, category: string) { return values.map(([checkpoint_id, score, evidence]) => ({ checkpoint_id, category, score, evidence })); }

async function findFiles(dir: string, target: string): Promise<string[]> {
  const results: string[] = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const path = resolve(dir, entry.name);
    if (entry.isDirectory()) results.push(...await findFiles(path, target));
    else if (entry.name === target) results.push(path);
  }
  return results;
}

async function findFilesBySuffix(dir: string, suffix: string): Promise<string[]> {
  const results: string[] = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const path = resolve(dir, entry.name);
    if (entry.isDirectory()) results.push(...await findFilesBySuffix(path, suffix));
    else if (entry.name.endsWith(suffix)) results.push(path);
  }
  return results;
}

function toCsv(rowsValue: Record<string, unknown>[]): string {
  if (!rowsValue.length) return "";
  const headers = Object.keys(rowsValue[0]);
  const escape = (value: unknown) => `"${String(value ?? "").replaceAll('"', '""')}"`;
  return `${headers.map(escape).join(",")}\n${rowsValue.map((row) => headers.map((key) => escape(row[key])).join(",")).join("\n")}\n`;
}

function parseArgs(values: string[]): { resultsRoot?: string } {
  const parsed: Record<string, string> = {};
  for (let index = 0; index < values.length; index += 1) {
    const key = values[index];
    if (!key.startsWith("--")) continue;
    parsed[key.slice(2)] = values[index + 1] ?? "";
    index += 1;
  }
  return { resultsRoot: parsed["results-root"] };
}
