from pathlib import Path
import asyncio
import json

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
    assert not hasattr(args, "task_type")


def test_parser_supports_plan_command():
    parser = cli.build_parser()

    args = parser.parse_args(["plan", "--task", "inspect the district", "--output", "plan.json"])

    assert args.command == "plan"
    assert args.task == "inspect the district"
    assert args.output == "plan.json"


def test_analyze_help_does_not_expose_task_type(capsys):
    parser = cli.build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["analyze", "--help"])

    help_text = capsys.readouterr().out
    assert "--task-type" not in help_text


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
    assert "plan" in help_text
    assert "capabilities" in help_text
    assert "shell" in help_text
    assert "case" not in help_text


def test_capability_report_supports_progressive_disclosure():
    report = cli._build_capability_report("building density morphology", level=2, limit=4)
    names = [item["name"] for item in report["items"]]

    assert "urban_density_morphology" in names
    capability = next(item for item in report["items"] if item["name"] == "urban_density_morphology")
    assert capability["invocation"]["python_function"].endswith("compute_built_form_metrics")


def test_shell_help_hides_task_type_option(capsys):
    parser = cli.build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["shell", "--help"])

    help_text = capsys.readouterr().out
    assert "--task-type" not in help_text


def test_shell_command_registry_supports_hermes_style_aliases():
    assert cli._resolve_shell_command("/help").name == "commands"
    assert cli._resolve_shell_command("/tools").name == "capabilities"
    assert cli._resolve_shell_command("/reset").name == "new"
    assert "/runtime" in cli._shell_command_words()


def test_shell_slash_command_detection_does_not_hijack_absolute_paths():
    assert cli._looks_like_shell_command("/status") is True
    assert cli._looks_like_shell_command("/commands") is True
    assert cli._looks_like_shell_command("/Users/me/aoi.geojson please inspect") is False


def test_runtime_status_formatter_reports_checkpoint_counts():
    summary = cli._format_runtime_status({
        "todo_completed": 2,
        "todo_total": 3,
        "checkpoint_count": 4,
        "blocked_count": 1,
    })

    assert "2/3 todos" in summary
    assert "4 checkpoints" in summary
    assert "1 blocked" in summary


def test_build_llm_client_requires_provider_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "qwen")
    for key in ("QWEN_API_KEY", "OPENAI_API_KEY", "Deepseek_API_KEY", "DEEPSEEK_API_KEY", "KIMI_API_KEY", "KIMI_CODE_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(RuntimeError, match="No API key detected"):
        cli._build_llm_client()


def test_build_llm_client_prefers_kimi_coding(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "kimi")
    monkeypatch.setenv("KIMI_CLIENT_TYPE", "auto")
    monkeypatch.setenv("KIMI_CODE_API_KEY", "dummy-code-key")
    monkeypatch.delenv("KIMI_API_KEY", raising=False)

    client = cli._build_llm_client()

    assert client.client_type == "coding"


def test_build_llm_client_can_force_kimi_standard(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "kimi")
    monkeypatch.setenv("KIMI_CLIENT_TYPE", "standard")
    monkeypatch.setenv("KIMI_API_KEY", "dummy-standard-key")
    monkeypatch.setenv("KIMI_CODE_API_KEY", "dummy-code-key")

    client = cli._build_llm_client()

    assert client.client_type == "standard"


def test_build_llm_client_wraps_kimi_auto_fallback(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "kimi")
    monkeypatch.setenv("KIMI_CLIENT_TYPE", "auto")
    monkeypatch.setenv("KIMI_CODE_API_KEY", "dummy-code-key")
    monkeypatch.setenv("KIMI_API_KEY", "dummy-standard-key")

    client = cli._build_llm_client()

    assert client.client_type == "coding"
    assert client.fallback_client_type == "standard"


def test_planner_keeps_task_context_for_all_subtasks():
    planner = PlannerAgent()
    message = AgentMessage(
        sender=AgentRole.MANAGER,
        receiver=AgentRole.PLANNER,
        msg_type="plan",
        payload={
            "question": "What is the capital of France?",
        },
        trace_id="trace_test",
    )

    result = asyncio.run(planner.execute(message))
    subtasks = result.payload["execution_plan"]["subtasks"]

    assert subtasks
    assert all(item["input_data"].get("question") == "What is the capital of France?" for item in subtasks)
    assert result.payload["execution_plan"]["workflow_profile"] == "adaptive_urban_analysis"
    assert result.payload["execution_plan"]["capability_context"]["disclosure_policy"] == "progressive"


def test_planner_injects_generic_feedback_lessons_for_spatial_validation():
    planner = PlannerAgent()
    message = AgentMessage(
        sender=AgentRole.MANAGER,
        receiver=AgentRole.PLANNER,
        msg_type="plan",
        payload={
            "question": "Validate an AOI boundary GeoJSON against cached layers, then export GIS overlay layers for review.",
        },
        trace_id="trace_feedback",
    )

    result = asyncio.run(planner.execute(message))
    lessons = result.payload["execution_plan"]["feedback_context"]["lessons"]
    lesson_ids = {lesson["lesson_id"] for lesson in lessons}

    assert "source_authority_before_cache" in lesson_ids
    assert "layered_gis_for_spatial_audit" in lesson_ids


def test_manager_restores_subtask_input_data():
    subtasks = ManagerAgent._parse_subtasks({
        "subtasks": [
            {
                "subtask_id": "st0",
                "objective": "answer question",
                "assigned_role": "analyst",
                "input_data": {"question": "What is the capital of France?"},
                "dependencies": [],
                "expected_output": "answer",
            }
        ]
    })

    assert subtasks[0].input_data["question"] == "What is the capital of France?"


def test_preview_plan_shows_multi_agent_roles_for_city_analysis(monkeypatch):
    monkeypatch.delenv("URBAN_AGENT_PLAN_LIVE", raising=False)

    plan = asyncio.run(cli._preview_plan(
        "分析宁波老外滩滨水街区的步行可达性、开放空间短板，并提出可视化输出建议",
        None,
        None,
    ))
    roles = [item["assigned_role"] for item in plan["subtasks"]]

    assert "perception" in roles
    assert "analyst" in roles
    assert "cartographer" in roles
    assert "reporter" in roles


def test_preview_plan_selects_multiple_method_capabilities(monkeypatch):
    monkeypatch.delenv("URBAN_AGENT_PLAN_LIVE", raising=False)

    plan = asyncio.run(cli._preview_plan(
        "分析老城区建筑密度、功能混合、街景一致性，并导出GIS图层栈",
        None,
        None,
    ))
    selected = plan["capability_context"]["selected_names"]

    assert plan["complexity"] in {"basic", "advanced"}
    assert "urban_density_morphology" in selected
    assert "function_mix_entropy" in selected
    assert "streetview_visual_consistency" in selected
    assert "gis_layer_stack_export" in selected


def test_preview_plan_respects_generic_stage_ladder(monkeypatch, tmp_path):
    monkeypatch.delenv("URBAN_AGENT_PLAN_LIVE", raising=False)
    task_input = tmp_path / "staged_metric_task.json"
    task_input.write_text(json.dumps({
        "stage": "single_district_single_indicator",
        "data_resources": {
            "predicted_building_function_poi": "machine-learning-predicted building function POI dataset",
            "osm_or_osm_cache": "OSM 道路和建筑轮廓数据",
        },
    }, ensure_ascii=False), encoding="utf-8")

    plan = asyncio.run(cli._preview_plan(
        "Use the declared raw data to construct one built-environment indicator for one district before scaling up.",
        None,
        str(task_input),
    ))
    selected = plan["capability_context"]["selected_names"]

    assert plan["complexity"] == "basic"
    assert len(plan["subtasks"]) == 4
    assert "urban_ml_modeling" not in selected


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