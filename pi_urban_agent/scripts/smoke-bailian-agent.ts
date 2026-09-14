/** Secret-safe function-calling smoke test for Bailian OpenAI-compatible models. */
const apiKey = process.env.URBAN_UPSTREAM_API_KEY?.trim();
const baseUrl = process.env.URBAN_UPSTREAM_BASE_URL?.trim()?.replace(/\/$/, "");
if (!apiKey || !baseUrl) throw new Error("URBAN_UPSTREAM_API_KEY and URBAN_UPSTREAM_BASE_URL are required");
const models = process.argv.slice(2);
if (!models.length) throw new Error("Pass one or more model IDs");
const results: Array<Record<string, unknown>> = [];
for (const model of models) {
  const started = Date.now();
  const response = await fetch(`${baseUrl}/chat/completions`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${apiKey}` },
    body: JSON.stringify({
      model,
      messages: [
        { role: "system", content: "Call the supplied function exactly once. Do not answer from memory." },
        { role: "user", content: "Read the current research state." },
      ],
      tools: [{ type: "function", function: { name: "urban_state", description: "Read bounded research state", parameters: { type: "object", properties: {}, additionalProperties: false } } }],
      tool_choice: "auto",
      enable_thinking: false,
      temperature: 0,
      max_tokens: 256,
      stream: false,
    }),
  });
  const body = await response.json() as any;
  const calls = body?.choices?.[0]?.message?.tool_calls ?? [];
  results.push({ model, httpStatus: response.status, ok: response.ok && calls.length === 1 && calls[0]?.function?.name === "urban_state", finishReason: body?.choices?.[0]?.finish_reason, toolCallCount: calls.length, durationMs: Date.now() - started, usage: body?.usage ?? null, errorCode: body?.error?.code ?? null });
}
console.log(JSON.stringify(results, null, 2));
if (results.some(result => !result.ok)) process.exitCode = 1;
