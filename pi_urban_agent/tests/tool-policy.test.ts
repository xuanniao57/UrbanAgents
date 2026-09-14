import assert from "node:assert/strict";
import test from "node:test";
import { isToolAllowed, PHASE_TOOL_POLICY } from "../src/core/tool-policy.js";

test("phase tool policy exposes one bounded governance action per stage", () => {
  assert.equal(isToolAllowed("plan", "urban_commit_route_family"), true);
  assert.equal(isToolAllowed("execute", "urban_commit_run"), true);
  assert.equal(isToolAllowed("review", "urban_commit_run"), false);
  assert.equal(isToolAllowed("review", "urban_record_review"), true);
  assert.equal(isToolAllowed("human", "urban_human_decision"), true);
  assert.equal(isToolAllowed("review", "urban_commit_route_family"), false);
  assert.deepEqual(PHASE_TOOL_POLICY.finalize, ["urban_state", "urban_recall", "urban_finalize"]);
  assert.deepEqual(PHASE_TOOL_POLICY.complete, ["urban_state"]);
});
