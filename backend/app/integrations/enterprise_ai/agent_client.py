"""Public enterprise agent invocation service."""

from typing import Any

from .client import AgentTransport, OpenAICompatibleAgentTransport
from .config import EnterpriseAISettings
from .models import AgentInvocationResponse


class EnterpriseAgentClient:
    """Transport-independent facade for invoking enterprise agents."""

    def __init__(
        self,
        settings: EnterpriseAISettings,
        transport: AgentTransport | None = None,
    ) -> None:
        self.settings = settings
        self._transport = transport or OpenAICompatibleAgentTransport(settings)

    @classmethod
    def from_env(cls) -> "EnterpriseAgentClient":
        settings = EnterpriseAISettings.from_env()
        settings.validate_api_configuration()
        return cls(settings)

    async def invoke_agent(
        self, agent_id: str, input_data: dict[str, Any]
    ) -> AgentInvocationResponse:
        """Invoke one configured enterprise agent using structured input."""
        return await self._transport.invoke(agent_id, input_data)

    async def close(self) -> None:
        await self._transport.close()
