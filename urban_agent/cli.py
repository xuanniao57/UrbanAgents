"""UrbanAgent CLI.

默认面向真实城市分析任务，而不是只暴露内部 research pipeline。

Examples:
    python -m urban_agent
    python -m urban_agent analyze --task "分析同济大学周边步行可达性"
    python -m urban_agent analyze --task "基于输入 GeoJSON 诊断街道连通性" --input ./my_city_task.json
    python -m urban_agent doctor

Legacy pipeline commands are still available:
    python -m urban_agent perceive --data-type osm --bbox "121.4,31.2,121.5,31.3"
    python -m urban_agent cognize --input perception_result.json
    python -m urban_agent reason --input cognition_result.json --question "..."
    python -m urban_agent visualize --input analysis_result.json --format html
    python -m urban_agent review --input results.json
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import nullcontext
from dataclasses import dataclass
import importlib.util
import json
import logging
import os
import platform
import shutil
import shlex
import signal
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Sequence

try:
    from rich import box
    from rich.columns import Columns
    from rich.console import Console, Group
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.table import Table
    from rich.text import Text

    _RICH_AVAILABLE = True
except ImportError:
    box = Columns = Console = Group = Panel = Rule = Table = Text = None
    _RICH_AVAILABLE = False

try:
    from prompt_toolkit import prompt as _pt_prompt
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.completion import WordCompleter
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.styles import Style as PromptStyle

    _PROMPT_TOOLKIT_AVAILABLE = True
except ImportError:
    _pt_prompt = AutoSuggestFromHistory = FileHistory = PromptStyle = WordCompleter = None
    _PROMPT_TOOLKIT_AVAILABLE = False

from .config_store import (
    DEFAULT_ENV_TEMPLATE,
    apply_config_to_environment,
    configured_runs_dir,
    dump_simple_yaml,
    get_config_value,
    parse_config_value,
    read_urban_config,
    set_config_value,
    write_default_config,
    write_default_env,
    write_urban_config,
)
from .constants import (
    LEGACY_URBAN_HOME,
    PACKAGE_ROOT,
    display_urban_home,
    ensure_urban_home,
    get_config_path,
    get_env_path,
    get_install_root,
    get_logs_dir,
    get_sessions_dir,
    get_urban_home,
)

USER_CONFIG_DIR = get_urban_home()
USER_ENV_FILE = USER_CONFIG_DIR / ".env"
USER_CONFIG_FILE = get_config_path()
URBAN_CONFIG = read_urban_config(USER_CONFIG_FILE)


def _env_candidates() -> list[Path]:
    explicit_env = os.getenv("URBAN_AGENT_ENV")
    if explicit_env:
        return [Path(explicit_env).expanduser().resolve()]

    candidates: list[Path] = []
    override = os.getenv("URBAN_AGENT_HOME") or os.getenv("URBAN_AGENT_CONFIG_DIR")
    if override:
        candidates.append(Path(override).expanduser().resolve() / ".env")

    cwd = Path.cwd().resolve()
    for candidate in (cwd, *cwd.parents):
        candidates.append(candidate / ".env")
    candidates.append(USER_ENV_FILE)
    legacy_env = LEGACY_URBAN_HOME.expanduser().resolve() / ".env"
    if legacy_env != USER_ENV_FILE:
        candidates.append(legacy_env)
    return candidates


def _resolve_env_file() -> Optional[Path]:
    for candidate in _env_candidates():
        if candidate.exists():
            return candidate
    return None


def _resolve_project_root(env_file: Optional[Path] = None) -> Path:
    return PACKAGE_ROOT


def _default_runs_dir(runtime_root: Path) -> Path:
    if runtime_root == USER_CONFIG_DIR:
        return runtime_root / "runs"
    return runtime_root / "outputs" / "cli_runs"


ENV_FILE = _resolve_env_file()
PROJECT_ROOT = _resolve_project_root(ENV_FILE)
DEFAULT_RUNS_DIR = configured_runs_dir(URBAN_CONFIG)
DEFAULT_CASE_OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "case_studies"
ENV_TEMPLATE_FILE = PROJECT_ROOT / ".env.example"

SUPPORTED_INTERACTION_MODES = ("guided", "supervisory", "autonomous")
SUPPORTED_CASES = ("walkability", "mobility", "all")

PROVIDER_KEY_MAP = {
    "qwen": ["QWEN_API_KEY"],
    "openai": ["OPENAI_API_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY", "Deepseek_API_KEY"],
    "kimi": ["KIMI_CODE_API_KEY", "KIMI_API_KEY"],
}

_WORKFLOW_ROUTING_LABEL = "planner-driven"

if _RICH_AVAILABLE:
    _CONSOLE = Console(highlight=False, soft_wrap=True)
else:
    _CONSOLE = None

_AGENT_STYLES = {
    "planner": "bold blue",
    "manager": "bold white",
    "perception_worker": "bold magenta",
    "cognition_worker": "bold cyan",
    "perception": "bold magenta",
    "analyst": "bold cyan",
    "cartographer": "bold green",
    "reviewer": "bold yellow",
    "quality_controller": "bold red",
    "reporter": "bold yellow",
    "unknown": "bold white",
}


URBAN_AGENT_LOGO = """[#FFBF00]                 ▄▄▄   ▄▄▄· ▄▄▄▄▄ ▄▄▄▄▄ ▄▄▄▄▄ ▄▄▄▄▄ ▄▄▄▄▄ ▄▄▄▄▄ ▄▄▄▄▄ ▄▄▄▄▄ ▄▄▄▄▄ ▄▄▄▄▄ ▄▄▄▄▄ ▄▄▄▄▄ ▄▄▄▄▄ ▄▄▄▄▄[/]
[#FFBF00]                 ███▄ ███▐█ ▀█  ████▌ ████▌ ████▌ ████▌ ████▌ ████▌ ████▌ ████▌ ████▌ ████▌ ████▌ ████▌ ████▌[/]
[#FFD700]  █    █  █    █  ▐█.▪▐█·▄█▄▀▀▀█▄▐█    ▐█    ▐█    ▐█    ▐█    ▐█    ▐█    ▐█    ▐█    ▐█    ▐█    ▐█    [/]
[#FFD700]  █▄▄▄▄█  █▄▄▄▄█  ▐█▌·▐█▌▐█▐█▄▪▐█▐█    ▐█    ▐█    ▐█    ▐█    ▐█    ▐█    ▐█    ▐█    ▐█    ▐█    ▐█    [/]
[#FFBF00]  █▀▀▀▀▀  █     █ ▀▀▀ ▀▀▀▀▀ ▀▀▀▀  ▀▀▀▀  ▀▀▀▀  ▀▀▀▀  ▀▀▀▀  ▀▀▀▀  ▀▀▀▀  ▀▀▀▀  ▀▀▀▀  ▀▀▀▀  ▀▀▀▀  ▀▀▀▀ [/]
[#B8860B] ██▄▄██▌ ██▄▄██▌ ██▄▄ ██▄▄ ██▄▄▌ ██▄▄▌ ██▄▄▌ ██▄▄▌ ██▄▄▌ ██▄▄▌ ██▄▄▌ ██▄▄▌ ██▄▄▌ ██▄▄▌ ██▄▄▌ ██▄▄▌[/]
[#B8860B] ▀▀▀▀▀▀  ▀▀▀▀▀▀  ▀▀▀▀ ▀▀▀▀ ▀▀▀▀  ▀▀▀▀  ▀▀▀▀  ▀▀▀▀  ▀▀▀▀  ▀▀▀▀  ▀▀▀▀  ▀▀▀▀  ▀▀▀▀  ▀▀▀▀  ▀▀▀▀  ▀▀▀▀ [/]"""


@dataclass(frozen=True)
class ShellCommandDef:
    name: str
    description: str
    category: str
    aliases: tuple[str, ...] = ()
    args_hint: str = ""


SHELL_COMMAND_REGISTRY: list[ShellCommandDef] = [
    ShellCommandDef("new", "Start a fresh shell session", "Session", aliases=("reset",)),
    ShellCommandDef("clear", "Clear the terminal display", "Session"),
    ShellCommandDef("status", "Show shell, provider, and runtime status", "Session"),
    ShellCommandDef("runtime", "Show the last run's runtime ledger summary", "Session"),
    ShellCommandDef("plan", "Preview planner decomposition and worker assignment", "Urban Workflow", args_hint="<task>"),
    ShellCommandDef("capabilities", "List or search method-level capabilities", "Urban Workflow", aliases=("caps", "tools"), args_hint="[query]"),
    ShellCommandDef("doctor", "Run environment and provider checks", "Configuration"),
    ShellCommandDef("config", "Show active config locations and provider summary", "Configuration"),
    ShellCommandDef("mode", "Switch guided, supervisory, or autonomous mode", "Configuration", args_hint="<mode>"),
    ShellCommandDef("bbox", "Set or clear the default study-area bounding box", "Configuration", args_hint="<bbox|clear>"),
    ShellCommandDef("input", "Attach or clear a default task input JSON file", "Configuration", args_hint="<path|clear>"),
    ShellCommandDef("output", "Change the run artifact output directory", "Configuration", args_hint="<path>"),
    ShellCommandDef("commands", "Browse all slash commands grouped by category", "Info", aliases=("help",)),
    ShellCommandDef("quit", "Exit the shell", "Exit", aliases=("exit",)),
]


def _build_shell_command_lookup() -> dict[str, ShellCommandDef]:
    lookup: dict[str, ShellCommandDef] = {}
    for command in SHELL_COMMAND_REGISTRY:
        lookup[command.name] = command
        for alias in command.aliases:
            lookup[alias] = command
    return lookup


_SHELL_COMMAND_LOOKUP = _build_shell_command_lookup()


def _resolve_shell_command(name: str) -> Optional[ShellCommandDef]:
    return _SHELL_COMMAND_LOOKUP.get(name.lower().lstrip("/"))


def _shell_command_words() -> list[str]:
    words: list[str] = []
    for command in SHELL_COMMAND_REGISTRY:
        words.append(f"/{command.name}")
        words.extend(f"/{alias}" for alias in command.aliases)
    return sorted(words)


def _shell_commands_by_category() -> dict[str, list[ShellCommandDef]]:
    grouped: dict[str, list[ShellCommandDef]] = {}
    for command in SHELL_COMMAND_REGISTRY:
        grouped.setdefault(command.category, []).append(command)
    return grouped


def _looks_like_shell_command(text: str) -> bool:
    if not text.startswith("/"):
        return False
    first_word = text.split()[0]
    return "/" not in first_word[1:]


def _rich_ui_enabled() -> bool:
    """Rich UI is enabled as long as the library is importable.
    
    We prefer Rich formatting over plain-text fallback in all environments
    because modern terminals (VS Code, Windows Terminal, iTerm2) support
    ANSI escapes even when Python's isatty() heuristic disagrees.
    """
    return bool(_RICH_AVAILABLE and _CONSOLE is not None)


def _truncate_middle(value: str, max_length: int = 72) -> str:
    if len(value) <= max_length:
        return value
    keep = max(8, (max_length - 3) // 2)
    return f"{value[:keep]}...{value[-keep:]}"


def _output_dir_label(output_dir: str) -> str:
    path = Path(output_dir)
    return path.name or str(path)


def _agent_style(agent_name: str) -> str:
    return _AGENT_STYLES.get(agent_name, _AGENT_STYLES["unknown"])


def _agent_display_name(agent_name: str) -> str:
    return {
        "planner": "PlannerAgent",
        "manager": "ManagerAgent",
        "perception_worker": "PerceptionWorker",
        "cognition_worker": "CognitionWorker",
        "perception": "PerceptionWorker",
        "analyst": "AnalystWorker",
        "cartographer": "CartographerWorker",
        "reviewer": "ReviewHub",
        "quality_controller": "QualityController",
        "reporter": "ReporterWorker",
    }.get(agent_name, agent_name)


def _get_capabilities_summary() -> dict[str, list[str]]:
    """Return UrbanAgent capabilities grouped by family, for the welcome banner."""
    try:
        from .capabilities import get_default_capability_registry
        registry = get_default_capability_registry()
        grouped: dict[str, list[str]] = {}
        for item in registry.list_index():
            family = item.get("family", "general")
            grouped.setdefault(family, []).append(item["name"])
        return grouped
    except Exception:
        return {}

def _get_tools_summary() -> dict[str, list[str]]:
    """Return MCP tools grouped by category, for the welcome banner."""
    try:
        from plugins.mcp import UrbanMCPTools
        tools = UrbanMCPTools()
        grouped: dict[str, list[str]] = {}
        for tool_name in sorted(tools.tools.keys()):
            category = "urban analysis"
            if "acqui" in tool_name or "fetch" in tool_name:
                category = "data acquisition"
            elif "connect" in tool_name or "access" in tool_name or "topol" in tool_name:
                category = "network & topology"
            elif "density" in tool_name or "morph" in tool_name:
                category = "density & morphology"
            elif "svg" in tool_name or "geo" in tool_name or "export" in tool_name:
                category = "cartographic output"
            elif "signal" in tool_name or "mobility" in tool_name:
                category = "mobility & signals"
            grouped.setdefault(category, []).append(tool_name)
        return grouped
    except Exception:
        return {}
    return {
        "planner": "PlannerAgent",
        "manager": "ManagerAgent",
        "perception_worker": "PerceptionWorker",
        "cognition_worker": "CognitionWorker",
        "perception": "PerceptionWorker",
        "analyst": "AnalystWorker",
        "cartographer": "CartographerWorker",
        "reviewer": "ReviewHub",
        "quality_controller": "QualityController",
        "reporter": "ReporterWorker",
    }.get(agent_name, agent_name)


def _make_value_panel(title: str, value: str, *, style: str = "bold white") -> Any:
    if not _rich_ui_enabled():
        return None
    body = Text(justify="left")
    body.append(value, style=style)
    return Panel(body, title=title, border_style="bright_black", box=box.ASCII, padding=(0, 1), expand=True)


def _make_key_value_panel(title: str, rows: list[tuple[str, str]]) -> Any:
    if not _rich_ui_enabled():
        return None
    table = Table.grid(expand=True)
    table.add_column(style="dim", ratio=1, no_wrap=True)
    table.add_column(style="white", ratio=4)
    for key, value in rows:
        table.add_row(key, value)
    return Panel(table, title=title, border_style="bright_black", box=box.ASCII, padding=(0, 1))


def _make_caption_panel(text: str, *, title: Optional[str] = None) -> Any:
    if not _rich_ui_enabled():
        return None
    return Panel(text, title=title, border_style="bright_black", box=box.ASCII, padding=(0, 1))


def _print_renderable(renderable: Any) -> None:
    if _rich_ui_enabled():
        _CONSOLE.print(renderable)
    else:
        print(renderable)


class _OpenAICompatibleClient:
    def __init__(self):
        from openai import AsyncOpenAI

        self.api_key = os.getenv("OPENAI_API_KEY")
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        if not self.api_key:
            raise ValueError("OpenAI API key is not configured")

        self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

    async def generate(self, prompt: str, temperature: float = 0.7, max_tokens: int = 2000) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant specialized in urban analysis and spatial reasoning."},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content


def _selected_provider() -> str:
    model_config = URBAN_CONFIG.get("model", {}) if isinstance(URBAN_CONFIG, dict) else {}
    default_provider = model_config.get("provider", "qwen") if isinstance(model_config, dict) else "qwen"
    return os.getenv("LLM_PROVIDER", str(default_provider)).strip().lower() or "qwen"


def _build_kimi_client() -> Any:
    from .llm.kimi_client import KimiClient, KimiFallbackClient

    preference = os.getenv("KIMI_CLIENT_TYPE", "auto").strip().lower() or "auto"
    if preference in {"standard", "moonshot"}:
        return KimiClient(client_type="standard")
    if preference in {"coding", "code", "kimi-coding"}:
        try:
            return KimiClient(client_type="coding")
        except Exception:
            if os.getenv("KIMI_API_KEY"):
                return KimiClient(client_type="standard")
            raise
    if preference != "auto":
        raise ValueError("KIMI_CLIENT_TYPE must be auto, coding, or standard")

    if os.getenv("KIMI_CODE_API_KEY"):
        try:
            coding_client = KimiClient(client_type="coding")
            if os.getenv("KIMI_API_KEY"):
                return KimiFallbackClient(coding_client, KimiClient(client_type="standard"))
            return coding_client
        except Exception:
            if not os.getenv("KIMI_API_KEY"):
                raise
    return KimiClient(client_type="standard")


def _build_llm_client(role: str = "exec") -> Any:
    """Build an LLM client for a specific agent role.

    Roles:
      - "planner": deep-reasoning model (deepseek-v4-pro + thinking)
      - "exec":    fast model for workers/QC/review (deepseek-chat, no thinking)
    """
    provider_name = _selected_provider()
    if not any(os.getenv(key) for key in PROVIDER_KEY_MAP.get(provider_name, [])):
        raise RuntimeError(
            f"No API key detected for selected provider '{provider_name}'. "
            "Run 'urban-agent doctor' and configure .env before running real tasks."
        )

    try:
        if provider_name == "qwen":
            from .llm.qwen_client import QwenClient
            return QwenClient()
        if provider_name == "deepseek":
            from .llm.deepseek_client import DeepSeekClient
            if role == "planner":
                return DeepSeekClient(
                    model=os.getenv("DEEPSEEK_PLANNER_MODEL", os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")),
                    thinking=os.getenv("DEEPSEEK_PLANNER_THINKING", "enabled"),
                    reasoning_effort=os.getenv("DEEPSEEK_PLANNER_REASONING_EFFORT", "high"),
                )
            else:
                return DeepSeekClient(
                    model=os.getenv("DEEPSEEK_EXEC_MODEL", "deepseek-chat"),
                    thinking=os.getenv("DEEPSEEK_EXEC_THINKING", "disabled"),
                )
        if provider_name == "kimi":
            return _build_kimi_client()
        if provider_name == "openai":
            return _OpenAICompatibleClient()
    except Exception as error:
        raise RuntimeError(f"Failed to initialize provider '{provider_name}': {error}") from error

    raise RuntimeError(
        f"Unsupported provider '{provider_name}'. Supported providers: {', '.join(PROVIDER_KEY_MAP)}"
    )


def _build_planner_llm_client() -> Any:
    """Shortcut: deep-reasoning client for PlannerAgent."""
    return _build_llm_client(role="planner")


def _build_exec_llm_client() -> Any:
    """Shortcut: fast client for execution agents."""
    return _build_llm_client(role="exec")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="urban-agent",
        description="UrbanAgent CLI for real-world urban analysis tasks",
    )
    subparsers = parser.add_subparsers(dest="command")

    # --- task-oriented commands ---
    p_analyze = subparsers.add_parser("analyze", help="Run an urban analysis task")
    p_analyze.add_argument("--task", required=True, help="Natural-language task description")
    p_analyze.add_argument("--bbox", help="Bounding box: min_lon,min_lat,max_lon,max_lat")
    p_analyze.add_argument("--input", help="Task input JSON file")
    p_analyze.add_argument("--output-dir", default=str(DEFAULT_RUNS_DIR), help="Run artifact root directory")
    p_analyze.add_argument(
        "--interaction-mode",
        choices=SUPPORTED_INTERACTION_MODES,
        default="supervisory",
        help="Compatibility field. Use supervisory for collaborator-facing runs.",
    )
    p_analyze.add_argument("--name", help="Optional run name used in output directory naming")
    p_plan = subparsers.add_parser("plan", help="Preview UrbanAgent planner decomposition without executing the task")
    p_plan.add_argument("--task", required=True, help="Natural-language task description")
    p_plan.add_argument("--bbox", help="Bounding box: min_lon,min_lat,max_lon,max_lat")
    p_plan.add_argument("--input", help="Task input JSON file")
    p_plan.add_argument("--output", help="Optional JSON file for the planner output")

    p_doctor = subparsers.add_parser("doctor", help="Check environment, config, and provider status")
    p_doctor.add_argument("--json", action="store_true", help="Print JSON report")
    p_doctor.add_argument("--fix", action="store_true", help="Create missing runtime directories and default templates")

    p_init = subparsers.add_parser("init", help="Initialize user-level UrbanAgent config")
    p_init.add_argument("--from-env", help="Copy config from an existing .env file")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing user-level config")

    p_setup = subparsers.add_parser("setup", help="Run first-time configuration wizard")
    p_setup.add_argument("--non-interactive", action="store_true", help="Write defaults and apply explicit options without prompts")
    p_setup.add_argument("--provider", choices=sorted(PROVIDER_KEY_MAP), help="Default model provider")
    p_setup.add_argument("--model", help="Default model name")
    p_setup.add_argument("--runs-dir", help="Default run artifact directory")
    p_setup.add_argument("--api-key", help="API key for the selected provider")
    p_setup.add_argument("--force", action="store_true", help="Overwrite existing config.yaml and .env templates")

    p_config = subparsers.add_parser("config", help="Show config paths and provider status")
    p_config.add_argument("--json", action="store_true", help="Print JSON report")
    config_subparsers = p_config.add_subparsers(dest="config_command")
    p_config_get = config_subparsers.add_parser("get", help="Read a config.yaml value")
    p_config_get.add_argument("key", help="Dotted key, for example model.default")
    p_config_set = config_subparsers.add_parser("set", help="Set a config.yaml value")
    p_config_set.add_argument("key", help="Dotted key, for example model.default")
    p_config_set.add_argument("value", help="Scalar value")

    p_serve = subparsers.add_parser("serve", help="Start the UrbanAgent Web/API server")
    p_serve.add_argument("--host", default=None, help="Bind host")
    p_serve.add_argument("--port", type=int, default=None, help="Bind port")
    p_serve.add_argument("--reload", action="store_true", help="Enable uvicorn reload")

    p_service = subparsers.add_parser("service", help="Service lifecycle helper")
    p_service.add_argument("action", choices=["install", "start", "stop", "status"], help="Service action")

    p_update = subparsers.add_parser("update", help="Update a git-based UrbanAgent install")
    p_update.add_argument("--dir", default=None, help="Installation directory; defaults to detected git checkout or URBAN_AGENT_INSTALL_DIR")
    p_update.add_argument("--skip-install", action="store_true", help="Only pull code; skip pip install -e")
    p_update.add_argument("--dry-run", action="store_true", help="Print planned commands")

    p_uninstall = subparsers.add_parser("uninstall", help="Remove launch metadata or a managed install")
    p_uninstall.add_argument("--dir", default=None, help="Installation directory to remove")
    p_uninstall.add_argument("--full", action="store_true", help="Also remove URBAN_AGENT_HOME data")
    p_uninstall.add_argument("--yes", action="store_true", help="Confirm deletion")

    p_caps = subparsers.add_parser("capabilities", help="List or expand method-level capabilities")
    p_caps.add_argument("--query", help="Search by task, method, backend, or domain term")
    p_caps.add_argument("--level", type=int, choices=[0, 1, 2, 3], default=0, help="Disclosure level: 0 index, 1 card, 2 invocation, 3 full")
    p_caps.add_argument("--limit", type=int, default=8, help="Maximum capabilities to return")
    p_caps.add_argument("--json", action="store_true", help="Print JSON report")

    p_shell = subparsers.add_parser("shell", help="Start the interactive UrbanAgent shell")
    p_shell.add_argument("--bbox", help="Default bounding box")
    p_shell.add_argument("--input", help="Default input JSON file")
    p_shell.add_argument("--output-dir", default=str(DEFAULT_RUNS_DIR), help="Run artifact root directory")
    p_shell.add_argument("--interaction-mode", choices=SUPPORTED_INTERACTION_MODES, default="supervisory", help="Default shell mode")

    # --- multi-turn guided command (RDMA Figure 13 alignment) ---
    p_guided = subparsers.add_parser("guided", help="Run multi-turn guided analysis with human-in-the-loop (RDMA Figure 13 style)")
    p_guided.add_argument("--task", required=True, help="Natural-language task description")
    p_guided.add_argument("--input", help="Task input JSON file")
    p_guided.add_argument("--name", help="Run name for output directory")
    p_guided.add_argument("--output-dir", default=str(DEFAULT_RUNS_DIR), help="Run artifact root directory")

    # --- legacy pipeline commands ---
    p_perceive = subparsers.add_parser("perceive", help="Legacy: multi-source data perception")
    p_perceive.add_argument(
        "--data-type",
        required=True,
        choices=["osm", "remote_sensing", "street_view", "trajectory", "geojson", "text", "mixed"],
        help="Data type",
    )
    p_perceive.add_argument("--bbox", help="Bounding box: min_lon,min_lat,max_lon,max_lat")
    p_perceive.add_argument("--input", help="Input JSON file")
    p_perceive.add_argument("--output", help="Output JSON file", default="perception_result.json")

    p_cognize = subparsers.add_parser("cognize", help="Legacy: dual-space cognition")
    p_cognize.add_argument("--input", required=True, help="Perception result JSON file")
    p_cognize.add_argument("--task", default="", help="Task description")
    p_cognize.add_argument("--output", help="Output file", default="cognition_result.json")

    p_reason = subparsers.add_parser("reason", help="Legacy: spatial reasoning")
    p_reason.add_argument("--input", required=True, help="Cognition result JSON file")
    p_reason.add_argument("--question", default="", help="User question")
    p_reason.add_argument("--output", help="Output file", default="reasoning_result.json")

    p_viz = subparsers.add_parser("visualize", help="Legacy: create visual outputs")
    p_viz.add_argument("--input", required=True, help="Analysis result JSON file")
    p_viz.add_argument("--format", choices=["svg", "geojson", "both", "html", "all"], default="svg", help="Output format")
    p_viz.add_argument("--output", help="Output file prefix", default="visualization_output")

    p_correct = subparsers.add_parser("correct", help="Legacy: apply human correction modules")
    p_correct.add_argument("--input", required=True, help="Cognition result JSON file")
    p_correct.add_argument("--request", required=True, help="Correction request JSON file")
    p_correct.add_argument("--output", help="Corrected result output file", default="corrected_cognition.json")
    p_correct.add_argument("--html-output", help="Optional HTML review page output")

    p_review = subparsers.add_parser("review", help="Legacy: spatial quality review")
    p_review.add_argument("--input", required=True, help="Result JSON file")
    p_review.add_argument("--output", help="Review report output file", default="review_report.json")

    p_run = subparsers.add_parser("run", help="Legacy: run the end-to-end pipeline")
    p_run.add_argument("--question", required=True, help="Analysis question")
    p_run.add_argument("--bbox", help="Bounding box: min_lon,min_lat,max_lon,max_lat")
    p_run.add_argument("--input", help="Input data file")
    p_run.add_argument("--output-dir", help="Output directory", default=str(DEFAULT_RUNS_DIR))
    p_run.add_argument("--interaction-mode", choices=SUPPORTED_INTERACTION_MODES, default="supervisory", help="Compatibility field")

    return parser


def _build_case_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="urban-agent case",
        description="Source-only demo workflow command. Standard installed usage does not depend on it.",
    )
    parser.add_argument("--case", choices=SUPPORTED_CASES, default="all", help="Select source-only demo case")
    parser.add_argument("--output-dir", default=str(DEFAULT_CASE_OUTPUT_DIR), help="Case result directory")
    return parser


def _load_project_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None

    if load_dotenv and ENV_FILE and ENV_FILE.exists():
        load_dotenv(ENV_FILE, override=False)
    apply_config_to_environment(read_urban_config(USER_CONFIG_FILE))


def _configure_cli_logging() -> None:
    logging.getLogger("urban_agent").setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.ERROR)
    logging.getLogger("httpcore").setLevel(logging.ERROR)
    logging.getLogger("numexpr").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.ERROR)


def _write_default_user_config(source_env: Optional[str] = None, force: bool = False) -> Path:
    ensure_urban_home()
    USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if source_env:
        source = Path(source_env).expanduser().resolve()
        if not source.exists():
            raise FileNotFoundError(f"source .env not found: {source}")
        if force or not USER_ENV_FILE.exists():
            shutil.copyfile(source, USER_ENV_FILE)
    else:
        write_default_env(USER_ENV_FILE, force=force)
    write_default_config(USER_CONFIG_FILE, force=force)
    return USER_ENV_FILE


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _slugify(text: str, max_length: int = 48) -> str:
    cleaned = []
    for char in text.lower().strip():
        if char.isalnum():
            cleaned.append(char)
        elif char in {" ", "-", "_"}:
            cleaned.append("-")
    slug = "".join(cleaned).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return (slug or "run")[:max_length].rstrip("-")


def _parse_bbox(bbox: Optional[str]) -> Optional[dict[str, float]]:
    if not bbox:
        return None
    parts = [float(x) for x in bbox.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox must contain four comma-separated floats")
    return {
        "min_lon": parts[0],
        "min_lat": parts[1],
        "max_lon": parts[2],
        "max_lat": parts[3],
    }


def _read_json(path: str) -> Any:
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def _write_json(data: Any, path: Path | str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2, default=str)


def _write_text(text: str, path: Path | str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as file:
        file.write(text)


def _create_run_dir(output_root: Path, label: str) -> Path:
    run_dir = output_root / f"{_timestamp()}_{_slugify(label)}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _build_task_payload(task_text: str, bbox: Optional[str], input_path: Optional[str]) -> dict[str, Any]:
    task_payload: dict[str, Any] = {
        "question": task_text,
    }
    parsed_bbox = _parse_bbox(bbox)
    if parsed_bbox:
        task_payload["bbox"] = parsed_bbox
    if input_path:
        task_payload.update(_read_json(input_path))
    return task_payload


def _build_run_summary(run_dir: Path, result: dict[str, Any]) -> dict[str, Any]:
    efficiency = result.get("efficiency", {})
    final_answer = str(result.get("final_answer") or "").strip()
    exec_results = result.get("results", {})
    runtime = _summarize_runtime(exec_results.get("runtime", {}))
    return {
        "run_dir": str(run_dir),
        "status": result.get("status", "unknown"),
        "workflow_profile": result.get("plan", {}).get("workflow_profile", "adaptive_urban_analysis"),
        "trace_id": result.get("trace_id"),
        "agent_plan": _summarize_plan_with_status(result.get("plan", {}), exec_results),
        "total_latency_s": efficiency.get("total_latency_s"),
        "quality_control": result.get("quality_control", {}),
        "review": _summarize_review(result.get("review", {})),
        "runtime": runtime,
        "final_answer_preview": final_answer[:800],
    }


def _summarize_review(review: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(review, dict) or not review:
        return {}
    policy_scores = review.get("policy_scores", {})
    policies = []
    for name, payload in policy_scores.items():
        if not isinstance(payload, dict):
            continue
        policies.append({
            "name": name,
            "score": payload.get("score"),
            "applicable": payload.get("applicable", True),
            "issue_count": len(payload.get("issues", [])),
        })
    return {
        "passed": review.get("passed"),
        "recommendation": review.get("recommendation"),
        "quality_score": review.get("quality_score"),
        "urban_validity_score": review.get("urban_validity_score"),
        "warning_count": len(review.get("warnings", [])),
        "issue_count": len(review.get("issues", [])),
        "hard_failures": review.get("hard_failures", []),
        "policies": policies,
    }


def _summarize_runtime(runtime: dict[str, Any]) -> dict[str, Any]:
    if not runtime:
        return {}
    if "todo_total" in runtime and "checkpoint_count" in runtime:
        return dict(runtime)
    todos = runtime.get("todos", [])
    checkpoints = runtime.get("checkpoints", [])
    blocked = [checkpoint for checkpoint in checkpoints if checkpoint.get("approved") is False]
    return {
        "profile": runtime.get("runtime_profile", {}).get("name", "urban_runtime_kernel"),
        "mode": runtime.get("interaction_mode", "autonomous"),
        "todo_completed": sum(1 for todo in todos if todo.get("status") == "completed"),
        "todo_total": len(todos),
        "checkpoint_count": len(checkpoints),
        "blocked_count": len(blocked),
        "last_checkpoint": checkpoints[-1].get("checkpoint_id") if checkpoints else None,
    }


def _format_runtime_status(runtime: dict[str, Any]) -> str:
    if not runtime:
        return "no run yet"
    blocked = runtime.get("blocked_count", 0)
    status = f"{runtime.get('todo_completed', 0)}/{runtime.get('todo_total', 0)} todos, {runtime.get('checkpoint_count', 0)} checkpoints"
    if blocked:
        status += f", {blocked} blocked"
    return status


def _summarize_plan(plan: dict[str, Any]) -> list[dict[str, str]]:
    summary = []
    for index, subtask in enumerate(plan.get("subtasks", []), start=1):
        raw_agent = str(subtask.get("assigned_role", "unknown"))
        summary.append({
            "step": str(index),
            "agent": _agent_display_name(raw_agent),
            "raw_agent": raw_agent,
            "objective": str(subtask.get("objective", "")),
        })
    return summary


def _summarize_plan_with_status(plan: dict[str, Any], exec_results: dict[str, Any]) -> list[dict[str, str]]:
    """Merge plan subtasks with execution status from ManagerAgent results."""
    subtask_results = exec_results.get("subtask_results", {})
    summary = []
    for index, subtask in enumerate(plan.get("subtasks", []), start=1):
        st_id = str(subtask.get("subtask_id", f"plan_st{index}"))
        raw_agent = str(subtask.get("assigned_role", "unknown"))
        # Find matching execution result
        exec_status = subtask_results.get(st_id, {})
        status = exec_status.get("status", "planned")
        summary.append({
            "step": str(index),
            "agent": _agent_display_name(raw_agent),
            "raw_agent": raw_agent,
            "objective": str(subtask.get("objective", "")),
            "status": status,
        })
    return summary


def _build_observable_summary(run_dir: Path, manifest: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    reasoning_steps = [event.get("payload", {}) for event in events if event.get("type") == "reasoning_step"]
    agent_plan = []
    for index, todo in enumerate(manifest.get("todos", []), start=1):
        raw_agent = str(todo.get("agent", "unknown"))
        agent_plan.append({
            "step": str(index),
            "agent": _agent_display_name(raw_agent),
            "raw_agent": raw_agent,
            "objective": str(todo.get("title", "")),
            "status": str(todo.get("status", "unknown")),
            "artifacts": str(len(todo.get("artifacts", []))),
        })
    return {
        "run_dir": str(run_dir),
        "status": manifest.get("status", "unknown"),
        "workflow_profile": "adaptive_urban_analysis",
        "trace_id": manifest.get("run_id"),
        "agent_plan": agent_plan,
        "total_latency_s": None,
        "quality_control": manifest.get("quality_control", {"plan_passed": True, "exec_passed": True}),
        "artifact_count": len(manifest.get("artifacts", [])),
        "artifacts": manifest.get("artifacts", []),
        "reasoning_steps": reasoning_steps[:6],
        "final_answer_preview": "Observable UrbanAgent run completed with subagent status, reasoning breadcrumbs, GIS layers, charts, tables, and report artifacts.",
    }


def _print_section(title: str) -> None:
    if _rich_ui_enabled():
        _CONSOLE.print(Rule(Text(title, style="bold cyan"), style="bright_black"))
        return
    print(f"\n== {title} ==")


def _print_run_report(summary: dict[str, Any]) -> None:
    if _rich_ui_enabled():
        qc = summary.get("quality_control", {})
        qc_plan = "pass" if qc.get("plan_passed") else "revise"
        qc_exec = "pass" if qc.get("exec_passed") else "revise"
        cards = [
            _make_value_panel("Status", str(summary["status"]), style="bold green" if summary["status"] == "success" else "bold yellow"),
            _make_value_panel("Routing", _WORKFLOW_ROUTING_LABEL, style="bold cyan"),
            _make_value_panel("Latency", f"{summary['total_latency_s']:.2f} s" if summary.get("total_latency_s") is not None else "n/a", style="bold white"),
            _make_value_panel("QC", f"plan {qc_plan} | exec {qc_exec}", style="bold magenta" if "revise" in {qc_plan, qc_exec} else "bold green"),
        ]
        if summary.get("runtime"):
            runtime = summary["runtime"]
            cards.append(_make_value_panel(
                "Runtime",
                f"{runtime.get('todo_completed', 0)}/{runtime.get('todo_total', 0)} todos | {runtime.get('checkpoint_count', 0)} checks",
                style="bold cyan" if not runtime.get("blocked_count") else "bold yellow",
            ))
        if summary.get("review"):
            review = summary["review"]
            review_status = "pass" if review.get("passed") else "revise"
            score = review.get("urban_validity_score") or review.get("quality_score")
            score_text = f"{float(score):.2f}" if score is not None else "n/a"
            cards.append(_make_value_panel(
                "Review",
                f"{review_status} | {score_text}",
                style="bold green" if review.get("passed") else "bold yellow",
            ))
        hero = _make_key_value_panel(
            "Run Complete",
            [
                ("Run dir", _truncate_middle(summary["run_dir"])),
                ("Trace", str(summary.get("trace_id") or "n/a")),
            ],
        )
        _CONSOLE.print(Group(hero, Columns(cards, equal=True, expand=True)))
        if summary.get("agent_plan"):
            table = Table(box=box.ASCII, expand=True)
            table.add_column("Step", style="dim", width=6, no_wrap=True)
            table.add_column("Agent", width=20, no_wrap=True)
            table.add_column("Status", width=10, no_wrap=True)
            table.add_column("Objective", style="white")
            for item in summary["agent_plan"]:
                raw_agent = item.get("raw_agent", item["agent"])
                table.add_row(item["step"], Text(item["agent"], style=_agent_style(raw_agent)), item.get("status", "planned"), item["objective"])
            _CONSOLE.print(Panel(table, title="Agent Workflow", border_style="bright_black", box=box.ASCII, padding=(0, 1)))
        if summary.get("reasoning_steps"):
            reasoning = Table(box=box.ASCII, expand=True)
            reasoning.add_column("Agent", width=20, no_wrap=True)
            reasoning.add_column("Method", style="white")
            reasoning.add_column("Confidence", width=10, no_wrap=True)
            for step in summary["reasoning_steps"]:
                raw_agent = str(step.get("agent", "unknown"))
                reasoning.add_row(_agent_display_name(raw_agent), str(step.get("method", "")), str(step.get("confidence", "")))
            _CONSOLE.print(Panel(reasoning, title="Reasoning Breadcrumbs", border_style="bright_black", box=box.ASCII, padding=(0, 1)))
        if summary.get("review", {}).get("policies"):
            review_table = Table(box=box.ASCII, expand=True)
            review_table.add_column("Policy", style="white")
            review_table.add_column("Score", width=8, no_wrap=True)
            review_table.add_column("Applies", width=8, no_wrap=True)
            review_table.add_column("Issues", width=8, no_wrap=True)
            for policy in summary["review"]["policies"]:
                score = policy.get("score")
                score_text = f"{float(score):.2f}" if score is not None else "n/a"
                review_table.add_row(
                    str(policy.get("name", "")),
                    score_text,
                    "yes" if policy.get("applicable") else "no",
                    str(policy.get("issue_count", 0)),
                )
            title = f"ReviewHub ({summary['review'].get('recommendation', 'n/a')}, warnings={summary['review'].get('warning_count', 0)})"
            _CONSOLE.print(Panel(review_table, title=title, border_style="bright_black", box=box.ASCII, padding=(0, 1)))
        if summary.get("artifacts"):
            artifact_table = Table(box=box.ASCII, expand=True)
            artifact_table.add_column("Artifact", width=26, no_wrap=True)
            artifact_table.add_column("Type", width=20, no_wrap=True)
            artifact_table.add_column("Path", style="dim")
            for artifact in summary["artifacts"][:10]:
                artifact_table.add_row(str(artifact.get("title", artifact.get("id", ""))), str(artifact.get("type", "")), _truncate_middle(str(artifact.get("path", "")), 64))
            _CONSOLE.print(Panel(artifact_table, title=f"Artifacts ({summary.get('artifact_count', len(summary.get('artifacts', [])))})", border_style="bright_black", box=box.ASCII, padding=(0, 1)))
        preview = summary.get("final_answer_preview") or ""
        if preview:
            _CONSOLE.print(Panel(preview, title="Answer", border_style="cyan", box=box.ASCII, padding=(0, 1)))
        return

    _print_section("Run Complete")
    print(f"Run directory   {summary['run_dir']}")
    print(f"Status          {summary['status']}")
    if summary.get("trace_id"):
        print(f"Trace ID        {summary['trace_id']}")
    if summary.get("total_latency_s") is not None:
        print(f"Latency         {summary['total_latency_s']:.2f} s")
    if summary.get("runtime"):
        runtime = summary["runtime"]
        print(
            f"Runtime         {runtime.get('todo_completed', 0)}/{runtime.get('todo_total', 0)} todos, "
            f"{runtime.get('checkpoint_count', 0)} checkpoints, mode={runtime.get('mode', 'autonomous')}"
        )
    if summary.get("review"):
        review = summary["review"]
        score = review.get("urban_validity_score") or review.get("quality_score")
        score_text = f"{float(score):.2f}" if score is not None else "n/a"
        print(f"ReviewHub      {review.get('recommendation', 'n/a')} score={score_text} warnings={review.get('warning_count', 0)}")
    if summary.get("agent_plan"):
        print("\nAgent workflow")
        for item in summary["agent_plan"]:
            status = item.get("status", "planned")
            print(f"  {item['step']}. {item['agent']:<22} {status:<10} {item['objective']}")
    if summary.get("reasoning_steps"):
        print("\nReasoning breadcrumbs")
        for step in summary["reasoning_steps"]:
            raw_agent = str(step.get("agent", "unknown"))
            print(f"  - {_agent_display_name(raw_agent)}: {step.get('method', '')} (confidence={step.get('confidence', '')})")
    if summary.get("artifacts"):
        print(f"\nArtifacts ({summary.get('artifact_count', len(summary['artifacts']))})")
        for artifact in summary["artifacts"][:10]:
            print(f"  - {artifact.get('title', artifact.get('id'))}: {artifact.get('path')}")
    preview = summary.get("final_answer_preview") or ""
    if preview:
        print("\nAnswer")
        print(preview)


def _provider_status(provider_name: str) -> dict[str, Any]:
    keys = PROVIDER_KEY_MAP.get(provider_name, [])
    present = [key for key in keys if os.getenv(key)]
    status = {
        "keys": keys,
        "configured": bool(present),
        "present_keys": present,
    }
    if provider_name == "kimi":
        status["client_type"] = os.getenv("KIMI_CLIENT_TYPE", "auto")
        status["selection_order"] = ["coding", "standard"] if status["client_type"] == "auto" else [status["client_type"]]
    return status


def _build_doctor_report() -> dict[str, Any]:
    selected_provider = _selected_provider()
    providers = {name: _provider_status(name) for name in PROVIDER_KEY_MAP}
    configured_providers = [name for name, status in providers.items() if status["configured"]]
    warnings = []

    if ENV_FILE is None or not ENV_FILE.exists():
        warnings.append(f"no .env file found; run 'urban-agent init' or create {USER_ENV_FILE}")
    if not USER_CONFIG_FILE.exists():
        warnings.append(f"no config.yaml found; run 'urban-agent setup' or create {USER_CONFIG_FILE}")
    if not configured_providers:
        warnings.append("no provider API key detected in environment")
    if selected_provider not in providers:
        warnings.append(f"selected provider '{selected_provider}' is not in the documented provider list")
    elif not providers[selected_provider]["configured"]:
        warnings.append(f"selected provider '{selected_provider}' has no detected API key")

    return {
        "project_root": str(PROJECT_ROOT),
        "install_root": str(get_install_root()),
        "urban_home": str(USER_CONFIG_DIR),
        "cwd": str(Path.cwd()),
        "config": {
            "user_config_dir": str(USER_CONFIG_DIR),
            "user_env_file": str(USER_ENV_FILE),
            "user_config_file": str(USER_CONFIG_FILE),
            "active_env_file": str(ENV_FILE) if ENV_FILE else None,
            "env_candidates": [str(item) for item in _env_candidates()],
        },
        "python": {
            "version": platform.python_version(),
            "executable": sys.executable,
        },
        "environment": {
            ".env_exists": bool(ENV_FILE and ENV_FILE.exists()),
            "config_yaml_exists": USER_CONFIG_FILE.exists(),
            ".env_example_exists": ENV_TEMPLATE_FILE.exists(),
            "selected_provider": selected_provider,
            "configured_providers": configured_providers,
            "providers": providers,
        },
        "paths": {
            "default_runs_dir": str(DEFAULT_RUNS_DIR),
            "sessions_dir": str(get_sessions_dir()),
            "logs_dir": str(get_logs_dir()),
        },
        "warnings": warnings,
    }


def _doctor_fix() -> dict[str, Any]:
    ensure_urban_home()
    env_existed = USER_ENV_FILE.exists()
    config_existed = USER_CONFIG_FILE.exists()
    write_default_env(USER_ENV_FILE, force=False)
    write_default_config(USER_CONFIG_FILE, force=False)
    return {
        "urban_home": str(USER_CONFIG_DIR),
        "env": "kept" if env_existed else "created",
        "config": "kept" if config_existed else "created",
        "runs_dir": str(DEFAULT_RUNS_DIR),
        "sessions_dir": str(get_sessions_dir()),
        "logs_dir": str(get_logs_dir()),
    }


def _print_doctor_report(report: dict[str, Any]) -> None:
    env = report["environment"]
    if _rich_ui_enabled():
        cards = [
            _make_value_panel("Provider", str(env["selected_provider"]), style="bold cyan"),
            _make_value_panel("Configured", ", ".join(env["configured_providers"]) if env["configured_providers"] else "none", style="bold green" if env["configured_providers"] else "bold yellow"),
            _make_value_panel("Python", report["python"]["version"], style="bold white"),
            _make_value_panel("Runs", _output_dir_label(report["paths"]["default_runs_dir"]), style="bold white"),
        ]
        info = _make_key_value_panel(
            "UrbanAgent Doctor",
            [
                ("Runtime root", _truncate_middle(report["project_root"])),
                ("Urban home", _truncate_middle(report["urban_home"])),
                ("Install root", _truncate_middle(report["install_root"])),
                ("Working dir", _truncate_middle(report["cwd"])),
                ("Config file", _truncate_middle(report["config"]["active_env_file"] or "not found")),
                ("Config YAML", _truncate_middle(report["config"]["user_config_file"])),
                ("User config", _truncate_middle(report["config"]["user_config_dir"])),
                ("Executable", _truncate_middle(report["python"]["executable"])),
            ],
        )
        _CONSOLE.print(Group(info, Columns(cards, equal=True, expand=True)))
        if report["warnings"]:
            warning_table = Table.grid(expand=True)
            warning_table.add_column(style="yellow")
            for warning in report["warnings"]:
                warning_table.add_row(f"- {warning}")
            _CONSOLE.print(Panel(warning_table, title="Warnings", border_style="yellow", box=box.ASCII, padding=(0, 1)))
        else:
            _CONSOLE.print(_make_caption_panel("No obvious blocking issues detected.", title="Status"))
        return

    _print_section("UrbanAgent Doctor")
    print(f"Runtime root         {report['project_root']}")
    print(f"Urban home           {report['urban_home']}")
    print(f"Install root         {report['install_root']}")
    print(f"Working directory    {report['cwd']}")
    print(f"Config file          {report['config']['active_env_file'] or 'not found'}")
    print(f"Config YAML          {report['config']['user_config_file']}")
    print(f"User config dir      {report['config']['user_config_dir']}")
    print(f"Python               {report['python']['version']} ({report['python']['executable']})")
    print(f"Selected provider    {env['selected_provider']}")
    print(f"Configured providers {', '.join(env['configured_providers']) if env['configured_providers'] else 'none'}")
    if report["warnings"]:
        print("\nWarnings:")
        for warning in report["warnings"]:
            print(f"- {warning}")
    else:
        print("\nNo obvious blocking issues detected.")


def _load_workflow_case_module():
    module_path = PROJECT_ROOT / "scripts" / "benchmarks" / "workflow_case_studies.py"
    if not module_path.exists():
        raise FileNotFoundError(
            "'urban-agent case' is a source-only demo command and is not part of the standard installed task surface. "
            "Use 'urban-agent analyze' or 'urban-agent shell' for arbitrary city analysis tasks. "
            f"Missing source file: {module_path}"
        )
    spec = importlib.util.spec_from_file_location("urban_agent_workflow_case_studies", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load workflow case module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _print_case_command_unavailable(error: Exception) -> None:
    print(str(error))


async def _run_case_studies(case_name: str, output_dir: str) -> Path:
    module = _load_workflow_case_module()
    cases = None if case_name == "all" else [case_name]
    result = await module.run_all_cases(cases=cases)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"case_studies_{_timestamp()}.json"
    _write_json(result, out_path)
    return out_path


async def _run_pipeline_task(
    *,
    task_text: str,
    bbox: Optional[str],
    input_path: Optional[str],
    output_dir: str,
    interaction_mode: str,
    run_name: Optional[str] = None,
    session_id: Optional[str] = None,
    show_progress: bool = False,
) -> dict[str, Any]:
    from .agents.orchestrator import MultiAgentOrchestrator
    from .core import PerceptionModule, ReasoningModule

    task_payload = _build_task_payload(task_text, bbox, input_path)
    run_dir = _create_run_dir(Path(output_dir), run_name or task_text)
    stable_session_id = session_id or run_dir.name
    artifact_dir = run_dir / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    task_payload["artifact_dir"] = str(artifact_dir)
    task_payload["run_dir"] = str(run_dir)

    request_record = {
        "timestamp": datetime.now().isoformat(),
        "task": task_text,
        "bbox": bbox,
        "input_path": input_path,
        "interaction_mode": interaction_mode,
        "task_payload": task_payload,
    }
    _write_json(request_record, run_dir / "request.json")

    if show_progress:
        if _rich_ui_enabled():
            _CONSOLE.print("[bold cyan]PLAN[/] preparing multi-agent runtime (planner=deep-reasoning, exec=flash)")
        else:
            print("[plan] preparing multi-agent runtime (planner=deep, exec=flash)")
    planner_llm_client = _build_planner_llm_client()
    exec_llm_client = _build_exec_llm_client()
    vlm_client = exec_llm_client if hasattr(exec_llm_client, "analyze_image") else None
    perception_module = PerceptionModule(llm_client=exec_llm_client, vlm_client=vlm_client)
    reasoning_module = ReasoningModule(llm_client=exec_llm_client)
    prompt_snapshot_path = get_sessions_dir() / stable_session_id / "prompt_snapshot.json" if session_id else run_dir / "prompt_snapshot.json"

    orchestrator = MultiAgentOrchestrator(
        llm_client=exec_llm_client,
        planner_llm_client=planner_llm_client,
        vlm_client=vlm_client,
        interaction_mode=interaction_mode,
        perception_module=perception_module,
        reasoning_module=reasoning_module,
        config={
            **read_urban_config(USER_CONFIG_FILE),
            "session_id": stable_session_id,
            "prompt_snapshot_path": str(prompt_snapshot_path),
            "project_root": str(Path.cwd()),
        },
    )
    if show_progress:
        if _rich_ui_enabled():
            _CONSOLE.print("[bold green]EXEC[/] planner -> workers -> reviewer")
        else:
            print("[execute] planner -> workers -> reviewer")
    result = await orchestrator.run(task_payload)
    _write_json(result, run_dir / "result.json")

    summary = _build_run_summary(run_dir, result)
    _write_json(summary, run_dir / "summary.json")
    if summary.get("final_answer_preview"):
        _write_text(summary["final_answer_preview"], run_dir / "final_answer.txt")

    return {
        "run_dir": run_dir,
        "result": result,
        "summary": summary,
    }


async def _preview_plan(task_text: str, bbox: Optional[str], input_path: Optional[str]) -> dict[str, Any]:
    from .agents.base import AgentMessage, AgentRole
    from .agents.planner import PlannerAgent

    task_payload = _build_task_payload(task_text, bbox, input_path)
    llm_client = None
    if os.getenv("URBAN_AGENT_PLAN_LIVE", "0") == "1":
        try:
            llm_client = _build_llm_client()
        except RuntimeError:
            pass
    planner = PlannerAgent(llm_client=llm_client)
    message = AgentMessage(
        sender=AgentRole.MANAGER,
        receiver=AgentRole.PLANNER,
        msg_type="plan",
        payload=task_payload,
        trace_id=f"preview_{_timestamp()}",
    )
    result = await planner.execute(message)
    return result.payload["execution_plan"]


def _print_plan(plan: dict[str, Any]) -> None:
    if _rich_ui_enabled():
        meta = _make_key_value_panel(
            "Multi-Agent Plan",
            [
                ("Plan ID", str(plan.get("plan_id", "unknown"))),
                ("Workflow", str(plan.get("workflow_profile", "adaptive_urban_analysis"))),
                ("Complexity", str(plan.get("complexity", "unknown"))),
                ("Steps", str(len(plan.get("subtasks", [])))),
            ],
        )
        table = Table(box=box.ASCII, expand=True)
        table.add_column("Step", style="dim", width=6, no_wrap=True)
        table.add_column("Agent", width=20, no_wrap=True)
        table.add_column("Objective", style="white")
        for item in _summarize_plan(plan):
            table.add_row(item["step"], Text(item["agent"], style=_agent_style(item.get("raw_agent", item["agent"]))), item["objective"])
        _CONSOLE.print(Group(meta, Panel(table, title="Agent Workflow", border_style="bright_black", box=box.ASCII, padding=(0, 1))))
        capability_names = plan.get("capability_context", {}).get("selected_names", [])
        if capability_names:
            _CONSOLE.print(_make_caption_panel(", ".join(capability_names), title="Selected Capabilities"))
        return

    _print_section("Multi-Agent Plan")
    print(f"Plan ID        {plan.get('plan_id', 'unknown')}")
    print(f"Workflow       {plan.get('workflow_profile', 'adaptive_urban_analysis')}")
    print(f"Complexity     {plan.get('complexity', 'unknown')}")
    print("\nAgent workflow")
    for item in _summarize_plan(plan):
        print(f"  {item['step']}. {item['agent']:<18} {item['objective']}")
    capability_names = plan.get("capability_context", {}).get("selected_names", [])
    if capability_names:
        print("\nSelected capabilities")
        for name in capability_names:
            print(f"  - {name}")


def _build_capability_report(query: Optional[str], level: int = 0, limit: int = 8) -> dict[str, Any]:
    from .capabilities import get_default_capability_registry

    registry = get_default_capability_registry()
    if query:
        selected = registry.search(query, limit=limit)
        names = [capability.name for capability in selected]
    else:
        names = registry.names()[:limit]
    items = registry.disclose(names, level=level)
    return {
        "query": query,
        "level": level,
        "count": len(items),
        "items": items,
        "disclosure_policy": "progressive",
    }


def _print_capability_report(report: dict[str, Any]) -> None:
    if _rich_ui_enabled():
        table = Table(box=box.ASCII, expand=True)
        table.add_column("Capability", style="bold cyan", no_wrap=True, width=28)
        table.add_column("Family", width=14, no_wrap=True)
        table.add_column("Summary", style="white")
        for item in report["items"]:
            table.add_row(str(item.get("name", "")), str(item.get("family", "")), str(item.get("summary", "")))
        _CONSOLE.print(Panel(table, title=f"Capabilities (level {report['level']})", border_style="bright_black", box=box.ASCII, padding=(0, 1)))
        return

    _print_section(f"Capabilities (level {report['level']})")
    for item in report["items"]:
        print(f"- {item.get('name')} [{item.get('family')}] {item.get('summary')}")
        if report["level"] >= 1:
            backends = item.get("backend_names") or [backend.get("name") for backend in item.get("backends", [])]
            if backends:
                print(f"  backends: {', '.join(str(backend) for backend in backends)}")
        if report["level"] >= 2 and item.get("invocation"):
            invocation = item["invocation"]
            print(f"  mcp_tool: {invocation.get('mcp_tool')}")


class UrbanAgentShell:
    def __init__(self, args: argparse.Namespace):
        self.bbox = args.bbox
        self.input_path = args.input
        self.output_dir = args.output_dir
        self.interaction_mode = args.interaction_mode
        self.session_started_at = datetime.now()
        self.session_id = f"{self.session_started_at.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        self.last_summary: Optional[dict[str, Any]] = None
        self._history_file = USER_CONFIG_DIR / ".urban_agent_history"

    def run(self) -> None:
        self._print_banner()
        self._print_welcome()
        while True:
            try:
                line = self._prompt().strip()
            except EOFError:
                print()
                return
            except KeyboardInterrupt:
                print("\nUse /exit to leave the shell.")
                continue

            if not line:
                continue
            if _looks_like_shell_command(line):
                if self._handle_command(line):
                    return
                continue

            if self.interaction_mode == "guided":
                if not self._confirm_task(line):
                    print("Cancelled.")
                    continue

            try:
                report = asyncio.run(
                    _run_pipeline_task(
                        task_text=line,
                        bbox=self.bbox,
                        input_path=self.input_path,
                        output_dir=self.output_dir,
                        interaction_mode=self.interaction_mode,
                        session_id=self.session_id,
                        show_progress=True,
                    )
                )
            except RuntimeError as error:
                print(f"Run failed: {error}")
                continue
            self.last_summary = report["summary"]
            _print_run_report(report["summary"])

    def _print_welcome(self) -> None:
        """Post-banner welcome message, curator status, and tip."""
        accent = "#FFD700"
        dim_color = "#B8860B"
        text_color = "#FFF8DC"

        if _rich_ui_enabled():
            _CONSOLE.print()
            _CONSOLE.print(f"[{text_color}]Welcome to UrbanAgent! Type a city-analysis task or /commands for help.[/]")
            _CONSOLE.print(f"[dim {dim_color}]✦ Tip: Enter any urban question directly — routing, data, and methods are inferred from your task.[/]")

            # Runtime readiness summary
            provider = _selected_provider()
            caps_by_family = _get_capabilities_summary()
            total_caps = sum(len(v) for v in caps_by_family.values())
            tools_by_category = _get_tools_summary()
            total_tools = sum(len(v) for v in tools_by_category.values())

            _CONSOLE.print(f"[dim {dim_color}]💾 runtime: provider={provider}  ·  mode={self.interaction_mode}  ·  routing={_WORKFLOW_ROUTING_LABEL}[/]")
            _CONSOLE.print(f"[dim {dim_color}]   {total_tools} tools registered  ·  {total_caps} capabilities  ·  use /doctor to verify[/]")

            # Warning if no env file
            if ENV_FILE is None:
                _CONSOLE.print(f"[yellow]⚠ No .env file found — run 'urban-agent init' to configure API keys[/]")
            return

        # Plain text fallback
        print()
        print("Welcome to UrbanAgent! Type a city-analysis task or /commands for help.")
        print("✦ Tip: Enter any urban question directly — routing, data, and methods are inferred.")
        print(f"💾 runtime: provider={_selected_provider()}  ·  mode={self.interaction_mode}")
        if ENV_FILE is None:
            print("⚠ No .env file found — run 'urban-agent init' to configure API keys")

    def _print_banner(self) -> None:
        provider = _selected_provider()
        if _rich_ui_enabled():
            # Two-column banner
            accent = "#FFD700"
            dim_color = "#B8860B"
            text_color = "#FFF8DC"
            border_color = "#CD7F32"
            session_color = "#8B8682"

            # Build capability index
            caps_by_family = _get_capabilities_summary()
            total_caps = sum(len(v) for v in caps_by_family.values())

            # Build tool index
            tools_by_category = _get_tools_summary()
            total_tools = sum(len(v) for v in tools_by_category.values())

            # ── Right column: tools + capabilities ──
            right_lines: list[str] = []
            right_lines.append(f"[bold {accent}]Available Tools[/]")
            sorted_cats = sorted(tools_by_category.keys())
            for cat in sorted_cats:
                names = sorted(tools_by_category[cat])
                tools_str = ", ".join(f"[{text_color}]{n}[/]" for n in names)
                right_lines.append(f"[dim {dim_color}]{cat}:[/] {tools_str}")
            if not sorted_cats:
                right_lines.append(f"[dim {dim_color}]No tools registered[/]")

            right_lines.append("")
            right_lines.append(f"[bold {accent}]Available Capabilities[/]")
            sorted_families = sorted(caps_by_family.keys())
            for family in sorted_families[:8]:
                names = sorted(caps_by_family[family])
                caps_str = ", ".join(f"[{text_color}]{n}[/]" for n in names)
                if len(caps_str) > 55:
                    caps_str = caps_str[:52] + "..."
                right_lines.append(f"[dim {dim_color}]{family}:[/] {caps_str}")
            remaining = len(sorted_families) - 8
            if remaining > 0:
                right_lines.append(f"[dim {dim_color}](and {remaining} more families...)[/]")
            if not sorted_families:
                right_lines.append(f"[dim {dim_color}]No capabilities registered[/]")

            right_lines.append("")
            summary_parts = [f"{total_tools} tools", f"{total_caps} capabilities", "/commands for help"]
            right_lines.append(f"[dim {dim_color}]{' · '.join(summary_parts)}[/]")

            # ── Left column: hero + meta ──
            model_label = provider
            left_lines = [URBAN_AGENT_LOGO, "", f"[bold {accent}]{model_label}[/] [dim {dim_color}]· urban-mobility runtime[/]"]
            left_lines.append(f"[dim {session_color}]Session: {self.session_id}[/]")
            left_lines.append(f"[dim {dim_color}]{_truncate_middle(str(PROJECT_ROOT))}[/]")
            left_lines.append(f"[dim {dim_color}]Mode: {self.interaction_mode}  ·  Routing: {_WORKFLOW_ROUTING_LABEL}[/]")
            left_content = "\n".join(left_lines)
            right_content = "\n".join(right_lines)

            layout_table = Table.grid(padding=(0, 2))
            layout_table.add_column("left", justify="center", width=42, no_wrap=True)
            layout_table.add_column("right", justify="left")
            layout_table.add_row(left_content, right_content)

            version_label = "UrbanAgent v0.1.0 · runtime-kernel branch"
            outer_panel = Panel(
                layout_table,
                title=f"[bold {accent}]{version_label}[/]",
                border_style=border_color,
                padding=(0, 2),
            )

            term_width = shutil.get_terminal_size().columns
            _CONSOLE.print()
            if term_width >= 95:
                _CONSOLE.print(URBAN_AGENT_LOGO)
                _CONSOLE.print()
            _CONSOLE.print(outer_panel)
            return

        # Fallback plain-text banner
        print()
        print("┌─────────────────────────────────────────────────────────┐")
        print("│       UrbanAgent - City Science Agent Framework         │")
        print("└─────────────────────────────────────────────────────────┘")
        print(f"Session ID    {self.session_id}")
        print(f"Runtime root  {PROJECT_ROOT}")
        print(f"Config file   {ENV_FILE or 'not found'}")
        print(f"Provider      {_selected_provider()}")
        print(f"Routing       {_WORKFLOW_ROUTING_LABEL}")
        print(f"Mode          {self.interaction_mode}")
        print("-" * 57)
        print("Enter any city-analysis task. Use /commands, /plan, /tools, /runtime, /status, /doctor, or /quit.")

    def _confirm_task(self, task_text: str) -> bool:
        if _rich_ui_enabled():
            panel = _make_key_value_panel(
                "Confirm Run",
                [
                    ("Routing", _WORKFLOW_ROUTING_LABEL),
                    ("Mode", self.interaction_mode),
                    ("Input", self.input_path or "none"),
                    ("BBox", self.bbox or "none"),
                    ("Output dir", _truncate_middle(self.output_dir)),
                    ("Task", task_text),
                ],
            )
            _CONSOLE.print(panel)
            reply = _CONSOLE.input("[bold cyan]Proceed[/]? [dim][y/N][/dim] ").strip().lower()
            return reply in {"y", "yes"}

        print("\nRun summary:")
        print(f"- routing: {_WORKFLOW_ROUTING_LABEL}")
        print(f"- mode: {self.interaction_mode}")
        print(f"- input: {self.input_path or 'none'}")
        print(f"- bbox: {self.bbox or 'none'}")
        print(f"- output dir: {self.output_dir}")
        print(f"- task: {task_text}")
        reply = input("Proceed? [y/N] ").strip().lower()
        return reply in {"y", "yes"}

    def _prompt(self) -> str:
        hr = "─" * min(shutil.get_terminal_size().columns, 80)
        hr_dim = f"[dim #8B8682]{hr}[/]"
        if _PROMPT_TOOLKIT_AVAILABLE:
            USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            if _rich_ui_enabled():
                _CONSOLE.print(hr_dim)
            style = PromptStyle.from_dict({
                "brand": "#FFBF00 bold",
                "mode": "#CD7F32",
                "separator": "#B8860B",
                "prompt": "#FFD700 bold",
                "": "#FFF8DC",
            })
            result = _pt_prompt(
                [
                    ("class:brand", "urban-agent"),
                    ("class:separator", " · "),
                    ("class:mode", self.interaction_mode),
                    ("class:prompt", " ❯ "),
                ],
                history=FileHistory(str(self._history_file)),
                completer=WordCompleter(_shell_command_words(), ignore_case=True, sentence=True),
                auto_suggest=AutoSuggestFromHistory(),
                style=style,
                placeholder=(
                    lambda: [("class:separator", "Enter a city-analysis task or /command...")]
                ) if hasattr(_pt_prompt, "__code__") or True else None,
            )
            if _rich_ui_enabled():
                _CONSOLE.print(hr_dim)
            return result
        if _rich_ui_enabled():
            _CONSOLE.print(hr_dim)
            prompt = (
                f"[bold #FFBF00]urban-agent[/]"
                f"[#CD7F32] · {self.interaction_mode}[/]"
                f" [bold #FFD700]❯[/] "
            )
            result = _CONSOLE.input(prompt)
            _CONSOLE.print(hr_dim)
            return result
        print(hr)
        result = input("urban-agent ❯ ")
        print(hr)
        return result

    def _handle_command(self, line: str) -> bool:
        parts = shlex.split(line)
        command_def = _resolve_shell_command(parts[0])
        if command_def is None:
            print(f"Unknown command: {parts[0].lower()}. Use /commands.")
            return False
        command = f"/{command_def.name}"
        args = parts[1:]

        if command == "/quit":
            return True
        if command == "/commands":
            self._print_help()
            return False
        if command == "/new":
            self.session_started_at = datetime.now()
            self.session_id = f"{self.session_started_at.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
            self.last_summary = None
            print(f"Started new UrbanAgent session: {self.session_id}")
            return False
        if command == "/clear":
            os.system("cls" if os.name == "nt" else "clear")
            self._print_banner()
            return False
        if command == "/status":
            self._print_status()
            return False
        if command == "/runtime":
            self._print_runtime()
            return False
        if command == "/doctor":
            _print_doctor_report(_build_doctor_report())
            return False
        if command == "/config":
            _cmd_config(argparse.Namespace(json=False))
            return False
        if command == "/capabilities":
            query = " ".join(args).strip() or None
            _print_capability_report(_build_capability_report(query, level=1 if query else 0))
            return False
        if command == "/plan":
            task_text = " ".join(args).strip()
            if not task_text:
                print("Usage: /plan <natural-language city-analysis task>")
                return False
            plan = asyncio.run(_preview_plan(task_text, self.bbox, self.input_path))
            _print_plan(plan)
            return False
        if command == "/mode":
            if not args:
                print(f"Current mode: {self.interaction_mode}")
            elif args[0] in SUPPORTED_INTERACTION_MODES:
                self.interaction_mode = args[0]
                print(f"Mode set to {self.interaction_mode}")
            else:
                print(f"Unsupported mode: {args[0]}")
            return False
        if command == "/bbox":
            if not args:
                print(f"Current bbox: {self.bbox or 'none'}")
            elif args[0].lower() == "clear":
                self.bbox = None
                print("Cleared bbox")
            else:
                self.bbox = args[0]
                print(f"BBox set to {self.bbox}")
            return False
        if command == "/input":
            if not args:
                print(f"Current input: {self.input_path or 'none'}")
            elif args[0].lower() == "clear":
                self.input_path = None
                print("Cleared input file")
            else:
                candidate = Path(args[0])
                if not candidate.exists():
                    print(f"Input file not found: {candidate}")
                else:
                    self.input_path = str(candidate)
                    print(f"Input file set to {self.input_path}")
            return False
        if command == "/output":
            if not args:
                print(f"Current output dir: {self.output_dir}")
            else:
                self.output_dir = args[0]
                print(f"Output dir set to {self.output_dir}")
            return False
        print(f"Command is registered but has no handler yet: {command}")
        return False

    def _print_help(self) -> None:
        if _rich_ui_enabled():
            accent = "#FFD700"
            panels = []
            for category, commands in _shell_commands_by_category().items():
                table = Table(box=box.SIMPLE_HEAVY, expand=True, show_header=False)
                table.add_column("Command", style=f"bold {accent}", no_wrap=True, width=24)
                table.add_column("Purpose", style="#FFF8DC")
                for item in commands:
                    aliases = f" aliases: {', '.join('/' + alias for alias in item.aliases)}" if item.aliases else ""
                    usage = f" /{item.name} {item.args_hint}" if item.args_hint else f" /{item.name}"
                    table.add_row(usage, f"{item.description}{aliases}")
                panels.append(Panel(table, title=category, border_style="#CD7F32", box=box.SQUARE, padding=(0, 1)))
            _CONSOLE.print(Group(*panels))
            _CONSOLE.print(_make_caption_panel(
                "Direct task entry is the primary interaction path.\nRouting is inferred from the task text instead of being selected up front.",
                title="Interaction Model",
            ))
            return

        _print_section("Shell Commands")
        for category, commands in _shell_commands_by_category().items():
            print(f"\n◆ {category}")
            for item in commands:
                aliases = f" ({', '.join('/' + alias for alias in item.aliases)})" if item.aliases else ""
                usage = f"/{item.name} {item.args_hint}" if item.args_hint else f"/{item.name}"
                print(f"  {usage:<24} {item.description}{aliases}")

    def _print_status(self) -> None:
        runtime = self.last_summary.get("runtime", {}) if self.last_summary else {}
        accent = "#FFD700"
        if _rich_ui_enabled():
            _CONSOLE.print(_make_key_value_panel(
                "UrbanAgent Status",
                [
                    ("Session ID", self.session_id),
                    ("Started", self.session_started_at.strftime("%Y-%m-%d %H:%M:%S")),
                    ("Routing", _WORKFLOW_ROUTING_LABEL),
                    ("Mode", self.interaction_mode),
                    ("Provider", _selected_provider()),
                    ("BBox", self.bbox or "none"),
                    ("Input", _truncate_middle(self.input_path or "none")),
                    ("Output dir", _truncate_middle(self.output_dir)),
                    ("Config", _truncate_middle(str(ENV_FILE or "not found"))),
                    ("Last runtime", _format_runtime_status(runtime)),
                ],
            ))
            return

        print()
        print("┌─────────────────────────────────────────────────────────┐")
        print("│                  UrbanAgent CLI Status                 │")
        print("└─────────────────────────────────────────────────────────┘")
        print("◆ Session")
        print(f"  Session ID:   {self.session_id}")
        print(f"  Started:      {self.session_started_at.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Routing:      {_WORKFLOW_ROUTING_LABEL}")
        print(f"  Mode:         {self.interaction_mode}")
        print(f"  Provider:     {_selected_provider()}")
        print("◆ Context")
        print(f"  BBox:         {self.bbox or 'none'}")
        print(f"  Input:        {self.input_path or 'none'}")
        print(f"  Output dir:   {self.output_dir}")
        print(f"  Config:       {ENV_FILE or 'not found'}")
        print("◆ Runtime")
        print(f"  Last run:     {_format_runtime_status(runtime)}")

    def _print_runtime(self) -> None:
        if not self.last_summary:
            print("No completed run in this shell session yet.")
            return
        runtime = self.last_summary.get("runtime", {})
        if not runtime:
            print("Last run did not include a runtime ledger summary.")
            return
        if _rich_ui_enabled():
            _CONSOLE.print(_make_key_value_panel(
                "Last Runtime Ledger",
                [
                    ("Profile", str(runtime.get("profile", "urban_runtime_kernel"))),
                    ("Mode", str(runtime.get("mode", "autonomous"))),
                    ("Todos", f"{runtime.get('todo_completed', 0)}/{runtime.get('todo_total', 0)}"),
                    ("Checkpoints", str(runtime.get("checkpoint_count", 0))),
                    ("Blocked", str(runtime.get("blocked_count", 0))),
                    ("Last checkpoint", str(runtime.get("last_checkpoint") or "none")),
                ],
            ))
            return
        print("\n◆ Last Runtime Ledger")
        print(f"  Profile:          {runtime.get('profile', 'urban_runtime_kernel')}")
        print(f"  Mode:             {runtime.get('mode', 'autonomous')}")
        print(f"  Todos:            {runtime.get('todo_completed', 0)}/{runtime.get('todo_total', 0)}")
        print(f"  Checkpoints:      {runtime.get('checkpoint_count', 0)}")
        print(f"  Blocked:          {runtime.get('blocked_count', 0)}")
        print(f"  Last checkpoint:  {runtime.get('last_checkpoint') or 'none'}")


# ── Command implementations ──────────────────────────────────────

async def _cmd_perceive(args):
    """执行感知"""
    from .core.perception import PerceptionModule

    task = {"data_type": args.data_type}
    if args.bbox:
        parts = [float(x) for x in args.bbox.split(",")]
        task["bbox"] = {"min_lon": parts[0], "min_lat": parts[1], "max_lon": parts[2], "max_lat": parts[3]}
    if args.input:
        with open(args.input, encoding="utf-8") as f:
            task.update(json.load(f))

    module = PerceptionModule()
    result = await module.process(task)
    _write_json(result, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2)[:3000])


def _cmd_cognize(args):
    """执行双空间认知"""
    from legacy.urban_agent_legacy.cognition import SpatialCognition

    with open(args.input, encoding="utf-8") as f:
        perception_data = json.load(f)

    # SpatialCognition.understand() expects a context object with raw_features
    # We create a lightweight adapter
    class _Context:
        def __init__(self, data):
            self.raw_features = data
            self.buildings = data.get("buildings", [])
            self.roads = data.get("roads", data.get("road_network", []))
            self.pois = data.get("pois", [])
            self.features = data

    cognition = SpatialCognition()
    result = cognition.understand(_Context(perception_data), args.task)
    _write_json(result, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str)[:3000])


async def _cmd_reason(args):
    """执行空间推理"""
    from .core.reasoning import ReasoningModule

    with open(args.input, encoding="utf-8") as f:
        input_data = json.load(f)

    task = {"question": args.question}
    module = ReasoningModule()
    result = await module.infer(input_data, {}, task)
    _write_json(result, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str)[:3000])


def _cmd_visualize(args):
    """执行可视化"""
    from legacy.urban_agent_legacy.visualization import SpatialVisualizer

    with open(args.input, encoding="utf-8") as f:
        data = json.load(f)

    viz = SpatialVisualizer()

    # 从数据中提取所需字段
    raw_features = data.get("raw_features", data.get("features", data))
    intervention_areas = data.get("intervention_areas", data.get("proposals", []))
    bbox = data.get("bbox", (0, 0, 1, 1))
    if isinstance(bbox, dict):
        bbox = (bbox.get("min_lon", 0), bbox.get("min_lat", 0),
                bbox.get("max_lon", 1), bbox.get("max_lat", 1))
    elif isinstance(bbox, list):
        bbox = tuple(bbox)

    if args.format in ("svg", "both", "all"):
        svg_result = viz.create_svg_overlay(raw_features, intervention_areas, bbox)
        svg_path = f"{args.output}.svg"
        with open(svg_path, "w", encoding="utf-8") as f:
            f.write(svg_result if isinstance(svg_result, str) else str(svg_result))
        print(f"SVG written to {svg_path}")

    if args.format in ("geojson", "both", "all"):
        crs = data.get("crs") or raw_features.get("_crs") or "EPSG:4326"
        geojson_result = viz.create_geojson_collection(intervention_areas, crs)
        geojson_path = f"{args.output}.geojson"
        with open(geojson_path, "w", encoding="utf-8") as f:
            json.dump(geojson_result, f, ensure_ascii=False, indent=2) if isinstance(geojson_result, dict) else f.write(str(geojson_result))
        print(f"GeoJSON written to {geojson_path}")

    if args.format in ("html", "all"):
        html_result = viz.create_inspection_html(data)
        html_path = f"{args.output}.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_result)
        print(f"HTML written to {html_path}")


def _cmd_correct(args):
    """应用人工纠偏模块并导出修正结果。"""
    from .core import CorrectionModuleRegistry
    from legacy.urban_agent_legacy.visualization import SpatialVisualizer

    with open(args.input, encoding="utf-8") as f:
        cognition_result = json.load(f)
    with open(args.request, encoding="utf-8") as f:
        correction_request = json.load(f)

    registry = CorrectionModuleRegistry()
    result = registry.apply(cognition_result, correction_request)
    corrected_payload = result["corrected_payload"]

    _write_json(corrected_payload, args.output)
    print(f"Corrected cognition written to {args.output}")
    print(json.dumps(result["audit"], ensure_ascii=False, indent=2, default=str))

    if args.html_output:
        visualizer = SpatialVisualizer()
        html = visualizer.create_inspection_html(corrected_payload, corrections=result["audit"])
        with open(args.html_output, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"Inspection HTML written to {args.html_output}")


def _cmd_review(args):
    """执行空间质量审查"""
    with open(args.input, encoding="utf-8") as f:
        results = json.load(f)

    # Rule-based review (same logic as SpatialReviewerAgent)
    issues = []
    
    def _check_recursive(data, path=""):
        if isinstance(data, dict):
            for key in ("latitude", "lat"):
                val = data.get(key)
                if val is not None:
                    try:
                        if not (-90 <= float(val) <= 90):
                            issues.append(f"{path}.{key}={val}: latitude out of range [-90,90]")
                    except (ValueError, TypeError):
                        pass
            for key in ("longitude", "lon", "lng"):
                val = data.get(key)
                if val is not None:
                    try:
                        if not (-180 <= float(val) <= 180):
                            issues.append(f"{path}.{key}={val}: longitude out of range [-180,180]")
                    except (ValueError, TypeError):
                        pass
            for k, v in data.items():
                _check_recursive(v, f"{path}.{k}")
        elif isinstance(data, list):
            for i, item in enumerate(data):
                _check_recursive(item, f"{path}[{i}]")

    _check_recursive(results)
    policy = _load_cli_quality_policy()
    issue_penalty = float(policy.get("cli_issue_penalty", 0.15))
    confidence_threshold = float(policy.get("confidence_threshold", 0.0))
    quality_score = max(0.0, 1.0 - len(issues) * issue_penalty)
    report = {
        "quality_score": quality_score,
        "passed": quality_score >= confidence_threshold,
        "issues": issues,
        "recommendation": "accept" if quality_score >= confidence_threshold else "revise",
    }
    _write_json(report, args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def _load_cli_quality_policy() -> dict[str, Any]:
    try:
        from .memory_store import FileMemoryStore

        for record in FileMemoryStore.default().records("policy"):
            payload = record.to_dict()
            if payload.get("policy_id") == "quality_confidence_policy":
                return payload
    except Exception:
        return {}
    return {}


async def _cmd_run(args):
    """兼容旧入口，转发到新的 task-oriented runner。"""
    report = await _run_pipeline_task(
        task_text=args.question,
        bbox=args.bbox,
        input_path=args.input,
        output_dir=args.output_dir,
        interaction_mode=args.interaction_mode,
        show_progress=True,
    )
    _print_run_report(report["summary"])


async def _cmd_analyze(args):
    report = await _run_pipeline_task(
        task_text=args.task,
        bbox=args.bbox,
        input_path=args.input,
        output_dir=args.output_dir,
        interaction_mode=args.interaction_mode,
        run_name=args.name,
        show_progress=True,
    )
    _print_run_report(report["summary"])


async def _cmd_case(args):
    try:
        out_path = await _run_case_studies(args.case, args.output_dir)
    except FileNotFoundError as error:
        _print_case_command_unavailable(error)
        return
    print(f"Case results saved to {out_path}")


def _cmd_doctor(args):
    fix_report = None
    if getattr(args, "fix", False):
        fix_report = _doctor_fix()
    report = _build_doctor_report()
    if args.json:
        if fix_report:
            report["fix"] = fix_report
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    if fix_report:
        _print_section("UrbanAgent Doctor Fix")
        for key, value in fix_report.items():
            print(f"{key:<14} {value}")
    _print_doctor_report(report)


def _cmd_init(args):
    path = _write_default_user_config(args.from_env, force=args.force)
    if _rich_ui_enabled():
        _CONSOLE.print(_make_key_value_panel(
            "UrbanAgent Init",
            [
                ("API keys", _truncate_middle(str(path))),
                ("Config YAML", _truncate_middle(str(USER_CONFIG_FILE))),
                ("Provider", _selected_provider()),
            ],
        ))
        _CONSOLE.print(_make_caption_panel("Edit .env for API keys and config.yaml for model/runtime defaults.", title="Next Step"))
        return
    _print_section("UrbanAgent Init")
    print(f"API keys written to {path}")
    print(f"Config YAML written to {USER_CONFIG_FILE}")
    print("Edit .env for API keys and config.yaml for model/runtime defaults.")


def _prompt_default(label: str, current: str, *, choices: Optional[Sequence[str]] = None) -> str:
    choices_text = f" ({'/'.join(choices)})" if choices else ""
    reply = input(f"{label}{choices_text} [{current}]: ").strip()
    if not reply:
        return current
    if choices and reply not in choices:
        print(f"Unsupported value: {reply}; keeping {current}")
        return current
    return reply


def _provider_key_name(provider: str) -> str:
    return {
        "qwen": "QWEN_API_KEY",
        "openai": "OPENAI_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "kimi": "KIMI_CODE_API_KEY",
    }.get(provider, f"{provider.upper()}_API_KEY")


def _write_env_key(env_path: Path, key_name: str, value: str) -> None:
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    updated = False
    new_lines = []
    for line in lines:
        if line.startswith(f"{key_name}="):
            new_lines.append(f"{key_name}={value}")
            updated = True
        else:
            new_lines.append(line)
    if not updated:
        new_lines.append(f"{key_name}={value}")
    env_path.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")


def _cmd_setup(args):
    _write_default_user_config(force=args.force)
    config = read_urban_config(USER_CONFIG_FILE)
    model_config = config.get("model", {}) if isinstance(config, dict) else {}
    current_provider = str(model_config.get("provider", "qwen")) if isinstance(model_config, dict) else "qwen"
    current_model = str(model_config.get("default", "qwen-plus")) if isinstance(model_config, dict) else "qwen-plus"
    provider = args.provider or current_provider
    model_name = args.model or current_model
    runs_dir = args.runs_dir or str(configured_runs_dir(config))

    interactive = not args.non_interactive and sys.stdin.isatty()
    if interactive:
        provider = _prompt_default("Model provider", provider, choices=tuple(sorted(PROVIDER_KEY_MAP)))
        model_name = _prompt_default("Default model", model_name)
        runs_dir = _prompt_default("Runs directory", runs_dir)

    set_config_value(config, "model.provider", provider)
    set_config_value(config, "model.default", model_name)
    set_config_value(config, f"model.providers.{provider}.model", model_name)
    set_config_value(config, "runs.dir", runs_dir)
    write_urban_config(config, USER_CONFIG_FILE)

    api_key = args.api_key
    key_name = _provider_key_name(provider)
    if interactive and not api_key and not os.getenv(key_name):
        import getpass

        api_key = getpass.getpass(f"{key_name} (leave blank to skip): ").strip()
    if api_key:
        _write_env_key(USER_ENV_FILE, key_name, api_key)

    apply_config_to_environment(config)
    _print_section("UrbanAgent Setup")
    print(f"Urban home   {USER_CONFIG_DIR}")
    print(f"API keys     {USER_ENV_FILE}")
    print(f"Config YAML  {USER_CONFIG_FILE}")
    print(f"Provider     {provider}")
    print(f"Model        {model_name}")
    print(f"Runs dir     {runs_dir}")


def _cmd_config(args):
    if getattr(args, "config_command", None) == "get":
        config = read_urban_config(USER_CONFIG_FILE)
        try:
            value = get_config_value(config, args.key)
        except KeyError:
            print(f"Config key not found: {args.key}", file=sys.stderr)
            return 2
        if isinstance(value, dict):
            print(dump_simple_yaml(value).rstrip())
        else:
            print(value)
        return 0
    if getattr(args, "config_command", None) == "set":
        config = read_urban_config(USER_CONFIG_FILE)
        set_config_value(config, args.key, parse_config_value(args.value))
        write_urban_config(config, USER_CONFIG_FILE)
        print(f"Set {args.key} = {args.value}")
        return 0

    report = _build_doctor_report()
    if args.json:
        print(json.dumps(report["config"], ensure_ascii=False, indent=2))
        return
    if _rich_ui_enabled():
        _CONSOLE.print(_make_key_value_panel(
            "UrbanAgent Config",
            [
                ("Active env", _truncate_middle(report["config"]["active_env_file"] or "not found")),
                ("User env", _truncate_middle(report["config"]["user_env_file"])),
                ("Config YAML", _truncate_middle(report["config"]["user_config_file"])),
                ("Config dir", _truncate_middle(report["config"]["user_config_dir"])),
                ("Provider", report["environment"]["selected_provider"]),
                (
                    "Configured",
                    ", ".join(report["environment"]["configured_providers"]) if report["environment"]["configured_providers"] else "none",
                ),
            ],
        ))
        return
    _print_section("UrbanAgent Config")
    print(f"Active env  {report['config']['active_env_file'] or 'not found'}")
    print(f"User env    {report['config']['user_env_file']}")
    print(f"Config YAML {report['config']['user_config_file']}")
    print(f"Config dir  {report['config']['user_config_dir']}")
    print(f"Provider    {report['environment']['selected_provider']}")
    print(f"Configured  {', '.join(report['environment']['configured_providers']) if report['environment']['configured_providers'] else 'none'}")


def _find_git_root(start: Path) -> Optional[Path]:
    for candidate in (start.resolve(), *start.resolve().parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _cmd_update(args):
    if args.dir:
        install_dir = Path(args.dir).expanduser().resolve()
    else:
        managed_dir = get_install_root()
        install_dir = managed_dir if (managed_dir / "pyproject.toml").exists() else PACKAGE_ROOT
    git_probe = subprocess.run(
        ["git", "-C", str(install_dir), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
    )
    commands = [
        ["git", "-C", str(install_dir), "pull", "--ff-only"],
    ]
    if not args.skip_install:
        commands.append([sys.executable, "-m", "pip", "install", "-e", str(install_dir)])
    if args.dry_run:
        for command in commands:
            print(" ".join(shlex.quote(part) for part in command))
        return 0
    if git_probe.returncode != 0:
        print(f"Not a git checkout: {install_dir}", file=sys.stderr)
        return 2
    if not (install_dir / "pyproject.toml").exists() and not args.skip_install:
        print(f"No pyproject.toml at {install_dir}; use --skip-install or pass --dir to the package root.", file=sys.stderr)
        return 2
    for command in commands:
        subprocess.run(command, check=True)
    print(f"UrbanAgent updated at {install_dir}")
    return 0


def _cmd_uninstall(args):
    install_dir = Path(args.dir).expanduser().resolve() if args.dir else get_install_root()
    targets = []
    if install_dir.exists():
        targets.append(("install", install_dir))
    if args.full and USER_CONFIG_DIR.exists():
        targets.append(("urban_home", USER_CONFIG_DIR))
    if not targets:
        print("No managed UrbanAgent install/data directory found for removal.")
        return 0
    if not args.yes:
        print("Planned removal:")
        for label, path in targets:
            print(f"- {label}: {path}")
        print("Re-run with --yes to delete these paths.")
        return 1
    for _, path in targets:
        shutil.rmtree(path)
    print("UrbanAgent uninstall cleanup complete.")
    return 0


def _cmd_serve(args):
    config = read_urban_config(USER_CONFIG_FILE)
    gateway = config.get("gateway", {}) if isinstance(config, dict) else {}
    host = args.host or str(gateway.get("host", "127.0.0.1"))
    port = args.port or int(gateway.get("port", 8765))
    reload = bool(args.reload or gateway.get("reload", False))
    try:
        import uvicorn
    except ImportError:
        print("uvicorn is not installed; run 'pip install uvicorn' or reinstall UrbanAgent.", file=sys.stderr)
        return 2
    print(f"Starting UrbanAgent Web/API at http://{host}:{port}")
    uvicorn.run("web.app:app", host=host, port=port, reload=reload)
    return 0


def _service_pid_file() -> Path:
    return get_logs_dir() / "urban-agent-service.pid"


def _service_log_file() -> Path:
    return get_logs_dir() / "urban-agent-service.log"


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True,
            text=True,
        )
        return str(pid) in result.stdout
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _read_service_pid() -> Optional[int]:
    pid_file = _service_pid_file()
    if not pid_file.exists():
        return None
    try:
        return int(pid_file.read_text(encoding="utf-8").strip())
    except ValueError:
        return None


def _cmd_service(args):
    _print_section("UrbanAgent Service")
    ensure_urban_home()
    pid_file = _service_pid_file()
    log_file = _service_log_file()
    pid = _read_service_pid()

    if args.action == "status":
        if pid and _pid_is_running(pid):
            print(f"running pid={pid}")
            print(f"log {log_file}")
        else:
            print("stopped")
            if pid_file.exists():
                pid_file.unlink()
        return 0
    if args.action == "install":
        print("Lightweight service mode uses a PID file rather than registering a system service.")
        print(f"pid file {pid_file}")
        print(f"log file {log_file}")
        print("Use 'urban-agent service start' to launch the background Web/API process.")
        return 0
    if args.action == "start":
        if pid and _pid_is_running(pid):
            print(f"already running pid={pid}")
            return 0
        log_file.parent.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env.setdefault("URBAN_AGENT_HOME", str(USER_CONFIG_DIR))
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        with log_file.open("ab") as log_handle:
            process = subprocess.Popen(
                [sys.executable, "-m", "urban_agent", "serve"],
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                env=env,
                creationflags=creationflags,
                start_new_session=(os.name != "nt"),
            )
        pid_file.write_text(str(process.pid), encoding="utf-8")
        print(f"started pid={process.pid}")
        print(f"log {log_file}")
        return 0
    if args.action == "stop":
        if not pid or not _pid_is_running(pid):
            print("not running")
            if pid_file.exists():
                pid_file.unlink()
            return 0
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False)
        else:
            os.kill(pid, signal.SIGTERM)
        if pid_file.exists():
            pid_file.unlink()
        print(f"stopped pid={pid}")
        return 0
    return 2


def _cmd_capabilities(args):
    report = _build_capability_report(args.query, level=args.level, limit=args.limit)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return
    _print_capability_report(report)


def _cmd_plan(args):
    plan = asyncio.run(_preview_plan(args.task, args.bbox, args.input))
    if args.output:
        _write_json(plan, args.output)
    _print_plan(plan)


def _cmd_shell(args):
    UrbanAgentShell(args).run()


async def _cmd_guided(args) -> None:
    """Run multi-turn guided analysis with human-in-the-loop."""
    from examples.rdma_style_demo import run_multiturn

    task_text = args.task
    if args.input:
        input_path = Path(args.input)
        if input_path.exists():
            task_text = input_path.read_text(encoding="utf-8")
    output_root = Path(args.output_dir) / (args.name or f"guided_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    print(f"\nStarting multi-turn guided session...")
    print(f"Task: {task_text[:200]}...")
    print(f"Output: {output_root}\n")
    await run_multiturn(task_text, run_name=args.name, output_root=output_root)


def main(argv: Optional[Sequence[str]] = None) -> int:
    _load_project_env()
    _configure_cli_logging()
    parser = build_parser()
    raw_args = list(argv) if argv is not None else sys.argv[1:]

    if not raw_args:
        shell_args = argparse.Namespace(
            bbox=None,
            input=None,
            output_dir=str(DEFAULT_RUNS_DIR),
            interaction_mode="supervisory",
        )
        _cmd_shell(shell_args)
        return 0

    try:
        if raw_args[0] == "case":
            case_args = _build_case_parser().parse_args(raw_args[1:])
            asyncio.run(_cmd_case(case_args))
            return 0

        args = parser.parse_args(raw_args)

        if args.command == "analyze":
            asyncio.run(_cmd_analyze(args))
        elif args.command == "doctor":
            _cmd_doctor(args)
        elif args.command == "init":
            _cmd_init(args)
        elif args.command == "setup":
            result = _cmd_setup(args)
            if isinstance(result, int):
                return result
        elif args.command == "config":
            result = _cmd_config(args)
            if isinstance(result, int):
                return result
        elif args.command == "serve":
            result = _cmd_serve(args)
            if isinstance(result, int):
                return result
        elif args.command == "service":
            result = _cmd_service(args)
            if isinstance(result, int):
                return result
        elif args.command == "update":
            result = _cmd_update(args)
            if isinstance(result, int):
                return result
        elif args.command == "uninstall":
            result = _cmd_uninstall(args)
            if isinstance(result, int):
                return result
        elif args.command == "capabilities":
            _cmd_capabilities(args)
        elif args.command == "plan":
            _cmd_plan(args)
        elif args.command == "shell":
            _cmd_shell(args)
        elif args.command == "guided":
            asyncio.run(_cmd_guided(args))
        elif args.command == "perceive":
            asyncio.run(_cmd_perceive(args))
        elif args.command == "cognize":
            _cmd_cognize(args)
        elif args.command == "reason":
            asyncio.run(_cmd_reason(args))
        elif args.command == "visualize":
            _cmd_visualize(args)
        elif args.command == "correct":
            _cmd_correct(args)
        elif args.command == "review":
            _cmd_review(args)
        elif args.command == "run":
            asyncio.run(_cmd_run(args))
        else:
            parser.print_help()
            return 1
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
