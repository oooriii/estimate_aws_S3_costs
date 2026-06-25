from __future__ import annotations

from events import LogEvent
from parsers.access import parse_access_line
from parsers.error import parse_error_line


def parse_log_line(
    line: str,
    *,
    default_source: str = "-",
    kind_hint: str | None = None,
) -> LogEvent | None:
    """Parse an Apache access or error log line."""
    if kind_hint == "access":
        return parse_access_line(line, default_source=default_source)
    if kind_hint == "error":
        return parse_error_line(line, default_source=default_source)

    event = parse_access_line(line, default_source=default_source)
    if event is not None:
        return event
    return parse_error_line(line, default_source=default_source)
