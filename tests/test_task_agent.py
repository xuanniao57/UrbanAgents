import asyncio

from urban_agent import UrbanTaskAgent


def test_task_agent_execute_unknown_task_without_external_services():
    agent = UrbanTaskAgent()

    result = asyncio.run(
        agent.execute_task(
            task={"data_type": "text", "text": "Analyze the spatial structure near the Bund."},
            workflow_profile="adaptive_urban_analysis",
            city_data=None,
        )
    )

    assert result["status"] == "success"
    assert result["workflow_profile"] == "adaptive_urban_analysis"
    assert result["reasoning"]["workflow_profile"] == "adaptive_urban_analysis"
    assert result["action"]["action_type"] == "general"