import type { WorkflowPhase } from "./types.js";

const CORE = ["urban_state", "urban_recall"];

export function bootstrapTools(delegation: boolean): string[] {
  return ["read", "bash", "edit", "write", "urban_initialize", ...(delegation ? ["urban_delegate"] : [])];
}

export const PHASE_TOOL_POLICY: Record<WorkflowPhase, string[]> = {
  plan: ["urban_initialize", ...CORE, "urban_commit_route_family"],
  execute: [...CORE, "urban_commit_run"],
  review: [...CORE, "urban_record_review"],
  human: [...CORE, "urban_human_decision"],
  finalize: ["urban_state", "urban_recall", "urban_finalize"],
  complete: ["urban_state"],
};

export function activeToolsForPhase(phase: WorkflowPhase, allTools: string[]): string[] {
  const allowed = new Set(PHASE_TOOL_POLICY[phase]);
  return allTools.filter((name) => allowed.has(name));
}

export function isToolAllowed(phase: WorkflowPhase, toolName: string): boolean {
  return PHASE_TOOL_POLICY[phase].includes(toolName);
}
