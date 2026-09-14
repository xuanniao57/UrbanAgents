import { readFile, mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

// A first-request-only diagnostic, NOT an end-to-end evaluation. No proposed
// tool call is executed. All variants keep tools and the latest question fixed.
const source = resolve(process.argv[2]);
const out = resolve(process.argv[3]);
await mkdir(out, { recursive: true });
await writeFile(resolve(out, "diagnostic.lock"), new Date().toISOString(), { flag: "wx" });
const recovered = JSON.parse(await readFile(resolve(source, "request_13.json"), "utf8"));
const before = JSON.parse(await readFile(resolve(source, "request_10.json"), "utf8"));
const latest = recovered.messages.at(-1);
const system = recovered.messages.filter((m: any) => m.role === "system");
const variants = [
  { name: "fresh_question", messages: [...system, latest] },
  { name: "uncompressed_history", messages: [...system, ...before.messages.filter((m: any) => m.role !== "system"), { role: "assistant", content: "ACK" }, latest] },
  { name: "compressed_history", messages: recovered.messages },
];
for (const v of variants) {
  const request = { ...recovered, messages: v.messages, temperature: 0, max_tokens: 256, stream: false };
  delete request.stream_options;
  const start = Date.now();
  const response = await fetch("http://127.0.0.1:11434/v1/chat/completions", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request), signal: AbortSignal.timeout(180_000),
  });
  const data = await response.json();
  const result = { condition: v.name, durationMs: Date.now() - start, httpStatus: response.status, response: data };
  await writeFile(resolve(out, `${v.name}.json`), JSON.stringify({ request, result }, null, 2));
  console.log(JSON.stringify(result));
}
