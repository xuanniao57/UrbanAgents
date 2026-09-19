import assert from "node:assert/strict";
import test from "node:test";
import { resolveModelContext } from "../src/core/model-context.js";

test("model metadata drives context policy without model-name special cases", () => {
  const small = resolveModelContext({ provider: "local", id: "any-4b", contextWindow: 8_192, maxTokens: 2_048 }, { profile: "auto" });
  const large = resolveModelContext({ provider: "api", id: "frontier", contextWindow: 262_144, maxTokens: 16_384 }, { profile: "auto" });
  assert.equal(small.contextWindow, 8_192);
  assert.equal(small.maxOutputTokens, 2_048);
  assert.equal(small.source, "model_metadata");
  assert.equal(large.contextWindow, 262_144);
});

test("explicit deployment overrides correct inaccurate provider metadata", () => {
  const resolved = resolveModelContext(
    { provider: "local", id: "served-model", contextWindow: 32_768, maxTokens: 8_192 },
    { contextWindow: 12_288, maxOutputTokens: 3_072, profile: "compact" },
  );
  assert.equal(resolved.contextWindow, 12_288);
  assert.equal(resolved.maxOutputTokens, 3_072);
  assert.equal(resolved.profile, "compact");
  assert.equal(resolved.source, "override");
});
