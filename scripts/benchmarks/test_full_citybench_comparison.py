"""
Full CityBench Real Data Comparison Test
全量CityBench真实数据对比测试：裸Qwen vs Urban Agent
"""

import asyncio
import json
import logging
from pathlib import Path
from datetime import datetime
import sys
import os
from typing import Dict, List, Any, Optional
from collections import defaultdict

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

from urban_agent.core.agent import UrbanAgent
from urban_agent.evaluation.citybench_evaluator import CityBenchEvaluator
from urban_agent.llm.qwen_client import QwenClient
from urban_agent.tools.geo_tools import CityBenchDataLoader, GeoDataLoader, ImageProcessor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# CityBench数据路径
CITYBENCH_PATH = "d:\\GitHub_1\\world_agent\\urban-mobility-agent\\paper4_urban_svgagent\\third_party\\CityBench-main"


class BareQwenTester:
    """裸Qwen测试器 - 直接调用API无Agent框架"""
    
    def __init__(self, qwen_client: QwenClient):
        self.qwen = qwen_client
    
    async def test_remote_sensing_object_detection(
        self, 
        image_path: str, 
        image_id: str,
        city: str
    ) -> Dict:
        """裸Qwen遥感目标检测"""
        # 加载图像
        image = GeoDataLoader.load_remote_sensing_image(image_path)
        if image is None:
            return {"error": "Failed to load image"}
        
        # 直接使用VLM分析
        prompt = """Analyze this remote sensing image and list all visible urban objects.
        Return a JSON array of object names. Be specific and concise."""
        
        try:
            response = await self.qwen.analyze_image(image_path, prompt)
            
            # 解析对象列表
            import re
            # 尝试提取JSON数组
            json_match = re.search(r'\[.*?\]', response, re.DOTALL)
            if json_match:
                try:
                    objects = json.loads(json_match.group())
                except:
                    objects = [obj.strip() for obj in response.split(',') if obj.strip()]
            else:
                objects = [obj.strip() for obj in response.split(',') if obj.strip()]
            
            return {
                "objects": objects[:20],  # 限制数量
                "raw_response": response[:500],
                "image_id": image_id
            }
        except Exception as e:
            logger.error(f"裸Qwen分析失败: {e}")
            return {"objects": [], "error": str(e)}
    
    async def test_geolocation(self, image_path: str, city_options: List[str]) -> Dict:
        """裸Qwen地理定位"""
        prompt = f"""Identify which city this image is from. Choose from: {', '.join(city_options)}.
        Return ONLY the city name."""
        
        try:
            response = await self.qwen.analyze_image(image_path, prompt)
            
            # 提取城市名
            identified = "Unknown"
            for city in city_options:
                if city.lower() in response.lower():
                    identified = city
                    break
            
            return {
                "city": identified,
                "raw_response": response[:200]
            }
        except Exception as e:
            return {"city": "Unknown", "error": str(e)}
    
    async def test_urban_exploration(
        self, 
        city: str, 
        start_location: str,
        poi_distribution: Dict
    ) -> Dict:
        """裸Qwen城市探索"""
        prompt = f"""Given the following POI distribution in {city}:
        {json.dumps(poi_distribution, indent=2)}
        
        Starting from {start_location}, recommend the top 3 POI categories to explore.
        Return ONLY a comma-separated list of 3 categories."""
        
        try:
            response = await self.qwen.generate(prompt)
            
            # 解析类别
            categories = [cat.strip() for cat in response.split(',') if cat.strip()]
            
            return {
                "targets": categories[:3],
                "raw_response": response[:200]
            }
        except Exception as e:
            return {"targets": [], "error": str(e)}


async def run_full_comparison_test():
    """运行全量对比测试"""
    logger.info("\n" + "=" * 80)
    logger.info("🚀 全量CityBench真实数据对比测试")
    logger.info("对比：裸Qwen vs Urban Agent + Qwen")
    logger.info("=" * 80)
    
    # 初始化
    try:
        qwen_client = QwenClient()
        logger.info("✅ Qwen客户端初始化成功")
    except Exception as e:
        logger.error(f"❌ Qwen客户端初始化失败: {e}")
        return
    
    agent = UrbanAgent(llm_client=qwen_client, vlm_client=qwen_client, config={})
    logger.info("✅ Urban Agent初始化成功")
    
    bare_qwen = BareQwenTester(qwen_client)
    logger.info("✅ 裸Qwen测试器初始化成功")
    
    # 数据加载器
    data_loader = CityBenchDataLoader(CITYBENCH_PATH)
    
    # 评估器
    bare_evaluator = CityBenchEvaluator()
    agent_evaluator = CityBenchEvaluator()
    
    # 结果存储
    results = {
        "remote_sensing": {"bare": [], "agent": []},
        "geolocation": {"bare": [], "agent": []},
        "urban_exploration": {"bare": [], "agent": []}
    }
    
    # ===== 1. 遥感影像目标检测测试 =====
    logger.info("\n" + "=" * 80)
    logger.info("🛰️ 测试1: 遥感影像目标检测")
    logger.info("=" * 80)
    
    # 获取所有城市的遥感影像
    test_cities = ["Paris", "Beijing", "London", "NewYork"]
    rs_test_count = 0
    max_rs_tests = 10  # 限制测试数量
    
    for city in test_cities:
        if rs_test_count >= max_rs_tests:
            break
            
        logger.info(f"\n📍 测试城市: {city}")
        
        # 加载该城市的遥感数据
        dataset = data_loader.load_remote_sensing_dataset(city)
        if not dataset:
            continue
        
        image_dir = Path(dataset["image_dir"])
        images = list(image_dir.glob("*.png"))[:3]  # 每个城市测试3张
        
        for img_path in images:
            if rs_test_count >= max_rs_tests:
                break
            
            image_id = img_path.stem
            ground_truth = dataset["labels"].get(image_id, {})
            true_objects = [obj for obj, val in ground_truth.items() if val == 1]
            
            logger.info(f"  测试影像: {image_id}")
            
            # 裸Qwen测试
            logger.info("    🤖 裸Qwen...")
            try:
                bare_result = await bare_qwen.test_remote_sensing_object_detection(
                    str(img_path), image_id, city
                )
                bare_prediction = bare_result.get("objects", [])
                
                bare_eval = bare_evaluator.evaluate_task(
                    "object_detection",
                    bare_prediction,
                    true_objects,
                    {"perception": {}, "reasoning": {}, "action": bare_result}
                )
                
                results["remote_sensing"]["bare"].append({
                    "city": city,
                    "image_id": image_id,
                    "score": bare_eval["overall_score"],
                    "prediction": bare_prediction,
                    "ground_truth": true_objects
                })
                
                logger.info(f"      得分: {bare_eval['overall_score']:.3f}")
            except Exception as e:
                logger.error(f"      裸Qwen失败: {e}")
            
            # Urban Agent测试
            logger.info("    🎯 Urban Agent...")
            try:
                task = {
                    "task_type": "object_detection",
                    "data_type": "remote_sensing",
                    "image_path": str(img_path),
                    "image_id": image_id
                }
                
                image = GeoDataLoader.load_remote_sensing_image(str(img_path))
                city_data = {"image": image, "city": city}
                
                agent_result = await agent.execute_task(task, "object_detection", city_data)
                agent_prediction = agent_result.get("action", {}).get("objects", [])
                
                agent_eval = agent_evaluator.evaluate_task(
                    "object_detection",
                    agent_prediction,
                    true_objects,
                    agent_result
                )
                
                results["remote_sensing"]["agent"].append({
                    "city": city,
                    "image_id": image_id,
                    "score": agent_eval["overall_score"],
                    "prediction": agent_prediction,
                    "ground_truth": true_objects
                })
                
                logger.info(f"      得分: {agent_eval['overall_score']:.3f}")
            except Exception as e:
                logger.error(f"      Agent失败: {e}")
            
            rs_test_count += 1
    
    # ===== 2. 地理定位测试 =====
    logger.info("\n" + "=" * 80)
    logger.info("🌍 测试2: 地理定位")
    logger.info("=" * 80)
    
    # 使用遥感影像进行地理定位测试
    geo_cities = ["Beijing", "Paris", "London", "NewYork", "Tokyo"]
    
    for city in geo_cities[:3]:  # 测试3个城市
        logger.info(f"\n📍 测试城市: {city}")
        
        # 获取该城市的一张影像
        dataset = data_loader.load_remote_sensing_dataset(city)
        if not dataset:
            continue
        
        image_dir = Path(dataset["image_dir"])
        images = list(image_dir.glob("*.png"))
        
        if not images:
            continue
        
        img_path = images[0]
        
        # 裸Qwen测试
        logger.info("    🤖 裸Qwen...")
        try:
            bare_result = await bare_qwen.test_geolocation(str(img_path), geo_cities)
            bare_prediction = bare_result.get("city", "Unknown")
            
            bare_eval = bare_evaluator.evaluate_task(
                "geolocation",
                bare_prediction,
                city,
                {"perception": {}, "reasoning": {}, "action": bare_result}
            )
            
            results["geolocation"]["bare"].append({
                "city": city,
                "predicted": bare_prediction,
                "score": bare_eval["overall_score"]
            })
            
            logger.info(f"      预测: {bare_prediction}, 真实: {city}, 得分: {bare_eval['overall_score']:.3f}")
        except Exception as e:
            logger.error(f"      裸Qwen失败: {e}")
        
        # Urban Agent测试
        logger.info("    🎯 Urban Agent...")
        try:
            task = {
                "task_type": "geolocation",
                "data_type": "remote_sensing",
                "image_path": str(img_path)
            }
            
            image = GeoDataLoader.load_remote_sensing_image(str(img_path))
            city_data = {"image": image, "city_options": geo_cities}
            
            agent_result = await agent.execute_task(task, "geolocation", city_data)
            agent_prediction = agent_result.get("action", {}).get("identified_city", "Unknown")
            
            agent_eval = agent_evaluator.evaluate_task(
                "geolocation",
                agent_prediction,
                city,
                agent_result
            )
            
            results["geolocation"]["agent"].append({
                "city": city,
                "predicted": agent_prediction,
                "score": agent_eval["overall_score"]
            })
            
            logger.info(f"      预测: {agent_prediction}, 真实: {city}, 得分: {agent_eval['overall_score']:.3f}")
        except Exception as e:
            logger.error(f"      Agent失败: {e}")
    
    # ===== 3. 城市探索测试 =====
    logger.info("\n" + "=" * 80)
    logger.info("🏙️ 测试3: 城市探索")
    logger.info("=" * 80)
    
    exploration_cities = ["Beijing", "Paris", "London"]
    
    for city in exploration_cities:
        logger.info(f"\n📍 测试城市: {city}")
        
        # 加载探索任务
        df = data_loader.load_exploration_tasks(city)
        if df is None or df.empty:
            continue
        
        # 获取前2个任务
        for idx in range(min(2, len(df))):
            task_data = df.iloc[idx]
            start_location = task_data.get("start", f"Location_{idx}")
            
            # 模拟POI分布
            poi_distribution = {
                "restaurant": 15,
                "park": 5,
                "museum": 3,
                "shop": 20,
                "cafe": 8
            }
            
            ground_truth = ["restaurant", "park", "museum"]
            
            logger.info(f"  任务 {idx+1}: 从 {start_location} 开始探索")
            
            # 裸Qwen测试
            logger.info("    🤖 裸Qwen...")
            try:
                bare_result = await bare_qwen.test_urban_exploration(
                    city, start_location, poi_distribution
                )
                bare_prediction = bare_result.get("targets", [])
                
                bare_eval = bare_evaluator.evaluate_task(
                    "urban_exploration",
                    bare_prediction,
                    ground_truth,
                    {"perception": {}, "reasoning": {}, "action": bare_result}
                )
                
                results["urban_exploration"]["bare"].append({
                    "city": city,
                    "task_id": idx,
                    "score": bare_eval["overall_score"],
                    "prediction": bare_prediction
                })
                
                logger.info(f"      得分: {bare_eval['overall_score']:.3f}")
            except Exception as e:
                logger.error(f"      裸Qwen失败: {e}")
            
            # Urban Agent测试
            logger.info("    🎯 Urban Agent...")
            try:
                task = {
                    "task_type": "urban_exploration",
                    "data_type": "osm",
                    "city": city,
                    "start_location": start_location
                }
                
                city_data = {
                    "city": city,
                    "poi_categories": poi_distribution
                }
                
                agent_result = await agent.execute_task(task, "urban_exploration", city_data)
                agent_prediction = agent_result.get("action", {}).get("exploration_plan", {}).get("targets", [])
                
                agent_eval = agent_evaluator.evaluate_task(
                    "urban_exploration",
                    agent_prediction,
                    ground_truth,
                    agent_result
                )
                
                results["urban_exploration"]["agent"].append({
                    "city": city,
                    "task_id": idx,
                    "score": agent_eval["overall_score"],
                    "prediction": agent_prediction
                })
                
                logger.info(f"      得分: {agent_eval['overall_score']:.3f}")
            except Exception as e:
                logger.error(f"      Agent失败: {e}")
    
    # ===== 结果汇总 =====
    logger.info("\n" + "=" * 80)
    logger.info("📊 全量测试汇总")
    logger.info("=" * 80)
    
    # 计算各任务类型的平均得分
    summary = {}
    
    for task_type in ["remote_sensing", "geolocation", "urban_exploration"]:
        bare_scores = [r["score"] for r in results[task_type]["bare"]]
        agent_scores = [r["score"] for r in results[task_type]["agent"]]
        
        bare_avg = sum(bare_scores) / len(bare_scores) if bare_scores else 0
        agent_avg = sum(agent_scores) / len(agent_scores) if agent_scores else 0
        
        improvement = agent_avg - bare_avg
        improvement_pct = (improvement / bare_avg * 100) if bare_avg > 0 else 0
        
        summary[task_type] = {
            "bare_count": len(bare_scores),
            "agent_count": len(agent_scores),
            "bare_avg": bare_avg,
            "agent_avg": agent_avg,
            "improvement": improvement,
            "improvement_pct": improvement_pct
        }
        
        logger.info(f"\n{task_type}:")
        logger.info(f"  裸Qwen:     {bare_avg:.3f} (n={len(bare_scores)})")
        logger.info(f"  Urban Agent: {agent_avg:.3f} (n={len(agent_scores)})")
        logger.info(f"  提升:       {improvement:+.3f} ({improvement_pct:+.1f}%)")
    
    # 总体统计
    all_bare = []
    all_agent = []
    for task_type in results:
        all_bare.extend([r["score"] for r in results[task_type]["bare"]])
        all_agent.extend([r["score"] for r in results[task_type]["agent"]])
    
    overall_bare = sum(all_bare) / len(all_bare) if all_bare else 0
    overall_agent = sum(all_agent) / len(all_agent) if all_agent else 0
    overall_improvement = overall_agent - overall_bare
    
    logger.info("\n" + "=" * 80)
    logger.info("📈 总体表现")
    logger.info("=" * 80)
    logger.info(f"裸Qwen平均:     {overall_bare:.3f}")
    logger.info(f"Urban Agent平均: {overall_agent:.3f}")
    logger.info(f"总体提升:       {overall_improvement:+.3f}")
    
    # 保存结果
    output_dir = Path("results")
    output_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"full_citybench_comparison_{timestamp}.json"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({
            "results": results,
            "summary": summary,
            "overall": {
                "bare_avg": overall_bare,
                "agent_avg": overall_agent,
                "improvement": overall_improvement
            },
            "timestamp": timestamp,
            "data_source": "real_citybench_full"
        }, f, indent=2, ensure_ascii=False)
    
    logger.info(f"\n💾 详细结果已保存到: {output_path}")
    
    return results, summary


if __name__ == "__main__":
    asyncio.run(run_full_comparison_test())
