"""A station record in a DSS file. Interface: :func:`read_dss`, :func:`split_pathname`.

``record`` is the pathname as HEC-HMS writes it in a gage (``//STATION/PRECIP-INC//1MIN/GAGE/``) or its parts
``B/C`` or ``B/C/F``; the D part is never typed, the catalogue supplies it. With no ``record`` the file must hold a
single series of the wanted quantity: C part ``PRECIP...`` for rain, ``FLOW...`` for flow, ``STAGE`` or ``ELEV...``
for a level. The file is read through a scratch copy and is never opened for writing. Units and the data type come
back as stored: the caller converts and decides what a PER-CUM or an INST-VAL means. DSS's undefined value, the flags
-901 and -902 and NaN are missing values.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from wadi2d.hms.dss import DssFile, DssPathname, open_dss
from wadi2d.io.series import (
    DSS,
    FLOW,
    LEVEL,
    PRECIPITATION,
    SECONDS_PER_MINUTE,
    SERIES_READERS,
    StationRecord,
)

C_PARTS = {PRECIPITATION: ("PRECIP",), FLOW: ("FLOW",), LEVEL: ("STAGE", "ELEV")}
MISSING_BELOW = -900.0
UNDEFINED_ABOVE = 1.0e30
PATH_PARTS = 6


def split_pathname(record: str) -> tuple[str, str, str | None, str | None]:
    """(B, C, F, E) of a pathname or of its ``B/C`` or ``B/C/F`` parts; F and E are None when not given."""
    text = record.strip()
    if text.startswith("/"):
        parts = text[1:-1].split("/") if text.endswith("/") else []
        if len(parts) != PATH_PARTS or not parts[1] or not parts[2]:
            raise ValueError(f"{record!r} is not a DSS pathname: it needs six parts, /A/B/C/D/E/F/")
        _a, b, c, _d, e, f = parts
        return b, c, f or None, e or None
    parts = text.split("/")
    if len(parts) not in (2, 3) or not all(parts[:2]):
        raise ValueError(f"{record!r}: name a DSS record by its pathname, or by its parts B/C or B/C/F")
    return parts[0], parts[1], (parts[2] or None) if len(parts) == 3 else None, None


def _interval(e_part: str) -> str:
    """An E part as one spelling: HEC-HMS writes ``1MIN`` in a gage where a version 7 catalogue says ``1Minute``."""
    return e_part.upper().replace("MINUTE", "MIN")


def _only(dss: DssFile, want: str, path: Path) -> DssPathname:
    wanted = C_PARTS.get(want, ())
    found = [p for p in dss.catalog() if not wanted or p.c.upper().startswith(wanted)]
    if len(found) != 1:
        names = sorted(str(p) for p in found) or sorted(str(p) for p in dss.catalog())
        some = "several" if found else "no"
        raise ValueError(
            f"{path.name} holds {some} {want} series, so the record must be named; it holds: {names}"
        )
    return found[0]


def _named(dss: DssFile, record: str, path: Path) -> DssPathname:
    b, c, f, e = split_pathname(record)
    found = [
        p
        for p in dss.catalog()
        if p.b.casefold() == b.casefold()
        and p.c.casefold() == c.casefold()
        and (f is None or p.f.casefold() == f.casefold())
        and (e is None or _interval(p.e) == _interval(e))
    ]
    if len(found) != 1:
        names = sorted(str(p) for p in dss.catalog())
        raise ValueError(f"{path.name} has {len(found)} records matching {record!r}; it holds: {names}")
    return found[0]


@SERIES_READERS.register(DSS)
def read_dss(
    path: Path,
    record: str | None = None,
    time_unit: str = "min",
    time_format: str | None = None,
    want: str = PRECIPITATION,
) -> StationRecord:
    """One time series of a DSS file, with its units and its data type."""
    with open_dss(path) as dss:
        found = _named(dss, record, path) if record else _only(dss, want, path)
        series = dss.read_timeseries(found.b, found.c, found.f, e=found.e)
    values = np.asarray(series.values, dtype=np.float64).copy()
    values[~np.isfinite(values) | (values <= MISSING_BELOW) | (np.abs(values) > UNDEFINED_ABOVE)] = np.nan
    interval = series.interval_seconds / SECONDS_PER_MINUTE if series.interval_seconds > 0 else None
    return StationRecord(
        f"{path.name} {series.pathname}", values, dates=np.asarray(series.times, dtype="datetime64[s]"),
        units=series.units.strip(), kind=series.data_type.strip().upper(), interval_min=interval,
    )  # fmt: skip
