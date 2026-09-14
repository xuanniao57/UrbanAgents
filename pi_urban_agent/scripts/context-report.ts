import { writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { ContextCompiler } from "../src/core/context-compiler.js";
import { ResearchStore } from "../src/core/research-store.js";
import { URBAN_AGENT_SYSTEM_PROMPT } from "../src/core/system-prompt.js";
import { PHASE_TOOL_POLICY } from "../src/core/tool-policy.js";
import type { WorkflowPhase } from "../src/core/types.js";
import { estimateTokens } from "../src/core/utils.js";

const runDir = resolve(process.argv[2] || "");
if (!process.argv[2]) throw new Error("Usage: npm run context:report -- <run-dir> [comma-separated-context-windows]");
const requested = process.argv[3] || process.env.URBAN_CONTEXT_REPORT_WINDOWS || "4096,8192,16384,40960,131072,262144";
const windows = [...new Set(requested.split(",").map((value) => Number.parseInt(value.trim(), 10)).filter((value) => Number.isFinite(value) && value > 0))];
if (!windows.length) throw new Error("No valid context windows were supplied.");

const state = await new ResearchStore(runDir).load();
const compiler = new ContextCompiler();
const phases: WorkflowPhase[] = ["plan", "execute", "review", "human", "finalize", "complete"];
const modelProfiles = windows.map((contextWindow) => {
  const maxOutputTokens = Math.min(16_384, Math.max(1_024, Math.floor(contextWindow * 0.2)));
  const phaseReports = Object.fromEntries(phases.map((phase) => {
    const packet = compiler.compile(state, { phase, contextWindow, maxOutputTokens });
    return [phase, {
      activeTools: PHASE_TOOL_POLICY[phase],
      activeToolCount: PHASE_TOOL_POLICY[phase].length,
      contextProfile: packet.budget.profile,
      contextFidelity: packet.fidelity,
      stateBudget: packet.budget.stateBudget,
      statePacketEstimatedTokens: packet.estimatedTokens,
      omissions: packet.omissions,
      activePathNodes: packet.activePath.length,
      siblingSummaries: packet.siblingSummaries.length,
      evidenceRecords: packet.evidence.length,
      reviewRecords: packet.reviews.length,
      humanDecisionRecords: packet.humanDecisions.length,
    }];
  }));
  const sample = compiler.compile(state, { contextWindow, maxOutputTokens });
  return { contextWindow, maxOutputTokens, profile: sample.budget.profile, budget: sample.budget, phaseReports };
});

const report = {
  schemaVersion: "2.1",
  runId: state.runId,
  policy: "model-metadata-driven adaptive budgeting; no model-name special cases",
  systemPromptCharacters: URBAN_AGENT_SYSTEM_PROMPT.length,
  systemPromptEstimatedTokens: estimateTokens(URBAN_AGENT_SYSTEM_PROMPT),
  modelProfiles,
  oldRuntimeComparison: {
    formerPromptAndMemoryCharactersApprox: 35_619,
    formerPromptAndMemoryTokensApprox: 8_905,
    formerAllToolSchemaCharactersApprox: 21_306,
    formerAllToolSchemaTokensApprox: 5_326,
  },
};
const path = join(runDir, "context_budget_report.json");
await writeFile(path, JSON.stringify(report, null, 2), "utf8");
console.log(JSON.stringify({
  success: true,
  path,
  profiles: modelProfiles.map(({ contextWindow, profile, phaseReports }) => ({
    contextWindow,
    profile,
    completeFidelity: (phaseReports.complete as { contextFidelity: string }).contextFidelity,
  })),
}, null, 2));
