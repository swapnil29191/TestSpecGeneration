"""Enterprise agent status and connectivity endpoints."""

from fastapi import APIRouter, HTTPException, Request

from backend.app.integrations.enterprise_ai.agent_client import EnterpriseAgentClient
from backend.app.integrations.enterprise_ai.config import EnterpriseAISettings
from backend.app.integrations.enterprise_ai.errors import (
    EnterpriseAIAuthenticationError,
    EnterpriseAIConfigurationError,
    EnterpriseAIConnectionError,
    EnterpriseAIError,
    EnterpriseAIRateLimitError,
    EnterpriseAITimeoutError,
)
from backend.app.integrations.enterprise_ai.models import (
    AgentConnectionTestResponse,
    EnterpriseAIStatus,
)
from backend.app.project_registry import ProjectConfigurationError, load_projects

router = APIRouter(prefix="/agents", tags=["agents"])

CONNECTION_TEST_INPUT = {
    "connection_test": True,
    "task": "Reply only with a short acknowledgement confirming this agent is reachable.",
}


@router.get("/status", response_model=EnterpriseAIStatus)
def get_agent_status(request: Request) -> EnterpriseAIStatus:
    settings = _load_enterprise_settings()
    projects = _project_ids(request)
    configured_agents = settings.configured_agent_ids(projects)
    notes = []
    if not settings.endpoint_configured:
        notes.append("ENTERPRISE_AI_BASE_URL is not configured.")
    if not settings.credentials_configured:
        notes.append("ENTERPRISE_AI_API_KEY is not configured.")
    if not configured_agents:
        notes.append("No project has a complete four-agent configuration.")
    if not notes:
        notes.append(
            "Configuration is available. No live enterprise connectivity test was performed."
        )
    return EnterpriseAIStatus(
        endpoint_configured=settings.endpoint_configured,
        credentials_configured=settings.credentials_configured,
        invocation_configuration_available=(
            settings.endpoint_configured
            and settings.credentials_configured
            and bool(configured_agents)
        ),
        invocation_mode="openai_compatible_agent_id_as_model",
        integration_status=notes,
        configured_projects=sorted(configured_agents),
        configured_agents=configured_agents,
    )


@router.post("/{agent_id}/test", response_model=AgentConnectionTestResponse)
async def test_agent_connection(
    agent_id: str,
    request: Request,
) -> AgentConnectionTestResponse:
    settings = _load_enterprise_settings()
    project_ids = _project_ids(request)
    configured_agents = settings.configured_agent_ids(project_ids)
    allowed_ids = {
        configured_id
        for agents in configured_agents.values()
        for configured_id in agents.values()
    }
    if agent_id not in allowed_ids:
        raise HTTPException(
            status_code=404,
            detail="The supplied agent ID is not present in the configured project workflows.",
        )

    try:
        settings.validate_api_configuration()
        client = EnterpriseAgentClient(settings)
        try:
            response = await client.invoke_agent(agent_id, CONNECTION_TEST_INPUT)
        finally:
            await client.close()
    except EnterpriseAIError as exc:
        raise HTTPException(status_code=_agent_error_status(exc), detail=exc.message) from exc

    return AgentConnectionTestResponse(agent_id=agent_id, response=response.content)


def _load_enterprise_settings() -> EnterpriseAISettings:
    try:
        return EnterpriseAISettings.from_env()
    except EnterpriseAIConfigurationError as exc:
        raise HTTPException(status_code=503, detail=exc.message) from exc


def _project_ids(request: Request) -> list[str]:
    try:
        projects = load_projects(request.app.state.settings.project_config_dir)
    except ProjectConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return [project["id"] for project in projects]


def _agent_error_status(error: EnterpriseAIError) -> int:
    if isinstance(error, EnterpriseAITimeoutError):
        return 504
    if isinstance(error, EnterpriseAIRateLimitError):
        return 429
    if isinstance(error, EnterpriseAIAuthenticationError):
        return 502
    if isinstance(error, EnterpriseAIConnectionError):
        return 503
    return 502
