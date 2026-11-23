"""Process-wide in-memory workflow execution snapshots, enabling status polling."""

from backend.app.orchestration.execution_context import WorkflowExecution


class ExecutionStore:
    """Keeps the latest snapshot of each workflow execution in memory."""

    def __init__(self) -> None:
        self._executions: dict[str, WorkflowExecution] = {}

    def save(self, execution: WorkflowExecution) -> None:
        self._executions[execution.execution_id] = execution.model_copy(deep=True)

    def get(self, execution_id: str) -> WorkflowExecution | None:
        return self._executions.get(execution_id)
