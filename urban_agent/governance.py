"""Resource-governance schema and memory-backed registry.

The kernel owns the schemas and the registry mechanics. Concrete access
policies and tool inventories are loaded from policy memory so experiments can
swap them without changing core code.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from .memory_store import FileMemoryStore


def _schema_to_dict(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return dict(value)
    return {}


class ToolCategory(str, Enum):
    """GeoAgent-style tool classification."""

    SYSTEM_INTERACTION = "System Interaction"
    DATA_UNDERSTANDING = "Data Understanding"
    DOMAIN_KNOWLEDGE = "Domain Knowledge"


@dataclass
class ToolDescriptor:
    """Structured tool descriptor with governance metadata."""

    name: str
    description: str
    category: ToolCategory
    read_roles: Set[str] = field(default_factory=lambda: {"*"})
    write_roles: Set[str] = field(default_factory=lambda: {"*"})
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    avg_latency_ms: Optional[float] = None
    token_cost_estimate: Optional[int] = None


@dataclass
class SpatialEvidence:
    bbox: Optional[List[float]] = None
    crs: Optional[str] = None
    admin_level: Optional[str] = None
    scale_band: Optional[str] = None
    spatial_relation_frame: Optional[str] = None


@dataclass
class TemporalEvidence:
    timestamp: Optional[str] = None
    time_window: Optional[str] = None
    granularity: Optional[str] = None
    forecast_horizon: Optional[str] = None
    freshness: Optional[str] = None


@dataclass
class PopulationEvidence:
    target_group: Optional[str] = None
    observed_group: Optional[str] = None
    affected_group: Optional[str] = None
    sampling_bias: Optional[str] = None
    stakeholder_source: Optional[str] = None


@dataclass
class GovernanceEvidence:
    provenance: Optional[str] = None
    license: Optional[str] = None
    collection_method: Optional[str] = None
    uncertainty: Optional[str] = None
    missing_layers: List[str] = field(default_factory=list)


@dataclass
class EvidenceManifest:
    spatial: Optional[Any] = None
    temporal: Optional[Any] = None
    population: Optional[Any] = None
    governance: Optional[Any] = None
    tags: List[str] = field(default_factory=list)
    data_sources: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "spatial": _schema_to_dict(self.spatial),
            "temporal": _schema_to_dict(self.temporal),
            "population": _schema_to_dict(self.population),
            "governance": _schema_to_dict(self.governance),
            "tags": list(self.tags),
            "data_sources": list(self.data_sources),
        }


@dataclass
class DataResource:
    """RMDA-style data resource description."""

    resource_id: str
    name: str
    description: str
    source: str
    format: str
    spatial_extent: Optional[Dict[str, float]] = None
    temporal_range: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    access_level: str = "read"
    spatial_schema: Optional[Any] = None
    temporal_schema: Optional[Any] = None
    population_schema: Optional[Any] = None
    governance_schema: Optional[Any] = None

    def to_evidence_manifest(self) -> Dict[str, Any]:
        bbox = None
        if isinstance(self.spatial_extent, dict):
            keys = ("min_lon", "min_lat", "max_lon", "max_lat")
            if all(key in self.spatial_extent for key in keys):
                bbox = [self.spatial_extent[key] for key in keys]

        return EvidenceManifest(
            spatial=self.spatial_schema or SpatialEvidence(bbox=bbox),
            temporal=self.temporal_schema or TemporalEvidence(time_window=self.temporal_range),
            population=self.population_schema,
            governance=self.governance_schema or GovernanceEvidence(provenance=self.source),
            tags=self.tags,
            data_sources=[value for value in (self.name, self.source, self.format) if value],
        ).to_dict()


def _load_governance_policy() -> Dict[str, Any]:
    try:
        store = FileMemoryStore.default()
        for record in store.records("policy"):
            payload = record.to_dict()
            if payload.get("policy_id") == "default_governance_policy":
                return payload
    except Exception:
        return {}
    return {}


def _tool_descriptor_from_dict(data: Dict[str, Any]) -> ToolDescriptor:
    category = ToolCategory(data.get("category", ToolCategory.SYSTEM_INTERACTION.value))
    return ToolDescriptor(
        name=str(data.get("name", "")),
        description=str(data.get("description", "")),
        category=category,
        read_roles=set(str(item) for item in data.get("read_roles", ["*"])),
        write_roles=set(str(item) for item in data.get("write_roles", ["*"])),
        input_schema=dict(data.get("input_schema") or {}),
        output_schema=dict(data.get("output_schema") or {}),
        avg_latency_ms=data.get("avg_latency_ms"),
        token_cost_estimate=data.get("token_cost_estimate"),
    )


_POLICY = _load_governance_policy()
ACCESS_MATRIX: Dict[str, Dict[str, str]] = dict(_POLICY.get("access_matrix") or {})
TOOL_INVENTORY: List[ToolDescriptor] = [
    _tool_descriptor_from_dict(item)
    for item in _POLICY.get("tool_inventory", [])
    if isinstance(item, dict) and item.get("name")
]


class GovernanceRegistry:
    """Registry for tool and data governance."""

    def __init__(
        self,
        *,
        access_matrix: Optional[Dict[str, Dict[str, str]]] = None,
        tool_inventory: Optional[List[ToolDescriptor]] = None,
    ) -> None:
        self.access_matrix = access_matrix if access_matrix is not None else ACCESS_MATRIX
        self._tools: Dict[str, ToolDescriptor] = {}
        self._data_resources: Dict[str, DataResource] = {}
        for descriptor in tool_inventory if tool_inventory is not None else TOOL_INVENTORY:
            self.register_tool(descriptor)

    def register_tool(self, descriptor: ToolDescriptor) -> None:
        self._tools[descriptor.name] = descriptor

    def get_tool(self, name: str) -> Optional[ToolDescriptor]:
        return self._tools.get(name)

    def list_tools_by_category(self, cat: ToolCategory) -> List[ToolDescriptor]:
        return [tool for tool in self._tools.values() if tool.category == cat]

    def check_access(self, role: str, tool_name: str, mode: str = "R") -> bool:
        descriptor = self._tools.get(tool_name)
        if descriptor is None:
            return False
        role_key = role.lower()
        if mode == "R":
            return "*" in descriptor.read_roles or role_key in descriptor.read_roles
        return "*" in descriptor.write_roles or role_key in descriptor.write_roles

    def tool_inventory_table(self) -> List[Dict[str, str]]:
        rows = []
        for descriptor in sorted(self._tools.values(), key=lambda item: (item.category.value, item.name)):
            rows.append(
                {
                    "Category": descriptor.category.value,
                    "Tool": descriptor.name,
                    "Description": descriptor.description,
                }
            )
        return rows

    def register_data(self, resource: DataResource) -> None:
        self._data_resources[resource.resource_id] = resource

    def get_data(self, resource_id: str) -> Optional[DataResource]:
        return self._data_resources.get(resource_id)

    def list_data_by_tags(self, *tags: str) -> List[DataResource]:
        tag_set = set(tags)
        return [resource for resource in self._data_resources.values() if tag_set & set(resource.tags)]
