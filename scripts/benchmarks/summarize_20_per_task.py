"""
汇总20_per_task测试结果
"""

import json
from pathlib import Path

# 读取结果文件
result_path = Path("d:\\GitHub_1\\world_agent\\urban-mobility-agent\\paper4_urban_svgagent\\results\\20_per_task_comparison_20260227_135912.json")

with open(result_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

print("=" * 80)
print("CityBench 8任务 × 20条测试对比结果汇总")
print("=" * 80)

for model_name in ["qwen", "kimi"]:
    print(f"\n{'='*60}")
    print(f"🤖 {model_name.upper()} 模型")
    print(f"{'='*60}")
    
    model_data = data[model_name]
    
    # 计算总体平均分
    bare_scores = []
    agent_scores = []
    
    print("\n各任务详细结果:")
    print("-" * 60)
    print(f"{'任务名称':<25} {'裸模型':<10} {'Agent':<10} {'提升':<10}")
    print("-" * 60)
    
    for task_name, task_data in model_data.items():
        bare_avg = task_data["bare_model"]["average"]
        agent_avg = task_data["agent"]["average"]
        improvement = agent_avg - bare_avg
        improvement_pct = (improvement / bare_avg * 100) if bare_avg > 0 else 0
        
        bare_scores.append(bare_avg)
        agent_scores.append(agent_avg)
        
        print(f"{task_name:<25} {bare_avg:<10.3f} {agent_avg:<10.3f} {improvement:+7.3f} ({improvement_pct:+5.1f}%)")
    
    print("-" * 60)
    
    # 总体统计
    overall_bare = sum(bare_scores) / len(bare_scores)
    overall_agent = sum(agent_scores) / len(agent_scores)
    overall_improvement = overall_agent - overall_bare
    overall_improvement_pct = (overall_improvement / overall_bare * 100) if overall_bare > 0 else 0
    
    print(f"\n📊 总体统计:")
    print(f"  裸模型平均分: {overall_bare:.3f}")
    print(f"  Agent平均分:  {overall_agent:.3f}")
    print(f"  总体提升:     {overall_improvement:+.3f} ({overall_improvement_pct:+.1f}%)")

# 跨模型对比
print("\n" + "=" * 80)
print("📈 跨模型对比")
print("=" * 80)

print("\n各任务最佳模型:")
print("-" * 60)
print(f"{'任务名称':<25} {'最佳模型':<15} {'得分':<10}")
print("-" * 60)

for task_name in data["qwen"].keys():
    qwen_agent = data["qwen"][task_name]["agent"]["average"]
    kimi_agent = data["kimi"][task_name]["agent"]["average"]
    
    if qwen_agent > kimi_agent:
        best_model = "Qwen-Agent"
        best_score = qwen_agent
    else:
        best_model = "Kimi-Agent"
        best_score = kimi_agent
    
    print(f"{task_name:<25} {best_model:<15} {best_score:<10.3f}")

print("\n" + "=" * 80)
