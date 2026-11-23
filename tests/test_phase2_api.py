"""Integration-style mocked tests for Phase 2 API endpoints."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from backend.app.integrations.enterprise_ai.client import OpenAICompatibleAgentTransport
from backend.app.integrations.enterprise_ai.models import AgentInvocationResponse
from backend.app.main import create_app


@pytest.fixture
def configured_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ENTERPRISE_AI_BASE_URL", "https://enterprise.invalid/v1")
    monkeypatch.setenv("ENTERPRISE_AI_API_KEY", "test-key")
    for project in ("GATEWAY", "ZONAL", "ADAS"):
        monkeypatch.setenv(f"{project}_REQUIREMENT_ANALYZER_AGENT_ID", f"{project}-1")
        monkeypatch.setenv(f"{project}_FEATURE_ANALYZER_AGENT_ID", f"{project}-2")
        monkeypatch.setenv(f"{project}_TESTSPEC_GENERATOR_AGENT_ID", f"{project}-3")
        monkeypatch.setenv(f"{project}_TESTSPEC_REVIEWER_AGENT_ID", f"{project}-4")
    yield


@pytest.fixture
def mocked_transport(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
    invocations: dict[str, list[str]] = {"agents": []}

    async def invoke(
        self: OpenAICompatibleAgentTransport, agent_id: str, input_data: dict
    ) -> AgentInvocationResponse:
        invocations["agents"].append(agent_id)
        return AgentInvocationResponse(agent_id=agent_id, content=f"response-from-{agent_id}")

    async def close(self: OpenAICompatibleAgentTransport) -> None:
        return None

    monkeypatch.setattr(OpenAICompatibleAgentTransport, "invoke", invoke)
    monkeypatch.setattr(OpenAICompatibleAgentTransport, "close", close)
    return invocations


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
    mocked_transport: dict[str, list[str]],
) -> None:
    response = TestClient(create_app()).post(
        "/api/v1/workflow/test-specification",
        json={"project": "gateway", "requirements": "REQ-1 shall operate."},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert mocked_transport["agents"] == [
        "GATEWAY-1",
        "GATEWAY-2",
        "GATEWAY-3",
        "GATEWAY-4",
    ]
    assert payload["final_reviewed_output"] == "response-from-GATEWAY-4"


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
