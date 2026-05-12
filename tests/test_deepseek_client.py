from urban_agent.llm.deepseek_client import DeepSeekClient


def test_deepseek_v4_pro_thinking_kwargs(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy-key")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("DEEPSEEK_THINKING", "enabled")

    client = DeepSeekClient()
    kwargs = client._build_completion_kwargs(
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.2,
        max_tokens=128,
    )

    assert kwargs["model"] == "deepseek-v4-pro"
    assert kwargs["extra_body"] == {"thinking": {"type": "enabled"}}
    assert kwargs["reasoning_effort"] == "high"
    assert "temperature" not in kwargs


def test_deepseek_disabled_thinking_keeps_sampling(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy-key")
    monkeypatch.setenv("DEEPSEEK_THINKING", "disabled")

    client = DeepSeekClient()
    kwargs = client._build_completion_kwargs(
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.2,
        max_tokens=128,
    )

    assert kwargs["extra_body"] == {"thinking": {"type": "disabled"}}
    assert kwargs["temperature"] == 0.2
