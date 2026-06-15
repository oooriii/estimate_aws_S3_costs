from pathlib import Path

import pytest

from static_paths import (
    DSPACE_STATIC_PATH_VERSION,
    classify_static_path,
    file_extension,
    static_path_version_note,
)


def test_static_path_version_note_mentions_dspace_5() -> None:
    assert DSPACE_STATIC_PATH_VERSION == "5.x"
    assert "5.x" in static_path_version_note()
    assert "7.x" in static_path_version_note()


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/static/css/main.css", "css"),
        ("/bitstream/10256.2/1/1/cover.JPG", "jpg"),
        ("/favicon.ico", "ico"),
        ("/static/README", ""),
    ],
)
def test_file_extension(path: str, expected: str) -> None:
    assert file_extension(path) == expected


def test_bitstream_handle_image_normalizes_path() -> None:
    path, category = classify_static_path(
        "/bitstream/handle/10256.2/42/cover.jpg?sequence=2"
    )
    assert category == "bitstream_image"
    assert path == "/bitstream/10256.2/42/2/cover.jpg"
