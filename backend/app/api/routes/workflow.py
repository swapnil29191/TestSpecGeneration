"""Test specification workflow API endpoint."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from backend.app.api.schemas import WorkflowRequest
from backend.app.integrations.enterprise_ai.agent_client import EnterpriseAgentClient
from backend.app.integrations.enterprise_ai.config import EnterpriseAISettings
from backend.app.integrations.enterprise_ai.errors import EnterpriseAIConfigurationError
from backend.app.orchestration.execution_context import WorkflowExecution
from backend.app.orchestration.workflow_config import TEST_SPECIFICATION_WORKFLOW
from backend.app.orchestration.workflow_engine import WorkflowEngine
from backend.app.project_registry import ProjectConfigurationError, load_projects

router = APIRouter(prefix="/workflow", tags=["workflow"])


@router.post("/test-specification", response_model=WorkflowExecution)
async def execute_test_specification_workflow(
    payload: WorkflowRequest,
    request: Request,
) -> WorkflowExecution | JSONResponse:
    projects = _available_projects(request)
    project_key = payload.project.lower()
    if project_key not in projects:
        raise HTTPException(
            status_code=404,
            detail=f"Unsupported project '{payload.project}'. Available projects: "
            + ", ".join(sorted(projects)),
        )

    try:
        settings = EnterpriseAISettings.from_env()
        settings.validate_api_configuration()
        agent_ids = settings.agent_ids_for_project(project_key)
    except EnterpriseAIConfigurationError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": exc.code, "message": exc.message, "missing": exc.missing},
        ) from exc

    client = EnterpriseAgentClient(settings)
    try:
        engine = WorkflowEngine(client, TEST_SPECIFICATION_WORKFLOW)
        execution = await engine.execute_workflow(
            project=project_key,
            requirements=payload.requirements,
            agent_ids=agent_ids,
        )
    finally:
        await client.close()

    if execution.status == "failed":
        return JSONResponse(
            status_code=_workflow_failure_status(execution.error.code if execution.error else ""),
            content=execution.model_dump(mode="json"),
        )
    return execution


def _available_projects(request: Request) -> set[str]:
    try:
        projects = load_projects(request.app.state.settings.project_config_dir)
    except ProjectConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {str(project["id"]).lower() for project in projects}


def _workflow_failure_status(error_code: str) -> int:
    if error_code == "enterprise_ai_timeout_error":
        return 504
    if error_code == "enterprise_ai_rate_limit_error":
        return 429
    if error_code == "enterprise_ai_connection_error":
        return 503
    return 502
