import urban_agent


def test_public_api_exports_versioned_symbols():
    assert hasattr(urban_agent, "__version__")
    assert hasattr(urban_agent, "UrbanAgent")
    assert hasattr(urban_agent, "UrbanTaskAgent")
    assert hasattr(urban_agent, "AsyncUrbanAgent")
    assert urban_agent.AsyncUrbanAgent is urban_agent.UrbanTaskAgent


def test_legacy_agent_alias_is_stable():
    assert urban_agent.LegacyUrbanAgent is urban_agent.UrbanAgent