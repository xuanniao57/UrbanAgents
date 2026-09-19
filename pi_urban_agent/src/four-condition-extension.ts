import { spawn } from "node:child_process";
import { appendFile, mkdir, writeFile } from "node:fs/promises";
import { resolve, dirname, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { randomUUID } from "node:crypto";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import urbanExtension from "./pi-extension.js";
import outputEnvelope from "./tool-output-extension.js";
import toolCatalog from "./tool-catalog-extension.js";
import { fourCondition, roleInstruction } from "./core/framework-conditions.js";
import { classifyTurn } from "./core/turn-outcome.js";

export default function extension(pi: ExtensionAPI) {
  const spec = fourCondition(process.env.URBAN_EVAL_CONDITION ?? "");
  if (!spec) throw new Error("Four-condition extension requires a v2 condition");
  const role = process.env.URBAN_AGENT_ROLE ?? "planner";
  const canDelegate = spec.delegation && role === "planner";
  process.env.URBAN_ENABLE_DELEGATION = canDelegate ? "1" : "0";
  process.env.URBAN_TOOL_DISCOVERY = "1";
  process.env.URBAN_ROLE_INSTRUCTION = roleInstruction(role, spec.delegation);
  if (spec.memory) urbanExtension(pi);
  else pi.on("before_agent_start", event => ({ systemPrompt: `${event.systemPrompt}\n${process.env.URBAN_ROLE_INSTRUCTION}` }));
  outputEnvelope(pi);
  toolCatalog(pi);
  if (!canDelegate) return;
  let busy = false;
  pi.registerTool({
    name: "urban_delegate", label: "Delegate research task",
    description: "Run a bounded Worker or independent Reviewer in a fresh Pi session, sharing workspace files and (when enabled) Research Tree, not conversation history. Supply task, current human constraints and evidence paths. Returns a concise report and trace path. No nested delegation.",
    parameters: Type.Object({ role: Type.Union([Type.Literal("worker"), Type.Literal("reviewer")]), task: Type.String(), constraints: Type.String(), evidencePaths: Type.Array(Type.String()) }),
    async execute(_id, params, signal) {
      if (busy) throw new Error("Wait for the current delegation; shared-state writes are serialized.");
      if (signal?.aborted) throw new Error("Delegation cancelled");
      busy = true;
      const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
      const workspace = process.env.URBAN_PI_WORKSPACE_ROOT!;
      const id = randomUUID();
      const folder = resolve(process.env.URBAN_DELEGATION_LOG_DIR!, id);
      await mkdir(folder, { recursive: true });
      const prompt = `${roleInstruction(params.role, false)}\nAssignment: ${params.task}\nHuman constraints supplied by coordinator: ${params.constraints}\nEvidence paths: ${JSON.stringify(params.evidencePaths)}\nReturn a short evidence-backed report and saved artifact paths.`;
      await writeFile(resolve(folder, "assignment.json"), JSON.stringify({ id, ...params, inheritedConversation: false }, null, 2));
      const args = [resolve(root, "node_modules/@earendil-works/pi-coding-agent/dist/cli.js"), "-a", "-e", resolve(root, "src/four-condition-extension.ts"), "--no-extensions", "--no-skills", "--no-prompt-templates", "--no-context-files", "--offline", "--mode", "json", "--thinking", process.env.URBAN_PI_THINKING??"off", "--provider", process.env.URBAN_PI_PROVIDER!, "--model", process.env.URBAN_PI_MODEL!, "--session", resolve(folder, "session.jsonl"), "-p", prompt];
      args.splice(2,0,'-e',resolve(root,'src/shared-environment-extension.ts'));
      const child = spawn(process.execPath, args, { cwd: workspace, windowsHide: true, stdio: ["ignore", "pipe", "pipe"], env: { ...process.env, URBAN_AGENT_ROLE: params.role, URBAN_ENABLE_DELEGATION: "0", URBAN_AUTHENTICATED_ACTOR: `agent:${params.role}:${id}` } });
      let output = "", errors = "";
      const cancel = () => child.kill();
      signal?.addEventListener("abort", cancel, { once: true });
      const timer = setTimeout(cancel, Number(process.env.URBAN_DELEGATE_TIMEOUT_MS ?? "300000"));
      const start = Date.now();
      try {
        child.stdout.on("data", chunk => { output += chunk.toString(); });
        child.stderr.on("data", chunk => { errors += chunk.toString(); });
        const code = await new Promise<number | null>((yes, no) => { child.once("error", no); child.once("close", yes); });
        await writeFile(resolve(folder, "events.jsonl"), output);
        await writeFile(resolve(folder, "stderr.txt"), errors);
        const events = output.split(/\r?\n/).flatMap(line => { try { return [JSON.parse(line)]; } catch { return []; } });
        const messages = events.filter(e => e.type === "message_end" && e.message?.role === "assistant").map(e => e.message);
        const completion = classifyTurn({failed:code!==0||Boolean(signal?.aborted),settled:code===0,budgetStop:false,messages,requests:[]});
        const failed = completion.outcome === 'failed';
        const report = (messages.at(-1)?.content ?? []).filter((b: any) => b.type === "text").map((b: any) => b.text).join("\n");
        const record = { id, role: params.role, code, failed, recoveredErrors:completion.recoveredErrors, scientificStatus:completion.scientificStatus, durationMs: Date.now() - start, toolCalls: events.filter(e => e.type === "tool_execution_start").length, session: resolve(folder, "session.jsonl") };
        await writeFile(resolve(folder, "result.json"), JSON.stringify({ ...record, report }, null, 2));
        await appendFile(resolve(process.env.URBAN_DELEGATION_LOG_DIR!, "index.jsonl"), JSON.stringify(record) + "\n");
        return { content: [{ type: "text" as const, text: `${failed ? "Delegation failed/incomplete" : "Delegation returned"}. Trace: ${relative(workspace, folder)}\n${report.slice(0, 2400)}${report.length > 2400 ? "\n[Report shortened; full report is in result.json.]" : ""}` }], details: record };
      } finally { clearTimeout(timer); signal?.removeEventListener("abort", cancel); busy = false; }
    },
  });
}
