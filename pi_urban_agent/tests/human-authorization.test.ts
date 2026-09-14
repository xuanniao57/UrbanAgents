import { test } from "node:test";
import assert from "node:assert/strict";
import { parseExplicitHumanPatch, selectActiveHumanAuthorization } from "../src/core/human-patch.js";
import type { WorkflowState } from "../src/core/types.js";
const state = { nodes: { route_a: { nodeId: "route_a", title: "Route A long title" } }, humanDecisions: [], pendingHumanPatches: [] } as unknown as WorkflowState;
test("queries and negated choices do not become runtime authorization", () => {
  for (const message of ["What is the main route route_a?", "Why was route_a blocked?", "Do not select route_a as the main route.", "不要选择 route_a 为主线。", "Do not retain route_a as sensitivity evidence."]) {
    assert.equal(parseExplicitHumanPatch(message, state).proposedDecision, undefined, message);
  }
  assert.equal(parseExplicitHumanPatch("Retain route_a as sensitivity evidence; do not promote it to the main route.", state).proposedDecision, "retain_sensitivity");
});
test("natural scale-result correction resolves the containing model route", () => {
  const routeState = {
    ...state,
    nodes: {
      ols_route: { nodeId: "ols_route", nodeType: "model_route", title: "ols_scale_baseline", summary: "跨尺度全局基线", parameters: {} },
      fixed_route: { nodeId: "fixed_route", nodeType: "model_route", title: "fixed_gwr_deferred", summary: "fixed-distance GWR", parameters: {} },
      adaptive_route: { nodeId: "adaptive_route", nodeType: "model_route", title: "adaptive_gwr_deferred", summary: "adaptive-bandwidth GWR", parameters: {} },
    },
  } as unknown as WorkflowState;
  const message = "800米OLS即使拟合比较高，也只保留为粗尺度对照，不作为唯一主方案。请把这个决定记下来；GWR仍然没有获准执行。";
  const parsed = parseExplicitHumanPatch(message, routeState);
  assert.deepEqual(parsed.targetBranchIds, ["ols_route"]);
  assert.equal(parsed.proposedDecision, "retain_sensitivity");
  assert.equal(parseExplicitHumanPatch("800米OLS是否应该保留为粗尺度对照？", routeState).proposedDecision, undefined);
});
test("planning language cannot adjudicate a route before that route exists", () => {
  const rootOnly = {
    ...state,
    nodes: { research_object: { nodeId: "research_object", nodeType: "research_object", title: "Shanghai scale study", summary: "", parameters: {} } },
  } as unknown as WorkflowState;
  const parsed = parseExplicitHumanPatch("先激活OLS跨尺度基线，另外两类GWR保留为待讨论比较。", rootOnly);
  assert.deepEqual(parsed.targetBranchIds, []);
  assert.equal(parsed.proposedDecision, undefined);
});
test("latest message cannot authorize through a stale or unclassified envelope", () => {
  const old = { patchId: "old", status: "pending", proposedDecision: "retain_sensitivity", targetBranchIds: ["route_a"] };
  assert.equal(selectActiveHumanAuthorization({ ...state, pendingHumanPatches: [old] } as any, "retain_sensitivity", ["route_a"]).patchId, "old");
  for (const newer of [{ status: "pending_unclassified", targetBranchIds: [] }, { status: "applied", proposedDecision: "retain_sensitivity", targetBranchIds: ["route_a"] }, { status: "pending", proposedDecision: "block", targetBranchIds: ["route_a"] }]) {
    assert.throws(() => selectActiveHumanAuthorization({ ...state, pendingHumanPatches: [old, newer] } as any, "retain_sensitivity", ["route_a"]));
  }
});
