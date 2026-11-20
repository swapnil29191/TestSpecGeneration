"""Configuration for the Devmate AI (OpenAI-compatible) endpoint.
Loads from environment variables or a .env file in this directory.
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass


class Config:
    """Centralized configuration for the Devmate AI API."""

    API_KEY: str = os.getenv("DEVMATE_API_KEY", "")
    BASE_URL: str = os.getenv("DEVMATE_BASE_URL", "")
    MODEL: str = os.getenv("DEVMATE_MODEL", "")  # model / agent_id (default, used when no project selected)

    # Per-project CAPL generation agent override. Each project can be backed by
    # a different Devmate agent_id; falls back to MODEL above when unset/unknown.
    PROJECT_MODELS: dict = {
        "PNG": os.getenv("DEVMATE_MODEL_PNG", ""),
        "Gateway": os.getenv("DEVMATE_MODEL_GATEWAY", ""),
        "BCM": os.getenv("DEVMATE_MODEL_BCM", ""),
    }

    # Validation pipeline agents — each is a distinct Devmate agent_id
    MODEL_SYNTAX: str = os.getenv("DEVMATE_MODEL_SYNTAX", "")    # Agent 1 — syntax & quality
    MODEL_XCP: str = os.getenv("DEVMATE_MODEL_XCP", "")          # Agent 2 — XCP validation
    MODEL_COMPLETE: str = os.getenv("DEVMATE_MODEL_COMPLETE", "")  # Agent 3 — duplicate/common code

    @classmethod
    def resolve_model(cls, project: str = "") -> str:
        """Return the CAPL generation agent_id for *project*, falling back to MODEL."""
        return cls.PROJECT_MODELS.get(project) or cls.MODEL

    CONNECT_TIMEOUT: int = int(os.getenv("DEVMATE_CONNECT_TIMEOUT", "10"))
    REQUEST_TIMEOUT: int = int(os.getenv("DEVMATE_REQUEST_TIMEOUT", "300"))
    MAX_RETRIES: int = int(os.getenv("DEVMATE_MAX_RETRIES", "2"))

    # Corporate proxy (optional)
    PROXY_URL: str = os.getenv("DEVMATE_PROXY_URL", "")
