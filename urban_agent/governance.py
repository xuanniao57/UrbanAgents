"""
Resource Governance — 资源管理与工具分类

参考 RMDA 的资源治理 (Data Governance + Model Governance + Tool Inventory):
1. Tool Classification: 按 GeoAgent Table 1 三类 (System Interaction, Data Understanding, Domain Knowledge)
2. Data Description Schema: RMDA-style hashtag-based 数据描述
3. Access Control Matrix: 明确每个 agent-role 对 tool/data 的 R/W 权限
4. Tool Inventory: 18 tools × 3 categories, 供论文 Table 引用
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Set


def _schema_to_dict(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return dict(value)
    return {}


# ---------------------------------------------------------------------------
# Tool Category (GeoAgent Table 1 taxonomy)
# ---------------------------------------------------------------------------

class ToolCategory(str, Enum):
    """GeoAgent-style tool classification."""
    SYSTEM_INTERACTION = "System Interaction"
    DATA_UNDERSTANDING = "Data Understanding"
    DOMAIN_KNOWLEDGE = "Domain Knowledge"


# ---------------------------------------------------------------------------
# Tool Descriptor
# ---------------------------------------------------------------------------

@dataclass
class ToolDescriptor:
    """Structured tool descriptor with governance metadata."""
    name: str
    description: str
    category: ToolCategory
    # RMDA-style access control
    read_roles: Set[str] = field(default_factory=lambda: {"*"})
    write_roles: Set[str] = field(default_factory=lambda: {"*"})
    # RMDA-style data description
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    # Cost / efficiency hints
    avg_latency_ms: Optional[float] = None
    token_cost_estimate: Optional[int] = None


# ---------------------------------------------------------------------------
# Typed Evidence Schema + Data Resource Descriptor
# ---------------------------------------------------------------------------

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
    source: str  # e.g. "OSM", "CityBench", "user_upload"
    format: str  # e.g. "GeoJSON", "CSV", "GeoTIFF"
    spatial_extent: Optional[Dict[str, float]] = None  # bbox
    temporal_range: Optional[str] = None
    tags: List[str] = field(default_factory=list)  # hashtag-based
    access_level: str = "read"  # "read" | "write" | "admin"
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

        spatial = self.spatial_schema or SpatialEvidence(bbox=bbox)
        temporal = self.temporal_schema or TemporalEvidence(time_window=self.temporal_range)
        governance = self.governance_schema or GovernanceEvidence(provenance=self.source)

        return EvidenceManifest(
            spatial=spatial,
            temporal=temporal,
            population=self.population_schema,
            governance=governance,
            tags=self.tags,
            data_sources=[value for value in (self.name, self.source, self.format) if value],
        ).to_dict()


# ---------------------------------------------------------------------------
# Access Control Matrix
# ---------------------------------------------------------------------------

# Each role has explicit R/W permission on resource categories
# Inspired by RMDA Table 2
ACCESS_MATRIX: Dict[str, Dict[str, str]] = {
    "planner": {
        "System Interaction": "R",
        "Data Understanding": "R",
        "Domain Knowledge": "R",
    },
    "perception": {
        "System Interaction": "R/W",
        "Data Understanding": "R/W",
        "Domain Knowledge": "R",
    },
    "analyst": {
        "System Interaction": "R",
        "Data Understanding": "R/W",
        "Domain Knowledge": "R/W",
    },
    "cartographer": {
        "System Interaction": "R/W",
        "Data Understanding": "R",
        "Domain Knowledge": "R",
    },
    "reporter": {
        "System Interaction": "R",
        "Data Understanding": "R",
        "Domain Knowledge": "R",
    },
    "spatial_reviewer": {
        "System Interaction": "R",
        "Data Understanding": "R",
        "Domain Knowledge": "R",
    },
    "quality_controller": {
        "System Interaction": "R",
        "Data Understanding": "R",
        "Domain Knowledge": "R",
    },
    "manager": {
        "System Interaction": "R/W",
        "Data Understanding": "R/W",
        "Domain Knowledge": "R/W",
    },
}


# ---------------------------------------------------------------------------
# Tool Inventory (18 tools classified)
# ---------------------------------------------------------------------------

TOOL_INVENTORY: List[ToolDescriptor] = [
    # ── System Interaction (6 tools) ──
    ToolDescriptor(
        name="fetch_osm_data",
        description="获取指定区域的 OpenStreetMap 数据",
        category=ToolCategory.SYSTEM_INTERACTION,
        read_roles={"perception", "analyst", "manager"},
        write_roles={"perception"},
    ),
    ToolDescriptor(
        name="list_connectors",
        description="列出可用的外部连接器",
        category=ToolCategory.SYSTEM_INTERACTION,
        read_roles={"*"},
    ),
    ToolDescriptor(
        name="rhino_health_check",
        description="检查 Rhino.Compute 服务状态",
        category=ToolCategory.SYSTEM_INTERACTION,
        read_roles={"*"},
    ),
    ToolDescriptor(
        name="evaluate_grasshopper_definition",
        description="执行 Grasshopper 定义文件",
        category=ToolCategory.SYSTEM_INTERACTION,
        read_roles={"cartographer", "analyst"},
        write_roles={"cartographer"},
    ),
    ToolDescriptor(
        name="call_grasshopper_hops",
        description="调用 Grasshopper Hops 远程端点",
        category=ToolCategory.SYSTEM_INTERACTION,
        read_roles={"cartographer", "analyst"},
        write_roles={"cartographer"},
    ),
    ToolDescriptor(
        name="invoke_rhino_compute",
        description="调用 Rhino.Compute REST 端点",
        category=ToolCategory.SYSTEM_INTERACTION,
        read_roles={"cartographer", "analyst"},
        write_roles={"cartographer"},
    ),

    # ── Data Understanding (7 tools) ──
    ToolDescriptor(
        name="analyze_connectivity",
        description="分析道路网络连通性",
        category=ToolCategory.DATA_UNDERSTANDING,
        read_roles={"analyst", "perception"},
        write_roles={"analyst"},
    ),
    ToolDescriptor(
        name="measure_accessibility",
        description="测量建筑到目标点的可达性",
        category=ToolCategory.DATA_UNDERSTANDING,
        read_roles={"analyst", "perception"},
        write_roles={"analyst"},
    ),
    ToolDescriptor(
        name="calculate_density",
        description="计算建筑密度分布",
        category=ToolCategory.DATA_UNDERSTANDING,
        read_roles={"analyst", "perception"},
        write_roles={"analyst"},
    ),
    ToolDescriptor(
        name="build_topology",
        description="从空间特征构建拓扑图",
        category=ToolCategory.DATA_UNDERSTANDING,
        read_roles={"analyst", "perception"},
        write_roles={"analyst"},
    ),
    ToolDescriptor(
        name="export_geojson",
        description="导出 GeoJSON 格式的空间数据",
        category=ToolCategory.DATA_UNDERSTANDING,
        read_roles={"*"},
        write_roles={"cartographer", "analyst"},
    ),
    ToolDescriptor(
        name="rank_traffic_signal_phases",
        description="根据车辆数据排序交通信号相位",
        category=ToolCategory.DATA_UNDERSTANDING,
        read_roles={"analyst"},
        write_roles={"analyst"},
    ),

    # ── Domain Knowledge (5 tools) ──
    ToolDescriptor(
        name="generate_svg_overlay",
        description="生成 SVG 空间干预可视化",
        category=ToolCategory.DOMAIN_KNOWLEDGE,
        read_roles={"cartographer", "reporter"},
        write_roles={"cartographer"},
    ),
    ToolDescriptor(
        name="generate_measurement_report",
        description="生成空间测量报告",
        category=ToolCategory.DOMAIN_KNOWLEDGE,
        read_roles={"reporter", "analyst"},
        write_roles={"reporter"},
    ),
    ToolDescriptor(
        name="select_exploration_target",
        description="选出综合评分最优探索目标",
        category=ToolCategory.DOMAIN_KNOWLEDGE,
        read_roles={"analyst"},
        write_roles={"analyst"},
    ),
]


# ---------------------------------------------------------------------------
# Governance Registry
# ---------------------------------------------------------------------------

class GovernanceRegistry:
    """Central registry for tool + data governance."""

    def __init__(self) -> None:
        self._tools: Dict[str, ToolDescriptor] = {}
        self._data_resources: Dict[str, DataResource] = {}
        # Load built-in inventory
        for td in TOOL_INVENTORY:
            self._tools[td.name] = td

    # -- Tool queries --

    def get_tool(self, name: str) -> Optional[ToolDescriptor]:
        return self._tools.get(name)

    def list_tools_by_category(self, cat: ToolCategory) -> List[ToolDescriptor]:
        return [t for t in self._tools.values() if t.category == cat]

    def check_access(self, role: str, tool_name: str, mode: str = "R") -> bool:
        """Check if an agent role has access to a tool."""
        td = self._tools.get(tool_name)
        if td is None:
            return False
        if mode == "R":
            return "*" in td.read_roles or role in td.read_roles
        return "*" in td.write_roles or role in td.write_roles

    def tool_inventory_table(self) -> List[Dict[str, str]]:
        """Return tabular data for paper Table (tool inventory)."""
        rows = []
        for td in sorted(self._tools.values(), key=lambda t: (t.category.value, t.name)):
            rows.append({
                "Category": td.category.value,
                "Tool": td.name,
                "Description": td.description,
            })
        return rows

    # -- Data resource queries --

    def register_data(self, resource: DataResource) -> None:
        self._data_resources[resource.resource_id] = resource

    def get_data(self, resource_id: str) -> Optional[DataResource]:
        return self._data_resources.get(resource_id)

    def list_data_by_tags(self, *tags: str) -> List[DataResource]:
        tag_set = set(tags)
        return [r for r in self._data_resources.values() if tag_set & set(r.tags)]
