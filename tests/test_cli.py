from pathlib import Path
import asyncio
import json

import pytest

from urban_agent import cli
from urban_agent.agents.base import AgentMessage, AgentRole
from urban_agent.agents.manager import ManagerAgent
from urban_agent.agents.orchestrator import MultiAgentOrchestrator
from urban_agent.agents.prompt_builder import UrbanAgentPromptBuilder
from urban_agent.agents.planner import PlannerAgent
from urban_agent.config_store import read_urban_config, set_config_value, write_default_config, write_urban_config
from urban_agent.constants import PACKAGE_ROOT, get_config_path, get_install_root, get_urban_home


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
    assert "setup" in help_text
    assert "update" in help_text
    assert "uninstall" in help_text
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
    config_target = target_dir / "config.yaml"
    source.write_text("LLM_PROVIDER=qwen\nQWEN_API_KEY=dummy\n", encoding="utf-8")

    monkeypatch.setattr(cli, "USER_CONFIG_DIR", target_dir)
    monkeypatch.setattr(cli, "USER_ENV_FILE", target)
    monkeypatch.setattr(cli, "USER_CONFIG_FILE", config_target)

    result = cli._write_default_user_config(str(source), force=True)

    assert result == target
    assert "QWEN_API_KEY=dummy" in target.read_text(encoding="utf-8")
    assert "model:" in config_target.read_text(encoding="utf-8")


def test_constants_respect_home_and_install_env(monkeypatch, tmp_path: Path):
    urban_home = tmp_path / "urban-home"
    install_root = tmp_path / "code"
    monkeypatch.setenv("URBAN_AGENT_HOME", str(urban_home))
    monkeypatch.setenv("URBAN_AGENT_INSTALL_DIR", str(install_root))

    assert get_urban_home() == urban_home.resolve()
    assert get_install_root() == install_root.resolve()
    assert get_config_path() == urban_home.resolve() / "config.yaml"


def test_default_urban_home_is_project_local_not_windows_profile(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("URBAN_AGENT_HOME", raising=False)
    monkeypatch.delenv("URBAN_AGENT_CONFIG_DIR", raising=False)
    monkeypatch.delenv("URBAN_AGENT_INSTALL_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))

    assert get_urban_home() == (tmp_path / ".urban-agent").resolve()
    assert get_install_root() == PACKAGE_ROOT.resolve()
    assert str(get_urban_home()).lower() != str(tmp_path / "localappdata" / "urban-agent").lower()


def test_config_yaml_supports_dotted_updates(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    write_default_config(config_path, force=True)
    config = read_urban_config(config_path)
    set_config_value(config, "model.default", "qwen-max")
    set_config_value(config, "runs.dir", str(tmp_path / "runs"))
    write_urban_config(config, config_path)

    updated = read_urban_config(config_path)

    assert updated["model"]["default"] == "qwen-max"
    assert updated["runs"]["dir"] == str(tmp_path / "runs")


def test_config_command_set_updates_config_yaml(monkeypatch, tmp_path: Path, capsys):
    config_path = tmp_path / "config.yaml"
    write_default_config(config_path, force=True)
    monkeypatch.setattr(cli, "USER_CONFIG_FILE", config_path)

    result = cli._cmd_config(type("Args", (), {"config_command": "set", "key": "model.default", "value": "qwen-plus-latest", "json": False})())

    assert result == 0
    assert read_urban_config(config_path)["model"]["default"] == "qwen-plus-latest"
    assert "model.default" in capsys.readouterr().out


def test_service_status_cleans_stale_pid(monkeypatch, tmp_path: Path, capsys):
    monkeypatch.setenv("URBAN_AGENT_HOME", str(tmp_path / "home"))
    pid_file = cli._service_pid_file()
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text("-1", encoding="utf-8")

    result = cli._cmd_service(type("Args", (), {"action": "status"})())

    assert result == 0
    assert "stopped" in capsys.readouterr().out
    assert not pid_file.exists()


def test_prompt_snapshot_hash_is_stable_for_same_session(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("URBAN_AGENT_HOME", str(tmp_path / "home"))
    (tmp_path / ".urbanagent.md").write_text("Use project-specific urban evidence rules.\n", encoding="utf-8")
    builder = UrbanAgentPromptBuilder(project_root=tmp_path, config={"model": {"provider": "qwen"}})

    first = builder.build(session_id="session-1", role_prompts={"planner": "Plan urban tasks."})
    (tmp_path / "dynamic_memory.json").write_text('{"new": "runtime recall"}', encoding="utf-8")
    second = builder.build(session_id="session-1", role_prompts={"planner": "Plan urban tasks."})

    assert first.prompt_hashes["planner"] == second.prompt_hashes["planner"]
    assert first.project_context_source and first.project_context_source.endswith(".urbanagent.md")
    assert first.tool_surfaces["planner"] == ["capability_index", "feedback_lessons", "project_context"]


def test_prompt_snapshot_reuses_same_session_and_refreshes_new_session(monkeypatch, tmp_path: Path):
    memory_root = tmp_path / "memory"
    policy_dir = memory_root / "policy_memory" / "quality"
    policy_dir.mkdir(parents=True)
    policy_file = policy_dir / "project_quality.json"
    policy_file.write_text(json.dumps({
        "policy_id": "project_quality",
        "summary": "Prefer municipal survey data v1.",
        "triggers": ["quality"],
        "scope": "project",
    }), encoding="utf-8")
    monkeypatch.setenv("URBAN_AGENT_MEMORY_ROOT", str(memory_root))
    monkeypatch.setenv("URBAN_AGENT_HOME", str(tmp_path / "home"))

    snapshot_path = tmp_path / "sessions" / "session-a" / "prompt_snapshot.json"
    config = {
        "session_id": "session-a",
        "prompt_snapshot_path": str(snapshot_path),
        "project_root": str(tmp_path),
        "memory": {"persistent": False},
    }
    first = MultiAgentOrchestrator(config=config, enable_memory=False, enable_quality_control=False)
    first_hash = first.prompt_snapshot.prompt_hashes["planner"]

    policy_file.write_text(json.dumps({
        "policy_id": "project_quality",
        "summary": "Prefer municipal survey data v2.",
        "triggers": ["quality"],
        "scope": "project",
    }), encoding="utf-8")
    second = MultiAgentOrchestrator(config=config, enable_memory=False, enable_quality_control=False)

    assert second.prompt_snapshot.prompt_hashes["planner"] == first_hash
    assert "Prefer municipal survey data v1" in second.prompt_snapshot.system_prompts["planner"]
    assert "Prefer municipal survey data v2" not in second.prompt_snapshot.system_prompts["planner"]

    new_session = MultiAgentOrchestrator(
        config={**config, "session_id": "session-b", "prompt_snapshot_path": str(tmp_path / "sessions" / "session-b" / "prompt_snapshot.json")},
        enable_memory=False,
        enable_quality_control=False,
    )

    assert new_session.prompt_snapshot.prompt_hashes["planner"] != first_hash
    assert "Prefer municipal survey data v2" in new_session.prompt_snapshot.system_prompts["planner"]


def test_memory_write_does_not_mutate_existing_session_prompt(monkeypatch, tmp_path: Path):
    from urban_agent.memory_store import FileMemoryStore

    memory_root = tmp_path / "memory"
    monkeypatch.setenv("URBAN_AGENT_MEMORY_ROOT", str(memory_root))
    monkeypatch.setenv("URBAN_AGENT_HOME", str(tmp_path / "home"))
    snapshot_path = tmp_path / "sessions" / "stable" / "prompt_snapshot.json"
    config = {
        "session_id": "stable",
        "prompt_snapshot_path": str(snapshot_path),
        "project_root": str(tmp_path),
        "memory": {"persistent": False},
    }

    first = MultiAgentOrchestrator(config=config, enable_memory=False, enable_quality_control=False)
    first_hash = first.prompt_snapshot.prompt_hashes["planner"]
    FileMemoryStore(memory_root).append_experience({"summary": "New runtime experience", "triggers": ["walkability"]})
    second = MultiAgentOrchestrator(config=config, enable_memory=False, enable_quality_control=False)

    assert second.prompt_snapshot.prompt_hashes["planner"] == first_hash


def test_role_tool_surfaces_are_isolated():
    builder = UrbanAgentPromptBuilder(
        config={"model": {"provider": "qwen"}},
        stable_policy_snapshot={"project_policy": {"summary": "Use traceable evidence."}},
    )
    snapshot = builder.build(session_id="roles", role_prompts={
        "planner": "Plan tasks.",
        "reporter": "Report results.",
        "spatial_reviewer": "Review spatial evidence.",
    })

    assert "feedback_lessons" in snapshot.tool_surfaces["planner"]
    assert "geojson_export" not in snapshot.tool_surfaces["planner"]
    assert "artifact_manifest" in snapshot.tool_surfaces["reporter"]
    assert "capability_invocation" not in snapshot.tool_surfaces["reporter"]
    assert "spatial_validation" in snapshot.tool_surfaces["spatial_reviewer"]
