"""Standardized JSON schema for consolidated, multi-source requirements."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

RequirementCategory = Literal["system", "software", "supporting_interface", "unknown"]
FindingSeverity = Literal["ERROR", "WARNING"]


class Traceability(BaseModel):
    """Where a requirement came from, preserved for audit/traceability."""

    source_file: str
    sheet_name: str
    source_row: int
    original_id_column: str | None = None


class StandardRequirement(BaseModel):
    """One requirement normalized to a schema downstream agents can rely on."""

    requirement_id: str
    requirement_category: RequirementCategory
    requirement_level: str | None = None
    requirement_text: str
    parent_requirement_id: str | None = None
    references: list[str] = Field(default_factory=list)
    status: str = ""
    verification_criteria: str = ""
    verification_level: str = ""
    module: str = ""
    testable: bool = True
    attributes: dict[str, Any] = Field(default_factory=dict)
    traceability: Traceability


class Finding(BaseModel):
    """Data-quality issue surfaced during consolidation (never silently discarded)."""

    severity: FindingSeverity
    message: str
    requirement_id: str | None = None
    source_file: str | None = None
    sheet_name: str | None = None


class SourceFileSummary(BaseModel):
    """Per-file ingestion summary for the API response."""

    file_name: str
    category: RequirementCategory
    sheets_read: list[str]
    requirement_count: int


class IngestionMeta(BaseModel):
    feature: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_files: list[SourceFileSummary] = Field(default_factory=list)
    total_requirements: int = 0


class IngestionResult(BaseModel):
    """Consolidated, standardized requirement dataset returned by the ingestion API."""

    meta: IngestionMeta
    requirements: list[StandardRequirement]
    findings: list[Finding]
    has_errors: bool
