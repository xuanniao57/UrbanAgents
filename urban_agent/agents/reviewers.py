"""
Review Layer Agents 鈥?璐ㄩ噺瀹℃煡涓庝汉鏈哄崗浣?

绗竴鐗堝疄鐜版部鐢?SpatialReviewer 瑙掕壊鍚嶄互淇濇寔鍏煎锛?
浣嗗叾鍐呴儴宸茬粡鍗囩骇涓?policy-based Review Hub锛?

1. Spatial Structural Review
2. Temporal Consistency Review
3. Population and Stakeholder Review
4. Evidence and Governance Review
5. Optional artifact reviewers (cartography / report)

QualityController 缁х画璐熻矗璺ㄥ眰鑱氬悎涓庤繑宸ュ喅绛栵紝
Review Hub 璐熻矗棰嗗煙鏈夋晥鎬у垽鏂€岄潪閫氱敤缃俊搴﹁瘎鍒嗐€?
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from .base import AgentMessage, AgentRole, BaseAgent
from ..feedback_memory import get_default_feedback_memory
from ..memory_store import FileMemoryStore

logger = logging.getLogger(__name__)


def _load_reviewer_policy() -> Dict[str, Any]:
    try:
        store = FileMemoryStore.default()
        for record in store.records("policy"):
            payload = record.to_dict()
            if payload.get("policy_id") == "urban_review_threshold_policy":
                return payload
    except Exception:
        return {}
    return {}


class SpatialReviewerAgent(BaseAgent):
    """
    Urban validity review hub.

    鍏煎鏃х殑 SpatialReviewer 鍛藉悕锛屼絾鑱岃矗宸叉墿灞曚负澶氱瓥鐣ュ鏌ワ細
    - Spatial Structural Review
    - Temporal Consistency Review
    - Population and Stakeholder Review
    - Evidence and Governance Review
    - Optional artifact review for cartography / report outputs
    """

    def _policy_criteria(self) -> Dict[str, Any]:
        """Load machine-readable review criteria from policy memory."""
        if self._feedback_memory is None:
            return {}
        if hasattr(self._feedback_memory, "policy_criteria"):
            return self._feedback_memory.policy_criteria()
        criteria: Dict[str, Any] = {}
        for lesson in getattr(self._feedback_memory, "lessons", []):
            criteria[lesson.lesson_id] = {
                "summary": getattr(lesson, "summary", ""),
                "scope": getattr(lesson, "scope", ""),
                "validation_checks": list(getattr(lesson, "validation_checks", [])),
                "expected_outputs": list(getattr(lesson, "expected_outputs", [])),
                "checks": list(getattr(lesson, "checks", [])),
            }
        return criteria

    def __init__(self, llm_client: Optional[Any] = None, feedback_memory: Optional[Any] = None, **kwargs):
        super().__init__(role=AgentRole.SPATIAL_REVIEWER, llm_client=llm_client, **kwargs)
        self._feedback_memory = feedback_memory or get_default_feedback_memory()
        self._review_corrections: list[Dict[str, Any]] = []
        policy = _load_reviewer_policy()
        self.required_policy_thresholds = dict(policy.get("required_policy_thresholds") or {})
        self.urban_validity_threshold = float(policy.get("urban_validity_threshold", 0.0))
        self.minor_issue_penalty = float(policy.get("minor_issue_penalty", 0.0))
        self.major_issue_penalty = float(policy.get("major_issue_penalty", self.minor_issue_penalty))
        self.relevant_feedback_lesson_ids = frozenset(policy.get("relevant_feedback_lesson_ids") or [])

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
        self._review_corrections = []

        policy_scores = self._evaluate_required_policies(results)
        artifact_scores = self._evaluate_optional_artifact_policies(results)
        warnings = self._collect_policy_issues(policy_scores, artifact_scores)

        if self.llm_client is not None and not warnings:
            llm_issues = await self._llm_review(results)
            warnings.extend(llm_issues)

        required_scores = {
            name: data["score"]
            for name, data in policy_scores.items()
            if data.get("applicable", True)
        }
        hard_failures = [
            name
            for name, threshold in self.required_policy_thresholds.items()
            if policy_scores.get(name, {}).get("applicable", True)
            and required_scores.get(name, 0.0) < threshold
        ]
        urban_validity_score = (
            sum(required_scores.values()) / len(required_scores)
            if required_scores else 1.0
        )
        alignment_score = required_scores.get("spatial_structural_review", 0.0)
        issues = [
            issue
            for name in hard_failures
            for issue in policy_scores.get(name, {}).get("issues", [])
        ]
        passed = not hard_failures and urban_validity_score >= self.urban_validity_threshold
        correction_memory = _dedupe_corrections(self._review_corrections)
        rerun_queue = [item for item in correction_memory if item.get("rerun_required")]

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
                "warnings": warnings,
                "policy_scores": policy_scores,
                "artifact_scores": artifact_scores,
                "hard_failures": hard_failures,
                "correction_memory": correction_memory,
                "rerun_queue": rerun_queue,
                "recommendation": "accept" if passed and not warnings else ("accept_with_warnings" if passed else "revise"),
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
        applicable = False

        for st_id, st_data, result in self._iter_subtask_results(results):
            if st_data.get("status") == "failed":
                issues.append(f"{st_id}: subtask failed before spatial review")
                score -= 0.2
                applicable = True

            evidence = result.get("evidence_manifest", {})
            spatial = evidence.get("spatial", {}) if isinstance(evidence, dict) else {}
            has_data_reference = self._has_data_reference(result)
            has_spatial_signal = bool(spatial or has_data_reference or result.get("bounds") or result.get("geometry") or result.get("alignment_diagnostics") or result.get("layer_stack"))
            if not has_spatial_signal:
                continue
            applicable = True

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
            corrections = result.get("correction_audit", [])
            human_alignment = result.get("human_alignment", {})

            if not spatial.get("bbox") and not has_data_reference:
                issues.append(f"{st_id}: missing bbox in evidence manifest")
                score -= 0.1
            if not spatial.get("crs") and not has_data_reference:
                issues.append(f"{st_id}: missing CRS in evidence manifest")
                score -= 0.1
            if not alignment.get("preferred_scale") and not has_data_reference:
                issues.append(f"{st_id}: missing preferred scale diagnostics")
                score -= 0.1
            if alignment.get("maup_like_risk") == "high" and not corrections and not human_alignment:
                issues.append(f"{st_id}: high MAUP-like risk without correction record")
                score -= self.minor_issue_penalty

            score = self._apply_gis_alignment_review(st_id, alignment, issues, score, result=result)

        return {
            "score": max(0.0, min(1.0, score)),
            "issues": issues,
            "applicable": applicable,
        }

    def _temporal_consistency_review(self, results: Dict) -> Dict[str, Any]:
        issues = []
        score = 1.0
        applicable = False

        for st_id, _, result in self._iter_subtask_results(results):
            evidence = result.get("evidence_manifest", {})
            temporal = evidence.get("temporal", {}) if isinstance(evidence, dict) else {}

            if not temporal or not any(temporal.values()):
                continue
            applicable = True

            if not temporal.get("time_window"):
                issues.append(f"{st_id}: missing time_window")
                score -= 0.05
            if not temporal.get("granularity"):
                issues.append(f"{st_id}: missing temporal granularity")
                score -= 0.05
            if not temporal.get("freshness"):
                issues.append(f"{st_id}: missing freshness declaration")
                score -= 0.05
            if temporal.get("forecast_horizon") and not temporal.get("time_window"):
                issues.append(f"{st_id}: forecast horizon provided without observation window")
                score -= self.minor_issue_penalty

        return {
            "score": max(0.0, min(1.0, score)),
            "issues": issues,
            "applicable": applicable,
        }

    def _population_and_stakeholder_review(self, results: Dict) -> Dict[str, Any]:
        issues = []
        score = 1.0
        applicable = False

        for st_id, _, result in self._iter_subtask_results(results):
            evidence = result.get("evidence_manifest", {})
            population = evidence.get("population", {}) if isinstance(evidence, dict) else {}
            human_alignment = result.get("human_alignment", {})
            stakeholder_feedback = human_alignment.get("stakeholder_feedback", [])

            if not population or not any(population.values()):
                if evidence:
                    applicable = True
                    issues.append(f"{st_id}: missing population evidence block")
                    score -= 0.55
                continue
            applicable = True

            target_group = population.get("target_group")
            observed_group = population.get("observed_group")
            affected_group = population.get("affected_group")
            stakeholder_source = population.get("stakeholder_source")
            sampling_bias = population.get("sampling_bias")

            if not target_group:
                issues.append(f"{st_id}: missing target_group")
                score -= self.minor_issue_penalty
            if not observed_group:
                issues.append(f"{st_id}: missing observed_group")
                score -= self.minor_issue_penalty
            if not affected_group:
                issues.append(f"{st_id}: missing affected_group")
                score -= 0.10
            if target_group and observed_group and target_group != observed_group and not sampling_bias:
                issues.append(f"{st_id}: target_group and observed_group differ without sampling_bias note")
                score -= self.minor_issue_penalty
            if not stakeholder_source and not stakeholder_feedback:
                issues.append(f"{st_id}: no stakeholder source or review feedback attached")
                score -= 0.10

        return {
            "score": max(0.0, min(1.0, score)),
            "issues": issues,
            "applicable": applicable,
        }

    def _evidence_and_governance_review(self, results: Dict) -> Dict[str, Any]:
        issues = []
        score = 1.0
        applicable = False

        for st_id, _, result in self._iter_subtask_results(results):
            evidence = result.get("evidence_manifest", {})
            governance = evidence.get("governance", {}) if isinstance(evidence, dict) else {}
            tags = evidence.get("tags", []) if isinstance(evidence, dict) else []
            has_data_reference = self._has_data_reference(result)

            if not governance and not has_data_reference:
                if evidence:
                    applicable = True
                    issues.append(f"{st_id}: missing governance evidence block")
                    score -= 0.55
                continue
            applicable = True

            for field in ("provenance", "license", "collection_method", "uncertainty"):
                if not governance.get(field):
                    issues.append(f"{st_id}: missing governance field {field}")
                    score -= 0.05

            missing_layers = governance.get("missing_layers", [])
            if missing_layers:
                issues.append(f"{st_id}: missing evidence layers {missing_layers}")
                score -= 0.10
            if not tags:
                issues.append(f"{st_id}: evidence manifest has no tags")
                score -= 0.05

            grounding_policy = result.get("grounding_policy", {})
            dataset_cards = result.get("dataset_cards", [])
            if isinstance(grounding_policy, dict) and grounding_policy:
                if grounding_policy.get("dataset_cards_required", False) and not dataset_cards:
                    issues.append(f"{st_id}: grounding policy requires dataset cards but none are attached")
                    score -= self.minor_issue_penalty
                if grounding_policy.get("known_limits_required", False):
                    incomplete_cards = [
                        card.get("resource_id") or card.get("name")
                        for card in dataset_cards
                        if isinstance(card, dict) and not card.get("known_limits")
                    ]
                    if incomplete_cards:
                        issues.append(f"{st_id}: dataset cards lack known_limits {incomplete_cards[:5]}")
                        score -= 0.10

            indicator_matrix = result.get("indicator_computability_matrix", [])
            if isinstance(indicator_matrix, list) and indicator_matrix:
                applicable = True
                require_disclosure = not isinstance(grounding_policy, dict) or grounding_policy.get("require_missing_evidence_disclosure", True)
                if require_disclosure:
                    for row in indicator_matrix:
                        if not isinstance(row, dict):
                            continue
                        status = row.get("status")
                        if status not in {"missing", "proxy"}:
                            continue
                        indicator = row.get("indicator") or row.get("name")
                        if indicator and not self._has_indicator_disclosure(result, str(indicator)):
                            issues.append(f"{st_id}: {indicator} is {status} but not disclosed in limitations")
                            score -= 0.05

        return {
            "score": max(0.0, min(1.0, score)),
            "issues": issues,
            "applicable": applicable,
        }

    def _cartography_review(self, results: Dict) -> Dict[str, Any]:
        issues = []
        score = 1.0
        applicable = False

        for st_id, _, result in self._iter_subtask_results(results):
            outputs = result.get("outputs", [])
            has_formal_artifact = any(
                name in outputs
                for name in (
                    "gis_layer_package",
                    "map_png",
                    "map_pdf",
                    "metric_csv",
                    "chart_png",
                    "streetview_grid_png",
                    "svg_overlay",
                    "geojson",
                    "map",
                )
            ) or bool(result.get("layer_stack"))
            if not has_formal_artifact:
                continue
            applicable = True
            if not result.get("legend") and not result.get("symbology"):
                issues.append(f"{st_id}: cartographic artifact lacks legend or symbology metadata")
                score -= 0.20
            if result.get("artifact_role") == "formal_gis" and not result.get("layer_stack"):
                issues.append(f"{st_id}: formal GIS artifact lacks reviewable layer stack")
                score -= 0.10
            if result.get("artifact_role") == "formal_gis" and not result.get("alignment_diagnostics"):
                issues.append(f"{st_id}: formal GIS artifact lacks AOI/layer alignment diagnostics")
                score -= 0.20
            elif result.get("alignment_diagnostics"):
                # Alignment diagnostics are evaluated by spatial_structural_review to avoid duplicate corrections.
                pass
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
                score -= self.minor_issue_penalty
            if "because" not in report_lower and "evidence" not in report_lower and "based on" not in report_lower:
                issues.append(f"{st_id}: report lacks explicit evidence linkage")
                score -= self.minor_issue_penalty

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
        seen = set()
        for payload in list(policy_scores.values()) + list(artifact_scores.values()):
            for issue in payload.get("issues", []):
                if issue in seen:
                    continue
                seen.add(issue)
                issues.append(issue)
        return issues

    @staticmethod
    def _has_data_reference(result: Dict[str, Any]) -> bool:
        if not isinstance(result, dict):
            return False
        for key in ("data_sources", "inferred_data_sources", "declared_paths", "accessible_paths"):
            value = result.get(key)
            if isinstance(value, dict) and value:
                return True
            if isinstance(value, list) and value:
                return True
        return bool(result.get("image_path") or result.get("geojson") or result.get("bounds"))

    @staticmethod
    def _has_indicator_disclosure(result: Dict[str, Any], indicator: str) -> bool:
        needle = indicator.lower()
        values = []
        for key in ("limitations", "answer", "analysis", "report"):
            value = result.get(key)
            if isinstance(value, list):
                values.extend(str(item) for item in value)
            elif isinstance(value, str):
                values.append(value)
        return any(needle in value.lower() for value in values)

    def _apply_gis_alignment_review(self, st_id: str, alignment: Dict[str, Any], issues: list[str], score: float, result: Optional[Dict[str, Any]] = None) -> float:
        if not isinstance(alignment, dict) or not alignment:
            return score
        result = result or {}
        status = alignment.get("status")
        if status in {"failed", "invalid_boundary", "no_boundary"}:
            issues.append(f"{st_id}: GIS alignment status is {status}")
            score -= self.major_issue_penalty

        context = alignment.get("context_buffer", {}) if isinstance(alignment.get("context_buffer"), dict) else {}
        if context:
            context_status = context.get("status")
            if context_status not in {"generated", "not_applicable"}:
                issues.append(f"{st_id}: AOI context buffer status is {context_status}")
                score -= 0.10

        score = self._apply_memory_policy_checks(st_id, alignment, result, issues, score)

        for issue in alignment.get("issues", []) or []:
            issues.append(f"{st_id}: {issue}")
            score -= 0.03
        layers = alignment.get("layers", {}) if isinstance(alignment.get("layers"), dict) else {}
        for layer_name, layer_diag in layers.items():
            if not isinstance(layer_diag, dict) or layer_name == "boundary":
                continue
            source_count = int(layer_diag.get("source_feature_count") or 0)
            exported_count = int(layer_diag.get("exported_feature_count") or 0)
            if source_count > 0 and exported_count == 0:
                issues.append(f"{st_id}: {layer_name} has source features but none intersect the AOI")
                score -= self.major_issue_penalty
        return score

    def _apply_memory_policy_checks(self, st_id: str, alignment: Dict[str, Any], result: Dict[str, Any], issues: list[str], score: float) -> float:
        criteria = self._policy_criteria()
        outputs = result.get("outputs", []) if isinstance(result.get("outputs", []), list) else []
        for policy_id, policy in criteria.items():
            for check in policy.get("checks", []) or []:
                if not isinstance(check, dict):
                    continue
                required_output = check.get("when_output_contains")
                if required_output and required_output not in outputs:
                    continue
                target = str(check.get("target") or "")
                if target == "context_buffer":
                    value = _get_path(alignment, check.get("metric_path", ""))
                    if not _policy_check_passes(value, check):
                        score = self._record_policy_issue(st_id, policy_id, check, issues, score, value=value)
                elif target == "metric_spatialization":
                    value = _get_path(alignment, check.get("metric_path", ""))
                    if not _policy_check_passes(value, check):
                        score = self._record_policy_issue(st_id, policy_id, check, issues, score, value=value)
                elif target == "layers.*":
                    layers = alignment.get("layers", {}) if isinstance(alignment.get("layers"), dict) else {}
                    for layer_name, layer_diag in layers.items():
                        if not isinstance(layer_diag, dict) or layer_name == "boundary":
                            continue
                        layer_roles = check.get("layer_roles")
                        if layer_roles and str(layer_name) not in set(str(item) for item in layer_roles):
                            continue
                        unless_path = check.get("unless_path")
                        if unless_path and _get_path(layer_diag, str(unless_path)):
                            continue
                        value = _get_path(layer_diag, check.get("metric_path", ""))
                        if value is None:
                            continue
                        if not _policy_check_passes(value, check):
                            score = self._record_policy_issue(st_id, policy_id, check, issues, score, value=value, layer_name=str(layer_name), layer_diag=layer_diag)
        return score

    def _record_policy_issue(
        self,
        st_id: str,
        policy_id: str,
        check: Dict[str, Any],
        issues: list[str],
        score: float,
        *,
        value: Any = None,
        layer_name: str | None = None,
        layer_diag: Optional[Dict[str, Any]] = None,
    ) -> float:
        message = _format_policy_message(check.get("message") or check.get("check_id") or "policy check failed", value=value, threshold=check.get("value"), layer=layer_name)
        issues.append(f"{st_id}: {message} (policy_memory:{policy_id})")
        repair_action = check.get("repair_action")
        record = {
            "source": "ReviewHub",
            "subtask_id": st_id,
            "policy_id": policy_id,
            "check_id": check.get("check_id"),
            "severity": check.get("severity", "warning"),
            "message": message,
            "observed_value": value,
            "threshold": check.get("value"),
            "affected_layer": layer_name,
            "repair_action": repair_action,
            "rerun_required": bool(repair_action),
        }
        if layer_diag:
            record["layer_diagnostics"] = {
                key: layer_diag.get(key)
                for key in (
                    "source_feature_count",
                    "exported_feature_count",
                    "source_to_context_width_ratio",
                    "source_to_context_height_ratio",
                    "source_extent_width_m",
                    "source_extent_height_m",
                    "source_extent_basis",
                )
                if key in layer_diag
            }
        self._review_corrections.append(record)
        return score - float(check.get("score_penalty") or 0.05)

    async def _llm_review(self, results: Dict) -> list[str]:
        """LLM 杈呭姪瀹℃煡"""
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



def _dedupe_corrections(corrections: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    deduped: list[Dict[str, Any]] = []
    seen = set()
    for item in corrections:
        key = (
            item.get("subtask_id"),
            item.get("policy_id"),
            item.get("check_id"),
            item.get("affected_layer"),
            item.get("observed_value"),
            item.get("repair_action"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _get_path(payload: Dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in str(path or "").split("."):
        if not part:
            continue
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _policy_check_passes(value: Any, check: Dict[str, Any]) -> bool:
    op = str(check.get("operator") or "==")
    threshold = check.get("value")
    try:
        if op == "is_true":
            return bool(value) is True
        if op == "is_false":
            return bool(value) is False
        if op == "in":
            return value in (threshold or [])
        if op == "not_in":
            return value not in (threshold or [])
        if op in {">=", ">", "<=", "<"}:
            left = float(value)
            right = float(threshold)
            if op == ">=":
                return left >= right
            if op == ">":
                return left > right
            if op == "<=":
                return left <= right
            return left < right
        if op in {"==", "="}:
            return value == threshold
        if op == "!=":
            return value != threshold
    except Exception:
        return False
    return False


def _format_policy_message(template: str, *, value: Any = None, threshold: Any = None, layer: str | None = None) -> str:
    try:
        value_pct = f"{float(value):.0%}" if isinstance(value, (int, float)) else str(value)
    except Exception:
        value_pct = str(value)
    try:
        value_text = f"{float(value):.3g}" if isinstance(value, (int, float)) else str(value)
    except Exception:
        value_text = str(value)
    try:
        threshold_text = f"{float(threshold):.3g}" if isinstance(threshold, (int, float)) else str(threshold)
    except Exception:
        threshold_text = str(threshold)
    return str(template).format(
        value=value_text,
        value_pct=value_pct,
        threshold=threshold_text,
        layer=layer or "layer",
    )

def _diagnose_buffer_source_coverage(context: Dict[str, Any], layers: Dict[str, Any]) -> list[str]:
    """Compare source data extent with context buffer to detect pre-clipped source data."""
    issues: list[str] = []
    if not context or not layers:
        return issues
    ctx_width = float(context.get("context_width_m") or 0)
    ctx_height = float(context.get("context_height_m") or 0)
    if ctx_width <= 0 or ctx_height <= 0:
        return issues
    minimum_coverage = float(context.get("minimum_source_context_coverage") or 0)
    if minimum_coverage <= 0:
        return issues
    for layer_name, layer_diag in layers.items():
        if not isinstance(layer_diag, dict) or layer_name == "boundary":
            continue
        source_bounds = layer_diag.get("source_bounds")
        if not source_bounds or len(source_bounds) != 4:
            continue
        source_width = max(0.0, float(source_bounds[2] or 0) - float(source_bounds[0] or 0))
        source_height = max(0.0, float(source_bounds[3] or 0) - float(source_bounds[1] or 0))
        width_coverage = source_width / ctx_width if source_width > 0 and ctx_width > 0 else None
        height_coverage = source_height / ctx_height if source_height > 0 and ctx_height > 0 else None
        if width_coverage is not None and width_coverage < minimum_coverage:
            issues.append(
                f"{layer_name}: source data extent covers only {width_coverage:.0%} of context buffer width "
                f"(source span ~{source_width:.0f}m vs buffer {ctx_width:.0f}m); "
                "source extent is below the policy coverage threshold"
            )
        if height_coverage is not None and height_coverage < minimum_coverage:
            issues.append(
                f"{layer_name}: source data extent covers only {height_coverage:.0%} of context buffer height "
                f"(source span ~{source_height:.0f}m vs buffer {ctx_height:.0f}m); "
                "source extent is below the policy coverage threshold"
            )
    return issues


class HumanCheckpointAgent(BaseAgent):
    """
    浜烘満鍗忎綔 Agent 鈥?6涓喅绛栨鏌ョ偣

    DP-1: Task interpretation & scoping
    DP-2: Data source validation
    DP-3: Spatial representation review
    DP-4: Intervention proposal selection
    DP-5: Parameter tuning
    DP-6: Result interpretation & narrative

    涓夌浜や簰妯″紡锛?
    - guided:    姣忎釜 DP 閮芥殏鍋滅瓑寰呬汉宸ョ‘璁?
    - supervisory: 鑷姩鎵ц + 浜嬪悗妫€鏌ョ偣
    - autonomous:  瀹屽叏鑷姩锛堜笉鏆傚仠锛?
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
        """鏍规嵁浜や簰妯″紡澶勭悊妫€鏌ョ偣"""
        if self.interaction_mode == "autonomous":
            return {"action": "approve", "reason": "autonomous mode"}

        if self.interaction_mode == "guided" and self.human_callback:
            return await self._ask_human(checkpoint_id, data)

        if self.interaction_mode == "supervisory":
            # 浜嬪悗璁板綍锛屼笉闃诲
            logger.info(f"Supervisory checkpoint {checkpoint_id}: auto-approved, logged for review")
            return {"action": "approve", "reason": "supervisory auto-approve"}

        return {"action": "approve", "reason": "no callback configured"}

    async def _ask_human(self, checkpoint_id: str, data: Dict) -> Dict:
        """璇锋眰浜哄伐杈撳叆"""
        if self.human_callback is None:
            return {"action": "approve", "reason": "no callback"}

        import asyncio

        if asyncio.iscoroutinefunction(self.human_callback):
            return await self.human_callback(checkpoint_id, data)
        return self.human_callback(checkpoint_id, data)


