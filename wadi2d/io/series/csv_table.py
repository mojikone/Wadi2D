"""A station record as a text table. Interface: :func:`read_csv`, :func:`parse_date`.

Accepted layout, stated once here and in ``W54 rain and flow gauges/README.md``:

* cells separated by commas, semicolons or tabs; lines starting with ``#`` and empty lines are left out;
* an optional heading line, which is any first line whose time cell is not a time;
* the first column is the time: a number counted from the start of the run in the job's ``time_unit``, or a date and
  time, year first (``2021-10-04 00:05``, ``2021-10-04T00:05:00``, ``2021/10/04 00:05``) or as HEC writes it
  (``04Oct2021 00:05``, ``04Oct2021, 2400``, ``4 October 2021, 00:05``); any other spelling needs the job's
  ``time_format`` (``%d/%m/%Y %H:%M``), because 04/10/2021 is two different days in two countries;
* a date in the first column and a time of day in the second are read as one time;
* the value is the column named by ``record`` in the heading, else the first column after the time;
* an empty cell, a word, ``nan`` or a value at or below -900 (the DSS flags -901 and -902) is a missing value.

Dates carry no time zone: they are the clock of whoever wrote the file.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from wadi2d.io.series import CSV, MINUTES_PER, SERIES_READERS, StationRecord

COMMENT = "#"
DELIMITERS = (",", ";", "\t")
SNIFFED_LINES = 20
MISSING_BELOW = -900.0
ENCODINGS = ("utf-8-sig", "latin-1")
ISO = re.compile(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?:[T ,]+(\d{1,2}):?(\d{2})(?::?(\d{2})(?:\.\d+)?)?)?$")
HEC = re.compile(r"^(\d{1,2})\s*([A-Za-z]{3,9})\s*(\d{4})(?:[ ,]+(\d{1,2}):?(\d{2})(?::?(\d{2}))?)?$")
CLOCK = re.compile(r"^(\d{1,2}):?(\d{2})(?::?(\d{2}))?$")
MONTH_NAMES = (
    ("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"), ("may",), ("jun", "june"),
    ("jul", "july"), ("aug", "august"), ("sep", "sept", "september"), ("oct", "october"), ("nov", "november"),
    ("dec", "december"),
)  # fmt: skip
MONTHS = {name: number for number, names in enumerate(MONTH_NAMES, start=1) for name in names}
END_OF_DAY = 24


def _moment(year: int, month: int, day: int, hour: str | None, minute: str | None, second: str | None) -> datetime:
    """A date with a time of day; 24:00 closes its own day, as HEC writes midnight."""
    hours = int(hour or 0)
    if hours > END_OF_DAY or (hours == END_OF_DAY and (int(minute or 0) or int(second or 0))):
        raise ValueError("no such time of day")
    return datetime(year, month, day) + timedelta(hours=hours, minutes=int(minute or 0), seconds=int(second or 0))


def parse_date(text: str, time_format: str | None = None) -> datetime | None:
    """A date and time, or None when the text is not one."""
    cell = text.strip().strip('"')
    try:
        if time_format is not None:
            return datetime.strptime(cell, time_format)  # noqa: DTZ007  a station clock has no zone
        found = ISO.match(cell)
        if found:
            year, month, day, *rest = found.groups()
            return _moment(int(year), int(month), int(day), *rest)
        found = HEC.match(cell)
        if found and found.group(2).lower() in MONTHS:
            day, month, year, *rest = found.groups()
            return _moment(int(year), MONTHS[month.lower()], int(day), *rest)
    except ValueError:
        return None
    return None


def _is_number(text: str) -> bool:
    try:
        float(text.strip().strip('"'))
    except ValueError:
        return False
    return True


def _value(text: str) -> float:
    if not _is_number(text):
        return float("nan")
    value = float(text.strip().strip('"'))
    return float("nan") if value <= MISSING_BELOW else value


def _rows(path: Path) -> list[list[str]]:
    text = ""
    for encoding in ENCODINGS:
        try:
            text = path.read_text(encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
    lines = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith(COMMENT)]
    if not lines:
        raise ValueError(f"{path.name}: the file holds no rows")
    counts = {mark: sum(line.count(mark) for line in lines[:SNIFFED_LINES]) for mark in DELIMITERS}
    mark = max(counts, key=lambda m: counts[m])
    if counts[mark] == 0:
        raise ValueError(
            f"{path.name}: one column only; a station record needs a time and a value, separated by commas, "
            "semicolons or tabs"
        )
    return [[cell.strip() for cell in line.split(mark)] for line in lines]


def _is_time(cell: str, time_format: str | None) -> bool:
    if time_format is None and _is_number(cell):
        return True
    return parse_date(cell, time_format) is not None


def _value_column(heading: list[str] | None, record: str | None, first_value: int, path: Path) -> int:
    if record is None:
        return first_value
    names = [cell.strip().strip('"') for cell in heading or []]
    matches = [n for n, name in enumerate(names) if name.casefold() == record.casefold()]
    if len(matches) != 1:
        raise ValueError(f"{path.name}: no single column headed {record!r}; the headings are {names}")
    return matches[0]


@SERIES_READERS.register(CSV)
def read_csv(
    path: Path, record: str | None = None, time_unit: str = "min", time_format: str | None = None, want: str = ""
) -> StationRecord:
    """The record of one value column of a text table; see the module's note for the layout."""
    rows = _rows(path)
    heading = None if _is_time(rows[0][0], time_format) else rows.pop(0)
    if not rows:
        raise ValueError(f"{path.name}: a heading and no rows")
    first = rows[0]
    dated = time_format is not None or not _is_number(first[0])
    split = dated and len(first) > 2 and CLOCK.match(first[1].strip('"')) is not None and parse_date(first[0]) is not None
    column = _value_column(heading, record, 2 if split else 1, path)
    times: list = []
    values = []
    for number, row in enumerate(rows, start=2 if heading else 1):
        if len(row) <= column:
            raise ValueError(f"{path.name}: row {number} has no value column")
        cell = f"{row[0]} {row[1]}" if split else row[0]
        if dated:
            moment = parse_date(cell, None if split else time_format)
            if moment is None:
                hint = "" if time_format else "; write dates year first, or give time_format"
                raise ValueError(f"{path.name}: row {number}: {cell!r} is not a date and time{hint}")
            times.append(moment)
        elif _is_number(cell):
            times.append(float(cell))
        else:
            raise ValueError(f"{path.name}: row {number}: {cell!r} is not a time; the rows above count from the run's start")
        values.append(_value(row[column]))
    data = np.asarray(values, dtype=np.float64)
    source = path.name if record is None else f"{path.name} [{record}]"
    if dated:
        return StationRecord(source, data, dates=np.array(times, dtype="datetime64[s]"))
    return StationRecord(source, data, minutes=np.asarray(times, dtype=np.float64) * MINUTES_PER[time_unit])
