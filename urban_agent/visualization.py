"""
Spatial Visualization: 空间可视化模块
生成与真实地理坐标对齐的SVG和GeoJSON输出
"""

from typing import Dict, List, Any, Tuple
import json
from shapely.geometry import Point, LineString, Polygon, mapping
from shapely.affinity import scale, translate
import xml.etree.ElementTree as ET


class SpatialVisualizer:
    """
    空间可视化器：创建与地图底图对齐的可视化输出
    
    核心功能：
    1. 将地理坐标精确映射到SVG坐标系
    2. 生成与底图对齐的干预区域叠加层
    3. 输出标准GeoJSON格式供GIS软件使用
    """
    
    def __init__(self, svg_size: int = 800):
        self.svg_size = svg_size
        self.padding = 20  # SVG边距
    
    def create_svg_overlay(self, raw_features: Dict, 
                          intervention_areas: List[Dict],
                          bbox: Tuple) -> str:
        """
        创建SVG叠加层（与地图底图精确对齐）
        
        Args:
            raw_features: 原始空间特征（包含建筑、道路等）
            intervention_areas: 干预区域列表
            bbox: 地理边界框 (minx, miny, maxx, maxy)
            
        Returns:
            SVG字符串
        """
        minx, miny, maxx, maxy = bbox
        
        # 计算缩放比例（保持宽高比）
        width = maxx - minx
        height = maxy - miny
        
        # 防止除零错误
        if width <= 0 or height <= 0:
            width = max(width, 100)
            height = max(height, 100)
        
        scale_factor = (self.svg_size - 2 * self.padding) / max(width, height)
        
        # 创建SVG根元素
        svg = ET.Element('svg')
        svg.set('xmlns', 'http://www.w3.org/2000/svg')
        svg.set('viewBox', f'0 0 {self.svg_size} {self.svg_size}')
        svg.set('style', 'background-color: #f5f5f5;')
        
        # 定义坐标转换函数
        def geo_to_svg(x, y):
            """将地理坐标转换为SVG坐标"""
            svg_x = self.padding + (x - minx) * scale_factor
            # Y轴翻转（SVG坐标系Y向下）
            svg_y = self.svg_size - self.padding - (y - miny) * scale_factor
            return svg_x, svg_y
        
        # 1. 绘制底图（道路和建筑）
        base_layer = ET.SubElement(svg, 'g')
        base_layer.set('id', 'base_map')
        
        # 绘制建筑
        buildings_gdf = raw_features.get('_gdf_buildings')
        if buildings_gdf is not None and len(buildings_gdf) > 0:
            buildings_layer = ET.SubElement(base_layer, 'g')
            buildings_layer.set('id', 'buildings')
            buildings_layer.set('fill', '#d1d5db')
            buildings_layer.set('stroke', '#9ca3af')
            buildings_layer.set('stroke-width', '0.5')
            
            for _, building in buildings_gdf.iterrows():
                geom = building.geometry
                if geom is not None:
                    points = self._geometry_to_svg_points(geom, geo_to_svg)
                    if points:
                        polygon = ET.SubElement(buildings_layer, 'polygon')
                        polygon.set('points', points)
        
        # 绘制道路
        roads_gdf = raw_features.get('_gdf_roads')
        if roads_gdf is not None and len(roads_gdf) > 0:
            roads_layer = ET.SubElement(base_layer, 'g')
            roads_layer.set('id', 'roads')
            roads_layer.set('fill', 'none')
            roads_layer.set('stroke', '#6b7280')
            roads_layer.set('stroke-width', '1.5')
            
            for _, road in roads_gdf.iterrows():
                geom = road.geometry
                if geom is not None and hasattr(geom, 'coords'):
                    path_data = self._line_to_svg_path(geom, geo_to_svg)
                    if path_data:
                        path = ET.SubElement(roads_layer, 'path')
                        path.set('d', path_data)
        
        # 2. 绘制干预区域（叠加层）
        intervention_layer = ET.SubElement(svg, 'g')
        intervention_layer.set('id', 'interventions')
        
        colors = {
            'connectivity_gap': '#10b981',  # 绿色
            'open_space_needed': '#3b82f6',  # 蓝色
            'activity_node_potential': '#f59e0b',  # 橙色
            'default': '#8b5cf6'  # 紫色
        }
        
        for area in intervention_areas:
            geom_dict = area.get('geometry', {})
            geom_type = geom_dict.get('type', '')
            coords = geom_dict.get('coordinates', [])
            
            color = colors.get(area.get('type'), colors['default'])
            
            if geom_type == 'Point':
                # 绘制点标记
                x, y = geo_to_svg(coords[0], coords[1])
                circle = ET.SubElement(intervention_layer, 'circle')
                circle.set('cx', str(x))
                circle.set('cy', str(y))
                circle.set('r', '8')
                circle.set('fill', color)
                circle.set('stroke', 'white')
                circle.set('stroke-width', '2')
                circle.set('opacity', '0.9')
                
                # 添加标签
                label = ET.SubElement(intervention_layer, 'text')
                label.set('x', str(x))
                label.set('y', str(y - 12))
                label.set('text-anchor', 'middle')
                label.set('font-size', '10')
                label.set('font-weight', 'bold')
                label.set('fill', '#374151')
                label.text = area.get('description', '')[:20]
                
            elif geom_type == 'LineString':
                # 绘制线条
                path_data = self._coords_to_svg_path(coords, geo_to_svg)
                if path_data:
                    path = ET.SubElement(intervention_layer, 'path')
                    path.set('d', path_data)
                    path.set('stroke', color)
                    path.set('stroke-width', '4')
                    path.set('stroke-dasharray', '8,4')
                    path.set('fill', 'none')
                    path.set('opacity', '0.8')
                    
            elif geom_type == 'Polygon':
                # 绘制多边形
                if coords and len(coords) > 0:
                    points = self._coords_to_svg_points(coords[0], geo_to_svg)
                    if points:
                        polygon = ET.SubElement(intervention_layer, 'polygon')
                        polygon.set('points', points)
                        polygon.set('fill', color)
                        polygon.set('fill-opacity', '0.3')
                        polygon.set('stroke', color)
                        polygon.set('stroke-width', '2')
                        
                        # 添加标签在中心
                        centroid = self._calculate_centroid(coords[0])
                        if centroid:
                            cx, cy = geo_to_svg(centroid[0], centroid[1])
                            label = ET.SubElement(intervention_layer, 'text')
                            label.set('x', str(cx))
                            label.set('y', str(cy))
                            label.set('text-anchor', 'middle')
                            label.set('dominant-baseline', 'middle')
                            label.set('font-size', '11')
                            label.set('font-weight', 'bold')
                            label.set('fill', '#1f2937')
                            label.text = area.get('description', '')[:15]
        
        # 3. 添加图例
        legend_layer = ET.SubElement(svg, 'g')
        legend_layer.set('id', 'legend')
        legend_layer.set('transform', f'translate({self.padding}, {self.padding})')
        
        legend_bg = ET.SubElement(legend_layer, 'rect')
        legend_bg.set('x', '0')
        legend_bg.set('y', '0')
        legend_bg.set('width', '150')
        legend_bg.set('height', str(len(intervention_areas) * 25 + 10))
        legend_bg.set('fill', 'white')
        legend_bg.set('stroke', '#e5e7eb')
        legend_bg.set('rx', '4')
        legend_bg.set('opacity', '0.95')
        
        for i, area in enumerate(intervention_areas):
            y_pos = 20 + i * 25
            color = colors.get(area.get('type'), colors['default'])
            
            # 图例色块
            rect = ET.SubElement(legend_layer, 'rect')
            rect.set('x', '10')
            rect.set('y', str(y_pos - 10))
            rect.set('width', '15')
            rect.set('height', '15')
            rect.set('fill', color)
            
            # 图例文字
            text = ET.SubElement(legend_layer, 'text')
            text.set('x', '30')
            text.set('y', str(y_pos + 2))
            text.set('font-size', '11')
            text.set('fill', '#374151')
            text.text = area.get('type', 'Unknown').replace('_', ' ').title()
        
        # 转换为字符串
        return ET.tostring(svg, encoding='unicode')
    
    def create_geojson_features(self, intervention_areas: List[Dict], 
                                crs: str) -> List[Dict]:
        """
        创建GeoJSON特征集合
        
        Args:
            intervention_areas: 干预区域列表
            crs: 坐标参考系
            
        Returns:
            GeoJSON特征列表
        """
        features = []
        
        for area in intervention_areas:
            geom_dict = area.get('geometry', {})
            
            feature = {
                'type': 'Feature',
                'geometry': geom_dict,
                'properties': {
                    'id': area.get('id'),
                    'type': area.get('type'),
                    'description': area.get('description'),
                    'target_node': area.get('target_node')
                }
            }
            
            features.append(feature)
        
        return features
    
    def create_geojson_collection(self, intervention_areas: List[Dict],
                                  crs: str) -> Dict:
        """
        创建完整的GeoJSON集合
        
        Args:
            intervention_areas: 干预区域列表
            crs: 坐标参考系
            
        Returns:
            GeoJSON集合字典
        """
        features = self.create_geojson_features(intervention_areas, crs)
        
        return {
            'type': 'FeatureCollection',
            'crs': {
                'type': 'name',
                'properties': {
                    'name': crs
                }
            },
            'features': features
        }
    
    def _geometry_to_svg_points(self, geom, geo_to_svg_func) -> str:
        """将几何对象转换为SVG点字符串"""
        from shapely.geometry import Polygon, MultiPolygon
        
        coords = []
        
        if isinstance(geom, Polygon):
            # 简单多边形
            coords = list(geom.exterior.coords)
        elif isinstance(geom, MultiPolygon):
            # 多部分多边形 - 取第一个部分
            if len(geom.geoms) > 0:
                coords = list(geom.geoms[0].exterior.coords)
        elif hasattr(geom, 'exterior'):
            # 其他有exterior的几何
            coords = list(geom.exterior.coords)
        elif hasattr(geom, 'coords'):
            # 线或点
            try:
                coords = list(geom.coords)
            except NotImplementedError:
                # Multi-part geometries don't have coords
                return ""
        else:
            return ""
        
        points = []
        for x, y in coords:
            svg_x, svg_y = geo_to_svg_func(x, y)
            points.append(f"{svg_x},{svg_y}")
        
        return " ".join(points)
    
    def _line_to_svg_path(self, geom, geo_to_svg_func) -> str:
        """将线几何转换为SVG路径"""
        if not hasattr(geom, 'coords'):
            return ""
        
        coords = list(geom.coords)
        if len(coords) < 2:
            return ""
        
        commands = []
        for i, (x, y) in enumerate(coords):
            svg_x, svg_y = geo_to_svg_func(x, y)
            cmd = 'M' if i == 0 else 'L'
            commands.append(f"{cmd} {svg_x} {svg_y}")
        
        return " ".join(commands)
    
    def _coords_to_svg_path(self, coords: List, geo_to_svg_func) -> str:
        """将坐标列表转换为SVG路径"""
        if len(coords) < 2:
            return ""
        
        commands = []
        for i, coord in enumerate(coords):
            if len(coord) >= 2:
                svg_x, svg_y = geo_to_svg_func(coord[0], coord[1])
                cmd = 'M' if i == 0 else 'L'
                commands.append(f"{cmd} {svg_x} {svg_y}")
        
        return " ".join(commands)
    
    def _coords_to_svg_points(self, coords: List, geo_to_svg_func) -> str:
        """将坐标列表转换为SVG点字符串"""
        points = []
        for coord in coords:
            if len(coord) >= 2:
                svg_x, svg_y = geo_to_svg_func(coord[0], coord[1])
                points.append(f"{svg_x},{svg_y}")
        
        return " ".join(points)
    
    def _calculate_centroid(self, coords: List) -> Tuple[float, float]:
        """计算多边形中心点"""
        if not coords:
            return None
        
        xs = [c[0] for c in coords if len(c) >= 2]
        ys = [c[1] for c in coords if len(c) >= 2]
        
        if not xs or not ys:
            return None
        
        return (sum(xs) / len(xs), sum(ys) / len(ys))


class MeasurementReporter:
    """测量报告生成器"""
    
    @staticmethod
    def generate_report(baseline: Dict, proposals: List[Dict]) -> str:
        """生成测量报告"""
        report = []
        report.append("=" * 60)
        report.append("空间干预测量报告")
        report.append("=" * 60)
        
        # 基线条件
        report.append("\n【基线条件】")
        
        connectivity = baseline.get('connectivity', {})
        report.append(f"  连通性:")
        report.append(f"    - 全局连通度: {connectivity.get('global_connectivity', 0):.2f}")
        report.append(f"    - 孤立节点数: {connectivity.get('isolated_nodes', 0)}")
        
        accessibility = baseline.get('accessibility', {})
        report.append(f"  可达性:")
        report.append(f"    - 平均距离: {accessibility.get('average_distance', 0):.1f}m")
        report.append(f"    - 300m覆盖率: {accessibility.get('within_300m', 0)*100:.1f}%")
        
        walkability = baseline.get('walkability', {})
        report.append(f"  步行友好性:")
        report.append(f"    - 交叉口密度: {walkability.get('intersection_density', 0):.2f}/km²")
        report.append(f"    - 步行友好度: {walkability.get('walkability_score', 0):.2f}")
        
        # 干预方案
        report.append("\n【干预方案】")
        for i, proposal in enumerate(proposals, 1):
            report.append(f"\n  方案 {i}: {proposal.get('id')}")
            report.append(f"    类型: {proposal.get('type')}")
            report.append(f"    描述: {proposal.get('description')}")
            
            impact = proposal.get('expected_impact', {})
            if impact:
                report.append(f"    预期效果:")
                for key, value in impact.items():
                    report.append(f"      - {key}: {value:.2f}")
            
            measurements = proposal.get('measurements', {})
            geom_info = measurements.get('geometry', {})
            if geom_info:
                report.append(f"    几何属性:")
                if 'area' in geom_info:
                    report.append(f"      - 面积: {geom_info['area']:.1f}m²")
                if 'length' in geom_info:
                    report.append(f"      - 长度: {geom_info['length']:.1f}m")
        
        report.append("\n" + "=" * 60)
        
        return "\n".join(report)
