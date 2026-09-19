import { readFile, writeFile, mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { randomUUID } from "node:crypto";
import { FAIR_PROTOCOL, makeBlindBundle, validateJudge, type ModuleTask } from "../src/core/fair-module-evaluation.js";

const [run, out, judgement] = process.argv.slice(2);
if (!run || !out) throw new Error("Usage: prepare-fair-module-judge.ts <run-dir> <new-blind-dir> [judge-result.json]");
const runDir = resolve(run);
const manifest = JSON.parse(await readFile(resolve(runDir, "run_manifest.json"), "utf8"));
if (manifest.protocol !== FAIR_PROTOCOL || !["plan", "reviewer"].includes(manifest.task)) throw new Error("Only freshly executed task-semantic-v1 plan/reviewer runs are admissible");
const prompt = await readFile(resolve(runDir, "task_prompt.txt"), "utf8");
const answer = await readFile(resolve(runDir, "assistant_output.txt"), "utf8");
const bundle = makeBlindBundle(manifest.task as ModuleTask, prompt, answer);
// Conditions and state-derived mechanism counts are deliberately absent from judge.json.
await mkdir(resolve(out));
await writeFile(resolve(out, "judge.json"), JSON.stringify(bundle, null, 2), "utf8");
const score = judgement ? validateJudge(bundle, JSON.parse(await readFile(resolve(judgement), "utf8"))) : null;
await writeFile(resolve(runDir, "semantic_evaluation.json"), JSON.stringify({
  protocol: FAIR_PROTOCOL, bundleId: randomUUID(), evidenceHash: bundle.evidenceHash,
  status: judgement ? "judged_pending_human_audit" : "awaiting_independent_judge",
  taskQualityScore: score, maximum: 8, runtimeExitCode: manifest.exitCode,
  executionSuccess: manifest.exitCode === 0,
  // Failure is reported separately; a missing judge is NOT a zero-quality observation.
  needsSecondJudge: true,
}, null, 2), "utf8");
console.log(JSON.stringify({ status: judgement ? "judged_pending_human_audit" : "awaiting_independent_judge", taskQualityScore: score }));
