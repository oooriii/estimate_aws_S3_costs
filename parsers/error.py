from __future__ import annotations

import re
from datetime import datetime

from events import LogEvent

# [Wed Jun 15 06:26:23.123456 2026] [error] [client 1.2.3.4:54321] message
ERROR_CLIENT_RE = re.compile(
    r"^\[(?P<timestamp>[^\]]+)\] "
    r"\[(?P<level>[^\]]+)\] "
    r"(?:\[[^\]]+\] )*"
    r"\[client (?P<remote_host>[^\]]+)\] "
    r"(?P<message>.+)$"
)

# [Wed Jun 15 06:26:23.123456 2026] [error] [pid 123] message (no client)
ERROR_SIMPLE_RE = re.compile(
    r"^\[(?P<timestamp>[^\]]+)\] "
    r"\[(?P<level>[^\]]+)\] "
    r"(?P<message>.+)$"
)

ERROR_TIMESTAMP_FORMATS = (
    "%a %b %d %H:%M:%S.%f %Y",
    "%a %b %d %H:%M:%S %Y",
)


def _parse_error_timestamp(raw: str) -> datetime | None:
    for fmt in ERROR_TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _normalize_remote_host(raw: str) -> str:
    host = raw.strip()
    if ":" in host and not host.startswith("["):
        # IPv4:port
        host = host.rsplit(":", 1)[0]
    elif host.startswith("[") and "]" in host:
        # [IPv6]:port
        host = host[1 : host.index("]")]
    return host


def parse_error_line(line: str, *, default_source: str = "-") -> LogEvent | None:
    stripped = line.strip()
    if not stripped or stripped[0] != "[":
        return None

    match = ERROR_CLIENT_RE.match(stripped)
    remote_host = "-"
    message = ""
    level = "error"
    timestamp_raw = ""

    if match:
        timestamp_raw = match.group("timestamp")
        level = match.group("level")
        remote_host = _normalize_remote_host(match.group("remote_host"))
        message = match.group("message").strip()
    else:
        simple = ERROR_SIMPLE_RE.match(stripped)
        if simple is None:
            return None
        timestamp_raw = simple.group("timestamp")
        level = simple.group("level")
        message = simple.group("message").strip()

    timestamp = _parse_error_timestamp(timestamp_raw)
    if timestamp is None:
        return None

    return LogEvent(
        source=default_source,
        kind="error",
        timestamp=timestamp,
        remote_host=remote_host,
        user_agent=None,
        path=None,
        status=None,
        bytes_sent=0,
        message=f"[{level}] {message}",
    )
