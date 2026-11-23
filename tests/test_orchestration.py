"""Tests for sequential enterprise agent orchestration."""

from typing import Any

import pytest

from backend.app.integrations.enterprise_ai.errors import EnterpriseAIConnectionError
from backend.app.integrations.enterprise_ai.models import AgentInvocationResponse
from backend.app.orchestration.workflow_config import TEST_SPECIFICATION_WORKFLOW
from backend.app.orchestration.workflow_engine import WorkflowEngine


AGENT_IDS = {
    "requirement_analyzer": "agent-1",
    "feature_analyzer": "agent-2",
    "testspec_generator": "agent-3",
    "testspec_reviewer": "agent-4",
}


class FakeAgentClient:
    def __init__(self, fail_at: int | None = None) -> None:
        self.fail_at = fail_at
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def invoke_agent(
        self, agent_id: str, input_data: dict[str, Any]
    ) -> AgentInvocationResponse:
        self.calls.append((agent_id, input_data))
        call_number = len(self.calls)
        if call_number == self.fail_at:
            raise EnterpriseAIConnectionError("Simulated connection failure.")
        return AgentInvocationResponse(
            agent_id=agent_id,
            content=f"output-{call_number}",
        )


@pytest.mark.asyncio
async def test_executes_all_agents_in_order_and_passes_prior_outputs() -> None:
    client = FakeAgentClient()
    engine = WorkflowEngine(client, TEST_SPECIFICATION_WORKFLOW)  # type: ignore[arg-type]

    execution = await engine.execute_workflow("gateway", "REQ-1", AGENT_IDS)

    assert execution.status == "completed"
    assert [call[0] for call in client.calls] == [
        "agent-1",
        "agent-2",
        "agent-3",
        "agent-4",
    ]
    assert client.calls[0][1]["requirements"] == "REQ-1"
    assert client.calls[1][1]["requirement_analysis"] == "output-1"
    assert client.calls[2][1]["feature_analysis"] == "output-2"
    assert client.calls[3][1]["generated_testspec"] == "output-3"
    assert execution.final_reviewed_output == "output-4"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_stage", [1, 2, 3])
async def test_workflow_stops_after_mandatory_agent_failure(failure_stage: int) -> None:
    client = FakeAgentClient(fail_at=failure_stage)
    engine = WorkflowEngine(client, TEST_SPECIFICATION_WORKFLOW)  # type: ignore[arg-type]

    execution = await engine.execute_workflow("zonal", "REQ-2", AGENT_IDS)

    assert execution.status == "failed"
    assert len(client.calls) == failure_stage
    assert execution.agent_executions[failure_stage - 1].status == "failed"
    assert all(
        record.status == "skipped"
        for record in execution.agent_executions[failure_stage:]
    )
    assert execution.summary.skipped_agents == 4 - failure_stage


@pytest.mark.asyncio
async def test_workflow_rejects_missing_agent_role() -> None:
    engine = WorkflowEngine(FakeAgentClient(), TEST_SPECIFICATION_WORKFLOW)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="testspec_reviewer"):
        await engine.execute_workflow(
            "adas",
            "REQ-3",
            {key: value for key, value in AGENT_IDS.items() if key != "testspec_reviewer"},
        )
