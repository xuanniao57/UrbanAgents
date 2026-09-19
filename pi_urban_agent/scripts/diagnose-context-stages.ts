import { spawn, spawnSync } from "node:child_process";
import { createServer } from "node:http";
import { appendFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { createHash } from "node:crypto";
import { SessionManager } from "@earendil-works/pi-coding-agent";
import { applyProviderCompatibility } from "../src/core/provider-compat.js";
import { FAIR_PROTOCOL, fairTaskPrompt } from "../src/core/fair-module-evaluation.js";

const args = Object.fromEntries(process.argv.slice(2).reduce<string[][]>((a, v, i, all) => v.startsWith("--") ? [...a, [v.slice(2), all[i + 1]]] : a, []));
const root = process.cwd();
const out = resolve(args.out ?? "evaluation/context_diagnosis_20260830/fixed_4b");
const model = args.model ?? "qwen3.5:4b-urban8k";
const thinking = args.thinking ?? "off";
const mode = args.mode ?? "all";
const task = args.task ?? "context";
if (!["context", "plan", "reviewer"].includes(task)) throw new Error("Unknown task");
if (task !== "context" && mode !== "fresh") throw new Error("Plan/reviewer tasks start from a fresh session");
await mkdir(out, { recursive: true });
// A diagnostic never overwrites an earlier run.
await writeFile(resolve(out, "diagnostic.lock"), new Date().toISOString(), { flag: "wx" });
let stage = "startup"; let requestIndex = 0;
const timelines: any[] = [];
const record = async (entry: any) => { const row = { time: new Date().toISOString(), stage, ...entry }; timelines.push(row); await appendFile(resolve(out, "timeline.jsonl"), JSON.stringify(row) + "\n"); };
const controllers = new Set<AbortController>();
const proxy = createServer(async (req, res) => {
  const id = ++requestIndex; const started = Date.now(); const currentStage = stage;
  const chunks: Buffer[] = []; for await (const chunk of req) chunks.push(chunk);
  const parsed = JSON.parse(Buffer.concat(chunks).toString());
  if (args.temperature !== undefined) parsed.temperature = Number(args.temperature);
  if (args.seed !== undefined) parsed.seed = Number(args.seed);
  const payload = JSON.stringify(parsed);
  // Loopback-only proxy stores research payloads, never authorization headers.
  await writeFile(resolve(out, `request_${id}.json`), payload);
  const ac = new AbortController(); controllers.add(ac);
  let raw = ""; let tail = ""; let firstMs: number | undefined; let answerChars = 0; let reasoningChars = 0; let finish: any; let usage: any;
  res.on("close", () => { if (!res.writableEnded) ac.abort(); });
  await record({ event: "request_start", id, requestStage: currentStage, maxTokens: parsed.max_tokens, maxCompletionTokens: parsed.max_completion_tokens, reasoning: parsed.reasoning_effort, messageCount: parsed.messages?.length });
  try {
    const r = await fetch(`http://127.0.0.1:11434${req.url}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: payload, signal: ac.signal });
    res.writeHead(r.status, { "Content-Type": r.headers.get("content-type") ?? "text/event-stream" });
    for await (const chunk of r.body!) {
      firstMs ??= Date.now() - started;
      const t = new TextDecoder().decode(chunk); raw += t; tail += t; res.write(chunk);
      const lines = tail.split("\n"); tail = lines.pop()!;
      for (const line of lines) if (line.startsWith("data: ") && !line.includes("[DONE]")) {
        const d = JSON.parse(line.slice(6)); const c = d.choices?.[0];
        answerChars += c?.delta?.content?.length ?? 0;
        reasoningChars += (c?.delta?.reasoning ?? c?.delta?.reasoning_content ?? "").length;
        if (c?.finish_reason) finish = c.finish_reason;
        if (d.usage) usage = d.usage;
      }
    }
    res.end();
  } catch (error) { await record({ event: "request_error", id, message: String(error) }); res.destroy(); }
  finally {
    controllers.delete(ac);
    await writeFile(resolve(out, `response_${id}.sse`), raw);
    await record({ event: "request_end", id, requestStage: currentStage, durationMs: Date.now() - started, firstMs, answerChars, reasoningChars, finish, usage, aborted: ac.signal.aborted });
  }
});
await new Promise<void>((yes) => proxy.listen(0, "127.0.0.1", yes));
const port = (proxy.address() as { port: number }).port;
const cfg = resolve(out, "runtime"); await mkdir(cfg);
const baseModel = { id: model, name: model, reasoning: true, input: ["text"], cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }, contextWindow: 8192, maxTokens: 2048 };
await writeFile(resolve(cfg, "models.json"), JSON.stringify({ providers: { "local-ollama": { api: "openai-completions", apiKey: "ollama-local", baseUrl: `http://127.0.0.1:${port}/v1`, models: [args.compat === "legacy" ? baseModel : applyProviderCompatibility("local-ollama", baseModel)] } } }));
await writeFile(resolve(cfg, "settings.json"), JSON.stringify({ compaction: { enabled: true, reserveTokens: 1638, keepRecentTokens: 1638 }, retry: { enabled: false, maxRetries: 0 } }));
const runDir = resolve(out, "research");
if (args["source-state"]) {
  await mkdir(runDir);
  const state = JSON.parse(await readFile(resolve(args["source-state"]), "utf8"));
  state.runDir = runDir;
  await writeFile(resolve(runDir, "research_state.json"), JSON.stringify(state, null, 2));
} else {
const fixture = spawnSync(process.execPath, ["--import", "tsx", "scripts/prepare-module-ablation-fixture.ts", "--task", task, "--run-dir", runDir, ...(task !== "context" ? ["--protocol", FAIR_PROTOCOL] : [])], { cwd: root, windowsHide: true, encoding: "utf8" });
if (fixture.status !== 0) throw new Error(fixture.stderr);
}
const original = JSON.parse(await readFile(resolve(runDir, "research_state.json"), "utf8"));
await writeFile(resolve(out, "state_before.json"), JSON.stringify(original, null, 2));
const sessionDir = resolve(out, "session"); await mkdir(sessionDir);
let sessionFile: string;
if (args.resume) {
  const entries = (await readFile(resolve(args.resume), "utf8")).trim().split(/\r?\n/).map((line) => JSON.parse(line));
  let boundary = entries.findIndex((e) => e.type === "compaction");
  if (args["resume-last"] === "true") {
    for (let i = entries.length - 1; i >= 0; i--) {
      if (entries[i].type === "compaction") { boundary = i; break; }
    }
  }
  if (boundary < 0) throw new Error("No completed source compaction to resume");
  const prefix = entries.slice(0, boundary + 1).map((e) => {
    if (e.type === "custom" && e.data?.runDir) e.data.runDir = runDir;
    return e;
  });
  sessionFile = resolve(sessionDir, "resumed.jsonl");
  await writeFile(sessionFile, prefix.map((e) => JSON.stringify(e)).join("\n") + "\n");
} else if (mode === "natural" || mode === "fresh") {
  const manager = SessionManager.create(root, sessionDir); sessionFile = manager.getSessionFile()!;
} else {
  const prepared = spawnSync(process.execPath, ["--import", "tsx", "scripts/prepare-context-ablation-session.ts", "--output-dir", sessionDir, "--model", model], { cwd: root, windowsHide: true, encoding: "utf8" });
  if (prepared.status !== 0) throw new Error(prepared.stderr);
  sessionFile = JSON.parse(prepared.stdout).sessionFile;
}
const child = spawn(process.execPath, ["node_modules/@earendil-works/pi-coding-agent/dist/cli.js", "-a", "-e", ".pi/extensions/urban-agent.ts", "--no-extensions", "--no-skills", "--no-prompt-templates", "--no-builtin-tools", "--no-context-files", "--offline", "--mode", "rpc", "--thinking", thinking, "--provider", "local-ollama", "--model", model, "--session", sessionFile], {
  cwd: root, windowsHide: true, env: { ...process.env, PI_CODING_AGENT_DIR: cfg, PI_OFFLINE: "1", URBAN_PI_RUN_DIR: runDir, URBAN_PI_REPOSITORY_ROOT: resolve(root, ".."), URBAN_CONTEXT_MODE: args.condition === "pi_default_compaction" ? "pi_default" : "hybrid_recall", URBAN_EVAL_CONDITION: args.condition ?? "urban_full", URBAN_EVAL_PROTOCOL: task === "context" ? "context-separated-v1" : FAIR_PROTOCOL, URBAN_DISABLED_TOOLS: args.condition === "urban_no_planner" ? "urban_commit_route_family,urban_open_branch,urban_prepare_worker" : args.condition === "urban_no_reviewer" ? "urban_prepare_review,urban_record_review" : "", URBAN_AUTHENTICATED_ACTOR: "diagnostic_human_20260830", URBAN_CONTEXT_WINDOW: "8192", URBAN_MAX_OUTPUT_TOKENS: "2048", URBAN_TOOL_ERROR_BUDGET: "4", URBAN_TOOL_CALL_BUDGET: "16" },
});
let buffer = ""; let rpcId = 0; let events: any[] = [];
const pending = new Map<string, { resolve: (e: any) => void; reject: (e: Error) => void }>();
let settled: (() => void) | undefined;
child.stderr.on("data", (chunk) => { void appendFile(resolve(out, "stderr.txt"), chunk); });
child.stdout.on("data", (chunk) => {
  buffer += chunk.toString(); const lines = buffer.split("\n"); buffer = lines.pop()!;
  for (const line of lines) if (line.trim()) {
    try {
      const e = JSON.parse(line); events.push(e); void appendFile(resolve(out, "pi_events.jsonl"), line + "\n");
      if (["compaction_start", "compaction_end", "agent_settled", "tool_execution_start", "tool_execution_end"].includes(e.type)) void record({ event: e.type, toolName: e.toolName, reason: e.reason, errorMessage: e.errorMessage });
      if (e.type === "response" && pending.has(e.id)) { const p = pending.get(e.id)!; pending.delete(e.id); e.success ? p.resolve(e) : p.reject(new Error(JSON.stringify(e))); }
      if (e.type === "agent_settled") { settled?.(); settled = undefined; }
    } catch { /* diagnostics remain in stderr */ }
  }
});
child.on("exit", () => { for (const p of pending.values()) p.reject(new Error("Pi exited")); pending.clear(); });
const rpc = (data: any) => new Promise<any>((yes, no) => { const id = `d${++rpcId}`; pending.set(id, { resolve: yes, reject: no }); child.stdin.write(JSON.stringify({ ...data, id }) + "\n"); });
async function deadline<T>(promise: Promise<T>, seconds: number): Promise<T> {
  let timer: NodeJS.Timeout | undefined;
  try { return await Promise.race([promise, new Promise<never>((_, no) => { timer = setTimeout(() => no(new Error(`Stage ${stage} exceeded ${seconds}s`)), seconds * 1000); })]); }
  finally { if (timer) clearTimeout(timer); }
}
async function turn(message: string) {
  const begin = events.length;
  const done = new Promise<void>((yes) => { settled = yes; });
  await writeFile(resolve(out, `prompt_${stage}.txt`), message);
  let complete = false;
  try {
    await deadline(rpc({ type: "prompt", message }), 30);
    await deadline(done, Number(args.timeout ?? 420));
    complete = true;
  } finally {
    const messages = events.slice(begin).filter((e) => e.type === "message_end" && e.message?.role === "assistant").map(e => e.message);
    const texts = (m: any) => (m?.content ?? []).filter((c: any) => c.type === "text").map((c: any) => c.text).join("\n");
    const answer = messages.map(texts).filter(Boolean).join("\n\n");
    await writeFile(resolve(out, `answer_${stage}.txt`), answer);
    await writeFile(resolve(out, `final_answer_${stage}.txt`), texts(messages.at(-1)));
    await writeFile(resolve(out, `state_${stage}.json`), await readFile(resolve(runDir, "research_state.json")));
    await record({ event: complete ? "stage_complete" : "stage_incomplete", answerChars: answer.length });
  }
}
const roleIds = [...new Set<string>(original.humanDecisions.filter((d: any) => d.decision !== "approve_claim").flatMap((d: any) => d.branchIds))];
const target = roleIds.find((id) => original.nodes[id].status === "deferred")!;
const recoveryPrompt = mode === "verify" && args["verify-scope"] === "active"
  ? "Read-only state check: report the current active branch ID, its latest human-assigned role, and the currently open research questions. Use current external state, not historical review text. Do not change any state or repeat earlier tasks."
  : "Read-only recovery: recover all analytical routes with explicit human decisions in the current Research Git Tree, excluding archived distractors. Report each exact ID, grid support, model/neighbourhood, last human-assigned role and available held-out R². Use external state; do not infer from dialogue. Do not alter any decision or phase. Return absent for unavailable facts.";
const humanPrompt = `I have reviewed the comparison. Retain ${target} as sensitivity evidence for the next comparison, not the main route. Do not claim a unique correct process scale. Record this human decision, invalidate conflicting old approval if necessary, and clear any resolved pending question. Keep metrics and other route roles unchanged. Then briefly confirm the updated role and remaining claim boundary.`;
try {
  await deadline(rpc({ type: "get_state" }), 40);
  if (args.resume) {
    stage = "resume_compacted"; await record({ event: "stage_complete", source: args.resume });
  } else if (mode === "fresh") {
    stage = "fresh_start"; await record({event:"stage_complete",source:"empty conversation; unchanged research fixture"});
  } else if (mode !== "natural") {
    stage = "compaction"; await record({ event: "stage_start" });
    const compact = await deadline(rpc({ type: "compact" }), Number(args.timeout ?? 420));
    await writeFile(resolve(out, "compaction.json"), JSON.stringify(compact, null, 2));
    await record({ event: "stage_complete", summaryChars: compact.data?.summary?.length });
  } else {
    // Real model-generated turns and real reported usage, no forged usage or manual compact command.
    for (let i = 1; i <= 18; i++) {
      stage = `natural_${i}`;
      const log = Array.from({ length: 12 }, (_, j) => `Provisional note ${i}.${j}: inspect ${200 + ((i + j) % 7) * 100} m support. These are discussion alternatives, not executed findings or approved roles. Exact decisions remain in external research state.`).join("\n");
      await turn(args["history-style"] === "neutral"
        ? `For this turn, briefly identify one uncertainty in these provisional spatial-scale alternatives. This is discussion, not authorization to alter research state.\n${log}`
        : `Archive this non-authoritative discussion for later. Do not call tools or change state. Reply only ACK.\n${log}`);
      if (events.some((e) => e.type === "compaction_end" && e.reason === "threshold" && !e.aborted && e.result)) break;
    }
    if (!events.some((e) => e.type === "compaction_end" && e.reason === "threshold" && !e.aborted && e.result)) throw new Error("Natural threshold compaction did not complete");
  }
  if (task !== "context") {
    stage = "task"; await record({ event: "stage_start" });
    await turn(fairTaskPrompt(task as "plan" | "reviewer", JSON.parse(await readFile(resolve(runDir, "common_task_evidence.json"), "utf8"))));
  } else if (mode !== "compact") {
    stage = "recovery"; await record({ event: "stage_start" }); await turn(recoveryPrompt);
    if (mode !== "verify") { stage = "human_patch"; await record({ event: "stage_start" }); await turn(humanPrompt); }
  }
  await record({ event: "diagnostic_complete" });
} catch (error) { await record({ event: "diagnostic_failure", message: String(error) }); }
finally {
  for (const ac of controllers) ac.abort();
  child.stdin.end();
  if (child.exitCode === null) child.kill();
  proxy.closeAllConnections(); proxy.close();
  const final = JSON.parse(await readFile(resolve(runDir, "research_state.json"), "utf8"));
  const hash = (x: any) => createHash("sha256").update(JSON.stringify(x)).digest("hex");
  await writeFile(resolve(out, "diagnostic_summary.json"), JSON.stringify({ task, model, thinking, mode, historyStyle: args["history-style"] ?? "ack", temperature: args.temperature, seed: args.seed, protocol: task === "context" ? "context-separated-v1" : FAIR_PROTOCOL, compatibility: args.compat ?? "fixed", condition: args.condition ?? "urban_full", roleIds, target, artifactMetricsUnchanged: hash(original.artifacts) === hash(final.artifacts), newHumanDecisions: final.humanDecisions.slice(original.humanDecisions.length), pendingHumanPatches: final.pendingHumanPatches, finalClaim: final.finalClaim, stages: timelines.filter((e) => e.event === "stage_complete" || e.event === "stage_incomplete" || e.event === "diagnostic_failure"), requests: timelines.filter((e) => e.event === "request_end") }, null, 2));
  await writeFile(resolve(out, "pi_events.jsonl"), events.map(e => JSON.stringify(e)).join("\n") + "\n");
  console.log(JSON.stringify({ out, finalStage: stage, stages: timelines.filter((e) => e.event === "stage_complete" || e.event === "diagnostic_failure") }));
}
