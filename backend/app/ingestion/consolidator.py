"""Consolidate normalized requirements from multiple files/sheets into one dataset.

Cross-source checks performed here (single-sheet normalization cannot see these):
  - duplicate requirement_id, same or conflicting text, across any file/sheet
  - parent_requirement_id that does not resolve to any ingested requirement
  - whether any testable requirements survived consolidation at all
"""

from __future__ import annotations

from backend.app.ingestion.schemas import Finding, StandardRequirement


def consolidate(
    all_requirements: list[StandardRequirement],
    existing_findings: list[Finding],
) -> tuple[list[StandardRequirement], list[Finding]]:
    """Merge requirements already normalized per-sheet; detect cross-source issues.

    No requirement is dropped — duplicates and broken references are reported as findings
    so a human (or an upstream agent) can resolve them, consistent with the rest of the
    pipeline's "never silently discard" policy.
    """
    findings = list(existing_findings)
    known_ids = {req.requirement_id for req in all_requirements if req.requirement_id}

    first_seen: dict[str, StandardRequirement] = {}
    for req in all_requirements:
        if not req.requirement_id:
            continue
        previous = first_seen.get(req.requirement_id)
        if previous is None:
            first_seen[req.requirement_id] = req
            continue
        same_text = previous.requirement_text.strip() == req.requirement_text.strip()
        findings.append(Finding(
            severity="ERROR" if not same_text else "WARNING",
            requirement_id=req.requirement_id,
            source_file=req.traceability.source_file,
            sheet_name=req.traceability.sheet_name,
            message=(
                f"Duplicate requirement_id '{req.requirement_id}' also found in "
                f"{previous.traceability.source_file}/{previous.traceability.sheet_name}"
                + ("" if same_text else " with different requirement text")
                + "."
            ),
        ))

    for req in all_requirements:
        parent_id = req.parent_requirement_id
        if parent_id and parent_id not in known_ids:
            findings.append(Finding(
                severity="WARNING",
                requirement_id=req.requirement_id or None,
                source_file=req.traceability.source_file,
                sheet_name=req.traceability.sheet_name,
                message=f"parent_requirement_id '{parent_id}' does not match any ingested requirement.",
            ))

    if all_requirements and not any(req.testable for req in all_requirements):
        findings.append(Finding(
            severity="WARNING",
            message="No testable requirements found across any uploaded file.",
        ))

    return all_requirements, findings
