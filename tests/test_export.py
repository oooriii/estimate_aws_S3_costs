import csv
from pathlib import Path

from abuse import IpTraffic
from export_csv import filter_problematic_ips, write_problematic_ips_csv
from pdf_report import EstimatePdfContext, _format_money_pdf, write_analyze_pdf, write_combined_pdf


def _ip(remote_host: str, records: int, size: int) -> IpTraffic:
    return IpTraffic(
        remote_host=remote_host,
        country_code="US",
        country_name="United States",
        records=records,
        bytes=size,
        user_agent_count=1,
        top_user_agent="TestBot/1.0",
    )


def test_filter_problematic_ips_prefers_abusive_rows():
    ips = (
        _ip("1.1.1.1", 100, 9000),
        _ip("8.8.8.8", 1, 100),
    )
    filtered = filter_problematic_ips(
        ips,
        total_records=101,
        total_bytes=9100,
        min_bytes_pct=5.0,
    )
    assert [item.remote_host for item in filtered] == ["1.1.1.1"]


def test_write_problematic_ips_csv(tmp_path):
    ips = (
        _ip("1.1.1.1", 100, 9000),
        _ip("8.8.8.8", 1, 100),
    )
    target = tmp_path / "ips.csv"
    row_count = write_problematic_ips_csv(
        target,
        ips,
        total_records=101,
        total_bytes=9100,
        min_bytes_pct=5.0,
    )

    assert row_count == 1
    with target.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["ip"] == "1.1.1.1"
    assert rows[0]["abusive"] == "yes"
    assert rows[0]["country_code"] == "US"


def test_format_money_pdf_includes_eur():
    assert _format_money_pdf(18.85, 0.92) == "USD 18.85 (EUR 17.34)"


def test_write_analyze_pdf_creates_pdf(tmp_path, sample_log_file):
    from abuse import parse_log

    result = parse_log(sample_log_file)
    target = tmp_path / "analyze.pdf"
    write_analyze_pdf(target, log_file=sample_log_file, result=result)
    assert target.is_file()
    assert target.read_bytes().startswith(b"%PDF")


def test_write_combined_pdf_creates_pdf(tmp_path, sample_log_file):
    from abuse import parse_log
    from cost_model import Inventory, build_estimates
    from pricing.loader import load_pricing_config
    from projection import project_traffic

    pricing, warnings = load_pricing_config(
        Path("pricing/templates/eu-south-2.json")
    )
    result = parse_log(sample_log_file)
    inventory = Inventory(storage_gb=100, items=1000)
    traffic = project_traffic(result.stats)
    estimate = build_estimates(
        result.stats,
        inventory,
        pricing,
        "STANDARD",
    )
    target = tmp_path / "combined.pdf"
    write_combined_pdf(
        target,
        log_file=sample_log_file,
        result=result,
        estimate=EstimatePdfContext(
            pricing=pricing,
            traffic=traffic,
            result=estimate,
            selected_storage_class="STANDARD",
            growth_rate=0.1,
            forecast_years=2,
            pricing_warnings=tuple(warnings),
        ),
    )
    assert target.is_file()
    assert target.stat().st_size > 1000
