"""
Devmate_AI pipeline orchestrator.

Same prompt/validation/file-writing logic as DIA_AI (reused directly to avoid
duplication) — only the API call itself differs: Devmate returns plain text
instead of a JSON envelope.
"""

import logging
from pathlib import Path
from typing import Optional

from VTT_Gen import TestCase, TSUMetadata
from DIA_AI.main import (
    SYSTEM_CONTEXT,
    SYSTEM_CONTEXT_UPDATE,
    build_capl_prompt,
    extract_capl_code,
    enforce_testfunction_name,
    prepend_step_header,
    validate_testcase_metadata,
    validate_capl_syntax,
    write_cin_file,
    write_combined_can,
)
from .client import DevmateClient

logger = logging.getLogger(__name__)


def generate_capl_for_testcase(
    tc: TestCase,
    metadata: TSUMetadata,
    api_client: DevmateClient,
    output_dir: Path,
    existing_code: Optional[str] = None,
    system_context: Optional[str] = None,
) -> Optional[str]:
    """End-to-end: validate, prompt, API call, extract, return CAPL code.

    Returns the extracted CAPL code string on success, or None on failure.
    """
    validate_testcase_metadata(tc, metadata)

    prompt = build_capl_prompt(tc, metadata, existing_code=existing_code)
    context = system_context or (SYSTEM_CONTEXT_UPDATE if existing_code else SYSTEM_CONTEXT)
    full_prompt = f"{context}\n\n{prompt}"

    logger.info(
        "Sending prompt for %s (prompt length: %d chars, mode: %s)",
        tc.common_id, len(full_prompt), "update" if existing_code else "generate",
    )
    raw_text = api_client.send_prompt(full_prompt)

    if not raw_text or len(raw_text.strip()) < 20:
        logger.error("Empty or very short response for %s (length=%d)", tc.common_id, len(raw_text or ""))
        return None

    code = extract_capl_code(raw_text)
    code = enforce_testfunction_name(code, tc.full_name)
    code = prepend_step_header(code, tc)

    try:
        validate_capl_syntax(code)
    except SyntaxError as exc:
        logger.warning(
            "Syntax validation failed for %s: %s — saving as .cin.invalid",
            tc.common_id, exc,
        )
        invalid_path = output_dir / f"{tc.common_id}.cin.invalid"
        invalid_path.parent.mkdir(parents=True, exist_ok=True)
        invalid_path.write_text(code, encoding="utf-8")
        return None

    logger.info("CAPL generated for %s (%d chars)", tc.common_id, len(code))
    return code
