from __future__ import annotations

import gzip
import re
import sys
from collections.abc import Iterator
from pathlib import Path

from events import LogEvent, normalize_timestamp
from parsers.detect import parse_log_line

MULTITAIL_HEADER_RE = re.compile(r"^==>\s+(.+?)\s+<==$")


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


def _parse_line(
    line: str,
    *,
    default_source: str,
    kind_hint: str | None,
) -> LogEvent | None:
    event = parse_log_line(
        line,
        default_source=default_source,
        kind_hint=kind_hint,
    )
    if event is None:
        return None
    return LogEvent(
        source=event.source,
        kind=event.kind,
        timestamp=normalize_timestamp(event.timestamp),
        remote_host=event.remote_host,
        user_agent=event.user_agent,
        path=event.path,
        status=event.status,
        bytes_sent=event.bytes_sent,
        message=event.message,
    )


def iter_events_from_lines(
    lines: Iterator[str],
    *,
    default_source: str = "-",
    kind_hint: str | None = None,
) -> Iterator[LogEvent]:
    current_source = default_source
    current_kind_hint = kind_hint

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        multitail = MULTITAIL_HEADER_RE.match(stripped)
        if multitail is not None:
            current_source = multitail.group(1)
            current_kind_hint = _kind_hint_for_path(Path(current_source))
            continue

        event = _parse_line(
            stripped,
            default_source=current_source,
            kind_hint=current_kind_hint,
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
