from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from defaults import discover_geoip_db
from geo import MaxMindGeoIpResolver, open_geoip_resolver
from watch.iptables_consolidate import write_consolidation_csv
from watch.ruleset_report import (
    analyze_ruleset,
    write_ruleset_countries_csv,
    write_ruleset_report_json,
    write_simplified_nftables,
)


def cmd_ruleset(args: argparse.Namespace) -> int:
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
        report = analyze_ruleset(
            args.file,
            geo_resolver=resolver,
            group_by_country=not args.no_group_by_country,
        )
    finally:
        if isinstance(resolver, MaxMindGeoIpResolver):
            resolver.close()

    if report.total_unique_ips == 0:
        console.print("[yellow]Warning:[/yellow] no IPv4 entries found in ruleset.")
        return 1

    summary = Table(show_header=False, box=None, padding=(0, 2))
    summary.add_column("Field", style="bold cyan")
    summary.add_column("Value")
    summary.add_row("File", str(report.source_path))
    summary.add_row("File size", f"{report.file_size_bytes:,} bytes")
    summary.add_row("Total IP entries", f"{report.total_entries:,}")
    summary.add_row("Unique IPs", f"{report.total_unique_ips:,}")
    summary.add_row(
        "Consolidated CIDRs",
        f"{report.consolidation.output_ranges:,}",
    )
    reduction = 100.0 * (
        1 - report.consolidation.output_ranges / report.total_unique_ips
    )
    summary.add_row("Potential reduction", f"{reduction:.1f}%")
    summary.add_row("Empty sets", ", ".join(report.empty_sets) or "—")
    summary.add_row("Active sets", ", ".join(report.active_sets) or "—")
    console.print(Panel(summary, title="[bold]Ruleset analysis[/bold]", border_style="green"))
    console.print(
        Panel(report.performance_assessment, title="[bold]Assessment[/bold]", border_style="yellow")
    )

    sets_table = Table(show_header=True, header_style="bold cyan")
    sets_table.add_column("Set")
    sets_table.add_column("Entries", justify="right")
    sets_table.add_column("Unique", justify="right")
    sets_table.add_column("Used", justify="center")
    sets_table.add_column("-> CIDRs", justify="right")
    sets_table.add_column("Reduction", justify="right")
    for item in report.set_summaries:
        sets_table.add_row(
            item.name,
            f"{item.entry_count:,}",
            f"{item.unique_ips:,}",
            "yes" if item.referenced else "no",
            f"{item.consolidated_ranges:,}",
            f"{item.consolidation_reduction_pct:.1f}%",
        )
    console.print(sets_table)

    countries_table = Table(show_header=True, header_style="bold cyan")
    countries_table.add_column("Country")
    countries_table.add_column("Code")
    countries_table.add_column("IPs", justify="right")
    countries_table.add_column("%", justify="right")
    for item in report.countries[: args.top_countries]:
        countries_table.add_row(
            item.country_name,
            item.country_code,
            f"{item.ip_count:,}",
            f"{item.pct_of_total:.1f}",
        )
    console.print(countries_table)

    output_dir = args.output_dir
    if output_dir is None:
        output_dir = Path("reports") / "ruleset"
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = args.json or (output_dir / "ruleset-report.json")
    countries_csv = args.countries_csv or (output_dir / "ruleset-countries.csv")
    cidrs_csv = args.cidrs_csv or (output_dir / "ruleset-consolidated.csv")
    nft_path = args.simplified_nft or (output_dir / "ruleset-simplified.nft")

    write_ruleset_report_json(json_path, report)
    write_ruleset_countries_csv(countries_csv, report)
    write_consolidation_csv(cidrs_csv, report.consolidation)
    write_simplified_nftables(nft_path, report, set_name=args.set_name)

    console.print(f"[green]JSON report:[/green] {json_path}")
    console.print(f"[green]Countries CSV:[/green] {countries_csv}")
    console.print(f"[green]Consolidated CIDRs CSV:[/green] {cidrs_csv}")
    console.print(f"[green]Simplified nftables:[/green] {nft_path}")

    return 0


def register_ruleset_command(subparsers: argparse._SubParsersAction) -> None:
    ruleset = subparsers.add_parser(
        "ruleset",
        help="Analyze an nftables ruleset dump and report countries, IPs, and CIDR consolidation",
    )
    ruleset.add_argument(
        "file",
        type=Path,
        help="nftables ruleset dump (output of nft -a list ruleset)",
    )
    ruleset.add_argument(
        "--geoip-db",
        type=Path,
        metavar="PATH",
        help="GeoLite2-Country.mmdb for country breakdown",
    )
    ruleset.add_argument(
        "--output-dir",
        type=Path,
        metavar="DIR",
        help="Output directory (default: reports/ruleset/)",
    )
    ruleset.add_argument(
        "--json",
        type=Path,
        metavar="PATH",
        help="JSON report output path",
    )
    ruleset.add_argument(
        "--countries-csv",
        type=Path,
        metavar="PATH",
        help="Country breakdown CSV path",
    )
    ruleset.add_argument(
        "--cidrs-csv",
        type=Path,
        metavar="PATH",
        help="Consolidated CIDR ranges CSV path",
    )
    ruleset.add_argument(
        "--simplified-nft",
        type=Path,
        metavar="PATH",
        help="Simplified nftables snippet with consolidated CIDR set",
    )
    ruleset.add_argument(
        "--set-name",
        default="blocked_consolidated",
        metavar="NAME",
        help="Set name in simplified nftables output (default: blocked_consolidated)",
    )
    ruleset.add_argument(
        "--top-countries",
        type=int,
        default=20,
        metavar="N",
        help="Show top N countries in terminal (default: 20)",
    )
    ruleset.add_argument(
        "--no-group-by-country",
        action="store_true",
        help="Consolidate CIDRs globally instead of per country",
    )
    ruleset.set_defaults(func=cmd_ruleset)
