"""
Urban Agent 测试脚本
验证城市空间认知-理解-决策框架
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from urban_agent import UrbanAgent
from urban_agent.visualization import MeasurementReporter


def main():
    print("\n" + "="*70)
    print("Urban Agent Framework Test")
    print("="*70 + "\n")
    
    # 初始化智能体
    agent = UrbanAgent()
    
    # 测试位置
    test_locations = [
        ("田子坊, 上海", "改善公共空间连通性"),
    ]
    
    for location, task in test_locations:
        try:
            # 执行分析
            context = agent.analyze(location, task, radius=500)
            
            # 输出结果
            print("\n" + "="*70)
            print("Analysis Results")
            print("="*70)
            
            # 空间理解摘要
            understanding = context.spatial_understanding
            print("\n【空间认知结果】")
            
            topo_graph = understanding.get('topological_graph', {})
            print(f"  拓扑节点数: {topo_graph.get('node_count', 0)}")
            print(f"  拓扑关系数: {topo_graph.get('relation_count', 0)}")
            
            patterns = understanding.get('spatial_patterns', {})
            fabric = patterns.get('urban_fabric', {})
            print(f"  建筑密度: {fabric.get('building_density', 0):.2f}")
            print(f"  网格规则性: {fabric.get('grid_regularity', 0):.2f}")
            
            findings = understanding.get('key_findings', [])
            print(f"\n  关键发现:")
            for finding in findings:
                print(f"    - {finding}")
            
            # 决策结果
            print("\n【空间决策结果】")
            print(f"  生成方案数: {len(context.design_proposals)}")
            print(f"  干预区域数: {len(context.intervention_areas)}")
            
            for i, area in enumerate(context.intervention_areas, 1):
                print(f"\n  干预区域 {i}:")
                print(f"    ID: {area.get('id')}")
                print(f"    类型: {area.get('type')}")
                print(f"    描述: {area.get('description')}")
                geom = area.get('geometry', {})
                print(f"    几何类型: {geom.get('type', 'Unknown')}")
            
            # 保存SVG
            if context.svg_overlay:
                output_file = f"urban_agent_output_{location.replace(', ', '_').replace(' ', '_')}.svg"
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(context.svg_overlay)
                print(f"\n✓ SVG saved to: {output_file}")
            
            # 保存GeoJSON
            if context.geojson_features:
                import json
                geojson_file = f"urban_agent_output_{location.replace(', ', '_').replace(' ', '_')}.geojson"
                with open(geojson_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        'type': 'FeatureCollection',
                        'features': context.geojson_features
                    }, f, ensure_ascii=False, indent=2)
                print(f"✓ GeoJSON saved to: {geojson_file}")
            
        except Exception as e:
            print(f"\n✗ Error analyzing {location}: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*70)
    print("Test completed!")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
