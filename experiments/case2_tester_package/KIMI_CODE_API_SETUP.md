# Kimi Code API 配置说明

本包默认使用实验中已跑通的 Kimi Code 路径：

```text
provider = kimi-coding
model    = kimi-for-coding
```

不要把它改成 `kimi-coding-cn`、`kimi-k2.6` 或 Moonshot CN chat-completions endpoint。Kimi Code provider 会由 Urban-Hermes runtime 自己处理路由；`KIMI_BASE_URL` 应保持为空或被清除。

## 1. 创建本地 env 文件

在 Case2 测试包根目录执行：

```powershell
Copy-Item .\env\kimi_code.env.example .\env\kimi_code.env -Force
notepad .\env\kimi_code.env
```

把下面三项都填成你自己的 Kimi Code API key：

```text
KIMI_CODE_API_KEY=你的_kimi_code_key
KIMI_API_KEY=你的_kimi_code_key
KIMI_CODING_API_KEY=你的_kimi_code_key
```

`KIMI_BASE_URL` 留空：

```text
KIMI_BASE_URL=
```

## 2. 加载 env

每次新开 PowerShell 后，先执行：

```powershell
. .\scripts\load_kimi_code_env.ps1 -EnvFile .\env\kimi_code.env
```

脚本会做三件事：

- 读取 `KIMI_CODE_API_KEY`
- 自动补齐 `KIMI_API_KEY` 和 `KIMI_CODING_API_KEY`
- 清除 `KIMI_BASE_URL`，避免误走 Moonshot CN chat-completions 路径

## 3. 冒烟测试

进入 Urban-Hermes runtime 根目录后执行：

```powershell
python -m urban_hermes.launcher "say hello in one word" --provider kimi-coding --model kimi-for-coding --max-turns 1 --yolo
```

能正常返回一个短回复，即 API key 和 provider 基本可用。若返回 `401`，优先检查 `env/kimi_code.env` 是否填错 key，并确认刚才的加载脚本已经执行。

## 4. 分享规则

可以分享：

- `env/kimi_code.env.example`
- `scripts/load_kimi_code_env.ps1`
- `KIMI_CODE_API_SETUP.md`

不要分享：

- `env/kimi_code.env`
- `.env`
- 任何包含真实 key 的截图、终端输出或压缩包
