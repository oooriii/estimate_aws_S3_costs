from pathlib import Path

from estimate_cli import cmd_estimate, parse_growth_rate


def test_parse_growth_rate_accepts_percent():
    assert parse_growth_rate("10%") == 0.1


def test_parse_growth_rate_accepts_decimal():
    assert parse_growth_rate("0.15") == 0.15


def test_cmd_estimate_runs_on_sample_log(sample_log_file, tmp_path):
    pricing = tmp_path / "pricing.json"
    pricing.write_text(
        Path("pricing/templates/eu-south-2.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    args = type(
        "Args",
        (),
        {
            "file": sample_log_file,
            "storage_gb": 1000.0,
            "items": 10_000,
            "growth": "10%",
            "pricing": pricing,
            "storage_class": "STANDARD",
        },
    )()
    assert cmd_estimate(args) == 0
