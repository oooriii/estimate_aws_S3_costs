from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from watch.aggregator import WatchSnapshot
from watch.config import WatchThresholds
from watch.subnet import collapse_subnets

BlockType = Literal["country", "subnet", "ip"]


@dataclass(frozen=True)
class BlockRecommendation:
    block_type: BlockType
    target: str
    country_code: str | None
    country_name: str | None
    requests: int
    rps: float
    reason: str
    detail: str


def _is_abusive_ip(
    stats_rps: float,
    stats_requests: int,
    thresholds: WatchThresholds,
) -> bool:
    return (
        stats_rps >= thresholds.min_rps_per_ip
        and stats_requests >= thresholds.min_requests_per_ip
    )


def _is_abusive_subnet(
    stats_rps: float,
    stats_requests: int,
    thresholds: WatchThresholds,
) -> bool:
    return (
        stats_rps >= thresholds.min_rps_per_subnet
        and stats_requests >= thresholds.min_requests_per_subnet
    )


def _is_abusive_country(
    stats_rps: float,
    stats_requests: int,
    thresholds: WatchThresholds,
) -> bool:
    return (
        stats_rps >= thresholds.min_rps_per_country
        and stats_requests >= thresholds.min_requests_per_country
    )


def recommend_blocks(
    snapshot: WatchSnapshot,
    *,
    thresholds: WatchThresholds,
) -> tuple[BlockRecommendation, ...]:
    recommendations: list[BlockRecommendation] = []

    for country in snapshot.countries:
        if country.country_code in ("LOCAL", "??", "OTHER"):
            continue
        if not _is_abusive_country(country.rps, country.requests, thresholds):
            continue

        top_subnets = [
            cidr
            for cidr, count in country.subnets.most_common()
            if count >= max(thresholds.min_requests_per_subnet // 5, 10)
        ]
        collapsed = collapse_subnets(top_subnets[:20])
        cidr_detail = ", ".join(collapsed[:10]) if collapsed else "—"

        recommendations.append(
            BlockRecommendation(
                block_type="country",
                target=country.country_code,
                country_code=country.country_code,
                country_name=country.country_name,
                requests=country.requests,
                rps=country.rps,
                reason="high_country_rps",
                detail=(
                    f"{len(country.unique_ips)} unique IPs; "
                    f"observed subnets: {cidr_detail}"
                ),
            )
        )

        for cidr in collapsed[:5]:
            count = country.subnets.get(cidr, 0)
            if count == 0:
                # collapsed block may cover multiple observed subnets
                count = sum(
                    requests
                    for subnet, requests in country.subnets.items()
                    if subnet in collapsed
                )
            recommendations.append(
                BlockRecommendation(
                    block_type="subnet",
                    target=cidr,
                    country_code=country.country_code,
                    country_name=country.country_name,
                    requests=count,
                    rps=country.rps,
                    reason="country_subnet_cluster",
                    detail=f"Part of abusive traffic from {country.country_name}",
                )
            )

    seen_ips: set[str] = set()
    for ip_stats in snapshot.ips:
        if ip_stats.key in ("-", "") or ip_stats.key in seen_ips:
            continue
        if not _is_abusive_ip(ip_stats.rps, ip_stats.requests, thresholds):
            continue
        seen_ips.add(ip_stats.key)
        recommendations.append(
            BlockRecommendation(
                block_type="ip",
                target=ip_stats.key,
                country_code=None,
                country_name=None,
                requests=ip_stats.requests,
                rps=ip_stats.rps,
                reason="high_ip_rps",
                detail=f"UA: {ip_stats.top_user_agent[:80]}",
            )
        )

    for subnet_stats in snapshot.subnets:
        if not _is_abusive_subnet(
            subnet_stats.rps,
            subnet_stats.requests,
            thresholds,
        ):
            continue
        if any(item.target == subnet_stats.key for item in recommendations):
            continue
        recommendations.append(
            BlockRecommendation(
                block_type="subnet",
                target=subnet_stats.key,
                country_code=None,
                country_name=None,
                requests=subnet_stats.requests,
                rps=subnet_stats.rps,
                reason="high_subnet_rps",
                detail=f"UA: {subnet_stats.top_user_agent[:80]}",
            )
        )

    return tuple(
        sorted(
            recommendations,
            key=lambda item: (-item.rps, -item.requests, item.target),
        )
    )
