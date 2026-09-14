import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

import { SessionManager } from "@earendil-works/pi-coding-agent";

const args = parseArgs(process.argv.slice(2));
if (!args.outputDir || !args.model) {
  throw new Error("Usage: prepare-context-ablation-session.ts --output-dir <dir> --model <ollama-tag>");
}
const outputDir = resolve(args.outputDir);
await mkdir(outputDir, { recursive: true });
const manager = SessionManager.create(process.cwd(), outputDir);
const now = Date.now();

const anchor = [
  "Archived research log before compaction.",
  "Exact admitted route IDs, model settings, metrics, review outcomes, and human roles were committed to the authoritative Research Git Tree, not repeated in dialogue.",
  "Later dialogue may contain provisional alternatives and must not overwrite those records. Retrieve exact prior facts from the tree when a later action depends on them.",
].join(" ");
appendPair(anchor, "Acknowledged the archived route facts; future decisions must check authoritative state.", 0);

for (let block = 1; block <= 7; block += 1) {
  const lines: string[] = [];
  for (let item = 0; item < 18; item += 1) {
    const support = 200 + ((block + item) % 7) * 100;
    const fraction = 10 + ((block * 3 + item) % 5) * 5;
    lines.push(
      `Provisional log ${block}.${item}: inspect ${support} m candidate with adaptive ${fraction}% neighbours; result not admitted, route id not assigned, and no human authorization.`,
    );
  }
  lines.push("Tool output preview was truncated; exact values remain in external artifacts and should be recalled by stable ID if needed.");
  appendPair(lines.join(" "), `Archived provisional block ${block}; no state change was authorized.`, block);
}

const sessionFile = manager.getSessionFile();
if (!sessionFile) throw new Error("Persistent session file was not created.");
await writeFile(resolve(outputDir, "prepared_session.json"), JSON.stringify({ sessionFile, entries: manager.getEntries().length }, null, 2), "utf8");
console.log(JSON.stringify({ sessionFile, entries: manager.getEntries().length }, null, 2));

function appendPair(userText: string, assistantText: string, index: number): void {
  const user = { role: "user" as const, content: userText, timestamp: now + index * 2_000 };
  const assistant = {
    role: "assistant",
    content: [{ type: "text", text: assistantText }],
    api: "openai-completions",
    provider: "local-ollama",
    model: args.model!,
    usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
    stopReason: "stop",
    timestamp: now + index * 2_000 + 1_000,
  } as Parameters<typeof manager.appendMessage>[0];
  manager.appendMessage(user);
  manager.appendMessage(assistant);
}

function parseArgs(values: string[]): { outputDir?: string; model?: string } {
  const parsed: Record<string, string> = {};
  for (let index = 0; index < values.length; index += 1) {
    const key = values[index];
    if (!key.startsWith("--")) continue;
    parsed[key.slice(2)] = values[index + 1] ?? "";
    index += 1;
  }
  return { outputDir: parsed["output-dir"], model: parsed.model };
}
