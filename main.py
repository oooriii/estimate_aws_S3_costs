import argparse
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table

LOG_HEADER_RE = re.compile(
    r"^(?P<log_file>/var/log/apache2/\S+?):"
    r"(?P<remote_host>(?:\d{1,3}\.){3}\d{1,3}|::[\da-fA-F:]+|-) "
    r"- - \[(?P<timestamp>[^\]]+)\] "
    r'"(?P<method>\S+) (?P<path>\S+) (?P<protocol>[^"]+)" '
    r"(?P<status>\d+) (?P<bytes>\S+) "
    r'"(?P<referrer>[^"]*)" '
    r"(?P<user_agent>.+)$"
)

TIMESTAMP_FORMAT = "%d/%b/%Y:%H:%M:%S %z"


@dataclass
class LogLine:
    """
    Línia de log Apache amb prefix de fitxer d'origen.

    Exemple:
    /var/log/apache2/access_ssl_anubis.log:- - - [15/Jun/2026:06:26:23 +0200] "GET /bitstream/handle/10256/23347/TobosoSalaElisabet_Annexos.pdf?sequence=2&isAllowed=y HTTP/1.1" 200 11555603 "-" "Mozilla/5.0 ..."
    """

    log_file: str
    remote_host: str
    timestamp: datetime
    method: str
    path: str
    protocol: str
    status: int
    bytes_sent: int
    referrer: str
    user_agent: str

    @classmethod
    def from_line(cls, line: str) -> "LogLine | None":
        match = LOG_HEADER_RE.match(line.strip())
        if not match:
            return None

        raw_bytes = match.group("bytes")
        user_agent = match.group("user_agent").strip()
        if user_agent.startswith('"') and user_agent.endswith('"'):
            user_agent = user_agent[1:-1]

        return cls(
            log_file=match.group("log_file"),
            remote_host=match.group("remote_host"),
            timestamp=datetime.strptime(match.group("timestamp"), TIMESTAMP_FORMAT),
            method=match.group("method"),
            path=match.group("path"),
            protocol=match.group("protocol"),
            status=int(match.group("status")),
            bytes_sent=0 if raw_bytes == "-" else int(raw_bytes),
            referrer=match.group("referrer"),
            user_agent=user_agent,
        )


@dataclass
class FileStats:
    min_date: datetime | None
    max_date: datetime | None
    total_records: int
    total_bytes: int


def format_bytes(size: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:,.2f} {unit}" if unit != "B" else f"{int(value):,} B"
        value /= 1024
    return f"{size:,} B"


def parse_file(file_path: Path, progress: Progress | None = None) -> FileStats:
    """
    Parseja un fitxer en format de log Apache i retorna estadístiques agregades:
    data mínima i màxima, nombre total de registres i bytes descarregats.
    """
    min_date: datetime | None = None
    max_date: datetime | None = None
    total_records = 0
    total_bytes = 0

    task_id = None
    if progress is not None:
        task_id = progress.add_task("Parsejant log...", total=None)

    with file_path.open(encoding="utf-8") as file:
        for line in file:
            log_line = LogLine.from_line(line)
            if log_line is None:
                continue

            total_records += 1
            total_bytes += log_line.bytes_sent

            if min_date is None or log_line.timestamp < min_date:
                min_date = log_line.timestamp
            if max_date is None or log_line.timestamp > max_date:
                max_date = log_line.timestamp

            if progress is not None and task_id is not None:
                progress.update(task_id, completed=total_records)

    return FileStats(
        min_date=min_date,
        max_date=max_date,
        total_records=total_records,
        total_bytes=total_bytes,
    )


def print_stats(console: Console, file_path: Path, stats: FileStats) -> None:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Camp", style="bold cyan")
    table.add_column("Valor")

    table.add_row("Fitxer", str(file_path))
    table.add_row("Data mínima", str(stats.min_date) if stats.min_date else "—")
    table.add_row("Data màxima", str(stats.max_date) if stats.max_date else "—")
    table.add_row("Registres", f"{stats.total_records:,}")
    table.add_row("Bytes descarregats", format_bytes(stats.total_bytes))

    console.print(
        Panel(table, title="[bold]Resultats de l'estudi[/bold]", border_style="green")
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analitza fitxers de log Apache i calcula estadístiques de descàrrega.",
    )
    parser.add_argument(
        "file",
        type=Path,
        help="Fitxer de log d'entrada",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    console = Console()
    args = build_parser().parse_args(argv)

    if not args.file.is_file():
        console.print(f"[red]Error:[/red] el fitxer '{args.file}' no existeix.")
        return 1

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=40),
        TextColumn("{task.completed:,} registres"),
        console=console,
        transient=True,
    ) as progress:
        stats = parse_file(args.file, progress=progress)

    if stats.total_records == 0:
        console.print(
            f"[yellow]Avís:[/yellow] no s'ha trobat cap registre vàlid a '{args.file}'."
        )
        return 1

    print_stats(console, args.file, stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
