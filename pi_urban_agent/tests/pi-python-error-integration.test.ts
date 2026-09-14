import test from "node:test";
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { spawn } from "node:child_process";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { ResearchStore } from "../src/core/research-store.js";
import { CONTRACT } from "./fixtures.js";

// Real Pi RPC and builtin bash; deterministic model transport, no GPU/API.
for (const mode of ["hybrid_recall", "pi_default"]) test(`Pi general bash recovers and commits a real run (${mode})`, { timeout: 30000 }, async () => {
  const root = await mkdtemp(join(tmpdir(), "urban-pi-bash-"));
  const workspace = join(root, "workspace");
  const run = join(root, "research");
  await mkdir(join(workspace, "work"), { recursive: true });
  await mkdir(join(workspace, "outputs"), { recursive: true });
  const store = await ResearchStore.initialize(run, CONTRACT);
  const family = await store.commitRouteFamily({
    title: "Initial bounded routes",
    decisionDimension: "model_role",
    decisionQuestion: "Which route executes first?",
    candidates: [
      { label: "OLS baseline", nodeType: "model_route", parameters: { model: "OLS" } },
      { label: "GWR comparison", nodeType: "model_route", parameters: { model: "GWR" } },
    ],
    activeCandidate: "OLS baseline",
    stopCondition: "Commit the script and nonempty result table.",
    expectedArtifacts: ["script", "result table"],
  });
  const script = join(workspace, "work", "analysis.py");
  await writeFile(script, [
    "import argparse, csv, pathlib",
    "p=argparse.ArgumentParser()",
    "p.add_argument('--action', required=True)",
    "a=p.parse_args()",
    "pathlib.Path('outputs').mkdir(exist_ok=True)",
    "with open('outputs/results.csv','w',newline='',encoding='utf-8') as f:",
    "    w=csv.writer(f); w.writerow(['scale_m','r2']); w.writerow([200,0.1])",
    "print('completed:'+a.action)",
    "",
  ].join("\n"), "utf8");

  let count = 0;
  const payloads: any[] = [];
  const server = createServer(async (req, res) => {
    const chunks: Buffer[] = [];
    for await (const chunk of req) chunks.push(chunk);
    payloads.push(JSON.parse(Buffer.concat(chunks).toString()));
    count += 1;
    const tool = count === 1
      ? { name: "bash", arguments: JSON.stringify({ command: "python work/analysis.py" }) }
      : count === 2
        ? { name: "bash", arguments: JSON.stringify({ command: "python work/analysis.py --action inventory" }) }
        : count === 3
          ? { name: "urban_commit_run", arguments: JSON.stringify({
            script_path: "work/analysis.py",
            result_path: "outputs/results.csv",
            summary: "Fixture result created by the corrected command.",
            metrics: { rows: 1 },
          }) }
          : null;
    res.writeHead(200, { "Content-Type": "text/event-stream" });
    const send = (delta: unknown, finish: string | null) => res.write(`data: ${JSON.stringify({
      id: `fixture_${count}`, object: "chat.completion.chunk", created: 1, model: "fixture-model",
      choices: [{ index: 0, delta, finish_reason: finish }],
    })}\n\n`);
    send({ role: "assistant", ...(tool
      ? { tool_calls: [{ index: 0, id: `call_${count}`, type: "function", function: tool }] }
      : { content: "The corrected command produced and committed a nonempty result; stop for review." }) }, null);
    send({}, tool ? "tool_calls" : "stop");
    res.end("data: [DONE]\n\n");
  });
  await new Promise<void>((yes) => server.listen(0, "127.0.0.1", yes));
  const port = (server.address() as { port: number }).port;
  const cfg = join(root, "runtime");
  const sessionDir = join(root, "sessions");
  await mkdir(cfg);
  await mkdir(sessionDir);
  await writeFile(join(cfg, "models.json"), JSON.stringify({ providers: { fixture: {
    api: "openai-completions", apiKey: "test-only", baseUrl: `http://127.0.0.1:${port}/v1`,
    models: [{ id: "fixture-model", name: "fixture-model", reasoning: false, input: ["text"],
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }, contextWindow: 32768, maxTokens: 1024 }],
  } } }));
  await writeFile(join(cfg, "settings.json"), JSON.stringify({ compaction: { enabled: false }, retry: { enabled: false } }));
  const extension = resolve(".pi/extensions/urban-agent.ts");
  const child = spawn(process.execPath, [
    resolve("node_modules/@earendil-works/pi-coding-agent/dist/cli.js"), "-a", "-e", extension,
    "--no-extensions", "--no-skills", "--no-prompt-templates", "--no-context-files", "--offline",
    "--mode", "rpc", "--thinking", "off", "--provider", "fixture", "--model", "fixture-model", "--session-dir", sessionDir,
  ], {
    cwd: workspace,
    windowsHide: true,
    env: {
      ...process.env,
      PI_CODING_AGENT_DIR: cfg,
      PI_OFFLINE: "1",
      URBAN_PI_RUN_DIR: run,
      URBAN_PI_WORKSPACE_ROOT: workspace,
      URBAN_CONTEXT_MODE: mode,
      URBAN_EVAL_CONDITION: mode === "pi_default" ? "pi_default_compaction" : "urban_full",
      URBAN_AUTHENTICATED_ACTOR: "fixture_expert",
      URBAN_DISABLED_TOOLS: "",
      URBAN_TOOL_ERROR_BUDGET: "4",
      URBAN_TOOL_CALL_BUDGET: "16",
    },
  });
  const events: any[] = [];
  let tail = "";
  let stderr = "";
  let timer: NodeJS.Timeout | undefined;
  const done = new Promise<void>((yes, no) => {
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.on("error", no);
    child.on("exit", (code) => { if (!events.some((event) => event.type === "agent_settled")) no(new Error(`Pi exited ${code}: ${stderr}`)); });
    child.stdout.on("data", (chunk) => {
      tail += chunk;
      const lines = tail.split("\n");
      tail = lines.pop()!;
      for (const line of lines) if (line.trim()) {
        const event = JSON.parse(line);
        events.push(event);
        if (event.type === "agent_settled") yes();
        if (event.type === "response" && !event.success) no(new Error(JSON.stringify(event)));
      }
    });
  });
  try {
    child.stdin.write(JSON.stringify({ id: "test", type: "prompt", message: "Run the active route. Correct one command error, verify the result, commit it, and stop for review." }) + "\n");
    await Promise.race([done, new Promise<never>((_, no) => { timer = setTimeout(() => no(new Error("Pi bash test timeout")), 25000); })]);
    const ends = events.filter((event) => event.type === "tool_execution_end");
    assert.deepEqual(ends.map((event) => event.isError), [true, false, false]);
    assert.match(JSON.stringify(ends[0].result), /Recovery guard: 3 tool-error attempt/);
    assert.match(JSON.stringify(ends[1].result), /completed:inventory/);
    assert.match(JSON.stringify(ends[2].result), /workflow is now in review/);
    assert.ok(payloads[0].tools.some((tool:any) => tool.function.name === "bash"));
    assert.ok(payloads[0].tools.some((tool:any) => tool.function.name === "urban_commit_run"));
    assert.ok(!payloads[0].tools.some((tool:any) => tool.function.name === "urban_commit_route_family"));
    assert.match(await readFile(join(workspace, "outputs", "results.csv"), "utf8"), /200,0.1/);
    const final = await store.load();
    assert.equal(final.phase, "review");
    assert.equal(final.activeFrontier?.status, "committed");
    assert.equal(final.nodes[family.active.nodeId].artifactIds.length, 2);
  } finally {
    clearTimeout(timer);
    child.stdin.end();
    child.kill();
    server.closeAllConnections();
    server.close();
  }
});
