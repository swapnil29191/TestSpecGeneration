"""In-memory execution state for agent workflows."""

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

AgentStatus = Literal["pending", "running", "completed", "failed", "skipped"]
WorkflowStatus = Literal["running", "completed", "failed"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AgentExecutionError(BaseModel):
    """Secret-free agent failure details."""

    code: str
    message: str


class AgentExecutionRecord(BaseModel):
    """Status and timing for one agent stage."""

    key: str
    role: str
    label: str
    agent_id: str
    status: AgentStatus = "pending"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    output: str | None = None
    error: AgentExecutionError | None = None


class WorkflowExecutionSummary(BaseModel):
    """Compact workflow completion summary."""

    completed_agents: int
    failed_agents: int
    skipped_agents: int
    failed_stage: str | None = None


class WorkflowExecution(BaseModel):
    """Serializable workflow state available for future persistence."""

    execution_id: str = Field(default_factory=lambda: str(uuid4()))
    project: str
    workflow: str = "test_specification"
    status: WorkflowStatus = "running"
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    agent_executions: list[AgentExecutionRecord]
    intermediate_outputs: dict[str, str] = Field(default_factory=dict)
    final_reviewed_output: str | None = None
    error: AgentExecutionError | None = None
    summary: WorkflowExecutionSummary


class ExecutionContext:
    """Mutates and exposes a workflow execution record."""

    def __init__(
        self,
        project: str,
        steps: list[tuple[str, str, str, str]],
    ) -> None:
        self.execution = WorkflowExecution(
            project=project,
            agent_executions=[
                AgentExecutionRecord(
                    key=key,
                    role=role,
                    label=label,
                    agent_id=agent_id,
                )
                for key, role, label, agent_id in steps
            ],
            summary=WorkflowExecutionSummary(
                completed_agents=0,
                failed_agents=0,
                skipped_agents=0,
            ),
        )

    def start(self, record: AgentExecutionRecord) -> None:
        record.status = "running"
        record.started_at = utc_now()

    def complete(
        self,
        record: AgentExecutionRecord,
        output_key: str,
        output: str,
    ) -> None:
        completed_at = utc_now()
        record.status = "completed"
        record.completed_at = completed_at
        record.duration_seconds = self._duration(record.started_at, completed_at)
        record.output = output
        self.execution.intermediate_outputs[output_key] = output
        self.execution.summary.completed_agents += 1

    def fail(
        self,
        record: AgentExecutionRecord,
        error: AgentExecutionError,
    ) -> None:
        completed_at = utc_now()
        record.status = "failed"
        record.completed_at = completed_at
        record.duration_seconds = self._duration(record.started_at, completed_at)
        record.error = error
        self.execution.status = "failed"
        self.execution.error = error
        self.execution.summary.failed_agents += 1
        self.execution.summary.failed_stage = record.label

    def skip_pending(self) -> None:
        for record in self.execution.agent_executions:
            if record.status == "pending":
                record.status = "skipped"
                self.execution.summary.skipped_agents += 1

    def finish(self) -> None:
        if self.execution.status != "failed":
            self.execution.status = "completed"
            self.execution.final_reviewed_output = self.execution.intermediate_outputs.get(
                "reviewed_testspec"
            )
        completed_at = utc_now()
        self.execution.completed_at = completed_at
        self.execution.duration_seconds = self._duration(
            self.execution.started_at, completed_at
        )

    @staticmethod
    def _duration(started_at: datetime | None, completed_at: datetime) -> float:
        if started_at is None:
            return 0.0
        return (completed_at - started_at).total_seconds()
