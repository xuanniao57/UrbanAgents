import type { HumanDecisionType, PendingHumanPatch, WorkflowState } from "./types.js";
import { sha256Text, trimToTokens } from "./utils.js";

export interface ParsedHumanPatch {
  sourceMessageHash: string;
  targetBranchIds: string[];
  proposedDecision?: HumanDecisionType;
  expectedSupersedesDecisionId?: string;
  rawTextDigest: string;
}

/**
 * Extract only explicit, consequential route/claim instructions. The parser is
 * deliberately conservative: ambiguous dialogue remains ordinary dialogue and
 * is never silently converted into scientific authorization.
 */
export function parseExplicitHumanPatch(text: string, state: WorkflowState): ParsedHumanPatch {
  const normalized = text.toLowerCase();
  const targetBranchIds = resolveTargetBranches(text, state);
  // A consequential checkpoint must bind to an existing Research Tree node.
  // Planning language about routes that have not been created yet remains an
  // ordinary instruction and cannot move the runtime into the human phase.
  const proposedDecision = targetBranchIds.length ? inferDecision(normalized) : undefined;
  const expectedSupersedesDecisionId = proposedDecision && targetBranchIds.length === 1
    ? latestConflictingRouteDecision(state, targetBranchIds[0], proposedDecision)?.decisionId
    : undefined;
  return {
    sourceMessageHash: sha256Text(text),
    targetBranchIds,
    proposedDecision,
    expectedSupersedesDecisionId,
    rawTextDigest: trimToTokens(text.replaceAll(/\s+/g, " ").trim(), 64),
  };
}

function resolveTargetBranches(text: string, state: WorkflowState): string[] {
  const normalizedText = normalizeLocator(text);
  const explicitMatches = Object.values(state.nodes)
    .filter((node) => {
      const id = normalizeLocator(node.nodeId);
      const title = normalizeLocator(node.title);
      return (id.length >= 6 && normalizedText.includes(id))
        || (title.length >= 10 && normalizedText.includes(title));
    })
    .map((node) => node.nodeId);
  if (explicitMatches.length) return explicitMatches;

  // People naturally refer to a route by its model family (for example,
  // "800 m OLS") rather than by the generated Research Tree node ID. Resolve
  // a model alias only when it identifies exactly one route; the mentioned
  // scale remains part of the decision rationale, not a new scale branch.
  const aliases: Array<[boolean, RegExp]> = [
    [/\bols\b/i.test(text), /(?:^|[^a-z0-9])ols(?:$|[^a-z0-9])/i],
    [/(?:fixed(?:[- _]?distance)?[- _]*gwr|固定(?:距离)?\s*gwr)/i.test(text), /(?:fixed(?:[- _]?distance)?[- _]*gwr|固定(?:距离)?\s*gwr)/i],
    [/(?:adaptive(?:[- _]?(?:bandwidth|neighbor))?[- _]*gwr|自适应(?:带宽|邻居)?\s*gwr)/i.test(text), /(?:adaptive(?:[- _]?(?:bandwidth|neighbor))?[- _]*gwr|自适应(?:带宽|邻居)?\s*gwr)/i],
  ];
  for (const [mentioned, alias] of aliases) {
    if (!mentioned) continue;
    const matches = Object.values(state.nodes).filter((node) =>
      node.nodeType === "model_route"
      && alias.test(`${node.title} ${node.summary} ${JSON.stringify(node.parameters)}`),
    );
    if (matches.length === 1) return [matches[0].nodeId];
  }
  return [];
}

function normalizeLocator(value: string): string {
  return value
    .toLowerCase()
    .replace(/\bmet(?:er|re)s?\b/g, "m")
    .replace(/\bkilomet(?:er|re)s?\b/g, "km")
    .replace(/[^a-z0-9]+/g, "");
}

function latestConflictingRouteDecision(
  state: WorkflowState,
  branchId: string,
  proposedDecision: HumanDecisionType,
) {
  return [...state.humanDecisions].reverse().find((decision) =>
    !decision.invalidatedAt
    && decision.decision !== "approve_claim"
    && decision.branchIds.includes(branchId)
    && decision.decision !== proposedDecision,
  );
}

function inferDecision(text: string): HumanDecisionType | undefined {
  // Question/negative clauses are not authorization. Ambiguous language remains
  // unclassified rather than overriding the model with a guessed instruction.
  text = text.split(/(?<=[.!?;。！？；])\s*|\n/).filter((clause) =>
    !/[?？]/.test(clause)
    && !/\b(?:do not|don't|never|must not|should not)\b|不要|不能|并非|不应/.test(clause),
  ).join(" ");
  if (/\b(?:retain(?:ed)?|keep)\b.{0,80}\b(?:sensitivit|comparison)|\b(?:sensitivit(?:y)?|comparison)\b.{0,80}\b(?:retain|keep)|保留.{0,20}(?:敏感性|对照|比较)|(?:敏感性|对照|比较).{0,20}保留/.test(text)) return "retain_sensitivity";
  if (/\b(?:select|choose|make|promote)\b.{0,60}\b(?:main|primary)|选为.{0,20}主|选择.{0,20}主线/.test(text)) return "select_main";
  if (/\brequest\b.{0,60}\bcomparison|\bopen\b.{0,60}\bcomparison|要求.{0,20}比较|增加.{0,20}比较/.test(text)) return "request_comparison";
  if (/\bdefer(?:red)?\b|暂缓|延期/.test(text)) return "defer";
  if (/\bblock(?:ed)?\b|阻断|禁止/.test(text)) return "block";
  if (/\bapprove\b.{0,40}\bclaim|批准.{0,20}结论|同意.{0,20}结论/.test(text)) return "approve_claim";
  return undefined;
}

export function currentHumanAuthorization(state: WorkflowState, sourceMessageHash?: string): PendingHumanPatch | undefined {
  const latest = state.pendingHumanPatches?.at(-1);
  if (!latest || latest.status !== "pending" || !latest.proposedDecision || !latest.targetBranchIds.length
    || (sourceMessageHash !== undefined && latest.sourceMessageHash !== sourceMessageHash)) return undefined;
  return latest;
}

export function selectActiveHumanAuthorization(state: WorkflowState, decision: HumanDecisionType, branchIds: string[], sourceMessageHash?: string): PendingHumanPatch {
  const latest = currentHumanAuthorization(state, sourceMessageHash);
  if (!latest) {
    throw new Error("The latest user message does not supply an unconsumed explicit route authorization. Ask for clarification; do not reuse an older or unclassified message as approval.");
  }
  if (latest.proposedDecision !== decision || latest.targetBranchIds.length !== branchIds.length || !latest.targetBranchIds.every((id) => branchIds.includes(id))) {
    throw new Error("The requested decision/targets conflict with the latest human authorization. Do not fall back to an older message.");
  }
  return latest;
}
