"""Method-level capability registry for UrbanAgent.

The registry separates urban-analysis methods from their execution backends.
LLM agents see compact capability cards first, then request concrete invocation
schemas only when a capability is selected for execution.
"""

from __future__ import annotations

import json
import re
import importlib
from dataclasses import dataclass, field
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
        payload.update({
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "backend_names": [backend.name for backend in self.backends],
            "constraints": list(self.constraints),
            "disclosure_hint": self.disclosure_hint,
        })
        return payload

    def level2(self, tool_parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = self.level1()
        payload.update({
            "backends": [backend.to_dict(include_metadata=False) for backend in self.backends],
            "invocation": {
                "mcp_tool": self.mcp_tool,
                "parameters": tool_parameters or {},
            } if self.mcp_tool else None,
        })
        return payload

    def level3(self, tool_definition: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = self.level2((tool_definition or {}).get("parameters"))
        payload.update({
            "tool_definition": tool_definition,
            "backends": [backend.to_dict(include_metadata=True) for backend in self.backends],
        })
        return payload


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
        capabilities = self._filtered(family=family)
        return [capability.level0() for capability in capabilities]

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
            haystack = " ".join([
                capability.name,
                capability.title,
                capability.family,
                capability.capability_type,
                capability.summary,
                " ".join(capability.inputs),
                " ".join(capability.outputs),
                " ".join(capability.tags),
                " ".join(backend.name for backend in capability.backends),
            ]).lower()
            score = sum(3 if term in capability.name.lower() else 1 for term in terms if term in haystack)
            if score:
                scored.append((score, capability))
        scored.sort(key=lambda item: (-item[0], item[1].name))
        return [capability for _, capability in scored[:limit]]

    def select_for_task(self, task: Dict[str, Any] | str, *, limit: int = 6, mcp_tools: Optional[Any] = None) -> Dict[str, Any]:
        text = task if isinstance(task, str) else json.dumps(task, ensure_ascii=False, default=str)
        selected = self.search(text, limit=limit)
        selected = _filter_contextual_false_positives(text, selected)
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
            tools.append({
                "type": "function",
                "function": {
                    "name": tool_definition["name"],
                    "description": tool_definition.get("description", capability.summary),
                    "parameters": tool_definition.get("parameters", {"type": "object", "properties": {}}),
                },
            })
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
            return {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
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


def get_default_capability_registry() -> CapabilityRegistry:
    return CapabilityRegistry(_default_capabilities())


def get_default_tool_broker(mcp_tools: Optional[Any] = None) -> ToolBroker:
    if mcp_tools is None:
        from .mcp_tools import get_mcp_tools

        mcp_tools = get_mcp_tools()
    return ToolBroker(get_default_capability_registry(), mcp_tools=mcp_tools)


def _backend(name: str, kind: str, target: str, description: str, *, executable: bool = False, requires: Optional[List[str]] = None) -> CapabilityBackend:
    return CapabilityBackend(
        name=name,
        kind=kind,
        target=target,
        description=description,
        executable=executable,
        requires=requires or [],
    )


def _default_capabilities() -> List[CapabilitySpec]:
    return [
        CapabilitySpec(
            name="osm_context_acquisition",
            title="OSM Context Acquisition",
            family="data",
            capability_type="geospatial_data_method",
            summary="Acquire roads, buildings, POIs, and land-use context for a study area.",
            inputs=["location", "radius", "data_types"],
            outputs=["road_graph", "buildings", "pois", "landuse"],
            tags=["osm", "openstreetmap", "roads", "buildings", "poi", "data", "context", "perception"],
            backends=[
                _backend("osmnx", "python_library", "osmnx", "Direct OSMnx feature and graph download."),
                _backend("mcp_fetch_osm_data", "mcp_tool", "fetch_osm_data", "UrbanAgent MCP wrapper for OSM acquisition.", executable=True),
                _backend("qgis_processing", "desktop_gis", "qgis", "QGIS processing models for OSM layers."),
            ],
            constraints=["Requires a resolvable place name or bounding geometry.", "Large regions should be tiled."],
            mcp_tool="fetch_osm_data",
        ),
        CapabilitySpec(
            name="network_connectivity_analysis",
            title="Network Connectivity Analysis",
            family="method",
            capability_type="spatial_network_method",
            summary="Measure graph connectivity, node degree, network density, and routing readiness.",
            inputs=["road_graph"],
            outputs=["average_degree", "node_count", "edge_count", "density"],
            tags=["connectivity", "network", "graph", "streets", "walkability", "routing", "accessibility"],
            backends=[
                _backend("networkx", "python_library", "networkx", "NetworkX graph metrics."),
                _backend("mcp_analyze_connectivity", "mcp_tool", "analyze_connectivity", "UrbanAgent MCP connectivity wrapper.", executable=True),
                _backend("arcgis_network_analyst", "enterprise_gis", "arcgis", "ArcGIS Network Analyst backend where licensed."),
            ],
            constraints=["Input graph must be routable and projected where metric distances are used."],
            mcp_tool="analyze_connectivity",
        ),
        CapabilitySpec(
            name="network_accessibility",
            title="Network Accessibility",
            family="method",
            capability_type="accessibility_method",
            summary="Compute distance or travel-time accessibility from origins to destinations.",
            inputs=["origins/buildings", "target_points", "network_or_distance_model"],
            outputs=["average_distance", "median_distance", "coverage_ratio", "isochrone_like_summary"],
            tags=["accessibility", "walkability", "amenity", "service", "distance", "equity", "network"],
            backends=[
                _backend("geopandas_shapely", "python_library", "geopandas+shapely", "Vector distance baseline."),
                _backend("mcp_measure_accessibility", "mcp_tool", "measure_accessibility", "UrbanAgent MCP accessibility wrapper.", executable=True),
                _backend("qgis_service_area", "desktop_gis", "qgis", "QGIS service-area processing workflow."),
            ],
            constraints=["Euclidean fallback should be labeled separately from network accessibility."],
            mcp_tool="measure_accessibility",
        ),
        CapabilitySpec(
            name="urban_density_morphology",
            title="Urban Density and Morphology Metrics",
            family="method",
            capability_type="urban_morphology_method",
            summary="Compute projected building footprint, coverage, height-proxy, road-density, and D/H morphology metrics.",
            inputs=["buildings", "roads", "aoi_boundary", "grid_size"],
            outputs=["building_coverage_ratio", "mean_height_proxy_m", "dh_ratio_proxy", "road_density_km_per_km2", "metric_rows"],
            tags=["density", "morphology", "building", "height", "d/h", "footprint", "urban fabric", "form"],
            backends=[
                _backend("geopandas_projected_metrics", "python_function", "urban_agent.tools.geo_tools:compute_built_form_metrics", "Local projected vector metrics for footprints, height proxies, roads, and D/H.", executable=True),
                _backend("mcp_calculate_density", "mcp_tool", "calculate_density", "UrbanAgent MCP density wrapper.", executable=True),
                _backend("grasshopper_metrics", "parametric_design", "grasshopper", "Parametric morphology metrics."),
            ],
            constraints=["Requires projected CRS for area and grid-size metrics."],
            mcp_tool="calculate_density",
        ),
        CapabilitySpec(
            name="function_mix_entropy",
            title="Function Mix Entropy",
            family="method",
            capability_type="land_use_function_method",
            summary="Compute Shannon entropy and dominant-share diagnostics from POI or building-function labels.",
            inputs=["poi_or_function_layer", "function_counts"],
            outputs=["function_entropy", "function_entropy_normalized", "dominant_function_share", "commercial_share", "metric_rows"],
            tags=["poi", "function", "land use", "entropy", "mixed use", "commercial", "building function"],
            backends=[
                _backend("pandas_geopandas_entropy", "python_function", "urban_agent.tools.geo_tools:compute_function_mix_entropy", "Local entropy computation from function counts or labeled GeoDataFrame.", executable=True),
            ],
            constraints=["Function labels inherit source/model uncertainty and should be reported with provenance."],
        ),
        CapabilitySpec(
            name="streetview_visual_consistency",
            title="Street-view Visual Consistency",
            family="method",
            capability_type="streetview_visual_method",
            summary="Compute transparent visual-consistency proxies from street-view image color histograms and palette distances.",
            inputs=["streetview_image_directory", "streetview_points"],
            outputs=["style_consistency_score", "traditional_palette_match_score", "traditional_palette_delta_e", "metric_rows"],
            tags=["streetview", "image", "style", "visual", "facade", "color", "palette", "heritage"],
            backends=[
                _backend("pillow_numpy_histograms", "python_function", "urban_agent.tools.geo_tools:compute_streetview_visual_consistency", "Local Pillow/NumPy color histogram and palette-distance proxy.", executable=True),
            ],
            constraints=["Color histogram consistency is a transparent proxy; material/signboard claims require VLM or manual labels."],
        ),
        CapabilitySpec(
            name="streetview_semantic_segmentation",
            title="Street-view Semantic Segmentation",
            family="method",
            capability_type="streetview_semantic_method",
            summary="Generate auditable street-view semantic proxy masks, per-image intermediate tables, and mask panels for streetscape assessment.",
            inputs=["streetview_image_directory", "streetview_points", "sample_limit"],
            outputs=["semantic_mask_panel", "per_image_semantic_csv", "semantic_metric_rows", "manifest"],
            tags=["streetview", "semantic segmentation", "image", "facade", "sky", "vegetation", "road", "signage", "mask"],
            backends=[
                _backend("traditional_proxy_masks", "python_function", "urban_agent.tools.advanced_visual_tools:compute_streetview_semantic_segmentation", "Deterministic color/position proxy masks with reviewable intermediate artifacts.", executable=True),
                _backend("trained_segmentation_model", "python_library", "mmsegmentation/segformer", "Optional trained semantic segmentation backend when installed."),
            ],
            constraints=["Proxy masks are intermediate evidence; trained segmentation or manual/MLLM review is required for strong semantic claims."],
        ),
        CapabilitySpec(
            name="streetview_mllm_evaluation",
            title="Street-view MLLM Evaluation Pack",
            family="method",
            capability_type="streetview_mllm_method",
            summary="Prepare auditable image prompt packs for MLLM-based facade, signage, vegetation, and pedestrian-realm assessment.",
            inputs=["streetview_image_directory", "evaluation_schema", "sample_limit"],
            outputs=["mllm_request_jsonl", "evaluation_manifest", "expected_response_schema"],
            tags=["streetview", "mllm", "vlm", "image", "facade", "signage", "visual evidence", "evaluation"],
            backends=[
                _backend("mllm_prompt_pack", "python_function", "urban_agent.tools.advanced_visual_tools:prepare_streetview_mllm_evaluation", "Prepare local image request pack without calling remote models.", executable=True),
                _backend("multimodal_llm", "model_endpoint", "configured_vlm_client", "Optional configured MLLM/VLM evaluator; must record model and data policy."),
            ],
            constraints=["Remote MLLM calls must explicitly record endpoint, model, data policy, and per-image JSON responses."],
        ),
        CapabilitySpec(
            name="spatial_overlay_export",
            title="Spatial Overlay and GeoJSON Export",
            family="action",
            capability_type="gis_interchange_method",
            summary="Package spatial features into interoperable GeoJSON outputs for GIS and web tools.",
            inputs=["features", "crs"],
            outputs=["geojson", "feature_count"],
            tags=["geojson", "overlay", "export", "interoperability", "gis", "qgis", "arcgis"],
            backends=[
                _backend("mcp_export_geojson", "mcp_tool", "export_geojson", "UrbanAgent MCP GeoJSON exporter.", executable=True),
                _backend("geopandas", "python_library", "geopandas", "GeoDataFrame export."),
                _backend("arcgis_feature_layer", "enterprise_gis", "arcgis", "ArcGIS hosted feature layer publishing."),
            ],
            mcp_tool="export_geojson",
        ),
        CapabilitySpec(
            name="cartographic_svg_overlay",
            title="Cartographic SVG Overlay",
            family="action",
            capability_type="visualization_method",
            summary="Generate lightweight SVG spatial overlays for inspection previews, not formal GIS evidence maps.",
            inputs=["base_features", "interventions", "bbox", "width"],
            outputs=["svg_content", "format", "size"],
            tags=["svg", "map", "visualization", "cartography", "figure", "overlay"],
            backends=[
                _backend("urbanagent_svg", "mcp_tool", "generate_svg_overlay", "UrbanAgent SVG visualizer.", executable=True),
                _backend("qgis_layout", "desktop_gis", "qgis", "QGIS layout export for high-fidelity maps."),
            ],
            constraints=["Requires bbox and feature geometries in a consistent coordinate frame."],
            mcp_tool="generate_svg_overlay",
        ),
        CapabilitySpec(
            name="urban_data_source_discovery",
            title="Urban Data Source Discovery",
            family="data",
            capability_type="data_grounding_method",
            summary="Discover, classify, and describe available local urban data sources before analysis.",
            inputs=["task_payload", "resource_catalog", "paths"],
            outputs=["paths", "resources", "bbox", "crs", "governance", "temporal"],
            tags=["data", "source", "discovery", "grounding", "paths", "resource catalog", "evidence"],
            backends=[
                _backend("file_tree_discovery", "python_function", "urban_agent.tools.geo_small_tools:discover_urban_data_sources_tool", "Folder-tree and payload-based source discovery.", executable=True),
            ],
            constraints=["Discovery does not certify data sufficiency; pair it with source extent diagnostics for context-buffer workflows."],
        ),
        CapabilitySpec(
            name="aoi_context_buffer",
            title="AOI Context Buffer Construction",
            family="method",
            capability_type="spatial_diagnostic_method",
            summary="Build an AOI-centered context buffer and report metric buffer diagnostics without exporting a full map.",
            inputs=["aoi_boundary", "context_buffer_width_factor", "context_buffer_height_factor"],
            outputs=["context_buffer_layer", "context_buffer_diagnostics"],
            tags=["aoi", "context", "buffer", "diagnostics", "scale"],
            backends=[
                _backend("geopandas_context_buffer", "python_function", "urban_agent.tools.geo_small_tools:build_aoi_context_buffer_tool", "Build context buffer diagnostics from a boundary layer.", executable=True),
            ],
            constraints=["Policy memory decides required factors and thresholds; the tool only computes diagnostics."],
        ),
        CapabilitySpec(
            name="spatial_source_diagnostics",
            title="Spatial Source Extent Diagnostics",
            family="method",
            capability_type="spatial_diagnostic_method",
            summary="Compare source layer extents with AOI and context buffer extents in a shared metric CRS.",
            inputs=["aoi_boundary", "roads", "buildings", "context_buffer"],
            outputs=["alignment_diagnostics", "source_to_context_width_ratio", "source_to_context_height_ratio"],
            tags=["source", "extent", "coverage", "buffer", "pre-clipped", "osm", "diagnostics"],
            backends=[
                _backend("geopandas_extent_diagnostics", "python_function", "urban_agent.tools.geo_small_tools:validate_source_extent_against_context", "Compute policy-ready source-vs-context diagnostics.", executable=True),
            ],
            constraints=["Threshold interpretation belongs to policy memory and ReviewHub, not the tool."],
        ),
        CapabilitySpec(
            name="gis_layer_stack_export",
            title="GIS Layer Stack Export",
            family="action",
            capability_type="formal_gis_visualization_method",
            summary="Export AOI-clipped analysis layers, AOI-centered 3x context-buffer layers, spatialized metric/result layers, projected map PNG/PDF, metric charts, and visual-evidence grids.",
            inputs=["aoi_boundary", "roads", "buildings", "function_layers", "metric_rows", "artifact_dir"],
            outputs=["gpkg", "context_buffer_layer", "context_layer_stack", "metric_result_layers", "map_png", "map_pdf", "metric_csv", "chart_png", "streetview_grid_png"],
            tags=["gis", "gpkg", "geopackage", "map", "buffer", "context", "metric result", "png", "pdf", "chart", "qgis", "cartography", "figure"],
            backends=[
                _backend("geopandas_matplotlib_bundle", "python_function", "urban_agent.tools.geo_tools:build_gis_artifact_bundle", "Local GeoPandas/Matplotlib formal GIS artifact bundle.", executable=True),
            ],
            constraints=["Formal figures should use projected CRS, keep the AOI centered inside a 3x-by-3x context frame when a boundary is available, and preserve computed metric/result layers for GIS review."],
        ),
        CapabilitySpec(
            name="qgis_project_and_render",
            title="QGIS Project Generation and Render",
            family="action",
            capability_type="qgis_integration_method",
            summary="Generate a QGIS API-written project from GPKG layers, apply symbology, validate layer loading, and optionally launch QGIS GUI.",
            inputs=["gpkg_path", "output_dir", "legend"],
            outputs=["qgis_project", "layer_diagnostics", "qgis_launch_status"],
            tags=["qgis", "qgs", "map", "render", "print layout", "symbology", "geopackage"],
            backends=[
                _backend("qgis_api_project", "python_function", "urban_agent.tools.qgis_tools:build_gis_artifact_bundle_with_qgis", "QGIS bundled Python API project writer with layer validation.", executable=True),
                _backend("qgis_project_writer", "python_function", "urban_agent.tools.qgis_project_gen:build_qgis_project_capability", "QGIS API project generator with pure-XML fallback.", executable=True),
            ],
            constraints=["Requires QGIS 3.x installed for the validated project writer.", "Generated .qgz can be opened in QGIS Desktop for interactive review."],
        ),
        CapabilitySpec(
            name="urban_3d_scene_generation",
            title="Urban 3D Scene Generation",
            family="action",
            capability_type="three_dimensional_visualization_method",
            summary="Build extrusion-ready building layers and manifests for QGIS 3D Map View and Rhino/Grasshopper scenario modeling.",
            inputs=["building_footprints", "height_or_levels", "aoi_boundary", "artifact_dir"],
            outputs=["urban_3d_gpkg", "grasshopper_input_json", "urban_3d_manifest"],
            tags=["3d", "三维", "qgis 3d", "extrusion", "height", "rhino", "grasshopper", "building"],
            backends=[
                _backend("building_extrusion_package", "python_function", "urban_agent.tools.advanced_visual_tools:build_urban_3d_scene_package", "Local 3D extrusion package for QGIS and Grasshopper.", executable=True),
                _backend("qgis_3d_map_view", "desktop_gis", "qgis", "QGIS 3D Map View inspection using extrusion height fields."),
            ],
            constraints=["Height fields must report whether values are direct, levels-derived, or defaults."],
        ),
        CapabilitySpec(
            name="rhino_grasshopper_bridge",
            title="Rhino-Grasshopper Local Bridge",
            family="action",
            capability_type="parametric_modeling_bridge",
            summary="Probe or launch local Rhino/Grasshopper workflows with proxy-free local environment settings.",
            inputs=["grasshopper_input_json", "launch_rhino"],
            outputs=["rhino_executables", "compute_executables", "network_policy", "launch_status"],
            tags=["rhino", "grasshopper", "parametric", "3d", "local", "no proxy", "compute"],
            backends=[
                _backend("local_rhino_probe", "python_function", "urban_agent.tools.advanced_visual_tools:probe_rhino_grasshopper_environment", "Probe Rhino/Grasshopper locally and clear proxy vars if launching.", executable=True),
            ],
            constraints=["Do not use proxy/VPN for local Rhino or Grasshopper startup; remote compute endpoints require explicit configuration."],
        ),
        CapabilitySpec(
            name="spatial_topology_construction",
            title="Spatial Topology Construction",
            family="method",
            capability_type="dual_space_method",
            summary="Build topology relations from vector features for dual-space spatial reasoning.",
            inputs=["features", "relation_threshold"],
            outputs=["topology_graph", "relations"],
            tags=["topology", "dual-space", "graph", "spatial relation", "cognition"],
            backends=[
                _backend("urbanagent_cognition", "mcp_tool", "build_topology", "UrbanAgent cognition topology builder.", executable=True),
                _backend("networkx_shapely", "python_library", "networkx+shapely", "Local topology graph construction."),
            ],
            constraints=["Threshold choice should match scale and CRS units."],
            mcp_tool="build_topology",
        ),
        CapabilitySpec(
            name="parametric_urban_design",
            title="Parametric Urban Design",
            family="method",
            capability_type="design_generation_method",
            summary="Run Rhino/Grasshopper workflows for geometry generation and scenario metrics.",
            inputs=["definition_path", "input_values", "pointer"],
            outputs=["geometry", "metrics", "design_options"],
            tags=["rhino", "grasshopper", "parametric", "design", "geometry", "scenario"],
            backends=[
                _backend("local_rhino_grasshopper_probe", "python_function", "urban_agent.tools.advanced_visual_tools:probe_rhino_grasshopper_environment", "Local Rhino/Grasshopper availability probe with no proxy startup policy.", executable=True),
                _backend("rhino_compute", "mcp_tool", "evaluate_grasshopper_definition", "Rhino.Compute Grasshopper definition execution.", executable=True, requires=["RHINO_COMPUTE_URL"]),
                _backend("grasshopper_hops", "mcp_tool", "call_grasshopper_hops", "Grasshopper Hops HTTP endpoint.", executable=True),
            ],
            constraints=["Requires Rhino.Compute or Hops service for live execution."],
            mcp_tool="evaluate_grasshopper_definition",
        ),
        CapabilitySpec(
            name="urban_ml_modeling",
            title="Urban ML/DL Modeling",
            family="method",
            capability_type="machine_learning_method",
            summary="Train or apply ML/DL models for land use, mobility, population, and spatial prediction tasks.",
            inputs=["feature_table", "labels_or_targets", "model_config"],
            outputs=["predictions", "metrics", "model_artifact", "feature_importance"],
            tags=["machine learning", "deep learning", "sklearn", "pytorch", "xgboost", "gnn", "prediction", "classification"],
            backends=[
                _backend("scikit_learn", "python_library", "sklearn", "Classical ML estimators and pipelines."),
                _backend("pytorch", "python_library", "torch", "Neural models and graph neural networks."),
                _backend("custom_python", "python_module", "urban_agent.adapters", "Project-specific model adapters."),
            ],
            constraints=["Training requires explicit target definition, validation split, and leakage checks."],
        ),
    ]


def _tokenize(text: str) -> List[str]:
    lowered = text.lower()
    tokens = re.findall(r"[a-z0-9_\-]+|[\u4e00-\u9fff]+", lowered)
    expanded: List[str] = []
    aliases = {
        "步行": ["walkability", "accessibility"],
        "可达性": ["accessibility"],
        "步行可达性": ["walkability", "accessibility"],
        "连通": ["connectivity", "network"],
        "街道网络": ["connectivity", "network"],
        "开放空间": ["amenity", "service", "accessibility", "map"],
        "土地利用": ["land use", "classification", "machine learning"],
        "密度": ["density"],
        "形态": ["morphology"],
        "模型": ["model", "machine learning"],
        "训练": ["train", "machine learning", "deep learning"],
        "机器学习": ["machine learning", "sklearn"],
        "深度学习": ["deep learning", "pytorch"],
        "草蜢": ["grasshopper"],
        "参数化": ["parametric", "grasshopper"],
        "制图": ["cartography", "svg", "map"],
        "地图": ["map", "visualization", "gis", "gpkg"],
        "gis": ["gis", "geopackage", "map"],
        "叠加": ["overlay", "gis", "map"],
        "图层": ["layer", "gis", "geopackage"],
        "风貌": ["style", "visual", "heritage", "streetview", "morphology"],
        "街景": ["streetview", "image", "visual", "style"],
        "街景语义": ["streetview", "semantic segmentation", "image", "facade"],
        "语义分割": ["semantic segmentation", "mask", "image"],
        "图像分割": ["semantic segmentation", "mask", "image"],
        "多模态": ["mllm", "vlm", "image", "evaluation"],
        "视觉语言": ["mllm", "vlm", "image", "evaluation"],
        "三维": ["3d", "extrusion", "height", "qgis 3d", "rhino", "grasshopper"],
        "3维": ["3d", "extrusion", "height", "qgis 3d", "rhino", "grasshopper"],
        "3d": ["3d", "extrusion", "qgis 3d", "rhino", "grasshopper"],
        "rhino": ["rhino", "grasshopper", "parametric", "3d"],
        "grasshopper": ["rhino", "grasshopper", "parametric", "3d"],
        "草图大师": ["3d", "parametric"],
        "功能熵": ["function", "entropy", "land use", "poi"],
        "功能混合": ["function", "entropy", "mixed use", "poi"],
        "高度": ["height", "morphology", "building"],
        "建筑轮廓": ["footprint", "building", "morphology"],
        "协调度": ["style", "visual", "morphology", "function"],
    }
    for token in tokens:
        expanded.append(token)
        expanded.extend(aliases.get(token, []))
    for phrase, phrase_aliases in aliases.items():
        if phrase in lowered and phrase not in expanded:
            expanded.append(phrase)
            expanded.extend(phrase_aliases)
    return [token.strip().lower() for token in expanded if token.strip()]


def _filter_contextual_false_positives(text: str, selected: List[CapabilitySpec]) -> List[CapabilitySpec]:
    lowered = text.lower()
    filtered: List[CapabilitySpec] = []
    for capability in selected:
        if capability.name == "urban_ml_modeling" and not _requests_ml_execution(lowered):
            continue
        filtered.append(capability)
    return filtered


def _requests_ml_execution(lowered_text: str) -> bool:
    execution_markers = [
        "train",
        "fit model",
        "model training",
        "classification model",
        "prediction model",
        "pytorch",
        "sklearn",
        "xgboost",
        "random forest",
        "训练",
        "分类模型",
        "预测模型",
        "机器学习模型",
        "深度学习模型",
    ]
    return any(marker in lowered_text for marker in execution_markers)

