"""
统计CityBench各任务的测试题数量
"""

from pathlib import Path
import pandas as pd
import json

CITYBENCH_PATH = Path("d:\\GitHub_1\\world_agent\\urban-mobility-agent\\paper4_urban_svgagent\\third_party\\CityBench-main\\citydata")

def count_exploration_tasks():
    """统计城市探索任务"""
    exploration_dir = CITYBENCH_PATH / "exploration_tasks"
    if not exploration_dir.exists():
        return 0
    
    total = 0
    for csv_file in exploration_dir.glob("case_*.csv"):
        try:
            df = pd.read_csv(csv_file)
            total += len(df)
            print(f"  {csv_file.name}: {len(df)} 题")
        except:
            pass
    return total

def count_geoqa_tasks():
    """统计地理问答任务"""
    geoqa_dir = CITYBENCH_PATH / "task_Geo_knowledge"
    if not geoqa_dir.exists():
        return 0
    
    # 统计各城市的测试文件
    total = 0
    for city_dir in geoqa_dir.iterdir():
        if city_dir.is_dir():
            v1_dir = city_dir / "v1"
            if v1_dir.exists():
                # 统计eval_开头的文件行数
                for csv_file in v1_dir.glob("eval_*.csv"):
                    try:
                        df = pd.read_csv(csv_file)
                        count = len(df)
                        total += count
                        print(f"  {city_dir.name}/{csv_file.name}: {count} 题")
                    except:
                        pass
    return total

def count_remote_sensing_tasks():
    """统计遥感任务（人口预测、目标检测、地理定位）"""
    rs_dir = CITYBENCH_PATH / "remote_sensing"
    if not rs_dir.exists():
        return 0
    
    total_images = 0
    for city_dir in rs_dir.iterdir():
        if city_dir.is_dir():
            images = list(city_dir.glob("*.png"))
            print(f"  {city_dir.name}: {len(images)} 张图像")
            total_images += len(images)
    return total_images

def count_mobility_tasks():
    """统计移动性预测任务"""
    mobility_dir = CITYBENCH_PATH / "mobility"
    if not mobility_dir.exists():
        return 0
    
    # 检查checkin_split目录
    checkin_dir = mobility_dir / "checkin_split"
    if checkin_dir.exists():
        total = 0
        for csv_file in checkin_dir.glob("*.csv"):
            try:
                df = pd.read_csv(csv_file)
                total += len(df)
                print(f"  {csv_file.name}: {len(df)} 条记录")
            except:
                pass
        return total
    return 0

def count_traffic_tasks():
    """统计交通信号任务 - 需要查看原始数据"""
    # 交通信号任务通常在EXP_ORIG_DATA中的地图数据
    exp_dir = CITYBENCH_PATH / "EXP_ORIG_DATA"
    if not exp_dir.exists():
        return 0
    
    # 统计有地图数据的城市数量
    cities_with_map = 0
    for city_dir in exp_dir.iterdir():
        if city_dir.is_dir():
            map_file = city_dir / f"{city_dir.name}.map.pb"
            if map_file.exists():
                cities_with_map += 1
    
    print(f"  有地图数据的城市: {cities_with_map} 个")
    # 每个城市通常有多个路口场景
    return cities_with_map * 10  # 估算

def count_navigation_tasks():
    """统计导航任务"""
    # 导航任务通常与exploration任务共享起点-终点对
    exploration_dir = CITYBENCH_PATH / "exploration_tasks"
    if not exploration_dir.exists():
        return 0
    
    total = 0
    for csv_file in exploration_dir.glob("case_*.csv"):
        try:
            df = pd.read_csv(csv_file)
            total += len(df)
        except:
            pass
    return total

def main():
    print("=" * 80)
    print("CityBench 8任务测试题数量统计")
    print("=" * 80)
    
    print("\n1. 城市探索 (Urban Exploration):")
    exploration_count = count_exploration_tasks()
    print(f"   总计: {exploration_count} 题")
    
    print("\n2. 地理问答 (GeoQA):")
    geoqa_count = count_geoqa_tasks()
    print(f"   总计: {geoqa_count} 题")
    
    print("\n3. 遥感任务 (Remote Sensing):")
    print("   包含: 人口预测、目标检测、地理定位")
    rs_count = count_remote_sensing_tasks()
    print(f"   总计: {rs_count} 张图像")
    
    print("\n4. 移动性预测 (Mobility Prediction):")
    mobility_count = count_mobility_tasks()
    print(f"   总计: {mobility_count} 条记录")
    
    print("\n5. 交通信号 (Traffic Signal):")
    traffic_count = count_traffic_tasks()
    print(f"   估算: {traffic_count} 个场景")
    
    print("\n6. 户外导航 (Outdoor Navigation):")
    nav_count = count_navigation_tasks()
    print(f"   总计: {nav_count} 条路径")
    
    print("\n" + "=" * 80)
    print("汇总:")
    print(f"  - 城市探索: {exploration_count} 题")
    print(f"  - 地理问答: {geoqa_count} 题")
    print(f"  - 遥感图像: {rs_count} 张")
    print(f"  - 移动性预测: {mobility_count} 条")
    print(f"  - 交通信号: ~{traffic_count} 场景")
    print(f"  - 户外导航: {nav_count} 条路径")
    print("=" * 80)

if __name__ == "__main__":
    main()
