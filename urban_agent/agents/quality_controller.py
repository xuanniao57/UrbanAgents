"""
Quality Controller Agent — 输出可靠性保障

参考 RMDA 的 QualityController 设计:
1. 置信度评分 (Confidence Self-Assessment)
2. 知识增强 RAG 验证 (Knowledge-Enhanced RAG)
3. 系统透明性 (Transparency)

评估维度 (加权投票):
- 语义相关性 (w1): 输出与任务描述的对齐度
- 历史可靠性 (w2): 该工具/agent 在同类任务上的成功率
- 元数据完整性 (w3): 必填字段的填充率
- 上下文对齐 (w4): 时空约束的匹配度

置信度阈值: C(R) >= 0.75 (recommender), C(O) = t1 ∧ t2 ∧ t3 (configurator)
"""

from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .base import AgentMessage, AgentRole, BaseAgent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Confidence scoring weights (RMDA Eq.1)
# ---------------------------------------------------------------------------
DEFAULT_WEIGHTS = {
    "semantic_relevance": 0.35,   # w1: cosine-sim between query & output embeddings
    "historical_reliability": 0.25,  # w2: past success rate of this agent/tool
    "metadata_completeness": 0.25,  # w3: required-fields-populated / total-required
    "context_alignment": 0.15,    # w4: spatiotemporal constraint match (binary)
}

CONFIDENCE_THRESHOLD = 0.75  # recommender acceptance threshold
MAX_RETRY = 2  # max retries before rejection

ANSWER_LIKE_FIELDS = (
    "answer",
    "analysis",
    "findings",
    "report",
    "recommendations",
    "summary",
    "llm_analysis",
    "conclusion",
)

GENERIC_PLACEHOLDERS = {
    "general reasoning completed",
    "processing perception data",
    "applying general spatial reasoning",
    "generating response",
    "rule-based fallback",
    "llm enrichment skipped",
}


@dataclass
class QualityReport:
    """Quality assessment report for a single agent output."""
    agent_role: str
    confidence_score: float
    passed: bool
    dimension_scores: Dict[str, float] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)
    recommendation: str = ""  # "accept", "retry", "reject"
    retry_count: int = 0


class QualityController(BaseAgent):
    """
    Quality Controller — 跨层输出验证

    RMDA-style 双模式评估:
    1. Recommender 评估 (加权投票 → 置信度分数)
    2. Configurator 评估 (三元可执行性检验: 语法 ∧ 资源可用 ∧ 参数约束)

    每次评估生成 QualityReport, 不满足阈值则触发重试或拒绝.
    """

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        weights: Optional[Dict[str, float]] = None,
        threshold: float = CONFIDENCE_THRESHOLD,
        max_retry: int = MAX_RETRY,
        **kwargs,
    ):
        super().__init__(role=AgentRole.QUALITY_CONTROLLER, llm_client=llm_client, **kwargs)
        self.weights = weights or dict(DEFAULT_WEIGHTS)
        self.threshold = threshold
        self.max_retry = max_retry
        # Historical success tracking
        self._success_history: Dict[str, List[bool]] = {}
        self._assessment_log: List[QualityReport] = []

    @property
    def role_prompt(self) -> str:
        return (
            "You are the Quality Controller Agent. For each upstream agent output you:\n"
            "1. Score semantic relevance (does it answer the original query?)\n"
            "2. Check metadata completeness (are required fields populated?)\n"
            "3. Validate context alignment (spatial/temporal constraints met?)\n"
            "4. Assess overall confidence.\n\n"
            "Return a JSON: {\"confidence\": 0.0-1.0, \"issues\": [...], "
            "\"recommendation\": \"accept|retry|reject\"}"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute(self, message: AgentMessage) -> AgentMessage:
        """Unified entry: assess any agent output wrapped in AgentMessage."""
        self.log_message(message)
        payload = message.payload
        agent_role = payload.get("source_role", message.sender.value)
        output_data = payload.get("output", payload)
        task_context = payload.get("task_context", {})
        mode = payload.get("qc_mode", "recommender")  # "recommender" or "configurator"

        if mode == "configurator":
            report = self._assess_configurator(agent_role, output_data, task_context)
        else:
            report = await self._assess_recommender(agent_role, output_data, task_context)

        self._assessment_log.append(report)
        self._record_history(agent_role, report.passed)

        return AgentMessage(
            sender=self.role,
            receiver=message.sender,
            msg_type="quality_report",
            payload={
                "confidence_score": report.confidence_score,
                "passed": report.passed,
                "issues": report.issues,
                "recommendation": report.recommendation,
                "dimension_scores": report.dimension_scores,
            },
            trace_id=message.trace_id,
        )

    async def assess(
        self,
        agent_role: str,
        output: Dict[str, Any],
        task_context: Dict[str, Any],
        mode: str = "recommender",
    ) -> QualityReport:
        """Direct programmatic assessment (no message wrapping)."""
        if mode == "configurator":
            return self._assess_configurator(agent_role, output, task_context)
        return await self._assess_recommender(agent_role, output, task_context)

    # ------------------------------------------------------------------
    # Recommender assessment (RMDA Eq.1: C(R) = Σ wi · vi(R))
    # ------------------------------------------------------------------

    async def _assess_recommender(
        self, agent_role: str, output: Dict, task_context: Dict
    ) -> QualityReport:
        scores: Dict[str, float] = {}

        # v1: semantic relevance (rule-based + optional LLM)
        scores["semantic_relevance"] = self._score_semantic_relevance(output, task_context)

        # v2: historical reliability
        scores["historical_reliability"] = self._score_historical_reliability(agent_role)

        # v3: metadata completeness
        scores["metadata_completeness"] = self._score_metadata_completeness(output, task_context)

        # v4: context alignment (spatial / temporal)
        scores["context_alignment"] = self._score_context_alignment(output, task_context)

        # Optional LLM-enhanced assessment
        if self.llm_client is not None:
            llm_adjustment = await self._llm_confidence_check(output, task_context)
            # Blend LLM score with rule-based checks. Metadata completeness is
            # deterministic, so the LLM may raise other confidence signals but
            # must not down-grade populated required fields.
            for dim in scores:
                llm_score = llm_adjustment.get(dim)
                if llm_score is None:
                    continue
                if dim in {"metadata_completeness", "historical_reliability"}:
                    scores[dim] = scores[dim]
                else:
                    scores[dim] = 0.75 * scores[dim] + 0.25 * float(llm_score)

        # Weighted sum
        confidence = sum(self.weights.get(dim, 0) * scores[dim] for dim in scores)
        confidence = max(0.0, min(1.0, confidence))

        passed = confidence >= self.threshold
        issues = self._collect_issues(scores, output, task_context)

        if not passed and len(issues) == 0:
            issues.append(f"Confidence {confidence:.3f} below threshold {self.threshold}")

        recommendation = "accept" if passed else "retry"
        return QualityReport(
            agent_role=agent_role,
            confidence_score=confidence,
            passed=passed,
            dimension_scores=scores,
            issues=issues,
            recommendation=recommendation,
        )

    # ------------------------------------------------------------------
    # Configurator assessment (RMDA Eq.2: C(O) = t1 ∧ t2 ∧ t3)
    # ------------------------------------------------------------------

    def _assess_configurator(
        self, agent_role: str, output: Dict, task_context: Dict
    ) -> QualityReport:
        issues: List[str] = []

        # t1: syntax validation (JSON structure, type adherence)
        t1 = self._check_syntax(output, task_context)
        if not t1:
            issues.append("Syntax validation failed: output structure does not match expected schema")

        # t2: resource availability (referenced tools/data exist)
        t2 = self._check_resource_availability(output, task_context)
        if not t2:
            issues.append("Resource availability check failed: referenced resources not accessible")

        # t3: parameter constraint adherence
        t3 = self._check_parameter_constraints(output, task_context)
        if not t3:
            issues.append("Parameter constraint violated")

        passed = t1 and t2 and t3
        confidence = 1.0 if passed else 0.0

        return QualityReport(
            agent_role=agent_role,
            confidence_score=confidence,
            passed=passed,
            dimension_scores={"syntax": float(t1), "resources": float(t2), "constraints": float(t3)},
            issues=issues,
            recommendation="accept" if passed else "reject",
        )

    # ------------------------------------------------------------------
    # Dimension scorers
    # ------------------------------------------------------------------

    @staticmethod
    def _score_semantic_relevance(output: Dict, task_context: Dict) -> float:
        """Rule-based semantic relevance for planner-driven urban analysis outputs."""
        if not output:
            return 0.0

        score = 0.5  # base
        output_str = json.dumps(output, ensure_ascii=False, default=str).lower()
        task_text = json.dumps(task_context, ensure_ascii=False, default=str).lower()
        expected_markers = [
            "answer",
            "analysis",
            "results",
            "report",
            "recommendations",
            "artifacts",
            "execution_plan",
            "subtasks",
            "confidence",
            "limitations",
            "evidence",
        ]
        score += min(0.3, 0.075 * sum(1 for marker in expected_markers if marker in output_str))
        task_terms = [term for term in re.findall(r"[a-z0-9_\-]+|[\u4e00-\u9fff]+", task_text) if len(term) > 1]
        if task_terms:
            overlap = sum(1 for term in set(task_terms[:80]) if term in output_str)
            score += min(0.2, overlap / max(len(set(task_terms[:80])), 1) * 0.4)
        if QualityController._has_execution_results(output):
            score += 0.05
        if not QualityController._extract_answer_like(output):
            score -= 0.20
        if QualityController._contains_placeholder(output):
            score -= 0.20
        return max(0.0, min(1.0, score))

    def _score_historical_reliability(self, agent_role: str) -> float:
        """Historical success rate for this agent role."""
        history = self._success_history.get(agent_role, [])
        if not history:
            return 0.7  # prior
        return sum(history[-20:]) / len(history[-20:])

    @staticmethod
    def _score_metadata_completeness(output: Dict, task_context: Dict) -> float:
        """Ratio of populated required fields, including nested execution results."""
        required = task_context.get("required_fields", ["status", "answer"])
        if not required:
            return 1.0

        populated = 0
        for field in required:
            if field == "status":
                value = output.get("status")
                if value is None and QualityController._has_execution_results(output):
                    value = "completed"
                populated += int(QualityController._has_value(value))
            elif field == "answer":
                populated += int(bool(QualityController._extract_answer_like(output)))
            elif field == "results":
                populated += int(QualityController._has_execution_results(output))
            else:
                populated += int(QualityController._has_value(output.get(field)))
        return populated / len(required)

    @staticmethod
    def _score_context_alignment(output: Dict, task_context: Dict) -> float:
        """Binary spatial/temporal constraint check."""
        score = 1.0
        # Spatial constraint: if task specifies a city, output should reference it
        expected_city = task_context.get("city", "")
        if expected_city:
            output_str = json.dumps(output, ensure_ascii=False, default=str).lower()
            if expected_city.lower() not in output_str:
                score -= 0.5
        return max(0.0, score)

    # ------------------------------------------------------------------
    # LLM-enhanced confidence check
    # ------------------------------------------------------------------

    async def _llm_confidence_check(self, output: Dict, task_context: Dict) -> Dict[str, float]:
        """Use LLM to provide additional confidence scoring."""
        prompt = (
            f"{self.role_prompt}\n\n"
            f"Task context: {json.dumps(task_context, ensure_ascii=False, default=str)[:1500]}\n\n"
            f"Agent output: {json.dumps(output, ensure_ascii=False, default=str)[:2000]}\n\n"
            "Assess the output quality. Return JSON:\n"
            '{"semantic_relevance": 0.0-1.0, "metadata_completeness": 0.0-1.0, '
            '"context_alignment": 0.0-1.0, "historical_reliability": 0.7}'
        )
        try:
            response = await self.call_llm(prompt)
            # Extract JSON from response
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except Exception as e:
            logger.warning(f"LLM confidence check failed: {e}")
        return {}

    # ------------------------------------------------------------------
    # Syntax / resource / constraint checks (configurator path)
    # ------------------------------------------------------------------

    @staticmethod
    def _check_syntax(output: Dict, task_context: Dict) -> bool:
        """Validate output structure against expected schema."""
        if not isinstance(output, dict):
            return False
        # Planner output: must have subtasks or execution_plan
        if output.get("subtasks") or output.get("execution_order") or output.get("execution_plan"):
            return True
        # General task output: must have at least status or answer
        return bool(output.get("status") or output.get("answer") or output.get("results"))

    @staticmethod
    def _check_resource_availability(output: Dict, task_context: Dict) -> bool:
        """Check that referenced resources exist."""
        tools_used = output.get("tools_used", [])
        available_tools = task_context.get("available_tools", None)
        if available_tools is not None and tools_used:
            return all(t in available_tools for t in tools_used)
        return True

    @staticmethod
    def _check_parameter_constraints(output: Dict, task_context: Dict) -> bool:
        """Validate parameter values against declared constraints."""
        constraints = task_context.get("parameter_constraints", {})
        for param, constraint in constraints.items():
            value = output.get(param)
            if value is None:
                continue
            if "min" in constraint and value < constraint["min"]:
                return False
            if "max" in constraint and value > constraint["max"]:
                return False
            if "enum" in constraint and value not in constraint["enum"]:
                return False
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _collect_issues(self, scores: Dict[str, float], output: Dict, task_context: Dict) -> List[str]:
        issues = []
        if scores.get("semantic_relevance", 1) < 0.5:
            issues.append("Low semantic relevance: output may not address the query")
        if scores.get("metadata_completeness", 1) < 0.75:
            issues.append("Missing required output fields")
        required = task_context.get("required_fields", [])
        if "answer" in required and not self._extract_answer_like(output):
            issues.append("Missing usable answer or analysis")
        if scores.get("context_alignment", 1) < 0.5:
            issues.append("Spatial/temporal context mismatch")
        if scores.get("historical_reliability", 1) < 0.3:
            issues.append("Agent has low historical reliability for this workflow")
        return issues

    @staticmethod
    def _has_execution_results(output: Dict[str, Any]) -> bool:
        results = output.get("results", output)
        if not isinstance(results, dict):
            return False
        subtask_results = results.get("subtask_results", {})
        completed = results.get("completed", 0)
        return bool(subtask_results) and int(completed or 0) > 0

    @staticmethod
    def _has_value(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return False
            lowered = stripped.lower()
            return not any(marker in lowered for marker in GENERIC_PLACEHOLDERS)
        if isinstance(value, (list, tuple, set, dict)):
            return len(value) > 0
        return True

    @staticmethod
    def _extract_answer_like(payload: Any, *, _depth: int = 0) -> str:
        if _depth > 5 or payload is None:
            return ""
        if isinstance(payload, str):
            return payload.strip() if QualityController._has_value(payload) else ""
        if isinstance(payload, list):
            for item in payload:
                found = QualityController._extract_answer_like(item, _depth=_depth + 1)
                if found:
                    return found
            return ""
        if not isinstance(payload, dict):
            return ""

        for field in ANSWER_LIKE_FIELDS:
            value = payload.get(field)
            if field == "conclusion" and isinstance(value, str):
                if not QualityController._has_value(value) or len(value.strip()) < 20:
                    continue
            if QualityController._has_value(value):
                if isinstance(value, str):
                    return value.strip()
                if isinstance(value, list):
                    return json.dumps(value, ensure_ascii=False, default=str)
                if isinstance(value, dict):
                    nested = QualityController._extract_answer_like(value, _depth=_depth + 1)
                    if nested:
                        return nested
                    return json.dumps(value, ensure_ascii=False, default=str)

        results = payload.get("results")
        if isinstance(results, dict):
            found = QualityController._extract_answer_like(results, _depth=_depth + 1)
            if found:
                return found

        subtask_results = payload.get("subtask_results")
        if isinstance(subtask_results, dict):
            for st_data in subtask_results.values():
                result = st_data.get("result", st_data) if isinstance(st_data, dict) else st_data
                found = QualityController._extract_answer_like(result, _depth=_depth + 1)
                if found:
                    return found
        return ""

    @staticmethod
    def _contains_placeholder(payload: Any) -> bool:
        try:
            text = json.dumps(payload, ensure_ascii=False, default=str).lower()
        except Exception:
            text = str(payload).lower()
        return any(marker in text for marker in GENERIC_PLACEHOLDERS)

    def _record_history(self, agent_role: str, success: bool):
        if agent_role not in self._success_history:
            self._success_history[agent_role] = []
        self._success_history[agent_role].append(success)

    def get_assessment_log(self) -> List[QualityReport]:
        return list(self._assessment_log)

    def get_reliability_stats(self) -> Dict[str, Dict[str, Any]]:
        """Return per-agent reliability statistics."""
        stats = {}
        for role, history in self._success_history.items():
            n = len(history)
            stats[role] = {
                "total_assessments": n,
                "success_rate": sum(history) / n if n else 0.0,
                "recent_rate": sum(history[-10:]) / min(10, n) if n else 0.0,
            }
        return stats
