import type { WorkflowState } from "./types.js";
import { currentHumanAuthorization } from "./human-patch.js";
import { liveReviewActions } from './state-obligations.js';

export interface BookmarkOptions {
  /** Bind an in-flight bookmark to the actual latest message, not older patches. */
  sourceMessageHash?: string;
  maxTokens?: number;
}

/** A bounded index, not a compressed copy of the tree. Never slice its tail. */
export function renderStateBookmark(state: WorkflowState, options: BookmarkOptions = {}): string {
  const active = state.nodes[state.activeBranchId];
  if (!active) throw new Error(`Cannot bookmark missing branch: ${state.activeBranchId}`);
  const limit = Math.floor(options.maxTokens ?? 360) * 4;
  if (!Number.isFinite(limit) || limit < 1024) throw new Error("Bookmark budget must be at least 256 estimated tokens");
  const opening = '<urban_state_bookmark schema="1.2">';
  const closing = '</urban_state_bookmark>';
  const footerReserve = '\nomitted_fields: 999; use urban_recall for details.'.length;
  const lines = [opening]; let omitted = 0;
  const fits = (line: string) => [...lines, line, closing].join('\n').length + footerReserve <= limit;
  const add = (line: string, fallback?: string) => {
    // Whole fields/IDs are retained or replaced by an explicit retrieval pointer.
    if (fits(line)) lines.push(line);
    else { omitted++; if (fallback && fits(fallback)) lines.push(fallback); }
  };
  const patch = currentHumanAuthorization(state, options.sourceMessageHash);
  add('instruction_priority: The latest user message is the active instruction. Old summaries and earlier turn instructions are history, not new orders.');
  add('memory_policy: Exact research facts live in the external Research Tree. Recall them only when needed; never infer human authorization.');
  add('recall_next: urban_recall only after urban_state {} gives the bounded route index; request all needed IDs once with scope=branch, detail=card.');
  add(patch
    ? 'next_action: Apply the current explicit choice with urban_human_decision; recall missing target facts first if needed.'
    : 'next_action: Follow the latest request. No human decision write is authorized by this bookmark.');
  add(patch
    ? `pending_human_patch: decision=${patch.proposedDecision} | targets=${JSON.stringify(patch.targetBranchIds)} | supersedes=${patch.expectedSupersedesDecisionId ?? "none"}`
    : 'pending_human_patch: none',
    'pending_human_patch: explicit choice; retrieve details with urban_recall {"scope":"pending"}.');
  add(`state_version: ${state.stateVersion ?? 0} | phase: ${state.phase}`);
  add(`current_focus_node_id: ${active.nodeId}`, 'current_focus_node_id: retrieve with urban_state {}.');
  add(`node_status: ${active.status} (not the current-focus pointer)`);
  if (state.activeFrontier) {
    add(`active_frontier: branch=${state.activeFrontier.branchId} | status=${state.activeFrontier.status}`);
    add(`frontier_stop_condition: ${state.activeFrontier.stopCondition}`,
      'frontier_stop_condition: retrieve with urban_state {}.');
    add(`frontier_expected_artifacts: ${state.activeFrontier.expectedArtifacts.join(', ')}`,
      'frontier_expected_artifacts: retrieve with urban_state {}.');
  }

  // Pending questions are authoritative. Historical review text is not a queue.
  // A live repair is separate: recordReview does not put repairs in that queue.
  const unresolved = state.pendingQuestions.at(-1) ?? liveReviewActions(state, active.nodeId).at(-1);
  add(`unresolved_review_action: ${unresolved ?? 'none'}`,
    'unresolved_review_action: open; retrieve pending questions and active review.');

  const latestHuman = [...state.humanDecisions].reverse().find((d) => !d.invalidatedAt && d.decision !== 'approve_claim' && d.branchIds.includes(active.nodeId));
  add(`human_evidence_role: ${latestHuman ? `${latestHuman.decision} | ${latestHuman.decisionId}` : 'none'}`);
  const approval = [...state.humanDecisions].reverse().find((d) => d.decision === 'approve_claim' && !d.invalidatedAt);
  add(`latest_claim_approval: ${approval?.decisionId ?? 'none'}`);

  const roles = new Map<string, string>();
  for (const d of state.humanDecisions) {
    if (d.invalidatedAt || d.decision === 'approve_claim') continue;
    for (const id of d.branchIds) roles.set(id, d.decision);
  }
  add(`route_index: ${[...roles].map(([id, role]) => `${role}=${id}`).join('; ') || 'none'}`,
    `route_index: ${roles.size} adjudicated routes; locate them with urban_recall scope=tree.`);
  add(`research_question: ${state.contract.researchQuestion}`);
  add(`claim_ceiling: ${state.contract.prohibitedClaims.map((c) => `no ${c}`).join('; ')}`,
    'claim_ceiling: retrieve contract before making claims.');
  if (omitted) lines.push(`omitted_fields: ${omitted}; use urban_recall for details.`);
  lines.push(closing);
  return lines.join('\n');
}
