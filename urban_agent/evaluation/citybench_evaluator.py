"""
CityBench Evaluator
CityBench三维评估指标实现
"""

import json
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path
import numpy as np

logger = logging.getLogger(__name__)


class CityBenchEvaluator:
    """
    CityBench评估器
    
    三维评估框架：
    1. State Perception (状态感知)
    2. Decision Sequence (决策序列)
    3. Task Outcome (任务结果)
    """
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.results: List[Dict] = []
        
    def evaluate_task(
        self,
        task_type: str,
        prediction: Any,
        ground_truth: Any,
        agent_output: Dict
    ) -> Dict[str, Any]:
        """
        评估单个任务
        
        Args:
            task_type: 任务类型
            prediction: 预测结果
            ground_truth: 真实标签
            agent_output: 智能体完整输出
            
        Returns:
            三维评估结果
        """
        # 1. State Perception Metrics
        state_perception = self._evaluate_state_perception(agent_output)
        
        # 2. Decision Sequence Metrics
        decision_sequence = self._evaluate_decision_sequence(agent_output)
        
        # 3. Task Outcome Metrics
        task_outcome = self._evaluate_task_outcome(
            task_type, prediction, ground_truth
        )
        
        result = {
            "task_type": task_type,
            "state_perception": state_perception,
            "decision_sequence": decision_sequence,
            "task_outcome": task_outcome,
            "overall_score": self._calculate_overall_score(
                state_perception, decision_sequence, task_outcome
            )
        }
        
        self.results.append(result)
        return result
    
    def _evaluate_state_perception(self, agent_output: Dict) -> Dict:
        """
        评估状态感知维度
        
        指标：
        - 数据覆盖率（Data Coverage）
        - 特征提取准确性（Feature Extraction Accuracy）
        - 空间理解准确度（Spatial Understanding Accuracy）
        """
        perception = agent_output.get("perception", {})
        
        # 数据覆盖率
        data_coverage = self._calculate_data_coverage(perception)
        
        # 特征提取质量
        feature_quality = self._evaluate_feature_quality(perception)
        
        # 空间理解准确度
        spatial_accuracy = self._evaluate_spatial_understanding(perception)
        
        return {
            "data_coverage": data_coverage,
            "feature_quality": feature_quality,
            "spatial_accuracy": spatial_accuracy,
            "average": np.mean([data_coverage, feature_quality, spatial_accuracy])
        }
    
    def _evaluate_decision_sequence(self, agent_output: Dict) -> Dict:
        """
        评估决策序列维度
        
        指标：
        - 推理链完整性（Reasoning Chain Completeness）
        - 决策一致性（Decision Consistency）
        - 工具使用效率（Tool Usage Efficiency）
        """
        reasoning = agent_output.get("reasoning", {})
        
        # 推理链完整性
        reasoning_completeness = self._evaluate_reasoning_completeness(reasoning)
        
        # 决策一致性
        decision_consistency = self._evaluate_decision_consistency(reasoning)
        
        # 工具使用效率
        tool_efficiency = self._evaluate_tool_efficiency(agent_output)
        
        return {
            "reasoning_completeness": reasoning_completeness,
            "decision_consistency": decision_consistency,
            "tool_efficiency": tool_efficiency,
            "average": np.mean([reasoning_completeness, decision_consistency, tool_efficiency])
        }
    
    def _evaluate_task_outcome(
        self,
        task_type: str,
        prediction: Any,
        ground_truth: Any
    ) -> Dict:
        """
        评估任务结果维度
        
        指标：
        - 准确性（Accuracy）
        - 精确度（Precision）
        - 召回率（Recall）
        - F1分数
        """
        if task_type == "population_prediction":
            return self._evaluate_population_prediction(prediction, ground_truth)
        elif task_type == "object_detection":
            return self._evaluate_object_detection(prediction, ground_truth)
        elif task_type == "geolocation":
            return self._evaluate_geolocation(prediction, ground_truth)
        elif task_type == "geoqa":
            return self._evaluate_geoqa(prediction, ground_truth)
        elif task_type == "mobility_prediction":
            return self._evaluate_mobility_prediction(prediction, ground_truth)
        elif task_type == "traffic_signal":
            return self._evaluate_traffic_signal(prediction, ground_truth)
        elif task_type == "outdoor_navigation":
            return self._evaluate_navigation(prediction, ground_truth)
        elif task_type == "urban_exploration":
            return self._evaluate_exploration(prediction, ground_truth)
        else:
            return {"accuracy": 0.0, "error": "Unknown task type"}
    
    def _evaluate_population_prediction(
        self,
        prediction: Any,
        ground_truth: Any
    ) -> Dict:
        """评估人口预测"""
        try:
            pred_val = float(prediction) if prediction else 0
            gt_val = float(ground_truth) if ground_truth else 1
            
            # 相对误差
            relative_error = abs(pred_val - gt_val) / gt_val if gt_val > 0 else 1
            
            # 准确率（误差在20%以内视为正确）
            accuracy = 1.0 if relative_error < 0.2 else max(0, 1 - relative_error)
            
            return {
                "accuracy": accuracy,
                "relative_error": relative_error,
                "predicted": pred_val,
                "ground_truth": gt_val
            }
        except:
            return {"accuracy": 0.0, "error": "Invalid prediction format"}
    
    def _evaluate_object_detection(
        self,
        prediction: Any,
        ground_truth: Any
    ) -> Dict:
        """评估目标检测"""
        try:
            pred_objects = set(prediction) if isinstance(prediction, list) else set()
            gt_objects = set(ground_truth) if isinstance(ground_truth, list) else set()
            
            # 计算精确率和召回率
            if len(pred_objects) == 0:
                precision = 0.0
            else:
                precision = len(pred_objects & gt_objects) / len(pred_objects)
            
            if len(gt_objects) == 0:
                recall = 0.0
            else:
                recall = len(pred_objects & gt_objects) / len(gt_objects)
            
            # F1分数
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
            
            return {
                "accuracy": f1,  # 使用F1作为准确率
                "precision": precision,
                "recall": recall,
                "f1_score": f1
            }
        except:
            return {"accuracy": 0.0, "error": "Invalid prediction format"}
    
    def _evaluate_geolocation(
        self,
        prediction: Any,
        ground_truth: Any
    ) -> Dict:
        """评估地理定位"""
        try:
            pred_city = str(prediction).lower() if prediction else ""
            gt_city = str(ground_truth).lower() if ground_truth else ""
            
            # 精确匹配
            accuracy = 1.0 if pred_city == gt_city else 0.0
            
            return {
                "accuracy": accuracy,
                "predicted": prediction,
                "ground_truth": ground_truth
            }
        except:
            return {"accuracy": 0.0, "error": "Invalid prediction format"}
    
    def _evaluate_geoqa(
        self,
        prediction: Any,
        ground_truth: Any
    ) -> Dict:
        """评估地理问答"""
        try:
            pred_answer = str(prediction).lower().strip() if prediction else ""
            gt_answer = str(ground_truth).lower().strip() if ground_truth else ""
            
            # 包含关系匹配
            accuracy = 1.0 if gt_answer in pred_answer or pred_answer in gt_answer else 0.0
            
            return {
                "accuracy": accuracy,
                "predicted": prediction,
                "ground_truth": ground_truth
            }
        except:
            return {"accuracy": 0.0, "error": "Invalid prediction format"}
    
    def _evaluate_mobility_prediction(
        self,
        prediction: Any,
        ground_truth: Any
    ) -> Dict:
        """评估移动性预测"""
        try:
            pred_loc = str(prediction).lower() if prediction else ""
            gt_loc = str(ground_truth).lower() if ground_truth else ""
            
            # 类别匹配
            accuracy = 1.0 if pred_loc == gt_loc else 0.0
            
            return {
                "accuracy": accuracy,
                "predicted": prediction,
                "ground_truth": ground_truth
            }
        except:
            return {"accuracy": 0.0, "error": "Invalid prediction format"}
    
    def _evaluate_traffic_signal(
        self,
        prediction: Any,
        ground_truth: Any
    ) -> Dict:
        """评估交通信号控制"""
        try:
            pred_time = float(prediction) if prediction else 0
            gt_time = float(ground_truth) if ground_truth else 1
            
            # 相对误差
            relative_error = abs(pred_time - gt_time) / gt_time if gt_time > 0 else 1
            
            # 准确率
            accuracy = max(0, 1 - relative_error)
            
            return {
                "accuracy": accuracy,
                "relative_error": relative_error,
                "predicted": pred_time,
                "ground_truth": gt_time
            }
        except:
            return {"accuracy": 0.0, "error": "Invalid prediction format"}
    
    def _evaluate_navigation(
        self,
        prediction: Any,
        ground_truth: Any
    ) -> Dict:
        """评估导航"""
        # 简化评估：检查是否包含关键地标
        try:
            pred_route = str(prediction).lower() if prediction else ""
            gt_route = str(ground_truth).lower() if ground_truth else ""
            
            # 简单匹配
            accuracy = 0.5 if len(pred_route) > 10 else 0.0
            
            return {
                "accuracy": accuracy,
                "route_quality": "basic"
            }
        except:
            return {"accuracy": 0.0, "error": "Invalid prediction format"}
    
    def _evaluate_exploration(
        self,
        prediction: Any,
        ground_truth: Any
    ) -> Dict:
        """评估城市探索"""
        try:
            pred_targets = set(prediction) if isinstance(prediction, list) else set()
            gt_targets = set(ground_truth) if isinstance(ground_truth, list) else set()
            
            # 计算覆盖率
            if len(gt_targets) == 0:
                coverage = 0.0
            else:
                coverage = len(pred_targets & gt_targets) / len(gt_targets)
            
            return {
                "accuracy": coverage,
                "coverage": coverage
            }
        except:
            return {"accuracy": 0.0, "error": "Invalid prediction format"}
    
    def _calculate_data_coverage(self, perception: Dict) -> float:
        """计算数据覆盖率"""
        if not perception:
            return 0.0
        
        # 检查关键字段是否存在
        key_fields = ["type", "features", "description"]
        coverage = sum(1 for field in key_fields if field in perception) / len(key_fields)
        
        return coverage
    
    def _evaluate_feature_quality(self, perception: Dict) -> float:
        """评估特征提取质量"""
        features = perception.get("features", {})
        
        if not features:
            return 0.3
        
        # 根据特征丰富度评分
        feature_count = len(features)
        return min(1.0, 0.3 + feature_count * 0.1)
    
    def _evaluate_spatial_understanding(self, perception: Dict) -> float:
        """评估空间理解准确度"""
        # 检查是否有空间信息
        has_bounds = "bounds" in perception
        has_topology = "topology" in perception
        
        score = 0.0
        if has_bounds:
            score += 0.5
        if has_topology:
            score += 0.5
        
        return score if score > 0 else 0.3
    
    def _evaluate_reasoning_completeness(self, reasoning: Dict) -> float:
        """评估推理链完整性"""
        reasoning_chain = reasoning.get("reasoning_chain", [])
        
        if not reasoning_chain:
            return 0.3
        
        # 根据推理步骤数量评分
        steps = len(reasoning_chain)
        return min(1.0, 0.3 + steps * 0.15)
    
    def _evaluate_decision_consistency(self, reasoning: Dict) -> float:
        """评估决策一致性"""
        # 简化评估
        has_conclusion = "conclusion" in reasoning or "answer" in reasoning
        
        return 0.8 if has_conclusion else 0.4
    
    def _evaluate_tool_efficiency(self, agent_output: Dict) -> float:
        """评估工具使用效率"""
        # 简化评估
        action = agent_output.get("action", {})
        has_answer = "answer" in action
        
        return 0.8 if has_answer else 0.4
    
    def _calculate_overall_score(
        self,
        state_perception: Dict,
        decision_sequence: Dict,
        task_outcome: Dict
    ) -> float:
        """计算总体得分"""
        sp_score = state_perception.get("average", 0)
        ds_score = decision_sequence.get("average", 0)
        to_score = task_outcome.get("accuracy", 0)
        
        # 加权平均
        weights = {"sp": 0.3, "ds": 0.3, "to": 0.4}
        overall = weights["sp"] * sp_score + weights["ds"] * ds_score + weights["to"] * to_score
        
        return overall
    
    def get_summary(self) -> Dict:
        """获取评估摘要"""
        if not self.results:
            return {"error": "No evaluation results"}
        
        # 按任务类型分组
        task_scores = {}
        for result in self.results:
            task_type = result["task_type"]
            if task_type not in task_scores:
                task_scores[task_type] = []
            task_scores[task_type].append(result["overall_score"])
        
        # 计算每个任务类型的平均得分
        summary = {
            "total_tasks": len(self.results),
            "task_types": {}
        }
        
        for task_type, scores in task_scores.items():
            summary["task_types"][task_type] = {
                "count": len(scores),
                "average_score": np.mean(scores),
                "std": np.std(scores)
            }
        
        # 总体平均分
        all_scores = [r["overall_score"] for r in self.results]
        summary["overall_average"] = np.mean(all_scores)
        summary["overall_std"] = np.std(all_scores)
        
        return summary
    
    def save_results(self, output_path: str):
        """保存评估结果"""
        output = {
            "results": self.results,
            "summary": self.get_summary()
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        
        logger.info(f"评估结果已保存到: {output_path}")
