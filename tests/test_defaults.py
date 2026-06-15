from defaults import (
    DEFAULT_REPORT_CSV_NAME,
    DEFAULT_REPORT_PDF_NAME,
    default_report_paths,
    discover_geoip_db,
)
from report_cli import resolve_report_outputs


def test_default_report_paths(tmp_path):
    pdf_path, csv_path = default_report_paths(output_dir=tmp_path / "reports")
    assert pdf_path == tmp_path / "reports" / DEFAULT_REPORT_PDF_NAME
    assert csv_path == tmp_path / "reports" / DEFAULT_REPORT_CSV_NAME


def test_resolve_report_outputs_uses_defaults(tmp_path):
    log_file = tmp_path / "sample.log"
    log_file.write_text("", encoding="utf-8")
    args = type(
        "Args",
        (),
        {
            "file": log_file,
            "output_dir": tmp_path / "out",
            "pdf": None,
            "csv_ips": None,
            "no_csv_ips": False,
        },
    )()
    pdf_path, csv_path = resolve_report_outputs(args)
    assert pdf_path == tmp_path / "out" / DEFAULT_REPORT_PDF_NAME
    assert csv_path == tmp_path / "out" / DEFAULT_REPORT_CSV_NAME


def test_discover_geoip_db_finds_single_match(tmp_path):
    db_dir = tmp_path / "GeoLite2-Country_20260612"
    db_dir.mkdir()
    db_file = db_dir / "GeoLite2-Country.mmdb"
    db_file.write_bytes(b"test")
    assert discover_geoip_db(tmp_path) == db_file
