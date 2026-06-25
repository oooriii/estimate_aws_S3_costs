from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console
from rich.table import Table

from defaults import discover_geoip_db
from geo import MaxMindGeoIpResolver, open_geoip_resolver
from watch.iptables_consolidate import (
    consolidate_ip_file,
    write_consolidation_csv,
    write_ipset_script,
)


def cmd_consolidate(args: argparse.Namespace) -> int:
    console = Console()

    if not args.file.is_file():
        console.print(f"[red]Error:[/red] file '{args.file}' does not exist.")
        return 1

    geoip_path = args.geoip_db or discover_geoip_db()
    resolver = None
    if geoip_path is not None:
        try:
            resolver = open_geoip_resolver(geoip_path)
        except (OSError, RuntimeError, ValueError) as exc:
            console.print(f"[red]Error:[/red] {exc}")
            return 1

    try:
        result = consolidate_ip_file(
            args.file,
            geo_resolver=resolver,
            group_by_country=not args.no_group_by_country,
        )
    finally:
        if isinstance(resolver, MaxMindGeoIpResolver):
            resolver.close()

    if result.unique_ips == 0:
        console.print("[yellow]Warning:[/yellow] no valid IPs found in input file.")
        return 1

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Field", style="bold cyan")
    table.add_column("Value")
    table.add_row("Input lines", f"{result.input_ips:,}")
    table.add_row("Unique IPs", f"{result.unique_ips:,}")
    table.add_row("Consolidated CIDR ranges", f"{result.output_ranges:,}")
    reduction = 100.0 * (1 - result.output_ranges / result.unique_ips)
    table.add_row("Rule reduction", f"{reduction:.1f}%")
    console.print(table)

    preview = Table(show_header=True, header_style="bold cyan")
    preview.add_column("Country")
    preview.add_column("Code")
    preview.add_column("CIDR")
    preview.add_column("IPs covered", justify="right")
    for item in result.ranges[: args.top]:
        preview.add_row(
            item.country_name,
            item.country_code,
            item.cidr,
            f"{item.ips_covered:,}",
        )
    console.print(preview)

    if args.csv is not None:
        write_consolidation_csv(args.csv, result)
        console.print(f"[green]CSV written to[/green] {args.csv}")
    if args.ipset is not None:
        write_ipset_script(args.ipset, result)
        console.print(f"[green]ipset script written to[/green] {args.ipset}")

    return 0


def register_consolidate_command(subparsers: argparse._SubParsersAction) -> None:
    consolidate = subparsers.add_parser(
        "consolidate",
        help="Collapse many blocked IPs into fewer CIDR ranges for iptables/ipset",
    )
    consolidate.add_argument(
        "file",
        type=Path,
        help="Text file with one IP per line (e.g. iptables export)",
    )
    consolidate.add_argument(
        "--geoip-db",
        type=Path,
        metavar="PATH",
        help="GeoLite2-Country.mmdb to group ranges by country",
    )
    consolidate.add_argument(
        "--csv",
        type=Path,
        metavar="PATH",
        help="Write consolidated CIDR ranges to CSV",
    )
    consolidate.add_argument(
        "--ipset",
        type=Path,
        metavar="PATH",
        help="Write bash script to populate an ipset with consolidated ranges",
    )
    consolidate.add_argument(
        "--top",
        type=int,
        default=25,
        metavar="N",
        help="Preview top N ranges in terminal (default: 25)",
    )
    consolidate.add_argument(
        "--no-group-by-country",
        action="store_true",
        help="Collapse all IPs globally instead of per country",
    )
    consolidate.set_defaults(func=cmd_consolidate)
