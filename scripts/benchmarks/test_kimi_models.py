"""
Kimi Models Test
测试Kimi k2.5和Kimi Code模型
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

from urban_agent.llm.kimi_client import KimiClient, MultiLLMClient
from urban_agent.core.agent import UrbanAgent
from urban_agent.evaluation.citybench_evaluator import CityBenchEvaluator
from urban_agent.tools.geo_tools import CityBenchDataLoader, GeoDataLoader

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# CityBench数据路径
CITYBENCH_PATH = "d:\\GitHub_1\\world_agent\\urban-mobility-agent\\paper4_urban_svgagent\\third_party\\CityBench-main"


async def test_kimi_basic():
    """测试Kimi基础功能"""
    logger.info("\n" + "=" * 80)
    logger.info("🧪 测试Kimi基础功能")
    logger.info("=" * 80)
    
    results = {}
    
    # 1. 测试Kimi Standard (kimi-k2.5)
    logger.info("\n📌 测试1: Kimi Standard (kimi-k2.5)")
    try:
        kimi_std = KimiClient(client_type="standard")
        
        # 文本生成测试
        prompt = "What are the key factors affecting urban population density? List 3 factors."
        response = await kimi_std.generate(prompt)
        
        logger.info(f"✅ Kimi Standard文本生成成功")
        logger.info(f"   响应: {response[:200]}...")
        
        results["kimi_standard"] = {
            "status": "success",
            "text_response": response[:200]
        }
    except Exception as e:
        logger.error(f"❌ Kimi Standard测试失败: {e}")
        results["kimi_standard"] = {"status": "failed", "error": str(e)}
    
    # 2. 测试Kimi Coding (kimi-for-coding)
    logger.info("\n📌 测试2: Kimi Coding (kimi-for-coding)")
    try:
        kimi_code = KimiClient(client_type="coding")
        
        # 代码生成测试
        prompt = "Write a Python function to calculate the distance between two GPS coordinates using the Haversine formula."
        response = await kimi_code.code_generate(prompt)
        
        logger.info(f"✅ Kimi Coding代码生成成功")
        logger.info(f"   代码长度: {len(response)} characters")
        
        results["kimi_coding"] = {
            "status": "success",
            "code_length": len(response),
            "code_preview": response[:300]
        }
    except Exception as e:
        logger.error(f"❌ Kimi Coding测试失败: {e}")
        results["kimi_coding"] = {"status": "failed", "error": str(e)}
    
    return results


async def test_kimi_vision():
    """测试Kimi视觉能力"""
    logger.info("\n" + "=" * 80)
    logger.info("👁️ 测试Kimi视觉能力")
    logger.info("=" * 80)
    
    results = {}
    
    # 加载一张遥感影像
    data_loader = CityBenchDataLoader(CITYBENCH_PATH)
    dataset = data_loader.load_remote_sensing_dataset("Paris")
    
    if not dataset:
        logger.error("无法加载遥感数据")
        return results
    
    image_dir = Path(dataset["image_dir"])
    images = list(image_dir.glob("*.png"))
    
    if not images:
        logger.error("未找到影像")
        return results
    
    image_path = str(images[0])
    logger.info(f"测试影像: {image_path}")
    
    # 测试Kimi Standard视觉
    logger.info("\n📌 测试Kimi Standard视觉分析")
    try:
        kimi_std = KimiClient(client_type="standard")
        
        prompt = "Analyze this remote sensing image. What urban features can you identify?"
        response = await kimi_std.analyze_image(image_path, prompt)
        
        logger.info(f"✅ Kimi Standard视觉分析成功")
        logger.info(f"   分析结果: {response[:300]}...")
        
        results["kimi_standard_vision"] = {
            "status": "success",
            "analysis": response[:500]
        }
    except Exception as e:
        logger.error(f"❌ Kimi Standard视觉分析失败: {e}")
        results["kimi_standard_vision"] = {"status": "failed", "error": str(e)}
    
    return results


async def test_kimi_with_urban_agent():
    """测试Kimi与Urban Agent集成"""
    logger.info("\n" + "=" * 80)
    logger.info("🎯 测试Kimi与Urban Agent集成")
    logger.info("=" * 80)
    
    results = {}
    
    # 测试数据
    data_loader = CityBenchDataLoader(CITYBENCH_PATH)
    dataset = data_loader.load_remote_sensing_dataset("Beijing")
    
    if not dataset:
        logger.error("无法加载数据")
        return results
    
    image_dir = Path(dataset["image_dir"])
    images = list(image_dir.glob("*.png"))
    
    if not images:
        logger.error("未找到影像")
        return results
    
    image_path = str(images[0])
    image_id = images[0].stem
    ground_truth = dataset["labels"].get(image_id, {})
    true_objects = [obj for obj, val in ground_truth.items() if val == 1]
    
    logger.info(f"测试影像: {image_id}")
    
    # 1. 使用Kimi Standard + Urban Agent
    logger.info("\n📌 测试Kimi Standard + Urban Agent")
    try:
        kimi_std = KimiClient(client_type="standard")
        agent = UrbanAgent(
            llm_client=kimi_std,
            vlm_client=kimi_std,
            config={}
        )
        
        task = {
            "task_type": "object_detection",
            "data_type": "remote_sensing",
            "image_path": image_path,
            "image_id": image_id
        }
        
        image = GeoDataLoader.load_remote_sensing_image(image_path)
        city_data = {"image": image, "city": "Beijing"}
        
        agent_result = await agent.execute_task(task, "object_detection", city_data)
        
        logger.info(f"✅ Kimi Standard + Agent成功")
        logger.info(f"   检测结果: {agent_result.get('action', {}).get('objects', [])}")
        
        results["kimi_standard_agent"] = {
            "status": "success",
            "objects": agent_result.get("action", {}).get("objects", [])
        }
    except Exception as e:
        logger.error(f"❌ Kimi Standard + Agent失败: {e}")
        results["kimi_standard_agent"] = {"status": "failed", "error": str(e)}
    
    return results


async def compare_models_on_citybench():
    """对比不同模型在CityBench上的表现"""
    logger.info("\n" + "=" * 80)
    logger.info("📊 多模型CityBench对比测试")
    logger.info("=" * 80)
    
    # 初始化多LLM客户端
    multi_llm = MultiLLMClient()
    available_clients = multi_llm.list_clients()
    
    logger.info(f"可用客户端: {available_clients}")
    
    if len(available_clients) < 2:
        logger.warning("可用客户端不足，无法进行对比")
        return {}
    
    # 加载测试数据
    data_loader = CityBenchDataLoader(CITYBENCH_PATH)
    dataset = data_loader.load_remote_sensing_dataset("Paris")
    
    if not dataset:
        logger.error("无法加载数据")
        return {}
    
    image_dir = Path(dataset["image_dir"])
    images = list(image_dir.glob("*.png"))[:3]  # 测试3张影像
    
    results = {client: [] for client in available_clients}
    
    for img_path in images:
        image_id = img_path.stem
        ground_truth = dataset["labels"].get(image_id, {})
        true_objects = [obj for obj, val in ground_truth.items() if val == 1]
        
        logger.info(f"\n📍 测试影像: {image_id}")
        
        for client_name in available_clients:
            logger.info(f"  🔄 使用 {client_name}...")
            
            try:
                client = multi_llm.get_client(client_name)
                agent = UrbanAgent(
                    llm_client=client,
                    vlm_client=client,
                    config={}
                )
                
                task = {
                    "task_type": "object_detection",
                    "data_type": "remote_sensing",
                    "image_path": str(img_path),
                    "image_id": image_id
                }
                
                image = GeoDataLoader.load_remote_sensing_image(str(img_path))
                city_data = {"image": image, "city": "Paris"}
                
                agent_result = await agent.execute_task(task, "object_detection", city_data)
                prediction = agent_result.get("action", {}).get("objects", [])
                
                # 简单评估
                if true_objects:
                    correct = len(set(prediction) & set(true_objects))
                    precision = correct / len(prediction) if prediction else 0
                    recall = correct / len(true_objects) if true_objects else 0
                    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
                else:
                    f1 = 0
                
                results[client_name].append({
                    "image_id": image_id,
                    "f1_score": f1,
                    "prediction": prediction,
                    "ground_truth": true_objects
                })
                
                logger.info(f"      F1: {f1:.3f}")
                
            except Exception as e:
                logger.error(f"      {client_name} 失败: {e}")
                results[client_name].append({
                    "image_id": image_id,
                    "error": str(e)
                })
    
    # 汇总结果
    logger.info("\n" + "=" * 80)
    logger.info("📈 模型对比结果")
    logger.info("=" * 80)
    
    for client_name, client_results in results.items():
        valid_results = [r for r in client_results if "f1_score" in r]
        if valid_results:
            avg_f1 = sum(r["f1_score"] for r in valid_results) / len(valid_results)
            logger.info(f"{client_name}: 平均F1 = {avg_f1:.3f} (n={len(valid_results)})")
        else:
            logger.info(f"{client_name}: 无有效结果")
    
    return results


async def main():
    """主测试函数"""
    logger.info("\n" + "=" * 80)
    logger.info("🚀 Kimi模型测试套件")
    logger.info("=" * 80)
    
    all_results = {}
    
    # 1. 基础功能测试
    basic_results = await test_kimi_basic()
    all_results["basic"] = basic_results
    
    # 2. 视觉能力测试
    vision_results = await test_kimi_vision()
    all_results["vision"] = vision_results
    
    # 3. Urban Agent集成测试
    agent_results = await test_kimi_with_urban_agent()
    all_results["agent_integration"] = agent_results
    
    # 4. CityBench对比测试
    comparison_results = await compare_models_on_citybench()
    all_results["citybench_comparison"] = comparison_results
    
    # 保存结果
    output_dir = Path("results")
    output_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"kimi_test_{timestamp}.json"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    
    logger.info(f"\n💾 测试结果已保存到: {output_path}")
    
    # 输出总结
    logger.info("\n" + "=" * 80)
    logger.info("📋 测试总结")
    logger.info("=" * 80)
    
    for test_type, results in all_results.items():
        logger.info(f"\n{test_type}:")
        for model, result in results.items():
            status = result.get("status", "unknown")
            logger.info(f"  {model}: {status}")
    
    return all_results


if __name__ == "__main__":
    asyncio.run(main())
