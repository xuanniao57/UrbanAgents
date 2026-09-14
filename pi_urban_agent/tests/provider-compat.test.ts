import { test } from "node:test";
import assert from "node:assert/strict";
import { applyProviderCompatibility, normalizeProviderPayload } from "../src/core/provider-compat.js";
test("Ollama uses a supported token ceiling and explicit thinking-off mapping", () => {
  const original = { maxTokens: 2048, compat: { supportsUsageInStreaming: true }, thinkingLevelMap: { high: "high" } };
  const result = applyProviderCompatibility("local-ollama", original) as any;
  assert.equal(result.compat.maxTokensField, "max_tokens");
  assert.equal(result.compat.supportsUsageInStreaming, true);
  assert.equal(result.thinkingLevelMap.off, "none");
  assert.equal(result.thinkingLevelMap.high, "high");
  assert.equal("maxTokensField" in original.compat, false);
});
test("Other provider contracts are not silently rewritten", () => {
  const source = { reasoning: true, compat: { maxTokensField: "max_completion_tokens" } };
  assert.deepEqual(applyProviderCompatibility("local-vllm", source), source);
});
test("legacy wire limit is translated without changing an explicit supported ceiling", () => {
  assert.deepEqual(normalizeProviderPayload("local-ollama", { max_completion_tokens: 48 }), { max_tokens: 48 });
  assert.deepEqual(normalizeProviderPayload("local-ollama", { max_completion_tokens: 48, max_tokens: 24 }), { max_tokens: 24 });
  assert.deepEqual(normalizeProviderPayload("other", { max_completion_tokens: 48 }), { max_completion_tokens: 48 });
});
test("installed Pi patch reserves proportionate space on small context windows", async () => {
  const moduleUrl = new URL("../node_modules/@earendil-works/pi-coding-agent/node_modules/@earendil-works/pi-ai/dist/api/simple-options.js", import.meta.url);
  const { clampMaxTokensToContext } = await import(moduleUrl.href);
  const context = { messages: [{ role: "user", content: "a".repeat(5000 * 4) }] };
  assert.equal(clampMaxTokensToContext({ contextWindow: 8192 }, context, 2048), 2048);
  assert.equal(clampMaxTokensToContext({ contextWindow: 8192 }, { messages: [{ role: "user", content: "a".repeat(9000 * 4) }] }, 2048), 1);
  assert.equal(clampMaxTokensToContext({ contextWindow: 128000 }, context, 2048), 2048);
});
