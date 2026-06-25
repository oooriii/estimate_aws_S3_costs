from pathlib import Path

import pytest

from watch.blocking import recommend_blocks
from watch.config import WatchThresholds
from watch.country_blocks import (
    CountryBlocksResolver,
    discover_country_blocks_paths,
    open_country_blocks_resolver,
)
from watch.country_blocks_export import export_flagged_country_cidrs


@pytest.fixture
def geolite2_fixture_dir() -> Path:
    return Path(__file__).parent / "fixtures" / "geolite2"


@pytest.fixture
def country_blocks_resolver(geolite2_fixture_dir: Path) -> CountryBlocksResolver:
    return CountryBlocksResolver(
        locations_path=geolite2_fixture_dir / "GeoLite2-Country-Locations-en.csv",
        blocks_ipv4_path=geolite2_fixture_dir / "GeoLite2-Country-Blocks-IPv4.csv",
    )


def test_country_blocks_resolver_loads_cidrs_sorted_by_size(
    country_blocks_resolver: CountryBlocksResolver,
):
    cidrs = country_blocks_resolver.blocks_for_country("US")
    assert cidrs == ("8.8.0.0/13", "8.8.4.0/24")

    summary = country_blocks_resolver.summary("IS", limit=2)
    assert summary is not None
    assert summary.total_cidrs == 2
    assert summary.sample_cidrs[0] == "82.115.0.0/16"


def test_discover_country_blocks_paths_from_mmdb_layout(
    geolite2_fixture_dir: Path, tmp_path: Path
):
    mmdb = tmp_path / "GeoLite2-Country.mmdb"
    mmdb.write_bytes(b"fake")
    for name in (
        "GeoLite2-Country-Locations-en.csv",
        "GeoLite2-Country-Blocks-IPv4.csv",
    ):
        (tmp_path / name).write_text(
            (geolite2_fixture_dir / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    paths = discover_country_blocks_paths(mmdb)
    assert paths is not None
    assert paths.locations.is_file()
    assert paths.blocks_ipv4 is not None


def test_open_country_blocks_resolver_auto_discovers(
    geolite2_fixture_dir: Path, tmp_path: Path
):
    mmdb = tmp_path / "GeoLite2-Country.mmdb"
    mmdb.write_bytes(b"fake")
    for name in (
        "GeoLite2-Country-Locations-en.csv",
        "GeoLite2-Country-Blocks-IPv4.csv",
    ):
        (tmp_path / name).write_text(
            (geolite2_fixture_dir / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    resolver = open_country_blocks_resolver(geoip_db=mmdb)
    assert resolver is not None
    assert resolver.blocks_for_country("US")


def test_recommend_blocks_includes_official_country_cidrs(
    country_blocks_resolver: CountryBlocksResolver,
):
    from datetime import datetime, timedelta

    from events import LogEvent
    from geo import StaticGeoIpResolver
    from watch.aggregator import WatchAggregator

    base = datetime(2026, 6, 15, 10, 0, 0)

    def event(ip: str, i: int) -> LogEvent:
        return LogEvent(
            source="access_ssl.log",
            kind="access",
            timestamp=base + timedelta(seconds=i),
            remote_host=ip,
            user_agent="bot",
            path="/",
            status=404,
            bytes_sent=0,
            message=None,
        )

    thresholds = WatchThresholds(
        window_seconds=60,
        min_rps_per_country=1.0,
        min_requests_per_country=10,
        min_rps_per_ip=100.0,
        top_n=10,
    )
    agg = WatchAggregator(
        thresholds=thresholds,
        geo_resolver=StaticGeoIpResolver({"82.115.10.20": ("IS", "Iceland")}),
    )
    for i in range(60):
        agg.ingest(event("82.115.10.20", i))

    snapshot = agg.snapshot(now=base + timedelta(seconds=59))
    blocks = recommend_blocks(
        snapshot,
        thresholds=thresholds,
        country_blocks=country_blocks_resolver,
        official_cidr_limit=2,
    )

    country_cidrs = [b for b in blocks if b.block_type == "country_cidr"]
    assert country_cidrs
    assert country_cidrs[0].target == "82.115.0.0/16"
    assert "official_country_cidr" in country_cidrs[0].reason


def test_export_flagged_country_cidrs_writes_per_country_csv(
    country_blocks_resolver: CountryBlocksResolver,
    tmp_path: Path,
):
    from watch.blocking import BlockRecommendation

    blocks = (
        BlockRecommendation(
            block_type="country",
            target="IS",
            country_code="IS",
            country_name="Iceland",
            requests=100,
            rps=12.0,
            reason="high_country_rps",
            detail="test",
        ),
    )

    written = export_flagged_country_cidrs(
        tmp_path,
        blocks,
        country_blocks_resolver,
    )
    assert len(written) == 1
    content = written[0].read_text(encoding="utf-8")
    assert "82.115.0.0/16" in content
    assert "geolite2-country-blocks" in content
