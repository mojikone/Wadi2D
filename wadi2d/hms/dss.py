"""DSS access: a thin, safe wrapper over ``hecdss``.

Interface: :func:`open_dss`, :class:`DssFile`, :class:`TimeSeries`, :class:`PairedTable`, :class:`GridRecord`,
:class:`DssPathname` and the F-part helpers :func:`run_fpart`, :func:`daa_fpart`, :func:`met_fpart`.

``hecdss`` creates a file that does not exist and has no read-only mode, so :func:`open_dss` refuses a
missing path and, when ``readonly`` (the default), works on a temporary copy deleted on close. The original
is only ever read by the copy. Series are resolved by (B, C, F) from the condensed catalogue, never by
typing a D part.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from types import TracebackType
from typing import Any, Self

import numpy as np

SCRATCH_PREFIX = "wadi2d_dss_"
RUN_PREFIX = "RUN"
DAA_PREFIX = "DAA"
MET_PREFIX = "MET"
POINT_SEPARATOR = ">"
PERIOD_TYPE_PREFIX = "PER"  # PER-CUM, PER-AVER: the stamp closes the period it describes
NATIVE_DEBUG_LEVEL = 1
GRID_SRS_CHARACTERS = 8192
"""``hecdss`` asks for 600 unless told, and PSD93 / UTM zone 40N takes 616."""

_native_configured = False


def run_fpart(name: str) -> str:
    """The F part of a simulation run: ``RUN:name``."""
    return f"{RUN_PREFIX}:{name}"


def daa_fpart(analysis: str, point: str) -> str:
    """The F part of a depth-area analysis at a point: ``DAA:name>point``."""
    return f"{DAA_PREFIX}:{analysis}{POINT_SEPARATOR}{point}"


def met_fpart(met: str, point: str) -> str:
    """The F part of a met model at an analysis point: ``MET:name>point``."""
    return f"{MET_PREFIX}:{met}{POINT_SEPARATOR}{point}"


@dataclass(frozen=True)
class DssPathname:
    """A catalogue pathname; ``d`` is condensed (``31Dec1999-02Jan2000``) for a time series."""

    a: str
    b: str
    c: str
    d: str
    e: str
    f: str

    def __str__(self) -> str:
        return f"/{self.a}/{self.b}/{self.c}/{self.d}/{self.e}/{self.f}/"


@dataclass(frozen=True)
class TimeSeries:
    """A regular or irregular series as stored: ``times`` are DSS stamps, ``data_type`` the DSS type."""

    pathname: DssPathname
    values: np.ndarray
    times: np.ndarray
    units: str
    data_type: str
    interval_seconds: int

    def period_start_times(self) -> np.ndarray:
        """Period-ending stamps moved to the start of their period; instantaneous series unchanged."""
        if not self.data_type.upper().startswith(PERIOD_TYPE_PREFIX):
            return self.times
        return self.times - np.timedelta64(self.interval_seconds, "s")


@dataclass(frozen=True)
class PairedTable:
    """A paired-data record; ``y`` is one-dimensional for a single curve, one column per curve otherwise."""

    pathname: DssPathname
    x: np.ndarray
    y: np.ndarray
    x_units: str
    y_units: str
    x_type: str
    y_type: str


@dataclass(frozen=True)
class GridRecord:
    """A gridded record as stored: ``values`` is (rows, columns) with the southern row first."""

    pathname: DssPathname
    values: np.ndarray
    lower_left_x: int
    lower_left_y: int
    cell_size: float
    x_cell_zero: float
    y_cell_zero: float
    null_value: float
    units: str
    grid_type: int
    srs: str


class DssLookupError(KeyError):
    """No catalogue pathname, or more than one, matches the request."""


def _same(left: str, right: str) -> bool:
    """DSS pathnames are case-insensitive."""
    return left.casefold() == right.casefold()


def _native_open(path: Path) -> Any:
    global _native_configured
    from hecdss import HecDss

    if not _native_configured:
        HecDss.set_global_debug_level(NATIVE_DEBUG_LEVEL)
        _native_configured = True
    return HecDss(str(path))


class DssFile:
    """An open DSS file; a context manager. Use :func:`open_dss` to get one."""

    def __init__(self, path: Path, scratch: Path | None = None) -> None:
        self._native = _native_open(path)
        self._scratch = scratch
        self._catalog: list[DssPathname] | None = None

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Release the file and delete the scratch copy."""
        self._native.close()
        if self._scratch is not None:
            shutil.rmtree(self._scratch, ignore_errors=True)
            self._scratch = None

    @property
    def record_count(self) -> int:
        """Records in the file; a condensed pathname stands for several."""
        return int(self._native.record_count())

    def catalog(self) -> list[DssPathname]:
        """The condensed catalogue."""
        if self._catalog is None:
            items = self._native.get_catalog().items
            self._catalog = [DssPathname(i.A, i.B, i.C, i.D, i.E, i.F) for i in items]
        return self._catalog

    def find(self, b: str, c: str, f: str | None = None, *, e: str | None = None) -> DssPathname:
        """The single pathname with these parts, or :class:`DssLookupError`."""
        matches = [
            p
            for p in self.catalog()
            if _same(p.b, b)
            and _same(p.c, c)
            and (f is None or _same(p.f, f))
            and (e is None or _same(p.e, e))
        ]
        if len(matches) != 1:
            found = [str(p) for p in matches]
            raise DssLookupError(f"{len(matches)} pathnames for B={b!r} C={c!r} F={f!r} E={e!r}: {found}")
        return matches[0]

    def read_timeseries(self, b: str, c: str, f: str | None = None, *, e: str | None = None) -> TimeSeries:
        """The series with parts (B, C, F); ``e`` narrows it when two intervals coexist."""
        pathname = self.find(b, c, f, e=e)
        series = self._native.get(str(pathname))
        return TimeSeries(
            pathname=pathname,
            values=np.asarray(series.values, dtype=float),
            times=np.array(series.times, dtype="datetime64[s]"),
            units=str(series.units),
            data_type=str(series.data_type),
            interval_seconds=int(series.interval),
        )

    def read_paired(self, target: str, c: str | None = None) -> PairedTable:
        """A paired-data record, from a full pathname or from its (B, C) parts."""
        if c is None:
            parts = target.split("/")
            pathname = self.find(parts[2], parts[3])
        else:
            pathname = self.find(target, c)
        table = self._native.get(str(pathname))
        y = np.asarray(table.values, dtype=float)
        return PairedTable(
            pathname=pathname,
            x=np.asarray(table.ordinates, dtype=float),
            y=y[:, 0] if y.ndim == 2 and y.shape[1] == 1 else y,
            x_units=str(table.units_independent),
            y_units=str(table.units_dependent),
            x_type=str(table.type_independent),
            y_type=str(table.type_dependent),
        )

    def grid_pathnames(self) -> list[DssPathname]:
        """Every gridded record; grids are never condensed, so each keeps its own D and E."""
        from hecdss.record_type import RecordType

        items = self._native.get_catalog().items
        return [DssPathname(i.A, i.B, i.C, i.D, i.E, i.F) for i in items if i.recType == RecordType.Grid]

    def read_grid(self, pathname: DssPathname) -> GridRecord:
        """The gridded record at this pathname, as stored."""
        layer = self._native._native
        layer.hec_dss_gridRetrieve = partial(
            layer.hec_dss_gridRetrieve, srsDefinitionLength=GRID_SRS_CHARACTERS
        )
        try:
            grid = self._native.get(str(pathname))
        finally:
            del layer.hec_dss_gridRetrieve
        if grid is None:
            raise DssLookupError(f"no gridded record at {pathname}")
        return GridRecord(
            pathname=pathname,
            values=np.asarray(grid.data, dtype=float),
            lower_left_x=int(grid.lowerLeftCellX),
            lower_left_y=int(grid.lowerLeftCellY),
            cell_size=float(grid.cellSize),
            x_cell_zero=float(grid.xCoordOfGridCellZero),
            y_cell_zero=float(grid.yCoordOfGridCellZero),
            null_value=float(grid.nullValue),
            units=str(grid.dataUnits),
            grid_type=int(grid.type),
            srs=str(grid.srsDefinition),
        )


def open_dss(path: str | Path, *, readonly: bool = True) -> DssFile:
    """Open a DSS file; a missing path raises. ``readonly`` works on a scratch copy deleted on close."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    if not readonly:
        return DssFile(source)
    scratch = Path(tempfile.mkdtemp(prefix=SCRATCH_PREFIX))
    try:
        copy = Path(shutil.copy2(source, scratch / source.name))
        return DssFile(copy, scratch)
    except Exception:
        shutil.rmtree(scratch, ignore_errors=True)
        raise
