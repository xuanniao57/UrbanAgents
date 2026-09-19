import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { createHash } from "node:crypto";

const dir = resolve(process.argv[2]);
const before = JSON.parse(await readFile(resolve(dir, "state_before.json"), "utf8"));
const after = JSON.parse(await readFile(resolve(dir, "research/research_state.json"), "utf8"));
const safeRead = async (name: string) => { try { return await readFile(resolve(dir, name), "utf8"); } catch { return ""; } };
const answer = await safeRead("answer_recovery.txt");
const events = (await safeRead("pi_events.jsonl")).trim().split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line));
const latest = new Map<string, any>();
for (const decision of before.humanDecisions) if (decision.decision !== "approve_claim") for (const id of decision.branchIds) latest.set(id, decision);
const factual = [...latest.entries()].map(([id, decision]) => {
  const node = before.nodes[id];
  const metric = node.artifactIds.map((aid: string) => before.artifacts[aid]?.metrics?.oof_r2).find((v: unknown) => typeof v === "number");
  return { id, expectedRole: decision.decision, reportedId: answer.includes(id), reportedRole: answer.includes(decision.decision), expectedR2: metric, reportedExactR2: typeof metric !== "number" ? null : answer.includes(String(metric)),
    // Presence checks only: manual review must check the facts are attached to the right route.
  };
});
const newDecisions = after.humanDecisions.slice(before.humanDecisions.length);
const target = [...latest.entries()].find(([id]) => before.nodes[id].status === "deferred")?.[0];
const prompt = await safeRead("prompt_human_patch.txt");
const hash = createHash("sha256").update(prompt).digest("hex");
const applied = newDecisions.find((d: any) => d.decision === "retain_sensitivity" && d.branchIds.length === 1 && d.branchIds[0] === target);
const patch = after.pendingHumanPatches?.find((p: any) => p.sourceMessageHash === hash);
const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
const recoverySnapshotText = await safeRead("state_recovery.json");
const recoverySnapshot = recoverySnapshotText ? JSON.parse(recoverySnapshotText) : null;
const result = {
  kind: "mechanical_checks_plus_manual_semantic_review_required", historicalFixture: true,
  humanPatchStagePerformed: !!prompt,
  readOnlyRecoveryStateUnchanged: recoverySnapshot ? same(before.nodes, recoverySnapshot.nodes)
    && same(before.humanDecisions, recoverySnapshot.humanDecisions) : null,
  recovery: factual,
  batchRecallCalls: events.filter((e) => e.type === "tool_execution_start" && e.toolName === "urban_recall" && Array.isArray(e.args?.ids) && e.args.ids.length > 1).length,
  humanPatch: !prompt ? null : { target, semanticRoleApplied: !!applied, actorAuthenticated: applied?.actorProvenance === "runtime_authenticated", sourceHashMatches: applied?.sourceMessageHash === hash,
    ingressEnvelopeApplied: patch?.status === "applied", sourceCreatedBeforeDecision: !!patch && !!applied && patch.createdAt <= applied.createdAt,
    oldApprovalsInvalidated: after.humanDecisions.filter((d: any) => d.decision === "approve_claim").every((d: any) => !!d.invalidatedAt),
    pendingQuestions: after.pendingQuestions, artifactsUnchanged: same(before.artifacts, after.artifacts),
    otherRouteStatusesUnchanged: Object.keys(before.nodes).filter((id) => id !== target).every((id) => before.nodes[id].status === after.nodes[id].status),
    finalClaimAbsent: !after.finalClaim,
  },
  naturalCompactions: events.filter((e) => e.type === "compaction_end" && e.reason === "threshold").map((e) => ({ aborted: e.aborted, tokensBefore: e.result?.tokensBefore, summary: e.result?.summary, usage: e.result?.usage })),
};
await writeFile(resolve(dir, "stage_assessment.json"), JSON.stringify(result, null, 2));
console.log(JSON.stringify({ factualRouteCount: factual.length, exactMetrics: factual.filter((r) => r.reportedExactR2).length, humanPatch: result.humanPatch, naturalCompactions: result.naturalCompactions.length }));
