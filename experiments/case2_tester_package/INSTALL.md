# Install Urban-Hermes For Case 2

## 0. 当前推荐路线

如果 GitHub clone 失败，不要继续耗在 clone 上。直接使用发送给你的离线压缩包或本地目录。

推荐目标目录：

```text
D:/UrbanAgents_Case2/paper4_urban_svgagent
```

离线包应该包含：

```text
paper4_urban_svgagent/
  hermes_urban_agent/                         # Urban-Hermes adapter
    urban_hermes/_vendor/hermes_runtime/      # Hermes 本体/runtime
  plugins/gis_backends/                       # QGIS / ArcGIS Pro 后端协议包
  experiments/case2_tester_package/           # 本测试包
```

## 1. Get Project Files

### Option A: Use Offline Zip

```powershell
New-Item -ItemType Directory -Force -Path D:/UrbanAgents_Case2 | Out-Null
Expand-Archive -Path D:/Downloads/UrbanAgents_Case2_Offline.zip -DestinationPath D:/UrbanAgents_Case2 -Force
Set-Location D:/UrbanAgents_Case2/paper4_urban_svgagent
```

如果解压后多了一层目录，例如：

```text
D:/UrbanAgents_Case2/UrbanAgents_Case2_Offline_20260519/paper4_urban_svgagent
```

就进入实际存在的 `paper4_urban_svgagent` 目录即可。

### Option B: Use Existing Local Directory

```powershell
Set-Location D:/path/to/your/paper4_urban_svgagent
```

### Option C: Clone From GitHub Or Mirror

只有网络可用时再使用：

```powershell
git clone https://github.com/xuanniao57/UrbanAgents.git D:/UrbanAgents_Case2
Set-Location D:/UrbanAgents_Case2
git checkout feature/hermes-urban-research-memory-qgis
git pull --ff-only origin feature/hermes-urban-research-memory-qgis
git rev-parse --short HEAD
```

## 2. Create Python Environment

```powershell
conda create -n urban-hermes-case2 python=3.11 -y
conda activate urban-hermes-case2
```

## 3. Install Urban-Hermes

```powershell
Set-Location D:/UrbanAgents_Case2/paper4_urban_svgagent
pip install -e .
$env:PYTHONPATH = "$PWD\hermes_urban_agent;$PWD"
```

`pip install -e .` 安装的是 `urban_agent` 主包；`urban_hermes` 和 vendored Hermes runtime 通过 `PYTHONPATH` 暴露。不要删除：

```text
hermes_urban_agent/urban_hermes/_vendor/hermes_runtime
```

## 4. Configure Kimi Code API

```powershell
Set-Location D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_tester_package
Copy-Item .\env\kimi_code.env.example .\env\kimi_code.env -Force
notepad .\env\kimi_code.env
```

在 `kimi_code.env` 中填入：

```text
KIMI_CODE_API_KEY=你的_Kimi_Code_key
KIMI_API_KEY=你的_Kimi_Code_key
KIMI_CODING_API_KEY=你的_Kimi_Code_key
KIMI_BASE_URL=
```

加载并验证：

```powershell
. .\scripts\load_kimi_code_env.ps1 -EnvFile .\env\kimi_code.env
```

## 5. Configure Hermes Home

```powershell
$env:HERMES_HOME = "D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_tester_package/hermes_home"
New-Item -ItemType Directory -Force -Path $env:HERMES_HOME | Out-Null
@"
model:
  default: kimi-for-coding
  provider: kimi-coding
toolsets:
- hermes-cli
agent:
  max_turns: 90
terminal:
  backend: local
"@ | Out-File -FilePath "$env:HERMES_HOME\config.yaml" -Encoding utf8
```

## 6. Preflight

```powershell
conda activate urban-hermes-case2
Set-Location D:/UrbanAgents_Case2/paper4_urban_svgagent
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONPATH = "$PWD\hermes_urban_agent;$PWD"
$env:HERMES_HOME = "D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_tester_package/hermes_home"
. D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_tester_package/scripts/load_kimi_code_env.ps1 -EnvFile D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_tester_package/env/kimi_code.env

# Kimi / Hermes 冒烟
python -m urban_hermes.launcher "say hello in one word" --provider kimi-coding --model kimi-for-coding --max-turns 1 --yolo

# 工具列表
python -m urban_hermes.launcher --list-tools --plain

# GIS 后端探测：QGIS 可选；ArcGIS Pro 可用时应看到 arcgis_pro.available=true
python experiments/case2_tester_package/scripts/gis_backend_preflight.py
```

应看到至少：

```text
urban_host_fs
urban_ground_task
urban_research_memory
urban_record_feedback
urban_review
urban_gis_workspace
```

如果 QGIS 未安装但 ArcGIS Pro 可用，这是可以接受的。继续实验时优先回传 ArcGIS Pro 的 FileGDB / validation JSON。详见 `ARCGIS_PRO_SUPPORT.md`。

## 7. Data Directory

实验数据目录必须存在，但数据格式不预设：

```powershell
New-Item -ItemType Directory -Force -Path D:/UrbanAgents_Case2_Data | Out-Null
New-Item -ItemType Directory -Force -Path D:/UrbanAgents_Case2_Output/realistic_dialogue | Out-Null
```

如果 `D:/UrbanAgents_Case2_Data` 为空，只能完成安装、Kimi 冒烟和 GIS backend preflight，不能完成真实 Case2 分析。请在回传清单里说明数据缺失。

## 安全规则

- `kimi_code.env`、`.env`、含 key 的截图/终端输出不能回传。
- 只能回传 `kimi_code.env.example` 和 `scripts/load_kimi_code_env.ps1`。