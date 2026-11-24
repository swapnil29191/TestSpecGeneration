"""Tests for the multi-source Excel requirement ingestion pipeline and API."""

from __future__ import annotations

from io import BytesIO

import openpyxl
import pytest
from fastapi.testclient import TestClient

from backend.app.ingestion.pipeline import UploadedExcelFile, ingest_files
from backend.app.main import create_app


def _workbook_bytes(sheet_name: str, headers: list[str], rows: list[list]) -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = sheet_name
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _system_file() -> bytes:
    return _workbook_bytes(
        "Requirements",
        ["ID", "Requirement Text", "Parent", "Status"],
        [
            ["SYS-001", "The gateway shall forward CAN frames within 10 ms.", None, "accepted"],
            ["SYS-002", "The gateway shall log diagnostic events.", None, "accepted"],
        ],
    )


def _software_file() -> bytes:
    return _workbook_bytes(
        "SW Reqs",
        ["Artifact ID", "Primary Text", "Parent Requirement", "Verification Criteria"],
        [
            ["SW-001", "The forwarding module shall queue frames with priority.", "SYS-001", "Unit test"],
            ["SW-002", "The diagnostic logger shall persist events to NVM.", "SYS-999", "Unit test"],
        ],
    )


def test_pipeline_consolidates_files_with_different_column_names() -> None:
    result = ingest_files(
        [
            UploadedExcelFile(file_name="system_requirements.xlsx", content=_system_file()),
            UploadedExcelFile(file_name="software_requirements.xlsx", content=_software_file()),
        ],
        feature="gateway_diagnostics",
    )

    ids = {req.requirement_id for req in result.requirements}
    assert ids == {"SYS-001", "SYS-002", "SW-001", "SW-002"}

    sys_req = next(r for r in result.requirements if r.requirement_id == "SYS-001")
    assert sys_req.requirement_category == "system"
    assert sys_req.traceability.source_file == "system_requirements.xlsx"
    assert sys_req.traceability.sheet_name == "Requirements"

    sw_req = next(r for r in result.requirements if r.requirement_id == "SW-001")
    assert sw_req.requirement_category == "software"
    assert sw_req.parent_requirement_id == "SYS-001"
    assert sw_req.verification_criteria == "Unit test"

    # SW-002's parent (SYS-999) does not exist anywhere -> broken-reference warning.
    broken_ref = [f for f in result.findings if "SYS-999" in f.message]
    assert len(broken_ref) == 1
    assert broken_ref[0].severity == "WARNING"


def test_duplicate_requirement_id_conflicting_text_is_error() -> None:
    file_a = _workbook_bytes("Reqs", ["ID", "Requirement Text"], [["SYS-001", "Text A"]])
    file_b = _workbook_bytes("Reqs", ["ID", "Requirement Text"], [["SYS-001", "Text B (conflicting)"]])

    result = ingest_files([
        UploadedExcelFile(file_name="a.xlsx", content=file_a),
        UploadedExcelFile(file_name="b.xlsx", content=file_b),
    ])

    duplicate_findings = [f for f in result.findings if "Duplicate requirement_id" in f.message]
    assert len(duplicate_findings) == 1
    assert duplicate_findings[0].severity == "ERROR"
    assert result.has_errors is True


def test_duplicate_requirement_id_same_text_is_warning() -> None:
    file_a = _workbook_bytes("Reqs", ["ID", "Requirement Text"], [["SYS-001", "Same text"]])
    file_b = _workbook_bytes("Reqs", ["ID", "Requirement Text"], [["SYS-001", "Same text"]])

    result = ingest_files([
        UploadedExcelFile(file_name="a.xlsx", content=file_a),
        UploadedExcelFile(file_name="b.xlsx", content=file_b),
    ])

    duplicate_findings = [f for f in result.findings if "Duplicate requirement_id" in f.message]
    assert len(duplicate_findings) == 1
    assert duplicate_findings[0].severity == "WARNING"


def test_empty_requirement_id_and_text_flagged() -> None:
    content = _workbook_bytes(
        "Reqs",
        ["ID", "Requirement Text"],
        [["", "Has text but no id"], ["SYS-010", ""]],
    )
    result = ingest_files([UploadedExcelFile(file_name="bad.xlsx", content=content)])

    assert any("requirement_id is empty" in f.message for f in result.findings)
    assert any("requirement_text is empty" in f.message for f in result.findings)
    assert result.has_errors is True


def test_category_auto_detected_from_file_name() -> None:
    result = ingest_files([
        UploadedExcelFile(file_name="software_dump.xlsx", content=_software_file()),
    ])
    assert result.meta.source_files[0].category == "software"
    assert all(req.requirement_category == "software" for req in result.requirements)


def test_explicit_category_overrides_auto_detection() -> None:
    result = ingest_files([
        UploadedExcelFile(
            file_name="unrelated_name.xlsx",
            content=_system_file(),
            category="supporting_interface",
        ),
    ])
    assert all(req.requirement_category == "supporting_interface" for req in result.requirements)


def test_unreadable_workbook_reported_without_blocking_other_files() -> None:
    result = ingest_files([
        UploadedExcelFile(file_name="corrupt.xlsx", content=b"not an excel file"),
        UploadedExcelFile(file_name="system_requirements.xlsx", content=_system_file()),
    ])
    assert any(f.source_file == "corrupt.xlsx" and f.severity == "ERROR" for f in result.findings)
    assert len(result.requirements) == 2


def test_rows_below_metadata_marker_are_ignored() -> None:
    content = _workbook_bytes(
        "Requirements",
        ["ID", "Requirement Text"],
        [
            ["SYS-001", "The gateway shall forward CAN frames within 10 ms."],
            ["METADATA", "Exported by DNG on 2026-11-23"],
            ["SYS-002", "This row is after the marker and must be ignored."],
        ],
    )
    result = ingest_files([UploadedExcelFile(file_name="system_requirements.xlsx", content=content)])
    ids = {req.requirement_id for req in result.requirements}
    assert ids == {"SYS-001"}


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_ingest_endpoint_consolidates_multiple_uploads(client: TestClient) -> None:
    response = client.post(
        "/api/v1/requirements/ingest",
        files=[
            ("files", ("system_requirements.xlsx", _system_file(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
            ("files", ("software_requirements.xlsx", _software_file(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
        ],
        data={"feature": "gateway_diagnostics"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["total_requirements"] == 4
    assert payload["meta"]["feature"] == "gateway_diagnostics"
    assert {s["file_name"] for s in payload["meta"]["source_files"]} == {
        "system_requirements.xlsx",
        "software_requirements.xlsx",
    }


def test_ingest_endpoint_rejects_non_excel_file(client: TestClient) -> None:
    response = client.post(
        "/api/v1/requirements/ingest",
        files=[("files", ("notes.txt", b"plain text", "text/plain"))],
    )
    assert response.status_code == 422


def test_ingest_endpoint_requires_matching_category_count(client: TestClient) -> None:
    response = client.post(
        "/api/v1/requirements/ingest",
        files=[("files", ("system_requirements.xlsx", _system_file(), "application/octet-stream"))],
        data={"categories": ["system", "software"]},
    )
    assert response.status_code == 422
