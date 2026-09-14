export const PHASES = ["plan", "execute", "review", "human", "finalize", "complete"] as const;
export type WorkflowPhase = (typeof PHASES)[number];

export const NODE_TYPES = [
  "research_object",
  "data_contract",
  "analysis_support",
  "model_route",
  "parameter_route",
  "validation_route",
  "diagnostic",
  "review",
  "human_checkpoint",
  "evidence_synthesis",
  "claim",
] as const;
export type ResearchNodeType = (typeof NODE_TYPES)[number];

export const NODE_STATUSES = [
  "proposed",
  "active",
  "executed",
  "reviewed",
  "selected",
  "retained_sensitivity",
  "repair_required",
  "deferred",
  "blocked",
  "complete",
] as const;
export type NodeStatus = (typeof NODE_STATUSES)[number];

export const REVIEW_DECISIONS = ["proceed", "repair", "new_branch", "block", "escalate"] as const;
export type ReviewDecisionType = (typeof REVIEW_DECISIONS)[number];

export const HUMAN_DECISIONS = [
  "select_main",
  "retain_sensitivity",
  "request_comparison",
  "defer",
  "block",
  "approve_claim",
] as const;
export type HumanDecisionType = (typeof HUMAN_DECISIONS)[number];

export interface ResearchContract {
  researchQuestion: string;
  boundary: string;
  observationWindow: string;
  population: string;
  outcome: string;
  covariates: string[];
  candidateSupports: string[];
  intendedClaim: string;
  prohibitedClaims: string[];
  crs?: string;
  gridOrigin?: string;
  validationGeography?: string;
}

export interface ArtifactRecord {
  artifactId: string;
  branchId: string;
  role: string;
  path: string;
  sha256: string;
  mediaType?: string;
  summary: string;
  metrics?: Record<string, number | string | boolean | null>;
  createdAt: string;
}

export interface ResearchNode {
  nodeId: string;
  nodeType: ResearchNodeType;
  title: string;
  parentIds: string[];
  status: NodeStatus;
  decisionQuestion: string;
  parameters: Record<string, unknown>;
  claimBoundary: string;
  summary: string;
  artifactIds: string[];
  createdAt: string;
  updatedAt: string;
}

export interface ReviewRecord {
  reviewId: string;
  branchId: string;
  decision: ReviewDecisionType;
  checks: Record<string, "pass" | "fail" | "unknown">;
  rationale: string;
  affectedClaims: string[];
  requiredAction?: string;
  createdAt: string;
}

export interface HumanDecisionRecord {
  decisionId: string;
  branchIds: string[];
  decision: HumanDecisionType;
  rationale: string;
  actor: string;
  /** Runtime-authenticated identity provenance. Legacy imported records omit these fields. */
  actorProvenance?: "runtime_authenticated" | "legacy_import";
  sourcePatchId?: string;
  sourceMessageHash?: string;
  supersedesDecisionId?: string;
  resultingClaimBoundary?: string;
  invalidatedAt?: string;
  invalidatedByDecisionId?: string;
  invalidationReason?: string;
  createdAt: string;
}

export interface PendingHumanPatch {
  patchId: string;
  actorId: string;
  source: "interactive" | "rpc" | "extension" | "test";
  sourceMessageHash: string;
  targetBranchIds: string[];
  proposedDecision?: HumanDecisionType;
  /** Existing route-role decision that the explicit human patch would replace. */
  expectedSupersedesDecisionId?: string;
  rawTextDigest: string;
  status: "pending_unclassified" | "pending" | "applied" | "superseded" | "consumed_no_patch";
  appliedDecisionId?: string;
  createdAt: string;
  appliedAt?: string;
  consumedAt?: string;
}

/** One bounded executable route; the rest of the Research Tree remains external memory. */
export interface ActiveResearchFrontier {
  familyId: string;
  branchId: string;
  stopCondition: string;
  expectedArtifacts: string[];
  status: "ready" | "committed" | "reviewed";
  updatedAt: string;
}

export interface WorkflowState {
  schemaVersion: "2.0";
  /** Monotonic version of the authoritative research state. Older runs may omit it. */
  stateVersion?: number;
  runId: string;
  runDir: string;
  phase: WorkflowPhase;
  contract: ResearchContract;
  contractHash: string;
  activeBranchId: string;
  activeFrontier?: ActiveResearchFrontier;
  nodes: Record<string, ResearchNode>;
  artifacts: Record<string, ArtifactRecord>;
  reviews: ReviewRecord[];
  humanDecisions: HumanDecisionRecord[];
  pendingHumanPatches?: PendingHumanPatch[];
  pendingQuestions: string[];
  finalClaim?: string;
  finalizedAt?: string;
  createdAt: string;
  updatedAt: string;
}

export type ResearchEventType =
  | "initialized"
  | "branch_opened"
  | "route_family_committed"
  | "phase_changed"
  | "artifact_attached"
  | "run_committed"
  | "review_recorded"
  | "human_decision_recorded"
  | "human_patch_persisted"
  | "human_patch_consumed"
  | "claim_approval_invalidated"
  | "finalized";

export interface ResearchEvent {
  eventId: string;
  type: ResearchEventType;
  timestamp: string;
  actor: "planner" | "worker" | "reviewer" | "human" | "system";
  branchId?: string;
  payload: Record<string, unknown>;
  stateHash: string;
}

export interface ContextBudget {
  contextWindow: number;
  maxOutputTokens?: number;
  profile: ContextProfile;
  responseReserve: number;
  safetyReserve: number;
  systemBudget: number;
  toolBudget: number;
  stateBudget: number;
  recentDialogueBudget: number;
}

export type ContextProfile = "micro" | "compact" | "balanced" | "spacious";
export type ContextFidelity = "full" | "compact" | "minimal" | "pointer";

export type RecallScope = "tree" | "branch" | "artifact" | "review" | "human_decision" | "pending" | "contract";
export type RecallDetail = "pointer" | "digest" | "card" | "full";

export interface ResearchTreePointer {
  nodeId: string;
  nodeType: ResearchNodeType;
  status: NodeStatus;
  title: string;
  parentIds: string[];
  artifactCount: number;
  reviewCount: number;
  digest?: string;
  claimBoundary?: string;
}

export interface RecoveryCapsule {
  schemaVersion: "1.0";
  runId: string;
  stateVersion: number;
  stateHash: string;
  phase: WorkflowPhase;
  activeBranchId: string;
  activePathIds: string[];
  contract: {
    hash: string;
    researchQuestion: string;
    candidateSupports: string[];
    intendedClaim: string;
    prohibitedClaims: string[];
  };
  adjudicatedRoutes: Array<{
    branchId: string;
    role: "main" | "sensitivity" | "blocked" | "deferred" | "comparison";
    decisionId: string;
    evidenceDigest?: string;
    claimBoundary?: string;
  }>;
  treeOutline: ResearchTreePointer[];
  pinnedHumanDecisions: Array<Pick<HumanDecisionRecord, "decisionId" | "branchIds" | "decision" | "rationale" | "resultingClaimBoundary">>;
  reviewConstraints: Array<Pick<ReviewRecord, "reviewId" | "branchId" | "decision" | "rationale" | "requiredAction">>;
  openLoops: string[];
  latestStateAt: string;
  omittedTreeNodes: number;
  recallRoutes: Record<string, string>;
}

export interface RecallRequest {
  scope: RecallScope;
  ids?: string[];
  branchId?: string;
  query?: string;
  detail?: RecallDetail;
  dependencyDepth?: number;
  tokenLimit?: number;
  /** Runtime-only per-turn de-duplication; not exposed as an LLM parameter. */
  excludeIds?: string[];
  /** Runtime-only binding to the latest user input; never an LLM argument. */
  sourceMessageHash?: string;
  range?: "current" | "all";
  cursor?: string;
}

export interface RecallResult {
  schemaVersion: "1.0";
  request: RecallRequest;
  stateVersion: number;
  stateHash: string;
  records: unknown[];
  omittedRecords: number;
  hasMore: boolean;
  recoveryHint?: string;
  effectiveRange?: string;
  currentFocusNodeId?: string;
  nextCursor?: string;
  oversizedRecord?: { id: string; requiredTokens: number };
  /** Runtime action cursor: the evidence needed for the current authenticated patch is now present. */
  actionSatisfied?: boolean;
  nextAction?: string;
}

export interface ContextOmissions {
  siblingBranches: number;
  evidenceRecords: number;
  reviewRecords: number;
  humanDecisionRecords: number;
  pendingQuestions: number;
}

export interface ContextPacket {
  schemaVersion: "2.0";
  phase: WorkflowPhase;
  activeBranchId: string;
  contractHash: string;
  budget: ContextBudget;
  fidelity: ContextFidelity;
  omissions: ContextOmissions;
  estimatedTokens: number;
  recoveryCapsule: RecoveryCapsule;
  researchContract: ResearchContract;
  activePath: ResearchNode[];
  siblingSummaries: Array<Pick<ResearchNode, "nodeId" | "title" | "status" | "summary" | "claimBoundary">>;
  evidence: ArtifactRecord[];
  reviews: ReviewRecord[];
  humanDecisions: HumanDecisionRecord[];
  pendingQuestions: string[];
  instructions: string[];
}

export interface WorkerPacket {
  packetId: string;
  branchId: string;
  assignment: string;
  contractHash: string;
  context: ContextPacket;
  expectedArtifacts: string[];
  allowedToolNames: string[];
  createdAt: string;
}

export interface ReviewerPacket {
  packetId: string;
  branchId: string;
  contractHash: string;
  context: ContextPacket;
  evidenceManifest: ArtifactRecord[];
  reviewQuestions: string[];
  createdAt: string;
}
