"""Pluggable human correction modules for inspectable urban analysis."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass
class CorrectionModuleSpec:
    """Machine-readable declaration for a correction module."""

    name: str
    description: str
    focus: str
    input_fields: List[str] = field(default_factory=list)
    output_fields: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "focus": self.focus,
            "input_fields": list(self.input_fields),
            "output_fields": list(self.output_fields),
        }


class CorrectionModuleRegistry:
    """Registry that applies human corrections as auditable modules."""

    def __init__(self):
        self._modules: Dict[str, Tuple[CorrectionModuleSpec, Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]]] = {}
        self._register_defaults()

    def register(
        self,
        spec: CorrectionModuleSpec,
        handler: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]],
    ) -> None:
        self._modules[spec.name] = (spec, handler)

    def list_modules(self) -> Dict[str, Dict[str, Any]]:
        return {
            name: spec.to_dict()
            for name, (spec, _) in self._modules.items()
        }

    def get(self, name: str) -> Optional[CorrectionModuleSpec]:
        item = self._modules.get(name)
        return item[0] if item else None

    def apply(self, payload: Dict[str, Any], request: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        request = request or {}
        corrected = copy.deepcopy(payload)
        corrected.setdefault("human_alignment", {})
        corrected.setdefault("correction_audit", [])

        audit = corrected["correction_audit"]
        selected_modules = request.get("selected_modules") or request.get("modules") or list(self._modules)
        corrected["human_alignment"]["selected_modules"] = list(selected_modules)

        entity_audit = self._apply_entity_overrides(corrected, request)
        if entity_audit:
            audit.extend(entity_audit)

        for module_name in selected_modules:
            item = self._modules.get(module_name)
            if item is None:
                audit.append({
                    "module": module_name,
                    "status": "skipped",
                    "reason": "module_not_registered",
                })
                continue

            spec, handler = item
            updates = handler(corrected, request)
            audit.append({
                "module": spec.name,
                "status": "applied" if updates.get("applied") else "noop",
                "applied_fields": updates.get("applied_fields", []),
                "notes": updates.get("notes", ""),
            })

        return {
            "corrected_payload": corrected,
            "audit": audit,
            "available_modules": self.list_modules(),
        }

    def _register_defaults(self) -> None:
        self.register(
            CorrectionModuleSpec(
                name="scale_alignment",
                description="Record scale shifts, MAUP-like risks, and analyst-preferred reading scales.",
                focus="scale_and_maup",
                input_fields=["scale"],
                output_fields=["alignment_diagnostics", "human_alignment"],
            ),
            self._apply_scale_alignment,
        )
        self.register(
            CorrectionModuleSpec(
                name="distribution_review",
                description="Persist pre-analysis distribution checks and visibility requirements.",
                focus="distribution_preview",
                input_fields=["distribution"],
                output_fields=["distribution_preview", "human_alignment"],
            ),
            self._apply_distribution_review,
        )
        self.register(
            CorrectionModuleSpec(
                name="stakeholder_equity",
                description="Attach stakeholder-specific concerns, survey feedback, and spatial justice warnings.",
                focus="fairness_and_contestation",
                input_fields=["stakeholder_feedback"],
                output_fields=["alignment_diagnostics", "human_alignment"],
            ),
            self._apply_stakeholder_feedback,
        )
        self.register(
            CorrectionModuleSpec(
                name="memory_priority",
                description="Capture which previous cases or overrides should be promoted or suppressed in later retrieval.",
                focus="memory_guidance",
                input_fields=["memory_directives"],
                output_fields=["human_alignment", "memory_directives"],
            ),
            self._apply_memory_directives,
        )

    def _apply_entity_overrides(self, corrected: Dict[str, Any], request: Dict[str, Any]) -> List[Dict[str, Any]]:
        audit: List[Dict[str, Any]] = []
        node_overrides = request.get("node_overrides", []) or []
        relation_overrides = request.get("relation_overrides", []) or []

        if node_overrides:
            applied = 0
            for override in node_overrides:
                if self._apply_node_override(corrected, override):
                    applied += 1
            audit.append({
                "module": "entity_override:nodes",
                "status": "applied" if applied else "noop",
                "applied_fields": ["nodes", "topological_graph.nodes"],
                "notes": f"applied {applied} node override(s)",
            })

        if relation_overrides:
            applied = 0
            for override in relation_overrides:
                if self._apply_relation_override(corrected, override):
                    applied += 1
            audit.append({
                "module": "entity_override:relations",
                "status": "applied" if applied else "noop",
                "applied_fields": ["edges", "topological_graph.relations"],
                "notes": f"applied {applied} relation override(s)",
            })

        return audit

    def _apply_node_override(self, corrected: Dict[str, Any], override: Dict[str, Any]) -> bool:
        node_id = override.get("id")
        if not node_id:
            return False

        applied = False
        for node in corrected.get("nodes", []) or []:
            if node.get("id") == node_id:
                for field in ("label", "name", "type", "notes"):
                    if field in override:
                        node[field] = override[field]
                        applied = True

        topo_nodes = corrected.get("topological_graph", {}).get("nodes", {})
        topo_node = topo_nodes.get(node_id)
        if isinstance(topo_node, dict):
            if "label" in override:
                topo_node["label"] = override["label"]
                applied = True
            if "type" in override:
                topo_node["type"] = override["type"]
                applied = True
            if "notes" in override:
                topo_node.setdefault("properties", {})["human_note"] = override["notes"]
                applied = True

        if applied:
            corrected.setdefault("human_alignment", {}).setdefault("node_overrides", []).append(override)
        return applied

    def _apply_relation_override(self, corrected: Dict[str, Any], override: Dict[str, Any]) -> bool:
        source = override.get("source") or override.get("from")
        target = override.get("target") or override.get("to")
        relation_type = override.get("type")
        action = override.get("action", "modify")
        if not source or not target:
            return False

        applied = False
        edges = corrected.get("edges", []) or []
        if action == "add":
            new_edge = {
                "from": source,
                "to": target,
                "type": relation_type or "connected",
                "distance_m": override.get("distance_m"),
                "notes": override.get("notes"),
            }
            edges.append(new_edge)
            corrected["edges"] = edges
            applied = True
        else:
            new_edges = []
            for edge in edges:
                match = edge.get("from") == source and edge.get("to") == target
                if not match:
                    new_edges.append(edge)
                    continue
                if action == "remove":
                    applied = True
                    continue
                if relation_type is not None:
                    edge["type"] = relation_type
                if "distance_m" in override:
                    edge["distance_m"] = override["distance_m"]
                if "notes" in override:
                    edge["notes"] = override["notes"]
                applied = True
                new_edges.append(edge)
            corrected["edges"] = new_edges

        relations = corrected.get("topological_graph", {}).get("relations", [])
        if isinstance(relations, list):
            new_relations = []
            for relation in relations:
                match = relation.get("source") == source and relation.get("target") == target
                if not match:
                    new_relations.append(relation)
                    continue
                if action == "remove":
                    applied = True
                    continue
                if action == "add":
                    new_relations.append(relation)
                    continue
                if relation_type is not None:
                    relation["type"] = relation_type
                if "notes" in override:
                    relation.setdefault("properties", {})["human_note"] = override["notes"]
                applied = True
                new_relations.append(relation)
            if action == "add":
                new_relations.append({
                    "source": source,
                    "target": target,
                    "type": relation_type or "connected",
                    "properties": {"human_note": override.get("notes")},
                    "has_vector_mapping": False,
                })
                applied = True
            corrected.setdefault("topological_graph", {})["relations"] = new_relations

        if applied:
            corrected.setdefault("human_alignment", {}).setdefault("relation_overrides", []).append(override)
        return applied

    def _apply_scale_alignment(self, corrected: Dict[str, Any], request: Dict[str, Any]) -> Dict[str, Any]:
        scale = request.get("scale") or {}
        if not scale:
            return {"applied": False}

        diagnostics = corrected.setdefault("alignment_diagnostics", {})
        diagnostics["preferred_scale"] = scale.get("preferred_scale", diagnostics.get("preferred_scale"))
        diagnostics["maup_like_risk"] = scale.get("maup_like_risk", diagnostics.get("maup_like_risk"))
        diagnostics.setdefault("scale_notes", []).extend(scale.get("notes", []) if isinstance(scale.get("notes"), list) else [scale.get("notes")] if scale.get("notes") else [])
        corrected.setdefault("human_alignment", {})["scale"] = scale
        return {
            "applied": True,
            "applied_fields": ["alignment_diagnostics", "human_alignment.scale"],
            "notes": "updated scale preference and MAUP-like risk",
        }

    def _apply_distribution_review(self, corrected: Dict[str, Any], request: Dict[str, Any]) -> Dict[str, Any]:
        distribution = request.get("distribution") or {}
        if not distribution:
            return {"applied": False}

        preview = corrected.setdefault("distribution_preview", {})
        checks = distribution.get("checks") or []
        existing_checks = preview.setdefault("human_checks", [])
        existing_checks.extend(checks)
        if distribution.get("notes"):
            preview.setdefault("notes", []).extend(
                distribution["notes"] if isinstance(distribution["notes"], list) else [distribution["notes"]]
            )
        if distribution.get("required_views"):
            preview["required_views"] = distribution["required_views"]
        corrected.setdefault("human_alignment", {})["distribution"] = distribution
        return {
            "applied": True,
            "applied_fields": ["distribution_preview", "human_alignment.distribution"],
            "notes": "attached pre-analysis distribution checks",
        }

    def _apply_stakeholder_feedback(self, corrected: Dict[str, Any], request: Dict[str, Any]) -> Dict[str, Any]:
        feedback = request.get("stakeholder_feedback") or request.get("survey_feedback") or []
        if not feedback:
            return {"applied": False}

        diagnostics = corrected.setdefault("alignment_diagnostics", {})
        fairness_flags = diagnostics.setdefault("fairness_flags", [])
        for item in feedback:
            group = item.get("group", "stakeholder")
            concern = item.get("concern") or item.get("notes") or "unspecified concern"
            fairness_flags.append(f"{group}: {concern}")
        corrected.setdefault("human_alignment", {})["stakeholder_feedback"] = feedback
        return {
            "applied": True,
            "applied_fields": ["alignment_diagnostics.fairness_flags", "human_alignment.stakeholder_feedback"],
            "notes": "attached stakeholder and spatial justice feedback",
        }

    def _apply_memory_directives(self, corrected: Dict[str, Any], request: Dict[str, Any]) -> Dict[str, Any]:
        memory_directives = request.get("memory_directives") or request.get("memory") or {}
        if not memory_directives:
            return {"applied": False}

        corrected["memory_directives"] = memory_directives
        corrected.setdefault("human_alignment", {})["memory_directives"] = memory_directives
        return {
            "applied": True,
            "applied_fields": ["memory_directives", "human_alignment.memory_directives"],
            "notes": "captured memory promotion/suppression directives",
        }