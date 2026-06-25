from __future__ import annotations

import re
from datetime import datetime

from events import LogEvent

TIMESTAMP_FORMAT = "%d/%b/%Y:%H:%M:%S %z"

# Optional log-file prefix (tail multitail / zgrep) + Apache combined log.
ACCESS_RE = re.compile(
    r"^(?:"
    r"(?P<log_file>/var/log/apache2/\S+?):"
    r")?"
    r"(?P<remote_host>(?:\d{1,3}\.){3}\d{1,3}|::[\da-fA-F:]+|[\da-fA-F:.]+|-) "
    r"- - \[(?P<timestamp>[^\]]+)\] "
    r'"(?P<method>\S+) (?P<path>\S+) (?P<protocol>[^"]+)" '
    r"(?P<status>\d+) (?P<bytes>\S+) "
    r'"(?P<referrer>[^"]*)" '
    r"(?P<user_agent>.+)$"
)


def parse_access_line(line: str, *, default_source: str = "-") -> LogEvent | None:
    match = ACCESS_RE.match(line.strip())
    if not match:
        return None

    raw_bytes = match.group("bytes")
    user_agent = match.group("user_agent").strip()
    if user_agent.startswith('"') and user_agent.endswith('"'):
        user_agent = user_agent[1:-1]

    source = match.group("log_file") or default_source
    normalized_ua = user_agent if user_agent and user_agent != "-" else None

    return LogEvent(
        source=source,
        kind="access",
        timestamp=datetime.strptime(match.group("timestamp"), TIMESTAMP_FORMAT),
        remote_host=match.group("remote_host"),
        user_agent=normalized_ua,
        path=match.group("path"),
        status=int(match.group("status")),
        bytes_sent=0 if raw_bytes == "-" else int(raw_bytes),
        message=None,
    )
