import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const out = resolve(process.argv[2] ?? "evaluation/context_diagnosis_20260830/wire_probe");
await mkdir(out, { recursive: true });
for (const field of ["max_completion_tokens", "max_tokens"]) {
  const body = { model: "qwen3.5:4b-urban8k", messages: [{ role: "user", content: "Write a detailed 1000-word explanation of spatial scale sensitivity, with ten sections." }], stream: true, stream_options: { include_usage: true }, reasoning_effort: "none", [field]: 48 };
  const ac = new AbortController(); const timer = setTimeout(() => ac.abort(), 90000);
  const start = Date.now(); let first: number | null = null; let raw = ""; let count = 0; let finish: unknown; let usage: unknown;
  try {
    const response = await fetch("http://127.0.0.1:11434/v1/chat/completions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: ac.signal });
    let tail = "";
    for await (const chunk of response.body!) {
      first ??= Date.now() - start;
      const text = new TextDecoder().decode(chunk); raw += text; tail += text;
      const lines = tail.split("\n"); tail = lines.pop()!;
      for (const line of lines) if (line.startsWith("data: ") && !line.includes("[DONE]")) {
        const item = JSON.parse(line.slice(6)); const choice = item.choices?.[0];
        if (choice?.delta?.content || choice?.delta?.reasoning) count++;
        if (choice?.finish_reason) finish = choice.finish_reason;
        if (item.usage) usage = item.usage;
      }
      if (count > 140) { ac.abort(); break; }
    }
  } catch (error) { raw += `\nPROBE_END: ${String(error)}`; }
  clearTimeout(timer);
  const result = { field, requestedLimit: 48, firstChunkMs: first, durationMs: Date.now() - start, generatedChunks: count, finish, usage, probeCancelled: ac.signal.aborted };
  await writeFile(resolve(out, `${field}.json`), JSON.stringify({ request: body, result }, null, 2));
  await writeFile(resolve(out, `${field}.sse`), raw);
  console.log(JSON.stringify(result));
}
