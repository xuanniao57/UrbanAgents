from urban_agent.feedback_memory import select_feedback_lessons


def test_feedback_memory_selects_aoi_context_buffer_lesson():
    context = select_feedback_lessons("研究区域要居中，缓冲区是九倍面积，道路、建筑和POI按缓冲区加载")
    lesson_ids = [lesson["lesson_id"] for lesson in context["lessons"]]

    assert "aoi_centered_context_buffer" in lesson_ids
    assert any("3x" in lesson["summary"] and "9x" in lesson["summary"] for lesson in context["lessons"])