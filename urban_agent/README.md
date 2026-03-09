# Urban Agent: 城市空间认知-理解-决策智能体框架

## 概述

Urban Agent 是一个基于OSM数据的城市空间分析与决策支持系统，实现了**"先拓扑化再矢量对应"**的空间理解框架。

## 核心架构

### 三层架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Urban Agent Core                         │
│                      (核心控制器)                            │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│   Perception  │    │   Cognition   │    │   Decision    │
│    (感知层)    │───▶│    (认知层)    │───▶│    (决策层)    │
└───────────────┘    └───────────────┘    └───────────────┘
        │                     │                     │
        ▼                     ▼                     ▼
   OSM数据获取          拓扑图构建              干预方案生成
   特征提取            语义标注                效果测量
   坐标转换            矢量映射                方案选择
```

### 关键特性

1. **真实地理坐标对齐**
   - 所有几何数据使用真实地理坐标（UTM投影）
   - SVG可视化精确映射到地图底图
   - 支持GeoJSON标准格式输出

2. **拓扑-矢量双层表示**
   - **拓扑层**: 抽象的关系网络（节点、连接、层次）
   - **矢量层**: 具体的度量几何（坐标、距离、形状）
   - **双向映射**: 拓扑结构 ↔ 矢量几何

3. **空间测量工具集**
   - 连通性测量（Connectivity）
   - 可达性测量（Accessibility）
   - 密度分布测量（Density）
   - 步行友好性测量（Walkability）

4. **MCP协议集成**
   - 标准化的工具接口
   - 支持外部系统调用
   - 可扩展的工具注册机制

## 模块说明

### 1. Core (核心模块)

`core.py` - 智能体核心控制器

```python
from urban_agent import UrbanAgent

# 初始化智能体
agent = UrbanAgent()

# 执行空间分析
context = agent.analyze(
    location="田子坊, 上海",
    task="改善公共空间连通性",
    radius=500
)

# 交互式查询
response = agent.query(context, "这个区域的主要问题是什么？")
```

### 2. Perception (感知层)

`perception.py` - 空间数据获取与解析

功能：
- 从OSM获取道路、建筑、POI、土地利用数据
- 计算空间指标（密度、连通性、方向性）
- 提取空间模式（网格规则性、聚类程度）

关键类：
- `SpatialPerception`: 主感知类
- `SpatialContext`: 空间上下文数据类

### 3. Cognition (认知层)

`cognition.py` - 空间理解与拓扑构建

核心概念：
- `TopologicalNode`: 拓扑节点（交叉口、聚类、开放空间）
- `TopologicalRelation`: 拓扑关系（邻接、连接、包含）
- `TopologicalGraph`: 拓扑图表示

处理流程：
1. 特征提取 → 识别关键空间元素
2. 拓扑构建 → 建立抽象关系网络
3. 语义标注 → 赋予空间元素意义
4. 矢量映射 → 将拓扑映射到真实坐标

### 4. Decision (决策层)

`decision.py` - 空间决策与方案生成

功能：
- 识别空间设计机会
- 生成干预提案
- 测量基线条件
- 评估提案效果
- 选择最优方案

关键类：
- `SpatialDecision`: 决策主类
- `InterventionProposal`: 干预提案
- `SpatialMeasurement`: 空间测量工具集

测量指标：
- `measure_connectivity`: 连通性
- `measure_accessibility`: 可达性
- `measure_density_distribution`: 密度分布
- `measure_walkability`: 步行友好性
- `measure_visual_integration`: 视觉整合度

### 5. Visualization (可视化模块)

`visualization.py` - 可视化输出

功能：
- 生成与地图对齐的SVG叠加层
- 导出GeoJSON格式数据
- 生成测量报告

关键类：
- `SpatialVisualizer`: 可视化器
- `MeasurementReporter`: 报告生成器

### 6. MCP Tools (MCP工具集成)

`mcp_tools.py` - MCP协议工具集

提供的工具：
- `fetch_osm_data`: 获取OSM数据
- `analyze_connectivity`: 分析连通性
- `measure_accessibility`: 测量可达性
- `calculate_density`: 计算密度
- `generate_svg_overlay`: 生成SVG
- `export_geojson`: 导出GeoJSON
- `build_topology`: 构建拓扑
- `generate_measurement_report`: 生成报告

## 使用示例

### 基本使用

```python
from urban_agent import UrbanAgent

# 创建智能体
agent = UrbanAgent()

# 分析指定区域
context = agent.analyze(
    location="田子坊, 上海",
    task="改善公共空间连通性",
    radius=500  # 分析半径500米
)

# 访问分析结果
print(f"拓扑节点数: {context.spatial_understanding['topological_graph']['node_count']}")
print(f"干预区域数: {len(context.intervention_areas)}")

# 保存可视化结果
with open("output.svg", "w") as f:
    f.write(context.svg_overlay)
```

### 使用MCP工具

```python
from urban_agent.mcp_tools import get_mcp_tools

# 获取MCP工具实例
mcp = get_mcp_tools()

# 执行工具
result = mcp.execute_tool("fetch_osm_data", {
    "location": "田子坊, 上海",
    "radius": 500,
    "data_types": ["roads", "buildings"]
})

# 获取工具定义
tool_definitions = mcp.get_tool_definitions()
```

### 自定义测量

```python
from urban_agent.decision import SpatialMeasurement

measurement = SpatialMeasurement()

# 测量连通性
connectivity = measurement.measure_connectivity(
    graph_nodes=nodes,
    graph_relations=relations
)

# 测量可达性
accessibility = measurement.measure_accessibility(
    buildings_gdf=buildings,
    target_points=target_points,
    max_dist=500
)
```

## 输出格式

### SVG输出

SVG文件包含：
1. **底图层**: 建筑（灰色填充）、道路（深灰色线条）
2. **干预层**: 根据类型使用不同颜色
   - 绿色: 连通性改进
   - 蓝色: 开放空间
   - 橙色: 活动节点
3. **图例**: 说明干预类型

### GeoJSON输出

标准GeoJSON格式，包含：
- 几何信息（Point、LineString、Polygon）
- 属性信息（ID、类型、描述、目标节点）
- 坐标参考系（CRS）

## 与DEGIM的关系

Urban Agent 是对 DEGIM 的改进和扩展：

| 特性 | DEGIM | Urban Agent |
|------|-------|-------------|
| 坐标系统 | 相对坐标 (rel_x, rel_y) | 真实地理坐标 (UTM) |
| 数据基础 | 简化OSM数据 | 完整OSM数据 + POI + 土地利用 |
| 空间理解 | 文本描述 | 拓扑图 + 语义标注 |
| 决策支持 | 概念性建议 | 量化测量 + 具体方案 |
| 可视化 | 简单SVG | 对齐底图 + 图例 + GeoJSON |
| 工具集成 | 无 | MCP协议支持 |

## 依赖项

```
osmnx>=1.6.0
geopandas>=0.13.0
shapely>=2.0.0
numpy>=1.24.0
networkx>=3.0
scikit-learn>=1.3.0
```

## 安装

```bash
pip install osmnx geopandas shapely numpy networkx scikit-learn
```

## 测试

```bash
python test_urban_agent.py
```

## 未来扩展

1. **多模态数据融合**: 整合街景图像、遥感影像
2. **时序分析**: 支持历史数据对比和趋势分析
3. **模拟仿真**: 集成空间行为模拟
4. **协作决策**: 多智能体协商机制
5. **实时数据**: 接入实时交通、人流数据

## 贡献

欢迎提交Issue和Pull Request。

## 许可

MIT License
