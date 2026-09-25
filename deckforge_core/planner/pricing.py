"""Pricing helpers (Workstream D)."""

from __future__ import annotations

ANTHROPIC_PRICING: dict[str, tuple[float, float, float]] = {
    "claude-sonnet-5": (3.0, 15.0, 0.30),
    "claude-sonnet-4-5": (3.0, 15.0, 0.30),
    "claude-opus-5-5": (5.0, 25.0, 0.50),
}


def format_cost(usd: float) -> str:
    return f"${usd:.4f}"


def cost_for(
    provider: str,
    model: str,
    in_toks: int,
    out_toks: int,
    cache_read: int = 0,
) -> float:
    if provider == "anthropic":
        pricing = ANTHROPIC_PRICING.get(model)
        if pricing is not None:
            price_in, price_out, price_cache = pricing
        else:
            # Fallback to sonnet
            price_in, price_out, price_cache = ANTHROPIC_PRICING["claude-sonnet-5"]
        cost = (
            in_toks * price_in
            + out_toks * price_out
            + cache_read * price_cache
        ) / 1_000_000
        return cost
    return 0.0
