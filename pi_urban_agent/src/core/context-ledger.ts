import { appendFile, mkdir, rename, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import type { ContextPacket, RecoveryCapsule } from "./types.js";
import { makeId, nowIso } from "./utils.js";

export interface ContextManifestEntry {
  event: "compiled" | "bookmarked" | "checkpointed" | "compacted" | "tree_navigation" | "recall";
  reason?: string;
  runId: string;
  stateVersion: number;
  phase: string;
  activeBranchId: string;
  contextWindow?: number;
  profile?: string;
  fidelity?: string;
  estimatedTokens?: number;
  tokensBefore?: number;
  estimatedTokensAfter?: number;
  injectedNodeIds?: string[];
  omittedTreeNodes?: number;
  recalledScope?: string;
  recalledRecords?: number;
  timestamp?: string;
}

export async function appendContextManifest(runDir: string, entry: ContextManifestEntry): Promise<void> {
  const path = join(runDir, "logs", "context_manifest.jsonl");
  await mkdir(dirname(path), { recursive: true });
  await appendFile(path, `${JSON.stringify({ ...entry, timestamp: entry.timestamp ?? nowIso() })}\n`, "utf8");
}

export async function writeRecoveryCheckpoint(
  runDir: string,
  capsule: RecoveryCapsule,
  metadata: Record<string, unknown>,
): Promise<{ jsonPath: string; markdownPath: string }> {
  const stamp = nowIso().replaceAll(/[-:.TZ]/g, "").slice(0, 14);
  const base = `context_checkpoint_${String(capsule.stateVersion).padStart(5, "0")}_${stamp}`;
  const jsonPath = join(runDir, "checkpoints", `${base}.json`);
  const markdownPath = join(runDir, "views", "recovery_capsule.md");
  await atomicWrite(jsonPath, JSON.stringify({ capsule, metadata }, null, 2));
  await atomicWrite(markdownPath, renderCapsuleMarkdown(capsule, metadata));
  return { jsonPath, markdownPath };
}

export function contextManifestFromPacket(packet: ContextPacket): Omit<ContextManifestEntry, "event" | "runId" | "stateVersion"> {
  return {
    phase: packet.phase,
    activeBranchId: packet.activeBranchId,
    contextWindow: packet.budget.contextWindow,
    profile: packet.budget.profile,
    fidelity: packet.fidelity,
    estimatedTokens: packet.estimatedTokens,
    injectedNodeIds: packet.recoveryCapsule.treeOutline.map((node) => node.nodeId),
    omittedTreeNodes: packet.recoveryCapsule.omittedTreeNodes,
  };
}

async function atomicWrite(path: string, content: string): Promise<void> {
  await mkdir(dirname(path), { recursive: true });
  const temporaryPath = `${path}.${process.pid}.${makeId("tmp")}`;
  await writeFile(temporaryPath, content, "utf8");
  await rename(temporaryPath, path);
}

function renderCapsuleMarkdown(capsule: RecoveryCapsule, metadata: Record<string, unknown>): string {
  const tree = capsule.treeOutline
    .map((node) => `- \`${node.nodeId}\` — ${node.status} — ${node.title}${node.digest ? ` — ${node.digest}` : ""}`)
    .join("\n");
  const openLoops = capsule.openLoops.map((value) => `- ${value}`).join("\n") || "- None recorded";
  return [
    "# Urban Agent Recovery Capsule",
    "",
    `- Run: \`${capsule.runId}\``,
    `- State version: \`${capsule.stateVersion}\``,
    `- State hash: \`${capsule.stateHash}\``,
    `- Phase: \`${capsule.phase}\``,
    `- Active branch: \`${capsule.activeBranchId}\``,
    `- Contract hash: \`${capsule.contract.hash}\``,
    "",
    "## Research question",
    "",
    capsule.contract.researchQuestion,
    "",
    "## Active path",
    "",
    capsule.activePathIds.map((id) => `- \`${id}\``).join("\n"),
    "",
    "## Research tree index",
    "",
    tree || "- No nodes",
    "",
    "## Open loops",
    "",
    openLoops,
    "",
    "## Recall routes",
    "",
    "```json",
    JSON.stringify(capsule.recallRoutes, null, 2),
    "```",
    "",
    "## Compaction metadata",
    "",
    "```json",
    JSON.stringify(metadata, null, 2),
    "```",
    "",
    "This view is derived from the authoritative JSON state. It is not a second source of truth.",
  ].join("\n");
}
