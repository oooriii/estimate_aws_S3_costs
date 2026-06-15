from __future__ import annotations

from dataclasses import dataclass

from parser import TrafficStats
from pricing.schema import PricingConfig
from pricing.tiers import tiered_cost, tiered_cost_breakdown
from projection import compound_annual_factor, project_traffic

BYTES_PER_GB = 1024**3
DEFAULT_CONSERVATIVE_SAFETY_MARGIN = 0.20


@dataclass(frozen=True)
class Inventory:
    storage_gb: float
    items: int
    annual_growth_rate: float = 0.0


@dataclass(frozen=True)
class CostLine:
    label: str
    usd: float
    calculation: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScenarioCosts:
    name: str
    monthly: tuple[CostLine, ...]
    annual: tuple[CostLine, ...]

    @property
    def monthly_total(self) -> float:
        return sum(line.usd for line in self.monthly)

    @property
    def annual_total(self) -> float:
        return sum(line.usd for line in self.annual)

    def total_calculation(self, *, period: str, growth_rate: float = 0.0) -> str:
        lines = self.monthly if period == "monthly" else self.annual
        total = self.monthly_total if period == "monthly" else self.annual_total
        parts = [f"{line.usd:.2f} USD" for line in lines]
        suffix = "monthly" if period == "monthly" else "annual"
        if period == "annual" and growth_rate > 0:
            suffix = f"annual ({growth_rate:.0%}/yr growth on all lines)"
        return f"{' + '.join(parts)} = {total:.2f} USD (total {suffix})"


@dataclass(frozen=True)
class EstimateResult:
    realistic_s3: ScenarioCosts
    conservative: ScenarioCosts
    realistic_cloudfront: ScenarioCosts | None


def _fmt_qty(value: float) -> str:
    if abs(value - round(value)) < 1e-9 and abs(value) < 1e15:
        return f"{int(round(value)):,}"
    return f"{value:,.2f}"


def _storage_calculation(
    inventory: Inventory,
    pricing: PricingConfig,
    storage_class: str,
) -> tuple[str, ...]:
    gb = inventory.storage_gb
    price = pricing.s3.storage_per_gb_month[storage_class]
    total = gb * price
    return (
        f"{_fmt_qty(gb)} GB x {price} USD/GB-mo = {total:.2f} USD "
        f"({storage_class} storage)",
    )


def _monitoring_calculation(inventory: Inventory, pricing: PricingConfig) -> tuple[str, ...]:
    per_1k = pricing.s3.intelligent_tiering_monitoring_per_1000_objects
    total = _monitoring_monthly_cost(inventory, pricing)
    return (
        f"{_fmt_qty(inventory.items)} objects / 1,000 x {per_1k} USD "
        f"= {total:.4f} USD (Intelligent-Tiering monitoring)",
    )


def _get_requests_calculation(
    requests: float,
    pricing: PricingConfig,
    *,
    label: str = "GET requests",
) -> tuple[str, ...]:
    per_1k = pricing.s3.requests_per_1000["GET"]
    per_request = per_1k / 1000.0
    total = (requests / 1000.0) * per_1k
    return (
        f"{_fmt_qty(requests)} {label} x {per_request:.7f} USD/request "
        f"= {total:.2f} USD",
    )


def _egress_calculation(
    bytes_amount: float,
    pricing: PricingConfig,
    *,
    use_cloudfront: bool,
    first_tier_only: bool,
    label: str,
) -> tuple[str, ...]:
    amount_gb = bytes_amount / BYTES_PER_GB
    if amount_gb <= 0:
        return (f"0 GB transferred = 0.00 USD ({label})",)

    tiers = (
        pricing.cloudfront.data_transfer_out_per_gb
        if use_cloudfront and pricing.cloudfront
        else pricing.s3.data_transfer_out_per_gb
    )
    service = "CloudFront" if use_cloudfront else "S3"

    if first_tier_only:
        price = tiers[0].price
        total = amount_gb * price
        return (
            f"Tiered price for: {_fmt_qty(amount_gb)} GB ({service}, first tier only)",
            f"{_fmt_qty(amount_gb)} GB x {price} USD/GB = {total:.2f} USD ({label})",
        )

    slices = tiered_cost_breakdown(amount_gb, tiers)
    lines = [f"Tiered price for: {_fmt_qty(amount_gb)} GB ({service})"]
    for item in slices:
        lines.append(
            f"{_fmt_qty(item.gb)} GB x {item.price_per_gb} USD/GB "
            f"= {item.subtotal_usd:.2f} USD"
        )
    total = tiered_cost(amount_gb, tiers)
    lines.append(f"Total tier cost = {total:.2f} USD ({label})")
    return tuple(lines)


def _cloudfront_requests_calculation(
    requests: float,
    pricing: PricingConfig,
) -> tuple[str, ...]:
    per_10k = pricing.cloudfront.requests_per_10000["GET"]
    per_request = per_10k / 10_000.0
    total = (requests / 10_000.0) * per_10k
    return (
        f"{_fmt_qty(requests)} CloudFront GET requests x {per_request:.7f} USD/request "
        f"= {total:.2f} USD",
    )


def _egress_cost(
    bytes_amount: float,
    pricing: PricingConfig,
    *,
    use_cloudfront: bool,
    first_tier_only: bool,
) -> float:
    amount_gb = bytes_amount / BYTES_PER_GB
    if amount_gb <= 0:
        return 0.0

    tiers = (
        pricing.cloudfront.data_transfer_out_per_gb
        if use_cloudfront and pricing.cloudfront
        else pricing.s3.data_transfer_out_per_gb
    )
    if first_tier_only:
        return amount_gb * tiers[0].price
    return tiered_cost(amount_gb, tiers)


def _storage_monthly_cost(
    inventory: Inventory,
    pricing: PricingConfig,
    storage_class: str,
) -> float:
    return inventory.storage_gb * pricing.s3.storage_per_gb_month[storage_class]


def _monitoring_monthly_cost(inventory: Inventory, pricing: PricingConfig) -> float:
    return (inventory.items / 1000.0) * (
        pricing.s3.intelligent_tiering_monitoring_per_1000_objects
    )


def _annualize(
    monthly: tuple[CostLine, ...],
    *,
    growth_rate: float = 0.0,
) -> tuple[CostLine, ...]:
    factor = compound_annual_factor(growth_rate)
    annual_lines: list[CostLine] = []
    for line in monthly:
        annual_usd = line.usd * factor
        if not line.calculation:
            annual_lines.append(CostLine(line.label, annual_usd))
            continue
        if growth_rate > 0:
            calc = (
                f"{line.usd:.2f} USD/mo x {factor:.4f} "
                f"(growth-adjusted annual factor, {growth_rate:.0%}/yr) "
                f"= {annual_usd:.2f} USD",
            )
        else:
            calc = (f"{line.usd:.2f} USD/mo x 12 = {annual_usd:.2f} USD",)
        annual_lines.append(CostLine(line.label, annual_usd, calculation=calc))
    return tuple(annual_lines)


def calculate_s3_direct(
    traffic_monthly_requests: float,
    traffic_monthly_bytes: float,
    inventory: Inventory,
    pricing: PricingConfig,
    storage_class: str,
    *,
    scenario_name: str = "S3 direct",
    first_tier_egress_only: bool = False,
) -> ScenarioCosts:
    storage_usd = _storage_monthly_cost(inventory, pricing, storage_class)
    monthly_lines: list[CostLine] = [
        CostLine(
            "Storage",
            storage_usd,
            calculation=_storage_calculation(inventory, pricing, storage_class),
        ),
    ]
    if storage_class == "INTELLIGENT_TIERING":
        monthly_lines.append(
            CostLine(
                "Intelligent-Tiering monitoring",
                _monitoring_monthly_cost(inventory, pricing),
                calculation=_monitoring_calculation(inventory, pricing),
            )
        )

    get_usd = (traffic_monthly_requests / 1000.0) * pricing.s3.requests_per_1000["GET"]
    egress_usd = _egress_cost(
        traffic_monthly_bytes,
        pricing,
        use_cloudfront=False,
        first_tier_only=first_tier_egress_only,
    )
    monthly_lines.extend(
        [
            CostLine(
                "GET requests",
                get_usd,
                calculation=_get_requests_calculation(traffic_monthly_requests, pricing),
            ),
            CostLine(
                "Data transfer out",
                egress_usd,
                calculation=_egress_calculation(
                    traffic_monthly_bytes,
                    pricing,
                    use_cloudfront=False,
                    first_tier_only=first_tier_egress_only,
                    label="S3 data transfer out",
                ),
            ),
        ]
    )
    monthly = tuple(monthly_lines)
    return ScenarioCosts(
        name=scenario_name,
        monthly=monthly,
        annual=_annualize(monthly, growth_rate=inventory.annual_growth_rate),
    )


def calculate_cloudfront(
    traffic_monthly_requests: float,
    traffic_monthly_bytes: float,
    inventory: Inventory,
    pricing: PricingConfig,
    storage_class: str,
    *,
    cache_hit_ratio: float,
    scenario_name: str,
    first_tier_egress_only: bool = False,
) -> ScenarioCosts:
    if pricing.cloudfront is None:
        raise ValueError("CloudFront pricing is not configured")

    cache_miss_ratio = 1.0 - cache_hit_ratio
    monthly_lines: list[CostLine] = [
        CostLine(
            "Storage",
            _storage_monthly_cost(inventory, pricing, storage_class),
            calculation=_storage_calculation(inventory, pricing, storage_class),
        ),
    ]
    if storage_class == "INTELLIGENT_TIERING":
        monthly_lines.append(
            CostLine(
                "Intelligent-Tiering monitoring",
                _monitoring_monthly_cost(inventory, pricing),
                calculation=_monitoring_calculation(inventory, pricing),
            )
        )

    origin_requests = traffic_monthly_requests * cache_miss_ratio
    origin_bytes = traffic_monthly_bytes * cache_miss_ratio
    cache_note = (
        f"Cache hit ratio {cache_hit_ratio:.0%}: "
        f"origin traffic = {_fmt_qty(traffic_monthly_requests)} requests "
        f"x {cache_miss_ratio:.0%} miss = {_fmt_qty(origin_requests)} origin requests"
    )

    monthly_lines.extend(
        [
            CostLine(
                "S3 origin GET requests",
                (origin_requests / 1000.0) * pricing.s3.requests_per_1000["GET"],
                calculation=(
                    cache_note,
                    *_get_requests_calculation(
                        origin_requests,
                        pricing,
                        label="S3 origin GET requests",
                    ),
                ),
            ),
            CostLine(
                "S3 origin data transfer",
                _egress_cost(
                    origin_bytes,
                    pricing,
                    use_cloudfront=False,
                    first_tier_only=first_tier_egress_only,
                ),
                calculation=(
                    f"{_fmt_qty(traffic_monthly_bytes / BYTES_PER_GB)} GB total transfer "
                    f"x {cache_miss_ratio:.0%} cache miss = "
                    f"{_fmt_qty(origin_bytes / BYTES_PER_GB)} GB to S3 origin",
                    *_egress_calculation(
                        origin_bytes,
                        pricing,
                        use_cloudfront=False,
                        first_tier_only=first_tier_egress_only,
                        label="S3 origin data transfer",
                    ),
                ),
            ),
            CostLine(
                "CloudFront data transfer",
                _egress_cost(
                    traffic_monthly_bytes,
                    pricing,
                    use_cloudfront=True,
                    first_tier_only=first_tier_egress_only,
                ),
                calculation=_egress_calculation(
                    traffic_monthly_bytes,
                    pricing,
                    use_cloudfront=True,
                    first_tier_only=first_tier_egress_only,
                    label="CloudFront data transfer",
                ),
            ),
            CostLine(
                "CloudFront requests",
                (traffic_monthly_requests / 10_000.0)
                * pricing.cloudfront.requests_per_10000["GET"],
                calculation=_cloudfront_requests_calculation(
                    traffic_monthly_requests,
                    pricing,
                ),
            ),
        ]
    )
    monthly = tuple(monthly_lines)
    return ScenarioCosts(
        name=scenario_name,
        monthly=monthly,
        annual=_annualize(monthly, growth_rate=inventory.annual_growth_rate),
    )


def build_estimates(
    stats: TrafficStats,
    inventory: Inventory,
    pricing: PricingConfig,
    storage_class: str,
    *,
    projection_mode: str = "simple",
) -> EstimateResult:
    realistic_traffic = project_traffic(
        stats,
        mode=projection_mode,
        safety_margin=0.0,
    )
    conservative_traffic = project_traffic(
        stats,
        mode=projection_mode,
        safety_margin=DEFAULT_CONSERVATIVE_SAFETY_MARGIN,
    )

    realistic_s3 = calculate_s3_direct(
        realistic_traffic.monthly_requests,
        realistic_traffic.monthly_bytes,
        inventory,
        pricing,
        storage_class,
    )

    conservative_candidates = [
        calculate_s3_direct(
            conservative_traffic.monthly_requests,
            conservative_traffic.monthly_bytes,
            inventory,
            pricing,
            storage_class,
            scenario_name="Conservative (S3 direct)",
            first_tier_egress_only=True,
        )
    ]

    realistic_cloudfront: ScenarioCosts | None = None
    if pricing.cloudfront is not None:
        realistic_cloudfront = calculate_cloudfront(
            realistic_traffic.monthly_requests,
            realistic_traffic.monthly_bytes,
            inventory,
            pricing,
            storage_class,
            cache_hit_ratio=pricing.cloudfront.recommended_cache_hit_ratio,
            scenario_name=(
                "S3 + CloudFront "
                f"({pricing.cloudfront.recommended_cache_hit_ratio:.0%} cache hit)"
            ),
        )
        conservative_candidates.append(
            calculate_cloudfront(
                conservative_traffic.monthly_requests,
                conservative_traffic.monthly_bytes,
                inventory,
                pricing,
                storage_class,
                cache_hit_ratio=0.0,
                scenario_name="Conservative (S3 + CloudFront, 0% cache)",
                first_tier_egress_only=True,
            )
        )

    conservative = max(conservative_candidates, key=lambda item: item.annual_total)
    conservative = ScenarioCosts(
        name=f"Conservative worst case ({conservative.name})",
        monthly=conservative.monthly,
        annual=conservative.annual,
    )

    return EstimateResult(
        realistic_s3=realistic_s3,
        conservative=conservative,
        realistic_cloudfront=realistic_cloudfront,
    )


def compare_storage_classes(
    stats: TrafficStats,
    inventory: Inventory,
    pricing: PricingConfig,
    storage_classes: tuple[str, ...],
    *,
    projection_mode: str = "simple",
) -> tuple[ScenarioCosts, ...]:
    """S3 direct realistic costs per storage class (egress/GET unchanged)."""
    realistic_traffic = project_traffic(
        stats,
        mode=projection_mode,
        safety_margin=0.0,
    )
    return tuple(
        calculate_s3_direct(
            realistic_traffic.monthly_requests,
            realistic_traffic.monthly_bytes,
            inventory,
            pricing,
            storage_class,
            scenario_name=storage_class,
        )
        for storage_class in storage_classes
    )
