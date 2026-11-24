"""Top-level orchestration: multiple uploaded Excel files -> consolidated IngestionResult."""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.ingestion.consolidator import consolidate
from backend.app.ingestion.exceptions import RequirementIngestionError
from backend.app.ingestion.excel_reader import read_workbook
from backend.app.ingestion.normalizer import normalize_sheet
from backend.app.ingestion.schemas import (
    Finding,
    IngestionMeta,
    IngestionResult,
    RequirementCategory,
    SourceFileSummary,
    StandardRequirement,
)

_CATEGORY_KEYWORDS: tuple[tuple[str, RequirementCategory], ...] = (
    ("system", "system"),
    ("sys", "system"),
    ("software", "software"),
    ("sw", "software"),
    ("interface", "supporting_interface"),
    ("supporting", "supporting_interface"),
)


@dataclass
class UploadedExcelFile:
    """One uploaded requirement export, as received by the API layer."""

    file_name: str
    content: bytes
    category: RequirementCategory | None = None


def infer_category(file_name: str) -> RequirementCategory:
    """Best-effort category guess from the file name when the caller did not specify one."""
    lowered = file_name.lower()
    for keyword, category in _CATEGORY_KEYWORDS:
        if keyword in lowered:
            return category
    return "unknown"


def ingest_files(
    files: list[UploadedExcelFile],
    *,
    feature: str | None = None,
) -> IngestionResult:
    """Parse, normalize and consolidate one or more uploaded Excel requirement exports.

    A failure reading one file (corrupt workbook, no data) is reported as an ERROR finding
    for that file without discarding results already extracted from the other files.
    """
    all_requirements: list[StandardRequirement] = []
    findings: list[Finding] = []
    source_summaries: list[SourceFileSummary] = []

    for uploaded in files:
        category = uploaded.category or infer_category(uploaded.file_name)
        try:
            sheets = read_workbook(uploaded.content, uploaded.file_name)
        except RequirementIngestionError as exc:
            findings.append(Finding(
                severity="ERROR",
                source_file=uploaded.file_name,
                message=str(exc),
            ))
            source_summaries.append(SourceFileSummary(
                file_name=uploaded.file_name,
                category=category,
                sheets_read=[],
                requirement_count=0,
            ))
            continue

        file_requirements: list[StandardRequirement] = []
        for sheet_name, (headers, rows) in sheets.items():
            sheet_requirements, sheet_findings = normalize_sheet(
                headers,
                rows,
                file_name=uploaded.file_name,
                sheet_name=sheet_name,
                default_category=category,
            )
            file_requirements.extend(sheet_requirements)
            findings.extend(sheet_findings)

        all_requirements.extend(file_requirements)
        source_summaries.append(SourceFileSummary(
            file_name=uploaded.file_name,
            category=category,
            sheets_read=list(sheets.keys()),
            requirement_count=len(file_requirements),
        ))

    all_requirements, findings = consolidate(all_requirements, findings)
    has_errors = any(finding.severity == "ERROR" for finding in findings)

    return IngestionResult(
        meta=IngestionMeta(
            feature=feature,
            source_files=source_summaries,
            total_requirements=len(all_requirements),
        ),
        requirements=all_requirements,
        findings=findings,
        has_errors=has_errors,
    )
