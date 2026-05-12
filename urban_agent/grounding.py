"""Input-grounding governance utilities for UrbanAgent.

This module turns discovered local resources and task-provided schemas into
reviewable runtime artifacts. It deliberately keeps task-specific indicators
out of the tools: indicators arrive through the task payload or experiment
configuration, then UrbanAgent evaluates whether the available resources can
support direct, proxy, or missing claims.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


from .memory_store import FileMemoryStore


def _load_grounding_knowledge() -> tuple[Dict[str, Dict[str, Any]], Dict[str, set[str]]]:
    """Load dataset role specs and aliases from knowledge memory."""
    role_specs: Dict[str, Dict[str, Any]] = {}
    data_aliases: Dict[str, set[str]] = {}
    try:
        store = FileMemoryStore.default()
        for record in store.records("knowledge"):
            payload = record.to_dict()
            if isinstance(payload.get("role_specs"), dict):
                role_specs.update({str(key): dict(value) for key, value in payload["role_specs"].items() if isinstance(value, dict)})
            if isinstance(payload.get("data_aliases"), dict):
                for key, value in payload["data_aliases"].items():
                    if isinstance(value, (list, tuple, set)):
                        data_aliases[str(key)] = {str(item) for item in value}
    except Exception:
        role_specs = {}
        data_aliases = {}
    return role_specs, data_aliases


ROLE_SPECS, DATA_ALIASES = _load_grounding_knowledge()

def build_input_grounding_package(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Build all input-grounding artifacts from a task payload."""
    task_data = arguments.get("task_data") or arguments.get("input_data") or arguments
    path_context = arguments.get("path_context") or {}
    dataset_cards = build_dataset_cards(task_data, path_context)
    grounding_policy = build_grounding_policy(task_data, dataset_cards)
    computability = build_indicator_computability_matrix(task_data, dataset_cards, path_context)
    workflow_event = build_workflow_memory_event(task_data, computability, dataset_cards)
    artifacts = write_grounding_artifacts(
        task_data,
        dataset_cards=dataset_cards,
        grounding_policy=grounding_policy,
        indicator_computability=computability,
        workflow_event=workflow_event,
    )
    return {
        "status": "grounding_complete",
        "dataset_cards": dataset_cards,
        "grounding_policy": grounding_policy,
        "indicator_computability_matrix": computability,
        "workflow_memory_event": workflow_event,
        "artifacts": artifacts,
    }


def build_dataset_cards(task_data: Dict[str, Any], path_context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Create dataset cards from task-declared resources and discovered paths."""
    path_context = path_context or {}
    cards: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for raw_card in _as_list(task_data.get("dataset_cards")):
        if not isinstance(raw_card, dict):
            continue
        card = dict(raw_card)
        resource_id = str(card.get("resource_id") or card.get("id") or card.get("name") or f"dataset_{len(cards) + 1}")
        card["resource_id"] = resource_id
        if resource_id not in seen:
            cards.append(card)
            seen.add(resource_id)

    authoritative_inputs = task_data.get("authoritative_inputs")
    if isinstance(authoritative_inputs, dict):
        for key, value in authoritative_inputs.items():
            if not value:
                continue
            role = _infer_role_from_key(key, value)
            resource_id = f"authoritative_{_norm(key) or len(cards) + 1}"
            card = _card_from_role(role, str(value), resource_id=resource_id, canonical=True)
            card["authority"] = "task_authoritative_input"
            card["input_key"] = str(key)
            if resource_id not in seen:
                cards.append(card)
                seen.add(resource_id)

    for resource in _as_list(path_context.get("resources")):
        if not isinstance(resource, dict):
            continue
        role = str(resource.get("role") or "")
        path_text = str(resource.get("path") or resource.get("source_path") or "")
        if not role or not path_text:
            continue
        card = _card_from_role(role, path_text, resource=resource)
        resource_id = card["resource_id"]
        if resource_id not in seen:
            cards.append(card)
            seen.add(resource_id)

    paths = path_context.get("paths", {})
    if isinstance(paths, dict):
        for role, path_text in paths.items():
            if not path_text:
                continue
            card = _card_from_role(str(role), str(path_text))
            resource_id = card["resource_id"]
            if resource_id not in seen:
                cards.append(card)
                seen.add(resource_id)

    return cards


def build_grounding_policy(task_data: Dict[str, Any], dataset_cards: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Build a reviewable grounding policy from task options and cards."""
    raw_policy = task_data.get("input_grounding_policy")
    policy = dict(raw_policy) if isinstance(raw_policy, dict) else {}
    policy.setdefault("policy_id", task_data.get("grounding_policy_id") or "urbanagent_input_grounding_policy")
    policy.setdefault("dataset_cards_required", True)
    policy.setdefault("known_limits_required", True)
    policy.setdefault("allow_proxy_indicators", True)
    policy.setdefault("require_missing_evidence_disclosure", True)
    policy.setdefault("literature_grounding", "reserved_interface_only")

    checks = list(_as_list(policy.get("checks")))
    if policy.get("authoritative_aoi_required", True):
        checks.append({
            "check_id": "authoritative_aoi_required",
            "severity": "hard",
            "rule": "AOI selection must use the task-declared authoritative boundary when provided.",
        })
    if policy.get("do_not_use_legacy_aoi"):
        checks.append({
            "check_id": "legacy_aoi_anti_use",
            "severity": "hard",
            "rule": "Deprecated cache AOIs must not silently define the analysis scope.",
        })
    checks.append({
        "check_id": "unsupported_indicator_downgrade",
        "severity": "hard",
        "rule": "Indicators without required evidence must be marked as proxy or missing.",
    })
    checks.append({
        "check_id": "source_limit_disclosure",
        "severity": "warning",
        "rule": "Dataset limits from cards must be carried into analysis limitations.",
    })
    policy["checks"] = _dedupe_checks(checks)
    policy["dataset_card_count"] = len(dataset_cards or [])
    policy["generated_at"] = datetime.now().isoformat(timespec="seconds")
    return policy


def build_indicator_computability_matrix(
    task_data: Dict[str, Any],
    dataset_cards: Optional[List[Dict[str, Any]]] = None,
    path_context: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Evaluate direct/proxy/missing support for task-provided indicators."""
    indicators = (
        task_data.get("indicator_requirements")
        or task_data.get("indicators")
        or task_data.get("computability_schema")
        or []
    )
    if not isinstance(indicators, list):
        return []

    available = available_evidence_tags(dataset_cards or [], path_context or {})
    matrix = []
    for item in indicators:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        required = _split_evidence_terms(row.get("required_data") or row.get("requires"))
        proxy_terms = _split_evidence_terms(
            row.get("available_proxy")
            or row.get("proxy_data")
            or row.get("fallback_data")
            or row.get("proxy")
        )
        required_supported = [_term_supported(term, available) for term in required]
        proxy_supported = [_term_supported(term, available) for term in proxy_terms]

        if required and all(required_supported):
            status = "direct"
            reason = "Required evidence is available."
            supported_terms = required
            missing_terms: list[str] = []
        elif proxy_terms and any(proxy_supported):
            status = "proxy"
            reason = row.get("reason") or "Required evidence is incomplete; supported proxy evidence is available."
            supported_terms = [term for term, ok in zip(proxy_terms, proxy_supported) if ok]
            missing_terms = [term for term, ok in zip(required, required_supported) if not ok]
        else:
            status = "missing"
            reason = row.get("reason") or "Required evidence is not available in the grounded input package."
            supported_terms = []
            missing_terms = [term for term, ok in zip(required, required_supported) if not ok] or required

        if row.get("status") in {"direct", "proxy", "missing"}:
            # Preserve stricter task labels. A task may deliberately mark an
            # indicator as missing even when a weak proxy exists.
            original = str(row["status"])
            if original == "missing" and status == "direct":
                status = "direct"
            elif original == "missing" and status == "proxy":
                status = "proxy"
            elif original == "proxy" and status == "direct":
                status = "direct"
            else:
                status = original if original in {"proxy", "missing"} else status

        row["status"] = status
        row["supported_evidence"] = "; ".join(supported_terms)
        row["missing_evidence"] = "; ".join(missing_terms)
        row["grounding_reason"] = reason
        matrix.append(row)
    return matrix


def available_evidence_tags(dataset_cards: List[Dict[str, Any]], path_context: Dict[str, Any]) -> set[str]:
    """Return normalized tags representing currently grounded evidence."""
    available: set[str] = set()
    for role in (path_context.get("paths") or {}).keys():
        available.add(_norm(role))
        available.update(_aliases_for(role))
    for card in dataset_cards:
        for key in ("resource_id", "name", "role", "source_path", "format"):
            value = card.get(key)
            if value:
                available.add(_norm(value))
                available.update(_aliases_for(str(value)))
        for key in (
            "semantic_tags",
            "data_view_tags",
            "spatio_temporal_tags",
            "preferred_uses",
            "evidence_tags",
            "metric_tags",
            "proxy_metrics",
            "supported_metrics",
            "aliases",
        ):
            for value in _as_list(card.get(key)):
                available.add(_norm(value))
                available.update(_aliases_for(str(value)))
    return {item for item in available if item}


def build_workflow_memory_event(
    task_data: Dict[str, Any],
    indicator_computability: Optional[List[Dict[str, Any]]] = None,
    dataset_cards: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Create a compact memory event that can be retrieved on similar tasks."""
    matrix = indicator_computability or []
    counts = {
        "direct": sum(1 for row in matrix if row.get("status") == "direct"),
        "proxy": sum(1 for row in matrix if row.get("status") == "proxy"),
        "missing": sum(1 for row in matrix if row.get("status") == "missing"),
    }
    return {
        "memory_type": "workflow_memory",
        "event_id": f"workflow_{datetime.now().strftime('%Y%m%dT%H%M%S')}",
        "task_family": task_data.get("task_family") or task_data.get("task_type") or "urban_analysis",
        "case_id": task_data.get("case_id") or task_data.get("id"),
        "site": task_data.get("site") or task_data.get("district") or task_data.get("location"),
        "read_keys": ["dataset_cards", "grounding_policy", "indicator_computability_matrix"],
        "write_keys": ["limitations", "supported_indicators", "missing_evidence"],
        "indicator_status_counts": counts,
        "dataset_card_count": len(dataset_cards or []),
        "lessons": _workflow_lessons(matrix),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }


def write_grounding_artifacts(
    task_data: Dict[str, Any],
    *,
    dataset_cards: Optional[List[Dict[str, Any]]] = None,
    grounding_policy: Optional[Dict[str, Any]] = None,
    indicator_computability: Optional[List[Dict[str, Any]]] = None,
    workflow_event: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    """Write grounding artifacts into task_data['artifact_dir'] when provided."""
    artifact_dir = task_data.get("artifact_dir")
    if not artifact_dir:
        return []
    root = Path(str(artifact_dir))
    root.mkdir(parents=True, exist_ok=True)
    artifacts: List[Dict[str, str]] = []

    if dataset_cards is not None:
        path = root / "urbanagent_dataset_cards.json"
        path.write_text(json.dumps(dataset_cards, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        artifacts.append({"type": "dataset_cards", "path": str(path)})

    if grounding_policy is not None:
        path = root / "urbanagent_grounding_policy.json"
        path.write_text(json.dumps(grounding_policy, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        artifacts.append({"type": "grounding_policy", "path": str(path)})

    if indicator_computability is not None:
        json_path = root / "urbanagent_indicator_computability_matrix.json"
        json_path.write_text(json.dumps(indicator_computability, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        artifacts.append({"type": "indicator_computability_json", "path": str(json_path)})
        csv_path = root / "urbanagent_indicator_computability_matrix.csv"
        _write_csv(csv_path, indicator_computability)
        artifacts.append({"type": "indicator_computability_csv", "path": str(csv_path)})

    if workflow_event is not None:
        path = root / "urbanagent_workflow_memory_event.json"
        path.write_text(json.dumps(workflow_event, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        artifacts.append({"type": "workflow_memory_event", "path": str(path)})

    return artifacts


def _card_from_role(
    role: str,
    path_text: str,
    *,
    resource_id: Optional[str] = None,
    canonical: bool = False,
    resource: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    spec = ROLE_SPECS.get(role, {})
    rid = resource_id or spec.get("resource_id") or f"resource_{_norm(role)}"
    card = {
        "resource_id": rid,
        "name": spec.get("name") or role.replace("_", " ").title(),
        "role": role,
        "canonical": canonical,
        "source_path": path_text,
        "format": (resource or {}).get("format") or _infer_format(path_text),
        "spatio_temporal_tags": ["place"],
        "semantic_tags": list(spec.get("semantic_tags", [role])),
        "data_view_tags": list(spec.get("data_view_tags", [])),
        "preferred_uses": list(spec.get("preferred_uses", [])),
        "known_limits": list(spec.get("known_limits", ["Source limits must be checked before strong claims."])),
        "anti_uses": list(spec.get("anti_uses", [])),
        "quality_checks": ["path_exists_or_declared", "role_classified", "known_limits_disclosed"],
    }
    if resource:
        for key in ("exists", "feature_count", "item_count", "crs", "geometry_types", "license", "collection_method", "uncertainty", "time_window", "freshness"):
            if key in resource:
                card[key] = resource[key]
    return card


def _infer_role_from_key(key: Any, value: Any) -> str:
    text = f"{key} {value}".lower()
    if any(token in text for token in ("aoi", "boundary", "study_area", "extent", "边界", "范围")):
        return "boundary"
    if any(token in text for token in ("streetview", "street_view", "street-level", "street_level", "街景")):
        return "streetview_dir"
    if any(token in text for token in ("road", "street_network", "network", "路网", "道路")):
        return "roads"
    if any(token in text for token in ("building", "footprint", "建筑")):
        return "buildings"
    if any(token in text for token in ("function", "landuse", "poi", "功能", "业态")):
        return "function_root"
    return "declared_resource"


def _workflow_lessons(matrix: List[Dict[str, Any]]) -> List[str]:
    lessons = []
    missing = [row.get("indicator") for row in matrix if row.get("status") == "missing"]
    proxy = [row.get("indicator") for row in matrix if row.get("status") == "proxy"]
    if proxy:
        lessons.append("Reuse proxy-capable workflow steps but disclose proxy status in later reports.")
    if missing:
        lessons.append("Reviewer should block or downgrade unsupported indicators unless new evidence is provided.")
    if not lessons:
        lessons.append("Grounded resources support the declared indicator set.")
    return lessons


def _term_supported(term: str, available: set[str]) -> bool:
    norm = _norm(term)
    if not norm:
        return False
    if norm in available:
        return True
    aliases = _aliases_for(term)
    if aliases & available:
        return True
    return any(alias in available or available_item in alias for alias in aliases for available_item in available)


def _split_evidence_terms(value: Any) -> List[str]:
    terms: List[str] = []
    for item in _as_list(value):
        if item is None:
            continue
        text = str(item)
        for raw in text.replace("；", ";").replace("、", ";").replace(",", ";").replace("/", ";").split(";"):
            raw = raw.strip()
            if raw:
                terms.append(raw)
    return terms


def _aliases_for(value: str) -> set[str]:
    norm = _norm(value)
    aliases = {norm}
    for key, mapped in DATA_ALIASES.items():
        if key in norm or norm in mapped:
            aliases.update({_norm(item) for item in mapped})
    return {item for item in aliases if item}


def _norm(value: Any) -> str:
    text = str(value).strip().lower()
    for old, new in (
        ("现状", "current_"),
        ("历史", "historical_"),
        ("保护建筑名录", "registry"),
        ("历史建筑标签", "registry"),
        ("保护名录", "registry"),
        ("名录", "registry"),
        ("街景", "streetview"),
        ("路网", "roads"),
        ("道路", "roads"),
        ("建筑轮廓", "buildings"),
        ("建筑", "buildings"),
        ("地块", "parcel"),
        ("材料", "material_label"),
        ("地标", "landmark_label"),
        ("poi", "poi"),
    ):
        text = text.replace(old, new)
    cleaned = []
    for char in text:
        if char.isalnum() or char in {"_", "-"}:
            cleaned.append(char)
        elif char.isspace():
            cleaned.append("_")
    return "".join(cleaned).strip("_")


def _infer_format(path_text: str) -> str:
    path = Path(path_text)
    if path.suffix:
        return path.suffix.lower().lstrip(".")
    lowered = path_text.lower()
    if lowered.startswith(("http://", "https://")) or " api" in f" {lowered}" or "source" in lowered:
        return "external_or_api_resource"
    return "directory_or_declared_resource"


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _dedupe_checks(checks: Iterable[Any]) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for check in checks:
        if not isinstance(check, dict):
            continue
        check_id = str(check.get("check_id") or check.get("id") or check)
        if check_id in seen:
            continue
        item = dict(check)
        item.setdefault("check_id", check_id)
        deduped.append(item)
        seen.add(check_id)
    return deduped


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: List[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames and not key.startswith("_"):
                fieldnames.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
