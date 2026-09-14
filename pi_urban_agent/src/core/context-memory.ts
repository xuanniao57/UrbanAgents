import type {
  ContextFidelity,
  HumanDecisionRecord,
  RecallDetail,
  RecallRequest,
  RecallResult,
  RecoveryCapsule,
  ResearchNode,
  ResearchTreePointer,
  ReviewRecord,
  WorkflowState,
} from "./types.js";
import { estimateTokens, sha256Text, trimToTokens } from "./utils.js";
import { currentHumanAuthorization } from './human-patch.js';
import { liveReviewActions } from './state-obligations.js';

const DEFAULT_RECALL_LIMIT = 1_200;
const MAX_RECALL_LIMIT = 8_000;

export function collectResearchPath(nodes: Record<string, ResearchNode>, leafId: string): ResearchNode[] {
  const result: ResearchNode[] = [];
  const visited = new Set<string>();
  const walk = (id: string): void => {
    if (visited.has(id)) return;
    visited.add(id);
    const node = nodes[id];
    if (!node) return;
    for (const parentId of node.parentIds) walk(parentId);
    result.push(node);
  };
  walk(leafId);
  return result;
}

export function buildRecoveryCapsule(
  state: WorkflowState,
  activeBranchId = state.activeBranchId,
  fidelity: ContextFidelity = "full",
): RecoveryCapsule {
  const activePath = collectResearchPath(state.nodes, activeBranchId);
  const activeIds = new Set(activePath.map((node) => node.nodeId));
  const orderedNodes = Object.values(state.nodes)
    .sort((a, b) => researchImportance(b, state, activeIds) - researchImportance(a, state, activeIds));
  const base: RecoveryCapsule = {
    schemaVersion: "1.0",
    runId: state.runId,
    stateVersion: state.stateVersion ?? 0,
    stateHash: sha256Text(state),
    phase: state.phase,
    activeBranchId,
    activePathIds: activePath.map((node) => node.nodeId),
    contract: {
      hash: state.contractHash,
      researchQuestion: state.contract.researchQuestion,
      candidateSupports: state.contract.candidateSupports,
      intendedClaim: state.contract.intendedClaim,
      prohibitedClaims: state.contract.prohibitedClaims,
    },
    // Compile human decisions into a small, explicit route-role index. This
    // prevents a small model from mistaking the currently active/deferred
    // branch for the adjudicated main or sensitivity route after compaction.
    adjudicatedRoutes: buildAdjudicatedRouteIndex(state),
    treeOutline: orderedNodes.map((node) => pointerFor(node, state, "digest")),
    pinnedHumanDecisions: [...state.humanDecisions]
      .sort((a, b) => decisionImportance(b, activeIds) - decisionImportance(a, activeIds) || b.createdAt.localeCompare(a.createdAt))
      .map(compactHuman),
    reviewConstraints: state.reviews
      .filter((review) => activeIds.has(review.branchId) || review.decision !== "proceed")
      .sort((a, b) => reviewImportance(b, activeIds) - reviewImportance(a, activeIds) || b.createdAt.localeCompare(a.createdAt))
      .map(compactReview),
    openLoops: unique([
      ...(state.pendingHumanPatches ?? [])
        .filter((patch) => patch === currentHumanAuthorization(state))
        .map((patch) => `AUTHENTICATED HUMAN PATCH ${patch.patchId}: ${patch.proposedDecision ?? "unparsed"} -> ${patch.targetBranchIds.join(",") || "unspecified"}`),
      ...state.pendingQuestions,
      ...liveReviewActions(state),
      ...Object.values(state.nodes)
        .filter((node) => node.status === "repair_required" || node.status === "deferred")
        .map((node) => `${node.nodeId}: ${node.decisionQuestion}`),
    ]),
    latestStateAt: state.updatedAt,
    omittedTreeNodes: 0,
    recallRoutes: {
      tree: "tool=urban_recall; arguments={\"scope\":\"tree\",\"detail\":\"digest\"}",
      branch: "tool=urban_recall; arguments={\"scope\":\"branch\",\"ids\":[\"NODE_ID\"],\"detail\":\"card\",\"dependency_depth\":2}",
      artifact: "tool=urban_recall; arguments={\"scope\":\"artifact\",\"branch_id\":\"NODE_ID\",\"detail\":\"card\"}",
      review: "tool=urban_recall; arguments={\"scope\":\"review\",\"branch_id\":\"NODE_ID\",\"detail\":\"card\"}",
      humanDecision: "tool=urban_recall; arguments={\"scope\":\"human_decision\",\"branch_id\":\"NODE_ID\",\"detail\":\"card\"}",
      search: "tool=urban_recall; arguments={\"scope\":\"branch\",\"query\":\"KEYWORDS\",\"detail\":\"digest\"}",
    },
  };
  return reduceRecoveryCapsule(base, fidelity);
}

export function reduceRecoveryCapsule(capsule: RecoveryCapsule, fidelity: ContextFidelity): RecoveryCapsule {
  const nodeLimit = fidelity === "full" ? 64 : fidelity === "compact" ? 32 : fidelity === "minimal" ? 14 : 8;
  const humanLimit = fidelity === "full" ? 24 : fidelity === "compact" ? 12 : fidelity === "minimal" ? 6 : 3;
  const reviewLimit = fidelity === "full" ? 24 : fidelity === "compact" ? 12 : fidelity === "minimal" ? 6 : 3;
  const loopLimit = fidelity === "full" ? 16 : fidelity === "compact" ? 8 : fidelity === "minimal" ? 4 : 2;
  const active = new Set(capsule.activePathIds);
  // Human-reviewed choices are authoritative recovery anchors.  They must not
  // disappear merely because many newer/blocked siblings score highly in a
  // chronological or status-based ranking.
  const pinnedDecisionIds = new Set([
    ...capsule.pinnedHumanDecisions.filter((decision) => decision.decision !== "block"),
    ...capsule.pinnedHumanDecisions.filter((decision) => decision.decision === "block").slice(0, 2),
  ].flatMap((decision) => decision.branchIds));
  const selected = capsule.treeOutline.slice(0, nodeLimit);
  for (const node of capsule.treeOutline) {
    if ((active.has(node.nodeId) || pinnedDecisionIds.has(node.nodeId))
      && !selected.some((item) => item.nodeId === node.nodeId)) selected.push(node);
  }
  const pointerOnly = fidelity === "pointer";
  return {
    ...capsule,
    recallRoutes: pointerOnly ? {
      tree: 'tool=urban_recall args={"scope":"tree","detail":"digest"}',
      branch: 'tool=urban_recall args={"scope":"branch","ids":["NODE_ID"],"detail":"card"}',
    } : capsule.recallRoutes,
    contract: pointerOnly
      ? {
        ...capsule.contract,
        intendedClaim: trimToTokens(capsule.contract.intendedClaim, 32),
        prohibitedClaims: capsule.contract.prohibitedClaims.slice(0, 4).map((value) => trimToTokens(value, 16)),
      }
      : capsule.contract,
    adjudicatedRoutes: capsule.adjudicatedRoutes.slice(0, pointerOnly ? 8 : 16).map((route) => ({
      ...route,
      evidenceDigest: route.evidenceDigest
        ? trimToTokens(route.evidenceDigest, pointerOnly ? 24 : 40)
        : undefined,
      claimBoundary: route.claimBoundary
        ? trimToTokens(route.claimBoundary, pointerOnly ? 18 : 32)
        : undefined,
    })),
    treeOutline: selected.map((node) => {
      if (!pointerOnly) return node;
      const isRecoveryAnchor = active.has(node.nodeId) || pinnedDecisionIds.has(node.nodeId);
      return {
        nodeId: node.nodeId,
        nodeType: node.nodeType,
        status: node.status,
        title: trimToTokens(node.title, 16),
        parentIds: node.parentIds,
        artifactCount: node.artifactCount,
        reviewCount: node.reviewCount,
        // Keep compact scientific evidence for the small set of authoritative
        // decision anchors; ordinary siblings remain pointer-only.
        digest: isRecoveryAnchor && node.digest ? trimToTokens(node.digest, 24) : undefined,
        claimBoundary: isRecoveryAnchor && node.claimBoundary ? trimToTokens(node.claimBoundary, 18) : undefined,
      };
    }),
    pinnedHumanDecisions: capsule.pinnedHumanDecisions.slice(0, humanLimit).map((decision) => ({
      ...decision,
      rationale: trimToTokens(decision.rationale, pointerOnly ? 14 : 36),
      resultingClaimBoundary: decision.resultingClaimBoundary
        ? trimToTokens(decision.resultingClaimBoundary, pointerOnly ? 14 : 28)
        : undefined,
    })),
    reviewConstraints: capsule.reviewConstraints.slice(0, reviewLimit).map((review) => ({
      ...review,
      rationale: trimToTokens(review.rationale, pointerOnly ? 14 : 36),
      requiredAction: review.requiredAction ? trimToTokens(review.requiredAction, pointerOnly ? 14 : 28) : undefined,
    })),
    openLoops: capsule.openLoops.slice(0, loopLimit).map((value) => trimToTokens(value, pointerOnly ? 16 : 36)),
    omittedTreeNodes: Math.max(0, capsule.treeOutline.length - selected.length),
  };
}

function buildAdjudicatedRouteIndex(state: WorkflowState): RecoveryCapsule["adjudicatedRoutes"] {
  const roleFor = (decision: HumanDecisionRecord["decision"]): RecoveryCapsule["adjudicatedRoutes"][number]["role"] | undefined => {
    if (decision === "select_main") return "main";
    if (decision === "retain_sensitivity") return "sensitivity";
    if (decision === "block") return "blocked";
    if (decision === "defer") return "deferred";
    if (decision === "request_comparison") return "comparison";
    return undefined;
  };
  const priority: Record<RecoveryCapsule["adjudicatedRoutes"][number]["role"], number> = {
    main: 0,
    sensitivity: 1,
    blocked: 2,
    deferred: 3,
    comparison: 4,
  };
  const byBranch = new Map<string, RecoveryCapsule["adjudicatedRoutes"][number]>();
  for (const decision of state.humanDecisions) {
    const role = roleFor(decision.decision);
    if (!role) continue;
    for (const branchId of decision.branchIds) {
      const node = state.nodes[branchId];
      if (!node) continue;
      byBranch.set(branchId, {
        branchId,
        role,
        decisionId: decision.decisionId,
        evidenceDigest: node.summary || node.decisionQuestion,
        claimBoundary: decision.resultingClaimBoundary || node.claimBoundary,
      });
    }
  }
  return [...byBranch.values()].sort((a, b) => priority[a.role] - priority[b.role] || a.branchId.localeCompare(b.branchId));
}

export function recallResearchState(state: WorkflowState, request: RecallRequest): RecallResult {
  // A tree recall is an index lookup, not a request to serialize external
  // memory into the dialogue. Exact evidence is paged in through branch IDs.
  const requestedDetail = request.scope === "tree"
    ? "pointer"
    : request.detail ?? "card";
  const detail = request.scope === "branch" && requestedDetail === "full" && (request.ids?.length ?? 0) > 1
    ? "card"
    : requestedDetail;
  const maximum = request.scope === "tree" ? 480 : MAX_RECALL_LIMIT;
  const fallback = request.scope === "tree"
    ? 480
    : request.scope === "branch" && (request.ids?.length ?? 0) > 1
      ? 1_600
      : DEFAULT_RECALL_LIMIT;
  const tokenLimit = Math.min(maximum, request.tokenLimit ?? fallback);
  const requestedIds = new Set((request.ids ?? []).filter(Boolean));
  const excludedIds = new Set((request.excludeIds ?? []).filter(Boolean));
  const branchId = request.branchId?.trim();
  const query = request.query?.trim().toLowerCase();
  const depth = Math.max(0, Math.min(8, request.dependencyDepth ?? 1));
  const effectiveBranchId = branchId || (!requestedIds.size && !query && request.range !== "all" ? state.activeBranchId : undefined);
  const all = request.range === "all" && !branchId && !requestedIds.size && !query;
  let candidates: unknown[] = [];

  if (request.scope === "tree") {
    const activeIds = new Set(collectResearchPath(state.nodes, state.activeBranchId).map((node) => node.nodeId));
    candidates = Object.values(state.nodes)
      .sort((a, b) => researchImportance(b, state, activeIds) - researchImportance(a, state, activeIds))
      .map((node) => ({ nodeId: node.nodeId, title: trimToTokens(node.title, 16), humanRole: latestRouteDecision(node.nodeId, state)?.decision ?? null }));
  } else if (request.scope === "branch") {
    const seeds = Object.values(state.nodes).filter((node) =>
      all || requestedIds.has(node.nodeId)
      || node.nodeId === branchId
      || Boolean(query && matchesQuery(searchableNode(node), query)),
    );
    if (!all && !requestedIds.size && !branchId && !query) {
      const active = state.nodes[state.activeBranchId];
      if (active) seeds.push(active);
    }
    const expanded = expandAncestors(state.nodes, seeds, depth);
    const compactBatch = requestedIds.size > 1 && detail === "card";
    candidates = expanded.filter((node) => !excludedIds.has(node.nodeId)).map((node) => compactBatch ? batchRouteCard(node, state) : branchRecord(node, state, detail));
  } else if (request.scope === "artifact") {
    candidates = Object.values(state.artifacts)
      .filter((artifact) =>
        all || requestedIds.has(artifact.artifactId)
        || artifact.branchId === effectiveBranchId
        || Boolean(query && matchesQuery(`${artifact.role} ${artifact.summary} ${artifact.path}`.toLowerCase(), query)),
      )
      .map((artifact) => detail === "pointer"
        ? { artifactId: artifact.artifactId, branchId: artifact.branchId, role: artifact.role, sha256: artifact.sha256 }
        : detail === "digest"
          ? { artifactId: artifact.artifactId, branchId: artifact.branchId, role: artifact.role, summary: artifact.summary, sha256: artifact.sha256 }
          : artifact);
  } else if (request.scope === "review") {
    candidates = state.reviews
      .filter((review) => all || requestedIds.has(review.reviewId) || review.branchId === effectiveBranchId || Boolean(query && matchesQuery(searchableReview(review), query)))
      .map((review) => detail === "full" ? review : compactReview(review));
  } else if (request.scope === "human_decision") {
    candidates = state.humanDecisions
      .filter((decision) => all || requestedIds.has(decision.decisionId) || decision.branchIds.includes(effectiveBranchId ?? "") || Boolean(query && matchesQuery(searchableDecision(decision), query)))
      .map((decision) => detail === "full" ? decision : compactHuman(decision));
  } else if (request.scope === "pending") {
    candidates = [
      ...(state.pendingHumanPatches ?? []).filter((patch) => patch.status === "pending" || patch.status === "pending_unclassified"),
      ...state.pendingQuestions.map((question, index) => ({ id: `pending_${index + 1}`, question })),
    ];
  } else if (request.scope === "contract") {
    candidates = [{ contractHash: state.contractHash, contract: state.contract }];
  }

  // Budget the complete wire object, including pagination. Never slice JSON text.
  const { sourceMessageHash: _hash, excludeIds: _excluded, cursor: _cursor, ...publicRequest } = request;
  const queryKey = sha256Text({ ...publicRequest, tokenLimit: undefined, detail, stateVersion: state.stateVersion, focus: state.activeBranchId }).slice(0, 12);
  const [cursorKey, cursorOffset] = request.cursor?.split(":") ?? [queryKey, "0"];
  const start = Number(cursorOffset);
  if (cursorKey !== queryKey || !Number.isInteger(start) || start < 0 || start > candidates.length) throw new Error("Recall cursor is stale or belongs to another query. Restart without cursor.");
  const records: unknown[] = [];
  const stateHash = sha256Text(state);
  const pendingPatch = currentHumanAuthorization(state, request.sourceMessageHash);
  const makePage = (): RecallResult => {
    const omittedRecords = candidates.length - start - records.length;
    const recalledPendingTargets = Boolean(
    pendingPatch
    && request.scope === "branch"
    && pendingPatch.targetBranchIds.length
    && pendingPatch.targetBranchIds.every((id) => requestedIds.has(id))
    && pendingPatch.targetBranchIds.every((id) => records.some((record) => (record as Record<string, unknown>)?.nodeId === id))
    && (detail === "card" || detail === "full"),
  );
  return {
    schemaVersion: "1.0",
    request: { ...publicRequest, detail, dependencyDepth: depth, tokenLimit },
    stateVersion: state.stateVersion ?? 0,
    stateHash,
    currentFocusNodeId: state.activeBranchId,
    effectiveRange: request.scope === "tree" || all ? "all" : branchId || (requestedIds.size || query ? "explicit selection" : effectiveBranchId) || request.scope,
    records,
    omittedRecords,
    hasMore: omittedRecords > 0,
    nextCursor: omittedRecords > 0 ? `${queryKey}:${start + records.length}` : undefined,
    recoveryHint: request.scope === "tree"
      ? 'Index only. For parameters, human decisions and metrics use scope="branch", ids=[needed node IDs], detail="card". nextCursor lists more IDs.'
      : omittedRecords > 0
      ? "More records exist. Repeat the same query with nextCursor, or request specific IDs."
      : undefined,
    actionSatisfied: recalledPendingTargets || undefined,
    nextAction: recalledPendingTargets && pendingPatch
      ? `Target evidence loaded. Do not recall these routes again. Current choice: ${pendingPatch.proposedDecision}; supersedes=${pendingPatch.expectedSupersedesDecisionId ?? "none"}.`
      : undefined,
  };
  };
  for (const candidate of candidates.slice(start)) {
    records.push(candidate);
    if (estimateTokens(makePage()) <= tokenLimit) continue;
    const requiredTokens = estimateTokens(makePage());
    records.pop();
    if (!records.length) {
      const page = makePage();
      const r = candidate as Record<string, unknown>;
      page.oversizedRecord = { id: String(r.nodeId ?? (r.node as ResearchNode | undefined)?.nodeId ?? r.artifactId ?? r.reviewId ?? r.decisionId ?? "contract"), requiredTokens };
      page.recoveryHint = "Record not loaded. Increase token_limit or request lower detail; unchanged cursor retries this record.";
      if (estimateTokens(page) > tokenLimit) throw new Error("Recall page metadata does not fit. Increase token_limit or narrow the query.");
      return page;
    }
    break;
  }
  const page = makePage();
  if (estimateTokens(page) > tokenLimit) throw new Error("Recall page metadata does not fit. Increase token_limit or narrow the query.");
  return page;
}

export function latestRouteDecision(nodeId: string, state: WorkflowState): HumanDecisionRecord | undefined {
  return [...state.humanDecisions].reverse().find(d => !d.invalidatedAt && d.decision !== "approve_claim" && d.branchIds.includes(nodeId));
}

export function renderRecoveryCapsule(capsule: RecoveryCapsule): string {
  return [
    '<urban_recovery_capsule schema="1.0">',
    JSON.stringify(capsule),
    "</urban_recovery_capsule>",
  ].join("\n");
}

function researchImportance(node: ResearchNode, state: WorkflowState, activeIds: Set<string>): number {
  let score = activeIds.has(node.nodeId) ? 1_000 : 0;
  score += node.status === "selected" ? 500
    : node.status === "retained_sensitivity" ? 450
      : node.status === "repair_required" ? 420
        : node.status === "blocked" ? 400
          : node.status === "deferred" ? 300
            : node.status === "reviewed" ? 250
              : 100;
  score += node.artifactIds.length * 15;
  score += state.reviews.filter((review) => review.branchId === node.nodeId).length * 25;
  for (const decision of state.humanDecisions.filter((item) => item.branchIds.includes(node.nodeId))) {
    // Decision semantics outrank incidental recency and legacy node-status
    // labels. This also supports imported runs whose chosen nodes are still
    // marked `complete` rather than `selected`/`retained_sensitivity`.
    score += decision.decision === "select_main" ? 900
      : decision.decision === "retain_sensitivity" ? 800
        : decision.decision === "block" ? 700
          : decision.decision === "defer" ? 600
            : decision.decision === "request_comparison" ? 500
              : decision.decision === "approve_claim" ? 100
                : 50;
  }
  return score;
}

function decisionImportance(decision: HumanDecisionRecord, activeIds: Set<string>): number {
  let score = decision.branchIds.some((id) => activeIds.has(id)) ? 1_000 : 0;
  if (decision.decision === "block" || decision.decision === "approve_claim") score += 500;
  if (decision.decision === "select_main" || decision.decision === "retain_sensitivity") score += 400;
  return score;
}

function reviewImportance(review: ReviewRecord, activeIds: Set<string>): number {
  let score = activeIds.has(review.branchId) ? 1_000 : 0;
  if (review.decision !== "proceed") score += 500;
  if (review.requiredAction) score += 250;
  return score;
}

function pointerFor(node: ResearchNode, state: WorkflowState, detail: RecallDetail): ResearchTreePointer {
  const pointer: ResearchTreePointer = {
    nodeId: node.nodeId,
    nodeType: node.nodeType,
    status: node.status,
    title: node.title,
    parentIds: node.parentIds,
    artifactCount: node.artifactIds.length,
    reviewCount: state.reviews.filter((review) => review.branchId === node.nodeId).length,
  };
  if (detail !== "pointer") {
    pointer.digest = trimToTokens(node.summary || node.decisionQuestion, detail === "digest" ? 28 : 56);
    pointer.claimBoundary = trimToTokens(node.claimBoundary, detail === "digest" ? 20 : 40);
  }
  return pointer;
}

function branchRecord(node: ResearchNode, state: WorkflowState, detail: RecallDetail): unknown {
  if (detail === "pointer" || detail === "digest") return pointerFor(node, state, detail);
  if (detail === "full") {
    return {
      node,
      artifacts: node.artifactIds.map((id) => state.artifacts[id]).filter(Boolean),
      reviews: state.reviews.filter((review) => review.branchId === node.nodeId),
      humanDecisions: state.humanDecisions.filter((decision) => decision.branchIds.includes(node.nodeId)),
    };
  }
  const latestReview = [...state.reviews].reverse().find((review) => review.branchId === node.nodeId);
  const metrics = Object.assign({}, ...node.artifactIds
    .map((id) => state.artifacts[id]?.metrics)
    .filter((value): value is NonNullable<typeof value> => Boolean(value)));
  const humanRoles = state.humanDecisions
    .filter((decision) => !decision.invalidatedAt && decision.branchIds.includes(node.nodeId) && decision.decision !== "approve_claim")
    .map((decision) => ({ decisionId: decision.decisionId, decision: decision.decision }));
  return {
    nodeId: node.nodeId,
    nodeType: node.nodeType,
    status: node.status,
    title: trimToTokens(node.title, 20),
    parentIds: node.parentIds,
    parameters: node.parameters,
    metrics,
    summary: trimToTokens(node.summary || node.decisionQuestion, 32),
    claimBoundary: trimToTokens(node.claimBoundary, 28),
    review: latestReview ? {
      reviewId: latestReview.reviewId,
      decision: latestReview.decision,
      rationale: trimToTokens(latestReview.rationale, 24),
      requiredAction: latestReview.requiredAction ? trimToTokens(latestReview.requiredAction, 18) : undefined,
    } : undefined,
    humanRoles,
  };
}

function batchRouteCard(node: ResearchNode, state: WorkflowState): unknown {
  const latestReview = [...state.reviews].reverse().find((review) => review.branchId === node.nodeId);
  const latestRole = latestRouteDecision(node.nodeId, state);
  const allMetrics = Object.assign({}, ...node.artifactIds
    .map((id) => state.artifacts[id]?.metrics)
    .filter((value): value is NonNullable<typeof value> => Boolean(value)));
  const parameters = Object.fromEntries(Object.entries(node.parameters).filter(([key]) =>
    /model|role|support|scale|kernel|bandwidth|distance|neighbor|neighbour/i.test(key),
  ));
  const metrics = Object.fromEntries(Object.entries(allMetrics).filter(([key]) =>
    /r2|rmse|mae|condition|radius|neighbor|neighbour/i.test(key),
  ));
  return {
    nodeId: node.nodeId,
    status: node.status,
    role: latestRole?.decision,
    roleDecisionId: latestRole?.decisionId,
    parameters,
    metrics,
    review: latestReview ? { decision: latestReview.decision, reviewId: latestReview.reviewId } : undefined,
    artifacts: node.artifactIds.map((id) => state.artifacts[id]).filter(Boolean).map((artifact) => ({
      artifactId: artifact.artifactId,
      role: artifact.role,
      path: artifact.path,
      sha256: artifact.sha256,
    })),
    claimBoundary: trimToTokens(node.claimBoundary, 12),
  };
}

function expandAncestors(nodes: Record<string, ResearchNode>, seeds: ResearchNode[], depth: number): ResearchNode[] {
  const ordered: ResearchNode[] = [];
  const seen = new Set<string>();
  const visit = (node: ResearchNode, remaining: number): void => {
    if (seen.has(node.nodeId)) return;
    seen.add(node.nodeId);
    ordered.push(node);
    if (remaining <= 0) return;
    for (const parentId of node.parentIds) {
      const parent = nodes[parentId];
      if (parent) visit(parent, remaining - 1);
    }
  };
  for (const seed of seeds) visit(seed, depth);
  return ordered;
}

function compactReview(review: ReviewRecord): RecoveryCapsule["reviewConstraints"][number] {
  return {
    reviewId: review.reviewId,
    branchId: review.branchId,
    decision: review.decision,
    rationale: trimToTokens(review.rationale, 48),
    requiredAction: review.requiredAction ? trimToTokens(review.requiredAction, 32) : undefined,
  };
}

function compactHuman(decision: HumanDecisionRecord): RecoveryCapsule["pinnedHumanDecisions"][number] {
  return {
    decisionId: decision.decisionId,
    branchIds: decision.branchIds,
    decision: decision.decision,
    rationale: trimToTokens(decision.rationale, 48),
    resultingClaimBoundary: decision.resultingClaimBoundary ? trimToTokens(decision.resultingClaimBoundary, 32) : undefined,
  };
}

function searchableNode(node: ResearchNode): string {
  return `${node.nodeId} ${node.nodeType} ${node.title} ${node.summary} ${node.decisionQuestion} ${node.claimBoundary}`.toLowerCase();
}

function searchableReview(review: ReviewRecord): string {
  return `${review.reviewId} ${review.branchId} ${review.decision} ${review.rationale} ${review.requiredAction ?? ""}`.toLowerCase();
}

function searchableDecision(decision: HumanDecisionRecord): string {
  return `${decision.decisionId} ${decision.branchIds.join(" ")} ${decision.decision} ${decision.rationale} ${decision.resultingClaimBoundary ?? ""}`.toLowerCase();
}

function matchesQuery(haystack: string, query: string): boolean {
  const normalize = (value: string): string[] => value
    .toLowerCase()
    .replaceAll(/[^\p{L}\p{N}_.-]+/gu, " ")
    .split(/\s+/)
    .map((token) => token.trim())
    .filter(Boolean);
  const terms = normalize(query);
  if (!terms.length) return false;
  const normalizedHaystack = normalize(haystack).join(" ");
  return terms.every((term) => normalizedHaystack.includes(term));
}

function unique(values: string[]): string[] {
  return [...new Set(values.map((value) => value.trim()).filter(Boolean))];
}
