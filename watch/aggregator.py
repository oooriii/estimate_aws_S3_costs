from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from events import LogEvent
from geo import GeoIpResolver, classify_remote_host
from watch.burst import BurstTracker
from watch.config import WatchThresholds
from watch.filters import WatchFilters
from watch.subnet import subnet_key


@dataclass
class ActorStats:
    key: str
    requests: int = 0
    rps: float = 0.0
    burst_count: int = 0
    max_burst_rps: float = 0.0
    max_burst_requests: int = 0
    last_seen: datetime | None = None
    user_agents: Counter[str] = field(default_factory=Counter)
    statuses: Counter[int] = field(default_factory=Counter)
    kinds: Counter[str] = field(default_factory=Counter)

    @property
    def top_user_agent(self) -> str:
        if not self.user_agents:
            return "—"
        return self.user_agents.most_common(1)[0][0]


@dataclass
class CountryStats:
    country_code: str
    country_name: str
    requests: int = 0
    rps: float = 0.0
    unique_ips: set[str] = field(default_factory=set)
    subnets: Counter[str] = field(default_factory=Counter)


@dataclass
class WatchSnapshot:
    window_seconds: float
    total_requests: int
    current_rps: float
    window_start: datetime | None
    window_end: datetime | None
    ips: tuple[ActorStats, ...]
    subnets: tuple[ActorStats, ...]
    countries: tuple[CountryStats, ...]
    user_agents: tuple[ActorStats, ...]


def _country_for_event(
    event: LogEvent,
    geo_resolver: GeoIpResolver | None,
) -> tuple[str, str]:
    normalized = classify_remote_host(event.remote_host)
    if normalized is not None:
        return normalized
    if geo_resolver is None:
        return "??", "Unknown"
    return geo_resolver.lookup(event.remote_host)


class WatchAggregator:
    def __init__(
        self,
        *,
        thresholds: WatchThresholds | None = None,
        geo_resolver: GeoIpResolver | None = None,
        filters: WatchFilters | None = None,
    ) -> None:
        self.thresholds = thresholds or WatchThresholds()
        self.geo_resolver = geo_resolver
        self.filters = filters or WatchFilters()
        self._events: deque[tuple[datetime, LogEvent, str, str, str | None]] = deque()
        self._total_requests = 0
        self.skipped_events = 0
        self._ip_bursts = BurstTracker(
            burst_window_seconds=self.thresholds.burst_window_seconds
        )
        self._subnet_bursts = BurstTracker(
            burst_window_seconds=self.thresholds.burst_window_seconds
        )

    def ingest(self, event: LogEvent) -> None:
        if self.filters.should_skip(event, self.geo_resolver):
            self.skipped_events += 1
            return

        country_code, country_name = _country_for_event(event, self.geo_resolver)
        subnet = subnet_key(
            event.remote_host,
            mask_v4=self.thresholds.subnet_mask_v4,
            mask_v6=self.thresholds.subnet_mask_v6,
        )
        self._events.append(
            (event.timestamp, event, country_code, country_name, subnet)
        )
        self._total_requests += 1

        if event.remote_host not in ("-", ""):
            self._ip_bursts.record(event.remote_host, event.timestamp)
        if subnet is not None:
            self._subnet_bursts.record(subnet, event.timestamp)

        self._prune(event.timestamp)

    def _prune(self, now: datetime) -> None:
        cutoff = now - timedelta(seconds=self.thresholds.window_seconds)
        while self._events and self._events[0][0] < cutoff:
            self._events.popleft()

    def snapshot(self, *, now: datetime | None = None) -> WatchSnapshot:
        if not self._events:
            return WatchSnapshot(
                window_seconds=self.thresholds.window_seconds,
                total_requests=0,
                current_rps=0.0,
                window_start=None,
                window_end=None,
                ips=(),
                subnets=(),
                countries=(),
                user_agents=(),
            )

        window_end = now or self._events[-1][0]
        self._prune(window_end)
        window_start = self._events[0][0]
        window_seconds = max(
            (window_end - window_start).total_seconds(),
            1.0,
        )
        total_requests = len(self._events)
        current_rps = total_requests / window_seconds

        by_ip: dict[str, ActorStats] = {}
        by_subnet: dict[str, ActorStats] = {}
        by_ua: dict[str, ActorStats] = {}
        by_country: dict[tuple[str, str], CountryStats] = {}

        for _ts, event, country_code, country_name, subnet in self._events:
            ip_stats = by_ip.setdefault(
                event.remote_host,
                ActorStats(key=event.remote_host),
            )
            ip_stats.requests += 1
            ip_stats.last_seen = event.timestamp
            ip_stats.kinds[event.kind] += 1
            if event.user_agent:
                ip_stats.user_agents[event.user_agent] += 1
            if event.status is not None:
                ip_stats.statuses[event.status] += 1

            if subnet is not None:
                subnet_stats = by_subnet.setdefault(subnet, ActorStats(key=subnet))
                subnet_stats.requests += 1
                subnet_stats.last_seen = event.timestamp
                subnet_stats.kinds[event.kind] += 1
                if event.user_agent:
                    subnet_stats.user_agents[event.user_agent] += 1
                if event.status is not None:
                    subnet_stats.statuses[event.status] += 1

            ua_key = event.user_agent or "(no user-agent)"
            ua_stats = by_ua.setdefault(ua_key, ActorStats(key=ua_key))
            ua_stats.requests += 1
            ua_stats.last_seen = event.timestamp
            ua_stats.kinds[event.kind] += 1
            if event.status is not None:
                ua_stats.statuses[event.status] += 1

            country_bucket = by_country.setdefault(
                (country_code, country_name),
                CountryStats(country_code=country_code, country_name=country_name),
            )
            country_bucket.requests += 1
            if event.remote_host not in ("-", ""):
                country_bucket.unique_ips.add(event.remote_host)
            if subnet is not None:
                country_bucket.subnets[subnet] += 1

        def with_rps(items: dict[str, ActorStats]) -> tuple[ActorStats, ...]:
            result: list[ActorStats] = []
            for stats in items.values():
                stats.rps = stats.requests / window_seconds
                if stats.key in by_ip:
                    burst = self._ip_bursts.metrics(stats.key)
                elif stats.key in by_subnet:
                    burst = self._subnet_bursts.metrics(stats.key)
                else:
                    burst = None
                if burst is not None:
                    stats.burst_count = burst.burst_count
                    stats.max_burst_rps = burst.max_burst_rps
                    stats.max_burst_requests = burst.max_burst_requests
                result.append(stats)
            return tuple(
                sorted(result, key=lambda item: (-item.requests, item.key))[
                    : self.thresholds.top_n
                ]
            )

        countries: list[CountryStats] = []
        for stats in by_country.values():
            stats.rps = stats.requests / window_seconds
            countries.append(stats)
        countries.sort(key=lambda item: (-item.requests, item.country_code))

        return WatchSnapshot(
            window_seconds=self.thresholds.window_seconds,
            total_requests=total_requests,
            current_rps=current_rps,
            window_start=window_start,
            window_end=window_end,
            ips=with_rps(by_ip),
            subnets=with_rps(by_subnet),
            countries=tuple(countries[: self.thresholds.top_n]),
            user_agents=with_rps(by_ua),
        )
