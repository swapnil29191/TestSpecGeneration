"""Multi-file Excel requirement ingestion endpoint (DNG exports -> standardized JSON)."""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.app.ingestion.pipeline import UploadedExcelFile, ingest_files
from backend.app.ingestion.schemas import IngestionResult, RequirementCategory

router = APIRouter(prefix="/requirements", tags=["requirements"])

_ALLOWED_EXTENSIONS = (".xlsx", ".xlsm")
_MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB per file; generous for DNG exports, bounds memory use.
_VALID_CATEGORIES = {"system", "software", "supporting_interface", "unknown"}


@router.post("/ingest", response_model=IngestionResult)
async def ingest_requirement_files(
    files: list[UploadFile] = File(..., description="One or more Excel requirement exports."),
    categories: list[str] | None = Form(
        None,
        description="Optional requirement category per file, same order as 'files' "
        "(system, software, supporting_interface). Use an empty string, or omit the field "
        "entirely, to auto-detect a file's category from its name.",
    ),
    feature: str | None = Form(None, description="Feature/chapter name to record in the result."),
) -> IngestionResult:
    if not files:
        raise HTTPException(status_code=422, detail="At least one Excel file must be uploaded.")

    if categories is not None and len(categories) != len(files):
        raise HTTPException(
            status_code=422,
            detail=f"Got {len(categories)} categories for {len(files)} files; "
            "provide one category per file or omit the field entirely.",
        )
    if categories is not None:
        invalid = sorted({value for value in categories if value and value not in _VALID_CATEGORIES})
        if invalid:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid categories {invalid}. Allowed: {sorted(_VALID_CATEGORIES)} or ''.",
            )

    uploaded: list[UploadedExcelFile] = []
    for index, upload in enumerate(files):
        file_name = upload.filename or f"file_{index + 1}.xlsx"
        if not file_name.lower().endswith(_ALLOWED_EXTENSIONS):
            raise HTTPException(
                status_code=422,
                detail=f"'{file_name}' is not a supported Excel file "
                f"({', '.join(_ALLOWED_EXTENSIONS)} only).",
            )
        content = await upload.read()
        if not content:
            raise HTTPException(status_code=422, detail=f"'{file_name}' is empty.")
        if len(content) > _MAX_FILE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"'{file_name}' exceeds the {_MAX_FILE_BYTES // (1024 * 1024)} MB upload limit.",
            )
        category: RequirementCategory | None = categories[index] if categories else None  # type: ignore[assignment]
        category = category or None
        uploaded.append(UploadedExcelFile(file_name=file_name, content=content, category=category))

    return ingest_files(uploaded, feature=feature)
