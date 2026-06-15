from datetime import UTC, datetime

import pytest

from parser import TrafficStats
from projection import project_traffic


@pytest.fixture
def sample_stats() -> TrafficStats:
    return TrafficStats(
        min_date=datetime(2026, 6, 1, tzinfo=UTC),
        max_date=datetime(2026, 6, 16, tzinfo=UTC),
        total_records=1500,
        total_bytes=150 * 1024**3,
    )


def test_project_traffic_scales_to_30_day_month(sample_stats):
    projected = project_traffic(sample_stats)

    assert projected.observed_days == pytest.approx(15.0)
    assert projected.scale_factor == pytest.approx(2.0)
    assert projected.monthly_requests == pytest.approx(3000.0)
    assert projected.monthly_bytes == pytest.approx(sample_stats.total_bytes * 2.0)
    assert projected.annual_requests == pytest.approx(36000.0)


def test_project_traffic_applies_safety_margin(sample_stats):
    projected = project_traffic(sample_stats, safety_margin=0.2)

    assert projected.monthly_requests == pytest.approx(3600.0)
    assert projected.safety_margin == 0.2
