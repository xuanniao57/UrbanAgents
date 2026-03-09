"""
Urban Agent 本地数据测试脚本
使用CityBench的本地Shapefile数据测试
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from urban_agent import UrbanAgent


def main():
    print("\n" + "="*70)
    print("Urban Agent Framework Test (Local Data)")
    print("="*70 + "\n")
    
    # 初始化智能体
    agent = UrbanAgent()
    
    # 测试城市（使用本地数据）
    test_cities = [
        ("Shanghai", "分析城市空间结构"),
        ("Beijing", "识别高密度区域"),
        ("Paris", "评估步行友好性"),
    ]
    
    for city, task in test_cities:
        try:
            print(f"\n{'='*70}")
            print(f"Testing: {city}")
            print(f"{'='*70}")
            
            # 执行分析（使用本地数据，radius参数无效）
            context = agent.analyze(city, task, radius=500)
            
            # 输出结果
            print("\n【分析结果】")
            
            # 空间理解摘要
            understanding = context.spatial_understanding
            topo_graph = understanding.get('topological_graph', {})
            print(f"  拓扑节点数: {topo_graph.get('node_count', 0)}")
            print(f"  拓扑关系数: {topo_graph.get('relation_count', 0)}")
            
            # 原始数据摘要
            raw = context.raw_features
            buildings = raw.get('buildings', {})
            roads = raw.get('roads', {})
            print(f"  建筑数量: {buildings.get('count', 0)}")
            print(f"  建筑密度: {buildings.get('density', 0):.2f}")
            print(f"  道路段数: {roads.get('segment_count', 0)}")
            print(f"  道路总长: {roads.get('total_length_m', 0):.0f}m")
            
            # 决策结果
            print(f"\n  干预区域数: {len(context.intervention_areas)}")
            for i, area in enumerate(context.intervention_areas[:3], 1):
                print(f"    {i}. {area.get('type')}: {area.get('description', '')[:30]}...")
            
            # 保存结果
            if context.svg_overlay:
                output_file = f"output_{city}.svg"
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(context.svg_overlay)
                print(f"\n[OK] SVG saved: {output_file}")
            
            if context.geojson_features:
                import json
                geojson_file = f"output_{city}.geojson"
                with open(geojson_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        'type': 'FeatureCollection',
                        'features': context.geojson_features
                    }, f, ensure_ascii=False, indent=2)
                print(f"[OK] GeoJSON saved: {geojson_file}")
            
        except Exception as e:
            print(f"\n[ERR] Error analyzing {city}: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*70)
    print("Test completed!")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
