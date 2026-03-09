"""
Urban Agent Core: 城市空间智能体核心控制器
实现认知-理解-决策三层架构
"""

from typing import Dict, List, Any, Optional
import json
from dataclasses import dataclass, field


@dataclass
class SpatialContext:
    """空间上下文：包含原始数据、认知结果和决策建议"""
    # 原始数据
    location: str = ""
    bbox: tuple = (0, 0, 0, 0)
    crs: str = ""
    
    # 感知层输出
    raw_features: Dict[str, Any] = field(default_factory=dict)
    
    # 认知层输出
    spatial_understanding: Dict[str, Any] = field(default_factory=dict)
    semantic_graph: Dict[str, Any] = field(default_factory=dict)
    
    # 决策层输出
    design_proposals: List[Dict] = field(default_factory=list)
    intervention_areas: List[Dict] = field(default_factory=list)
    
    # 可视化输出
    svg_overlay: str = ""
    geojson_features: List[Dict] = field(default_factory=list)


class UrbanAgent:
    """
    城市空间智能体：整合感知、认知、决策三层能力
    
    工作流程：
    1. Perception: 从OSM获取并解析空间数据
    2. Cognition: 理解空间结构、识别模式、提取语义
    3. Decision: 基于认知结果生成空间决策建议
    """
    
    def __init__(self, llm_client=None):
        self.perception = None
        self.cognition = None
        self.decision = None
        self.llm = llm_client
        self._init_modules()
    
    def _init_modules(self):
        """延迟导入避免循环依赖"""
        from .perception import OSMProcessor
        from .cognition import SpatialCognition
        from .decision import SpatialDecision
        
        self.perception = OSMProcessor()
        self.cognition = SpatialCognition(self.llm)
        self.decision = SpatialDecision(self.llm)
    
    def analyze(self, location: str, task: str, radius: int = 500) -> SpatialContext:
        """
        执行完整的城市空间分析流程
        
        Args:
            location: 地理位置（地址或坐标）
            task: 分析任务描述
            radius: 分析半径（米）
            
        Returns:
            SpatialContext: 包含完整分析结果的空间上下文
        """
        print(f"\n{'='*60}")
        print(f"Urban Agent Analysis: {location}")
        print(f"Task: {task}")
        print(f"{'='*60}\n")
        
        # Step 1: 空间感知 - 获取原始数据
        print("[Step 1] Spatial Perception: Fetching and parsing OSM data...")
        raw_features = self.perception.process(location, radius)
        
        context = SpatialContext(
            location=location,
            bbox=raw_features.get('_bbox', (0, 0, 0, 0)),
            crs=raw_features.get('_crs', ''),
            raw_features=raw_features
        )
        
        # Step 2: 空间认知 - 理解空间结构
        print("\n[Step 2] Spatial Cognition: Understanding spatial patterns...")
        cognitive_result = self.cognition.understand(context, task)
        context.spatial_understanding = cognitive_result
        
        # Step 3: 空间决策 - 生成设计方案
        print("\n[Step 3] Spatial Decision: Generating design proposals...")
        decision_result = self.decision.decide(context, task)
        context.design_proposals = decision_result.get('proposals', [])
        context.intervention_areas = decision_result.get('interventions', [])
        
        # Step 4: 可视化生成
        print("\n[Step 4] Visualization: Creating aligned overlays...")
        self._generate_visualization(context)
        
        return context
    
    def _generate_visualization(self, context: SpatialContext):
        """生成与地图底图对齐的可视化"""
        from .visualization import SpatialVisualizer
        
        visualizer = SpatialVisualizer()
        
        # 生成SVG（与真实地理坐标对齐）
        context.svg_overlay = visualizer.create_svg_overlay(
            context.raw_features,
            context.intervention_areas,
            context.bbox
        )
        
        # 生成GeoJSON（可用于GIS软件）
        context.geojson_features = visualizer.create_geojson_features(
            context.intervention_areas,
            context.crs
        )
    
    def query(self, context: SpatialContext, question: str) -> str:
        """基于已分析的空间上下文回答问题"""
        prompt = f"""
        基于以下城市空间分析结果回答问题：
        
        位置: {context.location}
        
        空间理解:
        {json.dumps(context.spatial_understanding, indent=2, ensure_ascii=False)}
        
        设计方案:
        {json.dumps(context.design_proposals, indent=2, ensure_ascii=False)}
        
        用户问题: {question}
        
        请提供专业、准确的城市空间分析回答。
        """
        
        if self.llm:
            return self.llm.generate(prompt)
        return "LLM client not configured"
