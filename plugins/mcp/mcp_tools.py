"""
MCP Tools Integration: MCP协议工具集成模块

提供与城市分析相关的MCP工具，支持：
1. 空间数据获取工具
2. 空间分析工具
3. 可视化输出工具
4. 外部服务调用工具
"""

from typing import Dict, List, Any, Optional, Callable, Sequence
import json
import math
from dataclasses import dataclass

from plugins.rhino.connectors import ConnectorRegistry, RhinoComputeConnector


@dataclass
class MCPTool:
    """MCP工具定义"""
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable


class UrbanMCPTools:
    """
    城市分析MCP工具集
    
    遵循MCP (Model Context Protocol) 协议规范，
    提供标准化的工具接口供智能体调用。
    """
    
    def __init__(
        self,
        *,
        include_rhino: bool = False,
        include_agent_tools: bool = False,
        include_hermes: bool = False,
        agent_toolsets: Optional[Sequence[str]] = None,
        tool_manifests: Optional[Sequence[str]] = None,
    ):
        self.tools: Dict[str, MCPTool] = {}
        self.connector_registry = ConnectorRegistry()
        if include_rhino:
            self._register_default_connectors()
        self._register_default_tools()
        if not include_rhino:
            for name in (
                "list_connectors",
                "rhino_health_check",
                "evaluate_grasshopper_definition",
                "call_grasshopper_hops",
                "invoke_rhino_compute",
            ):
                self.tools.pop(name, None)
        self.agent_runtime = None
        self.hermes_runtime = None
        if include_agent_tools or include_hermes:
            from urban_agent.tools.agent_toolkit import register_agent_core_tools, register_agent_tool_manifest

            self.agent_runtime = register_agent_core_tools(self.register_tool, toolsets=agent_toolsets)
            self.hermes_runtime = self.agent_runtime
            for manifest_path in tool_manifests or ():
                register_agent_tool_manifest(self.register_tool, manifest_path)

    def _register_default_connectors(self):
        self.connector_registry.register(
            RhinoComputeConnector(),
            capabilities=[
                "parametric_design",
                "grasshopper_evaluation",
                "geometry_generation",
            ],
            input_modalities=["vector_geometry", "parametric_schema", "json"],
            output_modalities=["geometry", "metrics", "design_options"],
            human_review_surfaces=["visual_preview", "parameter_adjustment"],
            metadata={
                "open_spec_version": "urban-agent-open-spec/v1",
                "adapter_role": "external_design_connector",
            },
        )
    
    def _register_default_tools(self):
        """注册默认工具集"""
        # 空间数据工具
        self.register_tool(
            name="fetch_osm_data",
            description="获取指定区域的OpenStreetMap数据",
            parameters={
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "地理位置名称或坐标"},
                    "radius": {"type": "number", "description": "搜索半径（米）", "default": 500},
                    "data_types": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["roads", "buildings", "pois", "landuse"]},
                        "description": "需要获取的数据类型"
                    }
                },
                "required": ["location"]
            },
            handler=self._handle_fetch_osm_data
        )
        
        # 空间分析工具
        self.register_tool(
            name="analyze_connectivity",
            description="分析区域的道路网络连通性",
            parameters={
                "type": "object",
                "properties": {
                    "road_graph": {"type": "object", "description": "道路网络图数据"}
                },
                "required": ["road_graph"]
            },
            handler=self._handle_analyze_connectivity
        )
        
        self.register_tool(
            name="measure_accessibility",
            description="测量从建筑到目标点的可达性",
            parameters={
                "type": "object",
                "properties": {
                    "buildings": {"type": "object", "description": "建筑数据"},
                    "target_points": {"type": "array", "items": {"type": "array"}, "description": "目标点坐标列表"},
                    "max_distance": {"type": "number", "description": "最大距离（米）", "default": 500}
                },
                "required": ["buildings", "target_points"]
            },
            handler=self._handle_measure_accessibility
        )
        
        self.register_tool(
            name="calculate_density",
            description="计算建筑密度分布",
            parameters={
                "type": "object",
                "properties": {
                    "buildings": {"type": "object", "description": "建筑数据"},
                    "grid_size": {"type": "number", "description": "网格大小（米）", "default": 100}
                },
                "required": ["buildings"]
            },
            handler=self._handle_calculate_density
        )
        
        # 可视化工具
        self.register_tool(
            name="generate_svg_overlay",
            description="生成SVG格式的空间干预可视化",
            parameters={
                "type": "object",
                "properties": {
                    "base_features": {"type": "object", "description": "底图特征数据"},
                    "interventions": {"type": "array", "description": "干预区域列表"},
                    "bbox": {"type": "array", "description": "边界框 [minx, miny, maxx, maxy]"},
                    "width": {"type": "number", "description": "SVG宽度", "default": 800}
                },
                "required": ["base_features", "interventions", "bbox"]
            },
            handler=self._handle_generate_svg
        )
        
        self.register_tool(
            name="export_geojson",
            description="导出GeoJSON格式的空间数据",
            parameters={
                "type": "object",
                "properties": {
                    "features": {"type": "array", "description": "空间特征列表"},
                    "crs": {"type": "string", "description": "坐标参考系"}
                },
                "required": ["features", "crs"]
            },
            handler=self._handle_export_geojson
        )
        
        # 拓扑分析工具
        self.register_tool(
            name="build_topology",
            description="从空间特征构建拓扑图",
            parameters={
                "type": "object",
                "properties": {
                    "features": {"type": "object", "description": "空间特征数据"},
                    "relation_threshold": {"type": "number", "description": "关系建立距离阈值（米）", "default": 100}
                },
                "required": ["features"]
            },
            handler=self._handle_build_topology
        )
        
        # 报告生成工具
        self.register_tool(
            name="generate_measurement_report",
            description="生成空间测量报告",
            parameters={
                "type": "object",
                "properties": {
                    "baseline": {"type": "object", "description": "基线测量数据"},
                    "proposals": {"type": "array", "description": "干预方案列表"}
                },
                "required": ["baseline", "proposals"]
            },
            handler=self._handle_generate_report
        )

        self.register_tool(
            name="rank_traffic_signal_phases",
            description="根据等待车辆数、总车辆数和车道数，对交通信号相位进行排序",
            parameters={
                "type": "object",
                "properties": {
                    "phase_options": {"type": "array", "description": "相位列表，每项包含 option/waiting_vehicle_count/vehicle_count/lane_count"}
                },
                "required": ["phase_options"]
            },
            handler=self._handle_rank_traffic_signal_phases
        )

        self.register_tool(
            name="select_exploration_target",
            description="从候选探索目标中选出综合 completion、average_step、success_time 最优项",
            parameters={
                "type": "object",
                "properties": {
                    "candidates": {"type": "array", "description": "候选目标列表"}
                },
                "required": ["candidates"]
            },
            handler=self._handle_select_exploration_target
        )

        self.register_tool(
            name="list_connectors",
            description="列出当前可用的外部连接器，如 Rhino.Compute、本地数据、API 连接器等",
            parameters={
                "type": "object",
                "properties": {}
            },
            handler=self._handle_list_connectors
        )

        self.register_tool(
            name="rhino_health_check",
            description="检查 Rhino.Compute 服务是否可达",
            parameters={
                "type": "object",
                "properties": {}
            },
            handler=self._handle_rhino_health_check
        )

        self.register_tool(
            name="evaluate_grasshopper_definition",
            description="通过 Rhino.Compute 执行 Grasshopper 定义文件 (.gh/.ghx)，返回计算结果",
            parameters={
                "type": "object",
                "properties": {
                    "definition_path": {"type": "string", "description": "Grasshopper 定义文件路径"},
                    "input_values": {"type": "object", "description": "输入参数字典"},
                    "pointer": {"type": "string", "description": "可选的组件指针/子图指针"}
                },
                "required": ["definition_path"]
            },
            handler=self._handle_evaluate_grasshopper_definition
        )

        self.register_tool(
            name="call_grasshopper_hops",
            description="调用 Grasshopper Hops HTTP 端点，适合远程参数化工作流编排",
            parameters={
                "type": "object",
                "properties": {
                    "endpoint": {"type": "string", "description": "Hops 端点 URL"},
                    "input_values": {"type": "object", "description": "输入参数字典"}
                },
                "required": ["endpoint"]
            },
            handler=self._handle_call_grasshopper_hops
        )

        self.register_tool(
            name="invoke_rhino_compute",
            description="调用 Rhino.Compute 任意 REST 端点，便于扩展几何构造、Brep 运算和参数化建模流程",
            parameters={
                "type": "object",
                "properties": {
                    "endpoint": {"type": "string", "description": "Rhino.Compute 端点，例如 /rhino/geometry/point3d/create"},
                    "arguments": {"type": "object", "description": "POST 请求体"}
                },
                "required": ["endpoint"]
            },
            handler=self._handle_invoke_rhino_compute
        )
    
    def register_tool(self, name: str, description: str, 
                     parameters: Dict, handler: Callable):
        """注册新工具"""
        self.tools[name] = MCPTool(
            name=name,
            description=description,
            parameters=parameters,
            handler=handler
        )
    
    def get_tool_definitions(self) -> List[Dict]:
        """获取所有工具定义（用于MCP协议）"""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters
            }
            for tool in self.tools.values()
        ]

    def get_openai_tool_definitions(self, names: Optional[List[str]] = None) -> List[Dict]:
        """Return MCP tools in OpenAI-compatible function-calling format."""
        selected = set(names or self.tools.keys())
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in self.tools.values()
            if tool.name in selected
        ]

    def get_tool_handler_map(self, names: Optional[List[str]] = None) -> Dict[str, Callable[..., str]]:
        """Return callable handlers suitable for LLM tool-call loops."""
        selected = set(names or self.tools.keys())
        handlers: Dict[str, Callable[..., str]] = {}
        for tool_name in selected:
            if tool_name not in self.tools:
                continue

            def _handler(_tool_name: str = tool_name, **kwargs: Any) -> str:
                return json.dumps(self.execute_tool(_tool_name, kwargs), ensure_ascii=False, default=str)

            handlers[tool_name] = _handler
        return handlers
    
    def execute_tool(self, tool_name: str, arguments: Dict) -> Dict:
        """
        执行指定工具
        
        Args:
            tool_name: 工具名称
            arguments: 工具参数
            
        Returns:
            工具执行结果
        """
        if tool_name not in self.tools:
            return {
                "success": False,
                "error": f"Tool '{tool_name}' not found"
            }
        
        tool = self.tools[tool_name]
        
        try:
            result = tool.handler(arguments)
            return {
                "success": True,
                "result": result
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    # ===== 工具处理器 =====
    
    def _handle_fetch_osm_data(self, args: Dict) -> Dict:
        """处理OSM数据获取"""
        import osmnx as ox
        
        location = args.get('location')
        radius = args.get('radius', 500)
        data_types = args.get('data_types', ['roads', 'buildings'])
        
        result = {}
        
        if 'roads' in data_types:
            graph = ox.graph_from_address(location, dist=radius, network_type='all')
            result['road_graph'] = graph
        
        if 'buildings' in data_types:
            buildings = ox.features_from_address(location, tags={"building": True}, dist=radius)
            result['buildings'] = buildings
        
        if 'pois' in data_types:
            pois = ox.features_from_address(
                location, 
                tags={"amenity": True, "shop": True}, 
                dist=radius
            )
            result['pois'] = pois
        
        return result
    
    def _handle_analyze_connectivity(self, args: Dict) -> Dict:
        """处理连通性分析"""
        import networkx as nx
        import numpy as np
        
        graph_data = args.get('road_graph')
        
        # 计算连通性指标
        degrees = [d for n, d in graph_data.degree()]
        
        return {
            'average_degree': float(np.mean(degrees)),
            'max_degree': max(degrees) if degrees else 0,
            'node_count': len(graph_data.nodes()),
            'edge_count': len(graph_data.edges()),
            'density': nx.density(graph_data)
        }
    
    def _handle_measure_accessibility(self, args: Dict) -> Dict:
        """处理可达性测量"""
        import numpy as np
        
        buildings = args.get('buildings')
        target_points = args.get('target_points', [])
        max_dist = args.get('max_distance', 500)
        
        centroids = buildings.centroid
        distances = []
        
        for centroid in centroids:
            min_dist = min(
                np.sqrt((centroid.x - tx)**2 + (centroid.y - ty)**2)
                for tx, ty in target_points
            )
            distances.append(min_dist)
        
        distances = np.array(distances)
        
        return {
            'average_distance': float(np.mean(distances)),
            'median_distance': float(np.median(distances)),
            'coverage_ratio': float(np.mean(distances < max_dist)),
            'within_100m': float(np.mean(distances < 100)),
            'within_300m': float(np.mean(distances < 300))
        }
    
    def _handle_calculate_density(self, args: Dict) -> Dict:
        """处理密度计算"""
        import numpy as np
        
        buildings = args.get('buildings')
        grid_size = args.get('grid_size', 100)
        
        bounds = buildings.total_bounds
        minx, miny, maxx, maxy = bounds
        
        x_cells = int((maxx - minx) / grid_size) + 1
        y_cells = int((maxy - miny) / grid_size) + 1
        
        density_grid = np.zeros((y_cells, x_cells))
        
        for _, building in buildings.iterrows():
            centroid = building.geometry.centroid
            bx = int((centroid.x - minx) / grid_size)
            by = int((centroid.y - miny) / grid_size)
            
            if 0 <= bx < x_cells and 0 <= by < y_cells:
                density_grid[by, bx] += building.geometry.area
        
        return {
            'grid_shape': (y_cells, x_cells),
            'mean_density': float(np.mean(density_grid)),
            'max_density': float(np.max(density_grid)),
            'uniformity': float(1 / (np.std(density_grid) / (np.mean(density_grid) + 1e-10) + 1))
        }
    
    def _handle_generate_svg(self, args: Dict) -> Dict:
        """处理SVG生成"""
        from legacy.urban_agent_legacy.visualization import SpatialVisualizer
        
        visualizer = SpatialVisualizer(svg_size=args.get('width', 800))
        
        svg_string = visualizer.create_svg_overlay(
            raw_features=args.get('base_features'),
            intervention_areas=args.get('interventions'),
            bbox=tuple(args.get('bbox'))
        )
        
        return {
            'svg_content': svg_string,
            'format': 'svg',
            'size': len(svg_string)
        }
    
    def _handle_export_geojson(self, args: Dict) -> Dict:
        """处理GeoJSON导出"""
        features = args.get('features', [])
        crs = args.get('crs', 'EPSG:4326')
        
        geojson = {
            'type': 'FeatureCollection',
            'crs': {
                'type': 'name',
                'properties': {'name': crs}
            },
            'features': features
        }
        
        return {
            'geojson': geojson,
            'feature_count': len(features)
        }
    
    def _handle_build_topology(self, args: Dict) -> Dict:
        """处理拓扑构建"""
        from legacy.urban_agent_legacy.cognition import SpatialCognition
        
        features = args.get('features')
        threshold = args.get('relation_threshold', 100)
        
        # 这里简化处理，实际应该调用完整的拓扑构建逻辑
        cognition = SpatialCognition()
        
        # 创建模拟的context对象
        class MockContext:
            def __init__(self, features):
                self.raw_features = features
        
        mock_context = MockContext(features)
        extracted = cognition._extract_features(mock_context)
        topo_graph = cognition._build_topology(extracted, mock_context)
        
        return topo_graph.to_dict()
    
    def _handle_generate_report(self, args: Dict) -> Dict:
        """处理报告生成"""
        from legacy.urban_agent_legacy.visualization import MeasurementReporter
        
        baseline = args.get('baseline', {})
        proposals = args.get('proposals', [])
        
        report = MeasurementReporter.generate_report(baseline, proposals)
        
        return {
            'report': report,
            'sections': ['baseline', 'proposals', 'measurements']
        }

    def _handle_rank_traffic_signal_phases(self, args: Dict) -> Dict:
        """给交通相位候选排序"""
        phase_options = args.get("phase_options", []) or []
        ranked = sorted(
            phase_options,
            key=lambda item: (
                -int(item.get("waiting_vehicle_count", 0)),
                -int(item.get("vehicle_count", 0)),
                -int(item.get("lane_count", 0)),
            )
        )
        best_option = ranked[0] if ranked else None
        return {
            "best_option": best_option,
            "ranked_options": ranked
        }

    def _handle_select_exploration_target(self, args: Dict) -> Dict:
        """从探索候选中选最优目标"""
        candidates = args.get("candidates", []) or []
        ranked = sorted(
            candidates,
            key=lambda item: (
                -float(item.get("completion", 0.0)),
                float(item.get("average_step", math.inf)),
                float(item.get("success_time", math.inf)),
            )
        )
        best = ranked[0] if ranked else None
        return {
            "best_candidate": best,
            "ranked_candidates": ranked,
        }

    def _get_rhino_connector(self) -> RhinoComputeConnector:
        connector = self.connector_registry.get("rhino_compute")
        if connector is None:
            raise RuntimeError("Rhino connector is not registered")
        return connector  # type: ignore[return-value]

    def _handle_list_connectors(self, args: Dict) -> Dict:
        return {
            "connectors": self.connector_registry.list_connectors(),
            "connector_specs": self.connector_registry.list_specs(),
        }

    def _handle_rhino_health_check(self, args: Dict) -> Dict:
        return self._get_rhino_connector().health_check()

    def _handle_evaluate_grasshopper_definition(self, args: Dict) -> Dict:
        return self._get_rhino_connector().execute("evaluate_definition", args)

    def _handle_call_grasshopper_hops(self, args: Dict) -> Dict:
        return self._get_rhino_connector().execute("call_hops", args)

    def _handle_invoke_rhino_compute(self, args: Dict) -> Dict:
        return self._get_rhino_connector().execute("rhino_command", args)


# 全局工具实例
mcp_tools = UrbanMCPTools()


def get_mcp_tools(
    *,
    include_rhino: bool = False,
    include_agent_tools: bool = False,
    include_hermes: bool = False,
    agent_toolsets: Optional[Sequence[str]] = None,
    tool_manifests: Optional[Sequence[str]] = None,
) -> UrbanMCPTools:
    """获取MCP工具实例"""
    if include_rhino or include_agent_tools or include_hermes or agent_toolsets or tool_manifests:
        return UrbanMCPTools(
            include_rhino=include_rhino,
            include_agent_tools=include_agent_tools,
            include_hermes=include_hermes,
            agent_toolsets=agent_toolsets,
            tool_manifests=tool_manifests,
        )
    return mcp_tools
