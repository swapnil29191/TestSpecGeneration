"""Integration-style mocked tests for Phase 2 API endpoints."""

from collections.abc import Iterator
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.app.integrations.enterprise_ai.client import OpenAICompatibleAgentTransport
from backend.app.integrations.enterprise_ai.errors import (
    EnterpriseAIConnectionError,
    EnterpriseAIRateLimitError,
)
from backend.app.integrations.enterprise_ai.models import AgentInvocationResponse
from backend.app.main import create_app

CLARIFIER_NEEDS_INPUT = (
    '{"status": "needs_clarification", '
    '"resolved_from_history": [], '
    '"open_questions": ["What is the expected response time under low voltage?"]}'
)
_TERMINAL_STATUSES = {"completed", "failed", "awaiting_clarification"}


def poll_until_terminal(
    client: TestClient, execution_id: str, timeout: float = 5.0
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    payload: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/workflow/executions/{execution_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] in _TERMINAL_STATUSES:
            return payload
        time.sleep(0.02)
    raise AssertionError(f"Execution did not reach a terminal state in time: {payload}")


@pytest.fixture
def configured_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ENTERPRISE_AI_BASE_URL", "https://enterprise.invalid/v1")
    monkeypatch.setenv("ENTERPRISE_AI_API_KEY", "test-key")
    for project in ("GATEWAY", "ZONAL", "PNG"):
        monkeypatch.setenv(f"{project}_REQUIREMENT_CLARIFIER_AGENT_ID", f"{project}-0")
        monkeypatch.setenv(f"{project}_REQUIREMENT_ANALYZER_AGENT_ID", f"{project}-1")
        monkeypatch.setenv(f"{project}_FEATURE_ANALYZER_AGENT_ID", f"{project}-2")
        monkeypatch.setenv(f"{project}_TESTSPEC_GENERATOR_AGENT_ID", f"{project}-3")
        monkeypatch.setenv(f"{project}_TESTSPEC_REVIEWER_AGENT_ID", f"{project}-4")
    yield


@pytest.fixture
def mocked_transport(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"agents": [], "responses": {}, "raise_for": {}}

    async def invoke(
        self: OpenAICompatibleAgentTransport, agent_id: str, input_data: dict
    ) -> AgentInvocationResponse:
        state["agents"].append(agent_id)
        if agent_id in state["raise_for"]:
            raise state["raise_for"][agent_id]
        if agent_id in state["responses"]:
            content = state["responses"][agent_id]
        elif agent_id.endswith("-0"):
            content = '{"status": "clear", "open_questions": [], "resolved_from_history": []}'
        else:
            content = f"response-from-{agent_id}"
        return AgentInvocationResponse(agent_id=agent_id, content=content)

    async def close(self: OpenAICompatibleAgentTransport) -> None:
        return None

    monkeypatch.setattr(OpenAICompatibleAgentTransport, "invoke", invoke)
    monkeypatch.setattr(OpenAICompatibleAgentTransport, "close", close)
    return state


def test_agent_status_endpoint_reports_safe_configuration_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ENTERPRISE_AI_BASE_URL", raising=False)
    monkeypatch.delenv("ENTERPRISE_AI_API_KEY", raising=False)
    response = TestClient(create_app()).get("/api/v1/agents/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["endpoint_configured"] is False
    assert payload["credentials_configured"] is False
    assert "test-key" not in str(payload)


def test_workflow_endpoint_invokes_configured_sequence(
    configured_env: None,
    mocked_transport: dict[str, Any],
) -> None:
    client = TestClient(create_app())
    start = client.post(
        "/api/v1/workflow/test-specification",
        json={"project": "gateway", "requirements": "REQ-1 shall operate."},
    )

    assert start.status_code == 202
    execution_id = start.json()["execution_id"]

    final = poll_until_terminal(client, execution_id)

    assert final["status"] == "completed"
    assert mocked_transport["agents"] == [
        "GATEWAY-0",
        "GATEWAY-1",
        "GATEWAY-2",
        "GATEWAY-3",
        "GATEWAY-4",
    ]
    assert final["final_reviewed_output"] == "response-from-GATEWAY-4"
    # historical_context_agent is optional and was not configured for this project.
    assert final["agent_executions"][0]["status"] == "skipped"


def test_workflow_endpoint_rejects_empty_requirements(configured_env: None) -> None:
    response = TestClient(create_app()).post(
        "/api/v1/workflow/test-specification",
        json={"project": "gateway", "requirements": "   "},
    )

    assert response.status_code == 422


def test_workflow_endpoint_rejects_unsupported_project(configured_env: None) -> None:
    response = TestClient(create_app()).post(
        "/api/v1/workflow/test-specification",
        json={"project": "unknown", "requirements": "REQ-1"},
    )

    assert response.status_code == 404


def test_workflow_endpoint_reports_missing_agent_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENTERPRISE_AI_BASE_URL", "https://enterprise.invalid/v1")
    monkeypatch.setenv("ENTERPRISE_AI_API_KEY", "test-key")
    monkeypatch.delenv("GATEWAY_REQUIREMENT_ANALYZER_AGENT_ID", raising=False)
    response = TestClient(create_app()).post(
        "/api/v1/workflow/test-specification",
        json={"project": "gateway", "requirements": "REQ-1"},
    )

    assert response.status_code == 503
    assert "GATEWAY_REQUIREMENT_ANALYZER_AGENT_ID" in response.text


def test_workflow_endpoint_rejects_invalid_environment_configuration(
    configured_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENTERPRISE_AI_TIMEOUT_SECONDS", "not-a-number")
    response = TestClient(create_app()).post(
        "/api/v1/workflow/test-specification",
        json={"project": "gateway", "requirements": "REQ-7 shall operate."},
    )

    assert response.status_code == 503
    assert "ENTERPRISE_AI_TIMEOUT_SECONDS" in response.text


def test_workflow_endpoint_reports_failure_at_final_reviewer_stage(
    configured_env: None,
    mocked_transport: dict[str, Any],
) -> None:
    client = TestClient(create_app())
    mocked_transport["raise_for"]["GATEWAY-4"] = EnterpriseAIConnectionError(
        "Simulated reviewer outage."
    )
    start = client.post(
        "/api/v1/workflow/test-specification",
        json={"project": "gateway", "requirements": "REQ-4 shall operate."},
    )
    execution_id = start.json()["execution_id"]

    final = poll_until_terminal(client, execution_id)

    assert final["status"] == "failed"
    assert final["error"]["code"] == "enterprise_ai_connection_error"
    reviewer_record = next(
        record for record in final["agent_executions"] if record["agent_id"] == "GATEWAY-4"
    )
    assert reviewer_record["status"] == "failed"


def test_workflow_endpoint_reports_rate_limit_error(
    configured_env: None,
    mocked_transport: dict[str, Any],
) -> None:
    client = TestClient(create_app())
    mocked_transport["raise_for"]["GATEWAY-2"] = EnterpriseAIRateLimitError(
        "Simulated rate limit."
    )
    start = client.post(
        "/api/v1/workflow/test-specification",
        json={"project": "gateway", "requirements": "REQ-5 shall operate."},
    )
    execution_id = start.json()["execution_id"]

    final = poll_until_terminal(client, execution_id)

    assert final["status"] == "failed"
    assert final["error"]["code"] == "enterprise_ai_rate_limit_error"


def test_workflow_endpoint_reports_unexpected_clarifier_response(
    configured_env: None,
    mocked_transport: dict[str, Any],
) -> None:
    client = TestClient(create_app())
    mocked_transport["responses"]["GATEWAY-0"] = "not valid json"
    start = client.post(
        "/api/v1/workflow/test-specification",
        json={"project": "gateway", "requirements": "REQ-6 shall operate."},
    )
    execution_id = start.json()["execution_id"]

    final = poll_until_terminal(client, execution_id)

    assert final["status"] == "failed"
    assert final["error"]["code"] == "unexpected_agent_response"


def test_workflow_clarification_pause_and_resume(
    configured_env: None,
    mocked_transport: dict[str, Any],
) -> None:
    client = TestClient(create_app())
    mocked_transport["responses"]["GATEWAY-0"] = CLARIFIER_NEEDS_INPUT
    start = client.post(
        "/api/v1/workflow/test-specification",
        json={"project": "gateway", "requirements": "REQ-8 shall operate."},
    )
    execution_id = start.json()["execution_id"]

    paused = poll_until_terminal(client, execution_id)
    assert paused["status"] == "awaiting_clarification"
    assert paused["open_questions"] == [
        "What is the expected response time under low voltage?"
    ]

    resume = client.post(
        f"/api/v1/workflow/executions/{execution_id}/clarifications",
        json={
            "answers": {
                "What is the expected response time under low voltage?": "200 ms maximum."
            }
        },
    )
    assert resume.status_code == 202

    final = poll_until_terminal(client, execution_id)
    assert final["status"] == "completed"
    assert mocked_transport["agents"] == [
        "GATEWAY-0",
        "GATEWAY-1",
        "GATEWAY-2",
        "GATEWAY-3",
        "GATEWAY-4",
    ]


def test_clarification_resume_rejects_when_execution_not_awaiting(
    configured_env: None,
    mocked_transport: dict[str, Any],
) -> None:
    client = TestClient(create_app())
    start = client.post(
        "/api/v1/workflow/test-specification",
        json={"project": "gateway", "requirements": "REQ-9 shall operate."},
    )
    execution_id = start.json()["execution_id"]
    poll_until_terminal(client, execution_id)

    resume = client.post(
        f"/api/v1/workflow/executions/{execution_id}/clarifications",
        json={"answers": {"anything": "answer"}},
    )

    assert resume.status_code == 409


def test_get_workflow_execution_returns_404_for_unknown_id() -> None:
    response = TestClient(create_app()).get("/api/v1/workflow/executions/does-not-exist")

    assert response.status_code == 404


def test_agent_connection_endpoint_uses_predefined_test_input(
    configured_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    async def invoke(
        self: OpenAICompatibleAgentTransport, agent_id: str, input_data: dict
    ) -> AgentInvocationResponse:
        captured.update(input_data)
        return AgentInvocationResponse(agent_id=agent_id, content="reachable")

    async def close(self: OpenAICompatibleAgentTransport) -> None:
        return None

    monkeypatch.setattr(OpenAICompatibleAgentTransport, "invoke", invoke)
    monkeypatch.setattr(OpenAICompatibleAgentTransport, "close", close)
    response = TestClient(create_app()).post("/api/v1/agents/GATEWAY-1/test")

    assert response.status_code == 200
    assert captured == {
        "connection_test": True,
        "task": "Reply only with a short acknowledgement confirming this agent is reachable.",
    }

