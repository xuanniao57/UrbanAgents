"""Method-level capability registry for UrbanAgent.

The kernel keeps only the registry mechanism and a small set of urban-analysis
capability cards. Benchmark, demo, desktop, and agent-runtime integrations belong
in memory cards or plugin manifests.
"""

from __future__ import annotations

import importlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence


DISCLOSURE_LEVELS = {0, 1, 2, 3}


@dataclass(frozen=True)
class CapabilityBackend:
    """Execution backend for a capability."""

    name: str
    kind: str
    target: str
    description: str = ""
    executable: bool = False
    requires: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self, *, include_metadata: bool = True) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "name": self.name,
            "kind": self.kind,
            "target": self.target,
            "description": self.description,
            "executable": self.executable,
            "requires": list(self.requires),
        }
        if include_metadata:
            payload["metadata"] = dict(self.metadata)
        return payload

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CapabilityBackend":
        return cls(
            name=str(data.get("name", "")),
            kind=str(data.get("kind", "")),
            target=str(data.get("target", "")),
            description=str(data.get("description", "")),
            executable=bool(data.get("executable", False)),
            requires=list(data.get("requires", []) or []),
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass(frozen=True)
class CapabilitySpec:
    """Method-level declaration exposed progressively to the planner."""

    name: str
    title: str
    family: str
    capability_type: str
    summary: str
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    backends: List[CapabilityBackend] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    disclosure_hint: str = "level_1_card"
    mcp_tool: Optional[str] = None

    def level0(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "family": self.family,
            "type": self.capability_type,
            "summary": self.summary,
            "tags": list(self.tags[:8]),
        }

    def level1(self) -> Dict[str, Any]:
        payload = self.level0()
        payload.update(
            {
                "inputs": list(self.inputs),
                "outputs": list(self.outputs),
                "backend_names": [backend.name for backend in self.backends],
                "constraints": list(self.constraints),
                "disclosure_hint": self.disclosure_hint,
            }
        )
        return payload

    def level2(self, tool_parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        executable_backend = next((backend for backend in self.backends if backend.executable), None)
        payload = self.level1()
        payload.update(
            {
                "backends": [backend.to_dict(include_metadata=False) for backend in self.backends],
                "invocation": (
                    {"mcp_tool": self.mcp_tool, "parameters": tool_parameters or {}}
                    if self.mcp_tool
                    else {"python_function": executable_backend.target, "parameters": tool_parameters or {}}
                    if executable_backend and executable_backend.kind == "python_function"
                    else None
                ),
            }
        )
        return payload

    def level3(self, tool_definition: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = self.level2((tool_definition or {}).get("parameters"))
        payload.update(
            {
                "tool_definition": tool_definition,
                "backends": [backend.to_dict(include_metadata=True) for backend in self.backends],
            }
        )
        return payload

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CapabilitySpec":
        return cls(
            name=str(data["name"]),
            title=str(data.get("title") or data["name"]),
            family=str(data.get("family") or "method"),
            capability_type=str(data.get("capability_type") or data.get("type") or "urban_method"),
            summary=str(data.get("summary") or data.get("description") or ""),
            inputs=list(data.get("inputs", []) or []),
            outputs=list(data.get("outputs", []) or []),
            tags=list(data.get("tags", []) or []),
            backends=[
                CapabilityBackend.from_dict(item)
                for item in data.get("backends", []) or []
                if isinstance(item, dict)
            ],
            constraints=list(data.get("constraints", []) or []),
            disclosure_hint=str(data.get("disclosure_hint") or "level_1_card"),
            mcp_tool=data.get("mcp_tool"),
        )


class CapabilityRegistry:
    """Registry with progressive disclosure and lightweight task search."""

    def __init__(self, capabilities: Optional[Iterable[CapabilitySpec]] = None):
        self._capabilities: Dict[str, CapabilitySpec] = {}
        for capability in capabilities or []:
            self.register(capability)

    def register(self, capability: CapabilitySpec) -> None:
        self._capabilities[capability.name] = capability

    def get(self, name: str) -> Optional[CapabilitySpec]:
        return self._capabilities.get(name)

    def names(self) -> List[str]:
        return sorted(self._capabilities)

    def list_index(self, *, family: Optional[str] = None) -> List[Dict[str, Any]]:
        return [capability.level0() for capability in self._filtered(family=family)]

    def disclose(self, names: Sequence[str], *, level: int = 1, mcp_tools: Optional[Any] = None) -> List[Dict[str, Any]]:
        if level not in DISCLOSURE_LEVELS:
            raise ValueError(f"unsupported disclosure level: {level}")

        disclosed = []
        for name in names:
            capability = self.get(name)
            if capability is None:
                continue
            tool_definition = self._tool_definition(capability.mcp_tool, mcp_tools)
            if level == 0:
                disclosed.append(capability.level0())
            elif level == 1:
                disclosed.append(capability.level1())
            elif level == 2:
                disclosed.append(capability.level2((tool_definition or {}).get("parameters")))
            else:
                disclosed.append(capability.level3(tool_definition))
        return disclosed

    def search(self, query: str, *, family: Optional[str] = None, limit: int = 8) -> List[CapabilitySpec]:
        terms = _tokenize(query)
        capabilities = self._filtered(family=family)
        if not terms:
            return capabilities[:limit]

        scored: List[tuple[int, CapabilitySpec]] = []
        for capability in capabilities:
            haystack = " ".join(
                [
                    capability.name,
                    capability.title,
                    capability.family,
                    capability.capability_type,
                    capability.summary,
                    " ".join(capability.inputs),
                    " ".join(capability.outputs),
                    " ".join(capability.tags),
                    " ".join(backend.name for backend in capability.backends),
                ]
            ).lower()
            score = sum(3 if term in capability.name.lower() else 1 for term in terms if term in haystack)
            if score:
                scored.append((score, capability))
        scored.sort(key=lambda item: (-item[0], item[1].name))
        return [capability for _, capability in scored[:limit]]

    def select_for_task(self, task: Dict[str, Any] | str, *, limit: int = 6, mcp_tools: Optional[Any] = None) -> Dict[str, Any]:
        text = task if isinstance(task, str) else json.dumps(task, ensure_ascii=False, default=str)
        selected = self.search(text, limit=limit)
        if not selected:
            selected = [self._capabilities[name] for name in self.names()[:limit]]
        names = [capability.name for capability in selected]
        return {
            "disclosure_policy": "progressive",
            "level0_index_size": len(self._capabilities),
            "selected_names": names,
            "selected_level0": self.disclose(names, level=0, mcp_tools=mcp_tools),
            "level1_cards": self.disclose(names, level=1, mcp_tools=mcp_tools),
        }

    def openai_tools_for(self, names: Sequence[str], *, mcp_tools: Optional[Any] = None) -> List[Dict[str, Any]]:
        tools = []
        for name in names:
            capability = self.get(name)
            if capability is None or not capability.mcp_tool:
                continue
            tool_definition = self._tool_definition(capability.mcp_tool, mcp_tools)
            if not tool_definition:
                continue
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool_definition["name"],
                        "description": tool_definition.get("description", capability.summary),
                        "parameters": tool_definition.get("parameters", {"type": "object", "properties": {}}),
                    },
                }
            )
        return tools

    def _filtered(self, *, family: Optional[str] = None) -> List[CapabilitySpec]:
        capabilities = [self._capabilities[name] for name in self.names()]
        if family:
            capabilities = [item for item in capabilities if item.family == family]
        return capabilities

    @staticmethod
    def _tool_definition(tool_name: Optional[str], mcp_tools: Optional[Any]) -> Optional[Dict[str, Any]]:
        if not tool_name or mcp_tools is None:
            return None
        if hasattr(mcp_tools, "tools") and tool_name in mcp_tools.tools:
            tool = mcp_tools.tools[tool_name]
            return {"name": tool.name, "description": tool.description, "parameters": tool.parameters}
        if hasattr(mcp_tools, "get_tool_definitions"):
            for tool in mcp_tools.get_tool_definitions():
                if tool.get("name") == tool_name:
                    return tool
        return None


class ToolBroker:
    """Resolve selected capabilities to executable tool backends."""

    def __init__(self, registry: CapabilityRegistry, mcp_tools: Optional[Any] = None):
        self.registry = registry
        self.mcp_tools = mcp_tools

    def choose_backend(self, capability_name: str, preferred_backend: Optional[str] = None) -> CapabilityBackend:
        capability = self.registry.get(capability_name)
        if capability is None:
            raise KeyError(f"unknown capability: {capability_name}")
        candidates = capability.backends
        if preferred_backend:
            candidates = [backend for backend in candidates if backend.name == preferred_backend]
        executable = [backend for backend in candidates if backend.executable]
        if not executable:
            raise RuntimeError(f"capability '{capability_name}' has no executable backend")
        return executable[0]

    def execute(self, capability_name: str, arguments: Dict[str, Any], *, backend_name: Optional[str] = None) -> Dict[str, Any]:
        backend = self.choose_backend(capability_name, backend_name)
        if backend.kind == "mcp_tool":
            if self.mcp_tools is None:
                raise RuntimeError("mcp_tools is not configured")
            return self.mcp_tools.execute_tool(backend.target, arguments)
        if backend.kind == "python_function":
            module_name, _, function_name = backend.target.partition(":")
            if not module_name or not function_name:
                raise RuntimeError(f"invalid python function target: {backend.target}")
            module = importlib.import_module(module_name)
            handler = getattr(module, function_name)
            return handler(arguments)
        raise RuntimeError(f"backend kind '{backend.kind}' is not directly executable")

    def tool_handlers_for(self, capability_names: Sequence[str]) -> Dict[str, Callable[..., str]]:
        handlers: Dict[str, Callable[..., str]] = {}
        for capability_name in capability_names:
            capability = self.registry.get(capability_name)
            if capability is None or capability.mcp_tool is None:
                continue

            def _handler(_capability_name: str = capability_name, **kwargs: Any) -> str:
                result = self.execute(_capability_name, kwargs)
                return json.dumps(result, ensure_ascii=False, default=str)

            handlers[capability.mcp_tool] = _handler
        return handlers


def get_default_capability_registry(*, include_external: bool = False) -> CapabilityRegistry:
    capabilities = list(_kernel_capabilities())
    if include_external:
        capabilities.extend(load_external_capability_cards())
    return CapabilityRegistry(capabilities)


def get_default_tool_broker(mcp_tools: Optional[Any] = None) -> ToolBroker:
    return ToolBroker(get_default_capability_registry(), mcp_tools=mcp_tools)


def load_external_capability_cards(paths: Optional[Iterable[str | Path]] = None) -> List[CapabilitySpec]:
    """Load optional capability cards from JSON files or plugin manifests."""

    roots: List[Path] = []
    env_root = os.getenv("URBAN_AGENT_CAPABILITY_ROOT")
    if env_root:
        roots.append(Path(env_root))
    if paths:
        roots.extend(Path(item) for item in paths)

    loaded: List[CapabilitySpec] = []
    for root in roots:
        if root.is_file():
            loaded.extend(_read_capability_file(root))
        elif root.exists():
            for path in sorted(root.rglob("*.json")):
                loaded.extend(_read_capability_file(path))
    return loaded


def _read_capability_file(path: Path) -> List[CapabilitySpec]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return []
    raw_items = data.get("capabilities", data.get("records", data)) if isinstance(data, dict) else data
    if isinstance(raw_items, dict):
        raw_items = [raw_items]
    if not isinstance(raw_items, list):
        return []
    specs = []
    for item in raw_items:
        if isinstance(item, dict) and item.get("name"):
            try:
                specs.append(CapabilitySpec.from_dict(item))
            except Exception:
                continue
    return specs


def _backend(name: str, kind: str, target: str, description: str, *, executable: bool = False, requires: Optional[List[str]] = None) -> CapabilityBackend:
    return CapabilityBackend(
        name=name,
        kind=kind,
        target=target,
        description=description,
        executable=executable,
        requires=requires or [],
    )


def _kernel_capabilities() -> List[CapabilitySpec]:
    return [
        CapabilitySpec(
            name="input_grounding_artifacts",
            title="Input Grounding Artifacts",
            family="governance",
            capability_type="grounding_method",
            summary="Build dataset cards, grounding policy, and indicator computability artifacts from task-declared resources.",
            inputs=["task_data", "path_context"],
            outputs=["dataset_cards", "grounding_policy", "indicator_computability_matrix"],
            tags=["grounding", "dataset card", "evidence", "computability", "policy"],
            backends=[
                _backend("grounding_generator", "python_function", "urban_agent.grounding:build_input_grounding_package", "Generate reviewable grounding artifacts.", executable=True),
            ],
            constraints=["Task-specific indicator schemas must arrive from task input or memory."],
        ),
        CapabilitySpec(
            name="osm_context_acquisition",
            title="OSM Context Acquisition",
            family="data",
            capability_type="geospatial_data_method",
            summary="Acquire roads, buildings, POIs, and land-use context for a study area.",
            inputs=["location", "radius", "data_types"],
            outputs=["road_graph", "buildings", "pois", "landuse"],
            tags=["osm", "openstreetmap", "roads", "buildings", "poi", "data"],
            backends=[
                _backend("overpass_context_fetch", "python_function", "urban_agent.tools.geo_small_tools:fetch_osm_overpass_tool", "Small Overpass fetch tool for AOI/context roads and buildings.", executable=True),
            ],
            constraints=["Requires a resolvable place name or bounding geometry."],
        ),
        CapabilitySpec(
            name="spatial_source_diagnostics",
            title="Spatial Source Extent Diagnostics",
            family="method",
            capability_type="spatial_diagnostic_method",
            summary="Compare source layer extents with AOI and context buffer extents in a shared metric CRS.",
            inputs=["aoi_boundary", "roads", "buildings", "context_buffer"],
            outputs=["alignment_diagnostics", "source_to_context_width_ratio", "source_to_context_height_ratio"],
            tags=["source", "extent", "coverage", "buffer", "diagnostics"],
            backends=[
                _backend("geopandas_extent_diagnostics", "python_function", "urban_agent.tools.geo_small_tools:validate_source_extent_against_context", "Compute source-vs-context diagnostics.", executable=True),
            ],
            constraints=["Threshold interpretation belongs to policy memory and ReviewHub."],
        ),
        CapabilitySpec(
            name="aoi_context_buffer",
            title="AOI Context Buffer",
            family="method",
            capability_type="spatial_context_method",
            summary="Build an AOI-centered context buffer and report metric buffer diagnostics.",
            inputs=["aoi_boundary", "context_buffer_width_factor", "context_buffer_height_factor"],
            outputs=["context_buffer_layer", "context_buffer_diagnostics"],
            tags=["aoi", "context", "buffer", "diagnostics", "scale"],
            backends=[
                _backend("geopandas_context_buffer", "python_function", "urban_agent.tools.geo_small_tools:build_aoi_context_buffer_tool", "Build context buffer diagnostics from a boundary layer.", executable=True),
            ],
            constraints=["Policy memory decides required factors and thresholds."],
        ),
        CapabilitySpec(
            name="urban_density_morphology",
            title="Urban Density and Morphology Metrics",
            family="method",
            capability_type="urban_morphology_method",
            summary="Compute building footprint, height-proxy, road-density, and morphology metrics.",
            inputs=["buildings", "roads", "aoi_boundary", "grid_size"],
            outputs=["building_coverage_ratio", "mean_height_proxy_m", "road_density_km_per_km2", "metric_rows"],
            tags=["density", "morphology", "building", "height", "footprint", "urban fabric"],
            backends=[
                _backend("geopandas_projected_metrics", "python_function", "urban_agent.tools.metrics.built_form:compute_built_form_metrics", "Projected vector metrics for footprints, height proxies, and roads.", executable=True),
            ],
            constraints=["Requires projected CRS for area and grid-size metrics."],
        ),
        CapabilitySpec(
            name="function_mix_entropy",
            title="Function Mix Entropy",
            family="method",
            capability_type="land_use_function_method",
            summary="Compute Shannon entropy and dominant-share diagnostics from POI or building-function labels.",
            inputs=["poi_or_function_layer", "function_counts"],
            outputs=["function_entropy", "function_entropy_normalized", "dominant_function_share", "metric_rows"],
            tags=["poi", "function", "land use", "entropy", "mixed use"],
            backends=[
                _backend("pandas_geopandas_entropy", "python_function", "urban_agent.tools.metrics.function_mix:compute_function_mix_entropy", "Entropy computation from function counts or labeled GeoDataFrame.", executable=True),
            ],
            constraints=["Function labels inherit source/model uncertainty and should be reported with provenance."],
        ),
        CapabilitySpec(
            name="streetview_visual_consistency",
            title="Street-view Visual Consistency",
            family="method",
            capability_type="streetview_visual_method",
            summary="Compute visual-consistency proxies from street-view image color histograms and palette distances.",
            inputs=["streetview_image_directory", "streetview_points"],
            outputs=["style_consistency_score", "traditional_palette_match_score", "metric_rows"],
            tags=["streetview", "image", "style", "visual", "facade", "color", "heritage"],
            backends=[
                _backend("pillow_numpy_histograms", "python_function", "urban_agent.tools.metrics.streetview_proxy:compute_streetview_visual_consistency", "Color histogram and palette-distance proxy.", executable=True),
            ],
            constraints=["Proxy only; material/signboard claims require VLM or manual labels."],
        ),
        CapabilitySpec(
            name="gis_layer_stack_export",
            title="GIS Layer Stack Export",
            family="action",
            capability_type="formal_gis_visualization_method",
            summary="Export AOI-clipped analysis layers, context layers, metric/result layers, maps, charts, and evidence grids.",
            inputs=["aoi_boundary", "roads", "buildings", "function_layers", "metric_rows", "artifact_dir"],
            outputs=["gpkg", "context_layer_stack", "metric_result_layers", "map_png", "map_pdf", "metric_csv", "chart_png"],
            tags=["gis", "gpkg", "geopackage", "map", "buffer", "context", "metric result"],
            backends=[
                _backend("geopandas_matplotlib_bundle", "python_function", "urban_agent.tools.export.gis_bundle:build_gis_artifact_bundle", "Local GeoPandas/Matplotlib formal GIS artifact bundle.", executable=True),
            ],
            constraints=["Artifact expectations and review thresholds are loaded from policy memory."],
        ),
    ]


def _tokenize(text: str) -> List[str]:
    lowered = text.lower()
    tokens = re.findall(r"[a-z0-9_\-]+|[\u4e00-\u9fff]+", lowered)
    aliases = {
        "步行": ["walkability", "accessibility"],
        "可达": ["accessibility"],
        "连通": ["connectivity", "network"],
        "密度": ["density"],
        "功能": ["function", "entropy", "land use"],
        "街景": ["streetview", "image", "visual"],
        "地图": ["map", "visualization", "gis"],
        "图层": ["layer", "gis", "geopackage"],
        "数据集": ["dataset", "card", "grounding"],
        "卡片": ["card", "dataset", "grounding"],
        "声明": ["grounding", "policy", "evidence"],
        "证据": ["evidence", "grounding", "dataset"],
        "osm": ["osm", "openstreetmap", "roads", "buildings"],
        "gis": ["gis", "geopackage", "map"],
    }
    expanded: List[str] = []
    for token in tokens:
        expanded.append(token)
        expanded.extend(aliases.get(token, []))
    for phrase, phrase_aliases in aliases.items():
        if phrase in lowered and phrase not in expanded:
            expanded.append(phrase)
            expanded.extend(phrase_aliases)
    return [token.strip().lower() for token in expanded if token.strip()]
