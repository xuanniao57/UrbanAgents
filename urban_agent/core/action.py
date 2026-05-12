"""
Action Module
行动执行模块
"""

import json
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class ActionModule:
    """
    行动模块：执行决策和工具调用
    
    功能：
    - MCP工具调用
    - API交互
    - 结果格式化
    - 置信度评估
    """
    
    def __init__(
        self,
        mcp_client: Optional[Any] = None,
        llm_client: Optional[Any] = None,
        config: Optional[Dict] = None
    ):
        self.mcp_client = mcp_client
        self.llm_client = llm_client
        self.config = config or {}
        self.tool_runtime = self.config.get("tool_runtime", "mcp")
        self.mcp_tools = self.config.get("mcp_tools")
        
        # 工具注册表
        self.tools: Dict[str, Any] = {}
        self._register_default_tools()
    
    def _register_default_tools(self):
        """注册默认工具"""
        self.tools = {
            "geocode": self._tool_geocode,
            "reverse_geocode": self._tool_reverse_geocode,
            "calculate_distance": self._tool_calculate_distance,
            "get_poi": self._tool_get_poi,
            "analyze_image": self._tool_analyze_image,
            "query_osm": self._tool_query_osm,
            "spatial_analysis": self._tool_spatial_analysis
        }
    
    async def execute(
        self,
        reasoning_result: Dict,
        task: Dict
    ) -> Dict[str, Any]:
        """
        执行行动
        
        Args:
            reasoning_result: 推理结果
            task: 原始任务
            
        Returns:
            行动结果
        """
        logger.info("行动模块使用通用 planner-driven 路径")
        return await self._action_general(reasoning_result, task)
    
    async def _action_population(
        self,
        reasoning_result: Dict,
        task: Dict
    ) -> Dict[str, Any]:
        """执行人口预测行动"""
        population = reasoning_result.get("predicted_population", 0)
        confidence = reasoning_result.get("confidence", 0.7)
        
        # 格式化答案
        answer = f"The estimated population is {population}."
        
        return {
            "action_type": "population_prediction",
            "answer": answer,
            "numerical_answer": population,
            "selected_option": reasoning_result.get("selected_option"),
            "confidence": confidence,
            "reasoning": reasoning_result.get("reasoning_chain", [])
        }
    
    async def _action_objects(
        self,
        reasoning_result: Dict,
        task: Dict
    ) -> Dict[str, Any]:
        """执行目标检测行动"""
        objects = reasoning_result.get("detected_objects", [])
        confidence = reasoning_result.get("confidence", 0.75)
        
        # 格式化答案
        answer = f"Detected objects: {', '.join(objects)}."
        
        return {
            "action_type": "object_detection",
            "answer": answer,
            "objects": objects,
            "object_count": len(objects),
            "confidence": confidence
        }
    
    async def _action_geolocation(
        self,
        reasoning_result: Dict,
        task: Dict
    ) -> Dict[str, Any]:
        """执行地理定位行动"""
        city = reasoning_result.get("identified_city", "Unknown")
        confidence = reasoning_result.get("confidence", 0.6)
        
        # 格式化答案
        answer = f"The image appears to be from {city}."
        
        return {
            "action_type": "geolocation",
            "answer": answer,
            "identified_city": city,
            "confidence": confidence
        }
    
    async def _action_mobility(
        self,
        reasoning_result: Dict,
        task: Dict
    ) -> Dict[str, Any]:
        """执行移动性预测行动"""
        prediction = reasoning_result.get("predicted_location", "")
        confidence = reasoning_result.get("confidence", 0.6)
        
        answer = f"Predicted next location: {prediction}."
        
        return {
            "action_type": "mobility_prediction",
            "answer": answer,
            "predicted_location": prediction,
            "confidence": confidence
        }
    
    async def _action_traffic(
        self,
        reasoning_result: Dict,
        task: Dict
    ) -> Dict[str, Any]:
        """执行交通信号控制行动"""
        signal_plan = reasoning_result.get("signal_plan", {})
        confidence = reasoning_result.get("confidence", 0.7)
        
        green_time = signal_plan.get("green_time", 30)
        
        answer = f"Recommended green time: {green_time} seconds."
        
        return {
            "action_type": "traffic_signal",
            "answer": answer,
            "signal_plan": signal_plan,
            "selected_option": signal_plan.get("selected_option"),
            "selected_phase": signal_plan.get("selected_phase"),
            "confidence": confidence
        }
    
    async def _action_navigation(
        self,
        reasoning_result: Dict,
        task: Dict
    ) -> Dict[str, Any]:
        """执行导航行动"""
        route = reasoning_result.get("route", "")
        confidence = reasoning_result.get("confidence", 0.65)
        
        return {
            "action_type": "outdoor_navigation",
            "answer": route,
            "route": route,
            "route_actions": reasoning_result.get("route_actions", []),
            "start": reasoning_result.get("start", ""),
            "end": reasoning_result.get("end", ""),
            "confidence": confidence
        }
    
    async def _action_exploration(
        self,
        reasoning_result: Dict,
        task: Dict
    ) -> Dict[str, Any]:
        """执行城市探索行动"""
        exploration_plan = reasoning_result.get("exploration_plan", {})
        confidence = reasoning_result.get("confidence", 0.7)
        
        targets = exploration_plan.get("targets", [])
        answer = f"Exploration targets: {', '.join(targets)}."
        
        return {
            "action_type": "urban_exploration",
            "answer": answer,
            "exploration_plan": exploration_plan,
            "selected_option": exploration_plan.get("selected_option"),
            "selected_destination": exploration_plan.get("selected_destination"),
            "confidence": confidence
        }
    
    async def _action_general(
        self,
        reasoning_result: Dict,
        task: Dict
    ) -> Dict[str, Any]:
        """执行通用行动"""
        conclusion = reasoning_result.get("conclusion", "")
        confidence = reasoning_result.get("confidence", 0.5)
        
        return {
            "action_type": "general",
            "answer": conclusion,
            "confidence": confidence
        }
    
    async def call_tool(
        self,
        tool_name: str,
        params: Dict
    ) -> Dict[str, Any]:
        """
        调用工具
        
        Args:
            tool_name: 工具名称
            params: 工具参数
            
        Returns:
            工具执行结果
        """
        if self.tool_runtime == "mcp":
            try:
                if self.mcp_client and hasattr(self.mcp_client, "execute_tool"):
                    return self.mcp_client.execute_tool(tool_name, params)
                if self.mcp_tools is None and self.config.get("enable_builtin_mcp"):
                    from urban_agent.mcp_tools import get_mcp_tools

                    self.mcp_tools = get_mcp_tools()
                if self.mcp_tools is None:
                    return {"success": False, "error": "MCP runtime is not configured"}
                return self.mcp_tools.execute_tool(tool_name, params)
            except Exception as e:
                logger.error(f"MCP tool {tool_name} failed: {e}")
                return {"success": False, "error": str(e)}

        if tool_name in self.tools:
            try:
                result = await self.tools[tool_name](**params)
                return {"success": True, "result": result}
            except Exception as e:
                logger.error(f"Tool {tool_name} failed: {e}")
                return {"success": False, "error": str(e)}
        else:
            return {"success": False, "error": f"Tool {tool_name} not found"}
    
    # 工具实现
    async def _tool_geocode(self, address: str) -> Dict:
        """地理编码"""
        # 简化实现
        return {"address": address, "coordinates": [0, 0]}
    
    async def _tool_reverse_geocode(self, lat: float, lon: float) -> Dict:
        """逆地理编码"""
        return {"coordinates": [lat, lon], "address": "Unknown"}
    
    async def _tool_calculate_distance(
        self,
        point1: List[float],
        point2: List[float]
    ) -> Dict:
        """计算距离"""
        import math
        
        # 简化的距离计算
        lat1, lon1 = point1
        lat2, lon2 = point2
        
        # 使用Haversine公式
        R = 6371000  # 地球半径（米）
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        
        a = math.sin(delta_phi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        distance = R * c
        
        return {"distance": distance, "unit": "meters"}
    
    async def _tool_get_poi(
        self,
        location: List[float],
        radius: float = 1000,
        category: str = "all"
    ) -> Dict:
        """获取POI"""
        # 简化实现
        return {
            "location": location,
            "radius": radius,
            "category": category,
            "pois": []
        }
    
    async def _tool_analyze_image(self, image_path: str) -> Dict:
        """分析图像"""
        if self.llm_client:
            analysis = await self.llm_client.analyze_image(
                image_path,
                "Describe the main urban objects, layout, and spatial cues in this image."
            )
            return {"image": image_path, "analysis": analysis}
        return {"image": image_path, "analysis": "No VLM available"}
    
    async def _tool_query_osm(
        self,
        bbox: List[float],
        tags: List[str]
    ) -> Dict:
        """查询OSM数据"""
        return {"bbox": bbox, "tags": tags, "features": []}
    
    async def _tool_spatial_analysis(
        self,
        geometry: Dict,
        operation: str
    ) -> Dict:
        """空间分析"""
        return {
            "geometry": geometry,
            "operation": operation,
            "result": {}
        }
