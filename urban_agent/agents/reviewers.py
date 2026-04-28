"""
Review Layer Agents — 质量审查与人机协作

第一版实现沿用 SpatialReviewer 角色名以保持兼容，
但其内部已经升级为 policy-based Review Hub：

1. Spatial Structural Review
2. Temporal Consistency Review
3. Population and Stakeholder Review
4. Evidence and Governance Review
5. Optional artifact reviewers (cartography / report)

QualityController 继续负责跨层聚合与返工决策，
Review Hub 负责领域有效性判断而非通用置信度评分。
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from .base import AgentMessage, AgentRole, BaseAgent

logger = logging.getLogger(__name__)


class SpatialReviewerAgent(BaseAgent):
    """
    Urban validity review hub.

    兼容旧的 SpatialReviewer 命名，但职责已扩展为多策略审查：
    - Spatial Structural Review
    - Temporal Consistency Review
    - Population and Stakeholder Review
    - Evidence and Governance Review
    - Optional artifact review for cartography / report outputs
    """

    REQUIRED_POLICY_THRESHOLDS = {
        "spatial_structural_review": 0.55,
        "temporal_consistency_review": 0.55,
        "population_and_stakeholder_review": 0.50,
        "evidence_and_governance_review": 0.55,
    }

    URBAN_VALIDITY_THRESHOLD = 0.65

    def __init__(self, llm_client: Optional[Any] = None, **kwargs):
        super().__init__(role=AgentRole.SPATIAL_REVIEWER, llm_client=llm_client, **kwargs)

    @property
    def role_prompt(self) -> str:
        return (
            "You are the Urban Validity Review Hub. You review whether urban analysis outputs "
            "are valid under spatial, temporal, population, and evidence constraints.\n"
            "You do not replace the Quality Controller. Instead, you provide domain-grounded "
            "review signals for downstream quality aggregation and revision routing."
        )

    async def execute(self, message: AgentMessage) -> AgentMessage:
        self.log_message(message)
        results = message.payload

        policy_scores = self._evaluate_required_policies(results)
        artifact_scores = self._evaluate_optional_artifact_policies(results)
        issues = self._collect_policy_issues(policy_scores, artifact_scores)

        if self.llm_client is not None and not issues:
            llm_issues = await self._llm_review(results)
            issues.extend(llm_issues)

        required_scores = {
            name: data["score"]
            for name, data in policy_scores.items()
        }
        hard_failures = [
            name
            for name, threshold in self.REQUIRED_POLICY_THRESHOLDS.items()
            if required_scores.get(name, 0.0) < threshold
        ]
        urban_validity_score = (
            sum(required_scores.values()) / len(required_scores)
            if required_scores else 0.0
        )
        alignment_score = required_scores.get("spatial_structural_review", 0.0)
        passed = not hard_failures and urban_validity_score >= self.URBAN_VALIDITY_THRESHOLD

        return AgentMessage(
            sender=self.role,
            receiver=AgentRole.MANAGER,
            msg_type="review",
            payload={
                "quality_score": urban_validity_score,
                "urban_validity_score": urban_validity_score,
                "alignment_score": alignment_score,
                "passed": passed,
                "issues": issues,
                "policy_scores": policy_scores,
                "artifact_scores": artifact_scores,
                "hard_failures": hard_failures,
                "recommendation": "accept" if passed else "revise",
            },
            trace_id=message.trace_id,
        )

    def _iter_subtask_results(self, results: Dict):
        subtask_results = results.get("subtask_results", {})
        for st_id, st_data in subtask_results.items():
            result = st_data.get("result", {})
            if isinstance(result, dict):
                yield st_id, st_data, result

    def _evaluate_required_policies(self, results: Dict) -> Dict[str, Dict[str, Any]]:
        return {
            "spatial_structural_review": self._spatial_structural_review(results),
            "temporal_consistency_review": self._temporal_consistency_review(results),
            "population_and_stakeholder_review": self._population_and_stakeholder_review(results),
            "evidence_and_governance_review": self._evidence_and_governance_review(results),
        }

    def _evaluate_optional_artifact_policies(self, results: Dict) -> Dict[str, Dict[str, Any]]:
        return {
            "cartography_review": self._cartography_review(results),
            "report_review": self._report_review(results),
        }

    def _spatial_structural_review(self, results: Dict) -> Dict[str, Any]:
        issues = []
        score = 1.0

        for st_id, st_data, result in self._iter_subtask_results(results):
            if st_data.get("status") == "failed":
                issues.append(f"{st_id}: subtask failed before spatial review")
                score -= 0.2

            for key in ("latitude", "lat"):
                val = result.get(key)
                if val is not None and not (-90 <= float(val) <= 90):
                    issues.append(f"{st_id}: latitude {val} out of range [-90, 90]")
                    score -= 0.2
            for key in ("longitude", "lon", "lng"):
                val = result.get(key)
                if val is not None and not (-180 <= float(val) <= 180):
                    issues.append(f"{st_id}: longitude {val} out of range [-180, 180]")
                    score -= 0.2

            alignment = result.get("alignment_diagnostics", {})
            evidence = result.get("evidence_manifest", {})
            spatial = evidence.get("spatial", {})
            corrections = result.get("correction_audit", [])
            human_alignment = result.get("human_alignment", {})

            if not spatial.get("bbox"):
                issues.append(f"{st_id}: missing bbox in evidence manifest")
                score -= 0.1
            if not spatial.get("crs"):
                issues.append(f"{st_id}: missing CRS in evidence manifest")
                score -= 0.1
            if not alignment.get("preferred_scale"):
                issues.append(f"{st_id}: missing preferred scale diagnostics")
                score -= 0.1
            if alignment.get("maup_like_risk") == "high" and not corrections and not human_alignment:
                issues.append(f"{st_id}: high MAUP-like risk without correction record")
                score -= 0.15

        return {
            "score": max(0.0, min(1.0, score)),
            "issues": issues,
            "applicable": True,
        }

    def _temporal_consistency_review(self, results: Dict) -> Dict[str, Any]:
        issues = []
        score = 1.0

        for st_id, _, result in self._iter_subtask_results(results):
            evidence = result.get("evidence_manifest", {})
            temporal = evidence.get("temporal", {})

            if not temporal:
                issues.append(f"{st_id}: missing temporal evidence")
                score -= 0.55
                continue

            if not temporal.get("time_window"):
                issues.append(f"{st_id}: missing time_window")
                score -= 0.15
            if not temporal.get("granularity"):
                issues.append(f"{st_id}: missing temporal granularity")
                score -= 0.15
            if not temporal.get("freshness"):
                issues.append(f"{st_id}: missing freshness declaration")
                score -= 0.10
            if temporal.get("forecast_horizon") and not temporal.get("time_window"):
                issues.append(f"{st_id}: forecast horizon provided without observation window")
                score -= 0.15

        return {
            "score": max(0.0, min(1.0, score)),
            "issues": issues,
            "applicable": True,
        }

    def _population_and_stakeholder_review(self, results: Dict) -> Dict[str, Any]:
        issues = []
        score = 1.0

        for st_id, _, result in self._iter_subtask_results(results):
            evidence = result.get("evidence_manifest", {})
            population = evidence.get("population", {})
            human_alignment = result.get("human_alignment", {})
            stakeholder_feedback = human_alignment.get("stakeholder_feedback", [])

            if not population:
                issues.append(f"{st_id}: missing population or stakeholder schema")
                score -= 0.60
                continue

            target_group = population.get("target_group")
            observed_group = population.get("observed_group")
            affected_group = population.get("affected_group")
            stakeholder_source = population.get("stakeholder_source")
            sampling_bias = population.get("sampling_bias")

            if not target_group:
                issues.append(f"{st_id}: missing target_group")
                score -= 0.15
            if not observed_group:
                issues.append(f"{st_id}: missing observed_group")
                score -= 0.15
            if not affected_group:
                issues.append(f"{st_id}: missing affected_group")
                score -= 0.10
            if target_group and observed_group and target_group != observed_group and not sampling_bias:
                issues.append(f"{st_id}: target_group and observed_group differ without sampling_bias note")
                score -= 0.15
            if not stakeholder_source and not stakeholder_feedback:
                issues.append(f"{st_id}: no stakeholder source or review feedback attached")
                score -= 0.10

        return {
            "score": max(0.0, min(1.0, score)),
            "issues": issues,
            "applicable": True,
        }

    def _evidence_and_governance_review(self, results: Dict) -> Dict[str, Any]:
        issues = []
        score = 1.0

        for st_id, _, result in self._iter_subtask_results(results):
            evidence = result.get("evidence_manifest", {})
            governance = evidence.get("governance", {})
            tags = evidence.get("tags", [])

            if not governance:
                issues.append(f"{st_id}: missing governance metadata")
                score -= 0.60
                continue

            for field in ("provenance", "license", "collection_method", "uncertainty"):
                if not governance.get(field):
                    issues.append(f"{st_id}: missing governance field {field}")
                    score -= 0.10

            missing_layers = governance.get("missing_layers", [])
            if missing_layers:
                issues.append(f"{st_id}: missing evidence layers {missing_layers}")
                score -= 0.10
            if not tags:
                issues.append(f"{st_id}: evidence manifest has no tags")
                score -= 0.05

        return {
            "score": max(0.0, min(1.0, score)),
            "issues": issues,
            "applicable": True,
        }

    def _cartography_review(self, results: Dict) -> Dict[str, Any]:
        issues = []
        score = 1.0
        applicable = False

        for st_id, _, result in self._iter_subtask_results(results):
            outputs = result.get("outputs", [])
            if not any(name in outputs for name in ("svg_overlay", "geojson", "map")):
                continue
            applicable = True
            if not result.get("legend") and not result.get("symbology"):
                issues.append(f"{st_id}: cartographic artifact lacks legend or symbology metadata")
                score -= 0.20

        return {
            "score": max(0.0, min(1.0, score)),
            "issues": issues,
            "applicable": applicable,
        }

    def _report_review(self, results: Dict) -> Dict[str, Any]:
        issues = []
        score = 1.0
        applicable = False

        for st_id, _, result in self._iter_subtask_results(results):
            report = result.get("report")
            if not isinstance(report, str) or not report.strip():
                continue
            applicable = True
            report_lower = report.lower()
            if "method" not in report_lower and "result" not in report_lower:
                issues.append(f"{st_id}: report lacks explicit methods/results sections")
                score -= 0.15
            if "because" not in report_lower and "evidence" not in report_lower and "based on" not in report_lower:
                issues.append(f"{st_id}: report lacks explicit evidence linkage")
                score -= 0.15

        return {
            "score": max(0.0, min(1.0, score)),
            "issues": issues,
            "applicable": applicable,
        }

    def _collect_policy_issues(
        self,
        policy_scores: Dict[str, Dict[str, Any]],
        artifact_scores: Dict[str, Dict[str, Any]],
    ) -> list[str]:
        issues = []
        for payload in list(policy_scores.values()) + list(artifact_scores.values()):
            issues.extend(payload.get("issues", []))
        return issues

    async def _llm_review(self, results: Dict) -> list[str]:
        """LLM 辅助审查"""
        import json

        prompt = (
            f"{self.role_prompt}\n\n"
            f"Review these results:\n{json.dumps(results, ensure_ascii=False, default=str)[:3000]}\n\n"
            "List any spatial inconsistencies as a JSON array of strings. "
            "Return [] if no issues."
        )
        try:
            response = await self.call_llm(prompt)
            return json.loads(response) if response.strip().startswith("[") else []
        except Exception:
            return []


class HumanCheckpointAgent(BaseAgent):
    """
    人机协作 Agent — 6个决策检查点

    DP-1: Task interpretation & scoping
    DP-2: Data source validation
    DP-3: Spatial representation review
    DP-4: Intervention proposal selection
    DP-5: Parameter tuning
    DP-6: Result interpretation & narrative

    三种交互模式：
    - guided:    每个 DP 都暂停等待人工确认
    - supervisory: 自动执行 + 事后检查点
    - autonomous:  完全自动（不暂停）
    """

    def __init__(
        self,
        interaction_mode: str = "autonomous",
        human_callback: Optional[Callable] = None,
        **kwargs,
    ):
        super().__init__(role=AgentRole.HUMAN_CHECKPOINT, **kwargs)
        self.interaction_mode = interaction_mode  # guided / supervisory / autonomous
        self.human_callback = human_callback
        self._checkpoint_log: list[Dict] = []

    @property
    def role_prompt(self) -> str:
        return (
            "You are the Human Checkpoint Agent. You manage decision points (DP-1 to DP-6) "
            "where human experts can review and adjust the analysis workflow."
        )

    async def execute(self, message: AgentMessage) -> AgentMessage:
        self.log_message(message)
        checkpoint_id = message.payload.get("checkpoint_id", "DP-0")
        data = message.payload.get("data", {})

        decision = await self._process_checkpoint(checkpoint_id, data)

        self._checkpoint_log.append({
            "checkpoint": checkpoint_id,
            "mode": self.interaction_mode,
            "decision": decision,
        })

        return AgentMessage(
            sender=self.role,
            receiver=AgentRole.MANAGER,
            msg_type="feedback",
            payload={"checkpoint_id": checkpoint_id, "decision": decision},
            trace_id=message.trace_id,
        )

    async def _process_checkpoint(self, checkpoint_id: str, data: Dict) -> Dict:
        """根据交互模式处理检查点"""
        if self.interaction_mode == "autonomous":
            return {"action": "approve", "reason": "autonomous mode"}

        if self.interaction_mode == "guided" and self.human_callback:
            return await self._ask_human(checkpoint_id, data)

        if self.interaction_mode == "supervisory":
            # 事后记录，不阻塞
            logger.info(f"Supervisory checkpoint {checkpoint_id}: auto-approved, logged for review")
            return {"action": "approve", "reason": "supervisory auto-approve"}

        return {"action": "approve", "reason": "no callback configured"}

    async def _ask_human(self, checkpoint_id: str, data: Dict) -> Dict:
        """请求人工输入"""
        if self.human_callback is None:
            return {"action": "approve", "reason": "no callback"}

        import asyncio

        if asyncio.iscoroutinefunction(self.human_callback):
            return await self.human_callback(checkpoint_id, data)
        return self.human_callback(checkpoint_id, data)
