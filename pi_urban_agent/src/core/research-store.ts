import { appendFile, mkdir, readFile, rename, stat, writeFile } from "node:fs/promises";
import { dirname, isAbsolute, join, relative, resolve } from "node:path";
import {
  HUMAN_DECISIONS,
  NODE_STATUSES,
  NODE_TYPES,
  PHASES,
  REVIEW_DECISIONS,
  type ArtifactRecord,
  type HumanDecisionRecord,
  type HumanDecisionType,
  type PendingHumanPatch,
  type NodeStatus,
  type ResearchContract,
  type ResearchEvent,
  type ResearchNode,
  type ResearchNodeType,
  type ReviewDecisionType,
  type ReviewRecord,
  type WorkflowPhase,
  type WorkflowState,
} from "./types.js";
import { makeId, nowIso, sha256File, sha256Text, stableJson } from "./utils.js";
import { buildStandaloneViewer } from "./frontend.js";

const STATE_FILE = "research_state.json";
const EVENTS_FILE = "research_events.jsonl";

export interface OpenBranchInput {
  nodeId?: string;
  nodeType: ResearchNodeType;
  title: string;
  parentIds?: string[];
  decisionQuestion: string;
  parameters?: Record<string, unknown>;
  claimBoundary: string;
  summary?: string;
  status?: NodeStatus;
}

export interface AttachEvidenceInput {
  branchId: string;
  role: string;
  path: string;
  summary: string;
  mediaType?: string;
  metrics?: Record<string, number | string | boolean | null>;
}

export interface RouteFamilyCandidateInput {
  label: string;
  nodeType?: Extract<ResearchNodeType, "analysis_support" | "model_route" | "parameter_route" | "validation_route">;
  parameters?: Record<string, unknown>;
  summary?: string;
}

export interface CommitRouteFamilyInput {
  title: string;
  decisionDimension: string;
  decisionQuestion: string;
  sharedParameters?: Record<string, unknown>;
  candidates: RouteFamilyCandidateInput[];
  activeCandidate: string;
  stopCondition: string;
  expectedArtifacts: string[];
  claimBoundary?: string;
}

export interface CommitRunInput {
  branchId: string;
  artifacts: Array<Omit<AttachEvidenceInput, "branchId">>;
}

export class ResearchStore {
  /**
   * Pi may execute independent tool calls concurrently. Store instances are
   * deliberately cheap and are recreated by the extension, so the queue must
   * be shared by every instance that points at the same run directory.
   */
  private static readonly mutationQueues = new Map<string, Promise<void>>();

  readonly runDir: string;
  readonly statePath: string;
  readonly eventsPath: string;

  constructor(runDir: string) {
    this.runDir = resolve(runDir);
    this.statePath = join(this.runDir, STATE_FILE);
    this.eventsPath = join(this.runDir, EVENTS_FILE);
  }

  static async initialize(runDir: string, contract: ResearchContract): Promise<ResearchStore> {
    // Hash the same JSON representation that is persisted (optional undefined
    // properties disappear on disk). Do not relax verification on later reads.
    contract = JSON.parse(JSON.stringify(contract));
    validateContract(contract);
    const store = new ResearchStore(runDir);
    await mkdir(store.runDir, { recursive: true });
    try {
      await stat(store.statePath);
      throw new Error(`Research state already exists: ${store.statePath}`);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
    }
    const timestamp = nowIso();
    const researchNode: ResearchNode = {
      nodeId: "research_object",
      nodeType: "research_object",
      title: contract.researchQuestion,
      parentIds: [],
      status: "active",
      decisionQuestion: "What urban phenomenon and claim are being studied?",
      parameters: {
        boundary: contract.boundary,
        observationWindow: contract.observationWindow,
        population: contract.population,
        outcome: contract.outcome,
        covariates: contract.covariates,
        candidateSupports: contract.candidateSupports,
      },
      claimBoundary: contract.prohibitedClaims.join("; "),
      summary: contract.intendedClaim,
      artifactIds: [],
      createdAt: timestamp,
      updatedAt: timestamp,
    };
    const state: WorkflowState = {
      schemaVersion: "2.0",
      stateVersion: 0,
      runId: makeId("urban"),
      runDir: store.runDir,
      phase: "plan",
      contract,
      contractHash: sha256Text(contract),
      activeBranchId: researchNode.nodeId,
      nodes: { [researchNode.nodeId]: researchNode },
      artifacts: {},
      reviews: [],
      humanDecisions: [],
      pendingHumanPatches: [],
      pendingQuestions: [],
      createdAt: timestamp,
      updatedAt: timestamp,
    };
    await store.persist(state, "initialized", "system", { contractHash: state.contractHash });
    return store;
  }

  async load(): Promise<WorkflowState> {
    const state = JSON.parse(await readFile(this.statePath, "utf8")) as WorkflowState;
    validateState(state);
    if (sha256Text(state.contract) !== state.contractHash) {
      throw new Error("The immutable research contract has changed since initialization.");
    }
    return state;
  }

  async loadEvents(limit = 50): Promise<ResearchEvent[]> {
    try {
      const lines = (await readFile(this.eventsPath, "utf8")).split(/\r?\n/).filter(Boolean);
      return lines.slice(-Math.max(1, limit)).map((line) => JSON.parse(line) as ResearchEvent);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return [];
      throw error;
    }
  }

  async openBranch(input: OpenBranchInput): Promise<ResearchNode> {
    return this.withMutationLock(async () => {
      if (!NODE_TYPES.includes(input.nodeType)) throw new Error(`Unsupported node type: ${input.nodeType}`);
      if (input.status && !NODE_STATUSES.includes(input.status)) throw new Error(`Unsupported node status: ${input.status}`);
      const state = await this.load();
      assertMutable(state);
      const parentIds = input.parentIds?.length ? input.parentIds : [state.activeBranchId];
      for (const parentId of parentIds) {
        if (!state.nodes[parentId]) throw new Error(`Unknown parent node: ${parentId}`);
      }
      const nodeId = input.nodeId?.trim() || makeId("branch");
      if (state.nodes[nodeId]) throw new Error(`Node already exists: ${nodeId}`);
      const timestamp = nowIso();
      const node: ResearchNode = {
        nodeId,
        nodeType: input.nodeType,
        title: input.title.trim(),
        parentIds: [...new Set(parentIds)],
        status: input.status ?? "proposed",
        decisionQuestion: input.decisionQuestion.trim(),
        parameters: input.parameters ?? {},
        claimBoundary: input.claimBoundary.trim(),
        summary: input.summary?.trim() ?? "",
        artifactIds: [],
        createdAt: timestamp,
        updatedAt: timestamp,
      };
      state.nodes[nodeId] = node;
      state.activeBranchId = nodeId;
      state.updatedAt = timestamp;
      assertAcyclic(state.nodes);
      await this.persist(state, "branch_opened", "planner", { node }, nodeId);
      return node;
    });
  }

  async commitRouteFamily(input: CommitRouteFamilyInput): Promise<{
    family: ResearchNode;
    candidates: ResearchNode[];
    active: ResearchNode;
    idempotent: boolean;
  }> {
    return this.withMutationLock(async () => {
      const state = await this.load();
      assertMutable(state);
      if (input.candidates.length < 2 || input.candidates.length > 12) {
        throw new Error("A route family must contain 2–12 bounded candidates.");
      }
      const labels = input.candidates.map((candidate) => candidate.label.trim());
      if (labels.some((label) => !label)) throw new Error("Every route-family candidate requires a nonempty label.");
      if (new Set(labels.map((label) => label.toLowerCase())).size !== labels.length) {
        throw new Error("Route-family candidate labels must be unique.");
      }
      const sweepCandidateCount = input.candidates.filter((candidate) => {
        const label = candidate.label.toLowerCase();
        const scalarSweepParameter = Object.entries(candidate.parameters ?? {}).some(([key, value]) =>
          /(scale|support|resolution|bandwidth|distance|neighbor)/i.test(key)
          && (typeof value === "number" || typeof value === "string"),
        );
        return /\d+\s*(m|km|%|neighbor)/i.test(label) || scalarSweepParameter;
      }).length;
      if (sweepCandidateCount >= 4) {
        throw new Error("Do not materialize a repeated scale/bandwidth sweep as many full branches. Keep the sweep values in one route candidate's parameter array and use candidates for distinct analytical roles.");
      }
      const reservedContractKey = /^(shared_parameters|features?|covariates?|outcome|crs|grid_origin|boundary|window|population|data_contract)$/i;
      for (const candidate of input.candidates) {
        const conflicts = Object.keys(candidate.parameters ?? {}).filter((key) => reservedContractKey.test(key));
        if (conflicts.length) {
          throw new Error(`Candidate ${candidate.label} repeats immutable contract fields (${conflicts.join(", ")}). Remove them; every route inherits the fixed contract automatically.`);
        }
      }
      const activeIndex = labels.findIndex((label) => label === input.activeCandidate.trim());
      if (activeIndex < 0) throw new Error(`activeCandidate must exactly match one candidate label: ${labels.join(", ")}.`);
      if (!input.stopCondition.trim()) throw new Error("The active route requires a concrete stop condition.");
      const expectedArtifacts = [...new Set(input.expectedArtifacts.map((item) => item.trim()).filter(Boolean))];
      if (!expectedArtifacts.length) throw new Error("The active route requires at least one expected artifact.");
      for (const candidate of input.candidates) {
        if (candidate.nodeType && !["analysis_support", "model_route", "parameter_route", "validation_route"].includes(candidate.nodeType)) {
          throw new Error(`Unsupported route-family candidate type: ${candidate.nodeType}`);
        }
      }

      const signature = sha256Text({
        contractHash: state.contractHash,
        title: input.title.trim(),
        decisionDimension: input.decisionDimension.trim(),
        sharedParameters: input.sharedParameters ?? {},
        candidates: input.candidates.map((candidate) => ({
          label: candidate.label.trim(),
          nodeType: candidate.nodeType ?? "model_route",
          parameters: candidate.parameters ?? {},
        })),
      });
      const existingFamily = Object.values(state.nodes).find((node) => node.parameters.route_family_signature === signature);
      if (existingFamily) {
        const existingCandidates = Object.values(state.nodes).filter((node) => node.parentIds.includes(existingFamily.nodeId));
        const active = state.nodes[state.activeFrontier?.branchId ?? ""]
          ?? existingCandidates.find((node) => node.parameters.route_candidate_label === input.activeCandidate);
        if (!active) throw new Error(`Existing route family ${existingFamily.nodeId} has no active candidate.`);
        return { family: existingFamily, candidates: existingCandidates, active, idempotent: true };
      }
      if (state.phase !== "plan") throw new Error(`A new route family can be committed only in plan phase, not ${state.phase}.`);

      const parentId = state.activeBranchId;
      if (!state.nodes[parentId]) throw new Error(`Active planning parent is missing: ${parentId}`);
      const timestamp = nowIso();
      const familyId = `family_${signature.slice(0, 12)}`;
      const claimBoundary = input.claimBoundary?.trim()
        || `${state.contract.intendedClaim} Prohibited: ${state.contract.prohibitedClaims.join("; ")}`;
      const family: ResearchNode = {
        nodeId: familyId,
        nodeType: "analysis_support",
        title: input.title.trim(),
        parentIds: [parentId],
        status: "proposed",
        decisionQuestion: input.decisionQuestion.trim(),
        parameters: {
          route_family_signature: signature,
          decision_dimension: input.decisionDimension.trim(),
          inherited_contract_hash: state.contractHash,
          shared: input.sharedParameters ?? {},
        },
        claimBoundary,
        summary: `${input.candidates.length} bounded candidates; one active frontier.`,
        artifactIds: [],
        createdAt: timestamp,
        updatedAt: timestamp,
      };
      const candidates = input.candidates.map((candidate, index): ResearchNode => ({
        nodeId: `${familyId}_route_${index + 1}`,
        nodeType: candidate.nodeType ?? "model_route",
        title: candidate.label.trim(),
        parentIds: [familyId],
        status: index === activeIndex ? "active" : "deferred",
        decisionQuestion: input.decisionQuestion.trim(),
        parameters: {
          route_family_id: familyId,
          route_candidate_label: candidate.label.trim(),
          inherited_contract_hash: state.contractHash,
          ...(candidate.parameters ?? {}),
        },
        claimBoundary,
        summary: candidate.summary?.trim() ?? "",
        artifactIds: [],
        createdAt: timestamp,
        updatedAt: timestamp,
      }));
      const active = candidates[activeIndex];
      for (const node of Object.values(state.nodes)) {
        if (node.status === "active") {
          node.status = "proposed";
          node.updatedAt = timestamp;
        }
      }
      state.nodes[familyId] = family;
      for (const candidate of candidates) state.nodes[candidate.nodeId] = candidate;
      state.activeBranchId = active.nodeId;
      state.activeFrontier = {
        familyId,
        branchId: active.nodeId,
        stopCondition: input.stopCondition.trim(),
        expectedArtifacts,
        status: "ready",
        updatedAt: timestamp,
      };
      state.phase = "execute";
      state.updatedAt = timestamp;
      assertAcyclic(state.nodes);
      await this.persist(state, "route_family_committed", "planner", {
        familyId,
        candidateIds: candidates.map((candidate) => candidate.nodeId),
        activeBranchId: active.nodeId,
        stopCondition: state.activeFrontier.stopCondition,
        expectedArtifacts,
      }, active.nodeId);
      return { family, candidates, active, idempotent: false };
    });
  }

  async setPhase(phase: WorkflowPhase, activeBranchId?: string): Promise<WorkflowState> {
    return this.withMutationLock(async () => {
      if (!PHASES.includes(phase)) throw new Error(`Unsupported workflow phase: ${phase}`);
      const state = await this.load();
      assertMutable(state);
      const pendingPatches = (state.pendingHumanPatches ?? []).filter((patch) => patch.status === "pending");
      if (pendingPatches.length && phase !== "human") {
        throw new Error(`Authenticated human patch ${pendingPatches.at(-1)?.patchId} must be applied before leaving the human phase.`);
      }
      const allowed: Record<WorkflowPhase, WorkflowPhase[]> = {
        plan: ["plan", "execute"],
        execute: ["execute", "review"],
        review: ["review", "plan", "human"],
        human: ["human", "plan", "finalize"],
        finalize: ["finalize"],
        complete: [],
      };
      if (!allowed[state.phase].includes(phase)) {
        throw new Error(`Invalid phase transition ${state.phase} -> ${phase}. Allowed: ${allowed[state.phase].join(", ") || "none"}.`);
      }
      if (activeBranchId) {
        if (!state.nodes[activeBranchId]) throw new Error(`Unknown branch: ${activeBranchId}`);
        state.activeBranchId = activeBranchId;
      }
      state.phase = phase;
      state.updatedAt = nowIso();
      await this.persist(state, "phase_changed", "system", { phase, activeBranchId: state.activeBranchId }, state.activeBranchId);
      return state;
    });
  }

  async attachEvidence(input: AttachEvidenceInput): Promise<ArtifactRecord> {
    return this.withMutationLock(async () => {
      const state = await this.load();
      assertMutable(state);
      const branch = state.nodes[input.branchId];
      if (!branch) throw new Error(`Unknown branch: ${input.branchId}`);
      const artifactPath = isAbsolute(input.path) ? input.path : resolve(this.runDir, input.path);
      await stat(artifactPath);
      const relativePath = relative(this.runDir, artifactPath);
      const storedPath = relativePath && !relativePath.startsWith("..") && !isAbsolute(relativePath) ? relativePath : artifactPath;
      const artifact: ArtifactRecord = {
        artifactId: makeId("artifact"),
        branchId: input.branchId,
        role: input.role.trim(),
        path: storedPath,
        sha256: await sha256File(artifactPath),
        mediaType: input.mediaType,
        summary: input.summary.trim(),
        metrics: input.metrics,
        createdAt: nowIso(),
      };
      state.artifacts[artifact.artifactId] = artifact;
      branch.artifactIds.push(artifact.artifactId);
      branch.status = "executed";
      branch.updatedAt = artifact.createdAt;
      state.updatedAt = artifact.createdAt;
      await this.persist(state, "artifact_attached", "worker", { artifact }, input.branchId);
      return artifact;
    });
  }

  async commitRun(input: CommitRunInput): Promise<ArtifactRecord[]> {
    return this.withMutationLock(async () => {
      const state = await this.load();
      assertMutable(state);
      const frontier = state.activeFrontier;
      if (!frontier) throw new Error("No active research frontier. Commit a bounded route family first.");
      if (input.branchId !== frontier.branchId || input.branchId !== state.activeBranchId) {
        throw new Error(`Run artifacts must target the active frontier ${frontier.branchId}.`);
      }
      const branch = state.nodes[input.branchId];
      if (!branch) throw new Error(`Unknown active branch: ${input.branchId}`);
      if (!input.artifacts.length) throw new Error("A run commit requires at least one artifact.");
      const roles = input.artifacts.map((artifact) => artifact.role.trim().toLowerCase());
      if (!roles.some((role) => /script|code/.test(role)) || !roles.some((role) => /result|metric|table/.test(role))) {
        throw new Error("A run commit requires both a code/script artifact and a result/table artifact.");
      }

      const timestamp = nowIso();
      const prepared: ArtifactRecord[] = [];
      for (const item of input.artifacts) {
        const artifactPath = isAbsolute(item.path) ? item.path : resolve(this.runDir, item.path);
        const info = await stat(artifactPath);
        if (!info.isFile() || info.size === 0) throw new Error(`Artifact is missing or empty: ${item.path}`);
        if (/result|metric|table/.test(item.role.toLowerCase()) && /\.csv$/i.test(artifactPath)) {
          const nonemptyLines = (await readFile(artifactPath, "utf8")).split(/\r?\n/).filter((line) => line.trim());
          if (nonemptyLines.length < 2) throw new Error(`CSV result must contain a header and at least one data row: ${item.path}`);
          const promisesCoefficients = /\bcoef(?:ficient)?s?\b|系数/i.test([
            frontier.stopCondition,
            branch.summary,
            String(branch.parameters.analytical_role ?? ""),
          ].join(" "));
          if (promisesCoefficients) {
            const header = new Set(nonemptyLines[0].replace(/^\uFEFF/, "").split(",").map((field) => field.trim().replace(/^"|"$/g, "")));
            const allowedCoefficientColumns = new Set(state.contract.covariates.flatMap((name) => [`coef_${name}`, `${name}_coef`]));
            const missing = state.contract.covariates.filter((name) =>
              !header.has(`coef_${name}`) && !header.has(`${name}_coef`),
            );
            if (missing.length) {
              throw new Error(`The active route promises coefficient evidence, but the result table lacks one scalar coefficient column for: ${missing.join(", ")}. Keep y one-dimensional and map every contract covariate to its own coefficient column.`);
            }
            const unexpected = [...header].filter((name) =>
              (name.startsWith("coef_") || name.endsWith("_coef")) && !allowedCoefficientColumns.has(name),
            );
            if (unexpected.length) {
              throw new Error(`The result table contains coefficient columns outside the fixed covariate contract: ${unexpected.join(", ")}. X must equal the contract covariate list exactly.`);
            }
          }
        }
        const relativePath = relative(this.runDir, artifactPath);
        prepared.push({
          artifactId: makeId("artifact"),
          branchId: input.branchId,
          role: item.role.trim(),
          path: relativePath && !relativePath.startsWith("..") && !isAbsolute(relativePath) ? relativePath : artifactPath,
          sha256: await sha256File(artifactPath),
          mediaType: item.mediaType,
          summary: item.summary.trim(),
          metrics: item.metrics,
          createdAt: timestamp,
        });
      }

      for (const artifact of prepared) {
        state.artifacts[artifact.artifactId] = artifact;
        branch.artifactIds.push(artifact.artifactId);
      }
      branch.status = "executed";
      branch.updatedAt = timestamp;
      state.phase = "review";
      state.activeFrontier = { ...frontier, status: "committed", updatedAt: timestamp };
      state.updatedAt = timestamp;
      await this.persist(state, "run_committed", "worker", {
        branchId: input.branchId,
        artifactIds: prepared.map((artifact) => artifact.artifactId),
        stopCondition: frontier.stopCondition,
      }, input.branchId);
      return prepared;
    });
  }

  async recordReview(input: {
    branchId: string;
    decision: ReviewDecisionType;
    checks: ReviewRecord["checks"];
    rationale: string;
    affectedClaims?: string[];
    requiredAction?: string;
  }): Promise<ReviewRecord> {
    return this.withMutationLock(async () => {
      if (!REVIEW_DECISIONS.includes(input.decision)) throw new Error(`Unsupported review decision: ${input.decision}`);
      const state = await this.load();
      assertMutable(state);
      const branch = state.nodes[input.branchId];
      if (!branch) throw new Error(`Unknown branch: ${input.branchId}`);
      if (!branch.artifactIds.length) throw new Error(`Reviewer cannot assess ${input.branchId} before a valid run artifact is committed.`);
      const record: ReviewRecord = {
        reviewId: makeId("review"),
        branchId: input.branchId,
        decision: input.decision,
        checks: input.checks,
        rationale: input.rationale.trim(),
        affectedClaims: input.affectedClaims ?? [],
        requiredAction: input.requiredAction?.trim(),
        createdAt: nowIso(),
      };
      state.reviews.push(record);
      branch.status = reviewStatus(input.decision);
      branch.updatedAt = record.createdAt;
      if (input.decision === "escalate" || input.decision === "new_branch") {
        const question = input.requiredAction || input.rationale;
        if (!state.pendingQuestions.includes(question)) state.pendingQuestions.push(question);
      }
      state.phase = input.decision === "repair" || input.decision === "new_branch" ? "plan" : "human";
      state.updatedAt = record.createdAt;
      if (state.activeFrontier?.branchId === input.branchId) {
        state.activeFrontier = { ...state.activeFrontier, status: "reviewed", updatedAt: record.createdAt };
      }
      await this.persist(state, "review_recorded", "reviewer", { review: record }, input.branchId);
      return record;
    });
  }

  async recordHumanDecision(input: {
    branchIds: string[];
    decision: HumanDecisionType;
    rationale: string;
    actor: string;
    actorProvenance?: "runtime_authenticated" | "legacy_import";
    sourcePatchId?: string;
    sourceMessageHash?: string;
    supersedesDecisionId?: string;
    resultingClaimBoundary?: string;
  }): Promise<HumanDecisionRecord> {
    return this.withMutationLock(async () => {
      if (!HUMAN_DECISIONS.includes(input.decision)) throw new Error(`Unsupported human decision: ${input.decision}`);
      const state = await this.load();
      assertMutable(state);
      if (!input.branchIds.length) throw new Error("A human decision must reference at least one branch.");
      validateHumanDecisionWrite(state, input);
      for (const branchId of input.branchIds) {
        if (!state.nodes[branchId]) throw new Error(`Unknown branch: ${branchId}`);
      }
      const pendingPatch = input.sourcePatchId
        ? (state.pendingHumanPatches ?? []).find((patch) => patch.patchId === input.sourcePatchId && (patch.status === "pending" || patch.status === "pending_unclassified"))
        : undefined;
      if (input.sourcePatchId && !pendingPatch) throw new Error(`Pending human patch is missing or already consumed: ${input.sourcePatchId}`);
      if (pendingPatch) {
        if (pendingPatch.actorId !== input.actor) throw new Error("Runtime actor does not match the authenticated pending patch.");
        if (pendingPatch.sourceMessageHash !== input.sourceMessageHash) throw new Error("Human source-message hash does not match the pending patch.");
        if (pendingPatch.proposedDecision && pendingPatch.proposedDecision !== input.decision) {
          throw new Error(`The pending human patch requests ${pendingPatch.proposedDecision}, not ${input.decision}.`);
        }
        if (pendingPatch.targetBranchIds.length && !sameSet(pendingPatch.targetBranchIds, input.branchIds)) {
          throw new Error("Tool-selected branches do not match the runtime-persisted human patch.");
        }
        if (pendingPatch.expectedSupersedesDecisionId && pendingPatch.expectedSupersedesDecisionId !== input.supersedesDecisionId) {
          throw new Error(`Human role change must supersede ${pendingPatch.expectedSupersedesDecisionId}.`);
        }
      }
      const record: HumanDecisionRecord = {
        decisionId: makeId("human"),
        branchIds: [...new Set(input.branchIds)],
        decision: input.decision,
        rationale: input.rationale.trim(),
        actor: input.actor.trim() || "human",
        actorProvenance: input.actorProvenance ?? (input.sourcePatchId ? "runtime_authenticated" : "legacy_import"),
        sourcePatchId: input.sourcePatchId,
        sourceMessageHash: input.sourceMessageHash,
        supersedesDecisionId: input.supersedesDecisionId?.trim(),
        resultingClaimBoundary: input.resultingClaimBoundary?.trim(),
        createdAt: nowIso(),
      };
      state.humanDecisions.push(record);
      if (pendingPatch) {
        pendingPatch.status = "applied";
        pendingPatch.appliedDecisionId = record.decisionId;
        pendingPatch.appliedAt = record.createdAt;
      }
      if (record.decision !== "approve_claim") invalidatePriorClaimApprovals(state, record);
      if (record.decision !== "approve_claim") {
        for (const branchId of record.branchIds) {
          const branch = state.nodes[branchId];
          branch.status = humanStatus(record.decision);
          branch.updatedAt = record.createdAt;
        }
      }
      if (record.decision !== "request_comparison") clearResolvedQuestions(state, record.branchIds);
      state.phase = record.decision === "approve_claim" ? "finalize" : record.decision === "request_comparison" ? "plan" : "human";
      state.updatedAt = record.createdAt;
      await this.persist(state, "human_decision_recorded", "human", { decision: record }, record.branchIds[0]);
      return record;
    });
  }

  async persistPendingHumanPatch(input: {
    actorId: string;
    source: PendingHumanPatch["source"];
    sourceMessageHash: string;
    targetBranchIds?: string[];
    proposedDecision?: HumanDecisionType;
    expectedSupersedesDecisionId?: string;
    rawTextDigest: string;
  }): Promise<PendingHumanPatch> {
    return this.withMutationLock(async () => {
      const state = await this.load();
      assertMutable(state);
      const targetBranchIds = [...new Set(input.targetBranchIds ?? [])];
      for (const branchId of targetBranchIds) if (!state.nodes[branchId]) throw new Error(`Unknown branch in human patch: ${branchId}`);
      state.pendingHumanPatches ??= [];
      const duplicate = state.pendingHumanPatches.find((patch) =>
        (patch.status === "pending" || patch.status === "pending_unclassified") && patch.sourceMessageHash === input.sourceMessageHash && patch.actorId === input.actorId,
      );
      if (duplicate) return duplicate;
      const patch: PendingHumanPatch = {
        patchId: makeId("human_patch"),
        actorId: input.actorId.trim() || "anonymous_human",
        source: input.source,
        sourceMessageHash: input.sourceMessageHash,
        targetBranchIds,
        proposedDecision: input.proposedDecision,
        expectedSupersedesDecisionId: input.expectedSupersedesDecisionId,
        rawTextDigest: input.rawTextDigest,
        status: input.proposedDecision ? "pending" : "pending_unclassified",
        createdAt: nowIso(),
      };
      state.pendingHumanPatches.push(patch);
      if (patch.status === "pending") state.phase = "human";
      state.updatedAt = patch.createdAt;
      await this.persist(state, "human_patch_persisted", "human", { patch }, targetBranchIds[0]);
      return patch;
    });
  }

  /**
   * Close an ordinary human message after its agent turn.  The immutable
   * ingress event remains in the log, but a message that carried no explicit
   * route decision must not stay in the active authorization queue.
   */
  async consumeUnclassifiedHumanPatch(sourceMessageHash: string, actorId: string): Promise<PendingHumanPatch | undefined> {
    return this.withMutationLock(async () => {
      const state = await this.load();
      const patch = [...(state.pendingHumanPatches ?? [])].reverse().find((candidate) =>
        candidate.sourceMessageHash === sourceMessageHash
        && candidate.actorId === actorId
        && candidate.status === "pending_unclassified",
      );
      if (!patch) return undefined;
      patch.status = "consumed_no_patch";
      patch.consumedAt = nowIso();
      state.updatedAt = patch.consumedAt;
      await this.persist(state, "human_patch_consumed", "system", {
        patchId: patch.patchId,
        sourceMessageHash: patch.sourceMessageHash,
        outcome: "consumed_no_patch",
      }, patch.targetBranchIds[0]);
      return patch;
    });
  }

  async finalize(finalClaim: string): Promise<{ state: WorkflowState; submissionPath: string; frontendPath: string; manifestPath: string; viewerPath: string }> {
    return this.withMutationLock(async () => {
      const state = await this.load();
      assertMutable(state);
      const pending = (state.pendingHumanPatches ?? []).filter((patch) => patch.status === "pending");
      if (pending.length) throw new Error(`Finalization is blocked by authenticated human patch ${pending.at(-1)?.patchId}. Apply or explicitly supersede it first.`);
      if (state.pendingQuestions.length) throw new Error(`Finalization is blocked by ${state.pendingQuestions.length} unresolved research question(s).`);
      if (!state.reviews.length) throw new Error("Finalization requires at least one recorded Reviewer decision.");
      if (!state.humanDecisions.length) throw new Error("Finalization requires a recorded human checkpoint.");
      const validClaimApproval = [...state.humanDecisions].reverse().find((decision) =>
        decision.decision === "approve_claim" && !decision.invalidatedAt,
      );
      if (!validClaimApproval) throw new Error("Finalization requires a current claim approval after the latest route-role change.");
      if (!Object.keys(state.artifacts).length) throw new Error("Finalization requires at least one hashed evidence artifact.");
      state.finalClaim = finalClaim.trim();
      state.phase = "complete";
      state.finalizedAt = nowIso();
      state.updatedAt = state.finalizedAt;
      state.nodes.research_object.status = "complete";
      const submissionPath = join(this.runDir, "checkpoint_submission.json");
      const frontendPath = join(this.runDir, "route_tree_frontend_state.json");
      const manifestPath = join(this.runDir, "evidence_manifest.json");
      const viewerPath = join(this.runDir, "research_route_viewer.html");
      await atomicWrite(submissionPath, JSON.stringify(buildCheckpointSubmission(state), null, 2));
      await atomicWrite(frontendPath, JSON.stringify(buildFrontendState(state), null, 2));
      await atomicWrite(manifestPath, JSON.stringify(Object.values(state.artifacts), null, 2));
      await atomicWrite(viewerPath, buildStandaloneViewer(state));
      await this.persist(state, "finalized", "system", { submissionPath, frontendPath, manifestPath, viewerPath });
      return { state, submissionPath, frontendPath, manifestPath, viewerPath };
    });
  }

  private async withMutationLock<T>(operation: () => Promise<T>): Promise<T> {
    const key = this.runDir;
    const previous = ResearchStore.mutationQueues.get(key) ?? Promise.resolve();
    let release!: () => void;
    const current = new Promise<void>((resolveLock) => { release = resolveLock; });
    const queued = previous.then(() => current);
    ResearchStore.mutationQueues.set(key, queued);
    await previous;
    try {
      return await operation();
    } finally {
      release();
      if (ResearchStore.mutationQueues.get(key) === queued) {
        ResearchStore.mutationQueues.delete(key);
      }
    }
  }

  private async persist(
    state: WorkflowState,
    type: ResearchEvent["type"],
    actor: ResearchEvent["actor"],
    payload: Record<string, unknown>,
    branchId?: string,
  ): Promise<void> {
    await mkdir(dirname(this.statePath), { recursive: true });
    state.stateVersion = (state.stateVersion ?? 0) + 1;
    const serialized = JSON.stringify(state, null, 2);
    await atomicWrite(this.statePath, serialized);
    const event: ResearchEvent = {
      eventId: makeId("event"),
      type,
      timestamp: nowIso(),
      actor,
      branchId,
      payload,
      stateHash: sha256Text(state),
    };
    await appendFile(this.eventsPath, `${JSON.stringify(event)}\n`, "utf8");
  }
}

async function atomicWrite(path: string, content: string): Promise<void> {
  await mkdir(dirname(path), { recursive: true });
  const temporaryPath = `${path}.${process.pid}.${makeId("tmp")}`;
  await writeFile(temporaryPath, content, "utf8");
  await rename(temporaryPath, path);
}

function validateContract(contract: ResearchContract): void {
  const required: Array<keyof ResearchContract> = [
    "researchQuestion", "boundary", "observationWindow", "population", "outcome", "covariates",
    "candidateSupports", "intendedClaim", "prohibitedClaims",
  ];
  for (const key of required) {
    const value = contract[key];
    if (value === undefined || value === null || value === "" || (Array.isArray(value) && value.length === 0)) {
      throw new Error(`Research contract field is required: ${key}`);
    }
  }
}

function validateState(state: WorkflowState): void {
  if (state.schemaVersion !== "2.0") throw new Error(`Unsupported state schema: ${String(state.schemaVersion)}`);
  if (!PHASES.includes(state.phase)) throw new Error(`Invalid workflow phase: ${state.phase}`);
  if (!state.nodes[state.activeBranchId]) throw new Error(`Active branch is missing: ${state.activeBranchId}`);
  if (state.activeFrontier) {
    const branch = state.nodes[state.activeFrontier.branchId];
    const family = state.nodes[state.activeFrontier.familyId];
    if (!branch || !family) throw new Error("Active frontier references a missing route or family.");
    if (state.activeBranchId !== branch.nodeId) throw new Error("Active frontier and current-focus pointer disagree.");
    if (!branch.parentIds.includes(family.nodeId)) throw new Error("Active frontier route does not inherit from its route family.");
    if (branch.parameters.inherited_contract_hash !== state.contractHash || family.parameters.inherited_contract_hash !== state.contractHash) {
      throw new Error("Active route family does not inherit the immutable research contract.");
    }
  }
  assertAcyclic(state.nodes);
}

function assertMutable(state: WorkflowState): void {
  if (state.phase === "complete") throw new Error("This research run is finalized and immutable.");
}

function assertAcyclic(nodes: Record<string, ResearchNode>): void {
  const visiting = new Set<string>();
  const visited = new Set<string>();
  const visit = (id: string): void => {
    if (visited.has(id)) return;
    if (visiting.has(id)) throw new Error(`Research graph cycle detected at ${id}`);
    visiting.add(id);
    for (const parentId of nodes[id]?.parentIds ?? []) {
      if (!nodes[parentId]) throw new Error(`Node ${id} references missing parent ${parentId}`);
      visit(parentId);
    }
    visiting.delete(id);
    visited.add(id);
  };
  Object.keys(nodes).forEach(visit);
}

function reviewStatus(decision: ReviewDecisionType): NodeStatus {
  return {
    proceed: "reviewed",
    repair: "repair_required",
    new_branch: "repair_required",
    block: "blocked",
    escalate: "reviewed",
  }[decision] as NodeStatus;
}

function humanStatus(decision: HumanDecisionType): NodeStatus {
  return {
    select_main: "selected",
    retain_sensitivity: "retained_sensitivity",
    request_comparison: "proposed",
    defer: "deferred",
    block: "blocked",
    approve_claim: "selected",
  }[decision] as NodeStatus;
}

function sameSet(left: string[], right: string[]): boolean {
  const a = [...new Set(left)].sort();
  const b = [...new Set(right)].sort();
  return a.length === b.length && a.every((value, index) => value === b[index]);
}

function invalidatePriorClaimApprovals(state: WorkflowState, routeDecision: HumanDecisionRecord): void {
  for (const approval of state.humanDecisions) {
    if (approval.decision !== "approve_claim" || approval.invalidatedAt) continue;
    approval.invalidatedAt = routeDecision.createdAt;
    approval.invalidatedByDecisionId = routeDecision.decisionId;
    approval.invalidationReason = `Route role changed by ${routeDecision.decision} on ${routeDecision.branchIds.join(", ")}.`;
  }
}

function clearResolvedQuestions(state: WorkflowState, branchIds: string[]): void {
  const exactActions = new Set(state.reviews
    .filter((review) => branchIds.includes(review.branchId) && review.requiredAction)
    .map((review) => review.requiredAction as string));
  const branchTerms = branchIds.flatMap((branchId) => [branchId, state.nodes[branchId]?.title ?? ""])
    .map((value) => value.trim().toLowerCase())
    .filter(Boolean);
  state.pendingQuestions = state.pendingQuestions.filter((question) => {
    if (exactActions.has(question)) return false;
    const normalized = question.toLowerCase();
    return !branchTerms.some((term) => normalized.includes(term));
  });
}

function validateHumanDecisionWrite(
  state: WorkflowState,
  input: { branchIds: string[]; decision: HumanDecisionType; rationale: string; supersedesDecisionId?: string; resultingClaimBoundary?: string },
): void {
  const uniqueIds = [...new Set(input.branchIds)];
  const singleTarget = new Set<HumanDecisionType>(["select_main", "retain_sensitivity", "defer", "block"]);
  if (singleTarget.has(input.decision) && uniqueIds.length !== 1) {
    throw new Error(`${input.decision} requires exactly one target branch. Recall the intended branch ID and retry without changing other routes.`);
  }

  for (const branchId of uniqueIds) {
    if (!state.nodes[branchId]) throw new Error(`Unknown branch: ${branchId}`);
  }

  const statedIntent = `${input.rationale} ${input.resultingClaimBoundary ?? ""}`.toLowerCase();
  if (input.decision === "select_main" && /(retain|keep|preserve).{0,32}sensitivit|sensitivity.{0,32}(only|branch|comparison)|do not.{0,24}(promote|select).{0,24}main/.test(statedIntent)) {
    throw new Error("Decision/rationale conflict: sensitivity evidence cannot be written as select_main. Use retain_sensitivity for the single intended branch.");
  }
  const explicitlyRejectsPromotion = /(?:do not|don't|not to|never).{0,24}(?:promote|select|make).{0,24}(?:main|primary)/.test(statedIntent);
  if (input.decision === "retain_sensitivity" && !explicitlyRejectsPromotion && /(make (it|this).{0,16}(the )?primary|select (it|this).{0,16}as (the )?main|promote (it|this).{0,16}(the )?main)/.test(statedIntent)) {
    throw new Error("Decision/rationale conflict: a primary route cannot be written as retain_sensitivity. Use select_main or revise the rationale.");
  }
  if ((input.decision === "defer" || input.decision === "block") && /(retain|keep|preserve).{0,36}sensitivit|sensitivity.{0,24}(evidence|branch|comparison)/.test(statedIntent)) {
    throw new Error(`Decision/rationale conflict: sensitivity evidence cannot be written as ${input.decision}. Use retain_sensitivity for the single intended branch.`);
  }
  if (input.decision === "approve_claim" && (input.supersedesDecisionId || /retain|keep|preserve|promote|select.{0,24}(route|branch)|sensitivity evidence/.test(statedIntent))) {
    throw new Error("approve_claim changes only the bounded claim after route roles are settled. It cannot supersede a route decision; use retain_sensitivity, select_main, defer, or block for the explicit branch instruction.");
  }

  if (uniqueIds.length === 1 && input.decision !== "approve_claim") {
    const prior = [...state.humanDecisions].reverse().find((decision) =>
      decision.branchIds.includes(uniqueIds[0]) && decision.decision !== "approve_claim",
    );
    if (prior?.decision === input.decision) {
      throw new Error(`Duplicate human decision: ${uniqueIds[0]} is already ${prior.decision} under ${prior.decisionId}. Do not create a second record.`);
    }
    if (prior && input.supersedesDecisionId !== prior.decisionId) {
      throw new Error(`Changing ${uniqueIds[0]} from ${prior.decision} requires supersedes_decision_id=${prior.decisionId}. Supply it only when the current human explicitly changes this branch.`);
    }
  }
}

function buildCheckpointSubmission(state: WorkflowState): Record<string, unknown> {
  const nodes = Object.values(state.nodes);
  const has = (predicate: (node: ResearchNode) => boolean) => nodes.some(predicate);
  const branchParameters = nodes.flatMap((node) => Object.keys(node.parameters));
  return {
    schema_version: "2.0",
    run_id: state.runId,
    contract_hash: state.contractHash,
    final_claim: state.finalClaim,
    checkpoints: {
      C1_research_object: Boolean(state.contract.researchQuestion && state.contract.intendedClaim && state.contract.prohibitedClaims.length),
      C2_cross_scale_contract: state.contract.candidateSupports.length >= 2 && state.contract.covariates.length > 0,
      C3_common_holdout: Boolean(state.contract.validationGeography),
      C4_model_roles: has((node) => node.nodeType === "model_route") && branchParameters.some((key) => /model|role/i.test(key)),
      C5_bandwidth_reasoning: branchParameters.some((key) => /bandwidth|kernel|neighbor|support/i.test(key)),
      C6_instability_response: state.reviews.some((review) => ["repair", "new_branch", "block", "escalate"].includes(review.decision)),
      C7_persistent_state: Object.keys(state.artifacts).length > 0 && state.humanDecisions.length > 0,
      C8_claim_calibration: Boolean(state.finalClaim) && state.humanDecisions.some((decision) => Boolean(decision.resultingClaimBoundary)),
    },
    branch_roles: nodes.map(({ nodeId, title, status, claimBoundary }) => ({ nodeId, title, status, claimBoundary })),
    reviews: state.reviews,
    human_decisions: state.humanDecisions,
    artifacts: Object.values(state.artifacts).map(({ artifactId, branchId, role, path, sha256 }) => ({ artifactId, branchId, role, path, sha256 })),
  };
}

function buildFrontendState(state: WorkflowState): Record<string, unknown> {
  return {
    schemaVersion: state.schemaVersion,
    runId: state.runId,
    phase: state.phase,
    contractHash: state.contractHash,
    nodes: Object.values(state.nodes),
    edges: Object.values(state.nodes).flatMap((node) => node.parentIds.map((parentId) => ({ source: parentId, target: node.nodeId }))),
    artifacts: Object.values(state.artifacts),
    reviews: state.reviews,
    humanDecisions: state.humanDecisions,
    finalClaim: state.finalClaim,
    stateHash: sha256Text(stableJson(state)),
  };
}
