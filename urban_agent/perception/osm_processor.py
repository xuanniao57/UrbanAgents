"""
OSM Processor: 城市空间数据处理器
支持从OSM或本地Shapefile获取城市数据
"""

import geopandas as gpd
from shapely.geometry import Point, Polygon, LineString, MultiLineString
from typing import Dict, List, Tuple, Any, Optional
import numpy as np
import os


class OSMProcessor:
    """
    城市数据处理模块：支持OSM和本地Shapefile数据源
    """
    
    def __init__(self, data_source: str = "auto"):
        """
        Args:
            data_source: 数据源类型 ("osm", "local", "auto")
        """
        self.data_source = data_source
        self.city_data_path = "third_party/CityBench-main/citydata/EXP_ORIG_DATA"
    
    def process(self, location: str, radius: int = 500) -> Dict:
        """
        处理指定区域的空间信息
        
        Args:
            location: 地理位置（城市名或地址）
            radius: 处理半径（米），对本地数据无效
            
        Returns:
            包含空间数据的字典
        """
        # 对于具体地址，直接使用OSM
        if '附近' in location or 'nearby' in location.lower() or ',' in location:
            print(f"  → Fetching from OSM for specific location...")
            return self._process_from_osm(location, radius)
        
        # 尝试从本地数据加载
        city_name = self._extract_city_name(location)
        local_data = self._load_local_data(city_name)
        
        if local_data is not None:
            print(f"  → Using local data for {city_name}")
            return self._process_local_data(local_data, location)
        
        # 如果没有本地数据，尝试OSM
        print(f"  → No local data found, attempting OSM fetch...")
        return self._process_from_osm(location, radius)
    
    def _extract_city_name(self, location: str) -> str:
        """从位置字符串提取城市名"""
        city_mapping = {
            '上海': 'Shanghai', '北京': 'Beijing', '巴黎': 'Paris',
            '伦敦': 'London', '纽约': 'NewYork', '东京': 'Tokyo',
            '悉尼': 'Sydney', '莫斯科': 'Moscow', '孟买': 'Mumbai',
            '内罗毕': 'Nairobi', '开普敦': 'CapeTown', '圣保罗': 'SaoPaulo'
        }
        
        for cn, en in city_mapping.items():
            if cn in location or en.lower() in location.lower():
                return en
        
        return location.split(',')[0].strip()
    
    def _load_local_data(self, city_name: str) -> Optional[gpd.GeoDataFrame]:
        """加载本地Shapefile数据"""
        shapefile_path = os.path.join(self.city_data_path, city_name, f"{city_name}.shp")
        
        if os.path.exists(shapefile_path):
            try:
                gdf = gpd.read_file(shapefile_path)
                return gdf
            except Exception as e:
                print(f"  ⚠ Error loading local data: {e}")
                return None
        
        return None
    
    def _process_local_data(self, gdf: gpd.GeoDataFrame, location: str) -> Dict:
        """处理本地数据（主要是建筑/区域数据）"""
        local_utm = gdf.estimate_utm_crs()
        gdf = gdf.to_crs(local_utm)
        
        # 本地数据主要是建筑多边形
        buildings = gdf[gdf.geometry.type.isin(['Polygon', 'MultiPolygon'])].copy()
        
        bounds = gdf.total_bounds
        
        # 为本地数据生成模拟的道路网络（基于建筑边界）
        roads = self._generate_roads_from_buildings(buildings)
        
        features = {
            'roads': self._analyze_roads(roads),
            'buildings': self._analyze_buildings(buildings),
            'pois': {},
            'landuse': {},
            'spatial_patterns': {
                'grid_regularity': 0.5,
                'building_clustering': self._calculate_clustering(buildings)
            },
            'connectivity': {
                'average_degree': 2.5,
                'intersection_density': 0.1
            },
            '_gdf_roads': roads,
            '_gdf_buildings': buildings,
            '_gdf_landuse': None,
            '_graph': None,
            '_bbox': bounds,
            '_crs': str(local_utm)
        }
        
        return features
    
    def _generate_roads_from_buildings(self, buildings_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """从建筑数据生成简化的道路网络"""
        if len(buildings_gdf) == 0:
            return gpd.GeoDataFrame(geometry=[], crs=buildings_gdf.crs)
        
        # 获取建筑中心点
        centroids = buildings_gdf.centroid
        
        # 创建简化的道路线（连接相邻建筑）
        from scipy.spatial import Delaunay
        
        coords = np.array([(p.x, p.y) for p in centroids])
        
        if len(coords) < 3:
            return gpd.GeoDataFrame(geometry=[], crs=buildings_gdf.crs)
        
        try:
            tri = Delaunay(coords)
            
            lines = []
            for simplex in tri.simplices:
                # 添加三角形的边作为道路
                for i in range(3):
                    p1 = coords[simplex[i]]
                    p2 = coords[simplex[(i+1)%3]]
                    line = LineString([p1, p2])
                    # 只添加不太长的边
                    if line.length < 500:  # 最大500米
                        lines.append(line)
            
            roads_gdf = gpd.GeoDataFrame(geometry=lines, crs=buildings_gdf.crs)
            return roads_gdf
        except:
            return gpd.GeoDataFrame(geometry=[], crs=buildings_gdf.crs)
    
    def _process_from_osm(self, location: str, radius: int) -> Dict:
        """从OSM获取数据"""
        import osmnx as ox
        
        print(f"  → Fetching road network (radius: {radius}m)...")
        try:
            road_graph = ox.graph_from_address(
                location, 
                dist=radius, 
                network_type='all',
                simplify=True
            )
        except Exception as e:
            print(f"  ⚠ Error fetching roads: {e}")
            road_graph = None
        
        print(f"  → Fetching building footprints...")
        try:
            buildings = ox.features_from_address(
                location,
                tags={"building": True},
                dist=radius
            )
        except Exception as e:
            print(f"  ⚠ Error fetching buildings: {e}")
            buildings = gpd.GeoDataFrame()
        
        print(f"  → Fetching Points of Interest...")
        pois = self._fetch_pois(location, radius)
        
        # 处理数据
        if len(buildings) > 0:
            local_utm = buildings.estimate_utm_crs()
            buildings = buildings.to_crs(local_utm)
            bounds = buildings.total_bounds
        else:
            local_utm = "EPSG:4326"
            bounds = (0, 0, 0, 0)
        
        if road_graph is not None:
            nodes, edges = ox.graph_to_gdfs(road_graph)
            edges = edges.to_crs(local_utm)
            connectivity = self._analyze_connectivity(road_graph)
        else:
            edges = gpd.GeoDataFrame(geometry=[], crs=local_utm)
            connectivity = {'average_degree': 0, 'intersection_density': 0}
        
        features = {
            'roads': self._analyze_roads(edges),
            'buildings': self._analyze_buildings(buildings),
            'pois': pois,
            'landuse': {},
            'spatial_patterns': {
                'grid_regularity': self._calculate_grid_regularity(edges),
                'building_clustering': self._calculate_clustering(buildings)
            },
            'connectivity': connectivity,
            '_gdf_roads': edges,
            '_gdf_buildings': buildings,
            '_gdf_landuse': None,
            '_graph': road_graph,
            '_bbox': bounds,
            '_crs': str(local_utm)
        }
        
        return features
    
    def _fetch_pois(self, location: str, radius: int) -> Dict[str, List[Dict]]:
        """获取各类POI数据"""
        import osmnx as ox
        
        poi_tags = {
            'amenity': ['restaurant', 'cafe', 'shop', 'school', 'hospital', 'parking'],
            'shop': True,
            'tourism': True,
            'leisure': True
        }
        
        try:
            pois = ox.features_from_address(location, tags=poi_tags, dist=radius)
            
            categorized = {}
            for _, poi in pois.iterrows():
                poi_type = poi.get('amenity') or poi.get('shop') or poi.get('tourism') or 'other'
                if poi_type not in categorized:
                    categorized[poi_type] = []
                
                geom = poi.geometry
                if isinstance(geom, Point):
                    coords = (geom.x, geom.y)
                elif isinstance(geom, Polygon):
                    coords = (geom.centroid.x, geom.centroid.y)
                else:
                    continue
                
                categorized[poi_type].append({
                    'name': poi.get('name', 'Unknown'),
                    'type': poi_type,
                    'coordinates': coords
                })
            
            return categorized
        except Exception as e:
            print(f"  ⚠ Warning: Could not fetch POIs: {e}")
            return {}
    
    def _analyze_roads(self, edges_gdf: gpd.GeoDataFrame) -> Dict:
        """分析道路网络特征"""
        if len(edges_gdf) == 0:
            return {'total_length_m': 0, 'segment_count': 0, 'road_types': {}}
        
        total_length = edges_gdf.length.sum()
        
        road_types = {}
        if 'highway' in edges_gdf.columns:
            for highway_type, group in edges_gdf.groupby('highway'):
                road_types[str(highway_type)] = {
                    'count': len(group),
                    'total_length': float(group.length.sum())
                }
        
        return {
            'total_length_m': float(total_length),
            'segment_count': len(edges_gdf),
            'road_types': road_types,
            'avg_segment_length': float(edges_gdf.length.mean()) if len(edges_gdf) > 0 else 0
        }
    
    def _analyze_buildings(self, buildings_gdf: gpd.GeoDataFrame) -> Dict:
        """分析建筑特征"""
        if len(buildings_gdf) == 0:
            return {'count': 0, 'total_area_m2': 0, 'density': 0}
        
        areas = buildings_gdf.area
        total_area = areas.sum()
        
        bounds = buildings_gdf.total_bounds
        site_area = (bounds[2] - bounds[0]) * (bounds[3] - bounds[1])
        density = total_area / site_area if site_area > 0 else 0
        
        building_types = {}
        if 'building' in buildings_gdf.columns:
            for btype, group in buildings_gdf.groupby('building'):
                building_types[str(btype)] = len(group)
        
        return {
            'count': len(buildings_gdf),
            'total_area_m2': float(total_area),
            'density': float(density),
            'avg_area_m2': float(areas.mean()),
            'building_types': building_types
        }
    
    def _analyze_connectivity(self, graph) -> Dict:
        """分析网络连通性"""
        import networkx as nx
        
        try:
            degrees = [d for n, d in graph.degree()]
            avg_degree = np.mean(degrees) if degrees else 0
            
            return {
                'average_degree': float(avg_degree),
                'intersection_density': len([n for n, d in graph.degree() if d > 2]) / len(graph.nodes()) if len(graph.nodes()) > 0 else 0
            }
        except:
            return {'average_degree': 0, 'intersection_density': 0}
    
    def _calculate_grid_regularity(self, edges_gdf: gpd.GeoDataFrame) -> float:
        """计算网格规则性"""
        return 0.5
    
    def _calculate_clustering(self, buildings: gpd.GeoDataFrame) -> float:
        """计算建筑聚类程度"""
        if len(buildings) < 2:
            return 0.0
        
        centroids = buildings.centroid
        coords = np.array([(p.x, p.y) for p in centroids])
        
        if len(coords) < 2:
            return 0.0
        
        from scipy.spatial.distance import pdist
        distances = pdist(coords)
        avg_distance = np.mean(distances)
        
        bounds = buildings.total_bounds
        max_dist = np.sqrt((bounds[2]-bounds[0])**2 + (bounds[3]-bounds[1])**2)
        clustering = 1 - min(1, avg_distance / (max_dist * 0.1 + 1e-10))
        
        return float(clustering)
