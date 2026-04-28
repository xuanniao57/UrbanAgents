"""
Spatial Cognition: 空间认知层
实现"先拓扑化再矢量对应"的空间理解框架

核心概念：
1. 拓扑空间 (Topological Space): 抽象的关系网络，关注连接性、邻接性、层次性
2. 矢量空间 (Vector Space): 具体的度量空间，关注坐标、距离、方向、形状
3. 映射关系: 拓扑结构 ↔ 矢量几何的双向转换
"""

from typing import Dict, List, Tuple, Any, Optional
import json
import networkx as nx
from shapely.geometry import Point, LineString, Polygon
from shapely.ops import nearest_points
import numpy as np


class TopologicalNode:
    """拓扑节点：表示空间中的功能区域或重要位置"""
    def __init__(self, node_id: str, node_type: str, semantic_label: str):
        self.id = node_id
        self.type = node_type  # 'junction', 'plaza', 'cluster', 'landmark', 'barrier'
        self.label = semantic_label
        self.connections: List[str] = []  # 连接的节点ID
        self.properties: Dict[str, Any] = {}
        self.vector_anchor: Optional[Tuple[float, float]] = None  # 对应的矢量坐标
        self.trace: List[Dict[str, Any]] = []

    def add_trace(self, step: str, explanation: str, evidence: Optional[Dict[str, Any]] = None):
        self.trace.append({
            'step': step,
            'explanation': explanation,
            'evidence': evidence or {}
        })
        
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'type': self.type,
            'label': self.label,
            'connections': self.connections,
            'properties': self.properties,
            'vector_anchor': self.vector_anchor,
            'trace': self.trace,
        }


class TopologicalRelation:
    """拓扑关系：表示节点间的空间关系"""
    def __init__(self, source: str, target: str, relation_type: str):
        self.source = source
        self.target = target
        self.type = relation_type  # 'adjacent', 'connected', 'contains', 'aligned', 'separated'
        self.properties: Dict[str, Any] = {}
        self.vector_geometry: Optional[Any] = None  # 对应的矢量几何
        self.trace: List[Dict[str, Any]] = []

    def add_trace(self, step: str, explanation: str, evidence: Optional[Dict[str, Any]] = None):
        self.trace.append({
            'step': step,
            'explanation': explanation,
            'evidence': evidence or {}
        })
        
    def to_dict(self) -> Dict:
        return {
            'source': self.source,
            'target': self.target,
            'type': self.type,
            'properties': self.properties,
            'has_vector_mapping': self.vector_geometry is not None,
            'trace': self.trace,
        }


class TopologicalGraph:
    """拓扑图：表示空间的抽象结构"""
    def __init__(self):
        self.nodes: Dict[str, TopologicalNode] = {}
        self.relations: List[TopologicalRelation] = []
        
    def add_node(self, node: TopologicalNode):
        self.nodes[node.id] = node
        
    def add_relation(self, relation: TopologicalRelation):
        self.relations.append(relation)
        # 更新节点的连接列表
        if relation.source in self.nodes:
            self.nodes[relation.source].connections.append(relation.target)
        if relation.target in self.nodes:
            self.nodes[relation.target].connections.append(relation.source)
    
    def to_dict(self) -> Dict:
        return {
            'nodes': {k: v.to_dict() for k, v in self.nodes.items()},
            'relations': [r.to_dict() for r in self.relations],
            'node_count': len(self.nodes),
            'relation_count': len(self.relations)
        }


class SpatialCognition:
    """
    空间认知模块：实现从原始数据到语义理解的转换
    
    处理流程：
    1. 特征提取 → 识别关键空间元素
    2. 拓扑构建 → 建立抽象关系网络
    3. 语义标注 → 赋予空间元素意义
    4. 矢量映射 → 将拓扑映射到真实坐标
    """
    
    def __init__(self, llm_client=None):
        self.llm = llm_client
        
    def understand(self, context, task: str) -> Dict:
        """
        执行空间认知流程
        
        Args:
            context: 空间上下文（包含感知层获取的原始数据）
            task: 任务描述
            
        Returns:
            包含拓扑图、语义理解、矢量映射的认知结果
        """
        print("  → Extracting spatial features...")
        features = self._extract_features(context)
        
        print("  → Building topological representation...")
        topo_graph = self._build_topology(features, context)
        
        print("  → Annotating semantic meaning...")
        semantics = self._annotate_semantics(topo_graph, context, task)
        
        print("  → Mapping to vector space...")
        vector_mapping = self._map_to_vector(topo_graph, context)

        spatial_patterns = self._identify_patterns(topo_graph, context)
        alignment_diagnostics = self._build_alignment_diagnostics(topo_graph, features, context, task)
        distribution_preview = self._build_distribution_preview(features)
        
        return {
            'topological_graph': topo_graph.to_dict(),
            'semantic_understanding': semantics,
            'vector_mapping': vector_mapping,
            'spatial_patterns': spatial_patterns,
            'key_findings': self._generate_findings(topo_graph, semantics, task),
            'alignment_diagnostics': alignment_diagnostics,
            'distribution_preview': distribution_preview,
            'inspection_payload': self._build_inspection_payload(
                topo_graph,
                alignment_diagnostics,
                distribution_preview,
                vector_mapping,
            ),
        }
    
    def _extract_features(self, context) -> Dict:
        """从原始数据中提取关键空间特征"""
        features = context.raw_features

        def _resolve(name: str, extractor):
            if name in features:
                return features.get(name) or []
            return extractor(features)
        
        extracted = {
            'junctions': _resolve('junctions', self._identify_junctions),
            'clusters': _resolve('clusters', self._identify_building_clusters),
            'corridors': _resolve('corridors', self._identify_corridors),
            'open_spaces': _resolve('open_spaces', self._identify_open_spaces),
            'barriers': _resolve('barriers', self._identify_barriers),
            'landmarks': _resolve('landmarks', self._identify_landmarks)
        }
        
        return extracted
    
    def _build_topology(self, features: Dict, context) -> TopologicalGraph:
        """构建拓扑图表示"""
        graph = TopologicalGraph()
        
        # 1. 添加节点
        # 交叉口节点
        for i, junction in enumerate(features['junctions']):
            node = TopologicalNode(
                node_id=f"junction_{i}",
                node_type="junction",
                semantic_label=f"Road junction {i}"
            )
            node.properties = {
                'degree': junction.get('degree', 0),
                'road_types': junction.get('road_types', []),
                'coordinates': junction.get('coordinates')
            }
            node.vector_anchor = junction.get('coordinates')
            node.add_trace(
                'feature_extraction',
                'Node created from a high-degree road intersection.',
                {
                    'degree': junction.get('degree', 0),
                    'coordinates': junction.get('coordinates'),
                }
            )
            graph.add_node(node)
        
        # 建筑聚类节点
        for i, cluster in enumerate(features['clusters']):
            node = TopologicalNode(
                node_id=f"cluster_{i}",
                node_type="cluster",
                semantic_label=f"Building cluster {i}"
            )
            node.properties = {
                'building_count': cluster.get('count', 0),
                'density': cluster.get('density', 0),
                'centroid': cluster.get('centroid'),
                'radius': cluster.get('radius', 80.0),
            }
            node.vector_anchor = cluster.get('centroid')
            node.add_trace(
                'feature_extraction',
                'Node created from a building cluster detected in perceived urban fabric.',
                {
                    'building_count': cluster.get('count', 0),
                    'density': cluster.get('density', 0),
                    'radius': cluster.get('radius', 80.0),
                }
            )
            graph.add_node(node)
        
        # 开放空间节点
        for i, space in enumerate(features['open_spaces']):
            node = TopologicalNode(
                node_id=f"openspace_{i}",
                node_type="plaza",
                semantic_label=f"Open space {i}"
            )
            node.properties = {
                'area': space.get('area', 0),
                'shape': space.get('shape_type', 'unknown'),
                'centroid': space.get('centroid')
            }
            node.vector_anchor = space.get('centroid')
            node.add_trace(
                'feature_extraction',
                'Node created from an open-space feature that may support gathering or visibility.',
                {
                    'area': space.get('area', 0),
                    'shape_type': space.get('shape_type', 'unknown'),
                }
            )
            graph.add_node(node)

        # 地标节点
        for i, landmark in enumerate(features['landmarks']):
            node = TopologicalNode(
                node_id=f"landmark_{i}",
                node_type="landmark",
                semantic_label=landmark.get('name', f"Landmark {i}")
            )
            coordinates = landmark.get('coordinates') or landmark.get('centroid')
            node.properties = {
                'category': landmark.get('type', 'landmark'),
                'importance': landmark.get('importance', 1.0),
                'coordinates': coordinates
            }
            node.vector_anchor = coordinates
            node.add_trace(
                'feature_extraction',
                'Node created from a salient landmark or named urban anchor.',
                {
                    'category': landmark.get('type', 'landmark'),
                    'importance': landmark.get('importance', 1.0),
                }
            )
            graph.add_node(node)

        # 屏障节点
        for i, barrier in enumerate(features['barriers']):
            node = TopologicalNode(
                node_id=f"barrier_{i}",
                node_type="barrier",
                semantic_label=barrier.get('description', f"Barrier {i}")
            )
            coordinates = barrier.get('coordinates') or barrier.get('centroid')
            node.properties = {
                'barrier_type': barrier.get('type', 'barrier'),
                'strength': barrier.get('strength', 1.0),
                'coordinates': coordinates
            }
            node.vector_anchor = coordinates
            node.add_trace(
                'feature_extraction',
                'Node created from a barrier-like feature that may interrupt movement or visibility.',
                {
                    'barrier_type': barrier.get('type', 'barrier'),
                    'strength': barrier.get('strength', 1.0),
                }
            )
            graph.add_node(node)
        
        # 2. 建立关系
        # 基于距离建立邻接关系
        nodes_list = list(graph.nodes.values())
        for i, node1 in enumerate(nodes_list):
            for node2 in nodes_list[i+1:]:
                if node1.vector_anchor and node2.vector_anchor:
                    dist = self._calculate_distance(
                        node1.vector_anchor, 
                        node2.vector_anchor
                    )
                    
                    # 根据距离和类型确定关系
                    relation_type = self._determine_relation_type(node1, node2, dist)
                    
                    if relation_type:
                        relation = TopologicalRelation(
                            source=node1.id,
                            target=node2.id,
                            relation_type=relation_type
                        )
                        relation.properties['distance'] = dist
                        relation.add_trace(
                            'relation_inference',
                            f"Relation inferred from node type combination and metric separation as {relation_type}.",
                            {
                                'distance': dist,
                                'source_type': node1.type,
                                'target_type': node2.type,
                                'source_anchor': node1.vector_anchor,
                                'target_anchor': node2.vector_anchor,
                            }
                        )
                        graph.add_relation(relation)
        
        return graph
    
    def _annotate_semantics(self, graph: TopologicalGraph, context, task: str) -> Dict:
        """为拓扑结构添加语义标注"""
        semantics = {
            'functional_zones': [],
            'movement_paths': [],
            'activity_centers': [],
            'spatial_qualities': {}
        }
        
        # 分析功能分区
        for node_id, node in graph.nodes.items():
            if node.type == 'cluster':
                density = node.properties.get('density', 0)
                if density > 0.7:
                    semantics['functional_zones'].append({
                        'node_id': node_id,
                        'type': 'high_density_residential',
                        'description': '高密度居住区'
                    })
                elif density > 0.4:
                    semantics['functional_zones'].append({
                        'node_id': node_id,
                        'type': 'medium_density_mixed',
                        'description': '中密度混合区'
                    })
                else:
                    semantics['functional_zones'].append({
                        'node_id': node_id,
                        'type': 'low_density_open',
                        'description': '低密度开放区'
                    })
            
            elif node.type == 'junction':
                degree = node.properties.get('degree', 0)
                if degree >= 4:
                    semantics['activity_centers'].append({
                        'node_id': node_id,
                        'type': 'major_intersection',
                        'description': '主要交通节点'
                    })
        
        # 分析路径结构
        for relation in graph.relations:
            if relation.type == 'connected':
                semantics['movement_paths'].append({
                    'from': relation.source,
                    'to': relation.target,
                    'type': 'direct_connection'
                })
        
        # 空间品质评估
        features = context.raw_features
        semantics['spatial_qualities'] = {
            'connectivity': features.get('connectivity', {}).get('average_degree', 0),
            'density_gradient': self._calculate_density_gradient(graph),
            'permeability': self._assess_permeability(graph),
            'legibility': self._assess_legibility(graph)
        }
        
        return semantics
    
    def _map_to_vector(self, graph: TopologicalGraph, context) -> Dict:
        """将拓扑结构映射到矢量空间"""
        mapping = {
            'node_coordinates': {},
            'relation_geometries': {},
            'spatial_index': {}
        }
        
        # 收集所有节点坐标
        for node_id, node in graph.nodes.items():
            if node.vector_anchor:
                mapping['node_coordinates'][node_id] = {
                    'x': node.vector_anchor[0],
                    'y': node.vector_anchor[1],
                    'crs': context.crs
                }
        
        # 为关系生成几何
        for relation in graph.relations:
            source_node = graph.nodes.get(relation.source)
            target_node = graph.nodes.get(relation.target)
            
            if (source_node and target_node and 
                source_node.vector_anchor and target_node.vector_anchor):
                
                # 创建连接线几何
                line = LineString([
                    source_node.vector_anchor,
                    target_node.vector_anchor
                ])
                
                relation.vector_geometry = line
                mapping['relation_geometries'][f"{relation.source}_{relation.target}"] = {
                    'type': 'LineString',
                    'coordinates': list(line.coords),
                    'length': line.length
                }
        
        # 构建空间索引（简化版本）
        coords = list(mapping['node_coordinates'].values())
        if coords:
            xs = [c['x'] for c in coords]
            ys = [c['y'] for c in coords]
            mapping['spatial_index'] = {
                'bounds': {
                    'minx': min(xs), 'miny': min(ys),
                    'maxx': max(xs), 'maxy': max(ys)
                },
                'resolution': 50  # 50米网格
            }
        
        return mapping
    
    def _identify_patterns(self, graph: TopologicalGraph, context) -> Dict:
        """识别空间模式"""
        patterns = {
            'network_structure': self._analyze_network_structure(graph),
            'hierarchy': self._identify_hierarchy(graph),
            'grain_direction': self._analyze_grain_direction(graph, context),
            'urban_fabric': self._characterize_fabric(graph, context)
        }
        return patterns
    
    def _generate_findings(self, graph: TopologicalGraph, semantics: Dict, task: str) -> List[str]:
        """生成关键发现"""
        findings = []
        
        # 基于图结构生成发现
        node_types = {}
        for node in graph.nodes.values():
            node_types[node.type] = node_types.get(node.type, 0) + 1
        
        findings.append(f"识别到 {len(graph.nodes)} 个空间节点，包括 {node_types.get('junction', 0)} 个交叉口")
        findings.append(f"识别到 {len(graph.relations)} 个空间关系")
        
        # 基于语义生成发现
        zones = semantics.get('functional_zones', [])
        if zones:
            findings.append(f"识别到 {len(zones)} 个功能分区")
        
        qualities = semantics.get('spatial_qualities', {})
        connectivity = qualities.get('connectivity', 0)
        if connectivity > 2.5:
            findings.append("该区域具有较高的街道连通性")
        elif connectivity < 1.5:
            findings.append("该区域街道连通性较低，可能存在可达性问题")
        
        return findings

    def _build_alignment_diagnostics(self,
                                     graph: TopologicalGraph,
                                     features: Dict,
                                     context,
                                     task: str) -> Dict:
        anchors = [node.vector_anchor for node in graph.nodes.values() if node.vector_anchor]
        relation_distances = [
            float(relation.properties.get('distance', 0.0))
            for relation in graph.relations
            if isinstance(relation.properties.get('distance'), (int, float))
        ]

        extent = self._estimate_extent(anchors)
        node_type_counts: Dict[str, int] = {}
        for node in graph.nodes.values():
            node_type_counts[node.type] = node_type_counts.get(node.type, 0) + 1

        dominant_type = max(node_type_counts, key=node_type_counts.get) if node_type_counts else 'unknown'
        total_nodes = max(len(graph.nodes), 1)
        dominant_ratio = node_type_counts.get(dominant_type, 0) / total_nodes
        missing_layers = [
            name for name in ('junctions', 'clusters', 'open_spaces', 'barriers', 'landmarks')
            if not features.get(name)
        ]

        if extent['max_span_m'] > 1200 and len(graph.nodes) <= 5:
            maup_like_risk = 'high'
        elif dominant_ratio > 0.65 or len(missing_layers) >= 2:
            maup_like_risk = 'medium'
        else:
            maup_like_risk = 'low'

        return {
            'task': task,
            'preferred_scale': self._infer_scale_band(extent['max_span_m']),
            'scale_span_m': extent['max_span_m'],
            'extent': extent,
            'relation_distance_stats': {
                'min_m': min(relation_distances) if relation_distances else 0.0,
                'median_m': float(np.median(relation_distances)) if relation_distances else 0.0,
                'max_m': max(relation_distances) if relation_distances else 0.0,
            },
            'dominant_node_type': dominant_type,
            'maup_like_risk': maup_like_risk,
            'human_review_prompts': [
                'Inspect the raw spatial distribution before accepting any topological summary.',
                'Confirm whether the current scale is appropriate for the planning question and note any scale shift.',
                'Check whether a stakeholder-specific fairness concern should override the default spatial reading.',
                'Decide whether previous memory from nearby places should be promoted, suppressed, or annotated.',
            ],
        }

    def _build_distribution_preview(self, features: Dict) -> Dict:
        feature_counts = {
            'junctions': len(features.get('junctions', [])),
            'clusters': len(features.get('clusters', [])),
            'corridors': len(features.get('corridors', [])),
            'open_spaces': len(features.get('open_spaces', [])),
            'barriers': len(features.get('barriers', [])),
            'landmarks': len(features.get('landmarks', [])),
        }
        missing_layers = [name for name, count in feature_counts.items() if count == 0]
        dominant_layer = max(feature_counts, key=feature_counts.get) if feature_counts else 'unknown'
        return {
            'feature_counts': feature_counts,
            'missing_layers': missing_layers,
            'dominant_layer': dominant_layer,
            'needs_visual_check': bool(missing_layers) or feature_counts.get(dominant_layer, 0) > 0,
            'review_questions': [
                'Which raw layers should be visually inspected before reasoning begins?',
                'Do observed distributions suggest a neighbourhood-scale pattern or a site-scale exception?',
            ],
        }

    def _build_inspection_payload(self,
                                  graph: TopologicalGraph,
                                  alignment_diagnostics: Dict,
                                  distribution_preview: Dict,
                                  vector_mapping: Dict) -> Dict:
        nodes = []
        for node in graph.nodes.values():
            x, y = node.vector_anchor if node.vector_anchor else (None, None)
            nodes.append({
                'id': node.id,
                'type': node.type,
                'label': node.label,
                'x': x,
                'y': y,
                'lat': y,
                'lng': x,
                'trace': node.trace,
                'properties': node.properties,
            })

        edges = []
        for relation in graph.relations:
            edges.append({
                'from': relation.source,
                'to': relation.target,
                'type': relation.type,
                'distance_m': relation.properties.get('distance'),
                'trace': relation.trace,
            })

        return {
            'nodes': nodes,
            'edges': edges,
            'alignment_diagnostics': alignment_diagnostics,
            'distribution_preview': distribution_preview,
            'vector_mapping': vector_mapping,
        }
    
    # ===== 辅助方法 =====
    
    def _identify_junctions(self, features: Dict) -> List[Dict]:
        """识别道路交叉口"""
        junctions = []
        graph = features.get('_graph')
        if graph:
            for node_id, data in graph.nodes(data=True):
                degree = graph.degree(node_id)
                if degree >= 3:  # 3条及以上道路交汇
                    junctions.append({
                        'id': node_id,
                        'degree': degree,
                        'coordinates': (data.get('x'), data.get('y')),
                        'road_types': []
                    })
        return junctions
    
    def _identify_building_clusters(self, features: Dict) -> List[Dict]:
        """识别建筑聚类"""
        clusters = []
        buildings_gdf = features.get('_gdf_buildings')
        
        if buildings_gdf is not None and len(buildings_gdf) > 0:
            # 使用简单的空间聚类（基于距离）
            from sklearn.cluster import DBSCAN
            
            centroids = buildings_gdf.centroid
            coords = np.array([(p.x, p.y) for p in centroids])
            
            if len(coords) > 5:
                clustering = DBSCAN(eps=50, min_samples=3).fit(coords)
                labels = clustering.labels_
                
                # 为每个聚类创建节点
                unique_labels = set(labels)
                for label in unique_labels:
                    if label == -1:  # 噪声点
                        continue
                    
                    mask = labels == label
                    cluster_buildings = buildings_gdf[mask]
                    bounds = cluster_buildings.total_bounds
                    width = max(float(bounds[2] - bounds[0]), 1.0)
                    height = max(float(bounds[3] - bounds[1]), 1.0)
                    envelope_area = width * height
                    footprint_area = float(cluster_buildings.area.sum())
                    
                    clusters.append({
                        'id': int(label),
                        'count': int(mask.sum()),
                        'density': float(footprint_area / max(envelope_area, 1.0)),
                        'centroid': (float(coords[mask, 0].mean()), float(coords[mask, 1].mean())),
                        'radius': float(max(width, height) / 2.0)
                    })
        
        return clusters
    
    def _identify_corridors(self, features: Dict) -> List[Dict]:
        """识别主要走廊/街道"""
        corridors = []
        roads = features.get('roads', {})
        
        # 基于道路类型识别主要走廊
        road_types = roads.get('road_types', {})
        for road_type, info in road_types.items():
            if road_type in ['primary', 'secondary', 'tertiary']:
                corridors.append({
                    'type': road_type,
                    'length': info.get('total_length', 0),
                    'count': info.get('count', 0)
                })
        
        return corridors
    
    def _identify_open_spaces(self, features: Dict) -> List[Dict]:
        """识别开放空间"""
        spaces = []
        
        # 基于土地利用识别
        landuse = features.get('landuse', {})
        for lutype, info in landuse.items():
            if lutype in ['park', 'recreation_ground', 'plaza', 'square']:
                spaces.append({
                    'type': lutype,
                    'area': info.get('area', 0),
                    'centroid': info.get('centroid'),
                    'shape_type': info.get('shape_type', 'polygon')
                })
        
        return spaces
    
    def _identify_barriers(self, features: Dict) -> List[Dict]:
        """识别空间障碍"""
        barriers = []
        
        # 大型建筑可能形成屏障
        buildings = features.get('buildings', {})
        if buildings.get('max_area', 0) > 10000:  # 大于1万平方米
            barriers.append({
                'type': 'large_building',
                'description': '大型建筑可能阻断视线和通行'
            })
        
        return barriers
    
    def _identify_landmarks(self, features: Dict) -> List[Dict]:
        """识别地标"""
        landmarks = []
        pois = features.get('pois', {})
        
        # 基于POI识别潜在地标
        for poi_type, poi_list in pois.items():
            if poi_type in ['monument', 'museum', 'church', 'tower']:
                for poi in poi_list[:3]:  # 每类最多取3个
                    landmarks.append({
                        'name': poi.get('name', 'Unknown'),
                        'type': poi_type,
                        'coordinates': poi.get('coordinates')
                    })
        
        return landmarks
    
    def _calculate_distance(self, p1: Tuple, p2: Tuple) -> float:
        """计算两点距离"""
        return np.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

    def _estimate_extent(self, anchors: List[Tuple[float, float]]) -> Dict:
        if not anchors:
            return {'minx': 0.0, 'miny': 0.0, 'maxx': 0.0, 'maxy': 0.0, 'max_span_m': 0.0}
        xs = [float(anchor[0]) for anchor in anchors]
        ys = [float(anchor[1]) for anchor in anchors]
        return {
            'minx': min(xs),
            'miny': min(ys),
            'maxx': max(xs),
            'maxy': max(ys),
            'max_span_m': max(max(xs) - min(xs), max(ys) - min(ys)),
        }

    def _infer_scale_band(self, max_span_m: float) -> str:
        if max_span_m <= 250:
            return 'site'
        if max_span_m <= 1200:
            return 'street_block'
        if max_span_m <= 5000:
            return 'neighbourhood'
        return 'district_or_city'
    
    def _determine_relation_type(self, node1: TopologicalNode, 
                                  node2: TopologicalNode, 
                                  distance: float) -> Optional[str]:
        """确定节点间关系类型"""
        if node1.type == 'barrier' or node2.type == 'barrier':
            if distance < 200:
                return 'separated'

        if {node1.type, node2.type} & {'cluster'} and {node1.type, node2.type} & {'plaza', 'landmark'}:
            cluster_node = node1 if node1.type == 'cluster' else node2
            cluster_radius = float(cluster_node.properties.get('radius', 80.0) or 80.0)
            if distance <= cluster_radius:
                return 'contains'

        if node1.vector_anchor and node2.vector_anchor:
            dx = abs(node1.vector_anchor[0] - node2.vector_anchor[0])
            dy = abs(node1.vector_anchor[1] - node2.vector_anchor[1])
            if distance < 250 and (dx < 20 or dy < 20):
                return 'aligned'

        # 基于距离阈值
        if distance < 100:  # 100米内
            return 'adjacent'
        elif distance < 300:  # 300米内
            return 'connected'
        else:
            return None
    
    def _calculate_density_gradient(self, graph: TopologicalGraph) -> float:
        """计算密度梯度"""
        densities = []
        for node in graph.nodes.values():
            if node.type == 'cluster':
                densities.append(node.properties.get('density', 0))
        
        if densities:
            return float(np.std(densities))  # 密度变化程度
        return 0.0
    
    def _assess_permeability(self, graph: TopologicalGraph) -> float:
        """评估空间渗透性"""
        # 基于连接数评估
        connection_counts = [len(node.connections) for node in graph.nodes.values()]
        if connection_counts:
            return float(np.mean(connection_counts))
        return 0.0
    
    def _assess_legibility(self, graph: TopologicalGraph) -> float:
        """评估空间可读性"""
        # 基于节点类型多样性
        type_counts = {}
        for node in graph.nodes.values():
            type_counts[node.type] = type_counts.get(node.type, 0) + 1
        
        # 类型越多，可读性越高
        return min(1.0, len(type_counts) / 5.0)
    
    def _analyze_network_structure(self, graph: TopologicalGraph) -> Dict:
        """分析网络结构"""
        # 转换为NetworkX图进行分析
        G = nx.Graph()
        for node_id in graph.nodes:
            G.add_node(node_id)
        for relation in graph.relations:
            G.add_edge(relation.source, relation.target)
        
        return {
            'clustering_coefficient': nx.average_clustering(G) if len(G) > 2 else 0,
            'density': nx.density(G),
            'is_connected': nx.is_connected(G) if len(G) > 0 else False
        }
    
    def _identify_hierarchy(self, graph: TopologicalGraph) -> Dict:
        """识别空间层次"""
        # 基于连接度识别层次
        degrees = {node_id: len(node.connections) 
                  for node_id, node in graph.nodes.items()}
        
        if degrees:
            max_degree = max(degrees.values())
            hierarchy = {
                'primary': [n for n, d in degrees.items() if d >= max_degree * 0.7],
                'secondary': [n for n, d in degrees.items() 
                            if max_degree * 0.3 <= d < max_degree * 0.7],
                'tertiary': [n for n, d in degrees.items() if d < max_degree * 0.3]
            }
        else:
            hierarchy = {'primary': [], 'secondary': [], 'tertiary': []}
        
        return hierarchy
    
    def _analyze_grain_direction(self, graph: TopologicalGraph, context) -> Dict:
        """分析空间肌理方向"""
        features = context.raw_features
        roads = features.get('roads', {})
        
        return {
            'dominant_orientation': roads.get('dominant_orientation', 0),
            'orientation_entropy': roads.get('orientation_entropy', 0),
            'regularity': features.get('spatial_patterns', {}).get('grid_regularity', 0)
        }
    
    def _characterize_fabric(self, graph: TopologicalGraph, context) -> Dict:
        """描述城市肌理特征"""
        features = context.raw_features
        
        return {
            'building_density': features.get('buildings', {}).get('density', 0),
            'connectivity': features.get('connectivity', {}).get('average_degree', 0),
            'clustering': features.get('spatial_patterns', {}).get('building_clustering', 0),
            'grid_regularity': features.get('spatial_patterns', {}).get('grid_regularity', 0)
        }
