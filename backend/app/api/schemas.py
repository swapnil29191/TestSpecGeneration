"""Pydantic request models for application APIs."""

from pydantic import BaseModel, Field, field_validator


class WorkflowRequest(BaseModel):
    """Input for the complete test specification workflow."""

    project: str = Field(min_length=1, max_length=100)
    requirements: str = Field(min_length=1)

    @field_validator("project", "requirements")
    @classmethod
    def reject_blank_values(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty")
        return stripped
