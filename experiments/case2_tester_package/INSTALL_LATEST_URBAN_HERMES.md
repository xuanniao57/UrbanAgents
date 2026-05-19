# Install Latest Urban-Hermes For Case 2

This checklist is for the collaborator-side agent. Follow it before running the Case 2 realistic dialogue test.

## 1. Clone Or Update Repository

If the repository does not exist locally:

```powershell
git clone https://github.com/xuanniao57/UrbanAgents.git D:/UrbanAgents_Case2
Set-Location D:/UrbanAgents_Case2
```

If it already exists:

```powershell
Set-Location D:/UrbanAgents_Case2
git fetch --all --prune
```

Checkout and update the target branch:

```powershell
git checkout feature/hermes-urban-research-memory-qgis
git pull --ff-only origin feature/hermes-urban-research-memory-qgis
```

Record the exact commit:

```powershell
git rev-parse --short HEAD
```

Write the commit id into `install_smoke_log.txt` in the return package.

## 2. Create Python Environment

```powershell
conda create -n urban-hermes-case2 python=3.11 -y
conda activate urban-hermes-case2
python --version
```

## 3. Install Urban-Hermes

```powershell
Set-Location D:/UrbanAgents_Case2/paper4_urban_svgagent
python -m pip install --upgrade pip
pip install -e .
$env:PYTHONPATH = "$PWD\hermes_urban_agent;$PWD"
```

If `pip install -e .` fails, save the full error output and stop. Do not edit source files unless the project owner explicitly asks you to patch the runtime.

## 4. Prepare Case 2 Run Package

Recommended package path:

```text
D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_run
```

If the package is distributed separately, copy the whole `case2_tester_package` folder to that path and preserve its internal directory structure.

## 5. Configure Kimi Code API

In the Case 2 package root:

```powershell
Set-Location D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_run
Copy-Item .\env\kimi_code.env.example .\env\kimi_code.env -Force
notepad .\env\kimi_code.env
. .\scripts\load_kimi_code_env.ps1 -EnvFile .\env\kimi_code.env
```

Security rule: never send back `kimi_code.env`, screenshots containing keys, or terminal logs that print secrets.

## 6. Configure Hermes Home

```powershell
$env:HERMES_HOME = "D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_run/hermes_home"
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

Do not set `KIMI_BASE_URL` to Moonshot CN chat-completions. The Kimi Code route is handled by the `kimi-coding` provider.

## 7. Runtime Preflight

From `D:/UrbanAgents_Case2/paper4_urban_svgagent`:

```powershell
conda activate urban-hermes-case2
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONPATH = "$PWD\hermes_urban_agent;$PWD"
$env:HERMES_HOME = "D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_run/hermes_home"
. D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_run/scripts/load_kimi_code_env.ps1 -EnvFile D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_run/env/kimi_code.env
python -m urban_hermes.launcher --list-tools --plain
```

Expected: tool list includes at least these tools:

```text
urban_host_fs
urban_host_python
urban_ground_task
urban_research_memory
urban_record_feedback
urban_review
urban_qgis_workspace
urban_qgis_process
```

If the exact total tool count differs across versions, do not fail only because of the count. Fail only if core urban tools are missing.

## 8. Provider Smoke Test

```powershell
python -m urban_hermes.launcher "say OK only" --provider kimi-coding --model kimi-for-coding --max-turns 1 --yolo --plain `
  2>&1 | Out-File -FilePath "D:/UrbanAgents_Case2_Output/install_smoke_log.txt" -Encoding utf8
```

Expected: a short normal response, ideally `OK`, and no `401`, no provider route error, no context-length failure.

## 9. QGIS Preflight

If QGIS is installed at the default path:

```powershell
Test-Path "C:/Program Files/QGIS 3.40.11/bin/python-qgis-ltr.bat"
```

If this returns `False`, record the actual QGIS path or note that QGIS validation cannot be run on this machine.

Do not import `qgis` from normal conda Python. Use the QGIS Python launcher for QGIS validation.

## 10. Installation Result To Report

Fill these fields in the return manifest:

```text
UrbanAgents repo path:
Branch:
Commit:
Python env:
Urban-Hermes launcher works: yes/no
Core urban tools present: yes/no
Kimi Code smoke test: pass/fail
QGIS Python available: yes/no/path
Notes:
```
