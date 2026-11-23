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


class ClarificationAnswers(BaseModel):
    """User answers to the requirement clarifier's open questions."""

    answers: dict[str, str] = Field(default_factory=dict)

    @field_validator("answers")
    @classmethod
    def reject_empty_answers(cls, value: dict[str, str]) -> dict[str, str]:
        if not value:
            raise ValueError("at least one answer must be provided")
        return value

