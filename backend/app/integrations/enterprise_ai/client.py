"""Transport adapters for enterprise agent invocation."""

from typing import Any, Protocol
import json

import httpx

from .config import EnterpriseAISettings
from .errors import (
    EnterpriseAIAuthenticationError,
    EnterpriseAIConnectionError,
    EnterpriseAIError,
    EnterpriseAIRateLimitError,
    EnterpriseAIResponseError,
    EnterpriseAITimeoutError,
)
from .models import AgentInvocationResponse


class AgentTransport(Protocol):
    """Replaceable transport contract used by the orchestration layer."""

    async def invoke(
        self, agent_id: str, input_data: dict[str, Any]
    ) -> AgentInvocationResponse: ...

    async def close(self) -> None: ...


class OpenAICompatibleAgentTransport:
    """Invoke agents as models through an OpenAI-compatible chat endpoint."""

    def __init__(self, settings: EnterpriseAISettings) -> None:
        from openai import AsyncOpenAI

        self._http_client = httpx.AsyncClient(
            proxy=settings.proxy_url or None,
            verify=settings.verify_ssl,
            timeout=httpx.Timeout(
                settings.timeout_seconds,
                connect=settings.connect_timeout_seconds,
            ),
        )
        self._client = AsyncOpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url,
            http_client=self._http_client,
            max_retries=settings.max_retries,
            timeout=settings.timeout_seconds,
        )

    async def invoke(
        self, agent_id: str, input_data: dict[str, Any]
    ) -> AgentInvocationResponse:
        from openai import APIConnectionError, APITimeoutError, AuthenticationError, RateLimitError
        from openai import APIError, OpenAIError

        payload = json.dumps(input_data, ensure_ascii=True, default=str)
        try:
            response = await self._client.chat.completions.create(
                model=agent_id,
                messages=[{"role": "user", "content": payload}],
            )
        except AuthenticationError as exc:
            raise EnterpriseAIAuthenticationError(
                "The enterprise AI platform rejected the configured credentials."
            ) from exc
        except APITimeoutError as exc:
            raise EnterpriseAITimeoutError(
                "The enterprise agent invocation timed out."
            ) from exc
        except APIConnectionError as exc:
            raise EnterpriseAIConnectionError(
                "The enterprise AI platform could not be reached."
            ) from exc
        except RateLimitError as exc:
            raise EnterpriseAIRateLimitError(
                "The enterprise AI platform rate limit was reached."
            ) from exc
        except APIError as exc:
            raise EnterpriseAIError(
                "The enterprise AI platform rejected the agent invocation."
            ) from exc
        except OpenAIError as exc:
            raise EnterpriseAIError(
                "The enterprise AI client could not complete the invocation."
            ) from exc
        except httpx.TimeoutException as exc:
            raise EnterpriseAITimeoutError(
                "The enterprise agent invocation timed out."
            ) from exc
        except httpx.RequestError as exc:
            raise EnterpriseAIConnectionError(
                "The enterprise AI platform could not be reached."
            ) from exc

        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError, TypeError) as exc:
            raise EnterpriseAIResponseError(
                "The enterprise AI platform returned an unexpected response format."
            ) from exc
        if not isinstance(content, str) or not content.strip():
            raise EnterpriseAIResponseError(
                "The enterprise AI platform returned an empty agent response."
            )

        return AgentInvocationResponse(
            agent_id=agent_id,
            content=content,
            response_id=getattr(response, "id", None),
        )

    async def close(self) -> None:
        await self._client.close()
