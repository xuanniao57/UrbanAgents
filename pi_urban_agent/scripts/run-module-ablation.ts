import { spawn, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { FAIR_PROTOCOL, fairTaskPrompt } from "../src/core/fair-module-evaluation.js";

const args = parseArgs(process.argv.slice(2));
const protocol = args.protocol ?? "legacy";
if (!["legacy", FAIR_PROTOCOL].includes(protocol)) throw new Error("Unknown evaluation protocol");
if (protocol === FAIR_PROTOCOL && (!args.tasks || args.tasks.split(",").some((task) => !["plan", "reviewer"].includes(task)))) throw new Error("task-semantic-v1 requires --tasks plan,reviewer (context protocol is unchanged)");
if (!args.model || !args.outputRoot) {
  throw new Error("Usage: run-module-ablation.ts --model <model-id> --output-root <dir> [--provider <provider>] [--base-url <url>] [--context-window <tokens>] [--max-output-tokens <tokens>] [--label <label>]");
}

const root = resolve(process.cwd());
const outputRoot = resolve(args.outputRoot);
const label = args.label ?? args.model.replaceAll(/[^A-Za-z0-9_.-]+/g, "_");
const modelRoot = resolve(outputRoot, label);
const configDir = resolve(modelRoot, ".pi-agent-runtime");
const provider = args.provider ?? "local-ollama";
const contextWindow = positiveInteger(args.contextWindow) ?? 8_192;
const maxOutputTokens = positiveInteger(args.maxOutputTokens) ?? 1_024;
const runTimeoutSeconds = positiveInteger(args.runTimeoutSeconds) ?? 240;
const runTimeoutMs = runTimeoutSeconds * 1_000;
await mkdir(modelRoot, { recursive: true });

await runCommand(tsx(), [
  resolve(root, "scripts", "materialize-model-config.ts"),
  "--source", resolve(root, ".pi-agent", "models.json"),
  "--out-dir", configDir,
  "--provider", provider,
  "--model", args.model,
  "--context-window", String(contextWindow),
  "--max-output-tokens", String(maxOutputTokens),
  ...(args.baseUrl ? ["--base-url", args.baseUrl] : []),
], root, process.env, 120_000);

const allRuns = [
  { task: "plan", condition: "urban_full" },
  { task: "plan", condition: "urban_no_planner" },
  { task: "reviewer", condition: "urban_full" },
  { task: "reviewer", condition: "urban_no_reviewer" },
  { task: "context", condition: "urban_full" },
  { task: "context", condition: "pi_default_compaction" },
  { task: "context", condition: "urban_no_tree" },
  { task: "context", condition: "urban_no_human" },
] as const;
const taskFilter = new Set((args.tasks ?? "").split(",").map((value) => value.trim()).filter(Boolean));
const conditionFilter = new Set((args.conditions ?? "").split(",").map((value) => value.trim()).filter(Boolean));
const runs = allRuns.filter((run) =>
  (!taskFilter.size || taskFilter.has(run.task))
  && (!conditionFilter.size || conditionFilter.has(run.condition)),
);
if (!runs.length) throw new Error("No runs match --tasks/--conditions filters.");

const summaries: Record<string, unknown>[] = [];
const repeats = positiveInteger(args.repeats) ?? 1;
for (const spec of runs) for (let repeat = 1; repeat <= repeats; repeat += 1) {
  const runDir = resolve(modelRoot, `${spec.task}__${spec.condition}__r${String(repeat).padStart(2, "0")}`);
  // Never silently replace a historical run, even when a new rubric is selected.
  await mkdir(runDir);
  // A killed Pi client does not reliably cancel an in-flight Ollama generation.
  // Reset before every repeat so a timed-out predecessor cannot queue-block the
  // next condition and invalidate paired independence.
  if (provider === "local-ollama") stopOllamaModel(args.model);
  await delay(2_000);
  const started = Date.now();
  let result: { exitCode: number; assistantText: string; compaction?: unknown; stderr: string } = {
    exitCode: 1, assistantText: "", stderr: "Run did not start.",
  };
  try {
    await runCommand(tsx(), [
      resolve(root, "scripts", "prepare-module-ablation-fixture.ts"),
      "--task", spec.task,
      "--run-dir", runDir,
      "--protocol", protocol,
    ], root, process.env, 120_000);
    const env = conditionEnvironment(spec.condition, runDir, spec.task);
    if (spec.task === "context") {
      const sessionDir = resolve(runDir, "prepared_session");
      const prepared = await runCommand(tsx(), [
        resolve(root, "scripts", "prepare-context-ablation-session.ts"),
        "--output-dir", sessionDir,
        "--model", args.model,
      ], root, env, 120_000);
      const sessionFile = (JSON.parse(prepared.stdout) as { sessionFile: string }).sessionFile;
      result = await runContextRpc(runDir, sessionFile, env);
    } else {
      result = await runPrintTask(spec.task, runDir, env);
    }
  } catch (error) {
    result = {
      exitCode: 1,
      assistantText: "",
      stderr: `RUN_FAILURE: ${error instanceof Error ? `${error.name}: ${error.message}\n${error.stack ?? ""}` : String(error)}`,
    };
  }
  const manifest = {
    protocol,
    primaryScore: protocol === FAIR_PROTOCOL ? "independent_task_semantic_judge_pending" : "legacy_implementation_checklist",
    model: args.model,
    label,
    provider,
    contextWindow,
    maxOutputTokens,
    runTimeoutSeconds,
    task: spec.task,
    condition: spec.condition,
    repeat,
    isolatedModelReset: provider === "local-ollama",
    runtimeSeconds: (Date.now() - started) / 1_000,
    exitCode: result.exitCode,
    compaction: result.compaction,
    gpu: hardwareSnapshot(),
  };
  await writeFile(resolve(runDir, "assistant_output.txt"), result.assistantText, "utf8");
  await writeFile(resolve(runDir, "stderr.txt"), result.stderr, "utf8");
  await writeFile(resolve(runDir, "run_manifest.json"), JSON.stringify(manifest, null, 2), "utf8");
  summaries.push(manifest);
  console.log(JSON.stringify(manifest));
  if (provider === "local-ollama") stopOllamaModel(args.model);
  await delay(2_000);
}

await writeFile(resolve(modelRoot, "model_run_summary.json"), JSON.stringify(summaries, null, 2), "utf8");

function conditionEnvironment(condition: string, runDir: string, task: string): NodeJS.ProcessEnv {
  const disabled: Record<string, string> = {
    // The current Planner writes a bounded route family atomically. Remove
    // that active interface as well as the legacy per-branch packet tools.
    urban_no_planner: "urban_commit_route_family,urban_open_branch,urban_prepare_worker",
    urban_no_reviewer: "urban_prepare_review,urban_record_review",
    urban_no_tree: "urban_state,urban_recall",
    urban_no_human: "urban_human_decision",
  };
  const apiHost = args.baseUrl ? new URL(args.baseUrl).hostname : "";
  return {
    ...process.env,
    // API timing runs must not inherit an environment-variable proxy. For a
    // system-level TUN proxy, the host still needs a DIRECT rule in the proxy client.
    HTTP_PROXY: "",
    HTTPS_PROXY: "",
    ALL_PROXY: "",
    NO_PROXY: apiHost,
    no_proxy: apiHost,
    PI_CODING_AGENT_DIR: configDir,
    PI_OFFLINE: "1",
    URBAN_PI_RUN_DIR: runDir,
    URBAN_PI_REPOSITORY_ROOT: resolve(root, ".."),
    URBAN_EVAL_CONDITION: condition,
    URBAN_EVAL_TASK: task,
    URBAN_EVAL_PROTOCOL: protocol,
    URBAN_CONTEXT_MODE: condition === "pi_default_compaction" || condition === "urban_no_tree" ? "pi_default" : "hybrid_recall",
    URBAN_CONTEXT_WINDOW: String(contextWindow),
    URBAN_MAX_OUTPUT_TOKENS: String(maxOutputTokens),
    URBAN_TOOL_ERROR_BUDGET: "4",
    URBAN_TOOL_CALL_BUDGET: "12",
    URBAN_AUTHENTICATED_ACTOR: "human_expert_20260825",
    URBAN_DISABLED_TOOLS: disabled[condition] ?? "",
  };
}

function positiveInteger(value?: string): number | undefined {
  if (!value) return undefined;
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed <= 0) throw new Error(`Expected a positive integer, received ${value}.`);
  return parsed;
}

async function runPrintTask(task: "plan" | "reviewer", runDir: string, env: NodeJS.ProcessEnv) {
  const promptFile = task === "plan" ? "planner.md" : "reviewer.md";
  const promptPath = resolve(root, "evaluation", "module_ablation_20260825", "prompts", promptFile);
  const prompt = protocol === FAIR_PROTOCOL
    ? fairTaskPrompt(task, JSON.parse(await readFile(resolve(runDir, "common_task_evidence.json"), "utf8")))
    : await readFile(promptPath, "utf8");
  await writeFile(resolve(runDir, "task_prompt.txt"), prompt, "utf8");
  const child = spawn(pi(), [
    "-a", "-e", resolve(root, ".pi", "extensions", "urban-agent.ts"),
    "--no-extensions", "--no-skills", "--no-prompt-templates",
    "--no-session", "--no-context-files", "--offline",
    "--mode", "rpc", "--thinking", "minimal", "--provider", provider, "--model", args.model!,
  ], { cwd: root, env, windowsHide: true, shell: process.platform === "win32" });
  const rpc = collectRpc(child);
  await delay(800);
  const settled = rpc.waitSettled();
  await rpc.send({ type: "prompt", message: prompt });
  let timedOut = false;
  await Promise.race([
    settled,
    delay(runTimeoutMs).then(async () => {
      timedOut = true;
      try { await rpc.send({ type: "abort" }); } catch { /* process may already be closing */ }
    }),
  ]);
  if (timedOut) await Promise.race([settled, delay(5_000)]);
  child.stdin.end();
  const exitCode = await closeChild(child, 10_000);
  const stdout = rpc.events.map((event) => JSON.stringify(event)).join("\n") + "\n";
  await writeFile(resolve(runDir, "pi_events.jsonl"), stdout, "utf8");
  return {
    exitCode: timedOut ? 124 : exitCode,
    assistantText: extractAssistantText(stdout),
    stderr: `${rpc.stderr()}${timedOut ? `\nRUN_GUARD: timed out after ${runTimeoutSeconds} seconds.` : ""}`,
  };
}

async function runContextRpc(runDir: string, sessionFile: string, env: NodeJS.ProcessEnv) {
  const child = spawn(pi(), [
    "-a", "-e", resolve(root, ".pi", "extensions", "urban-agent.ts"),
    "--no-extensions", "--no-skills", "--no-prompt-templates",
    "--no-builtin-tools", "--no-context-files", "--offline", "--mode", "rpc", "--thinking", "minimal",
    "--provider", provider, "--model", args.model!, "--session", sessionFile,
  ], { cwd: root, env, windowsHide: true, shell: process.platform === "win32" });
  const events: unknown[] = [];
  const stderr: Buffer[] = [];
  const hardTimeoutMs = 540_000;
  let hardTimedOut = false;
  let compactionData: unknown;
  let hardTimer: NodeJS.Timeout | undefined;
  let rejectHardDeadline: ((error: Error) => void) | undefined;
  const hardDeadline = new Promise<never>((_resolve, reject) => {
    rejectHardDeadline = reject;
  });
  hardTimer = setTimeout(() => {
    hardTimedOut = true;
    if (process.platform === "win32" && child.pid) spawnSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], { windowsHide: true });
    else child.kill("SIGKILL");
    rejectHardDeadline?.(new Error(`Context run exceeded hard wall-clock limit of ${hardTimeoutMs / 1_000} seconds.`));
  }, hardTimeoutMs);
  const guarded = <T>(promise: Promise<T>): Promise<T> => Promise.race([promise, hardDeadline]);
  const pending = new Map<string, { resolve: (value: any) => void; reject: (error: Error) => void }>();
  let buffer = "";
  let settledResolver: (() => void) | undefined;
  child.stderr.on("data", (chunk: Buffer) => stderr.push(chunk));
  child.stdout.on("data", (chunk: Buffer) => {
    buffer += chunk.toString("utf8");
    while (true) {
      const index = buffer.indexOf("\n");
      if (index < 0) break;
      const line = buffer.slice(0, index).replace(/\r$/, "");
      buffer = buffer.slice(index + 1);
      if (!line.trim()) continue;
      try {
        const event = JSON.parse(line) as any;
        events.push(event);
        if (event.type === "response" && event.id && pending.has(event.id)) {
          const request = pending.get(event.id)!;
          pending.delete(event.id);
          event.success ? request.resolve(event) : request.reject(new Error(JSON.stringify(event)));
        }
        if (event.type === "agent_settled" && settledResolver) {
          const resolver = settledResolver;
          settledResolver = undefined;
          resolver();
        }
      } catch {
        events.push({ type: "unparsed", line });
      }
    }
  });

  const send = (payload: Record<string, unknown>) => {
    const id = `req-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    return new Promise<any>((resolveRequest, rejectRequest) => {
      pending.set(id, { resolve: resolveRequest, reject: rejectRequest });
      child.stdin.write(`${JSON.stringify({ id, ...payload })}\n`);
    });
  };
  const waitSettled = () => new Promise<void>((resolveSettled, rejectSettled) => {
    const timer = setTimeout(() => {
      if (settledResolver === wrappedResolver) {
        settledResolver = undefined;
        rejectSettled(new Error("Timed out waiting for agent_settled"));
      }
    }, 900_000);
    timer.unref();
    const wrappedResolver = () => {
      clearTimeout(timer);
      resolveSettled();
    };
    settledResolver = wrappedResolver;
  });

  try {
    await guarded(delay(1_000));
    const compaction = await guarded(send({ type: "compact" }));
    compactionData = compaction.data;
    const settled = waitSettled();
    const prompt = await readFile(resolve(root, "evaluation", "module_ablation_20260825", "prompts", "context_human.md"), "utf8");
    await guarded(send({ type: "prompt", message: prompt }));
    const ingressState = JSON.parse(await readFile(resolve(runDir, "research_state.json"), "utf8")) as Record<string, any>;
    const promptHash = createHash("sha256").update(prompt).digest("hex");
    const ingressPatch = (ingressState.pendingHumanPatches ?? []).find((patch: Record<string, any>) =>
      patch.sourceMessageHash === promptHash && ["pending_unclassified", "pending", "applied"].includes(patch.status),
    );
    if (!ingressPatch) {
      throw new Error("INGRESS_ASSERTION_FAILED: prompt returned from RPC but no pending_human_patch envelope was persisted before LLM/tool completion.");
    }
    let turnTimedOut = false;
    await guarded(Promise.race([
      settled,
      delay(420_000).then(() => { turnTimedOut = true; }),
    ]));
    if (turnTimedOut) {
      try { void send({ type: "abort" }); } catch { /* process may already be closing */ }
      await guarded(Promise.race([settled, delay(5_000)]));
    }
    child.stdin.end();
    const closedCode = await guarded(closeChild(child, 20_000));
    const exitCode = turnTimedOut ? 124 : closedCode;
    const eventJsonl = events.map((event) => JSON.stringify(event)).join("\n") + "\n";
    await writeFile(resolve(runDir, "pi_events.jsonl"), eventJsonl, "utf8");
    return {
      exitCode,
      assistantText: extractAssistantText(eventJsonl),
      compaction: compactionData,
      stderr: `${Buffer.concat(stderr).toString("utf8")}${turnTimedOut ? "\nRUN_GUARD: context turn timed out after 420 seconds." : ""}`,
    };
  } catch (error) {
    if (!hardTimedOut) throw error;
    const eventJsonl = events.map((event) => JSON.stringify(event)).join("\n") + "\n";
    await writeFile(resolve(runDir, "pi_events.jsonl"), eventJsonl, "utf8");
    return {
      exitCode: 124,
      assistantText: extractAssistantText(eventJsonl),
      compaction: compactionData,
      stderr: `${Buffer.concat(stderr).toString("utf8")}\nRUN_GUARD: full context run timed out after ${hardTimeoutMs / 1_000} seconds (compaction + inference + tools).`,
    };
  } finally {
    if (hardTimer) clearTimeout(hardTimer);
  }
}

function collectRpc(child: ReturnType<typeof spawn>) {
  const events: unknown[] = [];
  const stderrChunks: Buffer[] = [];
  const pending = new Map<string, { resolve: (value: any) => void; reject: (error: Error) => void }>();
  let buffer = "";
  const settledWaiters: Array<() => void> = [];
  child.stderr?.on("data", (chunk: Buffer) => stderrChunks.push(chunk));
  child.stdout?.on("data", (chunk: Buffer) => {
    buffer += chunk.toString("utf8");
    while (true) {
      const index = buffer.indexOf("\n");
      if (index < 0) break;
      const line = buffer.slice(0, index).replace(/\r$/, "");
      buffer = buffer.slice(index + 1);
      if (!line.trim()) continue;
      try {
        const event = JSON.parse(line) as any;
        events.push(event);
        if (event.type === "response" && event.id && pending.has(event.id)) {
          const request = pending.get(event.id)!;
          pending.delete(event.id);
          event.success ? request.resolve(event) : request.reject(new Error(JSON.stringify(event)));
        }
        if (event.type === "agent_settled") settledWaiters.splice(0).forEach((resolveWaiter) => resolveWaiter());
      } catch {
        events.push({ type: "unparsed", line });
      }
    }
  });
  return {
    events,
    send(payload: Record<string, unknown>) {
      const id = `req-${Date.now()}-${Math.random().toString(16).slice(2)}`;
      return new Promise<any>((resolveRequest, rejectRequest) => {
        pending.set(id, { resolve: resolveRequest, reject: rejectRequest });
        child.stdin?.write(`${JSON.stringify({ id, ...payload })}\n`);
      });
    },
    waitSettled() { return new Promise<void>((resolveWaiter) => settledWaiters.push(resolveWaiter)); },
    stderr() { return Buffer.concat(stderrChunks).toString("utf8"); },
  };
}

async function closeChild(child: ReturnType<typeof spawn>, timeoutMs: number): Promise<number> {
  if (child.exitCode !== null || child.signalCode !== null) return child.exitCode ?? 1;
  return await new Promise<number>((resolveExit) => {
    const timer = setTimeout(() => {
      if (process.platform === "win32" && child.pid) spawnSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], { windowsHide: true });
      else child.kill("SIGKILL");
      resolveExit(1);
    }, timeoutMs);
    child.once("close", (code) => { clearTimeout(timer); resolveExit(code ?? 0); });
  });
}

function delay(ms: number): Promise<void> {
  return new Promise((resolveDelay) => setTimeout(resolveDelay, ms));
}

function extractAssistantText(jsonl: string): string {
  const texts: string[] = [];
  for (const line of jsonl.split(/\r?\n/).filter(Boolean)) {
    try {
      const event = JSON.parse(line) as any;
      if (event.type !== "message_end" || event.message?.role !== "assistant") continue;
      for (const item of event.message.content ?? []) if (item.type === "text" && item.text) texts.push(item.text);
    } catch {
      // Raw diagnostics remain in the event log.
    }
  }
  return texts.join("\n\n");
}

async function runCommand(executable: string, childArgs: string[], cwd: string, env: NodeJS.ProcessEnv, timeout: number) {
  const result = await capture(executable, childArgs, cwd, env, timeout);
  if (result.exitCode !== 0) throw new Error(result.stderr || result.stdout || `Command failed: ${executable}`);
  return result;
}

async function capture(executable: string, childArgs: string[], cwd: string, env: NodeJS.ProcessEnv, timeout: number): Promise<{ exitCode: number; stdout: string; stderr: string; timedOut: boolean }> {
  const child = spawn(executable, childArgs, { cwd, env, windowsHide: true, shell: process.platform === "win32" });
  const stdout: Buffer[] = [];
  const stderr: Buffer[] = [];
  let timedOut = false;
  child.stdout.on("data", (chunk: Buffer) => stdout.push(chunk));
  child.stderr.on("data", (chunk: Buffer) => stderr.push(chunk));
  const exitCode = await new Promise<number>((resolveExit, rejectExit) => {
    const timer = setTimeout(() => {
      timedOut = true;
      if (process.platform === "win32" && child.pid) spawnSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], { windowsHide: true });
      else child.kill("SIGKILL");
    }, timeout);
    child.once("error", rejectExit);
    child.once("close", (code) => { clearTimeout(timer); resolveExit(code ?? 1); });
  });
  return { exitCode, stdout: Buffer.concat(stdout).toString("utf8"), stderr: Buffer.concat(stderr).toString("utf8"), timedOut };
}

function hardwareSnapshot(): Record<string, string> {
  const gpu = spawnSync("nvidia-smi", ["--query-gpu=name,memory.used,memory.total,utilization.gpu", "--format=csv,noheader,nounits"], { encoding: "utf8", windowsHide: true });
  const ollama = spawnSync(process.platform === "win32" ? "ollama.exe" : "ollama", ["ps"], { encoding: "utf8", windowsHide: true });
  return { gpu: gpu.stdout?.trim() || gpu.stderr?.trim() || "unavailable", ollama: ollama.stdout?.trim() || ollama.stderr?.trim() || "unavailable" };
}

function stopOllamaModel(model: string): void {
  const executable = process.platform === "win32" ? "ollama.exe" : "ollama";
  spawnSync(executable, ["stop", model], { encoding: "utf8", windowsHide: true, timeout: 30_000, stdio: "ignore" });
}

function pi(): string { return resolve(root, "node_modules", ".bin", process.platform === "win32" ? "pi.cmd" : "pi"); }
function tsx(): string { return resolve(root, "node_modules", ".bin", process.platform === "win32" ? "tsx.cmd" : "tsx"); }

function parseArgs(values: string[]): {
  model?: string;
  outputRoot?: string;
  label?: string;
  tasks?: string;
  conditions?: string;
  provider?: string;
  baseUrl?: string;
  contextWindow?: string;
  maxOutputTokens?: string;
  runTimeoutSeconds?: string;
  repeats?: string;
  protocol?: string;
} {
  const parsed: Record<string, string> = {};
  for (let index = 0; index < values.length; index += 1) {
    const key = values[index];
    if (!key.startsWith("--")) continue;
    parsed[key.slice(2)] = values[index + 1] ?? "";
    index += 1;
  }
  return {
    model: parsed.model,
    outputRoot: parsed["output-root"],
    label: parsed.label,
    tasks: parsed.tasks,
    conditions: parsed.conditions,
    provider: parsed.provider,
    baseUrl: parsed["base-url"],
    contextWindow: parsed["context-window"],
    maxOutputTokens: parsed["max-output-tokens"],
    runTimeoutSeconds: parsed["run-timeout-seconds"],
    repeats: parsed.repeats,
    protocol: parsed.protocol,
  };
}
