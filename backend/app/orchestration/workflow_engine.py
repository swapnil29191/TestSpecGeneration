"""Sequential enterprise agent workflow execution."""

from collections.abc import Mapping, Sequence

from backend.app.integrations.enterprise_ai.agent_client import EnterpriseAgentClient
from backend.app.integrations.enterprise_ai.errors import EnterpriseAIError
from backend.app.orchestration.execution_context import (
    AgentExecutionError,
    ExecutionContext,
    WorkflowExecution,
)
from backend.app.orchestration.workflow_config import WorkflowStep


class WorkflowEngine:
    """Execute declarative workflow steps in strict sequence."""

    def __init__(
        self,
        client: EnterpriseAgentClient,
        workflow: Sequence[WorkflowStep],
    ) -> None:
        self._client = client
        self._workflow = tuple(workflow)

    async def execute_workflow(
        self,
        project: str,
        requirements: str,
        agent_ids: Mapping[str, str],
    ) -> WorkflowExecution:
        """Run all mandatory agents, stopping immediately on any failure."""
        missing_roles = [step.role for step in self._workflow if not agent_ids.get(step.role)]
        if missing_roles:
            raise ValueError(
                "Missing configured agent IDs for roles: " + ", ".join(missing_roles)
            )

        context = ExecutionContext(
            project=project,
            steps=[
                (step.key, step.role, step.label, agent_ids[step.role])
                for step in self._workflow
            ],
        )
        prior_outputs: dict[str, str] = {}

        for step, record in zip(
            self._workflow, context.execution.agent_executions, strict=True
        ):
            context.start(record)
            try:
                response = await self._client.invoke_agent(
                    agent_ids[step.role],
                    step.build_input(project, requirements, prior_outputs),
                )
            except EnterpriseAIError as exc:
                error = AgentExecutionError(code=exc.code, message=exc.message)
                context.fail(record, error)
                context.skip_pending()
                break
            except Exception:
                error = AgentExecutionError(
                    code="unexpected_agent_error",
                    message="The enterprise agent failed unexpectedly.",
                )
                context.fail(record, error)
                context.skip_pending()
                break

            context.complete(record, step.output_key, response.content)
            prior_outputs[step.output_key] = response.content

        context.finish()
        return context.execution
