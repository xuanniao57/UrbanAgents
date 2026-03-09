"""
Geospatial Tools
地理空间数据处理工具集
"""

import json
import logging
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
import numpy as np

# 数据处理库
try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

# 地理空间库
try:
    import geopandas as gpd
    from shapely.geometry import Point, Polygon, LineString, box
    from shapely.ops import unary_union
    HAS_GEOPANDAS = True
except ImportError:
    HAS_GEOPANDAS = False
    logging.warning("geopandas未安装，部分功能受限")

try:
    import rasterio
    from rasterio.plot import reshape_as_image
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False
    logging.warning("rasterio未安装，遥感影像处理受限")

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

logger = logging.getLogger(__name__)


class GeoDataLoader:
    """地理数据加载器"""
    
    @staticmethod
    def load_shapefile(filepath: str) -> Optional[gpd.GeoDataFrame]:
        """加载Shapefile"""
        if not HAS_GEOPANDAS:
            logger.error("geopandas未安装，无法加载Shapefile")
            return None
        
        try:
            gdf = gpd.read_file(filepath)
            logger.info(f"成功加载Shapefile: {filepath}, 记录数: {len(gdf)}")
            return gdf
        except Exception as e:
            logger.error(f"加载Shapefile失败: {e}")
            return None
    
    @staticmethod
    def load_geojson(filepath: str) -> Optional[Dict]:
        """加载GeoJSON"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data
        except Exception as e:
            logger.error(f"加载GeoJSON失败: {e}")
            return None
    
    @staticmethod
    def load_remote_sensing_image(filepath: str) -> Optional[np.ndarray]:
        """加载遥感影像"""
        if not HAS_RASTERIO:
            # 使用PIL作为备选
            if HAS_PIL:
                try:
                    img = Image.open(filepath)
                    return np.array(img)
                except Exception as e:
                    logger.error(f"PIL加载影像失败: {e}")
                    return None
            return None
        
        try:
            with rasterio.open(filepath) as src:
                image = src.read()
                # 转换为HWC格式
                if image.shape[0] in [1, 3, 4]:  # CHW格式
                    image = reshape_as_image(image)
                logger.info(f"成功加载遥感影像: {filepath}, 形状: {image.shape}")
                return image
        except Exception as e:
            logger.error(f"加载遥感影像失败: {e}")
            return None
    
    @staticmethod
    def load_citybench_remote_sensing(city: str, image_id: str, base_path: str) -> Optional[np.ndarray]:
        """加载CityBench遥感影像"""
        filepath = Path(base_path) / "citydata" / "remote_sensing" / city / f"{image_id}.png"
        if filepath.exists():
            return GeoDataLoader.load_remote_sensing_image(str(filepath))
        return None


class SpatialAnalyzer:
    """空间分析器"""
    
    @staticmethod
    def calculate_area(geometry) -> float:
        """计算面积"""
        if HAS_GEOPANDAS and geometry:
            return geometry.area
        return 0.0
    
    @staticmethod
    def calculate_distance(point1: Tuple[float, float], point2: Tuple[float, float]) -> float:
        """计算两点间距离（米）"""
        import math
        
        lat1, lon1 = point1
        lat2, lon2 = point2
        
        # Haversine公式
        R = 6371000  # 地球半径（米）
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        
        a = math.sin(delta_phi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return R * c
    
    @staticmethod
    def extract_bounding_box(gdf: gpd.GeoDataFrame) -> Dict:
        """提取边界框"""
        if not HAS_GEOPANDAS or gdf is None or gdf.empty:
            return {}
        
        bounds = gdf.total_bounds
        return {
            "min_x": bounds[0],
            "min_y": bounds[1],
            "max_x": bounds[2],
            "max_y": bounds[3],
            "center_x": (bounds[0] + bounds[2]) / 2,
            "center_y": (bounds[1] + bounds[3]) / 2
        }
    
    @staticmethod
    def analyze_road_network(gdf: gpd.GeoDataFrame) -> Dict:
        """分析道路网络"""
        if not HAS_GEOPANDAS or gdf is None:
            return {}
        
        # 计算总长度
        total_length = gdf.geometry.length.sum()
        
        # 道路类型统计
        road_types = {}
        if 'highway' in gdf.columns:
            road_types = gdf['highway'].value_counts().to_dict()
        
        return {
            "road_count": len(gdf),
            "total_length": float(total_length),
            "road_types": road_types,
            "avg_length": float(total_length / len(gdf)) if len(gdf) > 0 else 0
        }
    
    @staticmethod
    def analyze_buildings(gdf: gpd.GeoDataFrame) -> Dict:
        """分析建筑物"""
        if not HAS_GEOPANDAS or gdf is None:
            return {}
        
        # 计算总面积
        total_area = gdf.geometry.area.sum()
        
        # 建筑密度估算
        bounds = SpatialAnalyzer.extract_bounding_box(gdf)
        if bounds:
            bbox_area = (bounds["max_x"] - bounds["min_x"]) * (bounds["max_y"] - bounds["min_y"])
            density = total_area / bbox_area if bbox_area > 0 else 0
        else:
            density = 0
        
        return {
            "building_count": len(gdf),
            "total_area": float(total_area),
            "density": float(density),
            "avg_area": float(total_area / len(gdf)) if len(gdf) > 0 else 0
        }


class CityBenchDataLoader:
    """CityBench数据加载器"""
    
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.cities = ["Beijing", "London", "Paris", "Tokyo", "NewYork", "Mumbai", "Sydney", "Moscow", "Shanghai"]
    
    def load_city_shapefile(self, city: str) -> Optional[gpd.GeoDataFrame]:
        """加载城市Shapefile"""
        filepath = self.base_path / "citydata" / "EXP_ORIG_DATA" / city / f"{city}.shp"
        return GeoDataLoader.load_shapefile(str(filepath))
    
    def load_remote_sensing_dataset(self, city: str = "Paris") -> Dict:
        """加载遥感影像数据集"""
        # 加载标签文件
        label_file = self.base_path / "citydata" / "remote_sensing" / "all_city_img_object_set.json"
        
        if not label_file.exists():
            logger.warning(f"标签文件不存在: {label_file}")
            return {}
        
        try:
            with open(label_file, 'r') as f:
                labels = json.load(f)
            
            # 获取该城市的影像
            image_dir = self.base_path / "citydata" / "remote_sensing" / city
            if not image_dir.exists():
                logger.warning(f"影像目录不存在: {image_dir}")
                return {}
            
            images = list(image_dir.glob("*.png"))
            
            return {
                "city": city,
                "image_count": len(images),
                "labels": labels,
                "image_dir": str(image_dir)
            }
        except Exception as e:
            logger.error(f"加载遥感数据集失败: {e}")
            return {}
    
    def load_exploration_tasks(self, city: str) -> Optional[Any]:
        """加载城市探索任务"""
        if not HAS_PANDAS:
            return None
        
        filepath = self.base_path / "citydata" / "exploration_tasks" / f"case_{city}.csv"
        
        try:
            df = pd.read_csv(filepath)
            logger.info(f"成功加载探索任务: {city}, 任务数: {len(df)}")
            return df
        except Exception as e:
            logger.error(f"加载探索任务失败: {e}")
            return None
    
    def get_sample_task(self, task_type: str, city: str = "Paris") -> Dict:
        """获取示例任务"""
        if task_type == "remote_sensing":
            return self._get_remote_sensing_task(city)
        elif task_type == "urban_exploration":
            return self._get_exploration_task(city)
        else:
            return {}
    
    def _get_remote_sensing_task(self, city: str) -> Dict:
        """获取遥感任务"""
        dataset = self.load_remote_sensing_dataset(city)
        
        if not dataset:
            return {}
        
        # 获取第一张影像
        image_dir = Path(dataset["image_dir"])
        images = list(image_dir.glob("*.png"))
        
        if not images:
            return {}
        
        image_path = images[0]
        image_id = image_path.stem
        
        # 获取标签
        labels = dataset["labels"].get(image_id, {})
        
        return {
            "task_type": "object_detection",
            "image_path": str(image_path),
            "image_id": image_id,
            "ground_truth": labels,
            "city": city
        }
    
    def _get_exploration_task(self, city: str) -> Dict:
        """获取探索任务"""
        df = self.load_exploration_tasks(city)
        
        if df is None or df.empty:
            return {}
        
        # 获取第一个任务
        task = df.iloc[0]
        
        return {
            "task_type": "urban_exploration",
            "city": city,
            "start_location": task.get("start", ""),
            "target_categories": task.get("categories", []),
            "ground_truth": task.to_dict()
        }


class ImageProcessor:
    """图像处理器"""
    
    @staticmethod
    def preprocess_for_vlm(image: np.ndarray, target_size: Tuple[int, int] = (512, 512)) -> np.ndarray:
        """预处理图像用于VLM"""
        if not HAS_PIL:
            return image
        
        try:
            img = Image.fromarray(image)
            img = img.resize(target_size, Image.Resampling.LANCZOS)
            return np.array(img)
        except Exception as e:
            logger.error(f"图像预处理失败: {e}")
            return image
    
    @staticmethod
    def encode_for_api(image: np.ndarray) -> str:
        """编码图像用于API传输"""
        import base64
        from io import BytesIO
        
        try:
            img = Image.fromarray(image)
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            return base64.b64encode(buffered.getvalue()).decode()
        except Exception as e:
            logger.error(f"图像编码失败: {e}")
            return ""
    
    @staticmethod
    def analyze_image_statistics(image: np.ndarray) -> Dict:
        """分析图像统计信息"""
        return {
            "shape": image.shape,
            "dtype": str(image.dtype),
            "min": float(np.min(image)),
            "max": float(np.max(image)),
            "mean": float(np.mean(image)),
            "std": float(np.std(image))
        }


# 工具注册表
GEO_TOOLS = {
    "load_shapefile": GeoDataLoader.load_shapefile,
    "load_geojson": GeoDataLoader.load_geojson,
    "load_remote_sensing": GeoDataLoader.load_remote_sensing_image,
    "calculate_distance": SpatialAnalyzer.calculate_distance,
    "calculate_area": SpatialAnalyzer.calculate_area,
    "analyze_road_network": SpatialAnalyzer.analyze_road_network,
    "analyze_buildings": SpatialAnalyzer.analyze_buildings,
    "preprocess_image": ImageProcessor.preprocess_for_vlm,
    "encode_image": ImageProcessor.encode_for_api
}
