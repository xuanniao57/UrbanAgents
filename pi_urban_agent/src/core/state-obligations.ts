import type { WorkflowState } from './types.js';

/** Current obligations only. Review history remains intact for audit/recall. */
export function liveReviewActions(state: WorkflowState, branchId?: string): string[] {
  const latest = new Map<string, WorkflowState['reviews'][number]>();
  for (const r of state.reviews) latest.set(r.branchId, r);
  return [...latest.values()].filter((r) => (!branchId || r.branchId === branchId)
    && r.decision === 'repair' && state.nodes[r.branchId]?.status === 'repair_required'
    && r.requiredAction).map((r) => r.requiredAction!);
}
