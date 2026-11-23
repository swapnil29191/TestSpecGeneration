"""Test specification workflow API endpoints."""

import asyncio

from fastapi import APIRouter, HTTPException, Request

from backend.app.api.schemas import ClarificationAnswers, WorkflowRequest
from backend.app.integrations.enterprise_ai.agent_client import EnterpriseAgentClient
from backend.app.integrations.enterprise_ai.config import EnterpriseAISettings
from backend.app.integrations.enterprise_ai.errors import EnterpriseAIConfigurationError
from backend.app.orchestration.execution_context import ExecutionContext, WorkflowExecution
from backend.app.orchestration.execution_store import ExecutionStore
from backend.app.orchestration.workflow_config import TEST_SPECIFICATION_WORKFLOW
from backend.app.orchestration.workflow_engine import WorkflowEngine
from backend.app.project_registry import ProjectConfigurationError, load_projects

router = APIRouter(prefix="/workflow", tags=["workflow"])


@router.post(
    "/test-specification",
    response_model=WorkflowExecution,
    status_code=202,
)
async def start_test_specification_workflow(
    payload: WorkflowRequest,
    request: Request,
) -> WorkflowExecution:
    projects = _available_projects(request)
    project_key = payload.project.lower()
    if project_key not in projects:
        raise HTTPException(
            status_code=404,
            detail=f"Unsupported project '{payload.project}'. Available projects: "
            + ", ".join(sorted(projects)),
        )

    settings, agent_ids = _validated_agent_ids(project_key)
    client = EnterpriseAgentClient(settings)
    engine = WorkflowEngine(client, TEST_SPECIFICATION_WORKFLOW)
    try:
        context = engine.create_execution(project_key, payload.requirements, agent_ids)
    except ValueError as exc:
        await client.close()
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    store: ExecutionStore = request.app.state.execution_store
    store.save(context.execution)
    _run_in_background(request, engine, context, agent_ids, client, store)
    return context.execution


@router.get("/executions/{execution_id}", response_model=WorkflowExecution)
def get_workflow_execution(execution_id: str, request: Request) -> WorkflowExecution:
    store: ExecutionStore = request.app.state.execution_store
    execution = store.get(execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Unknown execution ID.")
    return execution


@router.post(
    "/executions/{execution_id}/clarifications",
    response_model=WorkflowExecution,
    status_code=202,
)
async def submit_clarification_answers(
    execution_id: str,
    payload: ClarificationAnswers,
    request: Request,
) -> WorkflowExecution:
    store: ExecutionStore = request.app.state.execution_store
    execution = store.get(execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Unknown execution ID.")
    if execution.status != "awaiting_clarification":
        raise HTTPException(
            status_code=409,
            detail="This execution is not awaiting clarification.",
        )

    settings, agent_ids = _validated_agent_ids(execution.project)
    context = ExecutionContext.from_execution(execution)
    context.apply_clarification_answers(payload.answers)
    store.save(context.execution)

    client = EnterpriseAgentClient(settings)
    engine = WorkflowEngine(client, TEST_SPECIFICATION_WORKFLOW)
    _run_in_background(request, engine, context, agent_ids, client, store)
    return context.execution


def _run_in_background(
    request: Request,
    engine: WorkflowEngine,
    context: ExecutionContext,
    agent_ids: dict[str, str],
    client: EnterpriseAgentClient,
    store: ExecutionStore,
) -> None:
    async def runner() -> None:
        try:
            await engine.run(context, agent_ids, on_update=store.save)
        finally:
            await client.close()

    task = asyncio.create_task(runner())
    background_tasks: set[asyncio.Task] = request.app.state.background_tasks
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)


def _validated_agent_ids(project_key: str) -> tuple[EnterpriseAISettings, dict[str, str]]:
    try:
        settings = EnterpriseAISettings.from_env()
        settings.validate_api_configuration()
        agent_ids = settings.agent_ids_for_project(project_key)
    except EnterpriseAIConfigurationError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": exc.code, "message": exc.message, "missing": exc.missing},
        ) from exc
    return settings, agent_ids


def _available_projects(request: Request) -> set[str]:
    try:
        projects = load_projects(request.app.state.settings.project_config_dir)
    except ProjectConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {str(project["id"]).lower() for project in projects}

