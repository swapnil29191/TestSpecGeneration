from fastapi import APIRouter, HTTPException, Request

from backend.app.project_registry import (
    ProjectConfigurationError,
    load_projects,
)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("")
def get_projects(request: Request) -> dict:
    settings = request.app.state.settings
    try:
        projects = load_projects(settings.project_config_dir)
    except ProjectConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"items": projects, "count": len(projects)}
