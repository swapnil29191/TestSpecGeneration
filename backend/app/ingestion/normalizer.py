"""Normalize one worksheet's raw rows into StandardRequirement objects."""

from __future__ import annotations

from typing import Any

from backend.app.ingestion.column_mapper import map_headers
from backend.app.ingestion.schemas import Finding, StandardRequirement, Traceability

_HEADING_LIKE_MARKERS = ("heading", "information", "constraint")


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _split_references(raw: Any) -> list[str]:
    if raw is None:
        return []
    text = str(raw).strip()
    if not text:
        return []
    for sep in (";", ",", "\n", "|"):
        if sep in text:
            return [part.strip() for part in text.split(sep) if part.strip()]
    return [text]


def _derive_level(artifact_type: str, default_category: str) -> tuple[str | None, str]:
    """Return ``(requirement_level, category)`` from the Artifact Type column, if present."""
    upper = artifact_type.upper()
    if upper.startswith("SYS"):
        return "SYSTEM", "system"
    if upper.startswith("SW"):
        return "SOFTWARE", "software"
    if artifact_type:
        return artifact_type.upper(), default_category
    return None, default_category


def normalize_sheet(
    headers: list[str],
    rows: list[tuple[int, dict[str, Any]]],
    *,
    file_name: str,
    sheet_name: str,
    default_category: str,
) -> tuple[list[StandardRequirement], list[Finding]]:
    """Convert raw ``(row_number, {header: value})`` rows into ``StandardRequirement`` objects.

    Args:
        headers: ordered column headers for this sheet.
        rows: raw rows as returned by ``excel_reader.read_workbook``.
        file_name: originating Excel file name (traceability).
        sheet_name: originating worksheet name (traceability).
        default_category: category to assign when the Artifact Type column cannot refine it
            (e.g. "system", "software", "supporting_interface", or "unknown").

    Returns:
        requirements: normalized requirement objects (rows with no usable id/text are still
            included so nothing is silently dropped; see findings for details).
        findings: row-level data-quality issues (empty id/text, unrecognised artifact type).
    """
    field_map = map_headers(headers)
    mapped_headers = set(field_map.values())
    findings: list[Finding] = []
    requirements: list[StandardRequirement] = []

    id_col = field_map.get("requirement_id")
    text_col = field_map.get("requirement_text") or field_map.get("requirement_name")
    artifact_col = field_map.get("artifact_type")

    for row_num, raw in rows:
        req_id = _text(raw.get(id_col)) if id_col else ""
        req_text = _text(raw.get(text_col)) if text_col else ""
        artifact_type = _text(raw.get(artifact_col)) if artifact_col else ""

        if not req_id and not req_text:
            # Structurally blank/heading-only row — nothing worth keeping or flagging.
            continue

        level, category = _derive_level(artifact_type, default_category)
        is_heading = any(marker in artifact_type.lower() for marker in _HEADING_LIKE_MARKERS)
        testable = bool(req_text) and not is_heading

        if not req_id:
            findings.append(Finding(
                severity="ERROR",
                message="requirement_id is empty.",
                source_file=file_name,
                sheet_name=sheet_name,
            ))
        if not req_text:
            findings.append(Finding(
                severity="ERROR",
                message="requirement_text is empty.",
                requirement_id=req_id or None,
                source_file=file_name,
                sheet_name=sheet_name,
            ))

        references: list[str] = []
        references_col = field_map.get("references")
        if references_col:
            references = _split_references(raw.get(references_col))

        attributes = {
            header: raw[header]
            for header in headers
            if header and header in raw and header not in mapped_headers
        }

        requirements.append(StandardRequirement(
            requirement_id=req_id,
            requirement_category=category,  # type: ignore[arg-type]
            requirement_level=level,
            requirement_text=req_text,
            parent_requirement_id=_text(raw.get(field_map.get("parent_requirement_id"))) or None,
            references=references,
            status=_text(raw.get(field_map.get("status"))),
            verification_criteria=_text(raw.get(field_map.get("verification_criteria"))),
            verification_level=_text(raw.get(field_map.get("verification_level"))),
            module=_text(raw.get(field_map.get("module"))),
            testable=testable,
            attributes=attributes,
            traceability=Traceability(
                source_file=file_name,
                sheet_name=sheet_name,
                source_row=row_num,
                original_id_column=id_col,
            ),
        ))

    return requirements, findings
