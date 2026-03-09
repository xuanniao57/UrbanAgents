# CityBench Runbook（WSL2）

更新时间：2026-02-24

## 1. 适用范围

用于在 Linux 环境（WSL2）执行 CityBench 全量 8 子任务。

## 2. 前置条件

- 已安装并可进入 WSL2（Ubuntu）
- 仓库位于：`/mnt/d/GitHub_1/world_agent/urban-mobility-agent`
- `third_party/CityBench-main/citydata` 已存在
- 已准备 API 变量：`QWEN_API_KEY`、`QWEN_API_BASE`、`QWEN_MODEL`

## 3. 一条命令启动（推荐）

```bash
cd /mnt/d/GitHub_1/world_agent/urban-mobility-agent; sed -i 's/\r$//' ./paper4_urban_svgagent/run_citybench_wsl.sh; chmod +x ./paper4_urban_svgagent/run_citybench_wsl.sh; QWEN_API_KEY='你的key' QWEN_API_BASE='https://dashscope.aliyuncs.com/compatible-mode/v1' QWEN_MODEL='qwen3-vl' ./paper4_urban_svgagent/run_citybench_wsl.sh
```

## 4. 常见报错与处理

### 报错：`run_citybench_wsl.sh: command not found`

原因：没有带相对路径执行。

处理：
```bash
./paper4_urban_svgagent/run_citybench_wsl.sh
```

### 报错：`/bin/bash^M: bad interpreter`

原因：脚本是 CRLF 换行。

处理：
```bash
sed -i 's/\r$//' ./paper4_urban_svgagent/run_citybench_wsl.sh
```

### 报错：`conda: command not found`

原因：WSL 未安装或未初始化 conda。

处理：先安装 Miniconda，再执行：
```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda init bash
source ~/.bashrc
```

## 5. 输出与验收

- 汇总文件：`paper4_urban_svgagent/outputs/citybench_run_summary.json`
- 任务日志：`paper4_urban_svgagent/outputs/citybench_run_logs/*.log`
- 结果目录：`paper4_urban_svgagent/third_party/CityBench-main/results/`

验收标准：
1. 8 子任务均有运行记录
2. 摘要文件成功生成
3. 关键失败可定位到具体任务日志

## 6. 安全提醒

- 不要把 API key 写入仓库文件
- 若 key 已在聊天/截图暴露，立即轮换
