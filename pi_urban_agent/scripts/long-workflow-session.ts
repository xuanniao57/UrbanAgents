/**
 * Persistent, fresh-session Pi RPC harness for an interactive context ablation.
 *
 * Usage: npx tsx scripts/long-workflow-session.ts --out /absolute/run
 *   --condition urban_full --data-root /paper/long_case/data
 *   [--model Qwen3.5-27B] [--base-url http://127.0.0.1:8000/v1]
 *   [--window 16384] [--output-tokens 3072]
 *
 * Publish UTF-8 inbox/001.json, inbox/002.json, ... containing {"message":"..."}
 * using an atomic rename. Each file is consumed exactly once, without retries.
 * The runtime owns the research directory and gives the model only relative
 * workspace paths. The first prompt asks the model to initialize the scientific
 * contract, never to choose filesystem locations.
 * Touch out/STOP to exit after the current turn. Never manufactures research
 * state/history and never requests compaction manually. Reusing an out is refused.
 */
import { spawn, spawnSync, type ChildProcessWithoutNullStreams } from "node:child_process";
import { appendFileSync } from "node:fs";
import { access, copyFile, cp, mkdir, readFile, readdir, rename, stat, writeFile } from "node:fs/promises";
import { createServer } from "node:http";
import { delimiter, dirname, isAbsolute, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { SessionManager } from "@earendil-works/pi-coding-agent";
import { resolveCompactionSettings } from "../src/core/model-context.js";

type Json = Record<string, any>;
type Turn = { number: number; name: string; dir: string; started: number; events: Json[]; requestIds: number[]; budgetStop?: string };
const options: Record<string, string> = {};
const allowed = new Set(["out", "condition", "data-root", "model", "base-url", "window", "output-tokens", "provider", "deadline", "seed"]);
for (let i = 2; i < process.argv.length; i += 2) {
  const key = process.argv[i]?.replace(/^--/, "");
  const value = process.argv[i + 1];
  if (!process.argv[i]?.startsWith("--") || !allowed.has(key) || !value || value.startsWith("--")) {
    throw new Error(`Expected --name value; supported options: ${[...allowed].join(", ")}`);
  }
  if (options[key] !== undefined) throw new Error(`Repeated option --${key}`);
  options[key] = value;
}
if (!options.out || !options["data-root"]) throw new Error("--out and --data-root are required");
const condition = options.condition ?? "urban_full";
const frameworkConditions = ["pi_plain", "pi_default_compaction", "urban_no_planner", "urban_no_reviewer", "urban_no_context", "urban_full"];
if (!frameworkConditions.includes(condition)) throw new Error("Unknown --condition");
function positiveInteger(value: string, name: string): number {
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed <= 0) throw new Error(`${name} must be a positive integer`);
  return parsed;
}
const contextWindow = positiveInteger(options.window ?? "16384", "--window");
const outputTokens = positiveInteger(options["output-tokens"] ?? "3072", "--output-tokens");
const seed = positiveInteger(options.seed ?? "42", "--seed");
if (contextWindow < 4096 || outputTokens >= contextWindow) throw new Error("Require window >= 4096 and output-tokens < window");
const baseUrl = new URL(options["base-url"] ?? "http://127.0.0.1:8000/v1");
if (!["http:", "https:"].includes(baseUrl.protocol) || baseUrl.username || baseUrl.password || baseUrl.search || baseUrl.hash) {
  throw new Error("--base-url must be HTTP(S), without credentials, query, or fragment");
}
const upstream = `${baseUrl.toString().replace(/\/$/, "")}/chat/completions`;
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(root, "..");
const out = resolve(options.out);
const dataRoot = resolve(options["data-root"]);
const dataRelative = relative(repositoryRoot, dataRoot);
if (isAbsolute(dataRelative) || dataRelative === ".." || dataRelative.startsWith(`..${sep}`)) {
  throw new Error("--data-root must be under the paper repository root (the unchanged Urban Python tool's allowed root)");
}
await access(dataRoot);
const model = options.model ?? "Qwen3.5-27B";
const contextMode = condition === "urban_no_context" || condition === "pi_plain" || condition === "pi_default_compaction" ? "pi_default" : "hybrid_recall";
const provider = options.provider ?? "local-vllm";
const upstreamApiKey = process.env.URBAN_UPSTREAM_API_KEY?.trim();
const localProvider = provider === "local-vllm" || provider === "local-ollama";
if (!localProvider && !upstreamApiKey) {
  throw new Error("URBAN_UPSTREAM_API_KEY must be configured for a non-local provider");
}
const expectedRunDir = resolve(out, "research");
const cfg = resolve(out, "runtime");
const cwd = resolve(out, "workspace");
const sessionDir = resolve(out, "session");
const inbox = resolve(out, "inbox");
const requestsDir = resolve(out, "requests");
const turnDeadlineMs = positiveInteger(options.deadline ?? '600', '--deadline') * 1000;
const actor = "simulated_researcher";
const python = resolve(process.env.URBAN_PI_PYTHON || resolve(root, "../.venv-section4/Scripts/python.exe"));
const now = () => new Date().toISOString();
async function exists(path: string): Promise<boolean> {
  try { await access(path); return true; }
  catch (error) { if ((error as NodeJS.ErrnoException).code === "ENOENT") return false; throw error; }
}
await mkdir(out, { recursive: true });
await writeFile(resolve(out, "session.lock"), JSON.stringify({ pid: process.pid, startedAt: now() }), { flag: "wx" });
for (const path of [expectedRunDir, cfg, cwd, sessionDir, resolve(out, "turns"), requestsDir]) {
  if (await exists(path)) throw new Error(`Fresh-run requirement: path already exists: ${path}`);
}
await Promise.all([cfg, cwd, sessionDir, inbox, requestsDir, resolve(out, "turns")].map(path => mkdir(path, { recursive: true })));
await Promise.all([resolve(cwd, "work"), resolve(cwd, "outputs")].map(path => mkdir(path, { recursive: true })));
await cp(dataRoot, resolve(cwd, "data"), { recursive: true, force: false, errorOnExist: true });
await copyFile(resolve(root, "long_case/data_contract.json"), resolve(cwd, "data_contract.json"));
const inputNames = (await readdir(resolve(cwd, "data"))).sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
const inventoryRows = await Promise.all(inputNames.map(async (name) => `- data/${name} (${(await stat(resolve(cwd, "data", name))).size} bytes)`));
const representativeHeader = (await readFile(resolve(cwd, "data/model_ready_200m.csv"), "utf8")).split(/\r?\n/, 1)[0];
await writeFile(resolve(cwd, "DATA_INVENTORY.md"), `# Runtime-verified input inventory

${inventoryRows.join("\n")}

Representative model-ready CSV header (200 m):

\`${representativeHeader}\`
`, "utf8");
await access(python);
const packageProbe = spawnSync(python, ["-c", "import sys,numpy,pandas,sklearn; print(sys.version.split()[0]); print(numpy.__version__); print(pandas.__version__); print(sklearn.__version__)"], { encoding: "utf8", windowsHide: true });
if (packageProbe.status !== 0) throw new Error(`Python environment probe failed: ${packageProbe.stderr}`);
const [pythonVersion, numpyVersion, pandasVersion, sklearnVersion] = packageProbe.stdout.trim().split(/\r?\n/);
const completionInstruction = condition === "pi_plain"
  ? "Save one completed script/result pair under `work/` and `outputs/`, then stop for the next human message."
  : "Commit one completed script/result pair with `urban_commit_run`, then stop for Reviewer inspection.";
await writeFile(resolve(cwd, "WORKSPACE.md"), `# Isolated urban-research workspace

- Read \`data_contract.json\` for the scientific contract and \`DATA_INVENTORY.md\` for the runtime-verified file inventory and representative schema.
- Inspect only needed files under \`data/\`; inputs are copies and must not be edited.
- Write model-created reusable Python code under \`work/\`.
- Write produced tables, logs, and figures under \`outputs/\`.
- Invoke Python as \`python\`; available core packages are numpy ${numpyVersion}, pandas ${pandasVersion}, and scikit-learn ${sklearnVersion} on Python ${pythonVersion}.
- Do not install or upgrade packages during a run; implement the analysis with the listed environment.
- The outcome and covariate names in \`data_contract.json\` are authoritative. Never construct X by taking every column left after an exclusion list, because identifiers, raw components, coordinates, or the outcome itself may remain.
- No prewritten analysis script or hidden recipe is present. Build the requested analysis from the contract and inspected columns.
- Use relative paths. ${completionInstruction}
`, "utf8");
let active: Turn | undefined;
let activeRunDir = expectedRunDir;
let stopRequested = false;
let shuttingDown = false;
let child: ChildProcessWithoutNullStreams | undefined;
let childFailure: Error | undefined;
let requestIndex = 0;
let rpcIndex = 0;
let turnNumber = 0;
let settled: (() => void) | undefined;
const pending = new Map<string, { resolve: (event: Json) => void; reject: (error: Error) => void }>();
const controllers = new Map<number, AbortController>();
const requests = new Map<number, Json>();
const requestJobs = new Set<Promise<void>>();
function timeline(event: string, data: Json = {}): void {
  appendFileSync(resolve(out, "timeline.jsonl"), JSON.stringify({ time: now(), turn: active?.number ?? null, event, ...data }) + "\n");
}
async function json(path: string, value: unknown): Promise<void> {
  await writeFile(path, JSON.stringify(value, null, 2) + "\n");
}
async function status(idle: boolean, data: Json = {}): Promise<void> {
  const value = { time: now(), pid: process.pid, idle, stopped: false, turn: active?.number ?? turnNumber,
    nextTurn: (turnNumber + 1).toString().padStart(3, "0"), condition, runDir: activeRunDir, ...data };
  const temp = resolve(out, "status.json.tmp");
  await json(temp, value);
  await rename(temp, resolve(out, "status.json"));
}
async function snapshot(path: string): Promise<void> {
  const statePath = resolve(activeRunDir, "research_state.json");
  if (await exists(statePath)) await writeFile(path, await readFile(statePath));
  else await json(path, null);
}
async function deadline<T>(promise: Promise<T>, milliseconds: number, label: string): Promise<T> {
  let timer: NodeJS.Timeout | undefined;
  try {
    return await Promise.race([promise, new Promise<never>((_, reject) => {
      timer = setTimeout(() => reject(new Error(`${label} exceeded ${milliseconds / 1000}s`)), milliseconds);
    })]);
  } finally { if (timer) clearTimeout(timer); }
}

// Only the model's JSON payload is persisted. Incoming headers, environment
// values and the upstream API key are never written to the run directory.
const proxy = createServer((req, res) => {
  const job = (async () => {
    if (req.method !== "POST" || req.url?.split("?")[0] !== "/v1/chat/completions") {
      res.writeHead(404); res.end("Only POST /v1/chat/completions is supported"); return;
    }
    const id = ++requestIndex;
    const turn = active;
    turn?.requestIds.push(id);
    const dir = resolve(requestsDir, String(id).padStart(6, "0"));
    await mkdir(dir);
    const start = Date.now();
    const ac = new AbortController();
    controllers.set(id, ac);
    const summary: Json = { id, turn: turn?.number ?? null, startedAt: now(), temperature: 0, seed, enableThinking: false };
    let raw = "";
    let tail = "";
    let firstMs: number | undefined;
    let answerChars = 0;
    let reasoningChars = 0;
    const decoder = new TextDecoder();
    const parseLine = (line: string) => {
      if (!line.startsWith("data:")) return;
      const content = line.slice(5).trim();
      if (!content || content === "[DONE]") return;
      try {
        const event = JSON.parse(content);
        if (event.usage) summary.usage = event.usage;
        if (event.error) summary.providerError = event.error;
        for (const choice of event.choices ?? []) {
          answerChars += (choice.delta?.content ?? "").length;
          reasoningChars += (choice.delta?.reasoning ?? choice.delta?.reasoning_content ?? "").length;
          if (choice.finish_reason) summary.finishReason = choice.finish_reason;
        }
      } catch { summary.unparsedSseLines = (summary.unparsedSseLines ?? 0) + 1; }
    };
    res.on("close", () => { if (!res.writableEnded) ac.abort(); });
    try {
      const chunks: Buffer[] = [];
      for await (const chunk of req) chunks.push(Buffer.from(chunk));
      const payload = JSON.parse(Buffer.concat(chunks).toString("utf8"));
      payload.temperature = 0;
      if (localProvider) {
        payload.seed = seed;
        payload.chat_template_kwargs = { ...payload.chat_template_kwargs, enable_thinking: false };
      } else {
        // Bailian's OpenAI-compatible HTTP API accepts enable_thinking at the
        // top level. Do not send local template controls or an undocumented
        // provider seed merely to mimic the local server.
        delete payload.seed;
        delete payload.chat_template_kwargs;
        payload.enable_thinking = false;
      }
      if (provider === 'local-ollama') payload.reasoning_effort = 'none';
      payload.max_tokens = Math.min(outputTokens, payload.max_tokens ?? payload.max_completion_tokens ?? outputTokens);
      delete payload.max_completion_tokens;
      if (provider !== 'local-ollama') delete payload.reasoning_effort;
      if (payload.stream) payload.stream_options = { ...payload.stream_options, include_usage: true };
      await json(resolve(dir, "request.json"), payload);
      Object.assign(summary, { model: payload.model, maxTokens: payload.max_tokens, messageCount: payload.messages?.length,
        tools: payload.tools?.map((tool: Json) => tool.function?.name) ?? [], stream: Boolean(payload.stream) });
      timeline("request_start", { id, requestTurn: summary.turn, maxTokens: payload.max_tokens, messageCount: payload.messages?.length });
      const response = await fetch(upstream, { method: "POST", body: JSON.stringify(payload),
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${localProvider ? "local-dummy" : upstreamApiKey}` }, signal: ac.signal });
      summary.httpStatus = response.status;
      summary.contentType = response.headers.get("content-type");
      res.writeHead(response.status, { "Content-Type": summary.contentType ?? "text/event-stream" });
      if (!response.body) throw new Error("Upstream response has no body");
      for await (const chunk of response.body) {
        firstMs ??= Date.now() - start;
        const part = decoder.decode(chunk, { stream: true });
        raw += part; tail += part;
        appendFileSync(resolve(dir, "response.sse"), part);
        res.write(chunk);
        const lines = tail.split("\n"); tail = lines.pop() ?? "";
        lines.forEach(parseLine);
      }
      const final = decoder.decode(); raw += final; tail += final;
      if (final) appendFileSync(resolve(dir, "response.sse"), final);
      if (tail) parseLine(tail);
      if (!summary.contentType?.includes("text/event-stream")) {
        try { const body = JSON.parse(raw); summary.usage = body.usage; summary.providerError = body.error; }
        catch { /* Raw body remains available for non-JSON errors. */ }
      }
      res.end();
    } catch (error) {
      summary.error = String(error);
      timeline("request_error", { id, requestTurn: summary.turn, message: String(error) });
      if (!res.headersSent) { res.writeHead(502, { "Content-Type": "application/json" }); res.end(JSON.stringify({ error: { message: String(error) } })); }
      else res.destroy();
    } finally {
      controllers.delete(id);
      Object.assign(summary, { endedAt: now(), durationMs: Date.now() - start, firstMs, answerChars, reasoningChars, aborted: ac.signal.aborted });
      if (!await exists(resolve(dir, "response.sse"))) await writeFile(resolve(dir, "response.sse"), raw);
      requests.set(id, summary);
      await json(resolve(dir, "summary.json"), summary);
      timeline("request_end", summary);
    }
  })();
  requestJobs.add(job);
  void job.catch(error => { childFailure = new Error(`Request logging failed: ${String(error)}`); stopRequested = true; res.destroy(); })
    .finally(() => requestJobs.delete(job));
});

function rpc(command: Json): Promise<Json> {
  if (!child || childFailure) return Promise.reject(childFailure ?? new Error("Pi is not running"));
  const id = `interactive-${++rpcIndex}`;
  return new Promise((yes, no) => {
    pending.set(id, { resolve: yes, reject: no });
    child!.stdin.write(JSON.stringify({ ...command, id }) + "\n", error => {
      if (error) { pending.delete(id); no(error); }
    });
  });
}
function receive(event: Json, line: string): void {
  appendFileSync(resolve(out, "pi_events.jsonl"), line + "\n");
  if (active) { active.events.push(event); appendFileSync(resolve(active.dir, "events.jsonl"), line + "\n"); }
  // Include schema-rejected calls, which bypass Pi extension tool_call/tool_result.
  // This is an outer human-turn bound, not reset by internal compaction/restarts.
  if (active && !active.budgetStop && event.type === 'tool_execution_end') {
    const ends=active.events.filter(e=>e.type==='tool_execution_end');
    if (ends.length>=32 || (ends.length>=4 && ends.slice(-4).every(e=>e.isError))) {
      active.budgetStop=ends.length>=32 ? '32 outer-turn tool attempts' : '4 consecutive tool errors';
      timeline('outer_budget_stop',{reason:active.budgetStop});
      void rpc({type:'abort'}).catch(error=>timeline('abort_error',{error:String(error)}));
    }
  }
  if (["compaction_start", "compaction_end", "agent_settled", "tool_execution_start", "tool_execution_end"].includes(event.type)) {
    timeline(event.type, { toolName: event.toolName, toolCallId: event.toolCallId, args: event.args,
      isError: event.isError, reason: event.reason, errorMessage: event.errorMessage });
  }
  if (event.type === "tool_execution_end" && event.toolName === "urban_initialize" && !event.isError && event.result?.details?.runDir) {
    activeRunDir = resolve(event.result.details.runDir);
  }
  if (event.type === "response" && pending.has(event.id)) {
    const waiter = pending.get(event.id)!; pending.delete(event.id);
    event.success ? waiter.resolve(event) : waiter.reject(new Error(event.error ?? JSON.stringify(event)));
  }
  if (event.type === "agent_settled") { settled?.(); settled = undefined; }
  // Never fabricate human authorization in response to an extension dialog.
  if (event.type === "extension_ui_request" && ["confirm", "select", "input", "editor"].includes(event.method)) {
    child?.stdin.write(JSON.stringify({ type: "extension_ui_response", id: event.id, cancelled: true }) + "\n");
    timeline("human_ui_cancelled", { requestId: event.id, method: event.method });
  }
}
async function runTurn(path: string, number: number): Promise<void> {
  const name = String(number).padStart(3, "0");
  const dir = resolve(out, "turns", name);
  await mkdir(dir);
  await writeFile(resolve(dir, "events.jsonl"), "");
  active = { number, name, dir, started: Date.now(), events: [], requestIds: [] };
  await status(false, { phase: "running" });
  await snapshot(resolve(dir, "state_before.json"));
  let outcome = "completed";
  let failure: string | undefined;
  let promptSubmitted = false;
  let agentSettled = false;
  let message = "";
  const done = new Promise<void>(yes => { settled = () => { agentSettled = true; yes(); }; });
  try {
    const queued = JSON.parse(await readFile(path, "utf8"));
    if (typeof queued.message !== "string" || !queued.message.trim() || Object.keys(queued).some(key => key !== "message")) {
      throw new Error("Inbox entry must contain only a nonempty string message");
    }
    message = queued.message;
    await writeFile(resolve(dir, "prompt.txt"), message);
    timeline("turn_start", { inbox: path });
    promptSubmitted = true;
    await deadline((async () => {
      // Pi may compact before acknowledging prompt. That work belongs to the
      // same human-turn deadline, not a shorter second timeout.
      await rpc({ type: "prompt", message });
      await done;
      if (childFailure) throw childFailure;
    })(), turnDeadlineMs, "Human turn");
  } catch (error) {
    outcome = "failed"; failure = String(error);
    timeline("turn_failure", { message: failure });
    for (const ac of controllers.values()) ac.abort();
    if (promptSubmitted && !agentSettled && !childFailure) {
      try { await deadline(rpc({ type: "abort" }), 15_000, "Pi abort"); }
      catch (abortError) { failure += `; ${String(abortError)}`; stopRequested = true; }
    }
    if (childFailure) stopRequested = true;
  } finally {
    settled = undefined;
    await deadline(Promise.allSettled([...requestJobs]), 15_000, "Request log drain").catch(error => {
      failure = `${failure ?? ""}; ${String(error)}`; outcome = "failed"; stopRequested = true;
    });
    if (!stopRequested) {
      try {
        const state = await deadline(rpc({ type: "get_state" }), 5_000, "Pi idle check");
        if (state.data?.isStreaming || state.data?.isCompacting || state.data?.pendingMessageCount) {
          throw new Error("Pi is not idle after turn; stopping instead of overlapping human turns");
        }
      } catch (error) { failure = `${failure ?? ""}; ${String(error)}`; outcome = "failed"; stopRequested = true; }
    }
    const turn = active!;
    const messages = turn.events.filter(event => event.type === "message_end" && event.message?.role === "assistant").map(event => event.message);
    const texts = (value: Json | undefined): string => (value?.content ?? []).filter((block: Json) => block.type === "text").map((block: Json) => block.text).join("\n");
    const assistantErrors = messages.filter(m => ["error", "aborted"].includes(m.stopReason)).map(m => ({ stopReason: m.stopReason, errorMessage: m.errorMessage }));
    const requestSummaries = turn.requestIds.map(id => requests.get(id) ?? { id, incomplete: true });
    const emptyLengthStop = requestSummaries.some(r => r.finishReason === "length" && !r.answerChars);
    if (turn.budgetStop || assistantErrors.length || emptyLengthStop || requestSummaries.some(r => r.error || r.providerError || r.httpStatus >= 400 || r.incomplete)) outcome = "failed";
    await writeFile(resolve(dir, "prompt.txt"), message);
    await writeFile(resolve(dir, "answer.txt"), messages.map(texts).filter(Boolean).join("\n\n"));
    await writeFile(resolve(dir, "final_answer.txt"), texts(messages.at(-1)));
    await snapshot(resolve(dir, "state_after.json"));
    await json(resolve(dir, "summary.json"), {
      turn: number, condition, contextMode, outcome, failure, budgetStop: turn.budgetStop, startedAt: new Date(turn.started).toISOString(),
      endedAt: now(), durationMs: Date.now() - turn.started, humanActor: actor, promptSubmitted, agentSettled,
      runDir: activeRunDir, expectedRunDir, runDirMatchesExpected: activeRunDir === expectedRunDir,
      eventCount: turn.events.length, assistantErrors,
      assistantUsage: messages.map(m => ({ model: m.model, stopReason: m.stopReason, usage: m.usage })),
      toolCalls: turn.events.filter(e => e.type === "tool_execution_start").map(e => ({ toolCallId: e.toolCallId, toolName: e.toolName, args: e.args })),
      toolErrors: turn.events.filter(e => e.type === "tool_execution_end" && e.isError),
      compactions: turn.events.filter(e => e.type === "compaction_start" || e.type === "compaction_end"),
      requestUsageTotals: requestSummaries.reduce((total, request) => ({
        promptTokens: total.promptTokens + (request.usage?.prompt_tokens ?? 0),
        completionTokens: total.completionTokens + (request.usage?.completion_tokens ?? 0),
        totalTokens: total.totalTokens + (request.usage?.total_tokens ?? 0),
        requestsWithUsage: total.requestsWithUsage + Number(Boolean(request.usage)),
      }), { promptTokens: 0, completionTokens: 0, totalTokens: 0, requestsWithUsage: 0 }),
      requests: requestSummaries,
    });
    timeline("turn_end", { outcome, failure });
    turnNumber = number; active = undefined;
    await status(!stopRequested, { phase: stopRequested ? "stopping" : "waiting", lastOutcome: outcome, lastFailure: failure });
  }
}

process.on("SIGINT", () => { stopRequested = true; });
process.on("SIGTERM", () => { stopRequested = true; });
let finalError: string | undefined;
try {
  await status(false, { phase: "starting" });
  await new Promise<void>((yes, no) => { proxy.once("error", no); proxy.listen(0, "127.0.0.1", yes); });
  const port = (proxy.address() as { port: number }).port;
  const compaction = resolveCompactionSettings(contextWindow, outputTokens);
  await json(resolve(cfg, "models.json"), { providers: { [provider]: {
    api: "openai-completions", apiKey: "local-dummy", baseUrl: `http://127.0.0.1:${port}/v1`,
    models: [{ id: model, name: model, reasoning: false, input: ["text"], contextWindow, maxTokens: outputTokens,
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
      compat: { maxTokensField: "max_tokens", supportsStore: false, supportsDeveloperRole: false, supportsReasoningEffort: false } }],
  } } });
  await json(resolve(cfg, "settings.json"), { compaction, retry: { enabled: false, maxRetries: 0 } });
  const manager = SessionManager.create(cwd, sessionDir);
  const sessionFile = manager.getSessionFile();
  if (!sessionFile) throw new Error("Pi did not allocate a fresh session file");
  await json(resolve(out, "manifest.json"), {
    protocol: "framework-ablation-v1", startedAt: now(), condition, contextMode, model, provider,
    baseUrl: baseUrl.toString(), contextWindow, outputTokens, compaction, turnDeadlineMs,
    temperature: 0, seed, thinking: "off", enableThinking: false, humanActor: actor,
    providerSeedSent: localProvider,
    toolCallBudget: 32, toolErrorBudget: 4, automaticRetries: false, manualCompaction: false,
    repositoryRoot, dataRoot, expectedRunDir, cwd, sessionFile, python,
    workspaceLayout: { contract: "data_contract.json", inputs: "data/", code: "work/", outputs: "outputs/" },
    initialResearchState: null, initialConversation: "fresh empty Pi session", builtinTools: true, contextFiles: false,
    conditionScope: condition === "pi_plain"
      ? "Pure Pi baseline with generic file and terminal tools; no Urban modules or Research Tree extension"
      : "Same task, data, generic tools and model; the named Urban module is removed only in its corresponding condition",
  });
  const pythonPath = dirname(python);
  const disabledByCondition: Record<string, string> = {
    urban_no_planner: "urban_commit_route_family,urban_open_branch,urban_prepare_worker",
    urban_no_reviewer: "urban_prepare_review,urban_record_review",
  };
  const env = { ...process.env, PATH: `${pythonPath}${delimiter}${process.env.PATH ?? ""}`, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8", PI_CODING_AGENT_DIR: cfg, PI_OFFLINE: "1", URBAN_PI_RUN_DIR: expectedRunDir,
    URBAN_PI_WORKSPACE_ROOT: cwd, URBAN_PI_REPOSITORY_ROOT: cwd, URBAN_DATA_ROOT: resolve(cwd, "data"), URBAN_PI_PYTHON: python,
    URBAN_CONTEXT_MODE: contextMode, URBAN_EVAL_CONDITION: condition, URBAN_EVAL_PROTOCOL: "framework-ablation-v1",
    URBAN_DISABLED_TOOLS: disabledByCondition[condition] ?? "", URBAN_AUTHENTICATED_ACTOR: actor, URBAN_CONTEXT_PROFILE: "auto",
    URBAN_CONTEXT_WINDOW: String(contextWindow), URBAN_MAX_OUTPUT_TOKENS: String(outputTokens),
    URBAN_BUDGET_LOG_DIR: out,
    URBAN_TOOL_ERROR_BUDGET: "4", URBAN_TOOL_CALL_BUDGET: "32" };
  const piArgs = [resolve(root, "node_modules/@earendil-works/pi-coding-agent/dist/cli.js"), "-a"];
  if (condition !== "pi_plain") piArgs.push("-e", resolve(root, ".pi/extensions/urban-agent.ts"));
  piArgs.push("--no-extensions", "--no-skills", "--no-prompt-templates", "--no-context-files", "--offline", "--mode", "rpc", "--thinking", "off",
    "--provider", provider, "--model", model, "--session", sessionFile);
  child = spawn(process.execPath, piArgs, { cwd, env, windowsHide: true, stdio: "pipe" });
  let buffer = "";
  child.stdout.setEncoding("utf8");
  child.stderr.on("data", (chunk: Buffer) => appendFileSync(resolve(out, "stderr.txt"), chunk));
  child.stdout.on("data", (chunk: string) => {
    buffer += chunk;
    const lines = buffer.split("\n"); buffer = lines.pop() ?? "";
    for (const line of lines) if (line.trim()) {
      let event: Json;
      try { event = JSON.parse(line); }
      catch { appendFileSync(resolve(out, "stdout_non_json.txt"), line + "\n"); continue; }
      receive(event, line);
    }
  });
  const failed = (error: Error) => {
    childFailure = error; stopRequested = true;
    for (const waiter of pending.values()) waiter.reject(error);
    pending.clear(); settled?.(); settled = undefined;
  };
  child.on("error", failed);
  child.stdin.on("error", error => { if (!shuttingDown) failed(error); });
  child.on("exit", (code, signal) => {
    timeline("pi_exit", { code, signal, expectedShutdown: shuttingDown });
    if (!shuttingDown) failed(new Error(`Pi exited (code=${code}, signal=${signal})`));
  });
  const initial = await deadline(rpc({ type: "get_state" }), 40_000, "Pi startup");
  await json(resolve(out, "initial_pi_state.json"), initial.data);
  if (initial.data?.messageCount !== 0 || !initial.data?.autoCompactionEnabled) throw new Error("Expected empty history with natural compaction enabled");
  await status(true, { phase: "waiting" });
  console.log(JSON.stringify({ out, idle: true, inbox, expectedRunDir, model, condition }));
  while (!stopRequested && !await exists(resolve(out, "STOP"))) {
    const next = turnNumber + 1;
    const path = resolve(inbox, `${String(next).padStart(3, "0")}.json`);
    if (await exists(path)) await runTurn(path, next);
    else await new Promise<void>(yes => setTimeout(yes, 300));
  }
} catch (error) {
  finalError = String(error); timeline("session_failure", { message: finalError }); process.exitCode = 1;
} finally {
  shuttingDown = true;
  for (const ac of controllers.values()) ac.abort();
  if (child && child.exitCode === null && child.signalCode === null) {
    const ended = new Promise<void>(yes => child!.once("exit", () => yes()));
    child.stdin.end();
    try { await deadline(ended, 5_000, "Pi shutdown"); }
    catch { child.kill(); }
  }
  proxy.closeAllConnections(); proxy.close();
  await Promise.allSettled([...requestJobs]);
  await status(false, { stopped: true, phase: "stopped", error: finalError ?? childFailure?.message });
  timeline("session_stopped", { completedTurns: turnNumber, error: finalError });
}
