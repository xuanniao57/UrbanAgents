import { ContextCompiler } from "./context-compiler.js";
import type { ContextCompileOptions } from "./context-compiler.js";
import { PHASE_TOOL_POLICY } from "./tool-policy.js";
import type { ReviewerPacket, WorkerPacket, WorkflowState } from "./types.js";
import { makeId, nowIso } from "./utils.js";

export function makeWorkerPacket(
  state: WorkflowState,
  input: { branchId: string; assignment: string; expectedArtifacts: string[] } & Pick<ContextCompileOptions, "contextWindow" | "maxOutputTokens" | "profile">,
): WorkerPacket {
  if (!state.nodes[input.branchId]) throw new Error(`Unknown worker branch: ${input.branchId}`);
  const context = new ContextCompiler().compile(state, {
    activeBranchId: input.branchId,
    phase: "execute",
    contextWindow: input.contextWindow,
    maxOutputTokens: input.maxOutputTokens,
    profile: input.profile,
  });
  return {
    packetId: makeId("worker_packet"),
    branchId: input.branchId,
    assignment: input.assignment,
    contractHash: state.contractHash,
    context,
    expectedArtifacts: input.expectedArtifacts,
    allowedToolNames: PHASE_TOOL_POLICY.execute,
    createdAt: nowIso(),
  };
}

export function makeReviewerPacket(
  state: WorkflowState,
  input: { branchId: string; reviewQuestions?: string[] } & Pick<ContextCompileOptions, "contextWindow" | "maxOutputTokens" | "profile">,
): ReviewerPacket {
  if (!state.nodes[input.branchId]) throw new Error(`Unknown reviewer branch: ${input.branchId}`);
  const context = new ContextCompiler().compile(state, {
    activeBranchId: input.branchId,
    phase: "review",
    contextWindow: input.contextWindow,
    maxOutputTokens: input.maxOutputTokens,
    profile: input.profile,
  });
  return {
    packetId: makeId("reviewer_packet"),
    branchId: input.branchId,
    contractHash: state.contractHash,
    context,
    evidenceManifest: Object.values(state.artifacts).filter((artifact) => artifact.branchId === input.branchId),
    reviewQuestions: input.reviewQuestions ?? [
      "Does the branch inherit the immutable cross-scale data contract?",
      "Are analysis support and model-process scale reported separately?",
      "Was evaluation performed on geographically held-out evidence?",
      "Do instability or missing evidence require repair, a new branch, blocking, or human escalation?",
      "What is the maximum claim supported by this artifact?",
    ],
    createdAt: nowIso(),
  };
}
