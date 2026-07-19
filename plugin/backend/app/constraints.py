from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from typing import Any

AGGREGATE_VALIDATOR_VERSION = "aggregate-domain-validator@2.0.1"
LEGACY_AGGREGATE_VALIDATOR_VERSION = "aggregate-domain-validator@2.0.0"


@dataclass(frozen=True)
class NormalizedConstraint:
    field: str
    operator: str
    value: int
    unit: str
    source_requirement_id: str
    source_block_id: str
    source_excerpt: str
    matched_expression: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class ConstraintParseError(Exception):
    pass


def extract_username_minimum_constraint(
    requirement: dict[str, Any],
) -> NormalizedConstraint | None:
    excerpt = requirement.get("source_excerpt")
    requirement_id = requirement.get("requirement_id")
    block_id = requirement.get("source_block_id")
    if (
        not isinstance(excerpt, str)
        or not excerpt
        or not isinstance(requirement_id, str)
        or not requirement_id
        or not isinstance(block_id, str)
        or not block_id
    ):
        return None
    normalized = normalize_constraint_text(excerpt)
    for clause in _clauses(normalized):
        parsed = _parse_english_username_clause(clause) or _parse_chinese_username_clause(clause)
        if parsed is None:
            continue
        value, expression = parsed
        return NormalizedConstraint(
            field="username",
            operator="greater_than_or_equal",
            value=value,
            unit="characters",
            source_requirement_id=requirement_id,
            source_block_id=block_id,
            source_excerpt=excerpt,
            matched_expression=expression,
        )
    return None


def parse_number_token(token: str) -> int:
    normalized = unicodedata.normalize("NFKC", token).strip().casefold()
    if re.fullmatch(r"[0-9]{1,4}", normalized):
        return int(normalized)
    if re.fullmatch(r"[a-z]+(?:[- ][a-z]+)*", normalized):
        return _parse_english_number(normalized)
    if re.fullmatch(r"[零〇一二两三四五六七八九十百千]+", normalized):
        return _parse_chinese_number(normalized)
    raise ConstraintParseError("UNSUPPORTED_NUMBER_EXPRESSION")


def normalize_constraint_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"\s+", " ", normalized).strip()


def _clauses(value: str) -> list[str]:
    return [
        clause.strip() for clause in re.split(r"(?<=[.!?。！？;；])\s*", value) if clause.strip()
    ]


_NUMBER = (
    r"(?:[0-9０-９]{1,4}|"
    r"(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|"
    r"twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred)"
    r"(?:[- ](?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|"
    r"twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred))*)"
)


def _parse_english_username_clause(clause: str) -> tuple[int, str] | None:
    patterns = (
        rf"\b(?:minimum|min)\s+username\s+length\s+(?:of|is)\s+(?P<number>{_NUMBER})\b",
        rf"\busername(?:s)?\b.{{0,50}}?\b(?:minimum(?:\s+of)?|at\s+least|"
        rf"no\s+fewer\s+than)\s+(?P<number>{_NUMBER})\s+"
        rf"(?:characters?|chars?|digits?)\b",
        rf"\busername(?:s)?\b.{{0,50}}?\b(?P<number>{_NUMBER})\s+or\s+more\s+"
        rf"(?:characters?|chars?|digits?)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, clause)
        if not match:
            continue
        try:
            value = parse_number_token(match.group("number"))
        except ConstraintParseError:
            return None
        return value, match.group(0)
    return None


def _parse_chinese_username_clause(clause: str) -> tuple[int, str] | None:
    number = r"(?P<number>[0-9０-９]{1,4}|[零〇一二两三四五六七八九十百千]+)"
    patterns = (
        rf"(?:用户名|账号名).{{0,20}}?(?:至少|不少于|不低于){number}(?:个字符|字符|位)",
        rf"(?:用户名|账号名).{{0,20}}?{number}(?:个字符|字符|位)(?:或以上|以上)",
        rf"(?:用户名|账号名)(?:最小|最低)(?:长度|位数)(?:为|是)?{number}(?:个字符|字符|位)?",
    )
    for pattern in patterns:
        match = re.search(pattern, clause)
        if not match:
            continue
        try:
            value = parse_number_token(match.group("number"))
        except ConstraintParseError:
            return None
        return value, match.group(0)
    return None


def _parse_english_number(value: str) -> int:
    ones = {
        "zero": 0,
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
        "eleven": 11,
        "twelve": 12,
        "thirteen": 13,
        "fourteen": 14,
        "fifteen": 15,
        "sixteen": 16,
        "seventeen": 17,
        "eighteen": 18,
        "nineteen": 19,
    }
    tens = {
        "twenty": 20,
        "thirty": 30,
        "forty": 40,
        "fifty": 50,
        "sixty": 60,
        "seventy": 70,
        "eighty": 80,
        "ninety": 90,
    }
    parts = value.replace("-", " ").split()
    if not parts or len(parts) > 4:
        raise ConstraintParseError("UNSUPPORTED_ENGLISH_NUMBER")
    total = 0
    current = 0
    for part in parts:
        if part in ones:
            current += ones[part]
        elif part in tens:
            current += tens[part]
        elif part == "hundred" and 1 <= current <= 9:
            current *= 100
        else:
            raise ConstraintParseError("UNSUPPORTED_ENGLISH_NUMBER")
    total += current
    if not 0 <= total <= 999:
        raise ConstraintParseError("NUMBER_OUT_OF_RANGE")
    return total


def _parse_chinese_number(value: str) -> int:
    digits = {
        "零": 0,
        "〇": 0,
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    units = {"十": 10, "百": 100, "千": 1000}
    if all(character in digits for character in value):
        return int("".join(str(digits[character]) for character in value))
    total = 0
    current = 0
    last_unit = 10000
    for character in value:
        if character in digits:
            current = digits[character]
            continue
        unit = units.get(character)
        if unit is None or unit >= last_unit:
            raise ConstraintParseError("UNSUPPORTED_CHINESE_NUMBER")
        total += (current or 1) * unit
        current = 0
        last_unit = unit
    total += current
    if not 0 <= total <= 9999:
        raise ConstraintParseError("NUMBER_OUT_OF_RANGE")
    return total
