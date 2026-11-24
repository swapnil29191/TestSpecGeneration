"""Read Excel requirement export workbooks into raw tabular rows.

Deliberately generic: unlike a single fixed DNG template, uploaded files may come from
System, Software or Supporting/Interface exports with different sheet layouts, so every
non-empty sheet is read rather than assuming one canonical sheet name.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any

import openpyxl

from backend.app.ingestion.exceptions import RequirementIngestionError

# Sheets that are DNG export scaffolding, not requirement data.
DEFAULT_SKIP_SHEETS = {"TableDetails", "Cover", "ReadMe", "Legend"}

# DNG appends a metadata footer below the real data; once the first column hits this
# marker, that row and everything below it on the sheet is export scaffolding, not data.
METADATA_MARKER = "METADATA"


def read_workbook(
    content: bytes,
    file_name: str,
    *,
    header_row: int = 1,
    skip_sheets: set[str] | None = None,
) -> dict[str, tuple[list[str], list[tuple[int, dict[str, Any]]]]]:
    """Parse every data sheet of an in-memory ``.xlsx``/``.xlsm`` workbook.

    Args:
        content: raw workbook bytes (e.g. from an uploaded file).
        file_name: original file name, used only for error messages.
        header_row: 1-based row holding column headers on each sheet.
        skip_sheets: sheet names to ignore (defaults to ``DEFAULT_SKIP_SHEETS``).

    Returns:
        Mapping of ``sheet_name -> (headers, rows)`` where ``rows`` is a list of
        ``(excel_row_number, {column_header: cell_value})`` for every non-blank row.

    Raises:
        RequirementIngestionError: if the workbook cannot be opened or has no usable sheets.
    """
    skip = skip_sheets if skip_sheets is not None else DEFAULT_SKIP_SHEETS
    try:
        workbook = openpyxl.load_workbook(BytesIO(content), data_only=True, read_only=True)
    except Exception as exc:
        raise RequirementIngestionError(f"Cannot open '{file_name}': {exc}") from exc

    sheets: dict[str, tuple[list[str], list[tuple[int, dict[str, Any]]]]] = {}
    try:
        for sheet_name in workbook.sheetnames:
            if sheet_name in skip:
                continue
            worksheet = workbook[sheet_name]
            try:
                header_cells = next(worksheet.iter_rows(min_row=header_row, max_row=header_row))
            except StopIteration:
                continue
            headers = [
                str(cell.value).strip() if cell.value is not None else ""
                for cell in header_cells
            ]
            if not any(headers):
                continue

            rows: list[tuple[int, dict[str, Any]]] = []
            for excel_row, values in enumerate(
                worksheet.iter_rows(min_row=header_row + 1, values_only=True),
                start=header_row + 1,
            ):
                if all(value is None for value in values):
                    continue
                first_value = values[0] if values else None
                if first_value is not None and METADATA_MARKER in str(first_value).strip().upper():
                    break
                row_dict = {header: value for header, value in zip(headers, values, strict=False) if header}
                rows.append((excel_row, row_dict))

            if rows:
                sheets[sheet_name] = (headers, rows)
    finally:
        workbook.close()

    if not sheets:
        raise RequirementIngestionError(
            f"'{file_name}' has no readable requirement data "
            f"(all sheets were empty or skipped: {sorted(skip)})."
        )
    return sheets
