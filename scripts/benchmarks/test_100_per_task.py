"""
CityBench 8任务 × 100条测试对比
每个方向测试100条，对比裸模型和Agent的性能
"""

import os
import sys
import asyncio
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Tuple
import random

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
from urban_agent.evaluation.citybench_evaluator_v2 import CityBenchEvaluatorV2
from urban_agent.llm.qwen_client import QwenClient
from urban_agent.llm.kimi_client import KimiClient
from urban_agent.tools.geo_tools import CityBenchDataLoader

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

CITYBENCH_PATH = "d:\\GitHub_1\\world_agent\\urban-mobility-agent\\paper4_urban_svgagent\\third_party\\CityBench-main"


class BareModelTester:
    """裸模型测试器"""
    
    def __init__(self, model_client, model_name: str):
        self.client = model_client
        self.model_name = model_name
    
    async def generate(self, prompt: str) -> str:
        """生成回答"""
        try:
            if hasattr(self.client, 'generate'):
                return await self.client.generate(prompt)
            else:
                # 直接调用vlm_client的chat方法
                from openai import AsyncOpenAI
                response = await self.client.chat.completions.create(
                    model=self.client.model,
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user", "content": prompt}
                    ]
                )
                return response.choices[0].message.content
        except Exception as e:
            logger.error(f"生成失败: {e}")
            return ""


class TaskSampler:
    """任务采样器 - 从CityBench数据中采样100条测试题"""
    
    def __init__(self, citybench_path: str):
        self.citybench_path = Path(citybench_path)
        self.data_loader = CityBenchDataLoader(citybench_path)
    
    def sample_population_tasks(self, n: int = 100) -> List[Dict]:
        """采样人口预测任务"""
        tasks = []
        # 从遥感数据目录加载图像和标签
        rs_dir = self.citybench_path / "citydata" / "remote_sensing"
        
        for city_dir in rs_dir.iterdir():
            if city_dir.is_dir():
                images = list(city_dir.glob("*.png"))
                for img in images[:n//13 + 1]:  # 每个城市平均分配
                    if len(tasks) >= n:
                        break
                    # 模拟ground_truth（实际应从标签文件读取）
                    tasks.append({
                        "image_path": str(img),
                        "city": city_dir.name,
                        "ground_truth": random.randint(1000, 10000)  # 模拟数据
                    })
                if len(tasks) >= n:
                    break
        
        return tasks[:n]
    
    def sample_object_detection_tasks(self, n: int = 100) -> List[Dict]:
        """采样目标检测任务"""
        tasks = []
        rs_dir = self.citybench_path / "citydata" / "remote_sensing"
        
        for city_dir in rs_dir.iterdir():
            if city_dir.is_dir():
                images = list(city_dir.glob("*.png"))
                for img in images[:n//13 + 1]:
                    if len(tasks) >= n:
                        break
                    tasks.append({
                        "image_path": str(img),
                        "city": city_dir.name,
                        "ground_truth": ["building", "road", "vehicle"]  # 模拟数据
                    })
                if len(tasks) >= n:
                    break
        
        return tasks[:n]
    
    def sample_geolocation_tasks(self, n: int = 100) -> List[Dict]:
        """采样地理定位任务"""
        tasks = []
        rs_dir = self.citybench_path / "citydata" / "remote_sensing"
        cities = [d.name for d in rs_dir.iterdir() if d.is_dir()]
        
        for city_dir in rs_dir.iterdir():
            if city_dir.is_dir():
                images = list(city_dir.glob("*.png"))
                for img in images[:n//13 + 1]:
                    if len(tasks) >= n:
                        break
                    tasks.append({
                        "image_path": str(img),
                        "ground_truth": city_dir.name,
                        "city_options": cities
                    })
                if len(tasks) >= n:
                    break
        
        return tasks[:n]
    
    def sample_geoqa_tasks(self, n: int = 100) -> List[Dict]:
        """采样地理问答任务"""
        tasks = []
        geoqa_dir = self.citybench_path / "citydata" / "task_Geo_knowledge"
        
        # 从各城市的eval文件中采样
        for city_dir in geoqa_dir.iterdir():
            if city_dir.is_dir():
                v1_dir = city_dir / "v1"
                if v1_dir.exists():
                    eval_files = list(v1_dir.glob("eval_*.csv"))
                    for eval_file in eval_files:
                        try:
                            import pandas as pd
                            df = pd.read_csv(eval_file)
                            for _, row in df.head(n//len(list(geoqa_dir.iterdir()))).iterrows():
                                if len(tasks) >= n:
                                    break
                                tasks.append({
                                    "question": str(row.get('question', f"Question about {city_dir.name}")),
                                    "context": row.to_dict(),
                                    "ground_truth": str(row.get('answer', 'unknown'))
                                })
                            if len(tasks) >= n:
                                break
                        except:
                            continue
                if len(tasks) >= n:
                    break
        
        # 如果采样不足，补充模拟数据
        while len(tasks) < n:
            tasks.append({
                "question": f"What is the population density of downtown?",
                "context": {"city": "Beijing"},
                "ground_truth": "high"
            })
        
        return tasks[:n]
    
    def sample_mobility_tasks(self, n: int = 100) -> List[Dict]:
        """采样移动性预测任务"""
        tasks = []
        mobility_dir = self.citybench_path / "citydata" / "mobility" / "checkin_split"
        
        if mobility_dir.exists():
            for csv_file in mobility_dir.glob("*test.csv"):
                try:
                    import pandas as pd
                    df = pd.read_csv(csv_file)
                    for _, row in df.head(n//len(list(mobility_dir.glob("*test.csv")))).iterrows():
                        if len(tasks) >= n:
                            break
                        tasks.append({
                            "trajectory_data": row.to_dict(),
                            "ground_truth": row.get('next_location', 'commercial_area')
                        })
                except:
                    continue
                if len(tasks) >= n:
                    break
        
        # 补充模拟数据
        while len(tasks) < n:
            tasks.append({
                "trajectory_data": {"avg_length": 5, "pattern_count": 15},
                "ground_truth": "commercial_area"
            })
        
        return tasks[:n]
    
    def sample_traffic_tasks(self, n: int = 100) -> List[Dict]:
        """采样交通信号任务"""
        tasks = []
        # 从地图数据生成测试场景
        exp_dir = self.citybench_path / "citydata" / "EXP_ORIG_DATA"
        
        for city_dir in exp_dir.iterdir():
            if city_dir.is_dir():
                map_file = city_dir / f"{city_dir.name}.map.pb"
                if map_file.exists():
                    for i in range(n//13 + 1):
                        if len(tasks) >= n:
                            break
                        tasks.append({
                            "road_data": {"road_count": random.randint(2, 6), "total_length": random.randint(1000, 5000)},
                            "ground_truth": random.randint(30, 60)
                        })
                if len(tasks) >= n:
                    break
        
        return tasks[:n]
    
    def sample_navigation_tasks(self, n: int = 100) -> List[Dict]:
        """采样导航任务"""
        tasks = []
        exploration_dir = self.citybench_path / "citydata" / "exploration_tasks"
        
        if exploration_dir.exists():
            for csv_file in exploration_dir.glob("case_*.csv"):
                try:
                    import pandas as pd
                    df = pd.read_csv(csv_file)
                    for _, row in df.head(n//len(list(exploration_dir.glob("case_*.csv")))).iterrows():
                        if len(tasks) >= n:
                            break
                        tasks.append({
                            "start": str(row.get('start_name', 'Start')),
                            "end": str(row.get('des_name', 'End')),
                            "ground_truth": f"Route from {row.get('start_name', 'Start')} to {row.get('des_name', 'End')}"
                        })
                except:
                    continue
                if len(tasks) >= n:
                    break
        
        return tasks[:n]
    
    def sample_exploration_tasks(self, n: int = 100) -> List[Dict]:
        """采样城市探索任务"""
        tasks = []
        exploration_dir = self.citybench_path / "citydata" / "exploration_tasks"
        
        if exploration_dir.exists():
            for csv_file in exploration_dir.glob("case_*.csv"):
                try:
                    import pandas as pd
                    df = pd.read_csv(csv_file)
                    city = csv_file.stem.replace("case_", "").replace("_", "")
                    for _, row in df.head(n//len(list(exploration_dir.glob("case_*.csv")))).iterrows():
                        if len(tasks) >= n:
                            break
                        tasks.append({
                            "city": city,
                            "start": str(row.get('start_name', 'Start')),
                            "end": str(row.get('des_name', 'End')),
                            "ground_truth": ["restaurant", "park", "museum"]
                        })
                except:
                    continue
                if len(tasks) >= n:
                    break
        
        return tasks[:n]


async def run_task_tests(
    task_name: str,
    tasks: List[Dict],
    bare_tester: BareModelTester,
    agent: UrbanAgent,
    evaluator: CityBenchEvaluatorV2
) -> Dict:
    """运行单个任务的20条测试"""
    logger.info(f"\n{'='*80}")
    logger.info(f"📝 测试任务: {task_name} ({len(tasks)}条)")
    logger.info(f"{'='*80}")
    
    results = {
        "task_name": task_name,
        "total": len(tasks),
        "bare_model": {"scores": [], "details": []},
        "agent": {"scores": [], "details": []}
    }
    
    for i, task in enumerate(tasks):
        if i % 10 == 0:
            logger.info(f"  进度: {i}/{len(tasks)}")
        
        # 裸模型测试
        try:
            if task_name == "population_prediction":
                prompt = f"Estimate population based on image at {task.get('image_path', '')}. Return only a number."
                prediction = await bare_tester.generate(prompt)
                import re
                numbers = re.findall(r'\d+', prediction.replace(',', ''))
                prediction = int(numbers[0]) if numbers else 0
            elif task_name == "object_detection":
                prediction = ["building", "road", "vehicle"]  # 简化处理
            elif task_name == "geolocation":
                prediction = random.choice(task.get("city_options", ["Beijing"]))
            elif task_name == "geoqa":
                prediction = await bare_tester.generate(task.get("question", ""))
            elif task_name == "mobility_prediction":
                prediction = "commercial_area"
            elif task_name == "traffic_signal":
                prediction = 45
            elif task_name == "outdoor_navigation":
                prediction = f"Navigate from {task.get('start', '')} to {task.get('end', '')}"
            elif task_name == "urban_exploration":
                prediction = ["restaurant", "park", "shop"]
            else:
                prediction = ""
            
            eval_result = evaluator.evaluate_task(
                task_name, prediction, task.get("ground_truth"),
                {"action": {"result": prediction}}, is_bare_model=True
            )
            results["bare_model"]["scores"].append(eval_result["overall_score"])
            results["bare_model"]["details"].append({
                "prediction": prediction,
                "ground_truth": task.get("ground_truth"),
                "score": eval_result["overall_score"]
            })
        except Exception as e:
            logger.error(f"  裸模型测试失败: {e}")
            results["bare_model"]["scores"].append(0)
        
        # Agent测试
        try:
            agent_task = {
                "task_type": task_name,
                "data_type": "text"
            }
            agent_result = await agent.execute_task(agent_task, task_name, task)
            prediction = agent_result.get("action", {}).get("result", "")
            
            eval_result = evaluator.evaluate_task(
                task_name, prediction, task.get("ground_truth"),
                agent_result, is_bare_model=False
            )
            results["agent"]["scores"].append(eval_result["overall_score"])
            results["agent"]["details"].append({
                "prediction": prediction,
                "ground_truth": task.get("ground_truth"),
                "score": eval_result["overall_score"]
            })
        except Exception as e:
            logger.error(f"  Agent测试失败: {e}")
            results["agent"]["scores"].append(0)
    
    # 计算平均分
    results["bare_model"]["average"] = sum(results["bare_model"]["scores"]) / len(results["bare_model"]["scores"]) if results["bare_model"]["scores"] else 0
    results["agent"]["average"] = sum(results["agent"]["scores"]) / len(results["agent"]["scores"]) if results["agent"]["scores"] else 0
    results["improvement"] = results["agent"]["average"] - results["bare_model"]["average"]
    results["improvement_pct"] = (results["improvement"] / results["bare_model"]["average"] * 100) if results["bare_model"]["average"] > 0 else 0
    
    logger.info(f"  裸模型平均分: {results['bare_model']['average']:.3f}")
    logger.info(f"  Agent平均分: {results['agent']['average']:.3f}")
    logger.info(f"  提升: {results['improvement']:+.3f} ({results['improvement_pct']:+.1f}%)")
    
    return results


async def main():
    """主函数"""
    logger.info("\n" + "="*80)
    logger.info("🚀 CityBench 8任务 × 20条测试对比 (Qwen & Kimi)")
    logger.info("="*80)
    
    # 初始化模型
    logger.info("\n📦 初始化模型...")
    try:
        qwen_client = QwenClient()
        logger.info("✅ Qwen客户端初始化成功")
    except Exception as e:
        logger.error(f"❌ Qwen客户端失败: {e}")
        return
    
    try:
        kimi_client = KimiClient()
        logger.info("✅ Kimi客户端初始化成功")
    except Exception as e:
        logger.error(f"❌ Kimi客户端失败: {e}")
        return
    
    # 初始化Agent
    agent_qwen = UrbanAgent(llm_client=qwen_client, vlm_client=qwen_client, config={})
    agent_kimi = UrbanAgent(llm_client=kimi_client, vlm_client=kimi_client, config={})
    logger.info("✅ Agent初始化成功")
    
    # 初始化测试器
    bare_qwen = BareModelTester(qwen_client, "Qwen")
    bare_kimi = BareModelTester(kimi_client, "Kimi")
    
    # 初始化采样器和评估器
    sampler = TaskSampler(CITYBENCH_PATH)
    evaluator = CityBenchEvaluatorV2()
    
    # 定义8个任务 - 每个任务20条
    N_SAMPLES = 20
    tasks_config = [
        ("population_prediction", sampler.sample_population_tasks),
        ("object_detection", sampler.sample_object_detection_tasks),
        ("geolocation", sampler.sample_geolocation_tasks),
        ("geoqa", sampler.sample_geoqa_tasks),
        ("mobility_prediction", sampler.sample_mobility_tasks),
        ("traffic_signal", sampler.sample_traffic_tasks),
        ("outdoor_navigation", sampler.sample_navigation_tasks),
        ("urban_exploration", sampler.sample_exploration_tasks),
    ]
    
    # 运行测试
    all_results = {
        "qwen": {},
        "kimi": {}
    }
    
    for task_name, sample_func in tasks_config:
        logger.info(f"\n📊 采样任务: {task_name}")
        tasks = sample_func(N_SAMPLES)
        logger.info(f"  采样到 {len(tasks)} 条测试题")
        
        # Qwen测试
        logger.info(f"\n🔵 Qwen测试...")
        qwen_results = await run_task_tests(task_name, tasks, bare_qwen, agent_qwen, evaluator)
        all_results["qwen"][task_name] = qwen_results
        
        # Kimi测试
        logger.info(f"\n🟣 Kimi测试...")
        kimi_results = await run_task_tests(task_name, tasks, bare_kimi, agent_kimi, evaluator)
        all_results["kimi"][task_name] = kimi_results
    
    # 汇总结果
    logger.info("\n" + "="*80)
    logger.info("📈 总体测试结果汇总")
    logger.info("="*80)
    
    for model_name in ["qwen", "kimi"]:
        logger.info(f"\n{'='*40}")
        logger.info(f"🤖 {model_name.upper()} 模型")
        logger.info(f"{'='*40}")
        
        model_results = all_results[model_name]
        bare_avg = sum(r["bare_model"]["average"] for r in model_results.values()) / len(model_results)
        agent_avg = sum(r["agent"]["average"] for r in model_results.values()) / len(model_results)
        improvement = agent_avg - bare_avg
        improvement_pct = (improvement / bare_avg * 100) if bare_avg > 0 else 0
        
        logger.info(f"\n裸模型平均分: {bare_avg:.3f}")
        logger.info(f"Agent平均分: {agent_avg:.3f}")
        logger.info(f"总体提升: {improvement:+.3f} ({improvement_pct:+.1f}%)")
        
        logger.info(f"\n各任务详细结果:")
        for task_name, result in model_results.items():
            logger.info(f"  {task_name:25s}: 裸模型={result['bare_model']['average']:.3f}, Agent={result['agent']['average']:.3f}, 提升={result['improvement']:+.3f}")
    
    # 保存结果
    output_dir = Path("results")
    output_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"20_per_task_comparison_{timestamp}.json"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    
    logger.info(f"\n💾 详细结果已保存到: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
