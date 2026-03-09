"""Backward-compatible sync UrbanAgent API."""

from dataclasses import dataclass, field
import json
from typing import Any, Dict, List


@dataclass
class SpatialContext:
    """空间上下文：包含原始数据、认知结果和决策建议。"""

    location: str = ""
    bbox: tuple = (0, 0, 0, 0)
    crs: str = ""
    raw_features: Dict[str, Any] = field(default_factory=dict)
    spatial_understanding: Dict[str, Any] = field(default_factory=dict)
    semantic_graph: Dict[str, Any] = field(default_factory=dict)
    design_proposals: List[Dict[str, Any]] = field(default_factory=list)
    intervention_areas: List[Dict[str, Any]] = field(default_factory=list)
    svg_overlay: str = ""
    geojson_features: List[Dict[str, Any]] = field(default_factory=list)


class UrbanAgent:
    """Legacy synchronous UrbanAgent kept for backward compatibility."""

    def __init__(self, llm_client=None):
        self.perception = None
        self.cognition = None
        self.decision = None
        self.llm = llm_client
        self._init_modules()

    def _init_modules(self):
        from .perception import OSMProcessor
        from .cognition import SpatialCognition
        from .decision import SpatialDecision

        self.perception = OSMProcessor()
        self.cognition = SpatialCognition(self.llm)
        self.decision = SpatialDecision(self.llm)

    def analyze(self, location: str, task: str, radius: int = 500) -> SpatialContext:
        raw_features = self.perception.process(location, radius)

        context = SpatialContext(
            location=location,
            bbox=raw_features.get("_bbox", (0, 0, 0, 0)),
            crs=raw_features.get("_crs", ""),
            raw_features=raw_features,
        )

        cognitive_result = self.cognition.understand(context, task)
        context.spatial_understanding = cognitive_result

        decision_result = self.decision.decide(context, task)
        context.design_proposals = decision_result.get("proposals", [])
        context.intervention_areas = decision_result.get("interventions", [])

        self._generate_visualization(context)
        return context

    def _generate_visualization(self, context: SpatialContext):
        from .visualization import SpatialVisualizer

        visualizer = SpatialVisualizer()
        context.svg_overlay = visualizer.create_svg_overlay(
            context.raw_features,
            context.intervention_areas,
            context.bbox,
        )
        context.geojson_features = visualizer.create_geojson_features(
            context.intervention_areas,
            context.crs,
        )

    def query(self, context: SpatialContext, question: str) -> str:
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