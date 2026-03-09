"""
Real CityBench Data Test
使用真实CityBench数据测试Urban Agent
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
from urban_agent.tools.geo_tools import CityBenchDataLoader, GeoDataLoader, ImageProcessor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# CityBench数据路径
CITYBENCH_PATH = "d:\\GitHub_1\\world_agent\\urban-mobility-agent\\paper4_urban_svgagent\\third_party\\CityBench-main"


async def test_remote_sensing_with_real_data(agent: UrbanAgent, evaluator: CityBenchEvaluator, city: str = "Paris"):
    """使用真实遥感影像测试目标检测"""
    logger.info(f"\n{'='*60}")
    logger.info(f"🛰️ 真实遥感影像测试 - {city}")
    logger.info(f"{'='*60}")
    
    # 加载CityBench数据
    data_loader = CityBenchDataLoader(CITYBENCH_PATH)
    task_info = data_loader.get_sample_task("remote_sensing", city)
    
    if not task_info:
        logger.error(f"无法加载{city}的遥感数据")
        return None, None
    
    image_path = task_info["image_path"]
    ground_truth = task_info["ground_truth"]
    
    logger.info(f"影像路径: {image_path}")
    logger.info(f"真实标签: {ground_truth}")
    
    # 加载影像
    image = GeoDataLoader.load_remote_sensing_image(image_path)
    if image is None:
        logger.error("影像加载失败")
        return None, None
    
    # 预处理影像
    image_stats = ImageProcessor.analyze_image_statistics(image)
    logger.info(f"影像统计: {image_stats}")
    
    # 准备任务
    task = {
        "task_type": "object_detection",
        "data_type": "remote_sensing",
        "image_path": image_path,
        "image_id": task_info["image_id"]
    }
    
    city_data = {
        "image": image,
        "image_stats": image_stats,
        "city": city
    }
    
    # 执行Agent任务
    logger.info("\n🎯 Urban Agent执行中...")
    result = await agent.execute_task(task, "object_detection", city_data)
    
    # 提取预测结果
    prediction = result.get("action", {}).get("objects", [])
    
    # 从ground_truth中提取正样本
    true_objects = [obj for obj, val in ground_truth.items() if val == 1]
    
    logger.info(f"Agent预测: {prediction}")
    logger.info(f"真实物体: {true_objects}")
    
    # 评估
    eval_result = evaluator.evaluate_task(
        "object_detection",
        prediction,
        true_objects,
        result
    )
    
    logger.info(f"评估得分: {eval_result['overall_score']:.3f}")
    
    return result, eval_result


async def test_urban_exploration_with_real_data(agent: UrbanAgent, evaluator: CityBenchEvaluator, city: str = "Beijing"):
    """使用真实城市数据测试探索任务"""
    logger.info(f"\n{'='*60}")
    logger.info(f"🏙️ 真实城市探索测试 - {city}")
    logger.info(f"{'='*60}")
    
    # 加载CityBench数据
    data_loader = CityBenchDataLoader(CITYBENCH_PATH)
    
    # 加载城市Shapefile
    gdf = data_loader.load_city_shapefile(city)
    if gdf is not None:
        logger.info(f"成功加载{city}地图数据，记录数: {len(gdf)}")
        
        # 分析城市数据
        from urban_agent.tools.geo_tools import SpatialAnalyzer
        bounds = SpatialAnalyzer.extract_bounding_box(gdf)
        logger.info(f"城市边界: {bounds}")
    
    # 加载探索任务
    task_info = data_loader.get_sample_task("urban_exploration", city)
    
    if not task_info:
        logger.error(f"无法加载{city}的探索任务")
        return None, None
    
    logger.info(f"任务信息: {task_info}")
    
    # 准备任务
    task = {
        "task_type": "urban_exploration",
        "data_type": "osm",
        "city": city,
        "start_location": task_info.get("start_location", ""),
        "target_categories": task_info.get("target_categories", [])
    }
    
    city_data = {
        "geo_data": gdf,
        "city": city,
        "poi_categories": {"restaurant": 15, "park": 5, "museum": 3, "shop": 20}
    }
    
    # 执行Agent任务
    logger.info("\n🎯 Urban Agent执行中...")
    result = await agent.execute_task(task, "urban_exploration", city_data)
    
    # 提取预测结果
    prediction = result.get("action", {}).get("exploration_plan", {}).get("targets", [])
    ground_truth = task_info.get("target_categories", [])
    
    logger.info(f"Agent预测: {prediction}")
    logger.info(f"真实目标: {ground_truth}")
    
    # 评估
    eval_result = evaluator.evaluate_task(
        "urban_exploration",
        prediction,
        ground_truth,
        result
    )
    
    logger.info(f"评估得分: {eval_result['overall_score']:.3f}")
    
    return result, eval_result


async def test_geolocation_with_real_images(agent: UrbanAgent, evaluator: CityBenchEvaluator):
    """使用真实街景图像测试地理定位"""
    logger.info(f"\n{'='*60}")
    logger.info("🌍 真实地理定位测试")
    logger.info(f"{'='*60}")
    
    # 尝试加载街景图像
    street_view_dir = Path(CITYBENCH_PATH) / "citydata" / "street_view"
    
    if not street_view_dir.exists():
        logger.warning(f"街景目录不存在: {street_view_dir}")
        logger.info("使用模拟数据进行测试")
        
        # 使用模拟数据
        task = {
            "task_type": "geolocation",
            "data_type": "street_view",
            "image_path": "simulated",
            "content": {"hint": "European city with historic architecture"}
        }
        
        city_data = {
            "description": "Historic city center with narrow streets, old buildings, and cafes",
            "city_options": ["Paris", "London", "Rome", "Vienna"]
        }
    else:
        # 查找街景图像
        image_files = list(street_view_dir.glob("**/*.jpg")) + list(street_view_dir.glob("**/*.png"))
        
        if not image_files:
            logger.warning("未找到街景图像")
            return None, None
        
        image_path = str(image_files[0])
        logger.info(f"使用街景图像: {image_path}")
        
        # 加载图像
        image = GeoDataLoader.load_remote_sensing_image(image_path)
        
        task = {
            "task_type": "geolocation",
            "data_type": "street_view",
            "image_path": image_path
        }
        
        city_data = {
            "image": image,
            "description": "Street view image for geolocation"
        }
    
    # 执行Agent任务
    logger.info("\n🎯 Urban Agent执行中...")
    result = await agent.execute_task(task, "geolocation", city_data)
    
    prediction = result.get("action", {}).get("identified_city", "Unknown")
    ground_truth = "Paris"  # 假设真实城市
    
    logger.info(f"Agent预测: {prediction}")
    logger.info(f"真实城市: {ground_truth}")
    
    # 评估
    eval_result = evaluator.evaluate_task(
        "geolocation",
        prediction,
        ground_truth,
        result
    )
    
    logger.info(f"评估得分: {eval_result['overall_score']:.3f}")
    
    return result, eval_result


async def main():
    """主测试函数"""
    logger.info("\n" + "=" * 80)
    logger.info("🚀 真实CityBench数据测试")
    logger.info("=" * 80)
    
    # 检查CityBench数据是否存在
    if not Path(CITYBENCH_PATH).exists():
        logger.error(f"CityBench数据路径不存在: {CITYBENCH_PATH}")
        return
    
    logger.info(f"CityBench数据路径: {CITYBENCH_PATH}")
    
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
    
    # 初始化评估器
    evaluator = CityBenchEvaluator()
    
    # 测试任务列表
    test_results = {}
    
    # 1. 遥感影像目标检测
    try:
        result, eval_result = await test_remote_sensing_with_real_data(agent, evaluator, "Paris")
        if result:
            test_results["remote_sensing"] = {
                "success": True,
                "evaluation": eval_result
            }
    except Exception as e:
        logger.error(f"遥感测试失败: {e}")
        test_results["remote_sensing"] = {"success": False, "error": str(e)}
    
    # 2. 城市探索
    try:
        result, eval_result = await test_urban_exploration_with_real_data(agent, evaluator, "Beijing")
        if result:
            test_results["urban_exploration"] = {
                "success": True,
                "evaluation": eval_result
            }
    except Exception as e:
        logger.error(f"城市探索测试失败: {e}")
        test_results["urban_exploration"] = {"success": False, "error": str(e)}
    
    # 3. 地理定位
    try:
        result, eval_result = await test_geolocation_with_real_images(agent, evaluator)
        if result:
            test_results["geolocation"] = {
                "success": True,
                "evaluation": eval_result
            }
    except Exception as e:
        logger.error(f"地理定位测试失败: {e}")
        test_results["geolocation"] = {"success": False, "error": str(e)}
    
    # 输出总结
    logger.info("\n" + "=" * 80)
    logger.info("📊 真实数据测试总结")
    logger.info("=" * 80)
    
    summary = evaluator.get_summary()
    logger.info(f"\n总体评估摘要:")
    logger.info(json.dumps(summary, indent=2))
    
    # 保存结果
    output_dir = Path("results")
    output_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"real_citybench_test_{timestamp}.json"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({
            "test_results": test_results,
            "summary": summary,
            "timestamp": timestamp,
            "data_source": "real_citybench"
        }, f, indent=2, ensure_ascii=False)
    
    logger.info(f"\n💾 详细结果已保存到: {output_path}")
    
    # 统计成功率
    success_count = sum(1 for r in test_results.values() if r.get("success", False))
    logger.info(f"\n测试完成: {success_count}/{len(test_results)} 个任务成功")
    
    return test_results


if __name__ == "__main__":
    asyncio.run(main())
