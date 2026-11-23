"""Sequential enterprise agent workflow execution."""

from collections.abc import Callable, Mapping, Sequence
import json

from backend.app.integrations.enterprise_ai.agent_client import EnterpriseAgentClient
from backend.app.integrations.enterprise_ai.errors import EnterpriseAIError
from backend.app.orchestration.execution_context import (
    AgentExecutionError,
    ExecutionContext,
    WorkflowExecution,
)
from backend.app.orchestration.workflow_config import WorkflowStep

OnUpdate = Callable[[WorkflowExecution], None]

CLARIFIER_ROLE = "requirement_clarifier"
_CLARIFIER_STATUSES = {"clear", "needs_clarification"}


class WorkflowEngine:
    """Execute declarative workflow steps in strict sequence."""

    def __init__(
        self,
        client: EnterpriseAgentClient,
        workflow: Sequence[WorkflowStep],
    ) -> None:
        self._client = client
        self._workflow = tuple(workflow)

    def create_execution(
        self,
        project: str,
        requirements: str,
        agent_ids: Mapping[str, str],
    ) -> ExecutionContext:
        """Build the pending execution record without running any agent."""
        missing_roles = [
            step.role
            for step in self._workflow
            if step.mandatory and not agent_ids.get(step.role)
        ]
        if missing_roles:
            raise ValueError(
                "Missing configured agent IDs for roles: " + ", ".join(missing_roles)
            )

        return ExecutionContext(
            project=project,
            requirements=requirements,
            steps=[
                (step.key, step.role, step.label, agent_ids.get(step.role, ""))
                for step in self._workflow
            ],
        )

    async def execute_workflow(
        self,
        project: str,
        requirements: str,
        agent_ids: Mapping[str, str],
        on_update: OnUpdate | None = None,
    ) -> WorkflowExecution:
        """Run all mandatory agents, stopping immediately on any failure."""
        context = self.create_execution(project, requirements, agent_ids)
        return await self.run(context, agent_ids, on_update=on_update)

    async def run(
        self,
        context: ExecutionContext,
        agent_ids: Mapping[str, str],
        on_update: OnUpdate | None = None,
    ) -> WorkflowExecution:
        """Run (or resume) an execution starting from its first pending stage."""
        records = context.execution.agent_executions
        prior_outputs: dict[str, str] = dict(context.execution.intermediate_outputs)
        if context.execution.clarification_answers:
            prior_outputs["clarification_answers"] = json.dumps(
                context.execution.clarification_answers, ensure_ascii=True
            )
        requirements = context.execution.requirements
        start_index = next(
            (index for index, record in enumerate(records) if record.status == "pending"),
            len(records),
        )
        self._notify(context, on_update)

        for index in range(start_index, len(self._workflow)):
            step = self._workflow[index]
            record = records[index]
            agent_id = agent_ids.get(step.role)

            if not agent_id:
                context.skip_optional(record)
                self._notify(context, on_update)
                continue

            context.start(record)
            self._notify(context, on_update)
            try:
                response = await self._client.invoke_agent(
                    agent_id,
                    step.build_input(context.execution.project, requirements, prior_outputs),
                )
            except EnterpriseAIError as exc:
                context.fail(record, AgentExecutionError(code=exc.code, message=exc.message))
                context.skip_pending()
                context.finish()
                self._notify(context, on_update)
                return context.execution
            except Exception:
                context.fail(
                    record,
                    AgentExecutionError(
                        code="unexpected_agent_error",
                        message="The enterprise agent failed unexpectedly.",
                    ),
                )
                context.skip_pending()
                context.finish()
                self._notify(context, on_update)
                return context.execution

            if step.role == CLARIFIER_ROLE:
                try:
                    decision = self._parse_clarifier_response(response.content)
                except ValueError:
                    context.fail(
                        record,
                        AgentExecutionError(
                            code="unexpected_agent_response",
                            message=(
                                "The requirement clarifier returned a response that could "
                                "not be interpreted."
                            ),
                        ),
                    )
                    context.skip_pending()
                    context.finish()
                    self._notify(context, on_update)
                    return context.execution

                context.complete(record, step.output_key, response.content)
                prior_outputs[step.output_key] = response.content
                if decision["status"] != "clear":
                    context.pause_for_clarification(
                        decision.get("open_questions", []),
                        decision.get("resolved_from_history", []),
                    )
                    self._notify(context, on_update)
                    return context.execution
                self._notify(context, on_update)
                continue

            context.complete(record, step.output_key, response.content)
            prior_outputs[step.output_key] = response.content
            self._notify(context, on_update)

        context.finish()
        self._notify(context, on_update)
        return context.execution

    @staticmethod
    def _parse_clarifier_response(content: str) -> dict:
        try:
            decision = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError("The clarifier response was not valid JSON.") from exc
        if not isinstance(decision, dict) or decision.get("status") not in _CLARIFIER_STATUSES:
            raise ValueError("The clarifier response did not contain a recognized status.")
        return decision

    @staticmethod
    def _notify(context: ExecutionContext, on_update: OnUpdate | None) -> None:
        if on_update is not None:
            on_update(context.execution)

