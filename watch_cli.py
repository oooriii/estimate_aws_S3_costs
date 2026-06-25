from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console

from geo import MaxMindGeoIpResolver, open_geoip_resolver
from source import iter_events
from watch.aggregator import WatchAggregator
from watch.blocking import recommend_blocks
from watch.config import WatchThresholds
from watch.live_display import LiveMonitor, render_snapshot


def _write_snapshot_csv(path: Path, snapshot, blocks) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "block_type",
                "target",
                "country_code",
                "country_name",
                "requests",
                "rps",
                "reason",
                "detail",
            ]
        )
        for item in blocks:
            writer.writerow(
                [
                    item.block_type,
                    item.target,
                    item.country_code or "",
                    item.country_name or "",
                    item.requests,
                    f"{item.rps:.4f}",
                    item.reason,
                    item.detail,
                ]
            )


def _write_snapshot_json(path: Path, snapshot, blocks) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now().isoformat(),
        "window_seconds": snapshot.window_seconds,
        "total_requests": snapshot.total_requests,
        "current_rps": snapshot.current_rps,
        "countries": [
            {
                "country_code": item.country_code,
                "country_name": item.country_name,
                "requests": item.requests,
                "rps": item.rps,
                "unique_ips": len(item.unique_ips),
            }
            for item in snapshot.countries
        ],
        "blocks": [
            {
                "block_type": item.block_type,
                "target": item.target,
                "country_code": item.country_code,
                "country_name": item.country_name,
                "requests": item.requests,
                "rps": item.rps,
                "reason": item.reason,
                "detail": item.detail,
            }
            for item in blocks
        ],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _build_thresholds(args: argparse.Namespace) -> WatchThresholds:
    return WatchThresholds(
        window_seconds=args.window,
        min_rps_per_ip=args.min_rps_ip,
        min_rps_per_subnet=args.min_rps_subnet,
        min_rps_per_country=args.min_rps_country,
        min_requests_per_ip=args.min_req_ip,
        min_requests_per_subnet=args.min_req_subnet,
        min_requests_per_country=args.min_req_country,
        subnet_mask_v4=args.subnet_v4,
        top_n=args.top,
    )


def cmd_watch(args: argparse.Namespace) -> int:
    console = Console()
    thresholds = _build_thresholds(args)

    resolver = None
    if args.geoip_db is not None:
        try:
            resolver = open_geoip_resolver(args.geoip_db)
        except (OSError, RuntimeError, ValueError) as exc:
            console.print(f"[red]Error:[/red] {exc}")
            return 1

    aggregator = WatchAggregator(thresholds=thresholds, geo_resolver=resolver)
    input_paths = args.files if args.files else None

    try:
        reading_stdin = not input_paths
        if args.live and reading_stdin and sys.stdin.isatty():
            console.print(
                "[red]Error:[/red] pipe Apache logs into stdin or pass log files.\n"
                "Example: ssh host 'sudo tail -F /var/log/apache2/access_ssl.log' "
                "| uv run python main.py watch --geoip-db GeoLite2-Country.mmdb"
            )
            return 1

        if args.live:
            with LiveMonitor(
                console, refresh_per_second=1.0 / max(args.refresh, 0.1)
            ) as monitor:
                for event in iter_events(input_paths):
                    aggregator.ingest(event)
                    snapshot = aggregator.snapshot(now=event.timestamp)
                    blocks = recommend_blocks(snapshot, thresholds=thresholds)
                    monitor.update(snapshot, blocks)
        else:
            last_snapshot = None
            last_blocks: tuple = ()
            for event in iter_events(input_paths):
                aggregator.ingest(event)
                last_snapshot = aggregator.snapshot(now=event.timestamp)
                last_blocks = recommend_blocks(last_snapshot, thresholds=thresholds)

            if last_snapshot is None:
                console.print("[yellow]Warning:[/yellow] no valid log events found.")
                return 1

            render_snapshot(console, last_snapshot, last_blocks)

            if args.export_csv is not None:
                _write_snapshot_csv(args.export_csv, last_snapshot, last_blocks)
                console.print(
                    f"[green]Block recommendations CSV:[/green] {args.export_csv}"
                )
            if args.export_json is not None:
                _write_snapshot_json(args.export_json, last_snapshot, last_blocks)
                console.print(f"[green]Snapshot JSON:[/green] {args.export_json}")
    finally:
        if isinstance(resolver, MaxMindGeoIpResolver):
            resolver.close()

    return 0


def register_watch_command(subparsers: argparse._SubParsersAction) -> None:
    watch = subparsers.add_parser(
        "watch",
        help="Monitor Apache access/error logs live and suggest blocks by RPS",
    )
    watch.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="Log files to analyze (default: read from stdin)",
    )
    watch.add_argument(
        "--geoip-db",
        type=Path,
        metavar="PATH",
        help="MaxMind GeoLite2-Country.mmdb for country breakdown and blocks",
    )
    watch.add_argument(
        "--live",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Live Rich dashboard (default: on; use --no-live for batch)",
    )
    watch.add_argument(
        "--refresh",
        type=float,
        default=2.0,
        metavar="SEC",
        help="Live UI refresh interval (default: 2)",
    )
    watch.add_argument(
        "--window",
        type=float,
        default=300.0,
        metavar="SEC",
        help="Sliding window for RPS calculations (default: 300)",
    )
    watch.add_argument(
        "--min-rps-ip",
        type=float,
        default=2.0,
        help="Flag IP at or above this RPS (default: 2)",
    )
    watch.add_argument(
        "--min-rps-subnet",
        type=float,
        default=5.0,
        help="Flag /24 subnet at or above this RPS (default: 5)",
    )
    watch.add_argument(
        "--min-rps-country",
        type=float,
        default=10.0,
        help="Flag country at or above this RPS (default: 10)",
    )
    watch.add_argument(
        "--min-req-ip",
        type=int,
        default=50,
        help="Minimum requests in window to flag an IP (default: 50)",
    )
    watch.add_argument(
        "--min-req-subnet",
        type=int,
        default=100,
        help="Minimum requests in window to flag a subnet (default: 100)",
    )
    watch.add_argument(
        "--min-req-country",
        type=int,
        default=200,
        help="Minimum requests in window to flag a country (default: 200)",
    )
    watch.add_argument(
        "--subnet-v4",
        type=int,
        default=24,
        metavar="BITS",
        help="IPv4 subnet mask for range grouping (default: 24)",
    )
    watch.add_argument(
        "--top",
        type=int,
        default=15,
        metavar="N",
        help="Top N rows per table (default: 15)",
    )
    watch.add_argument(
        "--export-csv",
        type=Path,
        metavar="PATH",
        help="Write block recommendations to CSV (batch mode)",
    )
    watch.add_argument(
        "--export-json",
        type=Path,
        metavar="PATH",
        help="Write snapshot JSON (batch mode)",
    )
    watch.set_defaults(func=cmd_watch)
