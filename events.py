from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

LogKind = Literal["access", "error"]


def normalize_timestamp(timestamp: datetime) -> datetime:
    """Make access (tz-aware) and error (naive) timestamps comparable."""
    if timestamp.tzinfo is not None:
        return timestamp.replace(tzinfo=None)
    return timestamp


@dataclass(frozen=True)
class LogEvent:
    """Normalized log record for live monitoring and aggregation."""

    source: str
    kind: LogKind
    timestamp: datetime
    remote_host: str
    user_agent: str | None
    path: str | None
    status: int | None
    bytes_sent: int
    message: str | None
