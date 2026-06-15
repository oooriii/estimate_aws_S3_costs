from __future__ import annotations

from dataclasses import dataclass

from pricing.schema import PriceTier


@dataclass(frozen=True)
class TierSlice:
    gb: float
    price_per_gb: float
    subtotal_usd: float


def tiered_cost_breakdown(
    amount_gb: float,
    tiers: tuple[PriceTier, ...],
) -> tuple[TierSlice, ...]:
    if amount_gb <= 0:
        return ()

    remaining = amount_gb
    previous_limit = 0.0
    slices: list[TierSlice] = []

    for tier in tiers:
        if tier.up_to_gb is None:
            if remaining > 0:
                slices.append(
                    TierSlice(
                        gb=remaining,
                        price_per_gb=tier.price,
                        subtotal_usd=remaining * tier.price,
                    )
                )
            return tuple(slices)

        tier_size = tier.up_to_gb - previous_limit
        used = min(remaining, tier_size)
        if used > 0:
            slices.append(
                TierSlice(
                    gb=used,
                    price_per_gb=tier.price,
                    subtotal_usd=used * tier.price,
                )
            )
        remaining -= used
        previous_limit = tier.up_to_gb

        if remaining <= 0:
            return tuple(slices)

    if remaining > 0 and tiers:
        price = tiers[-1].price
        slices.append(
            TierSlice(
                gb=remaining,
                price_per_gb=price,
                subtotal_usd=remaining * price,
            )
        )
    return tuple(slices)


def tiered_cost(amount_gb: float, tiers: tuple[PriceTier, ...]) -> float:
    if amount_gb <= 0:
        return 0.0

    remaining = amount_gb
    previous_limit = 0.0
    total = 0.0

    for tier in tiers:
        if tier.up_to_gb is None:
            total += remaining * tier.price
            return total

        tier_size = tier.up_to_gb - previous_limit
        used = min(remaining, tier_size)
        total += used * tier.price
        remaining -= used
        previous_limit = tier.up_to_gb

        if remaining <= 0:
            return total

    if tiers:
        total += remaining * tiers[-1].price
    return total
