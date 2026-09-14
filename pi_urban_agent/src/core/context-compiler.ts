import type {
  ArtifactRecord,
  ContextBudget,
  ContextFidelity,
  ContextPacket,
  ContextProfile,
  HumanDecisionRecord,
  ResearchNode,
  ReviewRecord,
  WorkflowPhase,
  WorkflowState,
} from "./types.js";
import { buildRecoveryCapsule, collectResearchPath, reduceRecoveryCapsule, renderRecoveryCapsule } from "./context-memory.js";
import { estimateTokens, trimToTokens } from "./utils.js";
import { renderStateBookmark, type BookmarkOptions } from "./context-bookmark.js";

/** Used only when a provider does not report model metadata. It is not a model-specific policy. */
export const FALLBACK_CONTEXT_WINDOW = 32_768;
export const MIN_CONTEXT_WINDOW = 4_096;

export interface ContextCompileOptions {
  contextWindow?: number;
  maxOutputTokens?: number;
  profile?: ContextProfile | "auto";
  phase?: WorkflowPhase;
  activeBranchId?: string;
}

interface ProfilePolicy {
  responseRatio: number;
  safetyRatio: number;
  systemRatio: number;
  toolRatio: number;
  stateRatio: number;
  systemCap: number;
  toolCap: number;
  stateCap: number;
}

const PROFILE_POLICIES: Record<ContextProfile, ProfilePolicy> = {
  micro: {
    responseRatio: 0.18, safetyRatio: 0.05, systemRatio: 0.16, toolRatio: 0.32, stateRatio: 0.32,
    systemCap: 768, toolCap: 1_600, stateCap: 2_000,
  },
  compact: {
    responseRatio: 0.17, safetyRatio: 0.04, systemRatio: 0.10, toolRatio: 0.20, stateRatio: 0.40,
    systemCap: 1_280, toolCap: 3_200, stateCap: 6_000,
  },
  balanced: {
    responseRatio: 0.16, safetyRatio: 0.04, systemRatio: 0.08, toolRatio: 0.14, stateRatio: 0.40,
    systemCap: 2_048, toolCap: 6_144, stateCap: 16_000,
  },
  spacious: {
    responseRatio: 0.10, safetyRatio: 0.025, systemRatio: 0.04, toolRatio: 0.06, stateRatio: 0.32,
    systemCap: 4_096, toolCap: 8_192, stateCap: 32_000,
  },
};

export function selectContextProfile(contextWindow: number): ContextProfile {
  if (contextWindow <= 8_192) return "micro";
  if (contextWindow <= 24_576) return "compact";
  if (contextWindow <= 65_536) return "balanced";
  return "spacious";
}

export function allocateBudget(
  contextWindow = FALLBACK_CONTEXT_WINDOW,
  maxOutputTokens?: number,
  requestedProfile: ContextProfile | "auto" = "auto",
): ContextBudget {
  // Never inflate a small model to a fictitious larger window.
  const normalized = Math.max(MIN_CONTEXT_WINDOW, Math.floor(contextWindow || FALLBACK_CONTEXT_WINDOW));
  const profile = requestedProfile === "auto" ? selectContextProfile(normalized) : requestedProfile;
  const policy = PROFILE_POLICIES[profile];
  const outputCeiling = maxOutputTokens && maxOutputTokens > 0
    ? Math.min(Math.floor(maxOutputTokens), Math.floor(normalized * 0.25))
    : Math.floor(normalized * policy.responseRatio);
  const responseReserve = Math.max(512, outputCeiling);
  const safetyReserve = Math.max(192, Math.floor(normalized * policy.safetyRatio));
  const available = Math.max(1_024, normalized - responseReserve - safetyReserve);
  const systemBudget = Math.max(384, Math.min(policy.systemCap, Math.floor(available * policy.systemRatio)));
  const toolBudget = Math.max(512, Math.min(policy.toolCap, Math.floor(available * policy.toolRatio)));
  const stateBudget = Math.max(640, Math.min(policy.stateCap, Math.floor(available * policy.stateRatio)));
  const recentDialogueBudget = normalized - responseReserve - safetyReserve - systemBudget - toolBudget - stateBudget;
  if (recentDialogueBudget < 256) {
    // Extremely small windows sacrifice state preview before response safety.
    const correction = 256 - recentDialogueBudget;
    return {
      contextWindow: normalized,
      maxOutputTokens,
      profile,
      responseReserve,
      safetyReserve,
      systemBudget,
      toolBudget,
      stateBudget: Math.max(384, stateBudget - correction),
      recentDialogueBudget: 256,
    };
  }
  return {
    contextWindow: normalized,
    maxOutputTokens,
    profile,
    responseReserve,
    safetyReserve,
    systemBudget,
    toolBudget,
    stateBudget,
    recentDialogueBudget,
  };
}

export class ContextCompiler {
  compile(state: WorkflowState, options?: ContextCompileOptions): ContextPacket {
    const phase = options?.phase ?? state.phase;
    const activeBranchId = options?.activeBranchId ?? state.activeBranchId;
    if (!state.nodes[activeBranchId]) throw new Error(`Cannot compile missing branch: ${activeBranchId}`);
    const budget = allocateBudget(options?.contextWindow, options?.maxOutputTokens, options?.profile);
    const activePath = collectResearchPath(state.nodes, activeBranchId);
    const activeIds = new Set(activePath.map((node) => node.nodeId));
    const siblings = Object.values(state.nodes)
      .filter((node) => !activeIds.has(node.nodeId))
      .sort((a, b) => importance(b, state) - importance(a, state))
      .map(({ nodeId, title, status, summary, claimBoundary }) => ({
        nodeId,
        title,
        status,
        summary: trimToTokens(summary, 120),
        claimBoundary: trimToTokens(claimBoundary, 100),
      }));
    const relevantArtifacts = selectArtifacts(state, activeIds, budget.stateBudget);
    const relevantReviews = state.reviews.filter((review) => activeIds.has(review.branchId) || review.decision !== "proceed");
    const relevantHumanDecisions = state.humanDecisions.filter((decision) => decision.branchIds.some((id) => activeIds.has(id)));
    const packet: ContextPacket = {
      schemaVersion: "2.0",
      phase,
      activeBranchId,
      contractHash: state.contractHash,
      budget,
      fidelity: preferredFidelity(budget),
      omissions: { siblingBranches: 0, evidenceRecords: 0, reviewRecords: 0, humanDecisionRecords: 0, pendingQuestions: 0 },
      estimatedTokens: 0,
      recoveryCapsule: buildRecoveryCapsule(state, activeBranchId, "full"),
      researchContract: state.contract,
      activePath,
      siblingSummaries: siblings,
      evidence: relevantArtifacts,
      reviews: relevantReviews,
      humanDecisions: relevantHumanDecisions,
      pendingQuestions: state.pendingQuestions,
      instructions: phaseInstructions(phase),
    };
    return fitPacketToBudget(packet);
  }

  render(packet: ContextPacket): string {
    return renderPacket(packet);
  }

  /**
   * Render the small, action-oriented projection that accompanies Pi's
   * chronological dialogue context. The Research Tree remains on disk and is
   * recalled by stable ID; this bookmark is deliberately not a compressed
   * copy of the whole tree.
   */
  stateBookmark(state: WorkflowState, options?: BookmarkOptions): string {
    return renderStateBookmark(state, options);
  }

  compactionSummary(state: WorkflowState, options?: ContextCompileOptions | number): string {
    const normalizedOptions = typeof options === "number" ? { contextWindow: options } : options;
    const packet = this.compile(state, normalizedOptions);
    return [
      "URBAN RESEARCH RECOVERY CHECKPOINT — reconstructed from authoritative structured state",
      renderRecoveryCapsule(packet.recoveryCapsule),
      `Context profile: ${packet.budget.profile}; fidelity: ${packet.fidelity}; window: ${packet.budget.contextWindow}; detailed omissions: ${JSON.stringify(packet.omissions)}.`,
      "Numeric parameters, artifact paths/hashes, review outcomes, and claim boundaries in structured state are authoritative and must not be inferred from discarded dialogue.",
      "Use urban_recall with stable node or artifact IDs to page omitted research records back into the working context.",
    ].join("\n");
  }
}


function importance(node: ResearchNode, state: WorkflowState): number {
  let score = node.status === "selected" ? 100 : node.status === "retained_sensitivity" ? 90 : node.status === "blocked" ? 80 : 20;
  score += node.artifactIds.length * 5;
  score += state.reviews.filter((review) => review.branchId === node.nodeId).length * 10;
  return score;
}

function selectArtifacts(state: WorkflowState, activeIds: Set<string>, budget: number): ArtifactRecord[] {
  const artifacts = Object.values(state.artifacts).sort((a, b) => {
    const activeDifference = Number(activeIds.has(b.branchId)) - Number(activeIds.has(a.branchId));
    return activeDifference || b.createdAt.localeCompare(a.createdAt);
  });
  const selected: ArtifactRecord[] = [];
  let used = 0;
  for (const artifact of artifacts) {
    const compact = { ...artifact, summary: trimToTokens(artifact.summary, 180) };
    const cost = estimateTokens(compact);
    if (used + cost > Math.floor(budget * 0.45) && selected.length) continue;
    selected.push(compact);
    used += cost;
  }
  return selected;
}

function phaseInstructions(phase: WorkflowPhase): string[] {
  const common = [
    "Treat structured research state as authoritative; do not reconstruct parameters from conversational memory.",
    "Do not silently change the immutable data contract. Open a typed branch when a research-design choice changes.",
    "Keep analysis-unit support distinct from model-process scale such as GWR bandwidth.",
    "Store large outputs as artifacts and cite their path and SHA-256 instead of pasting them into dialogue.",
  ];
  const byPhase: Record<WorkflowPhase, string[]> = {
    plan: ["Define comparable routes and explicit decision questions; do not execute or claim results yet."],
    execute: ["Execute only the active branch, attach artifacts, and report failures without rewriting the plan."],
    review: ["Audit evidence and issue exactly one of proceed, repair, new_branch, block, or escalate."],
    human: ["Request a human choice among reviewed routes; never infer approval from silence."],
    finalize: ["Finalize the bounded claim and required artifacts; do not open new branches."],
    complete: ["The run is immutable. Explain or export state but do not mutate it."],
  };
  return [...common, ...byPhase[phase]];
}

function preferredFidelity(budget: ContextBudget): ContextFidelity {
  if (budget.stateBudget >= 10_000) return "full";
  if (budget.stateBudget >= 3_200) return "compact";
  if (budget.stateBudget >= 1_200) return "minimal";
  return "pointer";
}

function fitPacketToBudget(original: ContextPacket): ContextPacket {
  const sequence: ContextFidelity[] = original.fidelity === "full"
    ? ["full", "compact", "minimal", "pointer"]
    : original.fidelity === "compact"
      ? ["compact", "minimal", "pointer"]
      : original.fidelity === "minimal"
        ? ["minimal", "pointer"]
        : ["pointer"];
  let candidate = original;
  for (const fidelity of sequence) {
    candidate = reducePacket(original, fidelity);
    candidate.estimatedTokens = estimateTokens(renderPacket(candidate));
    if (candidate.estimatedTokens <= candidate.budget.stateBudget) return candidate;
  }
  // Pointer mode is intentionally bounded and points back to authoritative disk state.
  candidate.fidelity = "pointer";
  candidate.recoveryCapsule = reduceRecoveryCapsule(original.recoveryCapsule, "pointer");
  candidate.siblingSummaries = [];
  candidate.evidence = candidate.evidence.slice(0, 1).map(compactArtifact);
  candidate.reviews = candidate.reviews.slice(-1).map(compactReview);
  candidate.humanDecisions = candidate.humanDecisions.slice(-1).map(compactHumanDecision);
  candidate.pendingQuestions = candidate.pendingQuestions.slice(0, 1).map((value) => trimToTokens(value, 20));
  candidate.omissions = omissionsFrom(original, candidate);
  candidate.estimatedTokens = estimateTokens(renderPacket(candidate));
  return candidate;
}

function reducePacket(original: ContextPacket, fidelity: ContextFidelity): ContextPacket {
  if (fidelity === "full") {
    const packet = { ...original, fidelity, recoveryCapsule: reduceRecoveryCapsule(original.recoveryCapsule, fidelity) };
    packet.omissions = omissionsFrom(original, packet);
    return packet;
  }
  const siblingLimit = fidelity === "compact" ? 10 : fidelity === "minimal" ? 4 : 1;
  const evidenceLimit = fidelity === "compact" ? 10 : fidelity === "minimal" ? 4 : 2;
  const reviewLimit = fidelity === "compact" ? 8 : fidelity === "minimal" ? 4 : 2;
  const humanLimit = fidelity === "compact" ? 8 : fidelity === "minimal" ? 3 : 1;
  const packet: ContextPacket = {
    ...original,
    fidelity,
    recoveryCapsule: reduceRecoveryCapsule(original.recoveryCapsule, fidelity),
    siblingSummaries: original.siblingSummaries.slice(0, siblingLimit).map((node) => ({
      ...node,
      summary: fidelity === "compact" ? trimToTokens(node.summary, 48) : "",
      claimBoundary: fidelity === "compact" ? trimToTokens(node.claimBoundary, 36) : trimToTokens(node.claimBoundary, 18),
    })),
    evidence: original.evidence.slice(0, evidenceLimit).map(compactArtifact),
    reviews: original.reviews.slice(-reviewLimit).map(compactReview),
    humanDecisions: original.humanDecisions.slice(-humanLimit).map(compactHumanDecision),
    pendingQuestions: original.pendingQuestions.slice(0, fidelity === "compact" ? 5 : 2).map((value) => trimToTokens(value, 36)),
  };
  packet.omissions = omissionsFrom(original, packet);
  return packet;
}

function compactArtifact(artifact: ArtifactRecord): ArtifactRecord {
  return { ...artifact, summary: trimToTokens(artifact.summary, 56) };
}

function compactReview(review: ReviewRecord): ReviewRecord {
  return {
    ...review,
    rationale: trimToTokens(review.rationale, 56),
    affectedClaims: review.affectedClaims.slice(0, 4).map((value) => trimToTokens(value, 20)),
    requiredAction: review.requiredAction ? trimToTokens(review.requiredAction, 32) : undefined,
  };
}

function compactHumanDecision(decision: HumanDecisionRecord): HumanDecisionRecord {
  return {
    ...decision,
    rationale: trimToTokens(decision.rationale, 48),
    resultingClaimBoundary: decision.resultingClaimBoundary ? trimToTokens(decision.resultingClaimBoundary, 32) : undefined,
  };
}

function omissionsFrom(original: ContextPacket, reduced: ContextPacket): ContextPacket["omissions"] {
  return {
    siblingBranches: Math.max(0, original.siblingSummaries.length - reduced.siblingSummaries.length),
    evidenceRecords: Math.max(0, original.evidence.length - reduced.evidence.length),
    reviewRecords: Math.max(0, original.reviews.length - reduced.reviews.length),
    humanDecisionRecords: Math.max(0, original.humanDecisions.length - reduced.humanDecisions.length),
    pendingQuestions: Math.max(0, original.pendingQuestions.length - reduced.pendingQuestions.length),
  };
}

function renderPacket(packet: ContextPacket): string {
  const contract = packet.researchContract;
  const fullOrCompact = packet.fidelity === "full" || packet.fidelity === "compact";
  if (packet.fidelity === "pointer") {
    const activeNode = packet.activePath.at(-1);
    const payload = {
      phase: packet.phase,
      activeBranchId: packet.activeBranchId,
      contextPolicy: {
        profile: packet.budget.profile,
        fidelity: packet.fidelity,
        modelContextWindow: packet.budget.contextWindow,
        stateBudget: packet.budget.stateBudget,
        omitted: packet.omissions,
        authoritativeState: "research_state.json",
      },
      recoveryCapsule: packet.recoveryCapsule,
      activeNode: activeNode ? {
        id: activeNode.nodeId,
        type: activeNode.nodeType,
        status: activeNode.status,
        title: trimToTokens(activeNode.title, 16),
      } : undefined,
      evidencePointers: packet.evidence.map(({ artifactId, branchId, role, path, sha256 }) => ({
        artifactId, branchId, role, path, sha256,
      })),
      instruction: "Use urban_recall for omitted detail; never infer omitted values.",
    };
    return ["<urban_research_context schema=\"2.0\">", JSON.stringify(payload), "</urban_research_context>"].join("\n");
  }
  const activeNodes = packet.activePath;
  const activePath = activeNodes.map((node) => ({
    id: node.nodeId,
    type: node.nodeType,
    status: node.status,
    title: node.title,
    parentIds: node.parentIds,
    decision: fullOrCompact ? node.decisionQuestion : undefined,
    parameters: node.parameters,
    claimBoundary: node.claimBoundary,
    artifactIds: node.artifactIds,
  }));
  const immutableContract = {
      contractHash: packet.contractHash,
      researchQuestion: contract.researchQuestion,
      boundary: contract.boundary,
      observationWindow: contract.observationWindow,
      population: contract.population,
      outcome: contract.outcome,
      covariates: contract.covariates,
      candidateSupports: contract.candidateSupports,
      intendedClaim: contract.intendedClaim,
      prohibitedClaims: contract.prohibitedClaims,
      crs: contract.crs,
      gridOrigin: contract.gridOrigin,
      validationGeography: contract.validationGeography,
    };
  const evidence = packet.evidence.map(({ artifactId, branchId, role, path, sha256, summary, metrics }) => ({
    artifactId, branchId, role, path, sha256, summary: fullOrCompact ? summary : undefined, metrics,
  }));
  const payload = {
    phase: packet.phase,
    activeBranchId: packet.activeBranchId,
    contextPolicy: {
      profile: packet.budget.profile,
      fidelity: packet.fidelity,
      modelContextWindow: packet.budget.contextWindow,
      stateBudget: packet.budget.stateBudget,
      omitted: packet.omissions,
      authoritativeState: "research_state.json",
    },
    recoveryCapsule: packet.recoveryCapsule,
    immutableContract,
    activePath,
    comparisonBranches: packet.siblingSummaries,
    evidence,
    reviews: packet.reviews,
    humanDecisions: packet.humanDecisions,
    pendingQuestions: packet.pendingQuestions,
    instructions: packet.instructions,
  };
  return ["<urban_research_context schema=\"2.0\">", JSON.stringify(payload), "</urban_research_context>"].join("\n");
}
