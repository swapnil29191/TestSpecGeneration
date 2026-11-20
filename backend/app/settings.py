"""Environment-backed application settings."""

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_env: str
    project_config_dir: Path
    cors_allowed_origins: tuple[str, ...]


def get_settings() -> Settings:
    raw_origins = os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:8501,http://127.0.0.1:8501",
    )
    origins = tuple(origin.strip() for origin in raw_origins.split(",") if origin.strip())

    return Settings(
        app_name=os.getenv("APP_NAME", "TestSpecGeneration"),
        app_env=os.getenv("APP_ENV", "development"),
        project_config_dir=Path(os.getenv("PROJECT_CONFIG_DIR", "config/projects")),
        cors_allowed_origins=origins,
    )
