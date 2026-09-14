"""Review contracts for auditable multi-scale urban analysis.

The module distinguishes the spatial support of observations from model,
validation, and diagnostic scales. It does not select an "optimal" scale.
Instead, it checks whether scale branches are comparable enough for a human
researcher to interpret their differences and returns an explicit claim gate.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable


_REQUIRED_BRANCH_FIELDS = (
    "branch_id",
    "analysis_unit",
    "outcome_contract",
    "feature_names",
    "validation_design",
    "model_protocol",
    "empty_grid_policy",
)
_OUTCOME_FIELDS = (
    "definition",
    "temporal_scope",
    "population_scope",
    "privacy_rule",
    "cohort_scheme",
)
_ANALYSIS_UNIT_FIELDS = ("geometry", "origin_id", "aoi_id")
_VALIDATION_FIELDS = ("partition_id", "fold_count", "macro_region_artifact")
_MODEL_FIELDS = ("candidate_families", "tuning_protocol_id", "metric_set")
_MAPPING_FIELDS = (
    "analysis_unit",
    "outcome_contract",
    "validation_design",
    "model_protocol",
    "empty_grid_policy",
)


def _as_sorted_strings(values: Any) -> list[str]:
    if not isinstance(values, (list, tuple, set)):
        return []
    return sorted(str(value) for value in values)


def _normalized_value(field: str, value: Any) -> Any:
    if field in {"candidate_families", "metric_set"}:
        return _as_sorted_strings(value)
    if isinstance(value, str):
        return value.strip()
    return value


def _as_mapping(value: Any) -> dict[str, Any]:
    """Return a safe mapping for schema-tolerant audits.

    LLM tool calls occasionally serialize a nested contract as a short string.
    The audit must report that schema defect instead of crashing while trying
    to call ``.get`` on it.
    """

    return dict(value) if isinstance(value, dict) else {}


def _distinct(branches: list[dict[str, Any]], container: str, field: str) -> list[Any]:
    values: list[Any] = []
    for branch in branches:
        payload = _as_mapping(branch.get(container))
        value = _normalized_value(field, payload.get(field))
        if value not in values:
            values.append(value)
    return values


def _issue(
    code: str,
    message: str,
    *,
    consequence: str,
    action: str,
    severity: str = "qualify",
) -> dict[str, str]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "consequence": consequence,
        "action": action,
    }


def audit_scale_branches(
    branches: Iterable[dict[str, Any]],
    diagnostics: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Audit cross-scale comparability and return a human-facing claim gate.

    ``pass`` admits a bounded statement about the scale component of MAUP.
    ``qualify`` retains a resolution-sensitivity comparison while recording
    co-varying data regimes. ``block`` means that the contract is incomplete.
    """

    items = [dict(branch) for branch in branches if isinstance(branch, dict)]
    diagnostic_items = [dict(item) for item in (diagnostics or []) if isinstance(item, dict)]
    issues: list[dict[str, str]] = []

    if len(items) < 2:
        issues.append(
            _issue(
                "insufficient_scale_branches",
                "At least two declared scale branches are required.",
                consequence="No cross-scale comparison can be audited.",
                action="Declare two or more research-object branches before model execution.",
                severity="block",
            )
        )

    for branch in items:
        missing = [field for field in _REQUIRED_BRANCH_FIELDS if not branch.get(field)]
        if missing:
            issues.append(
                _issue(
                    "incomplete_scale_contract",
                    f"{branch.get('branch_id', '<unnamed>')} is missing: {', '.join(missing)}.",
                    consequence="The branch cannot be compared or reproduced reliably.",
                    action="Complete the branch contract before accepting cross-scale evidence.",
                    severity="block",
                )
            )
        invalid_containers = [
            field
            for field in _MAPPING_FIELDS
            if branch.get(field) is not None and not isinstance(branch.get(field), dict)
        ]
        if invalid_containers:
            issues.append(
                _issue(
                    "invalid_scale_contract_schema",
                    f"{branch.get('branch_id', '<unnamed>')} has non-object fields: "
                    f"{', '.join(invalid_containers)}.",
                    consequence="Nested scale-contract fields cannot be audited reliably.",
                    action="Resubmit these fields as JSON objects that follow the tool schema.",
                    severity="block",
                )
            )

    if items:
        sizes = [_as_mapping(branch.get("analysis_unit")).get("size_m") for branch in items]
        if len({size for size in sizes if size is not None}) < 2:
            issues.append(
                _issue(
                    "analysis_scale_not_varied",
                    "The declared branches do not expose at least two analysis-unit sizes.",
                    consequence="The comparison does not test resolution sensitivity.",
                    action="Vary analysis-unit size while holding the comparison contract fixed.",
                    severity="block",
                )
            )

        for field in _ANALYSIS_UNIT_FIELDS:
            values = _distinct(items, "analysis_unit", field)
            if len(values) > 1:
                issues.append(
                    _issue(
                        f"analysis_unit_{field}_differs",
                        f"Analysis-unit {field} differs across branches: {values}.",
                        consequence="Scale and zoning/boundary effects are confounded.",
                        action="Use the same AOI, grid geometry, and origin, or report a combined scale-and-zoning sensitivity analysis.",
                    )
                )

        for field in _OUTCOME_FIELDS:
            values = _distinct(items, "outcome_contract", field)
            if len(values) > 1:
                consequence = (
                    "Released totals may change with both resolution and privacy/cohort cellization."
                    if field in {"privacy_rule", "cohort_scheme"}
                    else "The outcome or represented population changes together with resolution."
                )
                issues.append(
                    _issue(
                        f"outcome_{field}_differs",
                        f"Outcome-contract {field} differs across branches: {values}.",
                        consequence=consequence,
                        action="Reaggregate from the same pre-suppression records when authorized; otherwise retain a qualified data-regime comparison.",
                    )
                )

        feature_sets = [set(_as_sorted_strings(branch.get("feature_names"))) for branch in items]
        if feature_sets and any(values != feature_sets[0] for values in feature_sets[1:]):
            union = sorted(set().union(*feature_sets))
            common = sorted(set.intersection(*feature_sets)) if feature_sets else []
            issues.append(
                _issue(
                    "feature_set_differs",
                    f"Predictor sets differ across scales; common={common}, union={union}.",
                    consequence="Model-score differences cannot be attributed to spatial support alone.",
                    action="Use the common predictor intersection as the primary comparison and move extra variables to a matched sensitivity branch.",
                )
            )

        for field in _VALIDATION_FIELDS:
            values = _distinct(items, "validation_design", field)
            if len(values) > 1:
                issues.append(
                    _issue(
                        f"validation_{field}_differs",
                        f"Validation {field} differs across branches: {values}.",
                        consequence="Performance differences may reflect different held-out geographies rather than analysis scale.",
                        action="Assign every scale to the same prespecified macro-regions and persist the fold artifact.",
                    )
                )

        for field in _MODEL_FIELDS:
            values = _distinct(items, "model_protocol", field)
            if len(values) > 1:
                issues.append(
                    _issue(
                        f"model_protocol_{field}_differs",
                        f"Model protocol {field} differs across branches: {values}.",
                        consequence="Scale and model-selection effects are mixed.",
                        action="Use the same candidates, tuning policy, and metrics across scale branches.",
                    )
                )

        for branch in items:
            policy = _as_mapping(branch.get("empty_grid_policy"))
            required_statuses = {
                "outside_aoi",
                "true_zero",
                "privacy_suppressed_or_unreleased",
                "covariate_missing",
                "model_ready",
            }
            absent = sorted(required_statuses - set(policy))
            if absent:
                issues.append(
                    _issue(
                        "empty_grid_policy_incomplete",
                        f"{branch.get('branch_id')} does not distinguish: {', '.join(absent)}.",
                        consequence="Excluded cells can be silently recoded as zero or dropped without an attrition record.",
                        action="Create an attrition ledger and never recode privacy-suppressed cells as observed zeros.",
                        severity="block",
                    )
                )

    if diagnostic_items:
        for diagnostic in diagnostic_items:
            residual_source = str(diagnostic.get("residual_source") or "").lower()
            if "out_of_fold" not in residual_source and "oof" not in residual_source:
                issues.append(
                    _issue(
                        "moran_not_oof",
                        "Residual spatial autocorrelation was not declared on out-of-fold residuals.",
                        consequence="The diagnostic may describe training fit rather than held-out error geography.",
                        action="Compute Moran's I on persisted out-of-fold residuals for each validation repeat.",
                    )
                )
            if str(diagnostic.get("decision_role") or "").lower() in {
                "select_scale",
                "select_model",
                "select_gwr",
            }:
                issues.append(
                    _issue(
                        "moran_used_as_selector",
                        "Moran's I is assigned a direct model- or scale-selection role.",
                        consequence="Residual clustering alone cannot identify the correct scale, GWR, or GWRF.",
                        action="Use Moran's I to qualify unexplained spatial structure and trigger alternatives, not as a single-score selector.",
                        severity="block",
                    )
                )

        weight_kinds = {str(item.get("weight_kind") or "") for item in diagnostic_items}
        if weight_kinds == {"knn"} and len(diagnostic_items) > 1:
            issues.append(
                _issue(
                    "diagnostic_scale_not_equivalent",
                    "The same k-nearest-neighbor count represents different physical neighborhoods at different grid resolutions.",
                    consequence="Moran's I magnitudes should not be ranked directly across scales.",
                    action="Report scale-specific kNN diagnostics and add a common physical-distance diagnostic before cross-scale interpretation.",
                )
            )

    severity_counts = Counter(issue["severity"] for issue in issues)
    if severity_counts["block"]:
        status = "block"
    elif issues:
        status = "qualify"
    else:
        status = "pass"

    pure_scale_effect = status == "pass"
    if pure_scale_effect:
        label = "MAUP scale-component comparison under a harmonized protocol"
        maximum_claim = (
            "Observed differences are attributable to aggregation resolution within the declared "
            "AOI, grid origin, outcome, features, validation geography, and model protocol."
        )
    elif status == "qualify":
        label = "resolution-sensitivity comparison under partially different data regimes"
        maximum_claim = (
            "Results may be described as scale-conditioned differences under the recorded data "
            "regimes, not as a pure MAUP scale effect or proof of an optimal spatial scale."
        )
    else:
        label = "cross-scale comparison blocked pending contract repair"
        maximum_claim = "No cross-scale scientific claim is admitted until blocking contract gaps are repaired."

    return {
        "status": status,
        "branch_count": len(items),
        "pure_maup_scale_effect_admissible": pure_scale_effect,
        "recommended_label": label,
        "maximum_admissible_claim": maximum_claim,
        "issues": issues,
        "human_checkpoint": {
            "required": True,
            "question": (
                "Should the analyst retain a primary scale, report all branches as sensitivity "
                "evidence, or defer scale choice because the trade-offs remain unresolved?"
            ),
            "forbidden_shortcut": "Do not select scale by the largest R2 or smallest Moran's I alone.",
        },
        "scale_taxonomy": {
            "analysis_unit_scale": "spatial support used to construct observations",
            "model_process_scale": "bandwidth or neighborhood used to estimate local relationships",
            "validation_scale": "size and placement of geographically held-out regions",
            "diagnostic_scale": "spatial weights used to test residual structure",
        },
    }


def build_scale_evidence_cards(
    branches: Iterable[dict[str, Any]],
    metrics: Iterable[dict[str, Any]],
    diagnostics: Iterable[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Create compact evidence cards without collapsing a multi-metric trade-off."""

    metric_by_branch = {
        str(item.get("branch_id")): dict(item)
        for item in metrics
        if isinstance(item, dict) and item.get("branch_id")
    }
    diagnostic_by_branch: dict[str, list[dict[str, Any]]] = {}
    for item in diagnostics or []:
        if not isinstance(item, dict):
            continue
        diagnostic_by_branch.setdefault(str(item.get("branch_id")), []).append(dict(item))

    cards: list[dict[str, Any]] = []
    for branch in branches:
        if not isinstance(branch, dict):
            continue
        branch_id = str(branch.get("branch_id") or "")
        cards.append(
            {
                "branch_id": branch_id,
                "analysis_unit": branch.get("analysis_unit"),
                "outcome_scope": branch.get("outcome_contract"),
                "feature_count": len(branch.get("feature_names") or []),
                "feature_names": list(branch.get("feature_names") or []),
                "validation_design": branch.get("validation_design"),
                "empty_grid_policy": branch.get("empty_grid_policy"),
                "metrics": metric_by_branch.get(branch_id, {}),
                "spatial_diagnostics": diagnostic_by_branch.get(branch_id, []),
                "decision": "human_review_required",
            }
        )
    return cards
