"""Environment-backed configuration for enterprise agents."""

from dataclasses import dataclass
from collections.abc import Mapping
import os

from dotenv import load_dotenv

from .errors import EnterpriseAIConfigurationError

load_dotenv()

MANDATORY_AGENT_ENV_SUFFIXES = (
    ("requirement_clarifier", "REQUIREMENT_CLARIFIER_AGENT_ID"),
    ("requirement_analyzer", "REQUIREMENT_ANALYZER_AGENT_ID"),
    ("feature_analyzer", "FEATURE_ANALYZER_AGENT_ID"),
    ("testspec_generator", "TESTSPEC_GENERATOR_AGENT_ID"),
    ("testspec_reviewer", "TESTSPEC_REVIEWER_AGENT_ID"),
)

# Optional: skipped when not configured for a project instead of blocking the workflow.
OPTIONAL_AGENT_ENV_SUFFIXES = (
    ("historical_context_agent", "HISTORICAL_CONTEXT_AGENT_ID"),
)

AGENT_ENV_SUFFIXES = MANDATORY_AGENT_ENV_SUFFIXES + OPTIONAL_AGENT_ENV_SUFFIXES


@dataclass(frozen=True)
class EnterpriseAISettings:
    """Safe enterprise API and agent ID configuration."""

    base_url: str
    api_key: str
    timeout_seconds: float
    connect_timeout_seconds: float
    max_retries: int
    proxy_url: str
    verify_ssl: bool
    environment: Mapping[str, str]

    @classmethod
    def from_env(cls, environment: Mapping[str, str] | None = None) -> "EnterpriseAISettings":
        values = environment if environment is not None else os.environ
        return cls(
            base_url=values.get("ENTERPRISE_AI_BASE_URL", "").strip(),
            api_key=values.get("ENTERPRISE_AI_API_KEY", "").strip(),
            timeout_seconds=cls._read_float(values, "ENTERPRISE_AI_TIMEOUT_SECONDS", 120.0),
            connect_timeout_seconds=cls._read_float(
                values, "ENTERPRISE_AI_CONNECT_TIMEOUT_SECONDS", 10.0
            ),
            max_retries=cls._read_int(values, "ENTERPRISE_AI_MAX_RETRIES", 2),
            proxy_url=values.get("ENTERPRISE_AI_PROXY_URL", "").strip(),
            verify_ssl=values.get("ENTERPRISE_AI_VERIFY_SSL", "true").strip().lower()
            not in {"0", "false", "no", "off"},
            environment=dict(values),
        )

    @staticmethod
    def _read_float(values: Mapping[str, str], key: str, default: float) -> float:
        raw = values.get(key, str(default))
        try:
            value = float(raw)
        except ValueError as exc:
            raise EnterpriseAIConfigurationError(f"{key} must be a number.") from exc
        if value <= 0:
            raise EnterpriseAIConfigurationError(f"{key} must be greater than zero.")
        return value

    @staticmethod
    def _read_int(values: Mapping[str, str], key: str, default: int) -> int:
        raw = values.get(key, str(default))
        try:
            value = int(raw)
        except ValueError as exc:
            raise EnterpriseAIConfigurationError(f"{key} must be an integer.") from exc
        if value < 0:
            raise EnterpriseAIConfigurationError(f"{key} cannot be negative.")
        return value

    @property
    def endpoint_configured(self) -> bool:
        return bool(self.base_url)

    @property
    def credentials_configured(self) -> bool:
        return bool(self.api_key)

    def validate_api_configuration(self) -> None:
        missing: list[str] = []
        if not self.endpoint_configured:
            missing.append("ENTERPRISE_AI_BASE_URL")
        if not self.credentials_configured:
            missing.append("ENTERPRISE_AI_API_KEY")
        if missing:
            raise EnterpriseAIConfigurationError(
                "Enterprise AI configuration is incomplete. Missing: " + ", ".join(missing),
                missing=missing,
            )

    def agent_ids_for_project(self, project: str) -> dict[str, str]:
        project_prefix = "".join(
            character if character.isalnum() else "_" for character in project.strip()
        ).upper()
        agents: dict[str, str] = {}
        missing: list[str] = []
        for role, suffix in MANDATORY_AGENT_ENV_SUFFIXES:
            key = f"{project_prefix}_{suffix}"
            value = self.environment.get(key, "").strip()
            if value:
                agents[role] = value
            else:
                missing.append(key)
        for role, suffix in OPTIONAL_AGENT_ENV_SUFFIXES:
            key = f"{project_prefix}_{suffix}"
            value = self.environment.get(key, "").strip()
            if value:
                agents[role] = value
        if missing:
            raise EnterpriseAIConfigurationError(
                f"Agent configuration for project '{project}' is incomplete. Missing: "
                + ", ".join(missing),
                missing=missing,
            )
        return agents

    def configured_agent_ids(self, projects: list[str]) -> dict[str, dict[str, str]]:
        configured: dict[str, dict[str, str]] = {}
        for project in projects:
            try:
                configured[project] = self.agent_ids_for_project(project)
            except EnterpriseAIConfigurationError:
                continue
        return configured
