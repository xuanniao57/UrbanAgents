"""UrbanAgent CLI.

默认面向真实城市分析任务，而不是只暴露内部 research pipeline。

Examples:
    python -m urban_agent
    python -m urban_agent analyze --task-type geoqa --task "分析同济大学周边步行可达性"
    python -m urban_agent analyze --task-type open_workflow --task "基于输入 GeoJSON 诊断街道连通性" --input ./my_city_task.json
    python -m urban_agent doctor

Legacy pipeline commands are still available:
    python -m urban_agent perceive --data-type osm --bbox "121.4,31.2,121.5,31.3"
    python -m urban_agent cognize --input perception_result.json
    python -m urban_agent reason --task-type geoqa --input cognition_result.json --question "..."
    python -m urban_agent visualize --input analysis_result.json --format html
    python -m urban_agent review --input results.json
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import nullcontext
import importlib.util
import json
import logging
import os
import platform
import shutil
import shlex
import sys
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


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
USER_CONFIG_DIR = Path(os.getenv("URBAN_AGENT_CONFIG_DIR", Path.home() / ".urban-agent")).expanduser().resolve()
USER_ENV_FILE = USER_CONFIG_DIR / ".env"

DEFAULT_ENV_TEMPLATE = """# UrbanAgent user configuration
# This file is loaded from any working directory.

LLM_PROVIDER=qwen
LLM_MODEL=qwen-plus

QWEN_API_KEY=
QWEN_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen-plus

OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini

Deepseek_API_KEY=
Deepseek_API_BASE=https://api.deepseek.com
Deepseek_MODEL=deepseek-chat
DEEPSEEK_REASONER_MODEL=deepseek-reasoner

KIMI_API_KEY=
KIMI_BASE_URL=https://api.moonshot.cn/v1
KIMI_MODEL=moonshot-v1-auto
KIMI_CODE_API_KEY=
KIMI_CODE_API_BASE=https://api.moonshot.cn/v1
KIMI_CODE_MODEL=moonshot-v1-auto
"""


def _env_candidates() -> list[Path]:
    explicit_env = os.getenv("URBAN_AGENT_ENV")
    if explicit_env:
        return [Path(explicit_env).expanduser().resolve()]

    candidates: list[Path] = []
    override = os.getenv("URBAN_AGENT_HOME")
    if override:
        candidates.append(Path(override).expanduser().resolve() / ".env")

    cwd = Path.cwd().resolve()
    for candidate in (cwd, *cwd.parents):
        candidates.append(candidate / ".env")
    candidates.append(USER_ENV_FILE)
    return candidates


def _resolve_env_file() -> Optional[Path]:
    for candidate in _env_candidates():
        if candidate.exists():
            return candidate
    return None


def _resolve_project_root(env_file: Optional[Path] = None) -> Path:
    override = os.getenv("URBAN_AGENT_HOME")
    if override:
        return Path(override).expanduser().resolve()

    if env_file is not None:
        if env_file == USER_ENV_FILE:
            return USER_CONFIG_DIR
        return env_file.parent.resolve()

    cwd = Path.cwd().resolve()
    markers = (".env", ".env.example", "pyproject.toml")
    for candidate in (cwd, *cwd.parents):
        if any((candidate / marker).exists() for marker in markers):
            return candidate
    return cwd


def _default_runs_dir(runtime_root: Path) -> Path:
    if runtime_root == USER_CONFIG_DIR:
        return runtime_root / "runs"
    return runtime_root / "outputs" / "cli_runs"


ENV_FILE = _resolve_env_file()
PROJECT_ROOT = _resolve_project_root(ENV_FILE)
DEFAULT_RUNS_DIR = _default_runs_dir(PROJECT_ROOT)
DEFAULT_CASE_OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "case_studies"
ENV_TEMPLATE_FILE = PROJECT_ROOT / ".env.example"

SUPPORTED_TASK_TYPES = (
    "population_prediction",
    "object_detection",
    "geolocation",
    "geoqa",
    "mobility_prediction",
    "traffic_signal",
    "outdoor_navigation",
    "urban_exploration",
    "open_workflow",
)

SUPPORTED_INTERACTION_MODES = ("guided", "supervisory", "autonomous")
SUPPORTED_CASES = ("walkability", "mobility", "all")

PROVIDER_KEY_MAP = {
    "qwen": ["QWEN_API_KEY"],
    "openai": ["OPENAI_API_KEY"],
    "deepseek": ["Deepseek_API_KEY", "DEEPSEEK_API_KEY"],
    "kimi": ["KIMI_API_KEY", "KIMI_CODE_API_KEY"],
}

_AUTO_TASK_TYPE_LABEL = "adaptive"

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


def _rich_ui_enabled() -> bool:
    return bool(_RICH_AVAILABLE and _CONSOLE is not None and _CONSOLE.is_terminal)


def _truncate_middle(value: str, max_length: int = 72) -> str:
    if len(value) <= max_length:
        return value
    keep = max(8, (max_length - 3) // 2)
    return f"{value[:keep]}...{value[-keep:]}"


def _output_dir_label(output_dir: str) -> str:
    path = Path(output_dir)
    return path.name or str(path)


def _infer_task_type(task_text: str, input_path: Optional[str] = None) -> str:
    text_parts = [task_text]
    if input_path:
        text_parts.append(Path(input_path).name)
    text = " ".join(part for part in text_parts if part).lower()

    population_terms = ("population", "demographic", "residents", "census", "人口", "居民", "人口密度")
    forecast_terms = ("predict", "forecast", "estimate", "project", "simulate", "预测", "估计", "推演")
    if any(term in text for term in population_terms) and any(term in text for term in forecast_terms):
        return "population_prediction"

    if any(term in text for term in ("detect", "detection", "segment", "count buildings", "count cars", "识别", "检测", "分割")):
        return "object_detection"

    if any(term in text for term in ("geolocate", "where is this", "which city", "identify location", "定位", "在哪", "识别地点")):
        return "geolocation"

    if any(term in text for term in ("trajectory", "trajectories", "mobility", "trip", "od flow", "commute", "travel demand", "轨迹", "出行", "通勤", "流量")):
        return "mobility_prediction"

    if any(term in text for term in ("traffic signal", "signal timing", "intersection phase", "traffic light", "红绿灯", "信号配时", "路口相位")):
        return "traffic_signal"

    if any(term in text for term in ("route", "routing", "navigate", "navigation", "shortest path", "wayfinding", "walk route", "路径", "导航", "路线", "最短路")):
        return "outdoor_navigation"

    if any(
        term in text
        for term in (
            "compare",
            "scenario",
            "strategy",
            "planning brief",
            "recommend",
            "walkability",
            "accessibility",
            "amenity",
            "urban design",
            "public space",
            "street network",
            "compare city",
            "land use",
            "对比",
            "策略",
            "建议",
            "步行可达性",
            "可达性",
            "公共空间",
            "街道网络",
            "开放空间",
            "规划",
        )
    ):
        return "urban_exploration"

    return "geoqa"


def _resolve_task_type(task_text: str, task_type: Optional[str], input_path: Optional[str] = None) -> str:
    if task_type in SUPPORTED_TASK_TYPES:
        return task_type
    return _infer_task_type(task_text, input_path)


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
    return os.getenv("LLM_PROVIDER", "qwen").strip().lower() or "qwen"


def _build_llm_client() -> Any:
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

            return DeepSeekClient()
        if provider_name == "kimi":
            from .llm.kimi_client import KimiClient

            return KimiClient(client_type="standard")
        if provider_name == "openai":
            return _OpenAICompatibleClient()
    except Exception as error:
        raise RuntimeError(f"Failed to initialize provider '{provider_name}': {error}") from error

    raise RuntimeError(
        f"Unsupported provider '{provider_name}'. Supported providers: {', '.join(PROVIDER_KEY_MAP)}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="urban-agent",
        description="UrbanAgent CLI for real-world urban analysis tasks",
    )
    subparsers = parser.add_subparsers(dest="command")

    # --- task-oriented commands ---
    p_analyze = subparsers.add_parser("analyze", help="Run an urban analysis task")
    p_analyze.add_argument("--task-type", choices=SUPPORTED_TASK_TYPES, default=None, help=argparse.SUPPRESS)
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

    p_doctor = subparsers.add_parser("doctor", help="Check environment, config, and provider status")
    p_doctor.add_argument("--json", action="store_true", help="Print JSON report")

    p_init = subparsers.add_parser("init", help="Initialize user-level UrbanAgent config")
    p_init.add_argument("--from-env", help="Copy config from an existing .env file")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing user-level config")

    p_config = subparsers.add_parser("config", help="Show config paths and provider status")
    p_config.add_argument("--json", action="store_true", help="Print JSON report")

    p_shell = subparsers.add_parser("shell", help="Start the interactive UrbanAgent shell")
    p_shell.add_argument("--task-type", choices=SUPPORTED_TASK_TYPES, default=None, help=argparse.SUPPRESS)
    p_shell.add_argument("--bbox", help="Default bounding box")
    p_shell.add_argument("--input", help="Default input JSON file")
    p_shell.add_argument("--output-dir", default=str(DEFAULT_RUNS_DIR), help="Run artifact root directory")
    p_shell.add_argument("--interaction-mode", choices=SUPPORTED_INTERACTION_MODES, default="supervisory", help="Default shell mode")

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
    p_reason.add_argument("--task-type", required=True, choices=SUPPORTED_TASK_TYPES[:-1], help="Task type")
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
    p_run.add_argument("--task-type", default="geoqa", help="Task type")
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
        return

    if ENV_FILE and ENV_FILE.exists():
        load_dotenv(ENV_FILE, override=False)


def _configure_cli_logging() -> None:
    logging.getLogger("urban_agent").setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.ERROR)
    logging.getLogger("httpcore").setLevel(logging.ERROR)
    logging.getLogger("openai").setLevel(logging.ERROR)


def _write_default_user_config(source_env: Optional[str] = None, force: bool = False) -> Path:
    USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if USER_ENV_FILE.exists() and not force:
        return USER_ENV_FILE

    if source_env:
        source = Path(source_env).expanduser().resolve()
        if not source.exists():
            raise FileNotFoundError(f"source .env not found: {source}")
        shutil.copyfile(source, USER_ENV_FILE)
    else:
        USER_ENV_FILE.write_text(DEFAULT_ENV_TEMPLATE, encoding="utf-8")
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


def _build_task_payload(task_text: str, task_type: str, bbox: Optional[str], input_path: Optional[str]) -> dict[str, Any]:
    task_payload: dict[str, Any] = {
        "question": task_text,
        "task_type": task_type,
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
    return {
        "run_dir": str(run_dir),
        "status": result.get("status", "unknown"),
        "task_type": result.get("task_type", "unknown"),
        "trace_id": result.get("trace_id"),
        "agent_plan": _summarize_plan(result.get("plan", {})),
        "total_latency_s": efficiency.get("total_latency_s"),
        "quality_control": result.get("quality_control", {}),
        "final_answer_preview": final_answer[:800],
    }


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
        "task_type": "open_workflow",
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
            _make_value_panel("Routing", _AUTO_TASK_TYPE_LABEL, style="bold cyan"),
            _make_value_panel("Latency", f"{summary['total_latency_s']:.2f} s" if summary.get("total_latency_s") is not None else "n/a", style="bold white"),
            _make_value_panel("QC", f"plan {qc_plan} | exec {qc_exec}", style="bold magenta" if "revise" in {qc_plan, qc_exec} else "bold green"),
        ]
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
    return {
        "keys": keys,
        "configured": bool(present),
        "present_keys": present,
    }


def _build_doctor_report() -> dict[str, Any]:
    selected_provider = os.getenv("LLM_PROVIDER", "qwen").strip().lower() or "qwen"
    providers = {name: _provider_status(name) for name in PROVIDER_KEY_MAP}
    configured_providers = [name for name, status in providers.items() if status["configured"]]
    warnings = []

    if ENV_FILE is None or not ENV_FILE.exists():
        warnings.append(f"no .env file found; run 'urban-agent init' or create {USER_ENV_FILE}")
    if not configured_providers:
        warnings.append("no provider API key detected in environment")
    if selected_provider not in providers:
        warnings.append(f"selected provider '{selected_provider}' is not in the documented provider list")
    elif not providers[selected_provider]["configured"]:
        warnings.append(f"selected provider '{selected_provider}' has no detected API key")

    return {
        "project_root": str(PROJECT_ROOT),
        "cwd": str(Path.cwd()),
        "config": {
            "user_config_dir": str(USER_CONFIG_DIR),
            "user_env_file": str(USER_ENV_FILE),
            "active_env_file": str(ENV_FILE) if ENV_FILE else None,
            "env_candidates": [str(item) for item in _env_candidates()],
        },
        "python": {
            "version": platform.python_version(),
            "executable": sys.executable,
        },
        "environment": {
            ".env_exists": bool(ENV_FILE and ENV_FILE.exists()),
            ".env_example_exists": ENV_TEMPLATE_FILE.exists(),
            "selected_provider": selected_provider,
            "configured_providers": configured_providers,
            "providers": providers,
        },
        "paths": {
            "default_runs_dir": str(DEFAULT_RUNS_DIR),
        },
        "warnings": warnings,
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
                ("Working dir", _truncate_middle(report["cwd"])),
                ("Config file", _truncate_middle(report["config"]["active_env_file"] or "not found")),
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
    print(f"Working directory    {report['cwd']}")
    print(f"Config file          {report['config']['active_env_file'] or 'not found'}")
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
    task_type: Optional[str],
    bbox: Optional[str],
    input_path: Optional[str],
    output_dir: str,
    interaction_mode: str,
    run_name: Optional[str] = None,
    show_progress: bool = False,
) -> dict[str, Any]:
    from .agents.orchestrator import MultiAgentOrchestrator
    from .core import PerceptionModule, ReasoningModule
    from .runtime_observatory import ObservableUrbanRunner, RunArtifactStore, resolve_local_case

    resolved_task_type = _resolve_task_type(task_text, task_type, input_path)
    task_payload = _build_task_payload(task_text, resolved_task_type, bbox, input_path)
    local_case = resolve_local_case({"task": task_text, "location": task_payload.get("location", "")})
    if local_case is not None:
        request = {
            "task": task_text,
            "location": local_case.location,
            "radius": 600,
            "mode": interaction_mode,
            "case_id": "ningbo_old_bund",
            "run_name": run_name or "ningbo-old-bund-observable",
        }
        store = RunArtifactStore(Path(output_dir))
        runner = ObservableUrbanRunner(store)
        completed_run_id = None
        if show_progress:
            print("[plan] observable UrbanAgent runtime: PlannerAgent -> ManagerAgent -> Workers -> ReviewHub -> QualityController -> ReporterWorker")
        async for frame in runner.run(request):
            if frame.get("type") == "event":
                event = frame.get("event", {})
                payload = event.get("payload", {})
                if show_progress and event.get("type") == "agent_started":
                    print(f"[agent] {_agent_display_name(str(payload.get('agent', 'unknown')))} running")
                if show_progress and event.get("type") == "artifact_created":
                    artifact = payload.get("artifact", {})
                    print(f"[artifact] {artifact.get('title', artifact.get('id', 'artifact'))}")
                if event.get("type") == "run_completed":
                    completed_run_id = event.get("run_id")
            elif frame.get("type") == "complete":
                completed_run_id = frame.get("run_id")
        if completed_run_id is None:
            raise RuntimeError("Observable run did not produce a run id")
        manifest = store.read_manifest(completed_run_id)
        run_dir = Path(output_dir) / completed_run_id
        events = store.read_events(completed_run_id)
        summary = _build_observable_summary(run_dir, manifest, events)
        _write_json(summary, run_dir / "summary.json")
        return {"run_dir": run_dir, "result": manifest, "summary": summary}

    run_dir = _create_run_dir(Path(output_dir), run_name or task_text)

    request_record = {
        "timestamp": datetime.now().isoformat(),
        "task_type": resolved_task_type,
        "task": task_text,
        "bbox": bbox,
        "input_path": input_path,
        "interaction_mode": interaction_mode,
        "task_payload": task_payload,
    }
    _write_json(request_record, run_dir / "request.json")

    if show_progress:
        if _rich_ui_enabled():
            _CONSOLE.print("[bold cyan]PLAN[/] preparing multi-agent runtime")
        else:
            print("[plan] preparing multi-agent runtime")
    llm_client = _build_llm_client()
    vlm_client = llm_client if hasattr(llm_client, "analyze_image") else None
    perception_module = PerceptionModule(llm_client=llm_client, vlm_client=vlm_client)
    reasoning_module = ReasoningModule(llm_client=llm_client)

    orchestrator = MultiAgentOrchestrator(
        llm_client=llm_client,
        vlm_client=vlm_client,
        interaction_mode=interaction_mode,
        perception_module=perception_module,
        reasoning_module=reasoning_module,
    )
    if show_progress:
        if _rich_ui_enabled():
            _CONSOLE.print("[bold green]EXEC[/] planner -> workers -> reviewer")
        else:
            print("[execute] planner -> workers -> reviewer")
    result = await orchestrator.run(task_payload, task_type=resolved_task_type)
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


async def _preview_plan(task_text: str, task_type: Optional[str], bbox: Optional[str], input_path: Optional[str]) -> dict[str, Any]:
    from .agents.base import AgentMessage, AgentRole
    from .agents.planner import PlannerAgent

    resolved_task_type = _resolve_task_type(task_text, task_type, input_path)
    task_payload = _build_task_payload(task_text, resolved_task_type, bbox, input_path)
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
                ("Task category", str(plan.get("task_category", "unknown"))),
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
        return

    _print_section("Multi-Agent Plan")
    print(f"Plan ID        {plan.get('plan_id', 'unknown')}")
    print(f"Task category  {plan.get('task_category', 'unknown')}")
    print(f"Complexity     {plan.get('complexity', 'unknown')}")
    print("\nAgent workflow")
    for item in _summarize_plan(plan):
        print(f"  {item['step']}. {item['agent']:<18} {item['objective']}")


class UrbanAgentShell:
    def __init__(self, args: argparse.Namespace):
        self.task_type_override = getattr(args, "task_type", None)
        self.bbox = args.bbox
        self.input_path = args.input
        self.output_dir = args.output_dir
        self.interaction_mode = args.interaction_mode

    def run(self) -> None:
        self._print_banner()
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
            if line.startswith("/"):
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
                        task_type=self.task_type_override,
                        bbox=self.bbox,
                        input_path=self.input_path,
                        output_dir=self.output_dir,
                        interaction_mode=self.interaction_mode,
                        show_progress=True,
                    )
                )
            except RuntimeError as error:
                print(f"Run failed: {error}")
                continue
            _print_run_report(report["summary"])

    def _print_banner(self) -> None:
        if _rich_ui_enabled():
            hero_text = Text()
            hero_text.append("UrbanAgent CLI\n", style="bold white")
            hero_text.append("Multi-agent urban analysis shell\n", style="dim")
            hero_text.append("Planning | Execution | Review | Quality", style="bold cyan")

            cards = [
                _make_value_panel("Provider", _selected_provider(), style="bold cyan"),
                _make_value_panel("Routing", _AUTO_TASK_TYPE_LABEL, style="bold white"),
                _make_value_panel("Mode", self.interaction_mode, style="bold magenta"),
                _make_value_panel("Runs", _output_dir_label(self.output_dir), style="bold green"),
            ]
            context = _make_key_value_panel(
                "Session",
                [
                    ("Runtime root", _truncate_middle(str(PROJECT_ROOT))),
                    ("Config file", _truncate_middle(str(ENV_FILE or "not found"))),
                    ("Input file", _truncate_middle(self.input_path or "none")),
                    ("BBox", self.bbox or "none"),
                ],
            )
            hint = _make_caption_panel(
                "Enter any city-analysis task. Routing is automatic.\nUse /plan, /status, /config, /doctor, or /help.",
                title="Quick Start",
            )
            _CONSOLE.print(Group(
                Panel(hero_text, border_style="cyan", box=box.ASCII, padding=(0, 1)),
                Columns(cards, equal=True, expand=True),
                context,
                hint,
            ))
            return

        print()
        print("UrbanAgent CLI")
        print("Multi-agent urban analysis shell")
        print("-" * 48)
        print(f"Runtime root  {PROJECT_ROOT}")
        print(f"Config file   {ENV_FILE or 'not found'}")
        print(f"Provider      {_selected_provider()}")
        print(f"Routing       {_AUTO_TASK_TYPE_LABEL}")
        print(f"Mode          {self.interaction_mode}")
        print("-" * 48)
        print("Enter any city-analysis task. Routing is automatic. Use /plan, /status, /doctor, or /help.")

    def _confirm_task(self, task_text: str) -> bool:
        if _rich_ui_enabled():
            panel = _make_key_value_panel(
                "Confirm Run",
                [
                    ("Routing", _AUTO_TASK_TYPE_LABEL),
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
        print(f"- routing: {_AUTO_TASK_TYPE_LABEL}")
        print(f"- mode: {self.interaction_mode}")
        print(f"- input: {self.input_path or 'none'}")
        print(f"- bbox: {self.bbox or 'none'}")
        print(f"- output dir: {self.output_dir}")
        print(f"- task: {task_text}")
        reply = input("Proceed? [y/N] ").strip().lower()
        return reply in {"y", "yes"}

    def _prompt(self) -> str:
        if _rich_ui_enabled():
            prompt = (
                f"[bold cyan]urban-agent[/]"
                f"[dim] ({self.interaction_mode})[/]"
                f" [bold white]>[/] "
            )
            return _CONSOLE.input(prompt)
        return input("urban-agent> ")

    def _handle_command(self, line: str) -> bool:
        parts = shlex.split(line)
        command = parts[0].lower()
        args = parts[1:]

        if command in {"/exit", "/quit"}:
            return True
        if command == "/help":
            self._print_help()
            return False
        if command == "/status":
            self._print_status()
            return False
        if command == "/doctor":
            _print_doctor_report(_build_doctor_report())
            return False
        if command == "/config":
            _cmd_config(argparse.Namespace(json=False))
            return False
        if command == "/plan":
            task_text = " ".join(args).strip()
            if not task_text:
                print("Usage: /plan <natural-language city-analysis task>")
                return False
            plan = asyncio.run(_preview_plan(task_text, self.task_type_override, self.bbox, self.input_path))
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
        print(f"Unknown command: {command}. Use /help.")
        return False

    def _print_help(self) -> None:
        if _rich_ui_enabled():
            table = Table(box=box.ASCII, expand=True)
            table.add_column("Command", style="bold cyan", no_wrap=True, width=20)
            table.add_column("Purpose", style="white")
            table.add_row("/plan <task>", "Preview planner decomposition and agent assignment")
            table.add_row("/status", "Show active shell state and runtime profile")
            table.add_row("/doctor", "Run environment and provider checks")
            table.add_row("/config", "Show active config locations and provider summary")
            table.add_row("/mode <mode>", "Switch guided, supervisory, or autonomous mode")
            table.add_row("/bbox <bbox|clear>", "Set or clear the default study-area bounding box")
            table.add_row("/input <path|clear>", "Attach or clear a default task input JSON file")
            table.add_row("/output <path>", "Change the run artifact output directory")
            table.add_row("/exit", "Exit the shell")
            _CONSOLE.print(Panel(table, title="Slash Commands", border_style="bright_black", box=box.ASCII, padding=(0, 1)))
            _CONSOLE.print(_make_caption_panel(
                "Direct task entry is the primary interaction path.\nRouting is inferred from the task text instead of being selected up front.",
                title="Interaction Model",
            ))
            return

        _print_section("Shell Commands")
        print("/plan <task>        Preview planner + worker assignment")
        print("/status             Show current shell state")
        print("/doctor             Run environment checks")
        print("/config             Show config file locations")
        print("/mode <mode>        Set shell mode")
        print("/bbox <bbox|clear>  Set or clear default bbox")
        print("/input <path|clear> Set or clear default input JSON")
        print("/output <path>      Set output directory")
        print("/exit               Exit shell")

    def _print_status(self) -> None:
        if _rich_ui_enabled():
            _CONSOLE.print(_make_key_value_panel(
                "Shell Status",
                [
                    ("Routing", _AUTO_TASK_TYPE_LABEL),
                    ("Mode", self.interaction_mode),
                    ("Provider", _selected_provider()),
                    ("BBox", self.bbox or "none"),
                    ("Input", _truncate_middle(self.input_path or "none")),
                    ("Output dir", _truncate_middle(self.output_dir)),
                    ("Config", _truncate_middle(str(ENV_FILE or "not found"))),
                ],
            ))
            return

        _print_section("Shell Status")
        print(f"routing     {_AUTO_TASK_TYPE_LABEL}")
        print(f"mode        {self.interaction_mode}")
        print(f"bbox        {self.bbox or 'none'}")
        print(f"input       {self.input_path or 'none'}")
        print(f"output dir  {self.output_dir}")
        print(f"config      {ENV_FILE or 'not found'}")


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
    from .cognition import SpatialCognition

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

    task = {"task_type": args.task_type, "question": args.question}
    module = ReasoningModule()
    result = await module.infer(input_data, {}, task)
    _write_json(result, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str)[:3000])


def _cmd_visualize(args):
    """执行可视化"""
    from .visualization import SpatialVisualizer

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
    from .visualization import SpatialVisualizer

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
    quality_score = max(0.0, 1.0 - len(issues) * 0.15)
    report = {
        "quality_score": quality_score,
        "passed": quality_score >= 0.6,
        "issues": issues,
        "recommendation": "accept" if quality_score >= 0.6 else "revise",
    }
    _write_json(report, args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2))


async def _cmd_run(args):
    """兼容旧入口，转发到新的 task-oriented runner。"""
    report = await _run_pipeline_task(
        task_text=args.question,
        task_type=args.task_type,
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
        task_type=args.task_type,
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
    report = _build_doctor_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    _print_doctor_report(report)


def _cmd_init(args):
    path = _write_default_user_config(args.from_env, force=args.force)
    if _rich_ui_enabled():
        _CONSOLE.print(_make_key_value_panel(
            "UrbanAgent Init",
            [
                ("User config", _truncate_middle(str(path))),
                ("Provider", _selected_provider()),
            ],
        ))
        _CONSOLE.print(_make_caption_panel("Edit this file to change provider, model, or API keys.", title="Next Step"))
        return
    _print_section("UrbanAgent Init")
    print(f"User config written to {path}")
    print("Edit this file to change provider, model, or API keys.")


def _cmd_config(args):
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
    print(f"Config dir  {report['config']['user_config_dir']}")
    print(f"Provider    {report['environment']['selected_provider']}")
    print(f"Configured  {', '.join(report['environment']['configured_providers']) if report['environment']['configured_providers'] else 'none'}")


def _cmd_shell(args):
    UrbanAgentShell(args).run()


def main(argv: Optional[Sequence[str]] = None) -> int:
    _load_project_env()
    _configure_cli_logging()
    parser = build_parser()
    raw_args = list(argv) if argv is not None else sys.argv[1:]

    if not raw_args:
        shell_args = argparse.Namespace(
            task_type=None,
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
        elif args.command == "config":
            _cmd_config(args)
        elif args.command == "shell":
            _cmd_shell(args)
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
