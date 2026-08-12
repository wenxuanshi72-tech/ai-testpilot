from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from typing import Any

PRICING_PROVIDER = "deepseek"
PRICING_MODEL = "deepseek-v4-pro"
PRICING_VERSION = "deepseek-v4-pro@2026-07-27"
PRICING_CHECKED_AT = "2026-07-27"
INPUT_CACHE_HIT_RATE = Decimal("0.003625")
INPUT_CACHE_MISS_RATE = Decimal("0.435")
OUTPUT_RATE = Decimal("0.87")
CURRENCY = "USD"
COST_CALCULATION_VERSION = "llm-cost@1.0.0"
ESTIMATOR_VERSION = "conservative-serialized@1.0.0"
DEFAULT_SAFETY_MARGIN_PERCENT = 10
DEFAULT_INPUT_BUDGET_TOKENS = 2100
DEFAULT_OUTPUT_UTILIZATION_PERCENT = 75


@dataclass(frozen=True)
class TokenEstimate:
    character_count: int
    utf8_byte_count: int
    chars_per_4_tokens: int
    chars_per_3_tokens: int
    tokenizer_tokens: int | None
    base_tokens: int
    safety_margin_percent: int
    budget_tokens: int
    estimator_version: str = ESTIMATOR_VERSION

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CostSnapshot:
    pricing_provider: str
    pricing_model: str
    pricing_version: str
    pricing_checked_at: str
    input_cache_hit_tokens: int
    input_cache_miss_tokens: int
    output_tokens: int
    input_cache_hit_rate_usd_per_million: str
    input_cache_miss_rate_usd_per_million: str
    output_rate_usd_per_million: str
    estimated_cost_microusd: int
    actual_cost_microusd: int
    currency: str
    cost_calculation_version: str
    calculation_assumption: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def estimate_serialized_value(
    value: Any,
    *,
    safety_margin_percent: int = DEFAULT_SAFETY_MARGIN_PERCENT,
    tokenizer_tokens: int | None = None,
) -> TokenEstimate:
    serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return estimate_serialized_text(
        serialized,
        safety_margin_percent=safety_margin_percent,
        tokenizer_tokens=tokenizer_tokens,
    )


def estimate_serialized_text(
    value: str,
    *,
    safety_margin_percent: int = DEFAULT_SAFETY_MARGIN_PERCENT,
    tokenizer_tokens: int | None = None,
) -> TokenEstimate:
    if not 0 <= safety_margin_percent <= 100:
        raise ValueError("safety_margin_percent must be between 0 and 100")
    character_count = len(value)
    utf8_byte_count = len(value.encode("utf-8"))
    chars_per_4 = _ceil_div(character_count, 4)
    chars_per_3 = _ceil_div(character_count, 3)
    byte_conservative = _ceil_div(utf8_byte_count, 3)
    available = [chars_per_4, chars_per_3, byte_conservative]
    if tokenizer_tokens is not None:
        if tokenizer_tokens < 0:
            raise ValueError("tokenizer_tokens cannot be negative")
        available.append(tokenizer_tokens)
    base_tokens = max(available)
    budget_tokens = _decimal_to_int(
        Decimal(base_tokens) * (Decimal(100 + safety_margin_percent) / Decimal(100)),
        rounding=ROUND_CEILING,
    )
    return TokenEstimate(
        character_count=character_count,
        utf8_byte_count=utf8_byte_count,
        chars_per_4_tokens=chars_per_4,
        chars_per_3_tokens=max(chars_per_3, byte_conservative),
        tokenizer_tokens=tokenizer_tokens,
        base_tokens=base_tokens,
        safety_margin_percent=safety_margin_percent,
        budget_tokens=budget_tokens,
    )


def output_safe_token_limit(
    max_output_tokens: int,
    utilization_percent: int = DEFAULT_OUTPUT_UTILIZATION_PERCENT,
) -> int:
    if max_output_tokens <= 0 or not 1 <= utilization_percent <= 100:
        raise ValueError("invalid output capacity limit")
    return _decimal_to_int(
        Decimal(max_output_tokens) * Decimal(utilization_percent) / Decimal(100),
        rounding=ROUND_CEILING,
    )


def calculate_cost(
    *,
    provider_mode: str,
    input_tokens: int,
    output_tokens: int,
    input_cache_hit_tokens: int | None = None,
    input_cache_miss_tokens: int | None = None,
    estimated: bool = False,
    pricing_provider: str = PRICING_PROVIDER,
    pricing_model: str = PRICING_MODEL,
) -> CostSnapshot:
    if min(input_tokens, output_tokens) < 0:
        raise ValueError("token counts cannot be negative")
    if provider_mode == "mock":
        return _snapshot(
            0,
            0,
            0,
            0,
            "mock_provider_zero_cost",
            pricing_provider=pricing_provider,
            pricing_model=pricing_model,
        )
    if provider_mode != "real":
        raise ValueError("provider_mode must be real or mock")
    if input_cache_hit_tokens is None or input_cache_miss_tokens is None:
        hit_tokens = 0
        miss_tokens = input_tokens
        assumption = "provider_cache_split_unavailable_all_input_counted_as_cache_miss"
    else:
        hit_tokens = input_cache_hit_tokens
        miss_tokens = input_cache_miss_tokens
        if min(hit_tokens, miss_tokens) < 0 or hit_tokens + miss_tokens > input_tokens:
            raise ValueError("invalid provider cache token split")
        miss_tokens += input_tokens - hit_tokens - miss_tokens
        assumption = "provider_cache_split_used_with_unclassified_input_counted_as_cache_miss"
    microusd = _decimal_to_int(
        Decimal(hit_tokens) * INPUT_CACHE_HIT_RATE
        + Decimal(miss_tokens) * INPUT_CACHE_MISS_RATE
        + Decimal(output_tokens) * OUTPUT_RATE,
        rounding=ROUND_CEILING if estimated else ROUND_HALF_UP,
    )
    return _snapshot(
        hit_tokens,
        miss_tokens,
        output_tokens,
        microusd,
        assumption,
        estimated=estimated,
        pricing_provider=pricing_provider,
        pricing_model=pricing_model,
    )


def microusd_to_usd(value: int) -> str:
    if value < 0:
        raise ValueError("microusd cannot be negative")
    return format(Decimal(value) / Decimal(1_000_000), ".6f")


def _snapshot(
    hit_tokens: int,
    miss_tokens: int,
    output_tokens: int,
    microusd: int,
    assumption: str,
    *,
    estimated: bool = False,
    pricing_provider: str = PRICING_PROVIDER,
    pricing_model: str = PRICING_MODEL,
) -> CostSnapshot:
    return CostSnapshot(
        pricing_provider=pricing_provider,
        pricing_model=pricing_model,
        pricing_version=PRICING_VERSION,
        pricing_checked_at=PRICING_CHECKED_AT,
        input_cache_hit_tokens=hit_tokens,
        input_cache_miss_tokens=miss_tokens,
        output_tokens=output_tokens,
        input_cache_hit_rate_usd_per_million=str(INPUT_CACHE_HIT_RATE),
        input_cache_miss_rate_usd_per_million=str(INPUT_CACHE_MISS_RATE),
        output_rate_usd_per_million=str(OUTPUT_RATE),
        estimated_cost_microusd=microusd if estimated else 0,
        actual_cost_microusd=0 if estimated else microusd,
        currency=CURRENCY,
        cost_calculation_version=COST_CALCULATION_VERSION,
        calculation_assumption=assumption,
    )


def _ceil_div(value: int, divisor: int) -> int:
    return (value + divisor - 1) // divisor


def _decimal_to_int(value: Decimal, *, rounding: str) -> int:
    return int(value.quantize(Decimal("1"), rounding=rounding))
