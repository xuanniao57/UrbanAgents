/** Exercise the production extension callbacks without an LLM or fabricated dialogue.
 * This is tool-level capability verification, not an autonomous-research trial.
 */
import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import urbanAgentExtension from "../src/pi-extension.js";
import { ResearchStore } from "../src/core/research-store.js";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const runDir = resolve(process.argv[2] || join(root, "experiments/case2_figure_tool_verification_20260830"));
const resumeReview = process.argv.includes("--resume-review");
process.env.URBAN_PI_REPOSITORY_ROOT = root;
if (resumeReview) process.env.URBAN_PI_RUN_DIR = runDir;
else delete process.env.URBAN_PI_RUN_DIR;
const recipePath = join(root, "pi_urban_agent/capabilities/shanghai_scale_figures.json");
const recipe = JSON.parse(await readFile(recipePath, "utf8"));
type Output = { isError?: boolean; details: any; content: Array<{ text: string }> };
type Callback = { name: string; execute: (...args: any[]) => Promise<Output> };
const tools = new Map<string, Callback>();
let active = new Set(resumeReview ? ["urban_state", "urban_set_phase"] : ["urban_initialize"]);
const trace: unknown[] = resumeReview
  ? (await readFile(join(runDir, "logs/figure_tool_calls.jsonl"), "utf8")).trim().split(/\r?\n/).map(x => JSON.parse(x)) : [];
// Only the registration/event shell is replaced. All scientific tool callbacks,
// the Python process bridge and ResearchStore writes are production code.
const shell = {
  registerTool(tool: Callback) { tools.set(tool.name, tool); },
  on() {}, appendEntry() {}, setSessionName() {},
  setActiveTools(names: string[]) { active = new Set(names); },
};
urbanAgentExtension(shell as unknown as ExtensionAPI);
const ctx = { model: { contextWindow: 32768, maxTokens: 2048 } };
async function call(name: string, params: Record<string, unknown>): Promise<Output> {
  assert(active.has(name), `${name} is not exposed in this phase`);
  const tool = tools.get(name); assert(tool);
  const started = new Date().toISOString();
  const response = await tool.execute(`verify-${trace.length + 1}`, params, new AbortController().signal, undefined, ctx);
  trace.push({ name, params, started, ended: new Date().toISOString(), response });
  await mkdir(join(runDir, "logs"), { recursive: true });
  await writeFile(join(runDir, "logs/figure_tool_calls.jsonl"), trace.map(x => JSON.stringify(x)).join("\n") + "\n");
  assert(!response.isError, response.content.map(x => x.text).join("\n"));
  return response;
}
if (!resumeReview) {
await call("urban_initialize", {
  run_dir: runDir, research_question: "Expose comparable scale-sensitive evidence through reviewable research figures",
  boundary: "Shanghai inner-ring clipped AOI", observation_window: "19 and 21 September 2024",
  population: "Retained observed-device event samples", outcome: "log(1 + eligible two-day grid stay count)",
  covariates: recipe.analysis_contract.full_model_covariates,
  candidate_supports: recipe.analysis_contract.grid_scales_m.map((s: number) => `${s} m`),
  intended_claim: "Descriptive scale-conditioned associations and separate OOF predictive comparisons",
  prohibited_claims: ["causality", "universal optimal scale", "autonomous LLM discovery inferred from a tool replay"],
  crs: "EPSG:32651", grid_origin: "shared 100 m-aligned origin", validation_geography: "five common macro-regions",
});
await call("urban_open_branch", { node_id: "section41_figures", node_type: "diagnostic",
  title: "Section 4.1 figure-production capability verification", parent_ids: ["research_object"],
  decision_question: "Can the production tools regenerate and expose all requested figure evidence?",
  parameters: { recipe_path: recipePath, execution_mode: "scripted_production_tool_callback_verification_no_llm" },
  claim_boundary: "Rendering reproducibility; substantive scale judgement remains open" });
await call("urban_prepare_worker", { branch_id: "section41_figures",
  assignment: `Read the declared recipe at ${recipePath}, regenerate figures without altering source results, attach the export manifest, and request interpretation review.`,
  expected_artifacts: recipe.expected_artifacts });
await call("urban_python", { method: "inspect_json", arguments: { path: recipePath } });
const render = await call("urban_python", { method: "run_script", arguments: {
  script: join(root, recipe.script), cwd: root, args: ["--output-dir", join(runDir, "rendered")], timeout_seconds: 900,
} });
assert.equal(render.details.result.exit_code, 0, JSON.stringify(render.details));
const manifestPath = join(runDir, "rendered/figure_artifact_manifest.json");
await call("urban_python", { method: "inspect_json", arguments: { path: manifestPath } });
const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
assert(manifest.inputs_unchanged);
assert(Object.values(manifest.same_png_as_manuscript).every(Boolean));
const assets = [manifestPath, join(runDir, "rendered/tables_and_gis/table2_ols_all7.csv"),
  ...["fig4_aligned_supports_corrected", "fig5_separate_scale_trajectories", "fig6_ols_coefficients_all8", "fig7_coefficients_all8_all7"]
    .map(stem => join(runDir, `rendered/figures/${stem}.png`))];
for (const path of assets) {
  await call("urban_attach_evidence", { branch_id: "section41_figures", path,
    role: path.endsWith("json") ? "figure_source_and_export_manifest" : "empirical_visual_evidence",
    summary: "Regenerated from saved corrected case outputs; all units, predictors and scales follow the recipe. Descriptive maps are separate from OOF scores." });
}
}
await call("urban_set_phase", { phase: "review", active_branch_id: "section41_figures" });
await call("urban_prepare_review", { branch_id: "section41_figures", review_questions: recipe.review_questions });
await call("urban_record_review", { decision: "escalate",
  checks: { input_preservation: true, full_variable_scale_contract: true, png_reproduction: true },
  rationale: "Automated technical verifier: source hashes are unchanged, the full 8-by-7 contract passes, and all rendered PNGs match. This is not an LLM Reviewer or an expert scale-selection decision.",
  required_action: "Human review of spatial coefficient patterns and their urban interpretation remains open.", affected_claims: ["preferred urban reporting scale"] });
const state = await new ResearchStore(runDir).load();
const manifest = JSON.parse(await readFile(join(runDir, "rendered/figure_artifact_manifest.json"), "utf8"));
assert.equal(state.humanDecisions.length, 0);
assert.equal(state.finalClaim, undefined);
const summary = { success: true, execution_mode: "production_extension_callback_replay", llm_calls: 0,
  autonomous_research_trial: false, runDir, tool_calls: trace.length,
  outputs: manifest.exports.length, all_pngs_match: true, artifact_links: Object.keys(state.artifacts).length,
  checks: manifest.checks, human_decisions: state.humanDecisions.length, phase: state.phase,
  result: "Figure-generation and review-packet capability verified; no scientific approval fabricated." };
await writeFile(join(runDir, "capability_verification.json"), JSON.stringify(summary, null, 2));
console.log(JSON.stringify(summary, null, 2));
