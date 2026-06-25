import json
from datetime import datetime, timedelta
from pathlib import Path

from events import LogEvent
from watch.aggregator import WatchAggregator
from watch.blocking import recommend_blocks
from watch.config import WatchThresholds
from watch.snapshot import SnapshotScheduler


def _access_event(ip: str, *, ts: datetime) -> LogEvent:
    return LogEvent(
        source="access_ssl.log",
        kind="access",
        timestamp=ts,
        remote_host=ip,
        user_agent="scanner/1.0",
        path="/missing",
        status=404,
        bytes_sent=0,
        message=None,
    )


def test_blocking_flags_burst_rps_even_with_low_sustained_rps():
    base = datetime(2026, 6, 15, 10, 0, 0)
    thresholds = WatchThresholds(
        window_seconds=120,
        burst_window_seconds=2.0,
        min_burst_rps=5.0,
        min_burst_requests=10,
        min_rps_per_ip=100.0,
        min_requests_per_ip=1000,
        top_n=10,
    )
    agg = WatchAggregator(thresholds=thresholds)

    for i in range(30):
        agg.ingest(_access_event("82.115.10.20", ts=base + timedelta(seconds=i * 0.2)))

    snapshot = agg.snapshot(now=base + timedelta(seconds=10))
    blocks = recommend_blocks(snapshot, thresholds=thresholds)
    ip_blocks = [block for block in blocks if block.block_type == "ip"]
    assert ip_blocks
    assert ip_blocks[0].reason == "high_burst_rps"


def test_snapshot_scheduler_writes_timestamped_files(tmp_path: Path):
    base = datetime(2026, 6, 15, 10, 0, 0)
    thresholds = WatchThresholds(window_seconds=60, top_n=5)
    agg = WatchAggregator(thresholds=thresholds)
    for i in range(5):
        agg.ingest(_access_event("1.2.3.4", ts=base + timedelta(seconds=i)))

    snapshot = agg.snapshot(now=base + timedelta(seconds=5))
    blocks = recommend_blocks(snapshot, thresholds=thresholds)
    scheduler = SnapshotScheduler(directory=tmp_path, every_seconds=60.0)

    written = scheduler.maybe_write(snapshot, blocks, now=base)
    assert written is not None
    json_path, csv_path = written
    assert json_path.exists()
    assert csv_path.exists()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["total_requests"] == 5
    assert payload["ips"][0]["ip"] == "1.2.3.4"

    assert scheduler.maybe_write(snapshot, blocks, now=base) is None
