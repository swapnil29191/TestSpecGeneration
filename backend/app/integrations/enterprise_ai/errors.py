"""Errors raised by the enterprise AI integration layer."""


class EnterpriseAIError(Exception):
    """Base exception for enterprise AI failures."""

    code = "enterprise_ai_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class EnterpriseAIConfigurationError(EnterpriseAIError):
    """Raised when endpoint or agent configuration is incomplete."""

    code = "enterprise_ai_configuration_error"

    def __init__(self, message: str, missing: list[str] | None = None) -> None:
        super().__init__(message)
        self.missing = missing or []


class EnterpriseAIAuthenticationError(EnterpriseAIError):
    """Raised when the enterprise API rejects credentials."""

    code = "enterprise_ai_authentication_error"


class EnterpriseAIConnectionError(EnterpriseAIError):
    """Raised when the enterprise API cannot be reached."""

    code = "enterprise_ai_connection_error"


class EnterpriseAITimeoutError(EnterpriseAIError):
    """Raised when an enterprise agent invocation times out."""

    code = "enterprise_ai_timeout_error"


class EnterpriseAIRateLimitError(EnterpriseAIError):
    """Raised when the enterprise API rate-limits an invocation."""

    code = "enterprise_ai_rate_limit_error"


class EnterpriseAIResponseError(EnterpriseAIError):
    """Raised when the enterprise API returns an unexpected response."""

    code = "enterprise_ai_response_error"
