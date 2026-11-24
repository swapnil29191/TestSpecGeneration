"""Tests for sequential enterprise agent orchestration."""

from typing import Any

import pytest

from backend.app.integrations.enterprise_ai.errors import (
    EnterpriseAIConnectionError,
    EnterpriseAIRateLimitError,
)
from backend.app.integrations.enterprise_ai.models import AgentInvocationResponse
from backend.app.orchestration.execution_context import ExecutionContext
from backend.app.orchestration.workflow_config import TEST_SPECIFICATION_WORKFLOW
from backend.app.orchestration.workflow_engine import WorkflowEngine


# historical_context_agent is intentionally omitted: optional, skipped when unconfigured.
AGENT_IDS = {
    "requirement_clarifier": "agent-clarifier",
    "requirement_analyzer": "agent-1",
    "feature_analyzer": "agent-2",
    "testspec_generator": "agent-3",
    "testspec_reviewer": "agent-4",
}

CLARIFIER_CLEAR = '{"status": "clear", "open_questions": [], "resolved_from_history": []}'
CLARIFIER_NEEDS_INPUT = (
    '{"status": "needs_clarification", '
    '"resolved_from_history": ["Braking torque range confirmed from PNG-12."], '
    '"open_questions": ["What is the expected response time under low voltage?"]}'
)


class FakeAgentClient:
    def __init__(
        self,
        fail_at: int | None = None,
        failure: Exception | None = None,
        responses: dict[str, str] | None = None,
    ) -> None:
        self.fail_at = fail_at
        self.failure = failure or EnterpriseAIConnectionError("Simulated connection failure.")
        self.responses = responses or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def invoke_agent(
        self, agent_id: str, input_data: dict[str, Any]
    ) -> AgentInvocationResponse:
        self.calls.append((agent_id, input_data))
        call_number = len(self.calls)
        if call_number == self.fail_at:
            raise self.failure
        if agent_id in self.responses:
            return AgentInvocationResponse(agent_id=agent_id, content=self.responses[agent_id])
        return AgentInvocationResponse(
            agent_id=agent_id,
            content=f"output-{call_number}",
        )


@pytest.mark.asyncio
async def test_executes_all_agents_in_order_and_passes_prior_outputs() -> None:
    client = FakeAgentClient(responses={AGENT_IDS["requirement_clarifier"]: CLARIFIER_CLEAR})
    engine = WorkflowEngine(client, TEST_SPECIFICATION_WORKFLOW)  # type: ignore[arg-type]

    execution = await engine.execute_workflow("gateway", "REQ-1", AGENT_IDS)

    assert execution.status == "completed"
    assert [call[0] for call in client.calls] == [
        "agent-clarifier",
        "agent-1",
        "agent-2",
        "agent-3",
        "agent-4",
    ]
    assert execution.agent_executions[0].status == "skipped"  # historical context unconfigured
    assert client.calls[0][1]["requirements"] == "REQ-1"
    assert client.calls[0][1]["historical_context"] == ""
    assert client.calls[1][1]["requirement_clarification"] == CLARIFIER_CLEAR
    assert client.calls[1][1]["clarification_answers"] == ""
    assert client.calls[2][1]["requirement_analysis"] == "output-2"
    assert client.calls[3][1]["feature_analysis"] == "output-3"
    assert client.calls[4][1]["generated_testspec"] == "output-4"
    assert execution.final_reviewed_output == "output-5"


@pytest.mark.asyncio
async def test_optional_historical_context_agent_runs_when_configured() -> None:
    agent_ids = {**AGENT_IDS, "historical_context_agent": "agent-history"}
    client = FakeAgentClient(
        responses={
            AGENT_IDS["requirement_clarifier"]: CLARIFIER_CLEAR,
            "agent-history": "Prior PNG project resolved a similar braking ambiguity.",
        }
    )
    engine = WorkflowEngine(client, TEST_SPECIFICATION_WORKFLOW)  # type: ignore[arg-type]

    execution = await engine.execute_workflow("png", "REQ-9", agent_ids)

    assert execution.status == "completed"
    assert execution.agent_executions[0].status == "completed"
    assert client.calls[0][0] == "agent-history"
    assert (
        client.calls[1][1]["historical_context"]
        == "Prior PNG project resolved a similar braking ambiguity."
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_stage", [1, 2, 3, 4, 5])
async def test_workflow_stops_after_mandatory_agent_failure(failure_stage: int) -> None:
    client = FakeAgentClient(
        fail_at=failure_stage,
        responses={AGENT_IDS["requirement_clarifier"]: CLARIFIER_CLEAR},
    )
    engine = WorkflowEngine(client, TEST_SPECIFICATION_WORKFLOW)  # type: ignore[arg-type]

    execution = await engine.execute_workflow("zonal", "REQ-2", AGENT_IDS)

    assert execution.status == "failed"
    assert len(client.calls) == failure_stage
    assert execution.agent_executions[failure_stage].status == "failed"
    assert all(
        record.status == "skipped"
        for record in execution.agent_executions[failure_stage + 1 :]
    )
    assert execution.summary.skipped_agents == 1 + (5 - failure_stage)


@pytest.mark.asyncio
async def test_rate_limit_error_stops_workflow_with_rate_limit_code() -> None:
    client = FakeAgentClient(
        fail_at=2,
        failure=EnterpriseAIRateLimitError("Simulated rate limit."),
        responses={AGENT_IDS["requirement_clarifier"]: CLARIFIER_CLEAR},
    )
    engine = WorkflowEngine(client, TEST_SPECIFICATION_WORKFLOW)  # type: ignore[arg-type]

    execution = await engine.execute_workflow("gateway", "REQ-4", AGENT_IDS)

    assert execution.status == "failed"
    assert execution.error is not None
    assert execution.error.code == "enterprise_ai_rate_limit_error"
    assert execution.agent_executions[2].status == "failed"


@pytest.mark.asyncio
async def test_unexpected_exception_is_reported_as_unexpected_agent_error() -> None:
    client = FakeAgentClient(
        fail_at=3,
        failure=RuntimeError("boom"),
        responses={AGENT_IDS["requirement_clarifier"]: CLARIFIER_CLEAR},
    )
    engine = WorkflowEngine(client, TEST_SPECIFICATION_WORKFLOW)  # type: ignore[arg-type]

    execution = await engine.execute_workflow("gateway", "REQ-5", AGENT_IDS)

    assert execution.status == "failed"
    assert execution.error is not None
    assert execution.error.code == "unexpected_agent_error"


@pytest.mark.asyncio
async def test_clarifier_unparseable_response_fails_workflow() -> None:
    client = FakeAgentClient(responses={AGENT_IDS["requirement_clarifier"]: "not json"})
    engine = WorkflowEngine(client, TEST_SPECIFICATION_WORKFLOW)  # type: ignore[arg-type]

    execution = await engine.execute_workflow("gateway", "REQ-6", AGENT_IDS)

    assert execution.status == "failed"
    assert execution.error is not None
    assert execution.error.code == "unexpected_agent_response"
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_clarifier_pauses_workflow_when_open_questions_remain() -> None:
    client = FakeAgentClient(responses={AGENT_IDS["requirement_clarifier"]: CLARIFIER_NEEDS_INPUT})
    engine = WorkflowEngine(client, TEST_SPECIFICATION_WORKFLOW)  # type: ignore[arg-type]

    execution = await engine.execute_workflow("gateway", "REQ-7", AGENT_IDS)

    assert execution.status == "awaiting_clarification"
    assert execution.open_questions == [
        "What is the expected response time under low voltage?"
    ]
    assert execution.resolved_from_history == [
        "Braking torque range confirmed from PNG-12."
    ]
    assert len(client.calls) == 1
    assert execution.agent_executions[2].status == "pending"


@pytest.mark.asyncio
async def test_resume_workflow_continues_after_clarification_answers() -> None:
    client = FakeAgentClient(responses={AGENT_IDS["requirement_clarifier"]: CLARIFIER_NEEDS_INPUT})
    engine = WorkflowEngine(client, TEST_SPECIFICATION_WORKFLOW)  # type: ignore[arg-type]
    execution = await engine.execute_workflow("gateway", "REQ-8", AGENT_IDS)
    assert execution.status == "awaiting_clarification"

    context = ExecutionContext.from_execution(execution)
    context.apply_clarification_answers(
        {"What is the expected response time under low voltage?": "200 ms maximum."}
    )
    resumed = await engine.run(context, AGENT_IDS)

    assert resumed.status == "completed"
    assert len(client.calls) == 5
    requirement_analyzer_call = client.calls[1]
    assert requirement_analyzer_call[0] == AGENT_IDS["requirement_analyzer"]
    assert "200 ms maximum." in requirement_analyzer_call[1]["clarification_answers"]


@pytest.mark.asyncio
async def test_workflow_rejects_missing_agent_role() -> None:
    engine = WorkflowEngine(FakeAgentClient(), TEST_SPECIFICATION_WORKFLOW)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="testspec_reviewer"):
        await engine.execute_workflow(
            "png",
            "REQ-3",
            {key: value for key, value in AGENT_IDS.items() if key != "testspec_reviewer"},
        )

