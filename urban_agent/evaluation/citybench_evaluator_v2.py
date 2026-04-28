"""
CityBench Evaluator V2
改进版评估器 - 统一评估裸模型和Agent，对齐CityBench三维指标

核心改进:
1. 裸模型和Agent使用同一套Task Outcome评估标准
2. State Perception和Decision Sequence仅针对Agent评估，裸模型标记为N/A
3. 引入"推理深度"和"工具使用"作为Agent特有能力的评估维度
4. 最终得分采用加权平均，但区分裸模型和Agent的权重
"""

import json
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path
import numpy as np

logger = logging.getLogger(__name__)


class CityBenchEvaluatorV2:
    """
    CityBench评估器 V2
    
    三维评估框架（对齐CityBench论文）：
    1. State Perception (状态感知) - 仅Agent
    2. Decision Sequence (决策序列) - 仅Agent  
    3. Task Outcome (任务结果) - 裸模型和Agent统一评估
    
    新增维度:
    4. Reasoning Depth (推理深度) - 评估推理过程质量
    5. Tool Usage (工具使用) - 评估工具调用能力
    """
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.results: List[Dict] = []
        
    def evaluate_task(
        self,
        task_type: str,
        prediction: Any,
        ground_truth: Any,
        agent_output: Dict,
        is_bare_model: bool = False
    ) -> Dict[str, Any]:
        """
        评估单个任务
        
        Args:
            task_type: 任务类型
            prediction: 预测结果
            ground_truth: 真实标签
            agent_output: 智能体完整输出
            is_bare_model: 是否为裸模型（无Agent架构）
            
        Returns:
            评估结果
        """
        # 1. Task Outcome Metrics - 统一评估（核心指标）
        task_outcome = self._evaluate_task_outcome(
            task_type, prediction, ground_truth
        )
        
        result = {
            "task_type": task_type,
            "is_bare_model": is_bare_model,
            "task_outcome": task_outcome,
        }
        
        # 2. State Perception & Decision Sequence - 仅Agent
        if not is_bare_model:
            state_perception = self._evaluate_state_perception(agent_output, task_type)
            decision_sequence = self._evaluate_decision_sequence(agent_output, task_type)
            reasoning_depth = self._evaluate_reasoning_depth(agent_output)
            tool_usage = self._evaluate_tool_usage(agent_output)
            
            result.update({
                "state_perception": state_perception,
                "decision_sequence": decision_sequence,
                "reasoning_depth": reasoning_depth,
                "tool_usage": tool_usage,
            })
            
            # Agent总体得分：多维度加权
            result["overall_score"] = self._calculate_agent_score(
                task_outcome, state_perception, decision_sequence, 
                reasoning_depth, tool_usage
            )
        else:
            # 裸模型总体得分：仅Task Outcome
            result["overall_score"] = task_outcome.get("accuracy", 0)
            
            # 裸模型的其他维度标记为N/A
            result.update({
                "state_perception": {"status": "N/A", "note": "裸模型无感知模块"},
                "decision_sequence": {"status": "N/A", "note": "裸模型无决策序列"},
                "reasoning_depth": {"status": "N/A", "note": "裸模型无显式推理"},
                "tool_usage": {"status": "N/A", "note": "裸模型无工具使用"},
            })
        
        self.results.append(result)
        return result
    
    def _evaluate_task_outcome(
        self,
        task_type: str,
        prediction: Any,
        ground_truth: Any
    ) -> Dict:
        """
        评估任务结果维度 - 对齐CityBench官方指标
        
        所有任务类型都使用CityBench定义的核心指标
        """
        evaluators = {
            "population_prediction": self._eval_population,
            "object_detection": self._eval_object_detection,
            "geolocation": self._eval_geolocation,
            "geoqa": self._eval_geoqa,
            "mobility_prediction": self._eval_mobility,
            "traffic_signal": self._eval_traffic_signal,
            "outdoor_navigation": self._eval_navigation,
            "urban_exploration": self._eval_exploration,
        }
        
        evaluator = evaluators.get(task_type, self._eval_default)
        return evaluator(prediction, ground_truth)
    
    def _eval_population(self, prediction: Any, ground_truth: Any) -> Dict:
        """
        人口预测评估 - CityBench指标: RMSE, r2
        
        评估逻辑:
        - 相对误差 < 20%: 优秀 (1.0)
        - 相对误差 < 50%: 良好 (0.7)
        - 相对误差 < 100%: 及格 (0.4)
        - 相对误差 >= 100%: 不及格 (0.0-0.4)
        """
        try:
            pred_val = float(prediction) if prediction else 0
            gt_val = float(ground_truth) if ground_truth else 1
            
            # 避免除零
            if gt_val == 0:
                gt_val = 1
            
            # 相对误差
            relative_error = abs(pred_val - gt_val) / gt_val
            
            # 分段评分
            if relative_error < 0.2:
                accuracy = 1.0
            elif relative_error < 0.5:
                accuracy = 0.7
            elif relative_error < 1.0:
                accuracy = 0.4
            else:
                accuracy = max(0, 1 - relative_error * 0.5)
            
            # 计算RMSE和r2（用于报告）
            mse = (pred_val - gt_val) ** 2
            rmse = np.sqrt(mse)
            
            return {
                "accuracy": accuracy,
                "relative_error": relative_error,
                "rmse": rmse,
                "predicted": pred_val,
                "ground_truth": gt_val,
                "metric_type": "RMSE"
            }
        except:
            return {"accuracy": 0.0, "error": "Invalid prediction"}
    
    def _eval_object_detection(self, prediction: Any, ground_truth: Any) -> Dict:
        """
        目标检测评估 - CityBench指标: Infrastructure_Accuracy
        
        评估逻辑:
        - 使用F1分数评估检测质量
        - 考虑检测数量和类别匹配
        """
        try:
            pred_objects = set(str(o).lower().strip() for o in prediction) if isinstance(prediction, list) else set()
            gt_objects = set(str(o).lower().strip() for o in ground_truth) if isinstance(ground_truth, list) else set()
            
            # 如果没有ground_truth，使用默认对象列表评估
            if len(gt_objects) == 0:
                # 默认城市基础设施对象
                gt_objects = {
                    "building", "road", "bridge", "vehicle", "tree",
                    "sidewalk", "intersection", "park", "water", "infrastructure"
                }
            
            # 计算匹配
            matches = 0
            for pred in pred_objects:
                for gt in gt_objects:
                    if pred in gt or gt in pred:
                        matches += 1
                        break
            
            # 精确率和召回率
            precision = matches / len(pred_objects) if pred_objects else 0
            recall = min(1.0, matches / len(gt_objects)) if gt_objects else 0
            
            # F1分数
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
            
            return {
                "accuracy": f1,
                "precision": precision,
                "recall": recall,
                "f1_score": f1,
                "detected_count": len(pred_objects),
                "metric_type": "F1"
            }
        except:
            return {"accuracy": 0.0, "error": "Invalid prediction"}
    
    def _eval_geolocation(self, prediction: Any, ground_truth: Any) -> Dict:
        """
        地理定位评估 - CityBench指标: City_Accuracy, Acc@25km
        
        评估逻辑:
        - 精确匹配: 1.0
        - 不匹配: 0.0
        - Top-K评估: 如果提供候选列表，检查是否在Top-3中
        """
        try:
            pred_city = str(prediction).lower().strip() if prediction else ""
            gt_city = str(ground_truth).lower().strip() if ground_truth else ""

            if not pred_city or not gt_city:
                return {
                    "accuracy": 0.0,
                    "exact_match": 0.0,
                    "partial_match": 0.0,
                    "predicted": prediction,
                    "ground_truth": ground_truth,
                    "metric_type": "City_Accuracy"
                }
            
            # 精确匹配
            exact_match = 1.0 if pred_city == gt_city else 0.0
            
            # 部分匹配（城市名包含关系）
            partial_match = 0.0
            if exact_match == 0:
                if gt_city in pred_city or pred_city in gt_city:
                    partial_match = 0.5
            
            accuracy = max(exact_match, partial_match)
            
            return {
                "accuracy": accuracy,
                "exact_match": exact_match,
                "partial_match": partial_match,
                "predicted": prediction,
                "ground_truth": ground_truth,
                "metric_type": "City_Accuracy"
            }
        except:
            return {"accuracy": 0.0, "error": "Invalid prediction"}
    
    def _eval_geoqa(self, prediction: Any, ground_truth: Any) -> Dict:
        """
        地理问答评估 - CityBench指标: GeoQA_Average_Accuracy
        
        评估逻辑:
        - 关键词匹配
        - 语义相似度（简化版）
        """
        try:
            pred_answer = str(prediction).lower().strip() if prediction else ""
            gt_answer = str(ground_truth).lower().strip() if ground_truth else ""

            if not pred_answer or not gt_answer:
                return {
                    "accuracy": 0.0,
                    "match_type": "empty",
                    "predicted": prediction,
                    "ground_truth": ground_truth,
                    "metric_type": "GeoQA_Accuracy"
                }
            
            # 直接包含匹配
            if gt_answer in pred_answer or pred_answer in gt_answer:
                return {
                    "accuracy": 1.0,
                    "match_type": "exact",
                    "predicted": prediction,
                    "ground_truth": ground_truth,
                    "metric_type": "GeoQA_Accuracy"
                }
            
            # 关键词匹配
            pred_words = set(pred_answer.split())
            gt_words = set(gt_answer.split())
            
            if len(gt_words) > 0:
                overlap = len(pred_words & gt_words) / len(gt_words)
                accuracy = 1.0 if overlap > 0.5 else (0.5 if overlap > 0.2 else 0.0)
            else:
                accuracy = 0.0
            
            return {
                "accuracy": accuracy,
                "match_type": "keyword",
                "predicted": prediction,
                "ground_truth": ground_truth,
                "metric_type": "GeoQA_Accuracy"
            }
        except:
            return {"accuracy": 0.0, "error": "Invalid prediction"}
    
    def _eval_mobility(self, prediction: Any, ground_truth: Any) -> Dict:
        """
        移动性预测评估 - CityBench指标: Acc@1, F1
        
        评估逻辑:
        - 类别精确匹配
        """
        try:
            pred_loc = str(prediction).lower().strip() if prediction else ""
            gt_loc = str(ground_truth).lower().strip() if ground_truth else ""
            
            # 类别匹配
            accuracy = 1.0 if pred_loc == gt_loc else 0.0
            
            return {
                "accuracy": accuracy,
                "predicted": prediction,
                "ground_truth": ground_truth,
                "metric_type": "Acc@1"
            }
        except:
            return {"accuracy": 0.0, "error": "Invalid prediction"}
    
    def _eval_traffic_signal(self, prediction: Any, ground_truth: Any) -> Dict:
        """
        交通信号评估 - CityBench指标: Average_Queue_Length, Throughput
        
        评估逻辑（简化）:
        - 绿灯时间与最优值的接近程度
        """
        try:
            pred_time = float(prediction) if prediction else 0
            gt_time = float(ground_truth) if ground_truth else 45
            
            # 相对误差
            if gt_time > 0:
                relative_error = abs(pred_time - gt_time) / gt_time
                accuracy = max(0, 1 - relative_error)
            else:
                accuracy = 0.0
            
            return {
                "accuracy": accuracy,
                "predicted_time": pred_time,
                "optimal_time": gt_time,
                "metric_type": "Signal_Optimality"
            }
        except:
            return {"accuracy": 0.0, "error": "Invalid prediction"}
    
    def _eval_navigation(self, prediction: Any, ground_truth: Any) -> Dict:
        """
        导航评估 - CityBench指标: Navigation_Success_Ratio, Navigation_Average_Distance
        
        评估逻辑:
        - 路径合理性检查
        - 关键地标包含
        """
        try:
            pred_route = str(prediction).lower() if prediction else ""
            gt_route = str(ground_truth).lower() if ground_truth else ""
            
            # 检查是否包含关键方向词
            direction_keywords = ["west", "east", "north", "south", "head", "turn", "walk"]
            has_direction = any(kw in pred_route for kw in direction_keywords)
            
            # 检查路径长度（简化）
            route_length = len(pred_route.split())
            reasonable_length = 5 <= route_length <= 50
            
            # 综合评分
            if has_direction and reasonable_length:
                accuracy = 0.7
                # 如果包含关键地标，加分
                if any(landmark in pred_route for landmark in ["station", "square", "avenue", "street"]):
                    accuracy = 1.0
            elif has_direction:
                accuracy = 0.4
            else:
                accuracy = 0.1
            
            return {
                "accuracy": accuracy,
                "has_direction": has_direction,
                "route_length": route_length,
                "metric_type": "Navigation_Quality"
            }
        except:
            return {"accuracy": 0.0, "error": "Invalid prediction"}
    
    def _eval_exploration(self, prediction: Any, ground_truth: Any) -> Dict:
        """
        城市探索评估 - CityBench指标: Exploration_Success_Ratio
        
        评估逻辑:
        - 推荐类别的覆盖率和多样性
        """
        try:
            pred_targets = set(str(t).lower().strip() for t in prediction) if isinstance(prediction, list) else set()
            gt_targets = set(str(t).lower().strip() for t in ground_truth) if isinstance(ground_truth, list) else set()
            
            # 计算匹配
            matches = 0
            for pred in pred_targets:
                for gt in gt_targets:
                    if pred in gt or gt in pred:
                        matches += 1
                        break
            
            # 覆盖率
            if len(gt_targets) > 0:
                coverage = matches / len(gt_targets)
            else:
                coverage = 0.0
            
            # 多样性奖励
            diversity_bonus = min(0.2, len(pred_targets) * 0.05)
            
            accuracy = min(1.0, coverage + diversity_bonus)
            
            return {
                "accuracy": accuracy,
                "coverage": coverage,
                "diversity": len(pred_targets),
                "metric_type": "Exploration_Coverage"
            }
        except:
            return {"accuracy": 0.0, "error": "Invalid prediction"}
    
    def _eval_default(self, prediction: Any, ground_truth: Any) -> Dict:
        """默认评估器"""
        return {"accuracy": 0.0, "error": "Unknown task type"}
    
    def _evaluate_state_perception(self, agent_output: Dict, task_type: str) -> Dict:
        """
        评估状态感知维度 - 仅Agent
        
        根据任务类型评估不同的感知能力
        """
        perception = agent_output.get("perception", {})
        
        if not perception:
            return {"score": 0.0, "details": "无感知数据"}
        
        # 根据任务类型评估不同的感知维度
        task_perception_weights = {
            "population_prediction": ["image_features", "density_indicators"],
            "object_detection": ["image_analysis", "object_recognition"],
            "geolocation": ["visual_features", "city_characteristics"],
            "geoqa": ["spatial_understanding", "geographic_knowledge"],
            "mobility_prediction": ["trajectory_analysis", "pattern_recognition"],
            "traffic_signal": ["road_network", "traffic_state"],
            "outdoor_navigation": ["road_topology", "landmark_recognition"],
            "urban_exploration": ["poi_distribution", "urban_structure"],
        }
        
        # 检查关键感知维度
        key_dims = task_perception_weights.get(task_type, ["general"])
        detected_dims = []
        
        for dim in key_dims:
            if dim in perception or dim in str(perception).lower():
                detected_dims.append(dim)
        
        score = len(detected_dims) / len(key_dims) if key_dims else 0.5
        
        return {
            "score": score,
            "detected_dimensions": detected_dims,
            "expected_dimensions": key_dims,
        }
    
    def _evaluate_decision_sequence(self, agent_output: Dict, task_type: str) -> Dict:
        """
        评估决策序列维度 - 仅Agent
        
        评估多步决策的质量和稳定性
        """
        reasoning = agent_output.get("reasoning", {})
        action = agent_output.get("action", {})
        
        # 检查是否有推理链
        reasoning_chain = reasoning.get("reasoning_chain", [])
        has_reasoning = len(reasoning_chain) > 0
        
        # 检查是否有明确的决策步骤
        has_steps = "steps" in action or "plan" in action
        
        # 检查决策一致性
        conclusion = reasoning.get("conclusion", "")
        action_result = action.get("result", action.get("answer", ""))
        consistent = str(conclusion).lower() in str(action_result).lower() or \
                     str(action_result).lower() in str(conclusion).lower()
        
        # 计算得分
        score = 0.0
        if has_reasoning:
            score += 0.4
        if has_steps:
            score += 0.3
        if consistent:
            score += 0.3
        
        return {
            "score": score,
            "has_reasoning": has_reasoning,
            "has_steps": has_steps,
            "consistent": consistent,
            "reasoning_steps": len(reasoning_chain),
        }
    
    def _evaluate_reasoning_depth(self, agent_output: Dict) -> Dict:
        """
        评估推理深度 - 仅Agent
        
        评估推理过程的复杂度和质量
        """
        reasoning = agent_output.get("reasoning", {})
        
        # 分析推理文本长度（简化指标）
        reasoning_text = str(reasoning)
        text_length = len(reasoning_text)
        
        # 检查推理关键词
        depth_keywords = ["because", "therefore", "however", "analysis", "consider", 
                         "step", "first", "second", "third", "conclusion"]
        keyword_count = sum(1 for kw in depth_keywords if kw in reasoning_text.lower())
        
        # 评分
        length_score = min(1.0, text_length / 500)  # 500字符为满分
        keyword_score = min(1.0, keyword_count / 5)  # 5个关键词为满分
        
        score = 0.4 * length_score + 0.6 * keyword_score
        
        return {
            "score": score,
            "reasoning_length": text_length,
            "depth_keywords": keyword_count,
        }
    
    def _evaluate_tool_usage(self, agent_output: Dict) -> Dict:
        """
        评估工具使用 - 仅Agent
        
        评估工具调用的合理性和效率
        """
        action = agent_output.get("action", {})
        
        # 检查是否使用了工具
        used_tool = "tool" in action or "tool_calls" in action
        
        # 检查工具调用结果
        tool_success = action.get("status") == "success" or "result" in action
        
        # 评分
        if used_tool and tool_success:
            score = 1.0
        elif used_tool:
            score = 0.5
        else:
            score = 0.3  # 没有使用工具，基础分
        
        return {
            "score": score,
            "used_tool": used_tool,
            "tool_success": tool_success,
        }
    
    def _calculate_agent_score(
        self,
        task_outcome: Dict,
        state_perception: Dict,
        decision_sequence: Dict,
        reasoning_depth: Dict,
        tool_usage: Dict
    ) -> float:
        """
        计算Agent总体得分
        
        权重分配:
        - Task Outcome: 50% (核心)
        - State Perception: 15%
        - Decision Sequence: 15%
        - Reasoning Depth: 10%
        - Tool Usage: 10%
        """
        weights = {
            "task_outcome": 0.50,
            "state_perception": 0.15,
            "decision_sequence": 0.15,
            "reasoning_depth": 0.10,
            "tool_usage": 0.10,
        }
        
        scores = {
            "task_outcome": task_outcome.get("accuracy", 0),
            "state_perception": state_perception.get("score", 0),
            "decision_sequence": decision_sequence.get("score", 0),
            "reasoning_depth": reasoning_depth.get("score", 0),
            "tool_usage": tool_usage.get("score", 0),
        }
        
        overall = sum(weights[key] * scores[key] for key in weights)
        
        return overall
    
    def get_summary(self) -> Dict:
        """获取评估摘要"""
        if not self.results:
            return {"error": "No evaluation results"}
        
        # 分离裸模型和Agent结果
        bare_results = [r for r in self.results if r.get("is_bare_model")]
        agent_results = [r for r in self.results if not r.get("is_bare_model")]
        
        summary = {
            "total_tasks": len(self.results),
            "bare_model_tasks": len(bare_results),
            "agent_tasks": len(agent_results),
        }
        
        # 按任务类型分组统计
        task_types = set(r["task_type"] for r in self.results)
        
        for task_type in task_types:
            task_bare = [r["overall_score"] for r in bare_results if r["task_type"] == task_type]
            task_agent = [r["overall_score"] for r in agent_results if r["task_type"] == task_type]
            
            summary[task_type] = {
                "bare_model": {
                    "count": len(task_bare),
                    "average": np.mean(task_bare) if task_bare else None,
                },
                "agent": {
                    "count": len(task_agent),
                    "average": np.mean(task_agent) if task_agent else None,
                }
            }
        
        # 总体平均分
        if bare_results:
            summary["bare_model_overall"] = np.mean([r["overall_score"] for r in bare_results])
        if agent_results:
            summary["agent_overall"] = np.mean([r["overall_score"] for r in agent_results])
        
        return summary

    # ------------------------------------------------------------------
    # Complexity Stratification (GeoJSON Agents Table 5-7 style)
    # ------------------------------------------------------------------

    @staticmethod
    def classify_complexity(
        task: Dict[str, Any],
        task_type: str = "",
    ) -> str:
        """
        Classify a single task into complexity tier: basic / intermediate / advanced.

        Heuristics (aligned with GeoJSON Agents' 3-tier scheme):
        - basic:        ≤ 1 reasoning step, single data source, factual recall
        - intermediate: 2-3 reasoning steps, multi-source, requires spatial reasoning
        - advanced:     ≥ 4 steps or open-ended workflow, requires tool chaining
        """
        # Step count signals
        steps = task.get("workflow_steps", task.get("steps", []))
        tools = task.get("reference_tools", task.get("reference_tool_steps", []))
        question = str(task.get("question", task.get("task_instruction", "")))

        step_count = len(steps) if isinstance(steps, list) else 0
        tool_count = len(tools) if isinstance(tools, list) else 0

        # Keyword signals for complexity
        advanced_keywords = {"workflow", "pipeline", "multi-step", "综合分析", "对比", "跨区域", "预测"}
        intermediate_keywords = {"分析", "计算", "evaluate", "compare", "accessibility", "density"}

        q_lower = question.lower()
        has_advanced = any(k in q_lower for k in advanced_keywords)
        has_intermediate = any(k in q_lower for k in intermediate_keywords)

        if step_count >= 4 or tool_count >= 3 or has_advanced:
            return "advanced"
        if step_count >= 2 or tool_count >= 1 or has_intermediate:
            return "intermediate"
        return "basic"

    def get_summary_by_complexity(
        self,
        tasks: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Get summary stratified by complexity (GeoJSON Agents Table 5 format).

        Args:
            tasks: Optional list of raw task dicts (for complexity classification).
                   If not provided, all results are treated as 'unknown' complexity.

        Returns:
            {
                "basic":        {"count": N, "avg_score": 0.xx, ...},
                "intermediate": {...},
                "advanced":     {...},
            }
        """
        # Map case results to complexity tiers
        if tasks and len(tasks) == len(self.results):
            complexities = [self.classify_complexity(t) for t in tasks]
        else:
            complexities = ["unknown"] * len(self.results)

        from collections import defaultdict
        by_tier: Dict[str, list] = defaultdict(list)
        for cpx, result in zip(complexities, self.results):
            by_tier[cpx].append(result)

        summary = {}
        for tier in ["basic", "intermediate", "advanced", "unknown"]:
            recs = by_tier.get(tier, [])
            if not recs:
                continue
            scores = [r["overall_score"] for r in recs]
            bare = [r for r in recs if r.get("is_bare_model")]
            agent = [r for r in recs if not r.get("is_bare_model")]
            summary[tier] = {
                "count": len(recs),
                "avg_score": float(np.mean(scores)) if scores else 0,
                "bare_avg": float(np.mean([r["overall_score"] for r in bare])) if bare else None,
                "agent_avg": float(np.mean([r["overall_score"] for r in agent])) if agent else None,
            }
        return summary
