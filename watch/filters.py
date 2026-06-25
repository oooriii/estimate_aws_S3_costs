from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field

from events import LogEvent
from geo import GeoIpResolver, classify_remote_host


@dataclass
class WatchFilters:
    """Traffic filters: ignored clients are dropped; whitelisted clients are trusted."""

    ignore_ips: tuple[str, ...] = ("127.0.0.1", "::1")
    ignore_cidrs: tuple[str, ...] = ()
    ignore_private: bool = True
    whitelist_ips: tuple[str, ...] = ()
    whitelist_cidrs: tuple[str, ...] = ()
    whitelist_countries: tuple[str, ...] = ("LOCAL",)

    _ignore_networks: list[ipaddress._BaseNetwork] = field(
        default_factory=list, init=False, repr=False
    )
    _whitelist_networks: list[ipaddress._BaseNetwork] = field(
        default_factory=list, init=False, repr=False
    )
    _whitelist_hosts: set[str] = field(default_factory=set, init=False, repr=False)
    _ignore_hosts: set[str] = field(default_factory=set, init=False, repr=False)

    def __post_init__(self) -> None:
        self._ignore_hosts = {ip for ip in self.ignore_ips if ip}
        self._whitelist_hosts = {ip for ip in self.whitelist_ips if ip}
        self._ignore_networks = self._parse_networks(self.ignore_cidrs)
        self._whitelist_networks = self._parse_networks(self.whitelist_cidrs)

    @staticmethod
    def _parse_networks(cidrs: tuple[str, ...]) -> list[ipaddress._BaseNetwork]:
        networks: list[ipaddress._BaseNetwork] = []
        for cidr in cidrs:
            try:
                networks.append(ipaddress.ip_network(cidr, strict=False))
            except ValueError:
                continue
        return networks

    def _in_networks(
        self,
        remote_host: str,
        networks: list[ipaddress._BaseNetwork],
    ) -> bool:
        try:
            address = ipaddress.ip_address(remote_host)
        except ValueError:
            return False
        return any(address in network for network in networks)

    def _country_for_event(
        self,
        event: LogEvent,
        geo_resolver: GeoIpResolver | None,
    ) -> tuple[str, str]:
        normalized = classify_remote_host(event.remote_host)
        if normalized is not None:
            return normalized
        if geo_resolver is None:
            return "??", "Unknown"
        return geo_resolver.lookup(event.remote_host)

    def should_skip(
        self,
        event: LogEvent,
        geo_resolver: GeoIpResolver | None,
    ) -> bool:
        host = event.remote_host
        if not host or host == "-":
            return True

        if host in self._ignore_hosts:
            return True
        if host in self._whitelist_hosts:
            return True
        if self._in_networks(host, self._ignore_networks):
            return True
        if self._in_networks(host, self._whitelist_networks):
            return True

        if self.ignore_private:
            try:
                address = ipaddress.ip_address(host)
            except ValueError:
                return False
            if (
                address.is_private
                or address.is_loopback
                or address.is_link_local
            ):
                return True

        country_code, _country_name = self._country_for_event(event, geo_resolver)
        if country_code in self.whitelist_countries:
            return True

        return False
