import pytest

from cost_model import Inventory, calculate_s3_direct
from estimate_report import scenario_calculation_lines
from pricing.schema import (
    CloudFrontPricing,
    DisplayConfig,
    PriceTier,
    PricingConfig,
    S3Pricing,
)
from pricing.tiers import tiered_cost_breakdown


@pytest.fixture
def pricing_config() -> PricingConfig:
    return PricingConfig(
        effective_date=__import__("datetime").date(2026, 6, 15),
        region="eu-south-2",
        currency="USD",
        display=DisplayConfig(
            show_eur=True,
            usd_eur_rate=0.92,
            rate_note="test",
        ),
        sources={},
        s3=S3Pricing(
            storage_per_gb_month={
                "STANDARD": 0.023,
                "STANDARD_IA": 0.0125,
                "INTELLIGENT_TIERING": 0.023,
                "GLACIER_INSTANT": 0.005,
            },
            intelligent_tiering_monitoring_per_1000_objects=0.0025,
            requests_per_1000={"GET": 0.0004, "PUT": 0.005, "LIST": 0.005},
            data_transfer_out_per_gb=(
                PriceTier(up_to_gb=10240, price=0.09),
                PriceTier(up_to_gb=None, price=0.085),
            ),
        ),
        cloudfront=CloudFrontPricing(
            data_transfer_out_per_gb=(
                PriceTier(up_to_gb=10240, price=0.085),
                PriceTier(up_to_gb=None, price=0.08),
            ),
            requests_per_10000={"GET": 0.012},
            recommended_cache_hit_ratio=0.85,
        ),
    )


def test_tiered_cost_breakdown_splits_tiers():
    tiers = (
        PriceTier(up_to_gb=100, price=0.09),
        PriceTier(up_to_gb=None, price=0.085),
    )
    slices = tiered_cost_breakdown(150, tiers)

    assert len(slices) == 2
    assert slices[0].gb == 100
    assert slices[0].subtotal_usd == pytest.approx(9.0)
    assert slices[1].gb == 50
    assert slices[1].subtotal_usd == pytest.approx(4.25)


def test_s3_direct_includes_storage_calculation(pricing_config):
    scenario = calculate_s3_direct(
        traffic_monthly_requests=110_227,
        traffic_monthly_bytes=157.32 * 1024**3,
        inventory=Inventory(storage_gb=202, items=26_768),
        pricing=pricing_config,
        storage_class="STANDARD",
    )
    storage = scenario.monthly[0]

    assert storage.calculation
    assert "202 GB x 0.023 USD/GB-mo" in storage.calculation[0]
    assert "STANDARD storage" in storage.calculation[0]


def test_intelligent_tiering_includes_monitoring_calculation(pricing_config):
    scenario = calculate_s3_direct(
        traffic_monthly_requests=10_000,
        traffic_monthly_bytes=100 * 1024**3,
        inventory=Inventory(storage_gb=100, items=10_000),
        pricing=pricing_config,
        storage_class="INTELLIGENT_TIERING",
    )
    monitoring = next(
        line for line in scenario.monthly if line.label == "Intelligent-Tiering monitoring"
    )

    assert monitoring.calculation
    assert "10,000 objects / 1,000 x 0.0025 USD" in monitoring.calculation[0]


def test_scenario_calculation_lines_include_total(pricing_config):
    scenario = calculate_s3_direct(
        traffic_monthly_requests=1_000,
        traffic_monthly_bytes=10 * 1024**3,
        inventory=Inventory(storage_gb=50, items=1_000),
        pricing=pricing_config,
        storage_class="STANDARD",
    )
    lines = scenario_calculation_lines(scenario, period="monthly")

    assert any("total monthly" in line for line in lines)
    assert any("GET requests" in line for line in lines)
