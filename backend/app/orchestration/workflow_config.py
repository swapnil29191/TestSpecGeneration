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
            # Optional dependencies (e.g. historical context) may not have run.
            payload[dependency] = prior_outputs.get(dependency, "")
        return payload


TEST_SPECIFICATION_WORKFLOW = (
    WorkflowStep(
        key="historical_context",
        role="historical_context_agent",
        label="Historical Project Context",
        output_key="historical_context",
        mandatory=False,
        instruction=(
            "Using knowledge available to this agent from previously completed similar "
            "automotive projects, identify requirement gaps, ambiguities and clarification "
            "points already resolved in earlier similar projects that are directly relevant "
            "to the requirements provided. State clearly when nothing relevant is found. "
            "Do not invent project history that is not actually known."
        ),
    ),
    WorkflowStep(
        key="requirement_clarifier",
        role="requirement_clarifier",
        label="Requirement Clarifier",
        output_key="requirement_clarification",
        dependencies=("historical_context",),
        instruction=(
            "Using the original requirements and any historical project context, determine "
            "whether the requirements are sufficiently clear to proceed to analysis. Respond "
            "with strict JSON only, no prose, no markdown fences, in the exact form "
            '{"status": "clear" | "needs_clarification", '
            '"resolved_from_history": [string, ...], "open_questions": [string, ...]}. '
            "Only list questions that could not be resolved from historical context. Set "
            'status to "clear" only when open_questions is empty.'
        ),
    ),
    WorkflowStep(
        key="requirement_analyzer",
        role="requirement_analyzer",
        label="Requirement Analyzer",
        output_key="requirement_analysis",
        dependencies=("historical_context", "requirement_clarification", "clarification_answers"),
        instruction=(
            "Analyze the complete requirement set for completeness, ambiguity, missing "
            "preconditions and postconditions, unclear operating conditions, testability, "
            "interfaces, dependencies, constraints, conflicts, clarification questions, "
            "and safety-related verification gaps. Treat the supplied historical context "
            "and any user-provided clarification answers as authoritative context. Do not "
            "invent missing behavior."
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
