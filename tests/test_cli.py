from pathlib import Path
import asyncio

import pytest

from urban_agent import cli
from urban_agent.agents.base import AgentMessage, AgentRole
from urban_agent.agents.manager import ManagerAgent
from urban_agent.agents.orchestrator import MultiAgentOrchestrator
from urban_agent.agents.planner import PlannerAgent


def test_parser_supports_task_oriented_analyze_command():
    parser = cli.build_parser()

    args = parser.parse_args(["analyze", "--task", "inspect the district"])

    assert args.command == "analyze"
    assert args.task == "inspect the district"
    assert args.task_type is None


def test_auto_task_routing_infers_open_ended_urban_exploration():
    inferred = cli._resolve_task_type(
        "Compare the street network and public-space accessibility of two historic districts and suggest map layers for a planning brief",
        None,
        None,
    )

    assert inferred == "urban_exploration"


def test_create_run_dir_slugifies_label(tmp_path: Path):
    run_dir = cli._create_run_dir(tmp_path, "My Test Run")

    assert run_dir.exists()
    assert "my-test-run" in run_dir.name


def test_doctor_report_detects_configured_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "qwen")
    monkeypatch.setenv("QWEN_API_KEY", "dummy-key")

    report = cli._build_doctor_report()

    assert report["environment"]["selected_provider"] == "qwen"
    assert "qwen" in report["environment"]["configured_providers"]
    assert "active_env_file" in report["config"]
    assert "user_env_file" in report["config"]
    assert "default_runs_dir" in report["paths"]
    assert "case_script_exists" not in report["paths"]


def test_case_command_is_explicitly_source_only(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(cli, "PROJECT_ROOT", tmp_path)

    try:
        cli._load_workflow_case_module()
    except FileNotFoundError as error:
        message = str(error)
    else:
        raise AssertionError("expected FileNotFoundError for missing source-only case module")

    assert "source-only demo command" in message
    assert "urban-agent analyze" in message


def test_public_help_hides_source_only_case_command():
    help_text = cli.build_parser().format_help()

    assert "analyze" in help_text
    assert "doctor" in help_text
    assert "init" in help_text
    assert "config" in help_text
    assert "shell" in help_text
    assert "case" not in help_text


def test_shell_help_hides_task_type_option(capsys):
    parser = cli.build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["shell", "--help"])

    help_text = capsys.readouterr().out
    assert "--task-type" not in help_text


def test_build_llm_client_requires_provider_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "qwen")
    for key in ("QWEN_API_KEY", "OPENAI_API_KEY", "Deepseek_API_KEY", "DEEPSEEK_API_KEY", "KIMI_API_KEY", "KIMI_CODE_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(RuntimeError, match="No API key detected"):
        cli._build_llm_client()


def test_planner_keeps_task_context_for_all_subtasks():
    planner = PlannerAgent()
    message = AgentMessage(
        sender=AgentRole.MANAGER,
        receiver=AgentRole.PLANNER,
        msg_type="plan",
        payload={
            "task_type": "geoqa",
            "question": "What is the capital of France?",
        },
        trace_id="trace_test",
    )

    result = asyncio.run(planner.execute(message))
    subtasks = result.payload["execution_plan"]["subtasks"]

    assert subtasks
    assert all(item["input_data"].get("task_type") == "geoqa" for item in subtasks)


def test_manager_restores_subtask_input_data():
    subtasks = ManagerAgent._parse_subtasks({
        "subtasks": [
            {
                "subtask_id": "st0",
                "objective": "answer question",
                "assigned_role": "analyst",
                "input_data": {"task_type": "geoqa", "question": "What is the capital of France?"},
                "dependencies": [],
                "expected_output": "answer",
            }
        ]
    })

    assert subtasks[0].input_data["task_type"] == "geoqa"


def test_preview_plan_shows_multi_agent_roles_for_city_analysis(monkeypatch):
    monkeypatch.delenv("URBAN_AGENT_PLAN_LIVE", raising=False)

    plan = asyncio.run(cli._preview_plan(
        "分析宁波老外滩滨水街区的步行可达性、开放空间短板，并提出可视化输出建议",
        "geoqa",
        None,
        None,
    ))
    roles = [item["assigned_role"] for item in plan["subtasks"]]

    assert "perception" in roles
    assert "analyst" in roles
    assert "cartographer" in roles
    assert "reporter" in roles


def test_planner_does_not_treat_dataset_mentions_as_perception():
    role = PlannerAgent._assign_role(
        "Retrieve the capital city of France using a geographic knowledge base or administrative dataset."
    )

    assert role == AgentRole.ANALYST


def test_extract_answer_prefers_explicit_answer_over_later_validation_payload():
    results = {
        "subtask_results": {
            "st0": {
                "role": "analyst",
                "status": "completed",
                "result": {"answer": "Paris"},
            },
            "st1": {
                "role": "perception",
                "status": "completed",
                "result": {"type": "unknown", "content": {}},
            },
        }
    }

    assert MultiAgentOrchestrator._extract_answer(results) == "Paris"


def test_extract_answer_ignores_unanswered_structured_payload():
    results = {
        "subtask_results": {
            "st0": {
                "role": "perception",
                "status": "completed",
                "result": {"type": "unknown", "content": {}},
            }
        }
    }

    assert MultiAgentOrchestrator._extract_answer(results) == ""


def test_write_default_user_config_from_existing_env(monkeypatch, tmp_path: Path):
    source = tmp_path / "source.env"
    target_dir = tmp_path / "config"
    target = target_dir / ".env"
    source.write_text("LLM_PROVIDER=qwen\nQWEN_API_KEY=dummy\n", encoding="utf-8")

    monkeypatch.setattr(cli, "USER_CONFIG_DIR", target_dir)
    monkeypatch.setattr(cli, "USER_ENV_FILE", target)

    result = cli._write_default_user_config(str(source), force=True)

    assert result == target
    assert "QWEN_API_KEY=dummy" in target.read_text(encoding="utf-8")