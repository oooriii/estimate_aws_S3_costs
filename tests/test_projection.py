from datetime import UTC, datetime

import pytest

from parser import TrafficStats
from projection import (
    compound_annual_factor,
    project_traffic,
    target_month_days,
    yearly_forecast_totals,
)


@pytest.fixture
def sample_stats() -> TrafficStats:
    return TrafficStats(
        min_date=datetime(2026, 6, 1, tzinfo=UTC),
        max_date=datetime(2026, 6, 16, tzinfo=UTC),
        total_records=1500,
        total_bytes=150 * 1024**3,
    )


@pytest.fixture
def january_stats() -> TrafficStats:
    return TrafficStats(
        min_date=datetime(2026, 1, 1, tzinfo=UTC),
        max_date=datetime(2026, 1, 16, tzinfo=UTC),
        total_records=1500,
        total_bytes=150 * 1024**3,
    )


def test_project_traffic_scales_to_30_day_month(sample_stats):
    projected = project_traffic(sample_stats)

    assert projected.mode == "simple"
    assert projected.target_month_days == pytest.approx(30.0)
    assert projected.observed_days == pytest.approx(15.0)
    assert projected.scale_factor == pytest.approx(2.0)
    assert projected.monthly_requests == pytest.approx(3000.0)
    assert projected.monthly_bytes == pytest.approx(sample_stats.total_bytes * 2.0)
    assert projected.annual_requests == pytest.approx(36000.0)


def test_project_traffic_calendar_mode_uses_month_length(january_stats):
    projected = project_traffic(january_stats, mode="calendar")

    assert projected.mode == "calendar"
    assert projected.target_month_days == pytest.approx(31.0)
    assert projected.scale_factor == pytest.approx(31.0 / 15.0)
    assert projected.monthly_requests == pytest.approx(1500 * 31.0 / 15.0)


def test_target_month_days_for_june_calendar(sample_stats):
    assert target_month_days(sample_stats, "calendar") == pytest.approx(30.0)


def test_project_traffic_applies_safety_margin(sample_stats):
    projected = project_traffic(sample_stats, safety_margin=0.2)

    assert projected.monthly_requests == pytest.approx(3600.0)
    assert projected.safety_margin == 0.2


def test_compound_annual_factor_without_growth():
    assert compound_annual_factor(0.0) == pytest.approx(12.0)


def test_compound_annual_factor_with_growth():
    assert compound_annual_factor(0.10) == pytest.approx(12.54, rel=0.01)


def test_yearly_forecast_totals_compounds_growth():
    forecast = yearly_forecast_totals(1000.0, 0.10, 3)

    assert forecast == (
        (1, pytest.approx(1000.0)),
        (2, pytest.approx(1100.0)),
        (3, pytest.approx(1210.0)),
    )
