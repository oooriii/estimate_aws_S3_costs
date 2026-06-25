from argparse import Namespace
from datetime import datetime, timedelta
from pathlib import Path

from watch.burst import BurstTracker
from watch.config_loader import load_watch_config, resolve_watch_runtime


def test_burst_tracker_groups_rapid_requests():
    base = datetime(2026, 6, 15, 10, 0, 0)
    tracker = BurstTracker(burst_window_seconds=3.0)

    for i in range(25):
        tracker.record("1.2.3.4", base + timedelta(seconds=i * 0.5))

    metrics = tracker.metrics("1.2.3.4")
    assert metrics.burst_count == 1
    assert metrics.max_burst_requests == 25
    assert metrics.max_burst_rps > 1.0


def test_burst_tracker_splits_slow_requests_into_multiple_bursts():
    base = datetime(2026, 6, 15, 10, 0, 0)
    tracker = BurstTracker(burst_window_seconds=2.0)

    tracker.record("1.2.3.4", base)
    tracker.record("1.2.3.4", base + timedelta(seconds=1))
    tracker.record("1.2.3.4", base + timedelta(seconds=10))
    tracker.record("1.2.3.4", base + timedelta(seconds=11))

    metrics = tracker.metrics("1.2.3.4")
    assert metrics.burst_count == 2
    assert metrics.max_burst_requests == 2


def test_load_watch_config_reads_yaml(tmp_path: Path):
    config_file = tmp_path / "watch.yaml"
    config_file.write_text(
        """
geoip_db: GeoLite2-Country.mmdb
refresh_seconds: 5
live: false
thresholds:
  window_seconds: 120
  burst_window_seconds: 4
  min_burst_rps: 8
snapshots:
  directory: reports/custom
  every_seconds: 600
""".strip(),
        encoding="utf-8",
    )

    config = load_watch_config(config_file)
    assert config.geoip_db == "GeoLite2-Country.mmdb"
    assert config.refresh_seconds == 5.0
    assert config.live is False
    assert config.thresholds.window_seconds == 120.0
    assert config.thresholds.burst_window_seconds == 4.0
    assert config.thresholds.min_burst_rps == 8.0
    assert config.snapshots.directory == "reports/custom"
    assert config.snapshots.every_seconds == 600.0


def test_resolve_watch_runtime_cli_overrides_config(tmp_path: Path):
    config_file = tmp_path / "watch.yaml"
    config_file.write_text(
        "thresholds:\n  window_seconds: 120\n  min_rps_per_ip: 9\n",
        encoding="utf-8",
    )

    args = Namespace(
        config=config_file,
        geoip_db=None,
        refresh=2.0,
        live=True,
        window=600.0,
        burst_window=3.0,
        min_burst_rps=10.0,
        min_burst_req=20,
        min_rps_ip=1.0,
        min_rps_subnet=5.0,
        min_rps_country=10.0,
        min_req_ip=50,
        min_req_subnet=100,
        min_req_country=200,
        subnet_v4=24,
        top=15,
        snapshot_dir=None,
        snapshot_every=0.0,
        files=[],
        export_csv=None,
        export_json=None,
    )

    _config, thresholds = resolve_watch_runtime(
        args,
        argv=[
            "watch",
            "--config",
            str(config_file),
            "--window",
            "600",
            "--min-rps-ip",
            "1",
        ],
    )
    assert thresholds.window_seconds == 600.0
    assert thresholds.min_rps_per_ip == 1.0
