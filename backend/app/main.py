"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes import agents, health, projects, requirements, workflow
from backend.app.orchestration.execution_store import ExecutionStore
from backend.app.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Backend API for the Automotive Test Specification Generation application.",
    )
    application.state.settings = settings
    application.state.execution_store = ExecutionStore()
    application.state.background_tasks = set()

    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    application.include_router(health.router)
    application.include_router(health.router, prefix="/api/v1")
    application.include_router(projects.router, prefix="/api/v1")
    application.include_router(agents.router, prefix="/api/v1")
    application.include_router(requirements.router, prefix="/api/v1")
    application.include_router(workflow.router, prefix="/api/v1")

    @application.get("/")
    def root() -> dict[str, str]:
        return {
            "application": settings.app_name,
            "environment": settings.app_env,
            "status": "running",
        }

    return application


app = create_app()
