"""
Reasoning Module
空间推理与决策模块
"""

import json
import logging
import re
from typing import Dict, List, Any, Optional

from ..adapters import TrafficSignalAdapter

logger = logging.getLogger(__name__)


class ReasoningModule:
    """
    推理模块：基于场景图和知识图谱的空间推理
    
    推理能力：
    - 场景图生成与解析
    - 空间关系推理（拓扑、方向、距离）
    - 城市知识图谱查询
    - 决策序列生成
    """
    
    def __init__(
        self,
        llm_client: Optional[Any] = None,
        config: Optional[Dict] = None
    ):
        self.llm_client = llm_client
        self.config = config or {}
        self.mode = self.config.get("mode", "enhanced")
        self.traffic_adapter = TrafficSignalAdapter()
        self.knowledge_graph = self._init_knowledge_graph()
        
    def _init_knowledge_graph(self) -> Dict:
        """初始化知识图谱"""
        return {
            "spatial_relations": {
                "topological": ["contains", "within", "intersects", "disjoint", "touches"],
                "directional": ["north", "south", "east", "west", "northeast", "northwest", "southeast", "southwest"],
                "distance": ["near", "far", "adjacent", "distant"]
            },
            "urban_elements": {
                "land_use": ["residential", "commercial", "industrial", "green_space", "transportation"],
                "infrastructure": ["roads", "buildings", "utilities", "public_transport"],
                "amenities": ["schools", "hospitals", "parks", "shops", "restaurants"]
            }
        }

    def _is_enhanced_mode(self) -> bool:
        return str(self.mode).lower() != "legacy"

    def _extract_first_number(self, text: str) -> Optional[float]:
        if not text:
            return None
        match = re.search(r"-?\d+(?:,\d{3})*(?:\.\d+)?", text)
        if not match:
            return None
        return float(match.group(0).replace(",", ""))

    def _extract_choice_letter(self, text: str, choices: Dict[str, Any]) -> Optional[str]:
        if not text:
            return None
        upper_text = text.upper()
        for key in choices:
            if re.search(rf"\b{re.escape(str(key).upper())}\b", upper_text):
                return str(key).upper()
        for key, value in choices.items():
            if str(value).lower() in text.lower():
                return str(key).upper()
        return None

    def _normalize_time(self, time_value: Any) -> int:
        if isinstance(time_value, (int, float)):
            return int(time_value)
        if isinstance(time_value, str):
            match = re.search(r"(\d{1,2}):(\d{2})", time_value)
            if match:
                hour = int(match.group(1))
                minute = int(match.group(2))
                if "PM" in time_value.upper() and hour != 12:
                    hour += 12
                if "AM" in time_value.upper() and hour == 12:
                    hour = 0
                return hour * 60 + minute
        return 0

    def _infer_next_place(self, historical_data: List, context_stay: List, target_stay: Any) -> Optional[int]:
        candidates: Dict[int, float] = {}

        if isinstance(target_stay, (list, tuple)) and len(target_stay) >= 2:
            target_minute = self._normalize_time(target_stay[0])
            target_weekday = str(target_stay[1]).lower()
        else:
            target_minute = 0
            target_weekday = ""

        for stay in historical_data:
            if not isinstance(stay, (list, tuple)) or len(stay) < 3:
                continue
            place_id = stay[2]
            if place_id is None:
                continue
            score = 1.0
            if str(stay[1]).lower() == target_weekday:
                score += 2.0
            time_delta = abs(self._normalize_time(stay[0]) - target_minute)
            score += max(0.0, 1.5 - min(time_delta, 360) / 240.0)
            candidates[int(place_id)] = candidates.get(int(place_id), 0.0) + score

        for index, stay in enumerate(context_stay):
            if not isinstance(stay, (list, tuple)) or len(stay) < 3:
                continue
            place_id = stay[2]
            if place_id is None:
                continue
            recency_bonus = 2.5 + index
            candidates[int(place_id)] = candidates.get(int(place_id), 0.0) + recency_bonus

        if not candidates:
            return None

        ranked = sorted(candidates.items(), key=lambda item: item[1], reverse=True)
        return ranked[0][0]

    def _build_navigation_summary(self, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        actions = [str(step.get("action", "")).lower() for step in steps if step.get("action")]
        sentences = []
        for idx, action in enumerate(actions, start=1):
            if action == "forward":
                sentence = f"Step {idx}: continue forward."
            elif action == "left":
                sentence = f"Step {idx}: turn left at the next intersection."
            elif action == "right":
                sentence = f"Step {idx}: turn right at the next intersection."
            elif action == "stop":
                sentence = f"Step {idx}: stop at the destination."
            else:
                sentence = f"Step {idx}: {action}."
            sentences.append(sentence)
        return {
            "actions": actions,
            "text": " ".join(sentences)
        }

    def _select_best_exploration_candidate(self, candidates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not candidates:
            return None
        ranked = sorted(
            candidates,
            key=lambda item: (
                -float(item.get("completion", 0.0)),
                float(item.get("average_step", 9999.0)),
                float(item.get("success_time", 9999.0))
            )
        )
        return ranked[0]

    def _memory_records(self, memory_context: Dict) -> List[Dict[str, Any]]:
        records = []
        if not isinstance(memory_context, dict):
            return records

        working = memory_context.get("working")
        if isinstance(working, dict) and working:
            records.append(working)

        for item in memory_context.get("relevant_short_term", []):
            if isinstance(item, dict):
                records.append(item)

        long_term = memory_context.get("relevant_long_term", {})
        if isinstance(long_term, dict):
            for group in long_term.values():
                if isinstance(group, list):
                    for item in group:
                        if isinstance(item, dict):
                            experience = item.get("experience") if isinstance(item.get("experience"), dict) else item
                            if isinstance(experience, dict):
                                records.append(experience)

        best_match = memory_context.get("best_match")
        if isinstance(best_match, dict):
            experience = best_match.get("experience") if isinstance(best_match.get("experience"), dict) else best_match
            if isinstance(experience, dict):
                records.append(experience)

        return records

    def _find_memory_value(self, memory_context: Dict, predicate) -> Optional[Any]:
        for record in self._memory_records(memory_context):
            value = predicate(record)
            if value is not None:
                return value
        return None
    
    async def infer(
        self,
        perception_data: Dict,
        memory_context: Dict,
        task: Dict
    ) -> Dict[str, Any]:
        """
        执行推理
        
        Args:
            perception_data: 感知数据
            memory_context: 记忆上下文
            task: 任务定义
            
        Returns:
            推理结果
        """
        task_type = task.get("task_type", "unknown")
        
        logger.info(f"推理模块处理任务类型: {task_type}")
        
        # 根据任务类型选择推理策略
        if task_type == "population_prediction":
            return await self._reason_population(perception_data, memory_context, task)
        elif task_type == "object_detection":
            return await self._reason_objects(perception_data, memory_context, task)
        elif task_type == "geolocation":
            return await self._reason_geolocation(perception_data, memory_context, task)
        elif task_type == "geoqa":
            return await self._reason_geoqa(perception_data, memory_context, task)
        elif task_type == "mobility_prediction":
            return await self._reason_mobility(perception_data, memory_context, task)
        elif task_type == "traffic_signal":
            return await self._reason_traffic(perception_data, memory_context, task)
        elif task_type == "outdoor_navigation":
            return await self._reason_navigation(perception_data, memory_context, task)
        elif task_type == "urban_exploration":
            return await self._reason_exploration(perception_data, memory_context, task)
        else:
            return await self._general_reasoning(perception_data, memory_context, task)
    
    async def _reason_population(
        self,
        perception_data: Dict,
        memory_context: Dict,
        task: Dict
    ) -> Dict[str, Any]:
        """人口预测推理"""
        # 分析遥感影像特征
        features = perception_data.get("features", {})
        land_use = features.get("land_use", [])
        density = features.get("density", "unknown")
        
        # 基于土地利用和建筑密度推理人口
        reasoning_chain = [
            f"Observed land use types: {land_use}",
            f"Building density: {density}",
            "Analyzing urban morphology patterns...",
            "Estimating population based on residential area and density..."
        ]
        
        choices = task.get("choices", {})
        indicators = task.get("indicator_values", {})

        if self._is_enhanced_mode() and indicators:
            nightlight = float(indicators.get("nightlight") or 0)
            carbon = float(indicators.get("carbon") or 0)
            population = max(0, int(nightlight * 80 + carbon * 2.5))
            response = f"Estimated population: {population}"
        elif self.llm_client:
            prompt = f"""Based on the following urban features, estimate the population:
            Land use: {land_use}
            Density: {density}
            
            Provide a numerical estimate and reasoning."""
            
            try:
                response = await self.llm_client.generate(prompt)
                population = int(self._extract_first_number(response) or 1000)
            except:
                population = 1000
        else:
            # 简单的启发式规则
            population = self._heuristic_population(land_use, density)
            response = f"Estimated population: {population}"

        if self._is_enhanced_mode() and choices and self.llm_client:
            nearest_choice = min(
                choices.items(),
                key=lambda item: abs(float(item[1]) - float(population))
            )
            selected_option = str(nearest_choice[0]).upper()
        else:
            selected_option = None
        
        return {
            "task_type": "population_prediction",
            "reasoning_chain": reasoning_chain,
            "conclusion": response,
            "predicted_population": population,
            "selected_option": selected_option,
            "confidence": 0.7,
            "evidence": {
                "land_use": land_use,
                "density": density
            }
        }
    
    async def _reason_objects(
        self,
        perception_data: Dict,
        memory_context: Dict,
        task: Dict
    ) -> Dict[str, Any]:
        """目标检测推理"""
        description = perception_data.get("description", "")
        
        # 从描述中提取物体
        reasoning_chain = [
            "Analyzing image content...",
            "Identifying urban objects...",
            "Classifying object categories..."
        ]
        
        if self.llm_client and description:
            prompt = f"""List all objects visible in this urban scene:
            {description}
            
            Format: Object1, Object2, Object3..."""
            
            try:
                response = await self.llm_client.generate(prompt)
                objects = [obj.strip() for obj in response.split(",")]
            except:
                objects = ["building", "road", "vehicle"]
        else:
            objects = self._extract_objects_heuristic(description)
            response = ", ".join(objects)
        
        return {
            "task_type": "object_detection",
            "reasoning_chain": reasoning_chain,
            "detected_objects": objects,
            "object_count": len(objects),
            "conclusion": response,
            "confidence": 0.75
        }
    
    async def _reason_geolocation(
        self,
        perception_data: Dict,
        memory_context: Dict,
        task: Dict
    ) -> Dict[str, Any]:
        """地理定位推理"""
        description = perception_data.get("description", "")
        
        reasoning_chain = [
            "Analyzing visual features...",
            "Matching with known geographic patterns...",
            "Identifying distinctive landmarks..."
        ]
        
        city_options = task.get("city_options", [])

        if self.llm_client and description:
            prompt = f"""Based on these visual features, identify the city:
            {description}
            
            Consider: architecture style, street layout, vegetation, signage, vehicles.
            Choose exactly one city from: {', '.join(city_options) if city_options else 'the most likely city'}.
            Return only the city name."""
            
            try:
                response = await self.llm_client.generate(prompt)
                # 提取城市名
                cities = city_options or ["Beijing", "London", "Paris", "Tokyo", "NewYork", "Mumbai", "Sydney"]
                identified_city = None
                for city in cities:
                    if city.lower() in response.lower():
                        identified_city = city
                        break
                if not identified_city:
                    identified_city = "Unknown"
            except:
                identified_city = "Unknown"
                response = "Could not identify city"
        else:
            identified_city = "Unknown"
            response = "Insufficient data for geolocation"
        
        return {
            "task_type": "geolocation",
            "reasoning_chain": reasoning_chain,
            "identified_city": identified_city,
            "conclusion": response,
            "confidence": 0.6 if identified_city != "Unknown" else 0.3
        }
    
    async def _reason_geoqa(
        self,
        perception_data: Dict,
        memory_context: Dict,
        task: Dict
    ) -> Dict[str, Any]:
        """地理问答推理"""
        question = task.get("question", "")
        
        reasoning_chain = [
            f"Question: {question}",
            "Retrieving relevant spatial information...",
            "Analyzing geographic relationships...",
            "Formulating answer..."
        ]
        
        choices = task.get("choices", {})
        context = json.dumps(perception_data, indent=2, default=str)
        
        if self.llm_client:
            prompt = f"""Answer this geographic question based on the provided context:
            
            Question: {question}
            
            Context: {context}
            
            Choices: {json.dumps(choices, ensure_ascii=False) if choices else 'No fixed choices'}
            
            Provide a concise answer. If choices are provided, answer with the option letter and the final answer."""
            
            try:
                answer = await self.llm_client.generate(prompt)
            except:
                answer = "Unable to answer based on available information"
        else:
            answer = "LLM not available for reasoning"

        selected_option = self._extract_choice_letter(answer, choices) if choices else None
        
        return {
            "task_type": "geoqa",
            "reasoning_chain": reasoning_chain,
            "question": question,
            "answer": answer,
            "selected_option": selected_option,
            "confidence": 0.65
        }
    
    async def _reason_mobility(
        self,
        perception_data: Dict,
        memory_context: Dict,
        task: Dict
    ) -> Dict[str, Any]:
        """移动性预测推理"""
        flow_patterns = perception_data.get("flow_patterns", {})
        historical_data = task.get("historical_data", [])
        context_stay = task.get("context_stay", [])
        target_stay = task.get("target_stay")
        
        reasoning_chain = [
            "Analyzing historical trajectory patterns...",
            "Identifying movement trends...",
            "Predicting future mobility flows..."
        ]
        
        avg_length = flow_patterns.get("avg_length", 0)
        pattern_count = flow_patterns.get("pattern_count", 0)

        memory_prediction = self._find_memory_value(
            memory_context,
            lambda record: record.get("action", {}).get("predicted_location")
            if record.get("task", {}).get("task_type") == "mobility_prediction" and record.get("task", {}).get("city") == task.get("city")
            else None,
        )

        if self._is_enhanced_mode() and (historical_data or context_stay):
            prediction = self._infer_next_place(historical_data, context_stay, target_stay)
            if prediction is None:
                prediction = memory_prediction or "commercial_area"
        elif self._is_enhanced_mode() and memory_prediction is not None:
            prediction = memory_prediction
        elif self.llm_client:
            prompt = f"""Predict mobility flow based on:
            Average trajectory length: {avg_length}
            Number of patterns: {pattern_count}
            Historical stays: {historical_data}
            Recent context: {context_stay}
            Target stay: {target_stay}
            
            Predict the next location place ID or location category."""
            
            try:
                raw_prediction = await self.llm_client.generate(prompt)
                prediction = int(self._extract_first_number(raw_prediction)) if self._extract_first_number(raw_prediction) is not None else raw_prediction
            except:
                prediction = "commercial_area"
        else:
            prediction = "commercial_area" if pattern_count > 10 else "residential_area"
        
        return {
            "task_type": "mobility_prediction",
            "reasoning_chain": reasoning_chain,
            "predicted_location": prediction,
            "confidence": 0.6,
            "evidence": {
                "flow_patterns": flow_patterns,
                "historical_data": historical_data,
                "context_stay": context_stay,
                "target_stay": target_stay
            }
        }
    
    async def _reason_traffic(
        self,
        perception_data: Dict,
        memory_context: Dict,
        task: Dict
    ) -> Dict[str, Any]:
        """交通信号控制推理"""
        road_network = perception_data.get("road_network", {})
        
        reasoning_chain = [
            "Analyzing traffic flow data...",
            "Evaluating intersection conditions...",
            "Optimizing signal timing..."
        ]
        
        queue_lengths = task.get("queue_lengths", {})
        phase_options = task.get("phase_options", [])
        road_count = road_network.get("road_count", 0)
        memory_phase = self._find_memory_value(
            memory_context,
            lambda record: record.get("action", {}).get("selected_phase")
            if record.get("task", {}).get("task_type") == "traffic_signal" and record.get("task", {}).get("city") == task.get("city")
            else None,
        )

        if self._is_enhanced_mode() and phase_options:
            best_option = max(
                phase_options,
                key=lambda item: (
                    int(item.get("waiting_vehicle_count", 0)),
                    int(item.get("vehicle_count", 0)),
                )
            )
            selected_option = best_option.get("option")
            selected_phase = task.get("phase_map", {}).get(selected_option, selected_option)
            green_time = min(25 + int(best_option.get("waiting_vehicle_count", 0)) * 3, 90)
        elif self._is_enhanced_mode() and queue_lengths:
            proxy_task = self.traffic_adapter.build_task_from_queue_lengths(
                city=task.get("city", "unknown"),
                queue_lengths=queue_lengths,
                current_phase=task.get("current_phase"),
            )
            selected_option = self.traffic_adapter.pick_default_option(proxy_task)
            selected_phase = proxy_task.get("phase_map", {}).get(selected_option, selected_option)
            green_time = min(25 + int(max(queue_lengths.values())) * 3, 90)
        elif self._is_enhanced_mode() and memory_phase is not None:
            selected_option = None
            selected_phase = memory_phase
            green_time = 45
        else:
            selected_option = None
            selected_phase = "north_south"
            green_time = min(30 + road_count * 5, 90)
        
        return {
            "task_type": "traffic_signal",
            "reasoning_chain": reasoning_chain,
            "signal_plan": {
                "selected_option": selected_option,
                "selected_phase": selected_phase,
                "green_time": green_time,
                "yellow_time": 5,
                "red_time": green_time
            },
            "confidence": 0.7
        }
    
    async def _reason_navigation(
        self,
        perception_data: Dict,
        memory_context: Dict,
        task: Dict
    ) -> Dict[str, Any]:
        """户外导航推理"""
        road_network = perception_data.get("road_network", {})
        topology = perception_data.get("topology", {})
        
        reasoning_chain = [
            "Analyzing road network structure...",
            "Evaluating route options...",
            "Selecting optimal path..."
        ]
        
        steps = task.get("steps", [])
        start = task.get("start", "current_location")
        end = task.get("end", "destination")
        memory_route = self._find_memory_value(
            memory_context,
            lambda record: record.get("action", {}).get("route_actions")
            if record.get("task", {}).get("task_type") == "outdoor_navigation"
            and record.get("task", {}).get("start") == start
            and record.get("task", {}).get("end") == end
            else None,
        )

        if self._is_enhanced_mode() and steps:
            summary = self._build_navigation_summary(steps)
            directions = summary["text"]
            route_actions = summary["actions"]
        elif self._is_enhanced_mode() and memory_route:
            route_actions = [str(item).lower() for item in memory_route]
            directions = self._build_navigation_summary([
                {"action": action} for action in route_actions
            ])["text"]
        elif self.llm_client:
            prompt = f"""Generate navigation directions from {start} to {end}.
            Road network: {road_network}
            
            Provide step-by-step directions."""
            
            try:
                directions = await self.llm_client.generate(prompt)
            except:
                directions = f"Head towards {end}"
            route_actions = []
        else:
            directions = f"Head towards {end}"
            route_actions = []
        
        return {
            "task_type": "outdoor_navigation",
            "reasoning_chain": reasoning_chain,
            "route": directions,
            "route_actions": route_actions,
            "start": start,
            "end": end,
            "confidence": 0.65
        }
    
    async def _reason_exploration(
        self,
        perception_data: Dict,
        memory_context: Dict,
        task: Dict
    ) -> Dict[str, Any]:
        """城市探索推理"""
        poi_categories = perception_data.get("poi_categories", {})
        
        reasoning_chain = [
            "Analyzing POI distribution...",
            "Identifying exploration targets...",
            "Planning exploration sequence..."
        ]
        
        candidates = task.get("candidates", [])
        memory_destination = self._find_memory_value(
            memory_context,
            lambda record: record.get("action", {}).get("selected_destination")
            if record.get("task", {}).get("task_type") == "urban_exploration"
            and record.get("task", {}).get("city") == task.get("city")
            else None,
        )

        if self._is_enhanced_mode() and candidates:
            if memory_destination:
                remembered = next(
                    (candidate for candidate in candidates if candidate.get("des_name") == memory_destination),
                    None,
                )
            else:
                remembered = None
            best_candidate = remembered or self._select_best_exploration_candidate(candidates)
            exploration_plan = {
                "targets": [best_candidate.get("des_name", "")],
                "priority": "high",
                "selected_option": best_candidate.get("option"),
                "selected_destination": best_candidate.get("des_name")
            }
        else:
            top_categories = sorted(poi_categories.items(), key=lambda x: x[1], reverse=True)[:3]
            exploration_plan = {
                "targets": [cat[0] for cat in top_categories],
                "priority": "high" if len(top_categories) > 0 else "low"
            }
        
        return {
            "task_type": "urban_exploration",
            "reasoning_chain": reasoning_chain,
            "exploration_plan": exploration_plan,
            "confidence": 0.7
        }
    
    async def _general_reasoning(
        self,
        perception_data: Dict,
        memory_context: Dict,
        task: Dict
    ) -> Dict[str, Any]:
        """通用推理"""
        reasoning_chain = [
            "Processing perception data...",
            "Applying general spatial reasoning...",
            "Generating response..."
        ]
        
        return {
            "task_type": "general",
            "reasoning_chain": reasoning_chain,
            "conclusion": "General reasoning completed",
            "confidence": 0.5
        }
    
    def _heuristic_population(self, land_use: List, density: str) -> int:
        """启发式人口估计"""
        base = 1000
        
        if "residential" in land_use:
            base *= 5
        if "commercial" in land_use:
            base *= 2
        
        if density == "high":
            base *= 10
        elif density == "medium":
            base *= 5
        
        return base
    
    def _extract_objects_heuristic(self, description: str) -> List[str]:
        """启发式物体提取"""
        common_objects = ["building", "road", "vehicle", "tree", "person", "sign"]
        found = []
        for obj in common_objects:
            if obj in description.lower():
                found.append(obj)
        return found if found else ["building", "road"]
