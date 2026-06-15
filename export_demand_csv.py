from __future__ import annotations

import csv
from pathlib import Path

from demand import FileDemand


def write_top_files_csv(
    path: Path,
    files: tuple[FileDemand, ...],
    *,
    total_records: int,
    total_bytes: int,
    limit: int | None = None,
) -> int:
    rows = files if limit is None else files[:limit]
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "rank",
                "path",
                "item_id",
                "filename",
                "records",
                "records_pct",
                "bytes",
                "bytes_pct",
                "unique_ips",
                "bot_records",
                "human_records",
            ]
        )
        for rank, item in enumerate(rows, start=1):
            records_pct = (
                100.0 * item.records / total_records if total_records > 0 else 0.0
            )
            bytes_pct = 100.0 * item.bytes / total_bytes if total_bytes > 0 else 0.0
            writer.writerow(
                [
                    rank,
                    item.path,
                    item.item_id or "",
                    item.filename or "",
                    item.records,
                    f"{records_pct:.2f}",
                    item.bytes,
                    f"{bytes_pct:.2f}",
                    item.unique_ips,
                    item.bot_records,
                    item.human_records,
                ]
            )

    return len(rows)
