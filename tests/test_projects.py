from pathlib import Path

from backend.app.project_registry import load_projects


def test_loads_project_configurations() -> None:
    projects = load_projects(Path("config/projects"))
    project_ids = {project["id"] for project in projects}

    assert {"gateway", "zonal", "adas"} <= project_ids


def test_gateway_has_expected_features() -> None:
    projects = load_projects(Path("config/projects"))
    gateway = next(project for project in projects if project["id"] == "gateway")

    assert "diagnostics" in gateway["features"]
    assert "nvm" in gateway["features"]
