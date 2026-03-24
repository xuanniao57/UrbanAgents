# Open Benchmark Sources for Workflow Tasks

更新时间：2026-03-19

本文件记录已经检查过的参考 benchmark 论文资产，以及哪些内容已经成功落地到本地。

## 已落地资产

### 1. CityBench

状态：已在本仓库落地。

本地路径：

- third_party/CityBench-main

可复用内容：

1. CityData 数据资产
2. 8 类任务定义
3. quick benchmark 已经接入 UrbanWorkflowBench

### 2. GeoAnalystBench

状态：已成功下载开源仓库。

本地路径：

- third_party/GeoAnalystBench

许可证：Apache 2.0

已确认可复用内容：

1. 50 个 geoprocessing workflow task 定义
2. 自然语言 instruction
3. human-designed workflow
4. 参考代码字符串

说明：

1. 题目定义和 workflow 描述已在仓库中。
2. 原始数据文件主要通过 README 中的 Google Drive 链接提供，不全部直接随 repo 分发。

### 3. GeoBenchX

状态：已成功下载开源仓库。

本地路径：

- third_party/GeoBenchX

许可证：MIT

已确认可复用内容：

1. 202+ geospatial multi-step tasks
2. reference tool-calling steps
3. evaluator tuning set
4. 数据下载说明和数据目录规范

说明：

1. benchmark 题目与参考解已直接在 repo 中。
2. 原始数据包通过 README 中的 Google Drive 链接提供。

## 未确认开源资产

### 4. USTBench

状态：未找到稳定公开的 GitHub 仓库或可直接下载的数据入口。

当前处理方式：

1. 保留论文层面的 benchmark 设计参考
2. 不伪造下载链接
3. 暂不自动导入 task bank

## 当前输出

基于已落地的开源 benchmark，已构建：

1. 原始来源说明
2. UrbanWorkflowBench 可直接使用的 open workflow task bank

对应文件：

- benchmarks/urbanworkflowbench/v1_1/open_workflow_task_bank.json
- scripts/benchmarks/build_open_workflow_task_bank.py