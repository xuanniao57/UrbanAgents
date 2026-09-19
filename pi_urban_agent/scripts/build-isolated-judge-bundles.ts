import { createHash } from "node:crypto";
import { mkdir, readdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import type { WorkflowState } from "../src/core/types.js";

const args = parseArgs(process.argv.slice(2));
if (!args.resultsRoot || !args.outputDir) throw new Error("Usage: build-isolated-judge-bundles.ts --results-root <dir> --output-dir <dir>");
const resultsRoot = resolve(args.resultsRoot);
const outputDir = resolve(args.outputDir);
await mkdir(resolve(outputDir, "bundles"), { recursive: true });
const manifests = await findFiles(resultsRoot, "run_manifest.json");
const keyRows: string[] = ["sample_id,model,condition,repeat,run_dir"];

for (const manifestPath of manifests) {
  const runDir = resolve(manifestPath, "..");
  const manifest = JSON.parse(await readFile(manifestPath, "utf8")) as Record<string, any>;
  if (manifest.task !== "context") continue;
  const state = JSON.parse(await readFile(resolve(runDir, "research_state.json"), "utf8")) as WorkflowState;
  const fixture = JSON.parse(await readFile(resolve(runDir, "fixture_manifest.json"), "utf8")) as Record<string, any>;
  const baseline = Number(fixture.baselineHumanDecisions ?? 0);
  const assistant = await safeRead(resolve(runDir, "assistant_output.txt"));
  const newDecisions = state.humanDecisions.slice(baseline).map((decision) => ({
    evidence_id: `D-${decision.decisionId.slice(-8)}`,
    branch_ids: decision.branchIds,
    decision: decision.decision,
    rationale: decision.rationale,
    supersedes_decision_id: decision.supersedesDecisionId,
    resulting_claim_boundary: decision.resultingClaimBoundary,
  }));
  const sampleId = `S-${createHash("sha256").update(runDir).digest("hex").slice(0, 12)}`;
  const routeEvidence = ["ols_800_global", "gwr_300_adaptive_30", "gwr_700_adaptive_10_blocked", "gwr_800_fixed_12km"]
    .map((id, index) => {
      const node = state.nodes[id];
      const routeRoles = new Set(["select_main", "retain_sensitivity", "request_comparison", "defer", "block"]);
      const priorDecision = state.humanDecisions.slice(0, baseline)
        .filter((decision) => decision.branchIds.includes(id) && routeRoles.has(decision.decision))
        .at(-1);
      const currentDecision = state.humanDecisions
        .filter((decision) => decision.branchIds.includes(id) && routeRoles.has(decision.decision) && !decision.invalidatedAt)
        .at(-1);
      return node ? {
        evidence_id: `R${index + 1}`,
        route_id: id,
        final_status: node.status,
        prior_adjudicated_role: priorDecision?.decision ?? null,
        current_adjudicated_role: currentDecision?.decision ?? null,
        parameters: node.parameters,
        metrics: Object.assign({}, ...node.artifactIds.map((artifactId) => state.artifacts[artifactId]?.metrics).filter(Boolean)),
      } : { evidence_id: `R${index + 1}`, route_id: id, missing: true };
    });
  const bundle = {
    schema_version: "1.0",
    sample_id: sampleId,
    evaluation_scope: "Semantic workflow quality only. Identity/authentication provenance is deliberately excluded and is scored by deterministic rules elsewhere.",
    task: {
      requested_actions: [
        "Recover the exact main, adaptive sensitivity, blocked narrow-bandwidth, and deferred fixed-distance routes.",
        "Retain the executed 800 m fixed-distance GWR at 12 km as sensitivity evidence only, without promoting it to main.",
        "End with a within-city, sample-conditional statement that rejects causal and universal-optimal-scale claims.",
      ],
    },
    evidence: [
      { evidence_id: "A1", type: "assistant_response", text: assistant },
      { evidence_id: "D1", type: "new_structured_decisions", records: newDecisions },
      { evidence_id: "R0", type: "authoritative_route_snapshot_after_run", records: routeEvidence },
      { evidence_id: "Q1", type: "pending_questions_after_run", records: state.pendingQuestions },
    ],
  };
  await writeFile(resolve(outputDir, "bundles", `${sampleId}.json`), JSON.stringify(bundle, null, 2), "utf8");
  keyRows.push([sampleId, manifest.label, manifest.condition, manifest.repeat ?? 1, runDir].map(csv).join(","));
}

await writeFile(resolve(outputDir, "sample_key.csv"), `${keyRows.join("\n")}\n`, "utf8");
await writeFile(resolve(outputDir, "JUDGE_RUBRIC.md"), rubric(), "utf8");
await writeFile(resolve(outputDir, "JUDGE_OUTPUT_SCHEMA.json"), JSON.stringify(outputSchema(), null, 2), "utf8");
await writeFile(resolve(outputDir, "ISOLATED_JUDGE_AGENT_PROMPT.md"), judgeAgentPrompt(), "utf8");
console.log(JSON.stringify({ outputDir, samples: keyRows.length - 1 }, null, 2));

function rubric(): string {
  return `# Isolated semantic judge rubric\n\nYou are blind to model and framework identity. Read only one supplied bundle and this rubric. Do not inspect other files. Provenance/authentication is outside scope.\n\nA1 and D1 are agent-produced evidence. R0 is the authoritative reference snapshot used only to verify A1/D1; facts present only in R0 are not an agent accomplishment. Q1 is the post-run unresolved-question state. Empty or missing A1/D1 must not receive completion credit merely because R0 contains the correct answer.\n\nScore 0, 1, or 2 for each dimension:\n\n- J1 route recovery: A1 correctly reports all four routes' ID, spatial support, model/bandwidth, role, and held-out R2 when compared with R0. Partial, tool-only, or absent reporting cannot earn full credit.\n- J2 instruction adherence: D1/current state retains the fixed 800 m/12 km route as sensitivity only, without changing other metrics/routes.\n- J3 state coherence: the new role supersedes the prior defer semantically and unresolved route questions are not presented as settled evidence.\n- J4 claim calibration: A1/final decision language is within-city and sample-conditional, and explicitly rejects causal and universal-optimal-scale claims.\n- J5 uncertainty handling: missing evidence is acknowledged; no route, value, authorization, or completion is invented. A safe request for clarification may earn credit but does not equal task completion.\n\nFor every score cite one or more evidence_id values and give a short reason. Return JSON conforming to JUDGE_OUTPUT_SCHEMA.json, including confidence in [0,1] and an uncertainty note. Do not infer condition or model identity.`;
}

function outputSchema() {
  return { sample_id: "string", dimensions: [{ id: "J1..J5", score: "0|1|2", evidence_ids: ["A1"], reason: "string", confidence: "0..1" }], total: "0..10", severe_semantic_errors: ["string"], uncertainty: "string" };
}

function judgeAgentPrompt(): string {
  return `# Isolated-context semantic judge task

You are an independent evaluator in a fresh context. You must not inspect the source repository, run histories, conversations, condition/model labels, deterministic scores, or sample_key.csv.

The only permitted inputs are:

1. JUDGE_RUBRIC.md
2. JUDGE_OUTPUT_SCHEMA.json
3. one JSON file at a time from bundles/

For each bundle, evaluate only the semantic quality and claim calibration defined by the rubric. Identity, authentication, hashes, and runtime provenance are deliberately out of scope and remain governed by deterministic checks. Treat R0 only as a reference used to verify A1/D1. Do not award agent-completion credit for facts that appear only in R0.

Write one unwrapped JSON object per bundle to raw_outputs/<sample_id>.json. Preserve the exact sample_id. Every J1--J5 item must cite evidence IDs, include a short reason and confidence, and the top-level object must include total, severe_semantic_errors, and uncertainty. Do not infer or mention which model or framework produced a sample. Process bundles independently; do not rank or compare samples.
`;
}

async function safeRead(path: string): Promise<string> { try { return await readFile(path, "utf8"); } catch { return ""; } }
async function findFiles(dir: string, name: string): Promise<string[]> {
  const results: string[] = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const path = resolve(dir, entry.name);
    if (entry.isDirectory()) results.push(...await findFiles(path, name)); else if (entry.name === name) results.push(path);
  }
  return results;
}
function csv(value: unknown): string { return `"${String(value ?? "").replaceAll('"', '""')}"`; }
function parseArgs(values: string[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (let i = 0; i < values.length; i += 2) out[values[i].replace(/^--/, "")] = values[i + 1] ?? "";
  return { resultsRoot: out["results-root"], outputDir: out["output-dir"] };
}
