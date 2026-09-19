import { access, mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { callPython, type PythonMethod } from "./bridge/python-bridge.js";
import { ContextCompiler } from "./core/context-compiler.js";
import { parseExplicitHumanPatch, currentHumanAuthorization } from "./core/human-patch.js";
import { appendContextManifest, contextManifestFromPacket, writeRecoveryCheckpoint } from "./core/context-ledger.js";
import { recallResearchState, latestRouteDecision } from "./core/context-memory.js";
import { resolveModelContext, recallPageBudget } from "./core/model-context.js";
import { makeReviewerPacket, makeWorkerPacket } from "./core/packets.js";
import { ResearchStore } from "./core/research-store.js";
import { contractPopulation } from "./core/contract-population.js";
import { URBAN_AGENT_SYSTEM_PROMPT, urbanPhaseInstruction } from "./core/system-prompt.js";
import { FAIR_PROTOCOL, fairConditionInstruction } from "./core/fair-module-evaluation.js";
import { normalizeProviderPayload } from "./core/provider-compat.js";
import type { RecallDetail, RecallScope, ResearchContract, WorkflowPhase, WorkflowState } from "./core/types.js";
import { trimToTokens } from "./core/utils.js";
import { activeToolsForPhase, bootstrapTools } from "./core/tool-policy.js";
import { bashBoundaryError } from "./core/workspace-command.js";

const STATE_POINTER = "urban.state_pointer.v2";
const CONTEXT_MESSAGE = "urban.context.v2";
const TOOL_NAMES = [
  "urban_initialize",
  "urban_state",
  "urban_recall",
  "urban_set_phase",
  "urban_open_branch",
  "urban_commit_route_family",
  "urban_prepare_worker",
  "urban_python",
  "urban_read",
  "urban_attach_evidence",
  "urban_commit_run",
  "urban_prepare_review",
  "urban_record_review",
  "urban_human_decision",
  "urban_finalize",
];
const PI_BASE_TOOLS = ["read", "bash", "edit", "write"];
const RESEARCH_TOOLS = [
  "urban_state",
  "urban_recall",
  "urban_commit_route_family",
  "urban_commit_run",
  "urban_record_review",
  "urban_human_decision",
  "urban_finalize",
];

type ToolOutput = { content: Array<{ type: "text"; text: string }>; details: unknown };

function requireChoice<const T extends readonly string[]>(value: unknown, allowed: T, label: string): T[number] {
  if (typeof value !== "string" || !allowed.includes(value)) {
    throw new Error(`${label} must be exactly one of: ${allowed.join(", ")}. Received: ${String(value)}.`);
  }
  return value as T[number];
}

function ok(message: string, details: unknown): ToolOutput {
  return { content: [{ type: "text", text: trimToTokens(message, 700) }], details };
}

function fail(error: unknown): never {
  const message = error instanceof Error ? error.message : String(error);
  // Pi marks thrown tool errors as failures; a returned isError field is ignored.
  throw new Error(`Urban Agent error: ${trimToTokens(message, 500)}`);
}

async function exists(path: string): Promise<boolean> {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

export default function urbanAgentExtension(pi: ExtensionAPI): void {
  let currentInputHash: string | undefined;
  // Also covers direct launches with older models.json, in BOTH context conditions.
  pi.on("before_provider_request", (event, ctx) => normalizeProviderPayload(ctx.model?.provider, event.payload));
  const configuredRunDir = process.env.URBAN_PI_RUN_DIR ? resolve(process.env.URBAN_PI_RUN_DIR) : "";
  const workspaceRoot = resolve(process.env.URBAN_PI_WORKSPACE_ROOT || process.cwd());
  let runDir = configuredRunDir;
  let initialized = false;
  let repositoryRoot = process.env.URBAN_PI_REPOSITORY_ROOT ? resolve(process.env.URBAN_PI_REPOSITORY_ROOT) : process.cwd();
  let consecutiveToolErrors = 0;
  let toolCallsThisTurn = 0;
  let lastToolCallSignature = "";
  let recalledRecordIdsThisTurn = new Set<string>();
  let recallQueriesThisTurn = new Set<string>();
  let stateQueriesThisTurn = new Set<string>();
  let lastKnownPhase: WorkflowPhase = "plan";
  let lastInputSource: "interactive" | "rpc" | "extension" = "rpc";
  const toolErrorBudget = Math.max(2, Number.parseInt(process.env.URBAN_TOOL_ERROR_BUDGET ?? "4", 10) || 4);
  const toolCallBudget = Math.max(4, Number.parseInt(process.env.URBAN_TOOL_CALL_BUDGET ?? "16", 10) || 16);
  const compiler = new ContextCompiler();
  const disabledTools = new Set(
    (process.env.URBAN_DISABLED_TOOLS ?? "")
      .split(",")
      .map((name) => name.trim())
      .filter(Boolean),
  );
  const evalCondition = process.env.URBAN_EVAL_CONDITION ?? "urban_full";
  const evalTask = process.env.URBAN_EVAL_TASK ?? "";
  const contextMode = process.env.URBAN_CONTEXT_MODE ?? "hybrid_recall";
  const conditionPrompt: Record<string, string> = {
    urban_no_planner: "Ablation condition: the dedicated Planner module is absent. You may reason about and propose routes in your response, but Planner packets and persisted Planner branch-family state are unavailable. Do not pretend that such state was created.",
    urban_no_reviewer: "Ablation condition: the dedicated Reviewer module and executable review gate are absent. You may inspect evidence and recommend repairs in your response, but do not invent a Reviewer record or claim that commentary changed executable state.",
    urban_no_tree: "Ablation condition: the Urban Research Git Tree, structured state compiler, and indexed recall are absent. Use only the visible chronological dialogue and do not invent hidden branch state.",
    urban_no_human: "Ablation condition: no human gate is available. Do not infer selection, sensitivity retention, comparison requests, or claim approval.",
    tool_react: "Architecture baseline: use the exposed bounded analysis tool in a plain tool-ReAct loop. Planner, Reviewer, Research Git Tree, indexed recall, and human gates are absent.",
    pi_default_compaction: "Compaction baseline: retain the same Urban Agent tools and authoritative Research Tree, but use Pi's chronological dialogue compaction without the automatic state bookmark. Recall remains available so the comparison isolates context management rather than removing scientific state.",
    urban_no_context: "Ablation condition: retain the Urban Planner, Reviewer, tools, human-decision persistence, and authoritative Research Tree, but use Pi's chronological compaction without automatic Research-Tree bookmarks or recall injection. Indexed state remains available only when the model requests it.",
  };
  const baseSystemPrompt = process.env.URBAN_EVAL_PROTOCOL === FAIR_PROTOCOL
    ? `You are an urban-research agent evaluating a spatial-scale-sensitive task. Treat supplied evidence as data, distinguish analysis-unit support from model neighbourhood, and do not invent executed operations, evidence, or human authorization. Use available modules when useful, but always provide a self-contained scientific answer.\n\nCondition: ${fairConditionInstruction(evalCondition)}`
    : conditionPrompt[evalCondition]
    ? `${URBAN_AGENT_SYSTEM_PROMPT}\n\n${conditionPrompt[evalCondition]}`
    : URBAN_AGENT_SYSTEM_PROMPT;
  const urbanSystemPrompt = `${baseSystemPrompt}\n${process.env.URBAN_ROLE_INSTRUCTION ?? ""}\n${process.env.URBAN_TOOL_DISCOVERY === "1" ? 'Use urban_tools to discover and load research tools when needed. Phase is current focus, not a one-way workflow; revisit planning when evidence or human instructions require it.' : ''}`;

  const contextOptions = (model?: { contextWindow?: number; maxTokens?: number; provider?: string; id?: string }) =>
    resolveModelContext(model);

  const store = (): ResearchStore => {
    if (!runDir) throw new Error("No active research run. Call urban_initialize first.");
    return new ResearchStore(runDir);
  };

  const remember = (state: WorkflowState): void => {
    runDir = state.runDir;
    lastKnownPhase = state.phase;
    pi.appendEntry(STATE_POINTER, {
      runDir: state.runDir,
      runId: state.runId,
      phase: state.phase,
      activeBranchId: state.activeBranchId,
      contractHash: state.contractHash,
      updatedAt: state.updatedAt,
    });
  };

  const setPhaseTools = (phase: WorkflowPhase): void => {
    lastKnownPhase = phase;
    if (process.env.URBAN_TOOL_DISCOVERY === "1") return;
    if (typeof pi.setActiveTools !== "function") return;
    if (!initialized) {
      pi.setActiveTools(bootstrapTools(process.env.URBAN_ENABLE_DELEGATION === "1").filter(name => !disabledTools.has(name)));
      return;
    }
    pi.setActiveTools([...PI_BASE_TOOLS, ...activeToolsForPhase(phase, RESEARCH_TOOLS), ...(process.env.URBAN_ENABLE_DELEGATION === "1" ? ["urban_delegate"] : [])].filter((name) =>
      !(process.env.URBAN_AGENT_ROLE && process.env.URBAN_AGENT_ROLE !== "planner" && name === "urban_human_decision") &&
      !disabledTools.has(name) && !(name === "urban_initialize" && initialized),
    ));
  };

  const isInside = (root: string, candidate: string): boolean => {
    const rel = relative(root, candidate);
    return rel === "" || (!isAbsolute(rel) && rel !== ".." && !rel.startsWith(`..${sep}`));
  };

  const workspacePathError = (path: unknown): string | undefined => {
    if (typeof path !== "string" || !path.trim()) return "A nonempty workspace-relative path is required.";
    const candidate = resolve(workspaceRoot, path);
    if (isAbsolute(path) || !isInside(workspaceRoot, candidate)) {
      return "Use only paths relative to the current workspace, such as data/file.csv, work/analysis.py, or outputs/results.csv.";
    }
    return undefined;
  };

  const resolveEvidencePath = async (path: string): Promise<string> => {
    const candidates = isAbsolute(path)
      ? [resolve(path)]
      : [resolve(workspaceRoot, path), resolve(runDir, path)];
    for (const candidate of candidates) {
      if (!isInside(workspaceRoot, candidate) && !isInside(runDir, candidate)) continue;
      if (await exists(candidate)) return candidate;
    }
    throw new Error(
      `Evidence artifact must exist inside the active workspace or research run. Use a workspace-relative path such as outputs/results.csv.`,
    );
  };

  const contractFromWorkspace = async (overrides?: {
    population?: string;
    researchQuestion?: string;
    intendedClaim?: string;
    prohibitedClaims?: string[];
    candidateSupports?: string[];
    covariates?: string[];
  }): Promise<ResearchContract> => {
    const supplied = JSON.parse(await readFile(resolve(workspaceRoot, "data_contract.json"), "utf8")) as Record<string, unknown>;
    const variables = supplied.variables && typeof supplied.variables === "object" ? Object.keys(supplied.variables as object) : overrides?.covariates ?? [];
    const scales = Array.isArray(supplied.scales_m) ? supplied.scales_m.map((value) => `${value} m`) : overrides?.candidateSupports ?? [];
    if (!supplied.research_question || !supplied.aoi || !(supplied.window || supplied.time_window) || !supplied.outcome || !variables.length || !scales.length) {
      throw new Error("Read the data contract. For raw inputs without preset scales/variables, provide your proposed candidate_supports and covariates to initialize; this is a proposal, not human approval to fit.");
    }
    const boundaries = Array.isArray(supplied.boundaries) ? supplied.boundaries.map(String) : [];
    return {
      researchQuestion: overrides?.researchQuestion ?? String(supplied.research_question),
      boundary: String(supplied.aoi),
      observationWindow: String(supplied.window ?? supplied.time_window),
      population: contractPopulation(supplied, overrides?.population),
      outcome: String(supplied.outcome),
      covariates: variables,
      candidateSupports: scales,
      intendedClaim: overrides?.intendedClaim ?? String(supplied.analysis_scope ?? supplied.research_question),
      prohibitedClaims: overrides?.prohibitedClaims ?? boundaries,
      crs: supplied.crs ? String(supplied.crs) : undefined,
      gridOrigin: supplied.grid_origin_m ? JSON.stringify(supplied.grid_origin_m) : undefined,
      validationGeography: supplied.auxiliary_validation ? String(supplied.auxiliary_validation) : undefined,
    };
  };

  pi.registerTool({
    name: "urban_initialize",
    label: "Initialize Urban Research Git Tree",
    description: "Create the immutable research contract in the runtime-owned research directory. The runtime chooses the directory; do not supply a path.",
    parameters: Type.Object({
      research_question: Type.String(),
      population: Type.Optional(Type.String({ description: "Observed population/sample scope, only if absent from the data contract; not a population-count predictor. Base this on source metadata, without inventing eligibility rules." })),
      intended_claim: Type.String(),
      prohibited_claims: Type.Array(Type.String()),
      candidate_supports: Type.Optional(Type.Array(Type.String({description:"Proposed spatial supports with units, for raw-data contracts without preset scales."}))),
      covariates: Type.Optional(Type.Array(Type.String({description:"Proposed comparable covariate definitions, for raw-data contracts without preset variables."}))),
    }, { additionalProperties: false }),
    async execute(_id, params) {
      try {
        if (!configuredRunDir) throw new Error("The runtime did not configure URBAN_PI_RUN_DIR.");
        runDir = configuredRunDir;
        repositoryRoot = resolve(process.env.URBAN_PI_REPOSITORY_ROOT || repositoryRoot);
        const contract = await contractFromWorkspace({ population: params.population, researchQuestion: params.research_question, intendedClaim: params.intended_claim, prohibitedClaims: params.prohibited_claims, candidateSupports:params.candidate_supports, covariates:params.covariates });
        const created = await ResearchStore.initialize(runDir, contract);
        const state = await created.load();
        initialized = true;
        remember(state);
        setPhaseTools(state.phase);
        pi.setSessionName(`Urban Agent · ${state.runId}`);
        return ok(`Initialized ${state.runId}. Contract hash ${state.contractHash}. Phase: plan.`, state);
      } catch (error) {
        return fail(error);
      }
    },
  });

  pi.registerTool({
    name: "urban_state",
    label: "Inspect active research state",
    description: "Read current focus, route status, pending questions and the exact runtime-authenticated human patch (decision, targets and superseded decision). Call urban_state {} for current focus. Optional branch_id inspects a real node ID without changing focus; never search for the pending patch as a workspace file.",
    parameters: Type.Object({ branch_id: Type.Optional(Type.String()) }),
    async execute(_id, params, _signal, _onUpdate, ctx) {
      try {
        const state = await store().load();
        const nodeId = params.branch_id ?? state.activeBranchId;
        const stateQuery = params.branch_id ? `branch:${params.branch_id}` : "current";
        if (stateQueriesThisTurn.has(stateQuery)) {
          const loaded = {
            status: "already_loaded",
            already_loaded: true,
            query: stateQuery,
            stateVersion: state.stateVersion ?? 0,
            remaining_action: "Use the state card already present in this turn. Recall only missing evidence, otherwise continue the requested task.",
          };
          return { content: [{ type: "text", text: JSON.stringify(loaded) }], details: loaded };
        }
        const node = state.nodes[nodeId];
        if (!node) return fail(`Unknown branch ${nodeId}. Call urban_state {} to read the current focus.`);
        const familyId = state.activeFrontier?.familyId;
        const routes = Object.values(state.nodes).filter((candidate) =>
          candidate.nodeType === "model_route" && (!familyId || candidate.parentIds.includes(familyId)),
        );
        const candidateRouteIndex = routes.map((candidate) => {
          const latestReview = [...state.reviews].reverse().find((review) => review.branchId === candidate.nodeId);
          return {
            node_id: candidate.nodeId,
            title: candidate.title,
            status: candidate.status,
            artifact_count: candidate.artifactIds.length,
            review_decision: latestReview?.decision ?? null,
            human_evidence_role: latestRouteDecision(candidate.nodeId, state)?.decision ?? null,
          };
        });
        const pendingPatch = currentHumanAuthorization(state, currentInputHash);
        const artifacts = Object.values(state.artifacts).map((artifact) => ({
          artifact_id: artifact.artifactId,
          branch_id: artifact.branchId,
          role: artifact.role,
          path: isInside(workspaceRoot, artifact.path) ? relative(workspaceRoot, artifact.path) : relative(runDir, artifact.path),
          summary: trimToTokens(artifact.summary, 24),
        }));
        const unresolvedComparison = routes.filter((route) =>
          route.status === "deferred" || latestRouteDecision(route.nodeId, state)?.decision === "request_comparison",
        );
        const result = {
          stateVersion: state.stateVersion, phase: state.phase,
          current_focus_node_id: state.activeBranchId,
          active_frontier: state.activeFrontier ?? null,
          candidate_route_index: candidateRouteIndex,
          inspected_node: { node_id: nodeId, node_status: node.status, human_evidence_role: latestRouteDecision(nodeId, state)?.decision ?? null },
          committed_artifact_index: artifacts,
          pending_questions: state.pendingQuestions,
          pending_human_patch: pendingPatch ? {
            patch_id: pendingPatch.patchId,
            proposed_decision: pendingPatch.proposedDecision ?? null,
            target_branch_ids: pendingPatch.targetBranchIds,
            supersedes_decision_id: pendingPatch.expectedSupersedesDecisionId ?? null,
          } : null,
          next_decision: state.pendingQuestions.at(-1)
            ?? (unresolvedComparison.length ? `Resolve or retain deferred comparison route(s): ${unresolvedComparison.map((route) => route.nodeId).join(", ")}.` : null),
        };
        stateQueriesThisTurn.add(stateQuery);
        // Re-apply the phase policy without changing the provider-visible
        // recovery-tool schema. Some providers reuse an earlier tool plan.
        setPhaseTools(state.phase);
        return { content: [{ type: "text", text: JSON.stringify(result) }], details: result };
      } catch (error) {
        return fail(error);
      }
    },
  });

  pi.registerTool({
    name: "urban_recall",
    label: "Recall indexed research state",
    description: "Search REGISTERED Research Tree records, not files. Use Pi's read tool for files. scope=tree locates route IDs; scope=branch with ids recalls several routes in one batch. Prefer digest/card detail and stable IDs.",
    parameters: Type.Object({
      scope: Type.Union(["tree", "branch", "artifact", "review", "human_decision", "pending", "contract"].map((value) => Type.Literal(value))),
      ids: Type.Optional(Type.Array(Type.String())),
      branch_id: Type.Optional(Type.String()),
      query: Type.Optional(Type.String()),
      detail: Type.Optional(Type.Union(["pointer", "digest", "card", "full"].map((value) => Type.Literal(value)))),
      dependency_depth: Type.Optional(Type.Integer({ minimum: 0, maximum: 8 })),
      token_limit: Type.Optional(Type.Integer({ minimum: 128, maximum: 8000 })),
      range: Type.Optional(Type.Union([Type.Literal("current"), Type.Literal("all")])),
      cursor: Type.Optional(Type.String()),
    }),
    async execute(_id, params, _signal, _onUpdate, ctx) {
      try {
        const state = await store().load();
        const scope = requireChoice(params.scope, ["tree", "branch", "artifact", "review", "human_decision", "pending", "contract"] as const, "scope");
        const detail = params.detail === undefined
          ? undefined
          : requireChoice(params.detail, ["pointer", "digest", "card", "full"] as const, "detail");
        const modelContext = contextOptions(ctx.model);
        const remainingBudget = recallPageBudget(modelContext.contextWindow ?? 8_192, ctx.getContextUsage()?.tokens, modelContext.maxOutputTokens ?? 2048, scope === "tree");
        if (remainingBudget < 256) return fail("No context headroom for a recall page. Finish this turn with what is known; remaining evidence is not yet loaded.");
        const requestedIds = [...new Set(params.ids ?? [])].sort();
        const recallQuery = JSON.stringify({
          scope,
          ids: requestedIds,
          branch_id: params.branch_id ?? null,
          query: (params.query ?? "").trim().toLowerCase(),
          detail: detail ?? "card",
          range: params.range ?? "current",
        });
        if (recallQueriesThisTurn.has(recallQuery) || (requestedIds.length > 0 && requestedIds.every((id) => recalledRecordIdsThisTurn.has(id)))) {
          const loaded = {
            status: "already_loaded",
            already_loaded: true,
            loaded_ids: requestedIds,
            stateVersion: state.stateVersion ?? 0,
            remaining_action: "The requested records are already in this turn's context. Synthesize the answer or perform the next authorized action; do not recall them again.",
          };
          return { content: [{ type: "text", text: JSON.stringify(loaded) }], details: loaded };
        }
        const result = recallResearchState(state, {
          scope: scope as RecallScope,
          ids: params.ids,
          branchId: params.branch_id,
          query: params.query,
          detail: detail as RecallDetail | undefined,
          dependencyDepth: params.dependency_depth,
          tokenLimit: Math.min(params.token_limit ?? remainingBudget, remainingBudget),
          sourceMessageHash: currentInputHash,
          excludeIds: [...recalledRecordIdsThisTurn],
          range: params.range,
          cursor: params.cursor,
        });
        recallQueriesThisTurn.add(recallQuery);
        // A tree page is only an ID index.  It must not prevent a later
        // index-to-card upgrade for those same routes.
        if (scope !== "tree") for (const record of result.records) {
          const item = record as Record<string, unknown>;
          const id = item.nodeId ?? item.artifactId ?? item.reviewId ?? item.decisionId ?? item.patchId ?? item.id;
          if (typeof id === "string") recalledRecordIdsThisTurn.add(id);
        }
        await appendContextManifest(runDir, {
          event: "recall",
          runId: state.runId,
          stateVersion: state.stateVersion ?? 0,
          phase: state.phase,
          activeBranchId: state.activeBranchId,
          recalledScope: result.request.scope,
          recalledRecords: result.records.length,
        });
        const delivered = {
          ...result,
          status: "loaded",
          remaining_action: "Use these records to synthesize the answer or perform the next authorized action. Repeat only for a genuinely different missing record.",
        };
        setPhaseTools(state.phase);
        return {
          content: [{ type: "text", text: JSON.stringify(delivered) }],
          details: delivered,
        };
      } catch (error) {
        return fail(error);
      }
    },
  });

  pi.registerTool({
    name: "urban_set_phase",
    label: "Advance workflow phase",
    description: "Move to the next valid phase. phase must be exactly one of: plan, execute, review, human, finalize. Use active_branch_id, not activeBranchId.",
    parameters: Type.Object({
      phase: Type.String({ description: "Exactly one of: plan, execute, review, human, finalize." }),
      active_branch_id: Type.Optional(Type.String()),
    }),
    async execute(_id, params) {
      try {
        const phase = requireChoice(params.phase, ["plan", "execute", "review", "human", "finalize"] as const, "phase");
        const state = await store().setPhase(phase, params.active_branch_id);
        remember(state);
        setPhaseTools(state.phase);
        return ok(`Phase changed to ${state.phase}; active branch ${state.activeBranchId}.`, state);
      } catch (error) {
        return fail(error);
      }
    },
  });

  pi.registerTool({
    name: "urban_open_branch",
    label: "Open a typed research branch",
    description: "Record one consequential alternative without overwriting prior routes. Use analysis_support for grid resolution, model_route for OLS/GWR, and parameter_route for bandwidth. Omit claim_boundary to inherit the immutable contract boundary.",
    parameters: Type.Object({
      node_id: Type.Optional(Type.String()),
      node_type: Type.Optional(Type.String({ description: "Recommended: analysis_support, model_route, parameter_route, validation_route, diagnostic, evidence_synthesis, or claim. Unknown labels are normalized from the branch title and decision question." })),
      title: Type.String(),
      parent_ids: Type.Optional(Type.Array(Type.String())),
      decision_question: Type.String(),
      parameters: Type.Optional(Type.Record(Type.String(), Type.Any())),
      claim_boundary: Type.Optional(Type.String({ description: "Optional narrower boundary; otherwise inherit the immutable contract's intended and prohibited claims." })),
      summary: Type.Optional(Type.String()),
    }),
    async execute(_id, params) {
      try {
        const allowedNodeTypes = new Set(["data_contract", "analysis_support", "model_route", "parameter_route", "validation_route", "diagnostic", "evidence_synthesis", "claim"]);
        const requestedType = params.node_type?.trim();
        const hint = `${params.title} ${params.decision_question} ${requestedType ?? ""}`.toLowerCase();
        const inferredType = /bandwidth|kernel|parameter|带宽|参数/.test(hint) ? "parameter_route"
          : /\bols\b|\bgwr\b|model|模型/.test(hint) ? "model_route"
          : /validation|holdout|fold|验证|留出/.test(hint) ? "validation_route"
          : /diagnostic|residual|诊断|残差/.test(hint) ? "diagnostic"
          : /synth|merge|综合|合并/.test(hint) ? "evidence_synthesis"
          : /claim|结论|声明/.test(hint) ? "claim"
          : "analysis_support";
        const nodeType = (requestedType && allowedNodeTypes.has(requestedType) ? requestedType : inferredType) as Parameters<ResearchStore["openBranch"]>[0]["nodeType"];
        const current = await store().load();
        const requestedNodeId = params.node_id?.trim();
        const parentIds = params.parent_ids?.map((value) => value.trim()).filter(Boolean);
        const node = await store().openBranch({
          nodeId: requestedNodeId && !current.nodes[requestedNodeId] ? requestedNodeId : undefined,
          nodeType,
          title: params.title,
          parentIds: parentIds?.length ? parentIds : undefined,
          decisionQuestion: params.decision_question,
          parameters: requestedType && requestedType !== nodeType
            ? { ...(params.parameters ?? {}), requested_node_type: requestedType }
            : params.parameters,
          claimBoundary: params.claim_boundary ?? `${current.contract.intendedClaim} Prohibited: ${current.contract.prohibitedClaims.join("; ")}`,
          summary: params.summary,
        });
        const state = await store().load();
        remember(state);
        return ok(`Opened ${node.nodeId} (${node.nodeType}) under ${node.parentIds.join(", ")}.`, node);
      } catch (error) {
        return fail(error);
      }
    },
  });

  pi.registerTool({
    name: "urban_prepare_worker",
    label: "Create isolated Worker packet",
    description: "Compile only the active branch contract, dependencies, evidence pointers, tools, and expected artifacts for execution.",
    parameters: Type.Object({
      branch_id: Type.String(),
      assignment: Type.String(),
      expected_artifacts: Type.Array(Type.String()),
    }),
    async execute(_id, params, _signal, _onUpdate, ctx) {
      try {
        let state = await store().load();
        const packet = makeWorkerPacket(state, {
          branchId: params.branch_id,
          assignment: params.assignment,
          expectedArtifacts: params.expected_artifacts,
          ...contextOptions(ctx.model),
        });
        const path = join(runDir, "packets", `${packet.packetId}.json`);
        await mkdir(dirname(path), { recursive: true });
        await writeFile(path, JSON.stringify(packet, null, 2), "utf8");
        state = await store().setPhase("execute", params.branch_id);
        remember(state);
        setPhaseTools(state.phase);
        return ok(`Worker packet ${packet.packetId} created at ${path}. Execution phase activated.`, { path, packet });
      } catch (error) {
        return fail(error);
      }
    },
  });

  pi.registerTool({
    name: "urban_commit_route_family",
    label: "Commit a bounded route family",
    description: "Atomically record 2–6 distinct analytical roles and activate one frontier. One candidate represents one route across its parameter sweep; never create one candidate per scale or bandwidth. The runtime supplies parent, contract and claim boundary.",
    parameters: Type.Object({
      title: Type.String(),
      decision_dimension: Type.String(),
      candidates: Type.Array(Type.Object({
        label: Type.String(),
        analytical_role: Type.String({ description: "Short role, e.g. global baseline or deferred local comparison." }),
        parameter_sweeps: Type.Optional(Type.Array(Type.String(), { maxItems: 4, description: "Compact inherited sweep descriptions, e.g. supports_m=200,300,...; unresolved values stay unresolved." })),
        analysis_scope: Type.Optional(Type.String({description:"Current analytical subset and definitions (e.g. selected dates, outcome, covariates); distinguish these from all data available in the shared contract."})),
      }, { additionalProperties: false }), { minItems: 2, maxItems: 6 }),
      active_candidate: Type.String({ description: "Exact label of the single route to execute now." }),
      stop_condition: Type.String({ description: "Concrete condition after which the Worker must commit artifacts and stop." }),
    }, { additionalProperties: false }),
    async execute(_id, params) {
      try {
        const result = await store().commitRouteFamily({
          title: params.title,
          decisionDimension: params.decision_dimension,
          decisionQuestion: `What evidence should adjudicate ${params.decision_dimension}?`,
          candidates: params.candidates.map((candidate) => ({
            label: candidate.label,
            nodeType: "model_route",
            parameters: { analytical_role: candidate.analytical_role, parameter_sweeps: candidate.parameter_sweeps ?? [], ...(candidate.analysis_scope ? {analysis_scope:candidate.analysis_scope} : {}) },
            summary: candidate.analytical_role,
          })),
          activeCandidate: params.active_candidate,
          stopCondition: params.stop_condition,
          expectedArtifacts: ["analysis_script", "result_table"],
        });
        const state = await store().load();
        remember(state);
        setPhaseTools(state.phase);
        return ok(
          `${result.idempotent ? "Reused" : "Committed"} route family ${result.family.nodeId}. Active frontier: ${result.active.nodeId}. Stop after: ${state.activeFrontier?.stopCondition}.`,
          { ...result, activeFrontier: state.activeFrontier },
        );
      } catch (error) {
        return fail(error);
      }
    },
  });

  pi.registerTool({
    name: 'urban_read',
    label: 'Read a file or list a directory',
    description: 'Read a file or list a directory in ANY phase. Supply path only; format is detected automatically. Optional offset/limit page the content (characters for text, rows for CSV, entries for directories). Follow next_offset while has_more=true. No computation or state changes. urban_recall searches registered records, this tool reads actual files.',
    parameters: Type.Object({
      path: Type.String({description:'Absolute file or directory path.'}),
      offset: Type.Optional(Type.Integer({minimum:0})),
      limit: Type.Optional(Type.Integer({minimum:1,maximum:4000})),
    }, { additionalProperties: false }),
    async execute(_id, params, signal) {
      const response=await callPython('read_file', params, {signal,repositoryRoot,runDir});
      if (!response.success) return fail(response.error);
      return {content:[{type:'text',text:JSON.stringify(response.result)}],details:response};
    },
  });

  pi.registerTool({
    name: "urban_python",
    label: "Run bounded urban Python operation",
    description: 'Inspect/hash a FILE with arguments.path. list_directory lists a DIRECTORY. Read pages using offset/limit and returned next_offset. run_script requires an existing Python script and CLI args array, not inline code. Its manifest_path lists exact output files and full logs; read it rather than guessing filenames. Nonzero exit is a tool error. Previews are not complete datasets.',
    parameters: Type.Object({
      method: Type.String({enum:['inspect_json','inspect_csv','inspect_text','list_directory','hash_artifact','run_script'],description:'run_script executes an existing Python file; for read-only access prefer urban_read.'}),
      arguments: Type.Object({
        path: Type.Optional(Type.String({ minLength: 1, description: "Required for inspect_json, inspect_csv or hash_artifact." })),
        limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 4000, description: "Text/JSON: chars (default 1600); CSV: rows, max 50 (default 8); directory: entries, max 50." })),
        offset: Type.Optional(Type.Integer({ minimum: 0, description: "Page offset: text characters, CSV rows or directory entries. Use returned next_offset." })),
        script: Type.Optional(Type.String({ minLength: 1, description: "run_script only: required existing Python file path; no inline code or command." })),
        args: Type.Optional(Type.Array(Type.String(), { description: "run_script only: separate CLI tokens, e.g. [\"--action\",\"inventory\"]. Default []." })),
        cwd: Type.Optional(Type.String({ minLength: 1, description: "run_script working directory; defaults to script parent." })),
        timeout_seconds: Type.Optional(Type.Integer({ minimum: 1, maximum: 7200, description: "run_script only; default 1800." })),
        python: Type.Optional(Type.String({ minLength: 1, description: "Optional interpreter executable, not a shell command. Defaults to runtime Python." })),
      }, { additionalProperties: false }),
    }, { additionalProperties: false }),
    async execute(_id, params, signal) {
      try {
        const response = await callPython(params.method as PythonMethod, params.arguments, { signal, repositoryRoot, runDir });
        if (!response.success) return fail(response.error ?? "Python operation failed");
        // The envelope and its manifest/cursor must never be string-truncated.
        return { content: [{ type: "text", text: JSON.stringify(response.result) }], details: response };
      } catch (error) {
        return fail(error);
      }
    },
  });

  pi.registerTool({
    name: "urban_attach_evidence",
    label: "Attach hashed evidence",
    description: "Commit an existing workspace artifact to a Research Tree branch with its SHA-256, summary, role, and metrics. Use a relative path such as outputs/ols_results.csv.",
    parameters: Type.Object({
      branch_id: Type.String(),
      role: Type.String(),
      path: Type.String(),
      summary: Type.String(),
      media_type: Type.Optional(Type.String()),
      metrics: Type.Optional(Type.Record(Type.String(), Type.Union([Type.Number(), Type.String(), Type.Boolean(), Type.Null()]))),
    }),
    async execute(_id, params) {
      try {
        let state = await store().load();
        if (state.phase === "plan") state = await store().setPhase("execute", params.branch_id);
        const artifact = await store().attachEvidence({
          branchId: params.branch_id,
          role: params.role,
          path: await resolveEvidencePath(params.path),
          summary: params.summary,
          mediaType: params.media_type,
          metrics: params.metrics,
        });
        state = await store().setPhase("review", params.branch_id);
        remember(state);
        return ok(`Attached ${artifact.artifactId}; SHA-256 ${artifact.sha256}.`, artifact);
      } catch (error) {
        return fail(error);
      }
    },
  });

  pi.registerTool({
    name: "urban_prepare_review",
    label: "Create isolated Reviewer packet",
    description: "Compile the branch evidence and claim questions for a Reviewer without unrelated dialogue or sibling artifacts.",
    parameters: Type.Object({ branch_id: Type.String(), review_questions: Type.Optional(Type.Array(Type.String())) }),
    async execute(_id, params, _signal, _onUpdate, ctx) {
      try {
        let state = await store().load();
        const packet = makeReviewerPacket(state, {
          branchId: params.branch_id,
          reviewQuestions: params.review_questions,
          ...contextOptions(ctx.model),
        });
        const path = join(runDir, "packets", `${packet.packetId}.json`);
        await mkdir(dirname(path), { recursive: true });
        await writeFile(path, JSON.stringify(packet, null, 2), "utf8");
        state = await store().setPhase("review", params.branch_id);
        remember(state);
        setPhaseTools(state.phase);
        return ok(`Reviewer packet ${packet.packetId} created at ${path}. Review phase activated.`, { path, packet });
      } catch (error) {
        return fail(error);
      }
    },
  });

  pi.registerTool({
    name: "urban_commit_run",
    label: "Commit one completed run",
    description: "Atomically bind the active route's nonempty script, result table and optional log, then enter review. The result CSV must contain a header and at least one row. After success, stop the Worker turn; do not open more branches or continue recalling state.",
    parameters: Type.Object({
      script_path: Type.String({ description: "Workspace-relative code path, for example work/analysis.py." }),
      result_path: Type.String({ description: "Workspace-relative result path, for example outputs/results.csv." }),
      log_path: Type.Optional(Type.String({ description: "Optional workspace-relative execution log." })),
      summary: Type.String(),
      metrics: Type.Optional(Type.Record(Type.String(), Type.Union([Type.Number(), Type.String(), Type.Boolean(), Type.Null()]))),
    }, { additionalProperties: false }),
    async execute(_id, params) {
      try {
        const state = await store().load();
        const branchId = state.activeBranchId;
        const artifacts = [
          { role: "analysis_script", path: await resolveEvidencePath(params.script_path), summary: params.summary, mediaType: "text/x-python" },
          { role: "result_table", path: await resolveEvidencePath(params.result_path), summary: params.summary, mediaType: "text/csv", metrics: params.metrics },
        ];
        if (params.log_path) artifacts.push({ role: "execution_log", path: await resolveEvidencePath(params.log_path), summary: params.summary, mediaType: "text/plain", metrics: undefined });
        const committed = await store().commitRun({ branchId, artifacts });
        const updated = await store().load();
        remember(updated);
        setPhaseTools(updated.phase);
        return ok(
          `Committed ${committed.length} artifacts to ${branchId}; workflow is now in review. STOP this Worker turn and report only the committed artifact paths.`,
          { artifacts: committed, activeFrontier: updated.activeFrontier, stop: true },
        );
      } catch (error) {
        return fail(error);
      }
    },
  });

  pi.registerTool({
    name: "urban_record_review",
    label: "Record Reviewer gate",
    description: "Persist one evidence-grounded gate for the current active route. Do not send a route ID. decision is proceed, repair, new_branch, block, or escalate. checks maps each short check name to true (passed) or false (failed); omit checks that were not performed.",
    parameters: Type.Object({
      decision: Type.Union(["proceed", "repair", "new_branch", "block", "escalate"].map((value) => Type.Literal(value))),
      checks: Type.Record(Type.String(), Type.Boolean()),
      rationale: Type.String(),
      affected_claims: Type.Optional(Type.Array(Type.String())),
      required_action: Type.Optional(Type.String()),
    }),
    async execute(_id, params) {
      try {
        const decision = requireChoice(params.decision, ["proceed", "repair", "new_branch", "block", "escalate"] as const, "decision");
        const stateBeforeReview = await store().load();
        const branchId = stateBeforeReview.activeBranchId;
        if (!branchId) throw new Error("No active route is available for review.");
        const checks = Object.fromEntries(Object.entries(params.checks).map(([key, value]) => [key, value ? "pass" : "fail"])) as Record<string, "pass" | "fail">;
        const review = await store().recordReview({
          branchId,
          decision,
          checks,
          rationale: params.rationale,
          affectedClaims: params.affected_claims,
          requiredAction: params.required_action,
        });
        const state = await store().load();
        remember(state);
        setPhaseTools(state.phase);
        return ok(`Review ${review.reviewId}: ${review.decision}. Next phase: ${state.phase}.`, review);
      } catch (error) {
        return fail(error);
      }
    },
  });

  pi.registerTool({
    name: "urban_human_decision",
    label: "Record human checkpoint",
    description: "Record an explicit human evidence-role decision (select main, retain sensitivity, defer/block or approve claim). This is NOT a prerequisite for permission to execute a task. Ordinary instructions such as run OLS belong on the route analysis_scope. Decision, target routes and actor come from a runtime-authenticated patch, never from the model.",
    parameters: Type.Object({
      rationale: Type.Optional(Type.String({ description: "Why this human-authenticated route decision is being recorded." })),
      reasoning: Type.Optional(Type.String({ description: "Alias for rationale for providers that emit a reasoning field." })),
      resulting_claim_boundary: Type.Optional(Type.String()),
    }, { additionalProperties: false }),
    async execute(_id, params) {
      try {
        const rationale = (params.rationale ?? params.reasoning ?? "").trim();
        if (!rationale) throw new Error("urban_human_decision requires rationale (or its reasoning alias).");
        const currentState = await store().load();
        const pendingPatch = currentHumanAuthorization(currentState, currentInputHash);
        if (!pendingPatch) return ok("No pending evidence-role decision was applied. This tool does not authorize execution. Follow the latest human task instruction, record its scope on the route, and do not treat it as approval of results. If the intended evidence-role decision is ambiguous, ask the human.", {status:"not_applied",reason:"no_pending_evidence_role_decision"});
        const humanDecision = pendingPatch.proposedDecision!;
        const branchIds = pendingPatch.targetBranchIds;
        const decision = await store().recordHumanDecision({
          branchIds,
          decision: humanDecision,
          rationale,
          actor: pendingPatch.actorId,
          actorProvenance: "runtime_authenticated",
          sourcePatchId: pendingPatch.patchId,
          sourceMessageHash: pendingPatch.sourceMessageHash,
          supersedesDecisionId: pendingPatch.expectedSupersedesDecisionId,
          resultingClaimBoundary: params.resulting_claim_boundary,
        });
        const state = await store().load();
        remember(state);
        setPhaseTools(state.phase);
        return ok(`Human checkpoint ${decision.decisionId}: ${decision.decision}. Next phase: ${state.phase}. Current focus: ${state.activeBranchId}. Pending questions: ${JSON.stringify(state.pendingQuestions)}.`, decision);
      } catch (error) {
        return fail(error);
      }
    },
  });

  pi.registerTool({
    name: "urban_finalize",
    label: "Finalize reviewed research bundle",
    description: "Write checkpoint_submission.json, evidence_manifest.json, and route_tree_frontend_state.json. No new branch is allowed afterward.",
    parameters: Type.Object({ final_claim: Type.String() }),
    async execute(_id, params) {
      try {
        const result = await store().finalize(params.final_claim);
        remember(result.state);
        setPhaseTools(result.state.phase);
        return ok(`Finalized ${result.state.runId}. Submission: ${result.submissionPath}; frontend state: ${result.frontendPath}; viewer: ${result.viewerPath}; manifest: ${result.manifestPath}.`, result);
      } catch (error) {
        return fail(error);
      }
    },
  });

  pi.on("session_start", async (_event, ctx) => {
    const pointer = [...ctx.sessionManager.getEntries()].reverse().find(
      (entry) => entry.type === "custom" && entry.customType === STATE_POINTER,
    );
    if (pointer?.type === "custom" && pointer.data && typeof pointer.data === "object") {
      const saved = pointer.data as { runDir?: string };
      if (saved.runDir && !configuredRunDir) runDir = resolve(saved.runDir);
    }
    if (runDir && await exists(join(runDir, "research_state.json"))) {
      initialized = true;
      const state = await store().load();
      setPhaseTools(state.phase);
    } else {
      if (!configuredRunDir) throw new Error("The runtime did not configure URBAN_PI_RUN_DIR.");
      const inputContract = JSON.parse(await readFile(resolve(workspaceRoot,"data_contract.json"),"utf8"));
      if (!Array.isArray(inputContract.scales_m) || !inputContract.variables) {
        // Raw-data research has no preselected design. Let the agent propose it;
        // never fail session startup and leave every registered tool exposed.
        setPhaseTools("plan");
        return;
      }
      const created = await ResearchStore.initialize(configuredRunDir, await contractFromWorkspace());
      const state = await created.load();
      runDir = configuredRunDir;
      initialized = true;
      remember(state);
      setPhaseTools(state.phase);
    }
  });

  pi.on("agent_start", () => {
    consecutiveToolErrors = 0;
    toolCallsThisTurn = 0;
    lastToolCallSignature = "";
    recalledRecordIdsThisTurn = new Set<string>();
    recallQueriesThisTurn = new Set<string>();
    stateQueriesThisTurn = new Set<string>();
    setPhaseTools(lastKnownPhase);
  });

  pi.on("agent_end", async () => {
    if (!currentInputHash || !runDir || !await exists(join(runDir, "research_state.json"))) return;
    const actorId = (process.env.URBAN_AUTHENTICATED_ACTOR ?? "local_human").trim();
    const consumed = await store().consumeUnclassifiedHumanPatch(currentInputHash, actorId);
    if (consumed) remember(await store().load());
  });

  pi.on("input", async (event) => {
    if (["worker", "reviewer"].includes(process.env.URBAN_AGENT_ROLE ?? "")) return { action: "continue" };
    lastInputSource = event.source;
    if (event.source === "extension") return { action: "continue" };
    if (process.env.URBAN_EVAL_PROTOCOL === FAIR_PROTOCOL && ["plan", "reviewer"].includes(evalTask)) {
      return { action: "continue" };
    }
    if (!runDir || !await exists(join(runDir, "research_state.json"))) return { action: "continue" };
    const state = await store().load();
    const parsed = parseExplicitHumanPatch(event.text, state);
    const actorId = (process.env.URBAN_AUTHENTICATED_ACTOR ?? "local_human").trim();
    const patch = await store().persistPendingHumanPatch({
      actorId,
      source: event.source,
      sourceMessageHash: parsed.sourceMessageHash,
      targetBranchIds: parsed.targetBranchIds,
      proposedDecision: parsed.proposedDecision,
      expectedSupersedesDecisionId: parsed.expectedSupersedesDecisionId,
      rawTextDigest: parsed.rawTextDigest,
    });
    const updated = await store().load();
    remember(updated);
    pi.appendEntry("urban.pending_human_patch.v1", {
      patchId: patch.patchId,
      actorId: patch.actorId,
      sourceMessageHash: patch.sourceMessageHash,
      targetBranchIds: patch.targetBranchIds,
      proposedDecision: patch.proposedDecision,
      expectedSupersedesDecisionId: patch.expectedSupersedesDecisionId,
      persistedAt: patch.createdAt,
    });
    return { action: "continue" };
  });

  pi.on("before_agent_start", async (event, ctx) => {
    // Extend Pi and earlier extensions; never discard the shared environment.
    const systemPrompt = `${event.systemPrompt}\n\n${urbanSystemPrompt}`;
    if (!runDir || !await exists(join(runDir, "research_state.json"))) {
      initialized = false;
      setPhaseTools("plan");
      return {
        systemPrompt: `${systemPrompt}\n\nNo Research Tree exists yet. Read WORKSPACE.md and data_contract.json with Pi's read tool, inspect only the needed files under data/, then initialize an accurate contract. Do not guess missing contract fields or invent outputs.`,
      };
    }
    let state = await store().load();
    // Universal ingress boundary. RPC prompt paths can bypass `input`, while
    // before_agent_start always runs before the provider sees the message.
    if (!["worker", "reviewer"].includes(process.env.URBAN_AGENT_ROLE ?? "") && !(process.env.URBAN_EVAL_PROTOCOL === FAIR_PROTOCOL && ["plan", "reviewer"].includes(evalTask))) {
      const parsedIngress = parseExplicitHumanPatch(event.prompt, state);
      currentInputHash = parsedIngress.sourceMessageHash;
      await store().persistPendingHumanPatch({
        actorId: (process.env.URBAN_AUTHENTICATED_ACTOR ?? "local_human").trim(),
        source: lastInputSource,
        sourceMessageHash: parsedIngress.sourceMessageHash,
        targetBranchIds: parsedIngress.targetBranchIds,
        proposedDecision: parsedIngress.proposedDecision,
        expectedSupersedesDecisionId: parsedIngress.expectedSupersedesDecisionId,
        rawTextDigest: parsedIngress.rawTextDigest,
      });
      state = await store().load();
      remember(state);
    }
    setPhaseTools(state.phase);
    const phasePrompt = process.env.URBAN_TOOL_DISCOVERY === "1" ? `Current recorded focus: ${state.phase}. Follow the latest human request; discover tools to record progress, revise routes or inspect evidence when needed.` : urbanPhaseInstruction(state.phase);
    if (evalCondition === "urban_no_tree" || evalCondition === "tool_react" || evalCondition === "pi_default_compaction" || evalCondition === "urban_no_context" || contextMode === "pi_default") {
      return { systemPrompt: `${systemPrompt}\n\n${phasePrompt}` };
    }
    const resolvedContext = contextOptions(ctx.model);
    if (contextMode === "hybrid_recall") {
      const bookmark = compiler.stateBookmark(state, { sourceMessageHash: currentInputHash });
      setPhaseTools(state.phase);
      await appendContextManifest(runDir, {
        event: "bookmarked",
        runId: state.runId,
        stateVersion: state.stateVersion ?? 0,
        phase: state.phase,
        activeBranchId: state.activeBranchId,
        contextWindow: resolvedContext.contextWindow,
        profile: resolvedContext.profile,
        fidelity: "bookmark",
        estimatedTokens: Math.ceil(bookmark.length / 4),
        injectedNodeIds: [state.activeBranchId],
        omittedTreeNodes: Math.max(0, Object.keys(state.nodes).length - 1),
      });
      // Keep the current user instruction last in conversational order. The
      // bookmark is system-level background, not a synthetic post-user turn.
      return { systemPrompt: `${systemPrompt}\n\n${phasePrompt}\n\n${bookmark}` };
    }
    const packet = compiler.compile(state, resolvedContext);
    setPhaseTools(state.phase);
    await appendContextManifest(runDir, {
      event: "compiled",
      runId: state.runId,
      stateVersion: state.stateVersion ?? 0,
      ...contextManifestFromPacket(packet),
    });
    return {
      systemPrompt: `${systemPrompt}\n\n${phasePrompt}`,
      message: {
        customType: CONTEXT_MESSAGE,
        content: compiler.render(packet),
        display: false,
        details: {
          runDir,
          stateHash: state.contractHash,
          phase: state.phase,
          estimatedTokens: packet.estimatedTokens,
          contextProfile: packet.budget.profile,
          contextFidelity: packet.fidelity,
          contextSource: resolvedContext.source,
          modelLabel: resolvedContext.modelLabel,
        },
      },
    };
  });

  pi.on("context", (event) => {
    let lastUrbanContext = -1;
    event.messages.forEach((message, index) => {
      if ((message as { customType?: string }).customType === CONTEXT_MESSAGE) lastUrbanContext = index;
    });
    if (lastUrbanContext < 0) return;
    return {
      messages: event.messages.filter((message, index) =>
        (message as { customType?: string }).customType !== CONTEXT_MESSAGE || index === lastUrbanContext),
    };
  });

  pi.on("session_before_compact", async (event, ctx) => {
    if (contextMode === "pi_default" || evalCondition === "pi_default_compaction" || evalCondition === "urban_no_context" || evalCondition === "urban_no_tree" || evalCondition === "tool_react") return;
    if (!runDir || !await exists(join(runDir, "research_state.json"))) return;
    const state = await store().load();
    const resolvedContext = contextOptions(ctx.model);
    const packet = compiler.compile(state, resolvedContext);
    if (contextMode === "hybrid_recall") {
      const reason = (event as { reason?: string }).reason ?? "threshold";
      await writeRecoveryCheckpoint(runDir, packet.recoveryCapsule, {
        reason,
        policy: "pi_chronological_plus_external_tree",
        tokensBefore: event.preparation.tokensBefore,
        keepRecentTokens: event.preparation.settings.keepRecentTokens,
        reserveTokens: event.preparation.settings.reserveTokens,
      });
      await appendContextManifest(runDir, {
        event: "checkpointed",
        reason,
        runId: state.runId,
        stateVersion: state.stateVersion ?? 0,
        ...contextManifestFromPacket(packet),
        tokensBefore: event.preparation.tokensBefore,
      });
      // Do not replace Pi's chronological summary. The checkpoint remains on
      // disk and a short state bookmark is supplied at the next agent start.
      return;
    }
    const authoritativeSummary = compiler.compactionSummary(state, resolvedContext);
    const uncommittedDialogue = extractUncommittedUserTail([
      ...event.preparation.messagesToSummarize,
      ...event.preparation.turnPrefixMessages,
    ]);
    const summary = uncommittedDialogue.length
      ? `${authoritativeSummary}\n\n<uncommitted_user_tail status="not_yet_structured">\n${uncommittedDialogue.join("\n---\n")}\n</uncommitted_user_tail>\nThese excerpts are continuity hints, not authoritative research state. Commit any consequential instruction through the Research Git Tree before relying on it.`
      : authoritativeSummary;
    const reason = (event as { reason?: string }).reason ?? "threshold";
    const estimatedTokensAfter = Math.ceil(summary.length / 4) + event.preparation.settings.keepRecentTokens;
    await writeRecoveryCheckpoint(runDir, packet.recoveryCapsule, {
      reason,
      tokensBefore: event.preparation.tokensBefore,
      estimatedTokensAfter,
      firstKeptEntryId: event.preparation.firstKeptEntryId,
      keepRecentTokens: event.preparation.settings.keepRecentTokens,
      reserveTokens: event.preparation.settings.reserveTokens,
      contextProfile: packet.budget.profile,
      contextFidelity: packet.fidelity,
    });
    await appendContextManifest(runDir, {
      event: "compacted",
      reason,
      runId: state.runId,
      stateVersion: state.stateVersion ?? 0,
      ...contextManifestFromPacket(packet),
      tokensBefore: event.preparation.tokensBefore,
      estimatedTokensAfter,
    });
    return {
      compaction: {
        summary,
        firstKeptEntryId: event.preparation.firstKeptEntryId,
        tokensBefore: event.preparation.tokensBefore,
        estimatedTokensAfter,
        details: {
          schemaVersion: "2.0",
          runDir,
          runId: state.runId,
          contractHash: state.contractHash,
          activeBranchId: state.activeBranchId,
          phase: state.phase,
        },
      },
    };
  });

  pi.on("session_before_tree", async (_event, ctx) => {
    if (contextMode === "pi_default" || evalCondition === "pi_default_compaction" || evalCondition === "urban_no_context" || evalCondition === "urban_no_tree" || evalCondition === "tool_react") return;
    if (!runDir || !await exists(join(runDir, "research_state.json"))) return;
    const state = await store().load();
    const packet = compiler.compile(state, contextOptions(ctx.model));
    await writeRecoveryCheckpoint(runDir, packet.recoveryCapsule, { reason: "tree_navigation" });
    await appendContextManifest(runDir, {
      event: "tree_navigation",
      reason: "tree_navigation",
      runId: state.runId,
      stateVersion: state.stateVersion ?? 0,
      ...contextManifestFromPacket(packet),
    });
    return {
      summary: {
        summary: compiler.compactionSummary(state, contextOptions(ctx.model)),
        details: { schemaVersion: "2.0", runDir, activeBranchId: state.activeBranchId, contractHash: state.contractHash },
      },
      label: `urban:${state.activeBranchId}`,
    };
  });

  pi.on("tool_call", async (event, ctx) => {
    if (["worker","reviewer"].includes(process.env.URBAN_AGENT_ROLE ?? "") && event.toolName === "urban_human_decision") {
      return {block:true,reason:"Only the human-facing coordinator may apply authenticated human decisions. Report the required decision to the coordinator."};
    }
    if (![...PI_BASE_TOOLS, ...RESEARCH_TOOLS].includes(event.toolName)) return;
    const signature = `${event.toolName}:${JSON.stringify(event.input ?? {})}`;
    if (signature === lastToolCallSignature && ![...PI_BASE_TOOLS, "urban_recall", "urban_state"].includes(event.toolName)) {
      return {
        block: true,
        reason: "This identical action was just attempted. Inspect its saved inputs or output with read before retrying; do not repeat a possibly state-changing action blindly.",
      };
    }
    lastToolCallSignature = signature;
    toolCallsThisTurn += 1;
    if (toolCallsThisTurn > toolCallBudget) {
      ctx.abort();
      return {
        block: true,
        reason: `The bounded tool-call budget (${toolCallBudget}) is exhausted. Stop this turn and preserve the current Research Git Tree for review instead of continuing a repetitive route.`,
      };
    }
    if (event.toolName === "urban_initialize") {
      if (runDir && await exists(join(runDir, "research_state.json"))) {
        return { block: true, reason: "The research state is already initialized. Use urban_state; never replace the authoritative run directory." };
      }
      return;
    }
    if (disabledTools.has(event.toolName)) {
      return { block: true, reason: `Tool ${event.toolName} is disabled by the active framework condition.` };
    }
    if (["read", "edit", "write"].includes(event.toolName)) {
      const error = workspacePathError((event.input as { path?: unknown }).path);
      if (error) return { block: true, reason: error };
      return;
    }
    if (event.toolName === "bash") {
      const error = bashBoundaryError((event.input as { command?: unknown }).command);
      if (error) return { block: true, reason: error };
      return;
    }
    if (!initialized) return { block: true, reason: "Initialize the Research Tree before using research-governance tools." };
  });

  pi.on("tool_result", async (event, ctx) => {
    if (![...PI_BASE_TOOLS, ...RESEARCH_TOOLS].includes(event.toolName)) return;
    if (!event.isError) {
      consecutiveToolErrors = 0;
      return;
    }
    consecutiveToolErrors += 1;
    const remaining = Math.max(0, toolErrorBudget - consecutiveToolErrors);
    const guidance = remaining > 0
      ? `\nRecovery guard: ${remaining} tool-error attempt(s) remain. Do not repeat the same call. Read the exact tool schema, preserve the current run directory, and either correct one argument or stop with a bounded failure report.`
      : "\nRecovery guard: the consecutive tool-error budget is exhausted. The current agent turn is being stopped so the authoritative Research Git Tree remains intact for human review.";
    if (remaining === 0) ctx.abort();
    return {
      content: event.content.map((item) => item.type === "text" ? { ...item, text: `${item.text}${guidance}` } : item),
      details: { original: event.details, consecutiveToolErrors, toolErrorBudget, guardTriggered: remaining === 0 },
      isError: true,
    };
  });

  pi.on("tool_result", (event) => {
    // The v2 shared envelope owns archival before history persistence.
    if (process.env.URBAN_TOOL_DISCOVERY === "1") return;
    if (![...PI_BASE_TOOLS, ...TOOL_NAMES].includes(event.toolName)) return;
    if (["urban_recall", "urban_state", "urban_python", "urban_read"].includes(event.toolName)) return;
    const maxTokens = event.toolName === "read" ? 1400 : event.toolName === "bash" ? 500 : event.toolName === "write" || event.toolName === "edit" ? 250 : 800;
    const content = event.content.map((item) => {
      if (item.type !== "text" || item.text.length <= maxTokens * 4) return item;
      if (event.toolName !== "bash") return { ...item, text: trimToTokens(item.text, maxTokens) };
      const chars = maxTokens * 4;
      const head = Math.floor(chars * 0.55), tail = chars - head - 30;
      return { ...item, text: `${item.text.slice(0, head)}\n…[middle truncated]…\n${item.text.slice(-tail)}` };
    });
    return { content, details: event.details, isError: event.isError };
  });
}

function extractUncommittedUserTail(messages: unknown[]): string[] {
  const collected: string[] = [];
  for (const message of messages) {
    if (!message || typeof message !== "object" || (message as { role?: unknown }).role !== "user") continue;
    const content = (message as { content?: unknown }).content;
    const text = typeof content === "string"
      ? content
      : Array.isArray(content)
        ? content
          .filter((item): item is { type?: string; text?: string } => Boolean(item && typeof item === "object"))
          .filter((item) => item.type === "text" && typeof item.text === "string")
          .map((item) => item.text)
          .join("\n")
        : "";
    const cleaned = text.trim();
    if (cleaned && !cleaned.includes("<urban_research_context")) collected.push(trimToTokens(cleaned, 96));
  }
  return collected.slice(-3);
}
