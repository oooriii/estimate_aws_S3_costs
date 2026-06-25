
from parsers.access import parse_access_line
from parsers.detect import parse_log_line
from parsers.error import parse_error_line

ACCESS_LINE = (
    "203.0.113.10 - - [15/Jun/2026:06:26:23 +0200] "
    '"GET /bitstream/handle/10256/23347/document.pdf HTTP/1.1" '
    '200 11555603 "-" "Mozilla/5.0 (compatible; Googlebot/2.1)"'
)

ACCESS_LINE_PREFIXED = (
    "/var/log/apache2/access_ssl.log:203.0.113.10 - - [15/Jun/2026:06:26:23 +0200] "
    '"GET /favicon.ico HTTP/1.1" 404 512 "-" "curl/8.0"'
)

ERROR_LINE = (
    "[Wed Jun 15 06:26:23.123456 2026] [error] [client 203.0.113.55:54321] "
    "File does not exist: /var/www/html/missing"
)

ERROR_LINE_SSL = (
    "[Wed Jun 15 06:26:24.000000 2026] [ssl:error] [pid 12345] "
    "[client 198.51.100.20:44321] AH01630: request failed"
)


def test_parse_access_line_without_prefix():
    event = parse_access_line(ACCESS_LINE)
    assert event is not None
    assert event.kind == "access"
    assert event.remote_host == "203.0.113.10"
    assert event.status == 200
    assert event.path.endswith("document.pdf")
    assert "Googlebot" in (event.user_agent or "")


def test_parse_access_line_with_log_prefix():
    event = parse_access_line(ACCESS_LINE_PREFIXED)
    assert event is not None
    assert event.source.endswith("access_ssl.log")
    assert event.remote_host == "203.0.113.10"
    assert event.status == 404


def test_parse_error_line_with_client():
    event = parse_error_line(ERROR_LINE, default_source="error_ssl.log")
    assert event is not None
    assert event.kind == "error"
    assert event.remote_host == "203.0.113.55"
    assert event.user_agent is None
    assert "File does not exist" in (event.message or "")


def test_parse_error_line_ssl_variant():
    event = parse_error_line(ERROR_LINE_SSL)
    assert event is not None
    assert event.remote_host == "198.51.100.20"


def test_parse_log_line_auto_detects_access():
    event = parse_log_line(ACCESS_LINE)
    assert event is not None
    assert event.kind == "access"


def test_parse_log_line_auto_detects_error():
    event = parse_log_line(ERROR_LINE)
    assert event is not None
    assert event.kind == "error"


def test_parse_log_line_returns_none_for_garbage():
    assert parse_log_line("not a log line") is None


def test_iter_events_from_multitail_extract(tmp_path):
    from source import iter_events_from_file

    log_file = tmp_path / "multitail.log"
    log_file.write_text(
        "\n".join(
            [
                "==> /var/log/apache2/anubis_error.log <==",
                "[Thu Jun 25 13:25:06.086004 2026] [proxy:error] "
                "[pid 9059] [client 17.246.15.142:44990] timeout",
                "==> /var/log/apache2/anubis_access.log <==",
                '17.246.15.142 - - [25/Jun/2026:13:26:08 +0200] '
                '"GET /browse HTTP/1.1" 200 100 "-" "Applebot/0.1"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    events = list(iter_events_from_file(log_file))
    assert len(events) == 2
    assert events[0].kind == "error"
    assert events[0].source.endswith("anubis_error.log")
    assert events[0].remote_host == "17.246.15.142"
    assert events[1].kind == "access"
    assert events[1].source.endswith("anubis_access.log")


def test_normalize_timestamp_strips_timezone_for_comparison():
    from datetime import UTC, datetime

    from events import normalize_timestamp

    aware = datetime(2026, 6, 25, 13, 26, 8, tzinfo=UTC)
    naive = datetime(2026, 6, 25, 13, 25, 6)
    assert normalize_timestamp(aware) == datetime(2026, 6, 25, 13, 26, 8)
    assert normalize_timestamp(naive) == naive

