from __future__ import annotations

import calendar
from dataclasses import dataclass

from parser import TrafficStats

SIMPLE_MONTH_DAYS = 30.0
ANNUAL_MONTHS = 12.0
PROJECTION_MODES = ("simple", "calendar")


@dataclass(frozen=True)
class ProjectedTraffic:
    mode: str
    observed_days: float
    target_month_days: float
    scale_factor: float
    safety_margin: float
    monthly_requests: float
    monthly_bytes: float
    annual_requests: float
    annual_bytes: float


def target_month_days(stats: TrafficStats, mode: str = "simple") -> float:
    if mode == "simple":
        return SIMPLE_MONTH_DAYS
    if mode == "calendar":
        if stats.min_date is None:
            return SIMPLE_MONTH_DAYS
        return float(
            calendar.monthrange(stats.min_date.year, stats.min_date.month)[1]
        )
    allowed = ", ".join(PROJECTION_MODES)
    raise ValueError(f"unknown projection mode '{mode}'. Allowed: {allowed}")


def compound_annual_factor(growth_rate: float) -> float:
    """
    Sum of (1 + growth)^(m/12) for m = 0..11.

    Used to scale monthly run-rate costs to a growth-adjusted annual total.
    """
    if growth_rate <= 0:
        return ANNUAL_MONTHS
    step = (1.0 + growth_rate) ** (1.0 / ANNUAL_MONTHS)
    return growth_rate / (step - 1.0)


def project_traffic(
    stats: TrafficStats,
    *,
    mode: str = "simple",
    safety_margin: float = 0.0,
) -> ProjectedTraffic:
    """
    Scale observed log traffic to a monthly and annual projection.

    simple: always normalize to a 30-day month.
    calendar: normalize to the length of the calendar month of the first log entry.

    safety_margin adds headroom on top of the scaled traffic (e.g. 0.2 = +20%).
    """
    month_days = target_month_days(stats, mode)

    if stats.total_records == 0 or stats.observed_days <= 0:
        return ProjectedTraffic(
            mode=mode,
            observed_days=stats.observed_days,
            target_month_days=month_days,
            scale_factor=0.0,
            safety_margin=safety_margin,
            monthly_requests=0.0,
            monthly_bytes=0.0,
            annual_requests=0.0,
            annual_bytes=0.0,
        )

    scale_factor = month_days / stats.observed_days
    margin_multiplier = 1.0 + max(safety_margin, 0.0)

    monthly_requests = stats.total_records * scale_factor * margin_multiplier
    monthly_bytes = stats.total_bytes * scale_factor * margin_multiplier
    annual_factor = compound_annual_factor(0.0)

    return ProjectedTraffic(
        mode=mode,
        observed_days=stats.observed_days,
        target_month_days=month_days,
        scale_factor=scale_factor,
        safety_margin=safety_margin,
        monthly_requests=monthly_requests,
        monthly_bytes=monthly_bytes,
        annual_requests=monthly_requests * annual_factor,
        annual_bytes=monthly_bytes * annual_factor,
    )


def yearly_forecast_totals(
    base_annual_total: float,
    growth_rate: float,
    years: int,
) -> tuple[tuple[int, float], ...]:
    if years <= 0:
        return ()
    return tuple(
        (year, base_annual_total * ((1.0 + growth_rate) ** (year - 1)))
        for year in range(1, years + 1)
    )
