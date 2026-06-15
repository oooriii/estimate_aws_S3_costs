from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from parser import LogLine
from static_demand import parse_static_demand
from static_paths import classify_static_path


def _log_line(path: str, bytes_sent: int, *, ip: str = "1.2.3.4") -> str:
    return (
        f'/var/log/apache2/access_ssl.log:{ip} - - '
        f'[01/Jun/2026:10:00:00 +0200] "GET {path} HTTP/1.1" '
        f'200 {bytes_sent} "-" "Mozilla/5.0"'
    )


@pytest.mark.parametrize(
    ("raw_path", "category"),
    [
        ("/static/css/main.css", "theme"),
        ("/bitstream/handle/10256.2/123/cover.jpg?sequence=1", "bitstream_image"),
        ("/favicon.ico", "theme"),
    ],
)
def test_classify_static_path(raw_path: str, category: str) -> None:
    _path, result = classify_static_path(raw_path)
    assert result == category


def test_parse_static_demand_aggregates_paths_and_days(tmp_path: Path) -> None:
    log_file = tmp_path / "static.log"
    log_file.write_text(
        "\n".join(
            [
                _log_line("/static/css/main.css", 1000),
                _log_line("/static/css/main.css", 1000),
                _log_line(
                    "/bitstream/handle/10256.2/42/cover.jpg?sequence=1",
                    5000,
                ),
                _log_line("/fonts/open-sans.woff2", 2000, ip="5.6.7.8"),
                _log_line(
                    "/static/css/main.css",
                    1000,
                    ip="9.9.9.9",
                ),
            ]
        ),
        encoding="utf-8",
    )

    result = parse_static_demand(log_file)

    assert result.stats.total_records == 5
    assert result.stats.total_bytes == 10_000
    assert len(result.paths) == 3
    assert result.repeat_records == 2
    assert result.projection.monthly_requests > 0
    assert len(result.daily) == 1
    assert result.daily[0].records == 5

    theme = next(item for item in result.categories if item.category == "theme")
    assert theme.records == 4
    assert theme.unique_paths == 2

    top = result.paths[0]
    assert top.path.endswith("cover.jpg")
    assert top.bytes == 5000


def test_parse_static_demand_streams_large_file_without_loading_whole_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log_file = tmp_path / "large-static.log"
    with log_file.open("w", encoding="utf-8") as handle:
        for index in range(1000):
            handle.write(_log_line(f"/static/img/icon-{index % 5}.png", 100))
            handle.write("\n")

    seen: list[LogLine] = []

    def fake_iter(file_path: Path):
        from parser import iter_log_lines

        for line in iter_log_lines(file_path):
            seen.append(line)
            yield line

    monkeypatch.setattr("static_demand.iter_log_lines", fake_iter)
    result = parse_static_demand(log_file)

    assert len(seen) == 1000
    assert result.stats.total_records == 1000
    assert len(result.paths) == 5
