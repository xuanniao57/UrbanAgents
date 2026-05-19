# ArcGIS Pro Support For Case 2

## `.aprx` 是什么

`.aprx` 是 ArcGIS Pro 的工程文件，类似 QGIS 的 `.qgz/.qgs` 工程文件。

它通常保存：

- 地图和 3D Scene 列表
- 图层顺序
- 图层符号化和样式
- 布局、图例、比例尺、导出设置
- 图层数据源路径引用

它通常 **不等于数据本身**。真正的数据通常放在：

- File Geodatabase：`.gdb`
- GeoJSON / Shapefile / CSV
- Raster / Tile / Service

所以一个可复查的 ArcGIS Pro 产物至少应该包含：

```text
arcgis_workspace/
  data/protocol_arcgis_workspace.gdb
  project/*.aprx                  # 有 template_aprx 时生成
  maps/*.png / *.pdf              # 有布局模板时生成
  manifests/spatial_reasoning_manifest.json
  manifests/arcgis_validation_report.json
```

## 当前支持级别

当前 Urban-Hermes 已支持 ArcGIS Pro 后端的 **数据级验收**：

1. 探测 ArcGIS Pro Python / ArcPy
2. 按统一 `spatial_reasoning_manifest.json` 读取输入图层
3. 把 GeoJSON 点、线、面导入 FileGDB
4. 保留指标字段，例如 `vitality_score`、`road_density_m_per_ha`、`accessibility_score`
5. 生成 `arcgis_validation_report.json`
6. 检查 FileGDB 是否存在、feature count、metric fields、spatial reference、manifest 路径一致性

如果没有 `template_aprx`，validator 会给出 warning：

```text
no .aprx project was validated; provide template_aprx for full ArcGIS Pro project validation
```

这不是安装失败。它的含义是：当前已经完成 ArcGIS Pro 数据级验收，但还没有完成 `.aprx` 工程/布局图的完整视觉验收。

## 推荐给合作者的策略

如果机器只有 ArcGIS Pro、没有 QGIS：

1. 不要强行安装 QGIS。
2. 先运行 ArcGIS Pro backend probe。
3. 跑实验时要求 Urban-Hermes 生成可检查的 GIS manifest、GeoJSON/CSV 和 ArcGIS workspace。
4. 回传 `arcgis_workspace/`、`arcgis_validation_report.json` 和 transcript。
5. 如果需要完整 `.aprx` 地图，请提供一个空白 ArcGIS Pro template project，后续用 `template_aprx` 路径补跑。

## 手动探测 ArcGIS Pro Backend

在 `paper4_urban_svgagent` 根目录下运行：

```powershell
python experiments/case2_tester_package/scripts/gis_backend_preflight.py
```

结果会写到：

```text
D:/UrbanAgents_Case2_Output/preflight/gis_backend_preflight.json
```

如果 `arcgis_pro.available=true`，说明 ArcPy 可用。