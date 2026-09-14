import { test } from "node:test";
import assert from "node:assert/strict";
import { trimToTokens, estimateTokens } from "../src/core/utils.js";
test("small recall fields retain actual content instead of just a boilerplate marker", () => {
  const text = "No causal interpretation or universal optimal scale is authorized for this route.";
  for (const limit of [0, 1, 4, 12, 18, 20, 64]) {
    const result = trimToTokens(text, limit);
    assert.ok(estimateTokens(result) <= limit);
    if (limit >= 4) assert.ok(result.startsWith("No causal"));
  }
});
