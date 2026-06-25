from __future__ import annotations

import ipaddress


def subnet_key(remote_host: str, *, mask_v4: int = 24, mask_v6: int = 48) -> str | None:
    if remote_host in ("-", ""):
        return None
    try:
        address = ipaddress.ip_address(remote_host)
    except ValueError:
        return None
    if address.version == 4:
        network = ipaddress.ip_network(f"{address}/{mask_v4}", strict=False)
    else:
        network = ipaddress.ip_network(f"{address}/{mask_v6}", strict=False)
    return str(network)


def collapse_subnets(cidr_keys: list[str]) -> list[str]:
    """Merge adjacent/overlapping CIDR blocks where possible."""
    networks: list[ipaddress._BaseNetwork] = []
    for key in cidr_keys:
        try:
            networks.append(ipaddress.ip_network(key, strict=False))
        except ValueError:
            continue
    if not networks:
        return []
    collapsed = list(ipaddress.collapse_addresses(networks))
    return [
        str(network)
        for network in sorted(
            collapsed,
            key=lambda n: (n.version, n.network_address),
        )
    ]
