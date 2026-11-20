"""Load and validate project configuration files."""

from pathlib import Path
from typing import Any

import yaml


class ProjectConfigurationError(ValueError):
    """Raised when a project YAML file is missing required information."""


def load_projects(config_dir: Path) -> list[dict[str, Any]]:
    if not config_dir.exists():
        raise ProjectConfigurationError(
            f"Project configuration directory does not exist: {config_dir}"
        )

    projects: list[dict[str, Any]] = []
    for config_path in sorted(config_dir.glob("*.yaml")):
        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise ProjectConfigurationError(
                f"Invalid YAML in {config_path.name}: {exc}"
            ) from exc

        if not isinstance(raw, dict) or not isinstance(raw.get("project"), dict):
            raise ProjectConfigurationError(
                f"{config_path.name} must contain a top-level 'project' mapping."
            )

        project = raw["project"]
        project_id = project.get("id")
        name = project.get("name")
        features = raw.get("features", {})

        if not isinstance(project_id, str) or not project_id.strip():
            raise ProjectConfigurationError(
                f"{config_path.name}: project.id must be a non-empty string."
            )
        if not isinstance(name, str) or not name.strip():
            raise ProjectConfigurationError(
                f"{config_path.name}: project.name must be a non-empty string."
            )
        if not isinstance(features, dict):
            raise ProjectConfigurationError(
                f"{config_path.name}: features must be a mapping."
            )

        projects.append(
            {
                "id": project_id,
                "name": name,
                "description": str(project.get("description", "")),
                "features": [
                    feature_id
                    for feature_id, feature_config in features.items()
                    if isinstance(feature_config, dict)
                    and feature_config.get("enabled", True)
                ],
                "config_file": config_path.name,
            }
        )

    return projects
