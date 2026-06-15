import json
from datetime import date
from pathlib import Path

import pytest

from pricing.loader import load_pricing_config, save_pricing_config
from pricing.schema import (
    CloudFrontPricing,
    DisplayConfig,
    PriceTier,
    PricingConfig,
    S3Pricing,
    parse_pricing_config,
)
from pricing_cli import cmd_pricing_show, cmd_pricing_validate


@pytest.fixture
def valid_pricing_file(tmp_path) -> Path:
    config = PricingConfig(
        effective_date=date(2026, 6, 15),
        region="eu-south-2",
        currency="USD",
        display=DisplayConfig(
            show_eur=True,
            usd_eur_rate=0.95,
            rate_note="test",
        ),
        sources={"s3": "https://aws.amazon.com/s3/pricing/"},
        s3=S3Pricing(
            storage_per_gb_month={
                "STANDARD": 0.0255,
                "STANDARD_IA": 0.014,
                "INTELLIGENT_TIERING": 0.0255,
                "GLACIER_INSTANT": 0.0045,
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
            requests_per_10000={"GET": 0.0075},
            recommended_cache_hit_ratio=0.85,
        ),
    )
    target = tmp_path / "pricing.json"
    save_pricing_config(target, config)
    return target


def test_pricing_validate_accepts_valid_file(valid_pricing_file):
    args = type("Args", (), {"file": valid_pricing_file})()
    assert cmd_pricing_validate(args) == 0


def test_pricing_show_accepts_valid_file(valid_pricing_file):
    args = type("Args", (), {"file": valid_pricing_file})()
    assert cmd_pricing_show(args) == 0


def test_pricing_validate_rejects_missing_file(tmp_path):
    missing = tmp_path / "missing.json"
    args = type("Args", (), {"file": missing})()
    assert cmd_pricing_validate(args) == 1


def test_build_config_dict_matches_schema(valid_pricing_file):
    raw = json.loads(valid_pricing_file.read_text(encoding="utf-8"))
    config = parse_pricing_config(raw)
    assert config.region == "eu-south-2"
    assert load_pricing_config(valid_pricing_file)[0].region == "eu-south-2"
