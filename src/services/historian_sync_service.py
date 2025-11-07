"""Utilities to export historian data to external BI tools."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional
import csv

from src.app.extensions import db
from src.models.Data import DataLog


@dataclass
class HistorianExportResult:
    """Metadata returned after a historian export operation."""

    file_path: Path
    rows: int
    started_at: datetime
    finished_at: datetime


class HistorianSyncService:
    """Exports historian snapshots compatible with Power BI or similar tools."""

    def __init__(self, output_dir: str | Path = "exports/power_bi", session=None):
        self.output_dir = Path(output_dir)
        self.session = session or db.session

    def _ensure_output_dir(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _query_logs(
        self,
        *,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> Iterable[DataLog]:
        query = self.session.query(DataLog)
        if start:
            query = query.filter(DataLog.timestamp >= start)
        if end:
            query = query.filter(DataLog.timestamp <= end)
        return query.order_by(DataLog.timestamp.asc())

    def export_snapshot(
        self,
        *,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> HistorianExportResult:
        """Export a CSV snapshot with historian data."""

        self._ensure_output_dir()
        started_at = datetime.now(timezone.utc)
        filename = f"historian_{started_at.strftime('%Y%m%dT%H%M%SZ')}.csv"
        file_path = self.output_dir / filename

        count = 0
        with file_path.open("w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(
                [
                    "timestamp",
                    "plc_id",
                    "register_id",
                    "value_float",
                    "value_int",
                    "raw_value",
                    "quality",
                    "unit",
                    "is_alarm",
                ]
            )
            for log in self._query_logs(start=start, end=end):
                writer.writerow(
                    [
                        log.timestamp.isoformat() if log.timestamp else None,
                        log.plc_id,
                        log.register_id,
                        log.value_float,
                        log.value_int,
                        log.raw_value,
                        log.quality,
                        log.unit,
                        bool(log.is_alarm),
                    ]
                )
                count += 1

        finished_at = datetime.now(timezone.utc)
        return HistorianExportResult(
            file_path=file_path,
            rows=count,
            started_at=started_at,
            finished_at=finished_at,
        )


__all__ = ["HistorianSyncService", "HistorianExportResult"]
