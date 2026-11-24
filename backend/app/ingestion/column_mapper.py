"""Map arbitrary DNG export column headers to canonical requirement fields.

Different System / Software / Supporting-Interface exports (and different DNG module
configurations) rarely use identical column names, so headers are matched against a set of
known aliases rather than a single expected schema. Unmatched columns are preserved verbatim
in each requirement's ``attributes`` so no exported information is silently dropped.
"""

from __future__ import annotations

import re

# canonical field -> accepted source header variants (case/whitespace-insensitive).
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "requirement_id": (
        "id", "requirement id", "artifact id", "req id", "dng id", "identifier",
    ),
    "requirement_text": (
        "requirement text", "primary text", "text", "description", "requirement description",
        "req text",
    ),
    "requirement_name": (
        "name", "artifact name", "title", "heading",
    ),
    "artifact_type": (
        "artifact type", "type", "requirement type",
    ),
    "parent_requirement_id": (
        "parent", "parent id", "parent requirement", "parent link", "parent artifact",
    ),
    "status": (
        "status", "requirement status",
    ),
    "verification_criteria": (
        "verification criteria", "acceptance criteria", "pass fail criteria",
    ),
    "verification_level": (
        "verification level", "verification method", "test level",
    ),
    "module": (
        "module", "component", "subsystem",
    ),
    "references": (
        "linked resources", "links", "satisfies", "satisfied by", "validates",
        "validated by", "related requirements", "references", "trace links", "traces to",
    ),
}


def _normalize_header(header: str) -> str:
    return re.sub(r"[\s_\-]+", " ", header.strip().lower())


_ALIAS_LOOKUP: dict[str, str] = {
    _normalize_header(alias): field
    for field, aliases in FIELD_ALIASES.items()
    for alias in aliases
}


def map_headers(headers: list[str]) -> dict[str, str]:
    """Return ``{canonical_field: original_header}`` for every header that matches a known alias.

    Headers with no known alias are intentionally omitted here; callers keep them as
    free-form attributes so uncommon/custom DNG columns are never lost.
    """
    mapped: dict[str, str] = {}
    for header in headers:
        if not header:
            continue
        canonical = _ALIAS_LOOKUP.get(_normalize_header(header))
        if canonical and canonical not in mapped:
            mapped[canonical] = header
    return mapped
