"""
Qwen vs Urban Agent 对比测试
对比裸Qwen和Urban Agent + Qwen在CityBench任务上的表现
"""

import asyncio
import json
import logging
from pathlib import Path
from datetime import datetime
import sys
import os

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

from urban_agent.core.agent import UrbanAgent
from urban_agent.evaluation.citybench_evaluator import CityBenchEvaluator
from urban_agent.llm.qwen_client import QwenClient
from typing import Dict

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BareQwenTester:
    """裸Qwen测试器（无Agent框架）"""
    
    def __init__(self, qwen_client: QwenClient):
        self.qwen = qwen_client
    
    async def test_population_prediction(self, task: Dict, city_data: Dict) -> Dict:
        """裸Qwen人口预测"""
        prompt = f"""You are an urban analyst. Estimate the population based on the following information:
        
Land use: {city_data.get('land_use', [])}
Building density: {city_data.get('density', 'unknown')}
Building count: {city_data.get('building_count', 0)}

Provide ONLY a numerical estimate of the population. Return just the number."""
        
        response = await self.qwen.generate(prompt)
        
        # 提取数字
        import re
        numbers = re.findall(r'\d+', response.replace(',', ''))
        population = int(numbers[0]) if numbers else 1000
        
        return {
            "answer": population,
            "raw_response": response,
            "confidence": 0.5
        }
    
    async def test_object_detection(self, task: Dict, city_data: Dict) -> Dict:
        """裸Qwen目标检测"""
        prompt = f"""List all urban objects visible in this scene description:
        
{city_data.get('description', '')}

Return ONLY a comma-separated list of objects."""
        
        response = await self.qwen.generate(prompt)
        
        # 解析对象列表
        objects = [obj.strip() for obj in response.split(',') if obj.strip()]
        
        return {
            "objects": objects,
            "raw_response": response,
            "confidence": 0.5
        }
    
    async def test_geolocation(self, task: Dict, city_data: Dict) -> Dict:
        """裸Qwen地理定位"""
        prompt = f"""Identify the city based on this description:
        
{city_data.get('description', '')}
Hint: {task.get('content', {}).get('hint', '')}

Return ONLY the city name. Choose from: Beijing, London, Paris, Tokyo, New York, Mumbai, Sydney, or Unknown."""
        
        response = await self.qwen.generate(prompt)
        
        # 提取城市名
        cities = ["Beijing", "London", "Paris", "Tokyo", "New York", "Mumbai", "Sydney"]
        identified = "Unknown"
        for city in cities:
            if city.lower() in response.lower():
                identified = city
                break
        
        return {
            "city": identified,
            "raw_response": response,
            "confidence": 0.5
        }
    
    async def test_geoqa(self, task: Dict, city_data: Dict) -> Dict:
        """裸Qwen地理问答"""
        prompt = f"""Answer this geographic question:
        
Question: {task.get('question', '')}

Context: Population {city_data.get('population', 'unknown')}, Area {city_data.get('area', 'unknown')} sq km

Provide a concise answer."""
        
        response = await self.qwen.generate(prompt)
        
        return {
            "answer": response,
            "raw_response": response,
            "confidence": 0.5
        }
    
    async def test_mobility_prediction(self, task: Dict, city_data: Dict) -> Dict:
        """裸Qwen移动性预测"""
        prompt = f"""Predict the next location category based on:
        
Average trajectory length: {city_data.get('flow_patterns', {}).get('avg_length', 0)}
Number of patterns: {city_data.get('flow_patterns', {}).get('pattern_count', 0)}

Return ONLY one of: residential_area, commercial_area, industrial_area, or recreational_area."""
        
        response = await self.qwen.generate(prompt)
        
        return {
            "location": response.strip(),
            "raw_response": response,
            "confidence": 0.5
        }
    
    async def test_traffic_signal(self, task: Dict, city_data: Dict) -> Dict:
        """裸Qwen交通信号"""
        prompt = f"""Recommend traffic signal green time (in seconds) for an intersection with:
        
Road count: {city_data.get('road_network', {}).get('road_count', 0)}
Total road length: {city_data.get('road_network', {}).get('total_length', 0)} meters

Return ONLY a number between 20 and 90."""
        
        response = await self.qwen.generate(prompt)
        
        # 提取数字
        import re
        numbers = re.findall(r'\d+', response)
        green_time = int(numbers[0]) if numbers else 30
        green_time = max(20, min(90, green_time))
        
        return {
            "green_time": green_time,
            "raw_response": response,
            "confidence": 0.5
        }
    
    async def test_navigation(self, task: Dict, city_data: Dict) -> Dict:
        """裸Qwen导航"""
        prompt = f"""Provide navigation directions from {task.get('start', 'start')} to {task.get('end', 'destination')}.

Return brief step-by-step directions."""
        
        response = await self.qwen.generate(prompt)
        
        return {
            "route": response,
            "raw_response": response,
            "confidence": 0.5
        }
    
    async def test_exploration(self, task: Dict, city_data: Dict) -> Dict:
        """裸Qwen城市探索"""
        prompt = f"""Recommend top 3 POI categories to explore based on availability:
        
POI distribution: {city_data.get('poi_categories', {})}

Return ONLY a comma-separated list of 3 categories."""
        
        response = await self.qwen.generate(prompt)
        
        # 解析类别
        categories = [cat.strip() for cat in response.split(',') if cat.strip()]
        
        return {
            "targets": categories[:3],
            "raw_response": response,
            "confidence": 0.5
        }


async def run_comparison_test():
    """运行对比测试"""
    logger.info("\n" + "=" * 80)
    logger.info("🚀 Qwen vs Urban Agent 对比测试")
    logger.info("=" * 80)
    
    # 初始化Qwen客户端
    try:
        qwen_client = QwenClient()
        logger.info("✅ Qwen客户端初始化成功")
    except Exception as e:
        logger.error(f"❌ Qwen客户端初始化失败: {e}")
        return
    
    # 初始化Urban Agent
    agent = UrbanAgent(
        llm_client=qwen_client,
        vlm_client=qwen_client,
        config={}
    )
    logger.info("✅ Urban Agent初始化成功")
    
    # 初始化裸Qwen测试器
    bare_qwen = BareQwenTester(qwen_client)
    logger.info("✅ 裸Qwen测试器初始化成功")
    
    # 测试数据
    test_cases = {
        "population_prediction": {
            "task": {
                "task_type": "population_prediction",
                "data_type": "remote_sensing",
                "content": {"city": "Beijing", "area": "downtown"}
            },
            "city_data": {
                "land_use": ["residential", "commercial"],
                "density": "high",
                "building_count": 150
            },
            "ground_truth": 5000
        },
        "object_detection": {
            "task": {
                "task_type": "object_detection",
                "data_type": "street_view",
                "content": {"scene": "urban"}
            },
            "city_data": {
                "description": "Street view with buildings, cars, pedestrians, and roads in an urban area"
            },
            "ground_truth": ["building", "car", "pedestrian", "road"]
        },
        "geolocation": {
            "task": {
                "task_type": "geolocation",
                "data_type": "street_view",
                "content": {"hint": "Asian city with modern architecture and high-rise buildings"}
            },
            "city_data": {
                "description": "Modern cityscape with high-rise buildings, wide avenues, and contemporary architecture"
            },
            "ground_truth": "Beijing"
        },
        "geoqa": {
            "task": {
                "task_type": "geoqa",
                "data_type": "text",
                "question": "What is the population density of downtown Beijing?"
            },
            "city_data": {
                "population": 21500000,
                "area": 16410
            },
            "ground_truth": "high"
        },
        "mobility_prediction": {
            "task": {
                "task_type": "mobility_prediction",
                "data_type": "trajectory"
            },
            "city_data": {
                "flow_patterns": {"avg_length": 5, "pattern_count": 15}
            },
            "ground_truth": "commercial_area"
        },
        "traffic_signal": {
            "task": {
                "task_type": "traffic_signal",
                "data_type": "osm"
            },
            "city_data": {
                "road_network": {"road_count": 4, "total_length": 2000}
            },
            "ground_truth": 45
        },
        "outdoor_navigation": {
            "task": {
                "task_type": "outdoor_navigation",
                "data_type": "osm",
                "start": "Beijing Railway Station",
                "end": "Tiananmen Square"
            },
            "city_data": {
                "road_network": {"road_count": 5}
            },
            "ground_truth": "Head west on Chang'an Avenue"
        },
        "urban_exploration": {
            "task": {
                "task_type": "urban_exploration",
                "data_type": "osm"
            },
            "city_data": {
                "poi_categories": {"restaurant": 10, "park": 3, "museum": 2}
            },
            "ground_truth": ["restaurant", "park", "museum"]
        }
    }
    
    # 评估器
    bare_evaluator = CityBenchEvaluator()
    agent_evaluator = CityBenchEvaluator()
    
    # 结果存储
    results = {
        "bare_qwen": {},
        "urban_agent": {},
        "comparison": {}
    }
    
    # 测试每个任务
    for task_name, test_data in test_cases.items():
        logger.info(f"\n{'='*60}")
        logger.info(f"📋 测试任务: {task_name}")
        logger.info(f"{'='*60}")
        
        task = test_data["task"]
        city_data = test_data["city_data"]
        ground_truth = test_data["ground_truth"]
        
        # ===== 测试裸Qwen =====
        logger.info("\n🤖 裸Qwen测试...")
        try:
            test_method = getattr(bare_qwen, f"test_{task_name}")
            bare_result = await test_method(task, city_data)
            
            # 提取预测值
            if task_name == "population_prediction":
                bare_prediction = bare_result["answer"]
            elif task_name == "object_detection":
                bare_prediction = bare_result["objects"]
            elif task_name == "geolocation":
                bare_prediction = bare_result["city"]
            elif task_name == "geoqa":
                bare_prediction = bare_result["answer"]
            elif task_name == "mobility_prediction":
                bare_prediction = bare_result["location"]
            elif task_name == "traffic_signal":
                bare_prediction = bare_result["green_time"]
            elif task_name == "outdoor_navigation":
                bare_prediction = bare_result["route"]
            elif task_name == "urban_exploration":
                bare_prediction = bare_result["targets"]
            else:
                bare_prediction = None
            
            # 评估
            bare_eval = bare_evaluator.evaluate_task(
                task_name, bare_prediction, ground_truth,
                {"perception": {}, "reasoning": {}, "action": bare_result}
            )
            
            results["bare_qwen"][task_name] = {
                "prediction": bare_prediction,
                "ground_truth": ground_truth,
                "evaluation": bare_eval
            }
            
            logger.info(f"  预测: {bare_prediction}")
            logger.info(f"  真实: {ground_truth}")
            logger.info(f"  得分: {bare_eval['overall_score']:.3f}")
            
        except Exception as e:
            logger.error(f"  ❌ 裸Qwen测试失败: {e}")
            results["bare_qwen"][task_name] = {"error": str(e)}
        
        # ===== 测试Urban Agent =====
        logger.info("\n🎯 Urban Agent + Qwen测试...")
        try:
            agent_result = await agent.execute_task(task, task_name, city_data)
            
            # 提取预测值
            action = agent_result.get("action", {})
            if task_name == "population_prediction":
                agent_prediction = action.get("numerical_answer", 0)
            elif task_name == "object_detection":
                agent_prediction = action.get("objects", [])
            elif task_name == "geolocation":
                agent_prediction = action.get("identified_city", "")
            elif task_name == "geoqa":
                agent_prediction = action.get("answer", "")
            elif task_name == "mobility_prediction":
                agent_prediction = action.get("predicted_location", "")
            elif task_name == "traffic_signal":
                agent_prediction = action.get("signal_plan", {}).get("green_time", 30)
            elif task_name == "outdoor_navigation":
                agent_prediction = action.get("route", "")
            elif task_name == "urban_exploration":
                agent_prediction = action.get("exploration_plan", {}).get("targets", [])
            else:
                agent_prediction = None
            
            # 评估
            agent_eval = agent_evaluator.evaluate_task(
                task_name, agent_prediction, ground_truth, agent_result
            )
            
            results["urban_agent"][task_name] = {
                "prediction": agent_prediction,
                "ground_truth": ground_truth,
                "evaluation": agent_eval
            }
            
            logger.info(f"  预测: {agent_prediction}")
            logger.info(f"  真实: {ground_truth}")
            logger.info(f"  得分: {agent_eval['overall_score']:.3f}")
            
        except Exception as e:
            logger.error(f"  ❌ Urban Agent测试失败: {e}")
            results["urban_agent"][task_name] = {"error": str(e)}
        
        # 对比
        if task_name in results["bare_qwen"] and task_name in results["urban_agent"]:
            bare_score = results["bare_qwen"][task_name].get("evaluation", {}).get("overall_score", 0)
            agent_score = results["urban_agent"][task_name].get("evaluation", {}).get("overall_score", 0)
            improvement = agent_score - bare_score
            
            results["comparison"][task_name] = {
                "bare_qwen_score": bare_score,
                "urban_agent_score": agent_score,
                "improvement": improvement,
                "improvement_pct": (improvement / bare_score * 100) if bare_score > 0 else 0
            }
    
    # 输出总结
    logger.info("\n" + "=" * 80)
    logger.info("📊 对比测试总结")
    logger.info("=" * 80)
    
    # 裸Qwen总结
    bare_summary = bare_evaluator.get_summary()
    logger.info("\n🤖 裸Qwen表现:")
    logger.info(f"  总体平均分: {bare_summary.get('overall_average', 0):.3f}")
    
    # Urban Agent总结
    agent_summary = agent_evaluator.get_summary()
    logger.info("\n🎯 Urban Agent表现:")
    logger.info(f"  总体平均分: {agent_summary.get('overall_average', 0):.3f}")
    
    # 提升分析
    avg_improvement = sum(c["improvement"] for c in results["comparison"].values()) / len(results["comparison"])
    logger.info(f"\n📈 平均提升: {avg_improvement:.3f}")
    
    # 各任务对比
    logger.info("\n📋 各任务详细对比:")
    for task_name, comp in results["comparison"].items():
        logger.info(f"  {task_name}:")
        logger.info(f"    裸Qwen: {comp['bare_qwen_score']:.3f}")
        logger.info(f"    Agent:  {comp['urban_agent_score']:.3f}")
        logger.info(f"    提升:   {comp['improvement']:+.3f} ({comp['improvement_pct']:+.1f}%)")
    
    # 保存结果
    output_dir = Path("results")
    output_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"qwen_comparison_{timestamp}.json"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({
            "results": results,
            "bare_qwen_summary": bare_summary,
            "urban_agent_summary": agent_summary,
            "timestamp": timestamp
        }, f, indent=2, ensure_ascii=False)
    
    logger.info(f"\n💾 详细结果已保存到: {output_path}")
    
    return results


if __name__ == "__main__":
    asyncio.run(run_comparison_test())
