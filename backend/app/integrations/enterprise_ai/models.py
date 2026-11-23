"""Typed models shared by enterprise AI integrations."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentInvocationRequest(BaseModel):
    """Structured request passed to an enterprise agent."""

    agent_id: str = Field(min_length=1)
    input_data: dict[str, Any]


class AgentInvocationResponse(BaseModel):
    """Normalized response independent of the underlying API transport."""

    agent_id: str
    content: str
    transport: Literal["openai_compatible"] = "openai_compatible"
    response_id: str | None = None


class EnterpriseAIStatus(BaseModel):
    """Safe, secret-free enterprise AI configuration status."""

    endpoint_configured: bool
    credentials_configured: bool
    invocation_configuration_available: bool
    invocation_mode: str
    integration_status: list[str]
    configured_projects: list[str]
    configured_agents: dict[str, dict[str, str]]


class AgentConnectionTestResponse(BaseModel):
    """Result of a predefined enterprise agent connectivity test."""

    status: Literal["connected"] = "connected"
    agent_id: str
    response: str
