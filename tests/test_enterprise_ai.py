"""Tests for enterprise AI configuration and transport error mapping."""

from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from openai import AuthenticationError, APITimeoutError

from backend.app.integrations.enterprise_ai.client import OpenAICompatibleAgentTransport
from backend.app.integrations.enterprise_ai.config import EnterpriseAISettings
from backend.app.integrations.enterprise_ai.errors import (
    EnterpriseAIAuthenticationError,
    EnterpriseAIConfigurationError,
    EnterpriseAITimeoutError,
)


BASE_ENV = {
    "ENTERPRISE_AI_BASE_URL": "https://enterprise.invalid/v1",
    "ENTERPRISE_AI_API_KEY": "test-key",
}


def make_settings(overrides: dict[str, str] | None = None) -> EnterpriseAISettings:
    values = dict(BASE_ENV)
    values.update(overrides or {})
    return EnterpriseAISettings.from_env(values)


def test_missing_enterprise_api_configuration_is_reported() -> None:
    settings = make_settings({"ENTERPRISE_AI_BASE_URL": "", "ENTERPRISE_AI_API_KEY": ""})

    with pytest.raises(EnterpriseAIConfigurationError) as exc_info:
        settings.validate_api_configuration()

    assert exc_info.value.missing == [
        "ENTERPRISE_AI_BASE_URL",
        "ENTERPRISE_AI_API_KEY",
    ]


def test_missing_project_agent_id_is_reported() -> None:
    settings = make_settings()

    with pytest.raises(EnterpriseAIConfigurationError) as exc_info:
        settings.agent_ids_for_project("gateway")

    assert "GATEWAY_REQUIREMENT_ANALYZER_AGENT_ID" in exc_info.value.missing


class FailingCompletions:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def create(self, **_: Any) -> Any:
        raise self.error


def transport_with_error(error: Exception) -> OpenAICompatibleAgentTransport:
    transport = object.__new__(OpenAICompatibleAgentTransport)
    transport._client = SimpleNamespace(  # type: ignore[attr-defined]
        chat=SimpleNamespace(completions=FailingCompletions(error))
    )
    return transport


@pytest.mark.asyncio
async def test_authentication_failure_is_mapped_without_leaking_detail() -> None:
    request = httpx.Request("POST", "https://enterprise.invalid/v1/chat/completions")
    response = httpx.Response(401, request=request)
    transport = transport_with_error(
        AuthenticationError("secret server detail", response=response, body={})
    )

    with pytest.raises(EnterpriseAIAuthenticationError, match="rejected"):
        await transport.invoke("agent-1", {"requirements": "sensitive requirement"})


@pytest.mark.asyncio
async def test_timeout_is_mapped_to_domain_error() -> None:
    request = httpx.Request("POST", "https://enterprise.invalid/v1/chat/completions")
    transport = transport_with_error(APITimeoutError(request=request))

    with pytest.raises(EnterpriseAITimeoutError, match="timed out"):
        await transport.invoke("agent-1", {"requirements": "sensitive requirement"})
