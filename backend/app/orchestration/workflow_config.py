"""Declarative configuration for sequential agent workflows."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WorkflowStep:
    """One sequential stage in an agent workflow."""

    key: str
    role: str
    label: str
    output_key: str
    instruction: str
    dependencies: tuple[str, ...] = ()
    mandatory: bool = True

    def build_input(
        self,
        project: str,
        requirements: str,
        prior_outputs: dict[str, str],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "task": self.instruction,
            "project": project,
            "requirements": requirements,
        }
        for dependency in self.dependencies:
            payload[dependency] = prior_outputs[dependency]
        return payload


TEST_SPECIFICATION_WORKFLOW = (
    WorkflowStep(
        key="requirement_analyzer",
        role="requirement_analyzer",
        label="Requirement Analyzer",
        output_key="requirement_analysis",
        instruction=(
            "Analyze the complete requirement set for completeness, ambiguity, missing "
            "preconditions and postconditions, unclear operating conditions, testability, "
            "interfaces, dependencies, constraints, conflicts, clarification questions, "
            "and safety-related verification gaps. Do not invent missing behavior."
        ),
    ),
    WorkflowStep(
        key="feature_analyzer",
        role="feature_analyzer",
        label="Feature Context Analyzer",
        output_key="feature_analysis",
        dependencies=("requirement_analysis",),
        instruction=(
            "Analyze feature behavior and operating modes using the original requirements "
            "and requirement analysis. Identify interfaces, dependencies, interactions, "
            "positive and negative scenarios, boundary conditions, diagnostics, NVM, "
            "communication, safety considerations, and corner cases. Use the knowledge "
            "available to this agent without inventing requirements."
        ),
    ),
    WorkflowStep(
        key="testspec_generator",
        role="testspec_generator",
        label="Test Specification Generator",
        output_key="generated_testspec",
        dependencies=("requirement_analysis", "feature_analysis"),
        instruction=(
            "Generate detailed automotive test specifications with traceability, positive "
            "and negative coverage, boundary and transition scenarios, justified fault "
            "injection, preconditions, steps, expected results, verification method, test "
            "type, available ASIL classification, assumptions, and open questions. Preserve "
            "source requirements and do not invent unsupported expected behavior."
        ),
    ),
    WorkflowStep(
        key="testspec_reviewer",
        role="testspec_reviewer",
        label="Test Specification Reviewer",
        output_key="reviewed_testspec",
        dependencies=("requirement_analysis", "feature_analysis", "generated_testspec"),
        instruction=(
            "Review the generated test specifications for requirement coverage, traceability, "
            "corner cases, negative and boundary scenarios, duplicates, ambiguous steps, "
            "expected-result quality, unsupported assumptions, and safety gaps. Return the "
            "reviewed specifications, findings, required corrections, and overall status. "
            "Do not silently modify requirements or invent expected behavior."
        ),
    ),
)
