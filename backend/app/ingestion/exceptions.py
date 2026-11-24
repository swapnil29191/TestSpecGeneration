"""Safe, non-sensitive errors for the requirement ingestion pipeline."""

from __future__ import annotations


class RequirementIngestionError(Exception):
    """Raised for unrecoverable Excel/workbook problems (bad file, no sheets, etc.)."""
