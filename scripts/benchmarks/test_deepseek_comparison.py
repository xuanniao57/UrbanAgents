"""
DeepSeek模型对比测试
测试ds的chat模型、推理模型，以及用了urban agent之后二者的结果
"""

import os
import sys
import asyncio
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Tuple

# 加载环境变量
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                if key and value:
                    os.environ[key] = value

sys.path.insert(0, str(Path(__file__).parent))

from urban_agent.core.agent import UrbanAgent
from urban_agent.evaluation.citybench_evaluator import CityBenchEvaluator
from urban_agent.llm.deepseek_client import DeepSeekClient
from urban_agent.tools.geo_tools import CityBenchDataLoader, GeoDataLoader

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

CITYBENCH_PATH = "d:\\GitHub_1\\world_agent\\urban-mobility-agent\\paper4_urban_svgagent\\third_party\\CityBench-main"


class BareDeepSeekTester:
    """裸DeepSeek模型测试器"""
    
    def __init__(self, model_client, model_name: str):
        self.client = model_client
        self.model_name = model_name
    
    async def test_population_prediction(self, city_data: Dict) -> Tuple[Any, str]:
        """人口预测 - 任务1"""
        prompt = f"""Estimate the population based on:
Land use: {city_data.get('land_use', [])}
Building density: {city_data.get('density', 'unknown')}
Building count: {city_data.get('building_count', 0)}

Return ONLY a number."""
        
        response = await self.client.generate(prompt)
        
        # 提取数字
        import re
        numbers = re.findall(r'\d+', response.replace(',', ''))
        prediction = int(numbers[0]) if numbers else 1000
        
        return prediction, response
    
    async def test_object_detection(self, image_path: str) -> Tuple[List, str]:
        """目标检测 - 任务2"""
        prompt = "List all urban objects you might find in a satellite image of a city. Return a JSON array of object names."
        
        try:
            response = await self.client.generate(prompt)
            
            # 解析对象列表
            import re
            json_match = re.search(r'\[.*?\]', response, re.DOTALL)
            if json_match:
                try:
                    objects = json.loads(json_match.group())
                except:
                    objects = [obj.strip() for obj in response.split(',') if obj.strip()]
            else:
                objects = [obj.strip() for obj in response.split(',') if obj.strip()]
            
            return objects[:20], response
        except Exception as e:
            return [], str(e)
    
    async def test_geolocation(self, image_path: str, city_options: List[str]) -> Tuple[str, str]:
        """地理定位 - 任务3"""
        prompt = f"Based on typical urban characteristics, identify which city this might be. Choose from: {', '.join(city_options)}. Return ONLY the city name."
        
        try:
            response = await self.client.generate(prompt)
            
            identified = "Unknown"
            for city in city_options:
                if city.lower() in response.lower():
                    identified = city
                    break
            
            return identified, response
        except Exception as e:
            return "Unknown", str(e)
    
    async def test_geoqa(self, question: str, context: Dict) -> Tuple[str, str]:
        """地理问答 - 任务4"""
        prompt = f"""Answer this geographic question:
Question: {question}
Context: {json.dumps(context)}

Provide a concise answer."""
        
        response = await self.client.generate(prompt)
        return response, response
    
    async def test_mobility_prediction(self, trajectory_data: Dict) -> Tuple[str, str]:
        """移动性预测 - 任务5"""
        prompt = f"""Predict the next location based on:
Average trajectory length: {trajectory_data.get('avg_length', 0)}
Number of patterns: {trajectory_data.get('pattern_count', 0)}

Return ONLY one: residential_area, commercial_area, industrial_area, or recreational_area."""
        
        response = await self.client.generate(prompt)
        return response.strip(), response
    
    async def test_traffic_signal(self, road_data: Dict) -> Tuple[int, str]:
        """交通信号 - 任务6"""
        prompt = f"""Recommend traffic signal green time (seconds) for:
Road count: {road_data.get('road_count', 0)}
Total road length: {road_data.get('total_length', 0)} meters

Return ONLY a number between 20 and 90."""
        
        response = await self.client.generate(prompt)
        
        import re
        numbers = re.findall(r'\d+', response)
        green_time = int(numbers[0]) if numbers else 30
        green_time = max(20, min(90, green_time))
        
        return green_time, response
    
    async def test_navigation(self, start: str, end: str) -> Tuple[str, str]:
        """户外导航 - 任务7"""
        prompt = f"Provide navigation directions from {start} to {end}. Return brief step-by-step directions."
        
        response = await self.client.generate(prompt)
        return response, response
    
    async def test_urban_exploration(self, city: str, poi_distribution: Dict) -> Tuple[List, str]:
        """城市探索 - 任务8"""
        prompt = f"""Recommend top 3 POI categories to explore in {city}:
POI distribution: {json.dumps(poi_distribution)}

Return ONLY a comma-separated list of 3 categories."""
        
        response = await self.client.generate(prompt)
        categories = [cat.strip() for cat in response.split(',') if cat.strip()]
        
        return categories[:3], response


async def run_deepseek_tests():
    """运行DeepSeek测试"""
    logger.info("\n" + "=" * 80)
    logger.info("🚀 DeepSeek模型 CityBench 8任务对比测试")
    logger.info("=" * 80)
    
    # 初始化DeepSeek客户端
    logger.info("\n📦 初始化DeepSeek客户端...")
    
    try:
        ds_chat_client = DeepSeekClient(client_type="chat")
        logger.info("✅ DeepSeek Chat客户端初始化成功")
    except Exception as e:
        logger.error(f"❌ DeepSeek Chat客户端失败: {e}")
        return
    
    try:
        ds_reasoner_client = DeepSeekClient(client_type="reasoner")
        logger.info("✅ DeepSeek Reasoner客户端初始化成功")
    except Exception as e:
        logger.error(f"❌ DeepSeek Reasoner客户端失败: {e}")
        return
    
    # 初始化Agent
    agent_ds_chat = UrbanAgent(llm_client=ds_chat_client, vlm_client=ds_chat_client, config={})
    agent_ds_reasoner = UrbanAgent(llm_client=ds_reasoner_client, vlm_client=ds_reasoner_client, config={})
    logger.info("✅ Urban Agent初始化成功")
    
    # 初始化裸模型测试器
    bare_ds_chat = BareDeepSeekTester(ds_chat_client, "DeepSeek-Chat")
    bare_ds_reasoner = BareDeepSeekTester(ds_reasoner_client, "DeepSeek-Reasoner")
    
    # 初始化评估器
    evaluators = {
        "bare_ds_chat": CityBenchEvaluator(),
        "bare_ds_reasoner": CityBenchEvaluator(),
        "agent_ds_chat": CityBenchEvaluator(),
        "agent_ds_reasoner": CityBenchEvaluator()
    }
    
    # 结果存储
    all_results = {model: {} for model in evaluators.keys()}
    
    # 测试数据准备
    data_loader = CityBenchDataLoader(CITYBENCH_PATH)
    
    # ===== 任务1: 人口预测 =====
    logger.info("\n" + "=" * 80)
    logger.info("📊 任务1: 人口预测 (Population Prediction)")
    logger.info("=" * 80)
    
    task_data = {
        "land_use": ["residential", "commercial"],
        "density": "high",
        "building_count": 150
    }
    ground_truth = 5000
    
    for model_name, tester, agent in [
        ("bare_ds_chat", bare_ds_chat, None),
        ("bare_ds_reasoner", bare_ds_reasoner, None),
        ("agent_ds_chat", None, agent_ds_chat),
        ("agent_ds_reasoner", None, agent_ds_reasoner)
    ]:
        try:
            if tester:
                prediction, raw = await tester.test_population_prediction(task_data)
                result_data = {"prediction": prediction, "raw": raw}
            else:
                task = {"task_type": "population_prediction", "data_type": "remote_sensing"}
                result = await agent.execute_task(task, "population_prediction", task_data)
                prediction = result.get("action", {}).get("numerical_answer", 0)
                result_data = result
            
            eval_result = evaluators[model_name].evaluate_task(
                "population_prediction", prediction, ground_truth, 
                {"action": result_data} if tester else result_data
            )
            
            all_results[model_name]["population_prediction"] = {
                "prediction": prediction,
                "ground_truth": ground_truth,
                "score": eval_result["overall_score"]
            }
            
            logger.info(f"  {model_name}: {prediction} (真实: {ground_truth}, 得分: {eval_result['overall_score']:.3f})")
        except Exception as e:
            logger.error(f"  {model_name} 失败: {e}")
            all_results[model_name]["population_prediction"] = {"error": str(e)}
    
    # ===== 任务2: 目标检测 =====
    logger.info("\n" + "=" * 80)
    logger.info("📊 任务2: 目标检测 (Object Detection)")
    logger.info("=" * 80)
    
    dataset = data_loader.load_remote_sensing_dataset("Paris")
    if dataset:
        image_dir = Path(dataset["image_dir"])
        images = list(image_dir.glob("*.png"))
        
        if images:
            test_image = images[0]
            image_id = test_image.stem
            ground_truth = dataset["labels"].get(image_id, {})
            true_objects = [obj for obj, val in ground_truth.items() if val == 1]
            
            logger.info(f"测试影像: {image_id}")
            
            for model_name, tester, agent in [
                ("bare_ds_chat", bare_ds_chat, None),
                ("bare_ds_reasoner", bare_ds_reasoner, None),
                ("agent_ds_chat", None, agent_ds_chat),
                ("agent_ds_reasoner", None, agent_ds_reasoner)
            ]:
                try:
                    if tester:
                        prediction, raw = await tester.test_object_detection(str(test_image))
                        result_data = {"objects": prediction, "raw": raw}
                    else:
                        task = {
                            "task_type": "object_detection",
                            "data_type": "remote_sensing",
                            "image_path": str(test_image)
                        }
                        # DeepSeek不支持图像，使用文本模式
                        result = await agent.execute_task(task, "object_detection", {"image_path": str(test_image)})
                        prediction = result.get("action", {}).get("objects", [])
                        result_data = result
                    
                    eval_result = evaluators[model_name].evaluate_task(
                        "object_detection", prediction, true_objects,
                        {"action": result_data} if tester else result_data
                    )
                    
                    all_results[model_name]["object_detection"] = {
                        "prediction": prediction,
                        "ground_truth": true_objects,
                        "score": eval_result["overall_score"]
                    }
                    
                    logger.info(f"  {model_name}: 检测到{len(prediction)}个对象, 得分: {eval_result['overall_score']:.3f}")
                except Exception as e:
                    logger.error(f"  {model_name} 失败: {e}")
                    all_results[model_name]["object_detection"] = {"error": str(e)}
    
    # ===== 任务3: 地理定位 =====
    logger.info("\n" + "=" * 80)
    logger.info("📊 任务3: 地理定位 (Geolocation)")
    logger.info("=" * 80)
    
    city_options = ["Beijing", "Paris", "London", "NewYork", "Tokyo"]
    
    if dataset and images:
        test_image = images[0]
        ground_truth_city = "Paris"
        
        for model_name, tester, agent in [
            ("bare_ds_chat", bare_ds_chat, None),
            ("bare_ds_reasoner", bare_ds_reasoner, None),
            ("agent_ds_chat", None, agent_ds_chat),
            ("agent_ds_reasoner", None, agent_ds_reasoner)
        ]:
            try:
                if tester:
                    prediction, raw = await tester.test_geolocation(str(test_image), city_options)
                    result_data = {"city": prediction, "raw": raw}
                else:
                    task = {
                        "task_type": "geolocation",
                        "data_type": "remote_sensing",
                        "image_path": str(test_image)
                    }
                    result = await agent.execute_task(task, "geolocation", {"image_path": str(test_image), "city_options": city_options})
                    prediction = result.get("action", {}).get("identified_city", "Unknown")
                    result_data = result
                
                eval_result = evaluators[model_name].evaluate_task(
                    "geolocation", prediction, ground_truth_city,
                    {"action": result_data} if tester else result_data
                )
                
                all_results[model_name]["geolocation"] = {
                    "prediction": prediction,
                    "ground_truth": ground_truth_city,
                    "score": eval_result["overall_score"]
                }
                
                logger.info(f"  {model_name}: 预测{prediction}, 真实{ground_truth_city}, 得分: {eval_result['overall_score']:.3f}")
            except Exception as e:
                logger.error(f"  {model_name} 失败: {e}")
                all_results[model_name]["geolocation"] = {"error": str(e)}
    
    # ===== 任务4: 地理问答 =====
    logger.info("\n" + "=" * 80)
    logger.info("📊 任务4: 地理问答 (GeoQA)")
    logger.info("=" * 80)
    
    question = "What is the population density of downtown Beijing?"
    context = {"population": 21500000, "area": 16410}
    ground_truth_answer = "high"
    
    for model_name, tester, agent in [
        ("bare_ds_chat", bare_ds_chat, None),
        ("bare_ds_reasoner", bare_ds_reasoner, None),
        ("agent_ds_chat", None, agent_ds_chat),
        ("agent_ds_reasoner", None, agent_ds_reasoner)
    ]:
        try:
            if tester:
                prediction, raw = await tester.test_geoqa(question, context)
                result_data = {"answer": prediction, "raw": raw}
            else:
                task = {
                    "task_type": "geoqa",
                    "data_type": "text",
                    "question": question
                }
                result = await agent.execute_task(task, "geoqa", context)
                prediction = result.get("action", {}).get("answer", "")
                result_data = result
            
            eval_result = evaluators[model_name].evaluate_task(
                "geoqa", prediction, ground_truth_answer,
                {"action": result_data} if tester else result_data
            )
            
            all_results[model_name]["geoqa"] = {
                "prediction": prediction[:50] if isinstance(prediction, str) else prediction,
                "ground_truth": ground_truth_answer,
                "score": eval_result["overall_score"]
            }
            
            logger.info(f"  {model_name}: 得分: {eval_result['overall_score']:.3f}")
        except Exception as e:
            logger.error(f"  {model_name} 失败: {e}")
            all_results[model_name]["geoqa"] = {"error": str(e)}
    
    # ===== 任务5: 移动性预测 =====
    logger.info("\n" + "=" * 80)
    logger.info("📊 任务5: 移动性预测 (Mobility Prediction)")
    logger.info("=" * 80)
    
    trajectory_data = {"avg_length": 5, "pattern_count": 15}
    ground_truth_location = "commercial_area"
    
    for model_name, tester, agent in [
        ("bare_ds_chat", bare_ds_chat, None),
        ("bare_ds_reasoner", bare_ds_reasoner, None),
        ("agent_ds_chat", None, agent_ds_chat),
        ("agent_ds_reasoner", None, agent_ds_reasoner)
    ]:
        try:
            if tester:
                prediction, raw = await tester.test_mobility_prediction(trajectory_data)
                result_data = {"location": prediction, "raw": raw}
            else:
                task = {"task_type": "mobility_prediction", "data_type": "trajectory"}
                result = await agent.execute_task(task, "mobility_prediction", {"flow_patterns": trajectory_data})
                prediction = result.get("action", {}).get("predicted_location", "")
                result_data = result
            
            eval_result = evaluators[model_name].evaluate_task(
                "mobility_prediction", prediction, ground_truth_location,
                {"action": result_data} if tester else result_data
            )
            
            all_results[model_name]["mobility_prediction"] = {
                "prediction": prediction,
                "ground_truth": ground_truth_location,
                "score": eval_result["overall_score"]
            }
            
            logger.info(f"  {model_name}: 预测{prediction}, 得分: {eval_result['overall_score']:.3f}")
        except Exception as e:
            logger.error(f"  {model_name} 失败: {e}")
            all_results[model_name]["mobility_prediction"] = {"error": str(e)}
    
    # ===== 任务6: 交通信号 =====
    logger.info("\n" + "=" * 80)
    logger.info("📊 任务6: 交通信号 (Traffic Signal)")
    logger.info("=" * 80)
    
    road_data = {"road_count": 4, "total_length": 2000}
    ground_truth_time = 45
    
    for model_name, tester, agent in [
        ("bare_ds_chat", bare_ds_chat, None),
        ("bare_ds_reasoner", bare_ds_reasoner, None),
        ("agent_ds_chat", None, agent_ds_chat),
        ("agent_ds_reasoner", None, agent_ds_reasoner)
    ]:
        try:
            if tester:
                prediction, raw = await tester.test_traffic_signal(road_data)
                result_data = {"green_time": prediction, "raw": raw}
            else:
                task = {"task_type": "traffic_signal", "data_type": "osm"}
                result = await agent.execute_task(task, "traffic_signal", {"road_network": road_data})
                prediction = result.get("action", {}).get("signal_plan", {}).get("green_time", 30)
                result_data = result
            
            eval_result = evaluators[model_name].evaluate_task(
                "traffic_signal", prediction, ground_truth_time,
                {"action": result_data} if tester else result_data
            )
            
            all_results[model_name]["traffic_signal"] = {
                "prediction": prediction,
                "ground_truth": ground_truth_time,
                "score": eval_result["overall_score"]
            }
            
            logger.info(f"  {model_name}: 预测{prediction}s, 真实{ground_truth_time}s, 得分: {eval_result['overall_score']:.3f}")
        except Exception as e:
            logger.error(f"  {model_name} 失败: {e}")
            all_results[model_name]["traffic_signal"] = {"error": str(e)}
    
    # ===== 任务7: 户外导航 =====
    logger.info("\n" + "=" * 80)
    logger.info("📊 任务7: 户外导航 (Outdoor Navigation)")
    logger.info("=" * 80)
    
    start = "Beijing Railway Station"
    end = "Tiananmen Square"
    ground_truth_route = "Head west on Chang'an Avenue"
    
    for model_name, tester, agent in [
        ("bare_ds_chat", bare_ds_chat, None),
        ("bare_ds_reasoner", bare_ds_reasoner, None),
        ("agent_ds_chat", None, agent_ds_chat),
        ("agent_ds_reasoner", None, agent_ds_reasoner)
    ]:
        try:
            if tester:
                prediction, raw = await tester.test_navigation(start, end)
                result_data = {"route": prediction, "raw": raw}
            else:
                task = {
                    "task_type": "outdoor_navigation",
                    "data_type": "osm",
                    "start": start,
                    "end": end
                }
                result = await agent.execute_task(task, "outdoor_navigation", {"road_network": {"road_count": 5}})
                prediction = result.get("action", {}).get("route", "")
                result_data = result
            
            eval_result = evaluators[model_name].evaluate_task(
                "outdoor_navigation", prediction, ground_truth_route,
                {"action": result_data} if tester else result_data
            )
            
            all_results[model_name]["outdoor_navigation"] = {
                "prediction": prediction[:50] if isinstance(prediction, str) else prediction,
                "ground_truth": ground_truth_route,
                "score": eval_result["overall_score"]
            }
            
            logger.info(f"  {model_name}: 得分: {eval_result['overall_score']:.3f}")
        except Exception as e:
            logger.error(f"  {model_name} 失败: {e}")
            all_results[model_name]["outdoor_navigation"] = {"error": str(e)}
    
    # ===== 任务8: 城市探索 =====
    logger.info("\n" + "=" * 80)
    logger.info("📊 任务8: 城市探索 (Urban Exploration)")
    logger.info("=" * 80)
    
    city = "Beijing"
    poi_distribution = {"restaurant": 15, "park": 5, "museum": 3, "shop": 20}
    ground_truth_targets = ["restaurant", "park", "museum"]
    
    for model_name, tester, agent in [
        ("bare_ds_chat", bare_ds_chat, None),
        ("bare_ds_reasoner", bare_ds_reasoner, None),
        ("agent_ds_chat", None, agent_ds_chat),
        ("agent_ds_reasoner", None, agent_ds_reasoner)
    ]:
        try:
            if tester:
                prediction, raw = await tester.test_urban_exploration(city, poi_distribution)
                result_data = {"targets": prediction, "raw": raw}
            else:
                task = {"task_type": "urban_exploration", "data_type": "osm", "city": city}
                result = await agent.execute_task(task, "urban_exploration", {"poi_categories": poi_distribution})
                prediction = result.get("action", {}).get("exploration_plan", {}).get("targets", [])
                result_data = result
            
            eval_result = evaluators[model_name].evaluate_task(
                "urban_exploration", prediction, ground_truth_targets,
                {"action": result_data} if tester else result_data
            )
            
            all_results[model_name]["urban_exploration"] = {
                "prediction": prediction,
                "ground_truth": ground_truth_targets,
                "score": eval_result["overall_score"]
            }
            
            logger.info(f"  {model_name}: 预测{prediction}, 得分: {eval_result['overall_score']:.3f}")
        except Exception as e:
            logger.error(f"  {model_name} 失败: {e}")
            all_results[model_name]["urban_exploration"] = {"error": str(e)}
    
    # ===== 结果汇总 =====
    logger.info("\n" + "=" * 80)
    logger.info("📈 DeepSeek 8任务测试结果")
    logger.info("=" * 80)
    
    # 计算每个模型的平均分
    model_averages = {}
    for model_name in evaluators.keys():
        scores = [task["score"] for task in all_results[model_name].values() if "score" in task]
        avg = sum(scores) / len(scores) if scores else 0
        model_averages[model_name] = avg
    
    # 按平均分排序
    sorted_models = sorted(model_averages.items(), key=lambda x: x[1], reverse=True)
    
    logger.info("\n模型排名（按平均分）:")
    for rank, (model_name, avg) in enumerate(sorted_models, 1):
        logger.info(f"  {rank}. {model_name}: {avg:.3f}")
    
    # Agent框架提升分析
    logger.info("\n" + "=" * 80)
    logger.info("🎯 Agent框架提升分析")
    logger.info("=" * 80)
    
    # Chat提升
    chat_bare = model_averages["bare_ds_chat"]
    chat_agent = model_averages["agent_ds_chat"]
    chat_improvement = chat_agent - chat_bare
    chat_improvement_pct = (chat_improvement / chat_bare * 100) if chat_bare > 0 else 0
    
    logger.info(f"\nDeepSeek-Chat:")
    logger.info(f"  裸模型: {chat_bare:.3f}")
    logger.info(f"  Agent+模型: {chat_agent:.3f}")
    logger.info(f"  提升: {chat_improvement:+.3f} ({chat_improvement_pct:+.1f}%)")
    
    # Reasoner提升
    reasoner_bare = model_averages["bare_ds_reasoner"]
    reasoner_agent = model_averages["agent_ds_reasoner"]
    reasoner_improvement = reasoner_agent - reasoner_bare
    reasoner_improvement_pct = (reasoner_improvement / reasoner_bare * 100) if reasoner_bare > 0 else 0
    
    logger.info(f"\nDeepSeek-Reasoner:")
    logger.info(f"  裸模型: {reasoner_bare:.3f}")
    logger.info(f"  Agent+模型: {reasoner_agent:.3f}")
    logger.info(f"  提升: {reasoner_improvement:+.3f} ({reasoner_improvement_pct:+.1f}%)")
    
    # 保存结果
    output_dir = Path("results")
    output_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"deepseek_8tasks_comparison_{timestamp}.json"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({
            "results": all_results,
            "averages": model_averages,
            "improvements": {
                "chat": {"absolute": chat_improvement, "percentage": chat_improvement_pct},
                "reasoner": {"absolute": reasoner_improvement, "percentage": reasoner_improvement_pct}
            },
            "timestamp": timestamp
        }, f, indent=2, ensure_ascii=False)
    
    logger.info(f"\n💾 详细结果已保存到: {output_path}")
    
    return all_results, model_averages


if __name__ == "__main__":
    asyncio.run(run_deepseek_tests())
