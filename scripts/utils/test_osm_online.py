"""
Urban Agent OSM在线数据测试
直接使用OSM获取道路、建筑等完整数据
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from urban_agent.perception import OSMProcessor
from urban_agent.cognition import SpatialCognition
from urban_agent.decision import SpatialDecision
from urban_agent.visualization import SpatialVisualizer
from urban_agent.core import SpatialContext


def main():
    print("\n" + "="*70)
    print("Urban Agent - OSM Online Data Test")
    print("="*70 + "\n")
    
    # 测试位置
    test_locations = [
        "Tianzifang, Shanghai, China",
        "People's Square, Shanghai, China",
    ]
    
    for location in test_locations:
        print(f"\n{'='*70}")
        print(f"Testing: {location}")
        print(f"{'='*70}\n")
        
        try:
            # Step 1: 从OSM获取数据
            print("[Step 1] Fetching OSM data...")
            processor = OSMProcessor()
            raw_features = processor._process_from_osm(location, radius=500)
            
            print(f"\n  ✓ Roads: {raw_features['roads']['segment_count']} segments")
            print(f"    Total length: {raw_features['roads']['total_length_m']:.0f}m")
            print(f"  ✓ Buildings: {raw_features['buildings']['count']} buildings")
            print(f"    Density: {raw_features['buildings']['density']:.2f}")
            print(f"  ✓ POIs: {sum(len(v) for v in raw_features['pois'].values())} POIs")
            
            # Step 2: 空间认知
            print("\n[Step 2] Spatial cognition...")
            cognition = SpatialCognition()
            
            context = SpatialContext(
                location=location,
                bbox=raw_features['_bbox'],
                crs=raw_features['_crs'],
                raw_features=raw_features
            )
            
            understanding = cognition.understand(context, "analyze urban space")
            context.spatial_understanding = understanding
            
            topo_graph = understanding.get('topological_graph', {})
            print(f"  ✓ Topological nodes: {topo_graph.get('node_count', 0)}")
            print(f"  ✓ Topological relations: {topo_graph.get('relation_count', 0)}")
            
            # Step 3: 空间决策
            print("\n[Step 3] Spatial decision...")
            decision = SpatialDecision()
            decision_result = decision.decide(context, "improve connectivity")
            context.intervention_areas = decision_result.get('interventions', [])
            
            print(f"  ✓ Intervention areas: {len(context.intervention_areas)}")
            for i, area in enumerate(context.intervention_areas[:3], 1):
                print(f"    {i}. {area.get('type')}: {area.get('description', '')[:40]}...")
            
            # Step 4: 可视化
            print("\n[Step 4] Visualization...")
            visualizer = SpatialVisualizer()
            
            context.svg_overlay = visualizer.create_svg_overlay(
                raw_features,
                context.intervention_areas,
                context.bbox
            )
            context.geojson_features = visualizer.create_geojson_features(
                context.intervention_areas,
                context.crs
            )
            
            # 保存结果
            safe_name = location.replace(', ', '_').replace(' ', '_')
            
            if context.svg_overlay:
                svg_file = f"osm_test_{safe_name}.svg"
                with open(svg_file, 'w', encoding='utf-8') as f:
                    f.write(context.svg_overlay)
                print(f"  ✓ SVG saved: {svg_file}")
            
            if context.geojson_features:
                import json
                geojson_file = f"osm_test_{safe_name}.geojson"
                with open(geojson_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        'type': 'FeatureCollection',
                        'features': context.geojson_features
                    }, f, ensure_ascii=False, indent=2)
                print(f"  ✓ GeoJSON saved: {geojson_file}")
            
            print(f"\n✓ Analysis completed for {location}")
            
        except Exception as e:
            print(f"\n✗ Error: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*70)
    print("Test completed!")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
