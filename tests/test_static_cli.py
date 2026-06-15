from pathlib import Path

from static_cli import cmd_static


def test_cmd_static_runs_on_sample_log(tmp_path: Path) -> None:
    log_file = tmp_path / "static.log"
    log_file.write_text(
        '/var/log/apache2/access_ssl.log:1.2.3.4 - - '
        '[01/Jun/2026:10:00:00 +0200] "GET /static/css/main.css HTTP/1.1" '
        '200 1000 "-" "Mozilla/5.0"\n',
        encoding="utf-8",
    )
    args = type(
        "Args",
        (),
        {
            "file": log_file,
            "top": 10,
            "projection_mode": "simple",
            "output_dir": tmp_path / "reports",
            "csv": None,
            "csv_daily": None,
            "csv_summary": None,
            "no_csv": True,
        },
    )()
    assert cmd_static(args) == 0


def test_cmd_static_writes_exports(tmp_path: Path) -> None:
    log_file = tmp_path / "static.log"
    log_file.write_text(
        '/var/log/apache2/access_ssl.log:1.2.3.4 - - '
        '[01/Jun/2026:10:00:00 +0200] "GET /static/css/main.css HTTP/1.1" '
        '200 1000 "-" "Mozilla/5.0"\n',
        encoding="utf-8",
    )
    output_dir = tmp_path / "reports"
    args = type(
        "Args",
        (),
        {
            "file": log_file,
            "top": 5,
            "projection_mode": "simple",
            "output_dir": output_dir,
            "csv": output_dir / "files.csv",
            "csv_daily": output_dir / "daily.csv",
            "csv_summary": output_dir / "summary.csv",
            "no_csv": False,
        },
    )()
    assert cmd_static(args) == 0
    assert (output_dir / "files.csv").is_file()
    assert (output_dir / "daily.csv").is_file()
    assert (output_dir / "summary.csv").is_file()
