import test from "node:test";
import assert from "node:assert/strict";
import { FOUR_CONDITIONS, fourCondition, roleInstruction } from "../src/core/framework-conditions.js";
import { readFileSync } from "node:fs";
test("four conditions isolate organization and memory", () => {
  assert.equal(Object.keys(FOUR_CONDITIONS).length, 4);
  assert.deepEqual(fourCondition("urban_single_v2"), { delegation: false, memory: true });
  assert.deepEqual(fourCondition("urban_no_memory_v2"), { delegation: true, memory: false });
  assert.equal(fourCondition("urban_no_context"), undefined);
});
test("reviewer and worker have separate responsibilities, not forced counts", () => {
  assert.match(roleInstruction("reviewer", false), /fresh session/);
  assert.match(roleInstruction("planner", true), /optional/);
  assert.match(roleInstruction("worker", false), /Do not grant human authorization/);
});
test("delegation uses a new session and does not load parent conversation", () => {
  const source = readFileSync(new URL("../src/four-condition-extension.ts", import.meta.url), "utf8");
  assert.match(source, /randomUUID\(\)/);
  assert.match(source, /inheritedConversation: false/);
  assert.match(source, /--session/);
  assert.doesNotMatch(source, /getMessages|getBranch\(/);
});
