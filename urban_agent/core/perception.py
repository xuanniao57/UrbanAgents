"""
Perception Module
多源城市数据感知模块
"""

import base64
import json
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path
import numpy as np

logger = logging.getLogger(__name__)


class PerceptionModule:
    """
    感知模块：处理多源城市数据
    
    支持的数据类型：
    - 遥感影像（Remote Sensing）
    - 街景图像（Street View）
    - OSM数据（OpenStreetMap）
    - GeoJSON矢量数据
    - 轨迹数据（Trajectory）
    """
    
    def __init__(
        self,
        llm_client: Optional[Any] = None,
        vlm_client: Optional[Any] = None,
        config: Optional[Dict] = None
    ):
        self.llm_client = llm_client
        self.vlm_client = vlm_client
        self.config = config or {}
        
    async def process(
        self,
        task: Dict,
        city_data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        处理感知任务
        
        Args:
            task: 任务定义，包含数据类型和路径
            city_data: 城市数据
            
        Returns:
            感知结果
        """
        data_type = task.get("data_type", "unknown")
        
        logger.info(f"感知模块处理数据类型: {data_type}")
        
        if data_type == "remote_sensing":
            return await self._process_remote_sensing(task)
        elif data_type == "street_view":
            return await self._process_street_view(task)
        elif data_type == "osm":
            return await self._process_osm(task)
        elif data_type == "geojson":
            return await self._process_geojson(task)
        elif data_type == "trajectory":
            return await self._process_trajectory(task)
        elif data_type == "text":
            return await self._process_text(task)
        elif data_type == "mixed":
            return await self._process_mixed(task, city_data)
        else:
            return {"type": data_type, "content": task.get("content", {})}
    
    async def _process_remote_sensing(
        self,
        task: Dict
    ) -> Dict[str, Any]:
        """处理遥感影像"""
        image_path = task.get("image_path")
        
        if not image_path or not Path(image_path).exists():
            return {"type": "remote_sensing", "error": "Image not found"}
        
        # 使用VLM处理遥感影像
        if self.vlm_client:
            try:
                with open(image_path, "rb") as f:
                    image_data = base64.b64encode(f.read()).decode()
                
                prompt = """Analyze this remote sensing image. 
                Describe: 1) Land use types visible 2) Building density 3) Road network patterns 
                4) Green spaces 5) Any notable urban features."""
                
                description = await self.vlm_client.analyze_image(image_data, prompt)
                
                return {
                    "type": "remote_sensing",
                    "image_path": image_path,
                    "description": description,
                    "features": self._extract_features_from_description(description)
                }
            except Exception as e:
                logger.error(f"VLM处理遥感影像失败: {e}")
        
        # 基础图像分析（无VLM时）
        return {
            "type": "remote_sensing",
            "image_path": image_path,
            "description": "Remote sensing image loaded",
            "features": {"land_use": [], "density": "unknown"}
        }
    
    async def _process_street_view(
        self,
        task: Dict
    ) -> Dict[str, Any]:
        """处理街景图像"""
        image_path = task.get("image_path")
        
        if not image_path or not Path(image_path).exists():
            return {"type": "street_view", "error": "Image not found"}
        
        # 使用VLM处理街景图像
        if self.vlm_client:
            try:
                with open(image_path, "rb") as f:
                    image_data = base64.b64encode(f.read()).decode()
                
                prompt = """Analyze this street view image.
                Identify: 1) Scene type (commercial/residential/industrial) 2) Buildings and architecture
                3) Street elements (sidewalks, street furniture) 4) Vehicles and pedestrians
                5) Safety features 6) Accessibility features."""
                
                description = await self.vlm_client.analyze_image(image_data, prompt)
                
                return {
                    "type": "street_view",
                    "image_path": image_path,
                    "description": description,
                    "scene_graph": self._extract_scene_graph(description)
                }
            except Exception as e:
                logger.error(f"VLM处理街景图像失败: {e}")
        
        return {
            "type": "street_view",
            "image_path": image_path,
            "description": "Street view image loaded"
        }
    
    async def _process_osm(
        self,
        task: Dict
    ) -> Dict[str, Any]:
        """处理OSM数据"""
        osm_data = task.get("osm_data", {})
        
        # 提取道路网络、POI、建筑等
        roads = osm_data.get("roads", [])
        pois = osm_data.get("pois", [])
        buildings = osm_data.get("buildings", [])
        
        # 计算拓扑特征
        road_network = self._analyze_road_network(roads)
        
        return {
            "type": "osm",
            "road_network": road_network,
            "poi_count": len(pois),
            "building_count": len(buildings),
            "poi_categories": self._categorize_pois(pois),
            "topology": self._extract_topology(roads, buildings)
        }
    
    async def _process_geojson(
        self,
        task: Dict
    ) -> Dict[str, Any]:
        """处理GeoJSON数据"""
        geojson = task.get("geojson", {})
        
        features = geojson.get("features", [])
        
        # 分析几何特征
        geometries = []
        for feature in features:
            geom = feature.get("geometry", {})
            properties = feature.get("properties", {})
            geometries.append({
                "type": geom.get("type"),
                "coordinates": geom.get("coordinates"),
                "properties": properties
            })
        
        return {
            "type": "geojson",
            "feature_count": len(features),
            "geometries": geometries,
            "bounds": self._calculate_bounds(geometries),
            "area": self._calculate_area(geometries)
        }
    
    async def _process_trajectory(
        self,
        task: Dict
    ) -> Dict[str, Any]:
        """处理轨迹数据"""
        trajectories = task.get("trajectories", [])
        
        # 分析轨迹特征
        trajectory_features = []
        for traj in trajectories:
            points = traj.get("points", [])
            if len(points) > 1:
                trajectory_features.append({
                    "length": len(points),
                    "duration": points[-1].get("timestamp", 0) - points[0].get("timestamp", 0),
                    "start": points[0],
                    "end": points[-1],
                    "path": points
                })
        
        return {
            "type": "trajectory",
            "trajectory_count": len(trajectories),
            "features": trajectory_features,
            "flow_patterns": self._analyze_flow_patterns(trajectory_features)
        }
    
    async def _process_text(
        self,
        task: Dict
    ) -> Dict[str, Any]:
        """处理文本数据"""
        text = task.get("text", "")
        
        # 使用LLM提取关键信息
        if self.llm_client:
            try:
                prompt = f"""Extract key spatial information from this text:
                {text}
                
                Identify: 1) Locations mentioned 2) Spatial relationships 
                3) Urban features 4) Activities or events."""
                
                extraction = await self.llm_client.generate(prompt)
                
                return {
                    "type": "text",
                    "original_text": text,
                    "extraction": extraction,
                    "entities": self._extract_entities(text)
                }
            except Exception as e:
                logger.error(f"LLM处理文本失败: {e}")
        
        return {
            "type": "text",
            "original_text": text,
            "entities": self._extract_entities(text)
        }
    
    async def _process_mixed(
        self,
        task: Dict,
        city_data: Optional[Dict]
    ) -> Dict[str, Any]:
        """处理混合数据类型"""
        results = {}
        
        if city_data:
            for data_type, data in city_data.items():
                sub_task = {"data_type": data_type, "content": data}
                results[data_type] = await self.process(sub_task)
        
        return {
            "type": "mixed",
            "components": results
        }
    
    def _extract_features_from_description(self, description: str) -> Dict:
        """从描述中提取特征"""
        features = {
            "land_use": [],
            "density": "unknown",
            "road_pattern": "unknown"
        }
        
        # 简单的关键词匹配
        if "residential" in description.lower():
            features["land_use"].append("residential")
        if "commercial" in description.lower():
            features["land_use"].append("commercial")
        if "industrial" in description.lower():
            features["land_use"].append("industrial")
        if "green" in description.lower() or "park" in description.lower():
            features["land_use"].append("green_space")
        
        return features
    
    def _extract_scene_graph(self, description: str) -> Dict:
        """提取场景图"""
        # 简化的场景图提取
        return {
            "objects": [],
            "relationships": [],
            "scene_type": "unknown"
        }
    
    def _analyze_road_network(self, roads: List) -> Dict:
        """分析道路网络"""
        return {
            "road_count": len(roads),
            "total_length": sum(r.get("length", 0) for r in roads),
            "road_types": list(set(r.get("type", "unknown") for r in roads))
        }
    
    def _categorize_pois(self, pois: List) -> Dict:
        """分类POI"""
        categories = {}
        for poi in pois:
            cat = poi.get("category", "unknown")
            categories[cat] = categories.get(cat, 0) + 1
        return categories
    
    def _extract_topology(self, roads: List, buildings: List) -> Dict:
        """提取拓扑关系"""
        return {
            "connectivity": "analyzed",
            "building_road_ratio": len(buildings) / max(len(roads), 1)
        }
    
    def _calculate_bounds(self, geometries: List) -> Dict:
        """计算边界框"""
        if not geometries:
            return {}
        
        coords = []
        for geom in geometries:
            if geom.get("type") == "Point":
                coords.append(geom["coordinates"])
            elif geom.get("type") in ["Polygon", "LineString"]:
                coords.extend(geom["coordinates"])
        
        if not coords:
            return {}
        
        lons = [c[0] for c in coords if len(c) >= 2]
        lats = [c[1] for c in coords if len(c) >= 2]
        
        return {
            "min_lon": min(lons) if lons else 0,
            "max_lon": max(lons) if lons else 0,
            "min_lat": min(lats) if lats else 0,
            "max_lat": max(lats) if lats else 0
        }
    
    def _calculate_area(self, geometries: List) -> float:
        """计算总面积"""
        # 简化的面积计算
        return 0.0
    
    def _analyze_flow_patterns(self, trajectories: List) -> Dict:
        """分析流动模式"""
        return {
            "pattern_count": len(trajectories),
            "avg_length": np.mean([t["length"] for t in trajectories]) if trajectories else 0
        }
    
    def _extract_entities(self, text: str) -> List:
        """提取实体"""
        # 简化的实体提取
        return []
