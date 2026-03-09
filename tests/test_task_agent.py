import asyncio

from urban_agent import UrbanTaskAgent


def test_task_agent_execute_unknown_task_without_external_services():
    agent = UrbanTaskAgent()

    result = asyncio.run(
        agent.execute_task(
            task={"data_type": "text", "text": "Analyze the spatial structure near the Bund."},
            task_type="unknown",
            city_data=None,
        )
    )

    assert result["status"] == "success"
    assert result["reasoning"]["task_type"] == "general"
    assert result["action"]["action_type"] == "general"