import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const root = resolve(process.argv[2] ?? "evaluation/context_diagnosis_20260830");
const records = [];
for (const [run, requestId] of [["natural_08b", 13], ["post_natural_4b_verify", 1]] as const) {
  const dir = resolve(root, run);
  const request = JSON.parse(await readFile(resolve(dir, `request_${requestId}.json`), "utf8"));
  const state = JSON.parse(await readFile(resolve(dir, "state_recovery.json"), "utf8"));
  const system = request.messages.find((m: any) => m.role === "system").content as string;
  const bookmark = system.slice(system.indexOf("<urban_state_bookmark"));
  const latestPatch = state.pendingHumanPatches.at(-1);
  const displayedPatchId = bookmark.match(/pending_human_patch: (\S+)/)?.[1];
  const displayedPatch = state.pendingHumanPatches.find((p: any) => p.patchId === displayedPatchId);
  records.push({
    run, requestId, bookmark,
    latestInstructionRuleRetained: bookmark.includes("instruction_priority:"),
    completeBookmarkEnvelope: bookmark.includes("</urban_state_bookmark>"),
    latestPatchStatus: latestPatch?.status,
    displayedPatchId, displayedPatchStatus: displayedPatch?.status,
    unclassifiedMessageSuggestsHumanWrite: displayedPatch?.status === "pending_unclassified"
      && bookmark.includes("then call urban_human_decision"),
    authoritativePendingQuestions: state.pendingQuestions,
    displayedUnresolvedReviewAction: bookmark.split("\n").find((l) => l.startsWith("unresolved_review_action:")),
    latestUserPromptIsLastMessage: request.messages.at(-1)?.role === "user",
  });
}
await writeFile(resolve(root, "context_injection_audit.json"), JSON.stringify(records, null, 2));
console.log(JSON.stringify(records.map(({ bookmark, ...r }) => r), null, 2));
