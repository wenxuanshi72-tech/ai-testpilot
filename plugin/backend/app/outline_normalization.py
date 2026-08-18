from __future__ import annotations

import copy
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

SECTION_ID_PATTERN = re.compile(r"^SEC-[A-Za-z0-9_-]{1,64}$")
_BARE_NUMBER = re.compile(r"^[0-9]+$")
_SAFE_BODY = re.compile(r"^[A-Za-z0-9]+(?:[ _-]+[A-Za-z0-9]+)*$")


class OutlineNormalizationError(ValueError):
    pass


@dataclass(frozen=True)
class SectionIdNormalizationAudit:
    section_index: int
    original_section_id: str
    normalized_section_id: str
    reason: str


def _normalize_one(value: Any) -> tuple[str, str | None]:
    if not isinstance(value, str) or not value.strip():
        raise OutlineNormalizationError("SECTION_ID_EMPTY_OR_NOT_STRING")
    if SECTION_ID_PATTERN.fullmatch(value):
        return value, None
    canonical = unicodedata.normalize("NFKC", value).strip()
    if _BARE_NUMBER.fullmatch(canonical):
        number = int(canonical)
        if number < 1:
            raise OutlineNormalizationError("SECTION_ID_NUMBER_OUT_OF_RANGE")
        normalized = f"SEC-{number:03d}"
        if len(normalized.removeprefix("SEC-")) > 64:
            raise OutlineNormalizationError("SECTION_ID_TOO_LONG")
        return normalized, "bare_positive_integer"
    without_prefix = re.sub(r"(?i)^sec[ _-]+", "", canonical)
    if not without_prefix or not _SAFE_BODY.fullmatch(without_prefix):
        raise OutlineNormalizationError("SECTION_ID_HAS_AMBIGUOUS_CHARACTERS")
    body = re.sub(r"[ _-]+", "-", without_prefix).upper()
    normalized = f"SEC-{body}"
    if not SECTION_ID_PATTERN.fullmatch(normalized):
        raise OutlineNormalizationError("SECTION_ID_CANNOT_BE_NORMALIZED")
    return normalized, "safe_ascii_slug"


def normalize_outline_section_ids(
    outline: dict[str, Any],
) -> tuple[dict[str, Any], list[SectionIdNormalizationAudit]]:
    normalized = copy.deepcopy(outline)
    sections = normalized.get("sections")
    if not isinstance(sections, list) or not sections:
        raise OutlineNormalizationError("OUTLINE_SECTIONS_MISSING")
    audits: list[SectionIdNormalizationAudit] = []
    seen: dict[str, int] = {}
    for index, section in enumerate(sections):
        if not isinstance(section, dict):
            raise OutlineNormalizationError("OUTLINE_SECTION_NOT_OBJECT")
        original = section.get("section_id")
        accepted, reason = _normalize_one(original)
        if accepted in seen:
            raise OutlineNormalizationError(
                f"SECTION_ID_COLLISION:{seen[accepted]}:{index}:{accepted}"
            )
        seen[accepted] = index
        section["section_id"] = accepted
        if reason is not None:
            audits.append(SectionIdNormalizationAudit(index, str(original), accepted, reason))
    return normalized, audits
