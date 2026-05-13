"""Runtime config.yaml support for UrbanAgent.

The public contract is intentionally small: .env stores secrets, while
config.yaml stores non-secret runtime defaults.
"""

from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import re
from typing import Any, Mapping, Optional

from .constants import get_cache_dir, get_config_path, get_env_path, get_runs_dir


DEFAULT_ENV_TEMPLATE = """# UrbanAgent API keys
# Non-secret settings live in config.yaml.

QWEN_API_KEY=
OPENAI_API_KEY=
DEEPSEEK_API_KEY=
Deepseek_API_KEY=
KIMI_API_KEY=
KIMI_CODE_API_KEY=
"""

DEFAULT_CONFIG: dict[str, Any] = {
    "model": {
        "provider": "qwen",
        "default": "qwen-plus",
        "planner": "qwen-plus",
        "exec": "qwen-plus",
        "providers": {
            "qwen": {
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "model": "qwen-plus",
            },
            "openai": {
                "base_url": "https://api.openai.com/v1",
                "model": "gpt-4o-mini",
            },
            "deepseek": {
                "base_url": "https://api.deepseek.com",
                "model": "deepseek-v4-pro",
                "planner_model": "deepseek-v4-pro",
                "exec_model": "deepseek-chat",
                "thinking": "enabled",
                "reasoning_effort": "high",
            },
            "kimi": {
                "base_url": "https://api.moonshot.cn/v1",
                "model": "moonshot-v1-auto",
                "client_type": "auto",
                "coding_base_url": "https://api.kimi.com/coding/v1",
                "coding_model": "kimi-for-coding",
            },
        },
    },
    "runs": {
        "dir": "",
        "keep_request": True,
        "keep_prompt_snapshot": True,
    },
    "logging": {
        "level": "ERROR",
        "dir": "logs",
    },
    "tools": {
        "progressive_surface": True,
        "enable_web": True,
        "enable_mcp": False,
    },
    "data": {
        "cache_dir": "cache",
        "osm_cache_dir": "cache/osm",
        "gis_cache_dir": "cache/gis",
    },
    "gateway": {
        "host": "127.0.0.1",
        "port": 8765,
        "reload": False,
    },
    "agent": {
        "interaction_mode": "supervisory",
        "freeze_policy_memory": True,
        "project_context": True,
        "subdirectory_hints": True,
    },
    "memory": {
        "persistent": True,
        "namespace": "runtime",
        "load_limit": 200,
        "short_term_size": 100,
    },
}


def _deep_merge(base: dict[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"", "''", '""'}:
        return ""
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value.lower() in {"null", "none", "~"}:
        return None
    if (value.startswith("'") and value.endswith("'")) or (value.startswith('"') and value.endswith('"')):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _load_simple_yaml(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if value.strip() == "":
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _parse_scalar(value)
    return root


def _load_yaml_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(text) or {}
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return _load_simple_yaml(text)


_SAFE_BARE = re.compile(r"^[A-Za-z0-9_./@:+-]+$")


def _format_scalar(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if text and _SAFE_BARE.match(text):
        return text
    return '"' + text.replace('"', '\\"') + '"'


def dump_simple_yaml(data: Mapping[str, Any], indent: int = 0) -> str:
    lines: list[str] = []
    pad = " " * indent
    for key, value in data.items():
        if isinstance(value, Mapping):
            lines.append(f"{pad}{key}:")
            lines.append(dump_simple_yaml(value, indent + 2).rstrip())
        else:
            lines.append(f"{pad}{key}: {_format_scalar(value)}")
    return "\n".join(lines) + "\n"


def read_urban_config(path: Optional[Path] = None) -> dict[str, Any]:
    config_path = path or get_config_path()
    loaded = _load_yaml_file(config_path)
    return _deep_merge(DEFAULT_CONFIG, loaded)


def write_default_config(path: Optional[Path] = None, force: bool = False) -> Path:
    config_path = path or get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if config_path.exists() and not force:
        return config_path
    config_path.write_text(dump_simple_yaml(DEFAULT_CONFIG), encoding="utf-8")
    return config_path


def write_default_env(path: Optional[Path] = None, force: bool = False) -> Path:
    env_path = path or get_env_path()
    env_path.parent.mkdir(parents=True, exist_ok=True)
    if env_path.exists() and not force:
        return env_path
    env_path.write_text(DEFAULT_ENV_TEMPLATE, encoding="utf-8")
    return env_path


def get_config_value(config: Mapping[str, Any], dotted_key: str) -> Any:
    current: Any = config
    for part in dotted_key.split("."):
        if not isinstance(current, Mapping) or part not in current:
            raise KeyError(dotted_key)
        current = current[part]
    return current


def set_config_value(config: dict[str, Any], dotted_key: str, value: Any) -> dict[str, Any]:
    current = config
    parts = dotted_key.split(".")
    for part in parts[:-1]:
        child = current.setdefault(part, {})
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[parts[-1]] = value
    return config


def parse_config_value(raw: str) -> Any:
    return _parse_scalar(raw)


def write_urban_config(config: Mapping[str, Any], path: Optional[Path] = None) -> Path:
    config_path = path or get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(dump_simple_yaml(config), encoding="utf-8")
    return config_path


def configured_runs_dir(config: Mapping[str, Any]) -> Path:
    runs = config.get("runs", {}) if isinstance(config, Mapping) else {}
    configured = runs.get("dir") if isinstance(runs, Mapping) else None
    return get_runs_dir(str(configured) if configured else None)


def apply_config_to_environment(config: Mapping[str, Any]) -> None:
    model = config.get("model", {}) if isinstance(config, Mapping) else {}
    if not isinstance(model, Mapping):
        return
    provider = str(model.get("provider") or "qwen").strip().lower() or "qwen"
    default_model = str(model.get("default") or "qwen-plus")
    providers = model.get("providers", {}) if isinstance(model.get("providers"), Mapping) else {}
    provider_config = providers.get(provider, {}) if isinstance(providers, Mapping) else {}
    if not isinstance(provider_config, Mapping):
        provider_config = {}

    os_environ_defaults = {
        "LLM_PROVIDER": provider,
        "LLM_MODEL": default_model,
        "QWEN_API_BASE": str(provider_config.get("base_url") or "https://dashscope.aliyuncs.com/compatible-mode/v1") if provider == "qwen" else None,
        "QWEN_MODEL": str(provider_config.get("model") or default_model) if provider == "qwen" else None,
        "OPENAI_BASE_URL": str(provider_config.get("base_url") or "https://api.openai.com/v1") if provider == "openai" else None,
        "OPENAI_MODEL": str(provider_config.get("model") or default_model) if provider == "openai" else None,
        "DEEPSEEK_BASE_URL": str(provider_config.get("base_url") or "https://api.deepseek.com") if provider == "deepseek" else None,
        "DEEPSEEK_MODEL": str(provider_config.get("model") or default_model) if provider == "deepseek" else None,
        "DEEPSEEK_PLANNER_MODEL": str(provider_config.get("planner_model") or provider_config.get("model") or default_model) if provider == "deepseek" else None,
        "DEEPSEEK_EXEC_MODEL": str(provider_config.get("exec_model") or "deepseek-chat") if provider == "deepseek" else None,
        "DEEPSEEK_PLANNER_THINKING": str(provider_config.get("thinking") or "enabled") if provider == "deepseek" else None,
        "DEEPSEEK_PLANNER_REASONING_EFFORT": str(provider_config.get("reasoning_effort") or "high") if provider == "deepseek" else None,
        "KIMI_BASE_URL": str(provider_config.get("base_url") or "https://api.moonshot.cn/v1") if provider == "kimi" else None,
        "KIMI_MODEL": str(provider_config.get("model") or default_model) if provider == "kimi" else None,
        "KIMI_CLIENT_TYPE": str(provider_config.get("client_type") or "auto") if provider == "kimi" else None,
        "KIMI_CODE_API_BASE": str(provider_config.get("coding_base_url") or "https://api.kimi.com/coding/v1") if provider == "kimi" else None,
        "KIMI_CODE_MODEL": str(provider_config.get("coding_model") or "kimi-for-coding") if provider == "kimi" else None,
    }
    for key, value in os_environ_defaults.items():
        if value is not None and not os.environ.get(key):
            os.environ[key] = value

    if not os.environ.get("URBAN_AGENT_RUNS_DIR"):
        runs_dir = configured_runs_dir(config)
        if runs_dir != get_runs_dir():
            os.environ["URBAN_AGENT_RUNS_DIR"] = str(runs_dir)
    if not os.environ.get("URBAN_AGENT_CACHE_DIR"):
        os.environ["URBAN_AGENT_CACHE_DIR"] = str(get_cache_dir())
