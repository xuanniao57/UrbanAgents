import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

import { ResearchStore } from "../src/core/research-store.js";
import type { ResearchContract } from "../src/core/types.js";

const args = parseArgs(process.argv.slice(2));
if (!args.runDir || !args.contract) {
  throw new Error("Usage: initialize-eval-run.ts --run-dir <path> --contract <case_contract.json>");
}

const runDir = resolve(args.runDir);
const contractPath = resolve(args.contract);
const source = JSON.parse(await readFile(contractPath, "utf8")) as Record<string, unknown>;
const validation = (source.validation ?? {}) as Record<string, unknown>;
const supports = Array.isArray(source.analysis_unit_supports_m)
  ? source.analysis_unit_supports_m.map((value) => `${value} m`)
  : [];

const contract: ResearchContract = {
  researchQuestion: String(source.research_question ?? "Review spatial-scale sensitivity in an urban analysis."),
  boundary: String(source.study_boundary ?? "unspecified study boundary"),
  observationWindow: Array.isArray(source.observation_window)
    ? source.observation_window.map(String).join("; ")
    : String(source.observation_window ?? "unspecified observation window"),
  population: "observed sampled-device users represented by model-ready grid cells",
  outcome: String(source.outcome ?? "unspecified outcome"),
  covariates: Array.isArray(source.covariates) ? source.covariates.map(String) : [],
  candidateSupports: supports,
  intendedClaim: "Compare scale-conditioned evidence and assign bounded analytical roles without selecting a universal best scale.",
  prohibitedClaims: Array.isArray(source.prohibited_inferences)
    ? source.prohibited_inferences.map(String)
    : ["causal effect", "universally optimal spatial scale"],
  crs: String(source.coordinate_reference_system ?? ""),
  gridOrigin: String(source.grid_origin ?? ""),
  validationGeography: String(validation.geography ?? validation.method ?? ""),
};

const store = await ResearchStore.initialize(runDir, contract);
const state = await store.load();
await writeFile(
  resolve(runDir, "input_contract_snapshot.json"),
  JSON.stringify({ source_path: contractPath, source, normalized_contract: contract }, null, 2),
  "utf8",
);
console.log(JSON.stringify({ runDir, runId: state.runId, contractHash: state.contractHash }, null, 2));

function parseArgs(values: string[]): { runDir?: string; contract?: string } {
  const parsed: Record<string, string> = {};
  for (let index = 0; index < values.length; index += 1) {
    const key = values[index];
    if (!key.startsWith("--")) continue;
    parsed[key.slice(2)] = values[index + 1] ?? "";
    index += 1;
  }
  return { runDir: parsed["run-dir"], contract: parsed.contract };
}
