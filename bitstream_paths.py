from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote

BITSTREAM_SHORT_RE = re.compile(
    r"^/*bitstream/(?P<repo>\d+)/(?P<item>\d+)/(?P<seq>\d+)/(?P<file>[^/]+)$",
    re.IGNORECASE,
)
BITSTREAM_HANDLE_RE = re.compile(
    r"^/*bitstream/handle/(?P<repo>\d+)/(?P<item>\d+)/(?P<file>[^/]+)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class BitstreamRef:
    canonical_path: str
    item_id: str
    filename: str
    sequence: int


def parse_bitstream_ref(raw_path: str) -> BitstreamRef | None:
    """Map DSpace bitstream URL variants to one canonical document path."""
    path_part, _, query = raw_path.partition("?")
    path_part = unquote(path_part)

    match = BITSTREAM_SHORT_RE.match(path_part)
    if match:
        repo = match.group("repo")
        item = match.group("item")
        seq = int(match.group("seq"))
        filename = match.group("file")
        return BitstreamRef(
            canonical_path=f"/bitstream/{repo}/{item}/{seq}/{filename}",
            item_id=f"{repo}/{item}",
            filename=filename,
            sequence=seq,
        )

    match = BITSTREAM_HANDLE_RE.match(path_part)
    if not match:
        return None

    repo = match.group("repo")
    item = match.group("item")
    filename = match.group("file")
    sequence = 1
    if query:
        params = parse_qs(query)
        raw_sequence = params.get("sequence", ["1"])[0]
        try:
            sequence = int(raw_sequence)
        except ValueError:
            sequence = 1

    return BitstreamRef(
        canonical_path=f"/bitstream/{repo}/{item}/{sequence}/{filename}",
        item_id=f"{repo}/{item}",
        filename=filename,
        sequence=sequence,
    )


def normalize_request_path(raw_path: str) -> str:
    """Normalize any request path for grouping (strip query, decode, collapse //)."""
    path_part = unquote(raw_path.split("?", 1)[0])
    if not path_part.startswith("/"):
        path_part = f"/{path_part}"
    while "//" in path_part:
        path_part = path_part.replace("//", "/")
    return path_part
