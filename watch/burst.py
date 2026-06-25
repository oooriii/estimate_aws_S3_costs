from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class BurstMetrics:
    burst_count: int = 0
    max_burst_requests: int = 0
    max_burst_rps: float = 0.0


@dataclass
class _BurstState:
    last_ts: datetime | None = None
    burst_start: datetime | None = None
    current_burst_requests: int = 0
    burst_count: int = 0
    max_burst_requests: int = 0
    max_burst_rps: float = 0.0


@dataclass
class BurstTracker:
    """Group rapid requests from the same actor into bursts."""

    burst_window_seconds: float
    _states: dict[str, _BurstState] = field(default_factory=dict)

    def record(self, key: str, timestamp: datetime) -> None:
        if not key or key == "-":
            return

        state = self._states.setdefault(key, _BurstState())
        if state.last_ts is None:
            state.burst_start = timestamp
            state.current_burst_requests = 1
            state.burst_count = 1
            state.last_ts = timestamp
            return

        gap = (timestamp - state.last_ts).total_seconds()
        if gap <= self.burst_window_seconds:
            state.current_burst_requests += 1
        else:
            self._finalize_burst(state)
            state.burst_count += 1
            state.burst_start = timestamp
            state.current_burst_requests = 1

        state.last_ts = timestamp

    def metrics(self, key: str) -> BurstMetrics:
        state = self._states.get(key)
        if state is None:
            return BurstMetrics()
        self._finalize_burst(state)
        return BurstMetrics(
            burst_count=state.burst_count,
            max_burst_requests=state.max_burst_requests,
            max_burst_rps=state.max_burst_rps,
        )

    def _finalize_burst(self, state: _BurstState) -> None:
        if state.burst_start is None or state.last_ts is None:
            return
        if state.current_burst_requests <= 0:
            return

        duration = max((state.last_ts - state.burst_start).total_seconds(), 0.001)
        burst_rps = state.current_burst_requests / duration
        state.max_burst_requests = max(
            state.max_burst_requests,
            state.current_burst_requests,
        )
        state.max_burst_rps = max(state.max_burst_rps, burst_rps)
