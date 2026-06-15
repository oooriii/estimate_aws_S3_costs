from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn

from defaults import default_demand_paths
from demand import parse_file_demand
from demand_report import print_demand_report
from export_demand_csv import write_top_files_csv
from pdf_report import write_demand_pdf


def register_demand_command(subparsers: argparse._SubParsersAction) -> None:
    demand = subparsers.add_parser(
        "demand",
        help="Analyze which files or bitstreams are most downloaded",
    )
    demand.add_argument("file", type=Path, help="Input log file")
    demand.add_argument(
        "--top",
        type=int,
        default=25,
        metavar="N",
        help="Show top N files in the terminal and exports (default: 25)",
    )
    demand.add_argument(
        "--all-paths",
        action="store_true",
        help="Include non-bitstream paths (static assets, etc.)",
    )
    demand.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports"),
        help="Default directory for PDF and CSV outputs",
    )
    demand.add_argument(
        "--pdf",
        type=Path,
        metavar="PATH",
        help="Write a file demand PDF report (default: <output-dir>/file-demand.pdf)",
    )
    demand.add_argument(
        "--no-pdf",
        action="store_true",
        help="Skip PDF export",
    )
    demand.add_argument(
        "--csv",
        type=Path,
        metavar="PATH",
        help="Write top files to CSV (default: <output-dir>/top-files.csv)",
    )
    demand.add_argument(
        "--no-csv",
        action="store_true",
        help="Skip CSV export",
    )
    demand.set_defaults(func=cmd_demand)


def resolve_demand_outputs(args: argparse.Namespace) -> tuple[Path | None, Path | None]:
    default_pdf, default_csv = default_demand_paths(output_dir=args.output_dir)
    pdf_path = None if args.no_pdf else (args.pdf or default_pdf)
    csv_path = None if args.no_csv else (args.csv or default_csv)
    return pdf_path, csv_path


def cmd_demand(args: argparse.Namespace) -> int:
    console = Console()

    if not args.file.is_file():
        console.print(f"[red]Error:[/red] file '{args.file}' does not exist.")
        return 1

    if args.top < 0:
        console.print("[red]Error:[/red] --top must be >= 0.")
        return 1

    bitstreams_only = not args.all_paths
    pdf_path, csv_path = resolve_demand_outputs(args)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=40),
        TextColumn("{task.completed:,} records"),
        console=console,
        transient=True,
    ) as progress:
        result = parse_file_demand(
            args.file,
            bitstreams_only=bitstreams_only,
            progress=progress,
        )

    if result.stats.total_records == 0:
        hint = (
            " No bitstream paths matched (DSpace /bitstream/... URLs). "
            "Try --all-paths to include other request paths."
            if bitstreams_only
            else ""
        )
        console.print(
            f"[yellow]Warning:[/yellow] no matching records found in '{args.file}'.{hint}"
        )
        return 1

    print_demand_report(
        console,
        args.file,
        result,
        bitstreams_only=bitstreams_only,
        top=args.top,
    )

    if pdf_path is not None:
        try:
            write_demand_pdf(
                pdf_path,
                log_file=args.file,
                result=result,
                top=args.top,
                bitstreams_only=bitstreams_only,
            )
        except OSError as exc:
            console.print(f"[red]Error:[/red] could not write PDF: {exc}")
            return 1
        console.print(f"[green]PDF report written to[/green] {pdf_path}")

    if csv_path is not None:
        csv_limit = args.top or None
        try:
            row_count = write_top_files_csv(
                csv_path,
                result.files,
                total_records=result.stats.total_records,
                total_bytes=result.stats.total_bytes,
                limit=csv_limit,
            )
        except OSError as exc:
            console.print(f"[red]Error:[/red] could not write CSV: {exc}")
            return 1
        console.print(
            f"[green]Top files CSV written to[/green] {csv_path} ({row_count} rows)"
        )

    return 0
