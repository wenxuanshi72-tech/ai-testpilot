from __future__ import annotations

import pytest

from plugin.backend.app.constraints import (
    ConstraintParseError,
    extract_username_minimum_constraint,
    parse_number_token,
)


def _requirement(excerpt: str) -> dict[str, object]:
    return {
        "requirement_id": "REQ-GENERIC-001",
        "source_block_id": "BLK-L0001-L0001-0123456789",
        "source_excerpt": excerpt,
    }


@pytest.mark.parametrize(
    "excerpt",
    [
        "Username minimum 6 characters.",
        "Username minimum six characters.",
        "Username must contain at least 6 characters.",
        "Username must contain at least six characters.",
        "Username must contain six or more characters.",
        "用户名至少6位。",
        "用户名至少六位。",
        "Username must contain at least ６ characters.",
        "USERNAME must contain at\u00a0least\u20036 characters.",
        "The minimum username length is six.",
        "The minimum username length of six is required.",
        "Username may contain no fewer than six characters.",
    ],
)
def test_supported_username_minimum_forms(excerpt: str) -> None:
    constraint = extract_username_minimum_constraint(_requirement(excerpt))
    assert constraint is not None
    assert constraint.field == "username"
    assert constraint.operator == "greater_than_or_equal"
    assert constraint.value == 6
    assert constraint.unit == "characters"


@pytest.mark.parametrize(
    "excerpt",
    [
        "Username maximum six characters.",
        "Username must contain less than six characters.",
        "Username must contain fewer than six characters.",
        "Username must contain exactly six characters.",
        "Password must contain at least six characters.",
        "Username is required. The project contains 6 endpoints.",
        "Username must contain at least six.",
        "Username must contain at least half a dozen characters.",
    ],
)
def test_non_minimum_unrelated_or_incomplete_forms_do_not_pass(excerpt: str) -> None:
    assert extract_username_minimum_constraint(_requirement(excerpt)) is None


def test_constraint_parts_are_not_joined_across_requirements() -> None:
    requirements = [
        _requirement("Username is required."),
        {
            **_requirement("Password must contain at least six characters."),
            "requirement_id": "REQ-GENERIC-002",
        },
    ]
    assert all(extract_username_minimum_constraint(item) is None for item in requirements)


def test_missing_source_evidence_does_not_pass() -> None:
    requirement = _requirement("Username must contain at least six characters.")
    requirement["source_block_id"] = ""
    assert extract_username_minimum_constraint(requirement) is None


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("6", 6),
        ("６", 6),
        ("six", 6),
        ("twenty-six", 26),
        ("one hundred six", 106),
        ("六", 6),
        ("二十六", 26),
        ("一百零六", 106),
    ],
)
def test_general_bounded_number_parser(token: str, expected: int) -> None:
    assert parse_number_token(token) == expected


@pytest.mark.parametrize("token", ["dozen", "half", "many", "ten thousand"])
def test_unsupported_number_expression_is_explicit(token: str) -> None:
    with pytest.raises(ConstraintParseError):
        parse_number_token(token)
