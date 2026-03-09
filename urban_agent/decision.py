"""
Spatial Decision: 空间决策层
基于认知结果生成空间决策建议，并提供测量工具评估效果

与MCP工具集成：
- 使用MCP工具获取实时数据
- 通过MCP协议调用外部分析服务
- 将决策结果通过MCP输出到其他系统
"""

from typing import Dict, List, Tuple, Any, Optional
import json
from shapely.geometry import Point, LineString, Polygon, box
from shapely.ops import unary_union
import numpy as np


class InterventionProposal:
    """干预提案：表示一个空间设计建议"""
    def __init__(self, proposal_id: str, intervention_type: str):
        self.id = proposal_id
        self.type = intervention_type  # 'node', 'path', 'zone', 'barrier_removal'
        self.description = ""
        self.topological_target: Optional[str] = None  # 目标拓扑节点
        self.vector_geometry: Optional[Any] = None  # 矢量几何
        self.expected_impact: Dict[str, float] = {}
        self.measurements: Dict[str, Any] = {}
        
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'type': self.type,
            'description': self.description,
            'topological_target': self.topological_target,
            'geometry_type': type(self.vector_geometry).__name__ if self.vector_geometry else None,
            'expected_impact': self.expected_impact,
            'measurements': self.measurements
        }


class SpatialMeasurement:
    """空间测量工具集：用于量化评估空间特征和干预效果"""
    
    @staticmethod
    def measure_connectivity(graph_nodes: Dict, graph_relations: List) -> Dict:
        """测量连通性指标"""
        if not graph_nodes:
            return {'global_connectivity': 0, 'local_connectivity': 0}
        
        # 计算全局连通性（平均连接数）
        # 节点可能是对象或dict
        connection_counts = []
        for node in graph_nodes.values():
            if hasattr(node, 'connections'):
                connection_counts.append(len(node.connections))
            elif isinstance(node, dict):
                connection_counts.append(len(node.get('connections', [])))
            else:
                connection_counts.append(0)
        
        global_conn = np.mean(connection_counts) if connection_counts else 0
        
        # 计算局部连通性（变异系数）
        local_conn = np.std(connection_counts) / (np.mean(connection_counts) + 1e-10) if np.mean(connection_counts) > 0 else 0
        
        return {
            'global_connectivity': float(global_conn),
            'local_connectivity': float(local_conn),
            'max_degree': max(connection_counts) if connection_counts else 0,
            'isolated_nodes': sum(1 for c in connection_counts if c == 0)
        }
    
    @staticmethod
    def measure_accessibility(buildings_gdf, target_points: List[Tuple], max_dist: float = 500) -> Dict:
        """测量可达性：建筑到目标点的距离分布"""
        if buildings_gdf is None or len(buildings_gdf) == 0 or not target_points:
            return {'average_distance': 0, 'coverage_ratio': 0}
        
        building_centroids = buildings_gdf.centroid
        distances = []
        
        for centroid in building_centroids:
            min_dist = min(
                np.sqrt((centroid.x - tx)**2 + (centroid.y - ty)**2)
                for tx, ty in target_points
            )
            distances.append(min_dist)
        
        distances = np.array(distances)
        
        return {
            'average_distance': float(np.mean(distances)),
            'median_distance': float(np.median(distances)),
            'max_distance': float(np.max(distances)),
            'coverage_ratio': float(np.mean(distances < max_dist)),  # 在max_dist范围内的建筑比例
            'within_100m': float(np.mean(distances < 100)),
            'within_300m': float(np.mean(distances < 300))
        }
    
    @staticmethod
    def measure_density_distribution(buildings_gdf, grid_size: float = 100) -> Dict:
        """测量密度分布：将区域划分为网格计算密度"""
        if buildings_gdf is None or len(buildings_gdf) == 0:
            return {'uniformity': 0, 'hotspots': []}
        
        bounds = buildings_gdf.total_bounds
        minx, miny, maxx, maxy = bounds
        
        # 创建网格
        x_cells = int((maxx - minx) / grid_size) + 1
        y_cells = int((maxy - miny) / grid_size) + 1
        
        density_grid = np.zeros((y_cells, x_cells))
        
        # 计算每个网格的建筑面积
        for _, building in buildings_gdf.iterrows():
            centroid = building.geometry.centroid
            bx = int((centroid.x - minx) / grid_size)
            by = int((centroid.y - miny) / grid_size)
            
            if 0 <= bx < x_cells and 0 <= by < y_cells:
                density_grid[by, bx] += building.geometry.area
        
        # 归一化
        density_grid = density_grid / (grid_size * grid_size)
        
        # 识别热点（密度高于平均值的网格）
        mean_density = np.mean(density_grid)
        hotspots = []
        for y in range(y_cells):
            for x in range(x_cells):
                if density_grid[y, x] > mean_density * 1.5:
                    hotspots.append({
                        'grid_x': x,
                        'grid_y': y,
                        'density': float(density_grid[y, x]),
                        'center': (minx + x * grid_size + grid_size/2, 
                                  miny + y * grid_size + grid_size/2)
                    })
        
        # 计算均匀性（变异系数的倒数）
        uniformity = 1 / (np.std(density_grid) / (np.mean(density_grid) + 1e-10) + 1)
        
        return {
            'uniformity': float(uniformity),
            'mean_density': float(mean_density),
            'max_density': float(np.max(density_grid)),
            'hotspots': hotspots[:10]  # 最多返回10个热点
        }
    
    @staticmethod
    def measure_walkability(roads_gdf, pois: Dict) -> Dict:
        """测量步行友好性"""
        if roads_gdf is None or len(roads_gdf) == 0:
            return {'intersection_density': 0, 'poi_accessibility': 0}
        
        # 交叉口密度
        bounds = roads_gdf.total_bounds
        area = (bounds[2] - bounds[0]) * (bounds[3] - bounds[1]) / 1e6  # km²
        
        # 估算交叉口数量（基于道路端点）
        endpoints = set()
        for geom in roads_gdf.geometry:
            if hasattr(geom, 'coords'):
                coords = list(geom.coords)
                if len(coords) >= 2:
                    endpoints.add((coords[0][0], coords[0][1]))
                    endpoints.add((coords[-1][0], coords[-1][1]))
        
        intersection_density = len(endpoints) / area if area > 0 else 0
        
        # POI可达性（简化计算：POI数量/面积）
        total_pois = sum(len(poi_list) for poi_list in pois.values())
        poi_density = total_pois / area if area > 0 else 0
        
        return {
            'intersection_density': float(intersection_density),
            'poi_density': float(poi_density),
            'total_endpoints': len(endpoints),
            'walkability_score': min(1.0, (intersection_density / 100) * 0.5 + (poi_density / 50) * 0.5)
        }
    
    @staticmethod
    def measure_visual_integration(buildings_gdf, open_spaces: List[Dict]) -> Dict:
        """测量视觉整合度（开放空间与建筑的视觉关系）"""
        if buildings_gdf is None or len(buildings_gdf) == 0:
            return {'visual_exposure': 0, 'enclosure_ratio': 0}
        
        # 计算建筑总周长
        total_perimeter = sum(b.geometry.length for _, b in buildings_gdf.iterrows())
        
        # 估算面向开放空间的建筑立面
        exposed_perimeter = total_perimeter * 0.3  # 简化：假设30%的立面面向公共空间
        
        # 围合度（建筑周长与开放空间周长的比值）
        open_space_perimeter = sum(
            np.sqrt(space['area']) * 4 if 'area' in space else 0
            for space in open_spaces
        )
        
        enclosure_ratio = (exposed_perimeter / open_space_perimeter 
                          if open_space_perimeter > 0 else 0)
        
        return {
            'visual_exposure': float(exposed_perimeter),
            'enclosure_ratio': float(min(1.0, enclosure_ratio)),
            'building_perimeter': float(total_perimeter)
        }


class SpatialDecision:
    """
    空间决策模块：基于认知结果生成设计方案
    
    功能：
    1. 分析认知结果，识别设计机会
    2. 生成干预提案
    3. 使用测量工具评估提案效果
    4. 选择最优方案
    """
    
    def __init__(self, llm_client=None):
        self.llm = llm_client
        self.measurement = SpatialMeasurement()
    
    def decide(self, context, task: str) -> Dict:
        """
        执行空间决策流程
        
        Args:
            context: 空间上下文（包含认知结果）
            task: 任务描述
            
        Returns:
            包含设计方案和干预区域的决策结果
        """
        print("  → Analyzing spatial opportunities...")
        opportunities = self._identify_opportunities(context)
        
        print("  → Generating intervention proposals...")
        proposals = self._generate_proposals(opportunities, context, task)
        
        print("  → Measuring baseline conditions...")
        baseline = self._measure_baseline(context)
        
        print("  → Evaluating proposal impacts...")
        evaluated_proposals = self._evaluate_proposals(proposals, baseline, context)
        
        print("  → Selecting optimal interventions...")
        selected = self._select_interventions(evaluated_proposals, task)
        
        return {
            'proposals': [p.to_dict() for p in evaluated_proposals],
            'selected_interventions': [s.to_dict() for s in selected],
            'baseline_measurements': baseline,
            'intervention_areas': self._extract_intervention_geometries(selected)
        }
    
    def _identify_opportunities(self, context) -> List[Dict]:
        """识别空间设计机会"""
        opportunities = []
        understanding = context.spatial_understanding
        
        # 分析拓扑图识别机会
        topo_graph = understanding.get('topological_graph', {})
        nodes = topo_graph.get('nodes', {})
        
        # 机会1: 孤立节点（需要连接）
        for node_id, node in nodes.items():
            if len(node.get('connections', [])) == 0:
                opportunities.append({
                    'type': 'connectivity_gap',
                    'target': node_id,
                    'description': f'孤立节点 {node_id} 需要增加连接',
                    'priority': 'high'
                })
        
        # 机会2: 高密度区域（需要开放空间）
        for node_id, node in nodes.items():
            if node.get('type') == 'cluster':
                density = node.get('properties', {}).get('density', 0)
                if density > 0.7:
                    opportunities.append({
                        'type': 'open_space_needed',
                        'target': node_id,
                        'description': f'高密度区域 {node_id} 需要开放空间',
                        'priority': 'medium'
                    })
        
        # 机会3: 主要交叉口（可强化为活动节点）
        for node_id, node in nodes.items():
            if node.get('type') == 'junction':
                degree = node.get('properties', {}).get('degree', 0)
                if degree >= 4:
                    opportunities.append({
                        'type': 'activity_node_potential',
                        'target': node_id,
                        'description': f'主要交叉口 {node_id} 可发展为活动节点',
                        'priority': 'medium'
                    })
        
        return opportunities
    
    def _generate_proposals(self, opportunities: List[Dict], context, task: str) -> List[InterventionProposal]:
        """生成干预提案"""
        proposals = []
        
        for i, opp in enumerate(opportunities[:5]):  # 最多处理5个机会
            proposal = InterventionProposal(
                proposal_id=f"proposal_{i}",
                intervention_type=opp['type']
            )
            proposal.description = opp['description']
            proposal.topological_target = opp['target']
            
            # 根据机会类型生成具体几何
            if opp['type'] == 'connectivity_gap':
                proposal = self._design_connection(proposal, opp, context)
            elif opp['type'] == 'open_space_needed':
                proposal = self._design_open_space(proposal, opp, context)
            elif opp['type'] == 'activity_node_potential':
                proposal = self._design_activity_node(proposal, opp, context)
            
            proposals.append(proposal)
        
        return proposals
    
    def _design_connection(self, proposal: InterventionProposal, opportunity: Dict, context) -> InterventionProposal:
        """设计连接方案"""
        # 找到最近的连接节点
        target_id = opportunity['target']
        topo_graph = context.spatial_understanding.get('topological_graph', {})
        nodes = topo_graph.get('nodes', {})
        
        target_node = nodes.get(target_id, {})
        target_coords = target_node.get('vector_anchor')
        
        if target_coords:
            # 创建一条连接到最近节点的路径
            # 简化：创建一条短路径
            proposal.vector_geometry = LineString([
                target_coords,
                (target_coords[0] + 50, target_coords[1] + 50)  # 简化连接
            ])
            proposal.expected_impact = {
                'connectivity_improvement': 0.3,
                'accessibility_improvement': 0.2
            }
        
        return proposal
    
    def _design_open_space(self, proposal: InterventionProposal, opportunity: Dict, context) -> InterventionProposal:
        """设计开放空间方案"""
        target_id = opportunity['target']
        topo_graph = context.spatial_understanding.get('topological_graph', {})
        nodes = topo_graph.get('nodes', {})
        
        target_node = nodes.get(target_id, {})
        center = target_node.get('properties', {}).get('centroid')
        
        if center:
            # 创建一个矩形开放空间
            size = 30  # 30米
            proposal.vector_geometry = Polygon([
                (center[0] - size, center[1] - size),
                (center[0] + size, center[1] - size),
                (center[0] + size, center[1] + size),
                (center[0] - size, center[1] + size)
            ])
            proposal.expected_impact = {
                'open_space_added': size * size,
                'density_reduction': 0.1
            }
        
        return proposal
    
    def _design_activity_node(self, proposal: InterventionProposal, opportunity: Dict, context) -> InterventionProposal:
        """设计活动节点方案"""
        target_id = opportunity['target']
        topo_graph = context.spatial_understanding.get('topological_graph', {})
        nodes = topo_graph.get('nodes', {})
        
        target_node = nodes.get(target_id, {})
        center = target_node.get('vector_anchor')
        
        if center:
            # 创建一个圆形节点
            proposal.vector_geometry = Point(center).buffer(20)
            proposal.expected_impact = {
                'activity_potential': 0.8,
                'gathering_space': 1256  # 约40m半径圆的面积
            }
        
        return proposal
    
    def _measure_baseline(self, context) -> Dict:
        """测量基线条件"""
        features = context.raw_features
        
        measurements = {}
        
        # 测量连通性
        topo_graph = context.spatial_understanding.get('topological_graph', {})
        measurements['connectivity'] = self.measurement.measure_connectivity(
            topo_graph.get('nodes', {}),
            topo_graph.get('relations', [])
        )
        
        # 测量可达性
        buildings = features.get('_gdf_buildings')
        # 收集所有节点坐标作为目标点
        target_points = []
        for node in topo_graph.get('nodes', {}).values():
            anchor = node.get('vector_anchor')
            if anchor:
                target_points.append(anchor)
        
        measurements['accessibility'] = self.measurement.measure_accessibility(
            buildings, target_points
        )
        
        # 测量密度分布
        measurements['density'] = self.measurement.measure_density_distribution(buildings)
        
        # 测量步行友好性
        roads = features.get('_gdf_roads')
        pois = features.get('pois', {})
        measurements['walkability'] = self.measurement.measure_walkability(roads, pois)
        
        return measurements
    
    def _evaluate_proposals(self, proposals: List[InterventionProposal], 
                           baseline: Dict, context) -> List[InterventionProposal]:
        """评估提案效果"""
        for proposal in proposals:
            measurements = {}
            
            # 根据提案类型进行特定测量
            if proposal.type == 'connectivity_gap':
                measurements['connectivity_change'] = proposal.expected_impact.get('connectivity_improvement', 0)
            
            elif proposal.type == 'open_space_needed':
                measurements['open_space_area'] = proposal.expected_impact.get('open_space_added', 0)
                measurements['density_impact'] = proposal.expected_impact.get('density_reduction', 0)
            
            elif proposal.type == 'activity_node_potential':
                measurements['activity_potential'] = proposal.expected_impact.get('activity_potential', 0)
            
            # 通用测量：几何属性
            if proposal.vector_geometry:
                geom = proposal.vector_geometry
                measurements['geometry'] = {
                    'area': geom.area if hasattr(geom, 'area') else 0,
                    'length': geom.length if hasattr(geom, 'length') else 0,
                    'bounds': list(geom.bounds) if hasattr(geom, 'bounds') else []
                }
            
            proposal.measurements = measurements
        
        return proposals
    
    def _select_interventions(self, proposals: List[InterventionProposal], task: str) -> List[InterventionProposal]:
        """选择最优干预方案"""
        # 基于任务类型选择
        if 'connectivity' in task.lower():
            # 优先选择连通性改进
            scored = [(p, p.expected_impact.get('connectivity_improvement', 0)) for p in proposals]
        elif 'open space' in task.lower() or 'public' in task.lower():
            # 优先选择开放空间
            scored = [(p, p.expected_impact.get('open_space_added', 0)) for p in proposals]
        else:
            # 综合评分
            scored = []
            for p in proposals:
                score = sum(p.expected_impact.values())
                scored.append((p, score))
        
        # 排序并选择前3个
        scored.sort(key=lambda x: x[1], reverse=True)
        selected = [p for p, s in scored[:3]]
        
        return selected
    
    def _extract_intervention_geometries(self, interventions: List[InterventionProposal]) -> List[Dict]:
        """提取干预区域的几何信息用于可视化"""
        areas = []
        
        for intervention in interventions:
            if intervention.vector_geometry:
                geom = intervention.vector_geometry
                area_info = {
                    'id': intervention.id,
                    'type': intervention.type,
                    'description': intervention.description,
                    'geometry': self._geometry_to_dict(geom),
                    'target_node': intervention.topological_target
                }
                areas.append(area_info)
        
        return areas
    
    def _geometry_to_dict(self, geom) -> Dict:
        """将几何对象转换为字典"""
        if isinstance(geom, Point):
            return {
                'type': 'Point',
                'coordinates': [geom.x, geom.y]
            }
        elif isinstance(geom, LineString):
            return {
                'type': 'LineString',
                'coordinates': [[c[0], c[1]] for c in geom.coords]
            }
        elif isinstance(geom, Polygon):
            return {
                'type': 'Polygon',
                'coordinates': [[[c[0], c[1]] for c in geom.exterior.coords]]
            }
        else:
            return {'type': 'Unknown', 'coordinates': []}
