"""
Quality Controller Agent — 输出可靠性保障

Recommender-mode quality control is reflection-driven: deterministic checks
provide guardrails, while MemoryReflector judges contextual trustworthiness.
Configurator-mode validation remains deterministic for syntax/resource/parameter
constraints.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .base import AgentMessage, AgentRole, BaseAgent
from ..core.memory import MemoryReflector

logger = logging.getLogger(__name__)

QUALITY_DIMENSIONS = (
    "semantic_relevance",
    "historical_reliability",
    "metadata_completeness",
    "context_alignment",
)

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


def _neutral_weights() -> Dict[str, float]:
    value = 1.0 / len(QUALITY_DIMENSIONS)
    return {dimension: value for dimension in QUALITY_DIMENSIONS}


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
    reflection: Dict[str, Any] = field(default_factory=dict)


class QualityController(BaseAgent):
    """
    Quality Controller — 跨层输出验证

    双模式评估:
    1. Recommender 评估 (MemoryReflector targeted reflection)
    2. Configurator 评估 (三元可执行性检验: 语法 ∧ 资源可用 ∧ 参数约束)

    每次评估生成 QualityReport, 不满足阈值则触发重试或拒绝.
    """

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        weights: Optional[Dict[str, float]] = None,
        threshold: Optional[float] = None,
        max_retry: Optional[int] = None,
        reflector: Optional[Any] = None,
        **kwargs,
    ):
        super().__init__(role=AgentRole.QUALITY_CONTROLLER, llm_client=llm_client, **kwargs)
        self.weights = weights or _neutral_weights()
        self.threshold = float(threshold if threshold is not None else 0.5)
        self.max_retry = int(max_retry if max_retry is not None else 0)
        self.reflector = reflector or MemoryReflector(llm_client=llm_client)
        # Historical success tracking
        self._success_history: Dict[str, List[bool]] = {}
        self._assessment_log: List[QualityReport] = []

    @property
    def role_prompt(self) -> str:
        return (
            "You are the Quality Controller Agent. For each upstream agent output, "
            "perform contextual reflection rather than applying a fixed weighted rubric. "
            "Judge whether the output is trustworthy for this urban-analysis task, "
            "including data authority, evidence sufficiency, spatial/temporal coverage, "
            "uncertainty, and user/task alignment. Preserve deterministic schema/resource "
            "checks for configurator mode. Return JSON with confidence, issues, risks, "
            "reflection, and recommendation=accept|retry|reject."
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
                "reflection": report.reflection,
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
    # Recommender assessment: targeted reflection, not a weighted rubric
    # ------------------------------------------------------------------

    async def _assess_recommender(
        self, agent_role: str, output: Dict, task_context: Dict
    ) -> QualityReport:
        guardrail_scores = {
            "metadata_completeness": self._score_metadata_completeness(output, task_context),
            "context_alignment": self._score_context_alignment(output, task_context),
        }
        deterministic_issues = self._collect_guardrail_issues(guardrail_scores, output, task_context)
        reflection = await self.reflector.reflect_quality(
            agent_role=agent_role,
            output=output,
            task_context=task_context,
            deterministic_issues=deterministic_issues,
        )
        confidence = float(reflection.get("confidence", 0.0))
        recommendation = str(reflection.get("recommendation") or "retry")
        issues = [str(item) for item in reflection.get("issues", [])]
        passed = bool(reflection.get("passed")) and recommendation == "accept" and confidence >= self.threshold
        return QualityReport(
            agent_role=agent_role,
            confidence_score=confidence,
            passed=passed,
            dimension_scores={**guardrail_scores, "reflection_confidence": confidence},
            issues=issues,
            recommendation=recommendation,
            reflection=reflection,
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

    def _collect_guardrail_issues(self, scores: Dict[str, float], output: Dict, task_context: Dict) -> List[str]:
        issues = []
        if scores.get("metadata_completeness", 1) < 0.75:
            issues.append("Missing required output fields")
        required = task_context.get("required_fields", [])
        if "answer" in required and not self._extract_answer_like(output):
            issues.append("Missing usable answer or analysis")
        if scores.get("context_alignment", 1) < 0.5:
            issues.append("Spatial/temporal context mismatch")
        if self._contains_placeholder(output):
            issues.append("Output contains placeholder text")
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
