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
            # Blend LLM score with rule-based (70% rule / 30% LLM)
            for dim in scores:
                scores[dim] = 0.7 * scores[dim] + 0.3 * llm_adjustment.get(dim, scores[dim])

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
        """Rule-based semantic relevance: check task_type alignment and key fields."""
        task_type = task_context.get("task_type", "")
        if not output:
            return 0.0

        score = 0.5  # base
        # Check if output contains expected answer fields
        expected_keys = {
            "geoqa": ["answer", "analysis"],
            "population_prediction": ["predicted_population", "answer"],
            "object_detection": ["detected_objects"],
            "geolocation": ["predicted_city", "predicted_location"],
            "mobility_prediction": ["predicted_location", "answer"],
            "traffic_signal": ["selected_phase", "answer"],
            "outdoor_navigation": ["route_actions", "answer"],
            "urban_exploration": ["selected_option", "answer"],
        }
        for key in expected_keys.get(task_type, ["answer"]):
            if key in output or key in output.get("action", {}):
                score += 0.15
        return min(1.0, score)

    def _score_historical_reliability(self, agent_role: str) -> float:
        """Historical success rate for this agent role."""
        history = self._success_history.get(agent_role, [])
        if not history:
            return 0.7  # prior
        return sum(history[-20:]) / len(history[-20:])

    @staticmethod
    def _score_metadata_completeness(output: Dict, task_context: Dict) -> float:
        """Ratio of populated required fields."""
        required = task_context.get("required_fields", ["status", "answer"])
        if not required:
            return 1.0
        populated = sum(1 for f in required if output.get(f) is not None)
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
        # Must have at least status or answer
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
        if scores.get("metadata_completeness", 1) < 0.5:
            issues.append("Missing required output fields")
        if scores.get("context_alignment", 1) < 0.5:
            issues.append("Spatial/temporal context mismatch")
        if scores.get("historical_reliability", 1) < 0.3:
            issues.append("Agent has low historical reliability for this task type")
        return issues

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
