from pathlib import Path

from demand_cli import cmd_demand


def test_cmd_demand_runs_on_sample_log(sample_log_file, tmp_path):
    args = type(
        "Args",
        (),
        {
            "file": sample_log_file,
            "top": 10,
            "all_paths": False,
            "output_dir": tmp_path / "reports",
            "pdf": None,
            "no_pdf": True,
            "csv": None,
            "no_csv": True,
        },
    )()
    assert cmd_demand(args) == 0


def test_cmd_demand_writes_exports(sample_log_file, tmp_path):
    args = type(
        "Args",
        (),
        {
            "file": sample_log_file,
            "top": 5,
            "all_paths": False,
            "output_dir": tmp_path / "reports",
            "pdf": tmp_path / "reports" / "demand.pdf",
            "no_pdf": False,
            "csv": tmp_path / "reports" / "demand.csv",
            "no_csv": False,
        },
    )()
    assert cmd_demand(args) == 0
    assert Path(tmp_path / "reports" / "demand.pdf").is_file()
    assert Path(tmp_path / "reports" / "demand.csv").is_file()
