import json

from urban_agent.feedback_memory import FeedbackMemory, select_feedback_lessons
from urban_agent.memory_store import FileMemoryStore


def test_feedback_memory_selects_aoi_context_buffer_lesson():
    context = select_feedback_lessons("研究区域要居中，缓冲区是九倍面积，道路、建筑和POI按缓冲区加载")
    lesson_ids = [lesson["lesson_id"] for lesson in context["lessons"]]

    assert "aoi_centered_context_buffer" in lesson_ids
    assert any("3x" in lesson["summary"] and "9x" in lesson["summary"] for lesson in context["lessons"])


def test_feedback_memory_does_not_retrieve_experience_lessons(tmp_path):
    root = tmp_path / "memory"
    (root / "policy_memory" / "quality").mkdir(parents=True)
    (root / "experience_memory" / "runtime").mkdir(parents=True)
    (root / "policy_memory" / "quality" / "quality.json").write_text(json.dumps({
        "policy_id": "quality_policy",
        "summary": "Use traceable quality judgment for walkability.",
        "triggers": ["walkability"],
    }), encoding="utf-8")
    (root / "experience_memory" / "runtime" / "20260513.jsonl").write_text(json.dumps({
        "experience_id": "exp_walkability",
        "summary": "Runtime experience should be consumed by MemoryModule only.",
        "triggers": ["walkability"],
    }) + "\n", encoding="utf-8")

    context = FeedbackMemory(memory_store=FileMemoryStore(root)).select_for_task("walkability quality")
    lesson_ids = {lesson["lesson_id"] for lesson in context["lessons"]}

    assert "quality_policy" in lesson_ids
    assert "exp_walkability" not in lesson_ids
    assert all(lesson["memory_type"] in {"policy", "workflow"} for lesson in context["lessons"])