from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import asdict, dataclass
from typing import Any


class SourceBlockError(Exception):
    def __init__(self, code: str, audits: list[dict[str, Any]] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.audits = audits or []


@dataclass(frozen=True)
class SourceBlock:
    block_id: str
    start_line: int
    end_line: int
    text: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExcerptResolution:
    valid: bool
    resolved_excerpt: str | None
    resolution_type: str
    reason: str


def normalize_line_endings(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def build_source_blocks(prd_text: str, batch_text: str) -> list[SourceBlock]:
    document = normalize_line_endings(prd_text)
    bounded = normalize_line_endings(batch_text).strip()
    positions = _all_positions(document, bounded)
    if len(positions) != 1:
        raise SourceBlockError("BATCH_SOURCE_NOT_UNIQUE")
    start = positions[0]
    first_line = document[:start].count("\n") + 1
    lines = bounded.splitlines()
    blocks: list[SourceBlock] = []
    index = 0
    while index < len(lines):
        while index < len(lines) and not lines[index].strip():
            index += 1
        if index >= len(lines):
            break
        block_start = index
        while index < len(lines) and lines[index].strip():
            index += 1
        block_end = index - 1
        text = "\n".join(lines[block_start : block_end + 1])
        start_line = first_line + block_start
        end_line = first_line + block_end
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:10].upper()
        blocks.append(
            SourceBlock(
                block_id=f"BLK-L{start_line:04d}-L{end_line:04d}-{digest}",
                start_line=start_line,
                end_line=end_line,
                text=text,
            )
        )
    if not blocks:
        raise SourceBlockError("NO_SOURCE_BLOCKS")
    return blocks


def resolve_excerpt(block_text: str, model_excerpt: str) -> ExcerptResolution:
    source = normalize_line_endings(block_text)
    excerpt = normalize_line_endings(model_excerpt)
    exact_positions = _all_positions(source, excerpt)
    if len(exact_positions) == 1:
        return ExcerptResolution(True, excerpt, "exact", "EXACT_CONTIGUOUS_MATCH")
    if len(exact_positions) > 1:
        return ExcerptResolution(False, None, "rejected", "AMBIGUOUS_EXACT_MATCH")

    normalized_source, spans = _equivalent_form_with_spans(source)
    normalized_excerpt, _ = _equivalent_form_with_spans(excerpt)
    positions = _all_positions(normalized_source, normalized_excerpt)
    if len(positions) != 1:
        reason = "AMBIGUOUS_NORMALIZED_MATCH" if positions else "SOURCE_EXCERPT_NOT_FOUND"
        return ExcerptResolution(False, None, "rejected", reason)
    start = positions[0]
    end = start + len(normalized_excerpt)
    if not normalized_excerpt or end == 0:
        return ExcerptResolution(False, None, "rejected", "EMPTY_NORMALIZED_EXCERPT")
    original_start = spans[start][0]
    original_end = spans[end - 1][1]
    resolved = source[original_start:original_end]
    return ExcerptResolution(
        True,
        resolved,
        "normalized_equivalent",
        "UNIQUE_NFC_LINE_ENDING_OR_WHITESPACE_EQUIVALENCE",
    )


def validate_source_references(
    parsed: dict[str, Any],
    blocks: list[SourceBlock],
    prd_text: str,
) -> list[dict[str, Any]]:
    block_by_id = {block.block_id: block for block in blocks}
    requirements = parsed.get("requirements")
    if not isinstance(requirements, list):
        raise SourceBlockError("REQUIREMENTS_NOT_ARRAY")
    audits: list[dict[str, Any]] = []
    for requirement in requirements:
        if not isinstance(requirement, dict):
            raise SourceBlockError("REQUIREMENT_NOT_OBJECT", audits)
        requirement_id = str(requirement.get("requirement_id", ""))
        block_id = requirement.get("source_block_id")
        model_excerpt = requirement.get("source_excerpt")
        if not isinstance(block_id, str) or block_id not in block_by_id:
            audits.append(
                _audit(
                    requirement_id,
                    str(block_id or ""),
                    str(model_excerpt or ""),
                    None,
                    "rejected",
                    "SOURCE_BLOCK_NOT_FOUND",
                )
            )
            raise SourceBlockError("SOURCE_BLOCK_NOT_FOUND", audits)
        if not isinstance(model_excerpt, str):
            audits.append(
                _audit(requirement_id, block_id, "", None, "rejected", "SOURCE_EXCERPT_NOT_STRING")
            )
            raise SourceBlockError("SOURCE_EXCERPT_NOT_STRING", audits)
        block = block_by_id[block_id]
        resolution = resolve_excerpt(block.text, model_excerpt)
        audits.append(
            _audit(
                requirement_id,
                block_id,
                model_excerpt,
                resolution.resolved_excerpt,
                resolution.resolution_type,
                resolution.reason,
                block,
            )
        )
        if not resolution.valid or resolution.resolved_excerpt is None:
            raise SourceBlockError(resolution.reason, audits)
        if resolution.resolved_excerpt not in normalize_line_endings(prd_text):
            audits[-1]["resolution_type"] = "rejected"
            audits[-1]["reason"] = "EXCERPT_NOT_IN_PRD_VERSION"
            raise SourceBlockError("EXCERPT_NOT_IN_PRD_VERSION", audits)
        requirement["source_excerpt"] = resolution.resolved_excerpt

    unsupported = parsed.get("unsupported", [])
    if not isinstance(unsupported, list):
        raise SourceBlockError("UNSUPPORTED_NOT_ARRAY", audits)
    for item in unsupported:
        if not isinstance(item, dict):
            raise SourceBlockError("UNSUPPORTED_ITEM_NOT_OBJECT", audits)
        audits.append(
            _audit(
                "",
                str(item.get("source_block_id") or ""),
                str(item.get("statement") or ""),
                None,
                "unsupported",
                str(item.get("reason") or "NO_CONTINUOUS_SOURCE"),
            )
        )
    if unsupported:
        raise SourceBlockError("UNSUPPORTED_SOURCE_PRESENT", audits)
    return audits


def locate_existing_excerpt(
    blocks: list[SourceBlock], excerpt: str, prd_text: str
) -> tuple[SourceBlock, ExcerptResolution]:
    matches: list[tuple[SourceBlock, ExcerptResolution]] = []
    for block in blocks:
        resolution = resolve_excerpt(block.text, excerpt)
        if resolution.valid:
            matches.append((block, resolution))
    if len(matches) != 1:
        reason = "REUSED_EXCERPT_AMBIGUOUS" if matches else "REUSED_EXCERPT_NOT_FOUND"
        raise SourceBlockError(reason)
    block, resolution = matches[0]
    resolved_excerpt = resolution.resolved_excerpt
    if resolved_excerpt is None or resolved_excerpt not in normalize_line_endings(prd_text):
        raise SourceBlockError("REUSED_EXCERPT_NOT_IN_PRD")
    return block, resolution


def _audit(
    requirement_id: str,
    block_id: str,
    model_excerpt: str,
    resolved_excerpt: str | None,
    resolution_type: str,
    reason: str,
    block: SourceBlock | None = None,
) -> dict[str, Any]:
    return {
        "requirement_id": requirement_id,
        "source_block_id": block_id,
        "model_excerpt": model_excerpt,
        "resolved_excerpt": resolved_excerpt,
        "resolution_type": resolution_type,
        "reason": reason,
        "block_start_line": block.start_line if block else None,
        "block_end_line": block.end_line if block else None,
    }


def _all_positions(haystack: str, needle: str) -> list[int]:
    if not needle:
        return []
    positions: list[int] = []
    start = 0
    while True:
        found = haystack.find(needle, start)
        if found < 0:
            return positions
        positions.append(found)
        start = found + 1


def _equivalent_form_with_spans(value: str) -> tuple[str, list[tuple[int, int]]]:
    value = normalize_line_endings(value)
    output: list[str] = []
    spans: list[tuple[int, int]] = []
    index = 0
    while index < len(value):
        if value[index].isspace():
            end = index + 1
            while end < len(value) and value[end].isspace():
                end += 1
            output.append(" ")
            spans.append((index, end))
            index = end
            continue
        end = index + 1
        while end < len(value) and unicodedata.combining(value[end]):
            end += 1
        normalized = unicodedata.normalize("NFC", value[index:end])
        for character in normalized:
            output.append(character)
            spans.append((index, end))
        index = end
    return "".join(output), spans
