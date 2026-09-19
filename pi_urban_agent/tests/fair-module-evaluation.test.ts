import { test } from "node:test";
import assert from "node:assert/strict";
import { fairConditionInstruction, fairTaskPrompt, makeBlindBundle, validateJudge } from "../src/core/fair-module-evaluation.js";

test("ablations allow reasoning without dedicated module tools", () => {
  assert.match(fairConditionInstruction("urban_no_planner"), /may still reason/);
  assert.match(fairConditionInstruction("urban_no_reviewer"), /may still inspect evidence/);
  assert.doesNotMatch(fairConditionInstruction("urban_no_planner"), /Do not invent a branch plan/);
});
test("primary task evidence is condition- and storage-independent", () => {
  const prompt = fairTaskPrompt("plan", { commonData: "same" });
  const answer = "Compare 200–800m, keep the common covariates, inspect local coefficients.";
  const a = makeBlindBundle("plan", prompt, answer);
  const b = makeBlindBundle("plan", prompt, answer);
  assert.deepEqual(a, b);
  assert.equal("condition" in a, false);
  assert.equal("state" in a, false);
});
test("judge scores require exact output evidence and unique criteria", () => {
  const bundle = makeBlindBundle("reviewer", "facts", "Predictive transfer is not local interpretation.");
  const items = ["R1", "R2", "R3", "R4"].map((id) => ({ id, score: 2, quote: bundle.answer, rationale: "Supported" }));
  assert.equal(validateJudge(bundle, { evidenceHash: bundle.evidenceHash, items }), 8);
  assert.throws(() => validateJudge(bundle, { evidenceHash: "other", items }));
  assert.throws(() => validateJudge(bundle, { evidenceHash: bundle.evidenceHash, items: items.map((item) => ({ ...item, quote: "fabricated" })) }));
  assert.throws(() => validateJudge(bundle, { evidenceHash: bundle.evidenceHash, items: items.map((item) => ({ ...item, id: "R1" })) }));
});
test("missing answer cannot receive positive evidence-backed credit", () => {
  const bundle = makeBlindBundle("plan", "facts", "");
  const items = ["P1", "P2", "P3", "P4"].map((id) => ({ id, score: 0, quote: "", rationale: "No answer" }));
  assert.equal(validateJudge(bundle, { evidenceHash: bundle.evidenceHash, items }), 0);
  assert.throws(() => validateJudge(bundle, { evidenceHash: bundle.evidenceHash, items: items.map((item) => ({ ...item, score: 2 })) }));
});
