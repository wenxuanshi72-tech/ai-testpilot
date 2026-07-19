from __future__ import annotations

import copy

import pytest

from plugin.backend.app.source_blocks import (
    SourceBlockError,
    build_source_blocks,
    resolve_excerpt,
    validate_source_references,
)


def _document() -> str:
    return (
        "# Authentication\n\n"
        "## Security\n\n"
        "Passwords are never stored in plaintext.\n"
        "Cookies are restricted to approved browser contexts.\n"
        "Tokens are stored only as hashes.\n\n"
        "## Sessions\n\n"
        "Sessions expire after thirty minutes.\n"
    )


def _payload(block_id: str, excerpt: str) -> dict[str, object]:
    return {
        "batch_id": "BAT-001",
        "source_sections": ["## Security"],
        "requirements": [
            {
                "requirement_id": "REQ-SEC-001",
                "source_block_id": block_id,
                "source_excerpt": excerpt,
            }
        ],
        "unsupported": [],
        "reported_count": 1,
        "batch_complete": True,
    }


def test_exact_contiguous_excerpt_passes() -> None:
    document = _document()
    batch = (
        "## Security\n\nPasswords are never stored in plaintext.\n"
        "Cookies are restricted to approved browser contexts.\n"
        "Tokens are stored only as hashes."
    )
    blocks = build_source_blocks(document, batch)
    block = blocks[1]
    payload = _payload(block.block_id, "Passwords are never stored in plaintext.")
    audits = validate_source_references(payload, blocks, document)
    assert audits[0]["resolution_type"] == "exact"


@pytest.mark.parametrize(
    ("excerpt", "reason"),
    [
        ("Passwords must not be saved as plain text.", "SOURCE_EXCERPT_NOT_FOUND"),
        (
            "Passwords are never stored in plaintext. Tokens are stored only as hashes.",
            "SOURCE_EXCERPT_NOT_FOUND",
        ),
    ],
)
def test_paraphrase_and_non_contiguous_join_fail(excerpt: str, reason: str) -> None:
    document = _document()
    batch = (
        "## Security\n\nPasswords are never stored in plaintext.\n"
        "Cookies are restricted to approved browser contexts.\n"
        "Tokens are stored only as hashes."
    )
    blocks = build_source_blocks(document, batch)
    payload = _payload(blocks[1].block_id, excerpt)
    with pytest.raises(SourceBlockError, match=reason):
        validate_source_references(payload, blocks, document)


def test_wrong_block_id_and_excerpt_outside_selected_block_fail() -> None:
    document = _document()
    blocks = build_source_blocks(document, document.strip())
    payload = _payload("BLK-L9999-L9999-0000000000", "Passwords are never stored in plaintext.")
    with pytest.raises(SourceBlockError, match="SOURCE_BLOCK_NOT_FOUND"):
        validate_source_references(payload, blocks, document)
    payload = _payload(blocks[-1].block_id, "Passwords are never stored in plaintext.")
    with pytest.raises(SourceBlockError, match="SOURCE_EXCERPT_NOT_FOUND"):
        validate_source_references(payload, blocks, document)


def test_line_endings_and_unique_unicode_whitespace_are_reversible() -> None:
    assert resolve_excerpt("first\r\nsecond", "first\nsecond").valid
    resolution = resolve_excerpt("Café\u00a0account", "Cafe\u0301 account")
    assert resolution.valid
    assert resolution.resolution_type == "normalized_equivalent"
    assert resolution.resolved_excerpt == "Café\u00a0account"


def test_duplicate_normalized_text_is_not_silently_repaired() -> None:
    resolution = resolve_excerpt("same  text / same\ttext", "same text")
    assert not resolution.valid
    assert resolution.reason == "AMBIGUOUS_NORMALIZED_MATCH"


def test_unsupported_is_a_validation_failure_and_never_a_requirement() -> None:
    document = _document()
    blocks = build_source_blocks(document, document.strip())
    payload = _payload(blocks[1].block_id, "Passwords are never stored in plaintext.")
    payload["requirements"] = []
    payload["reported_count"] = 0
    payload["unsupported"] = [
        {
            "source_block_id": None,
            "statement": "A claim without continuous support.",
            "reason": "no_continuous_source",
        }
    ]
    with pytest.raises(SourceBlockError, match="UNSUPPORTED_SOURCE_PRESENT") as captured:
        validate_source_references(copy.deepcopy(payload), blocks, document)
    assert captured.value.audits[0]["resolution_type"] == "unsupported"
