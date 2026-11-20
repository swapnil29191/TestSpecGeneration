"""Minimal OpenAI-compatible client for the Devmate AI endpoint.
Relies on the OpenAI SDK's built-in retry handling for reliability.
"""

import logging

import httpx
import truststore
from openai import OpenAI

logger = logging.getLogger(__name__)

# Use the OS trust store so corporate proxy/TLS interception certs are accepted.
truststore.inject_into_ssl()


class DevmateClient:
    """Thin wrapper around the OpenAI SDK pointed at the Devmate endpoint."""

    def __init__(self, config) -> None:
        self.config = config
        http_client = httpx.Client(
            proxy=config.PROXY_URL or None,
            timeout=httpx.Timeout(config.REQUEST_TIMEOUT, connect=config.CONNECT_TIMEOUT),
        )
        self._client = OpenAI(
            api_key=config.API_KEY,
            base_url=config.BASE_URL,
            http_client=http_client,
            max_retries=config.MAX_RETRIES,
        )

    def send_prompt(self, prompt: str) -> str:
        """Send a prompt to the Devmate agent and return the response text."""
        logger.info("Sending prompt to Devmate (model=%s, prompt_len=%d)", self.config.MODEL, len(prompt))
        response = self._client.chat.completions.create(
            model=self.config.MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or ""
