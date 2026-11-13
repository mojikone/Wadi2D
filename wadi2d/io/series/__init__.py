"""Station records, a rain gauge's or a flow gauge's, as :class:`StationRecord`. Interface: :func:`read_record`,
:func:`series_format`, :data:`SERIES_READERS`.

A format is one new file holding a reader registered in :data:`SERIES_READERS`; nothing else knows it exists. A record
is what the file holds and no more: values with NaN where the file has none, and times either as dates or as a count
from the start of the run. What the values mean (depth in a period, a flow at an instant) is the caller's to decide,
helped by ``kind`` where the file says it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from wadi2d.storm.registry import Registry

CSV, DSS = "csv", "dss"
DSS_SUFFIX = ".dss"
CSV_SUFFIXES = (".csv", ".txt", ".tsv", ".dat")
SECONDS_PER_MINUTE = 60.0
MINUTES_PER = {"s": 1.0 / SECONDS_PER_MINUTE, "min": 1.0, "h": 60.0, "d": 1440.0}
PRECIPITATION, FLOW, LEVEL = "precipitation", "flow", "level"
"""What a caller is looking for, when a file holds more than one series."""
PERIOD_TOTAL, CUMULATIVE, INSTANT, PERIOD_MEAN = "PER-CUM", "INST-CUM", "INST-VAL", "PER-AVER"
"""The DSS data types, used as the kinds of any record: a depth in a period, a depth since the start, a value at an
instant, a mean over a period."""


@dataclass(frozen=True)
class StationRecord:
    """One series as stored. Exactly one of ``dates`` and ``minutes`` is set."""

    source: str
    values: np.ndarray
    dates: np.ndarray | None = None
    """``datetime64[s]``, for a file with dates."""
    minutes: np.ndarray | None = None
    """Minutes from the start of the run, for a file that counts from it."""
    units: str = ""
    kind: str = ""
    """One of the DSS data types, or empty when the file does not say."""
    interval_min: float | None = None
    """The period of a regular record that states one."""

    def __post_init__(self) -> None:
        times = self.dates if self.dates is not None else self.minutes
        if (self.dates is None) == (self.minutes is None) or times.size != self.values.size:
            raise ValueError(f"{self.source}: a record needs one time per value, as dates or as minutes")
        if times.size == 0:
            raise ValueError(f"{self.source}: the record is empty")
        steps = np.diff(times.astype("int64") if self.dates is not None else times)
        if np.any(steps <= 0):
            at = int(np.argmax(steps <= 0)) + 1
            raise ValueError(
                f"{self.source}: times must rise, and value {at + 1} ({times[at]}) does not come after the one before"
            )

    @property
    def dated(self) -> bool:
        return self.dates is not None

    def minutes_from(self, origin: np.datetime64 | None) -> np.ndarray:
        """The times as minutes from the start of the run; a record with dates needs the date of that start."""
        if self.minutes is not None:
            return self.minutes
        if origin is None:
            raise ValueError(f"{self.source}: the record has dates, so the date and time the run starts at is needed")
        return (self.dates - origin) / np.timedelta64(1, "s") / SECONDS_PER_MINUTE


SERIES_READERS: Registry[StationRecord] = Registry("station record")
"""Readers by format: ``reader(path=..., record=..., time_unit=..., time_format=..., want=...)``."""


def series_format(path: str | Path) -> str:
    """The format of a station record, from its file name."""
    suffix = Path(path).suffix.lower()
    if suffix == DSS_SUFFIX:
        return DSS
    if suffix in CSV_SUFFIXES:
        return CSV
    raise ValueError(f"{Path(path).name}: a station record comes as a CSV table (.csv, .txt) or a DSS file")


def read_record(
    path: str | Path,
    record: str | None = None,
    time_unit: str = "min",
    time_format: str | None = None,
    want: str = PRECIPITATION,
) -> StationRecord:
    """One series of a file; ``record`` picks it where the file holds several."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"station record not found: {source}")
    return SERIES_READERS.build(
        series_format(source), path=source, record=record, time_unit=time_unit, time_format=time_format, want=want
    )


from wadi2d.io.series import csv_table, dss_record  # noqa: E402  registers the formats

__all__ = [
    "CSV",
    "CUMULATIVE",
    "DSS",
    "FLOW",
    "INSTANT",
    "LEVEL",
    "MINUTES_PER",
    "PERIOD_MEAN",
    "PERIOD_TOTAL",
    "PRECIPITATION",
    "SERIES_READERS",
    "StationRecord",
    "csv_table",
    "dss_record",
    "read_record",
    "series_format",
]
