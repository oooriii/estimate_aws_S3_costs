from datetime import datetime, timedelta

from events import LogEvent
from geo import StaticGeoIpResolver
from watch.aggregator import WatchAggregator
from watch.blocking import recommend_blocks
from watch.config import WatchThresholds


def _access_event(
    ip: str,
    *,
    ts: datetime,
    ua: str = "Mozilla/5.0",
    status: int = 200,
) -> LogEvent:
    return LogEvent(
        source="access_ssl.log",
        kind="access",
        timestamp=ts,
        remote_host=ip,
        user_agent=ua,
        path="/index.html",
        status=status,
        bytes_sent=100,
        message=None,
    )


def _error_event(ip: str, *, ts: datetime) -> LogEvent:
    return LogEvent(
        source="error_ssl.log",
        kind="error",
        timestamp=ts,
        remote_host=ip,
        user_agent=None,
        path=None,
        status=None,
        bytes_sent=0,
        message="[error] not found",
    )


def test_aggregator_counts_access_and_error_together():
    base = datetime(2026, 6, 15, 10, 0, 0)
    agg = WatchAggregator(thresholds=WatchThresholds(window_seconds=60, top_n=5))
    agg.ingest(_access_event("1.2.3.4", ts=base))
    agg.ingest(_error_event("1.2.3.4", ts=base + timedelta(seconds=1)))

    snapshot = agg.snapshot(now=base + timedelta(seconds=2))
    assert snapshot.total_requests == 2
    assert len(snapshot.ips) == 1
    assert snapshot.ips[0].requests == 2
    assert snapshot.ips[0].kinds["access"] == 1
    assert snapshot.ips[0].kinds["error"] == 1


def test_aggregator_groups_country_and_subnet():
    base = datetime(2026, 6, 15, 10, 0, 0)
    resolver = StaticGeoIpResolver(
        {
            "8.8.4.4": ("US", "United States"),
            "8.8.8.8": ("US", "United States"),
        }
    )
    agg = WatchAggregator(
        thresholds=WatchThresholds(window_seconds=120, top_n=10),
        geo_resolver=resolver,
    )
    for i in range(30):
        agg.ingest(
            _access_event(
                "8.8.4.4" if i % 2 == 0 else "8.8.8.8",
                ts=base + timedelta(seconds=i),
            )
        )

    snapshot = agg.snapshot(now=base + timedelta(seconds=30))
    assert snapshot.countries
    assert snapshot.countries[0].country_code == "US"
    assert snapshot.subnets
    assert snapshot.subnets[0].key == "8.8.4.0/24"


def test_blocking_recommends_country_and_subnets():
    base = datetime(2026, 6, 15, 10, 0, 0)
    resolver = StaticGeoIpResolver({"82.115.10.20": ("IS", "Iceland")})
    thresholds = WatchThresholds(
        window_seconds=60,
        min_rps_per_country=1.0,
        min_requests_per_country=10,
        min_rps_per_ip=100.0,
        top_n=10,
    )
    agg = WatchAggregator(thresholds=thresholds, geo_resolver=resolver)
    for i in range(60):
        agg.ingest(_access_event("82.115.10.20", ts=base + timedelta(seconds=i)))

    snapshot = agg.snapshot(now=base + timedelta(seconds=59))
    blocks = recommend_blocks(snapshot, thresholds=thresholds)

    country_blocks = [b for b in blocks if b.block_type == "country"]
    subnet_blocks = [b for b in blocks if b.block_type == "subnet"]
    assert country_blocks
    assert country_blocks[0].target == "IS"
    assert subnet_blocks
    assert any("82.115.10.0/24" in b.target for b in subnet_blocks)
