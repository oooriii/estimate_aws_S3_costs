from __future__ import annotations

import gzip
import sys
from collections.abc import Iterator
from pathlib import Path

from events import LogEvent
from parsers.detect import parse_log_line


def _kind_hint_for_path(path: Path) -> str | None:
    name = path.name.lower()
    if "error" in name:
        return "error"
    if "access" in name:
        return "access"
    return None


def _open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return path.open(encoding="utf-8", errors="replace")


def iter_events_from_lines(
    lines: Iterator[str],
    *,
    default_source: str = "-",
    kind_hint: str | None = None,
) -> Iterator[LogEvent]:
    for line in lines:
        if not line.strip():
            continue
        event = parse_log_line(
            line,
            default_source=default_source,
            kind_hint=kind_hint,
        )
        if event is not None:
            yield event


def iter_events_from_file(path: Path) -> Iterator[LogEvent]:
    kind_hint = _kind_hint_for_path(path)
    with _open_text(path) as handle:
        yield from iter_events_from_lines(
            handle,
            default_source=str(path),
            kind_hint=kind_hint,
        )


def iter_events_from_stdin() -> Iterator[LogEvent]:
    yield from iter_events_from_lines(sys.stdin, default_source="stdin")


def iter_events(paths: list[Path] | None = None) -> Iterator[LogEvent]:
    if paths:
        for path in paths:
            yield from iter_events_from_file(path)
        return
    yield from iter_events_from_stdin()
