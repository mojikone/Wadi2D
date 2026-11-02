"""Gridded rain in a DSS file. Interface: :func:`read_dss_grid`, :func:`dss_choices`.

A frame is one record, ``/A/B/C/D/E/F/``, and only the pathname is its clock: D opens the period and E closes it, in
either order in the catalogue, and the header's ``isInterval`` is 0 on period records that came from DSS 6. A record
with no E, or with E equal to D, has no period, whatever its data type says, so it needs ``spec.interval_min``.

Rows. A DSS grid stores its southern row first, and ``hecdss`` returns that order untouched, so every frame is flipped
here. A round trip through ``hecdss`` cannot show this. It was shown from outside it: a GeoTIFF sampled by coordinate
and imported by HEC's Vortex, and an ESRI ASCII file through HEC's Asc2DssGrid, both end with their north row last in
the stored array; Vortex and Dss2AscGrid read it back north first; and on the HEC-HMS tenk sample, a Stage III radar
file, four subbasins' rain rebuilt from these rows over the 98 hours with a frame equals HEC-HMS's own to 0.000001 mm,
and misses by up to 5 mm in an hour the other way up.

Place. The outer south-west corner is ``cellZero + lowerLeftCell * cellSize``. Every writer tried leaves cell zero at 0
and neither HEC reader tried looks at it, so its sign is the field's plain meaning, not a measured one. Vortex snaps a
raster's origin to whole cells when it writes, by 300 m on a 1 km grid in one test; the file cannot show that.

Nulls. 0 in ``nullValue`` means it was never set, since dry cells are 0: Asc2DssGrid and the DSS 6 migration both leave
0 there and mark their holes with DSS's own -3.4e38, which :func:`depth_in_mm` turns to NaN as any deep negative. Any
other null value is honoured.

Frames of different extent go in the union of their extents; indices are whole cells of one lattice, so nothing is
resampled. Outside a frame's own extent there are two readings, and the file does not say which: it was cut to its wet
cells, so that ground is dry, or the coverage changed, so that ground is unknown. Nothing outside settles it: no real
file surveyed is clipped frame by frame, the one series found to vary mixes two WRF domains of different cell size, which
is refused here, and HEC-HMS 4.13 is no reference, aborting with no message when a cell falls outside a frame and
returning wrong rain even with every cell inside. So the frame decides: rain touching all four of its sides is
what cutting to the wet cells leaves, and its outside is then 0, as it is for a frame with no rain in it; any other
frame was not cut that way, and its outside is NaN. A wrong call costs little: a model reads NaN as no rain, so it
changes the note about missing data and not the depth.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pyproj

from wadi2d.hms.dss import DssFile, DssPathname, GridRecord, open_dss
from wadi2d.io.rain import DSS, RAIN_CHOICES, RAIN_READERS
from wadi2d.storm.rain_frames import SECONDS_PER_MINUTE, RainFrames, RainSpec, depth_in_mm

FILE_MARK = b"ZDSS"
VERSION_AT = 16
OLD_VERSION = b"6"
RAIN_WORDS = ("PRECIP", "RAIN")
"""The start of a rain C part: PRECIP, PRECIPITATION, RAINSH, and not TERRAIN."""
UNSET_NULL = 0.0
STAMP = re.compile(r"^(\d{1,2})([A-Za-z]{3})(\d{4}):(\d{2})(\d{2})$")
MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
SECONDS_PER_HOUR = 3600
HRAP_TYPES = (410, 411)
ALBERS_TYPES = (420, 421)
HRAP_WKT = (
    'PROJCS["Stereographic_CONUS_HRAP",GEOGCS["GCS_Sphere_LFM",DATUM["D_Sphere_LFM",SPHEROID["Sphere_LFM",6371200.0,0.0]],'
    'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],PROJECTION["Stereographic_North_Pole"],'
    'PARAMETER["False_Easting",1909762.5],PARAMETER["False_Northing",7624762.5],PARAMETER["Central_Meridian",-105.0],'
    'PARAMETER["Standard_Parallel_1",60.0],UNIT["Meter",1.0]]'
)
SHG_WKT = (
    'PROJCS["USA_Contiguous_Albers_Equal_Area_Conic_USGS_version",GEOGCS["GCS_North_American_1983",'
    'DATUM["D_North_American_1983",SPHEROID["GRS_1980",6378137.0,298.257222101]],PRIMEM["Greenwich",0.0],'
    'UNIT["Degree",0.0174532925199433]],PROJECTION["Albers"],PARAMETER["False_Easting",0.0],'
    'PARAMETER["False_Northing",0.0],PARAMETER["Central_Meridian",-96.0],PARAMETER["Standard_Parallel_1",29.5],'
    'PARAMETER["Standard_Parallel_2",45.5],PARAMETER["Latitude_Of_Origin",23.0],UNIT["Meter",1.0]]'
)


def _open(path: Path) -> DssFile:
    """The file, on a scratch copy; a file ``hecdss`` cannot read says why here, where it still can be said."""
    with open(path, "rb") as source:
        head = source.read(VERSION_AT + len(OLD_VERSION))
    if not head.startswith(FILE_MARK):
        raise ValueError(f"{path.name} is not a DSS file")
    if head[VERSION_AT:] == OLD_VERSION:
        raise ValueError(
            f"{path.name} is a DSS version 6 file: convert it to version 7, in HEC-DSSVue or HEC-HMS, first"
        )
    return open_dss(path)


def _series(pathnames: list[DssPathname]) -> dict[str, list[DssPathname]]:
    """Records by ``B/C/F``, the name a job gives."""
    found: dict[str, list[DssPathname]] = {}
    for pathname in pathnames:
        found.setdefault(f"{pathname.b}/{pathname.c}/{pathname.f}", []).append(pathname)
    return found


def _is_rain(series: str) -> bool:
    return series.split("/")[1].upper().startswith(RAIN_WORDS)


def _pick(found: dict[str, list[DssPathname]], wanted: str | None, name: str) -> list[DssPathname]:
    if wanted is not None:
        for series, pathnames in found.items():
            if series.casefold() == wanted.casefold():
                return pathnames
        raise ValueError(f"{name}: no gridded series {wanted!r}; it has {sorted(found)}")
    rain = sorted(series for series in found if _is_rain(series))
    if not rain:
        raise ValueError(f"{name}: no gridded precipitation in this file; its grids are {sorted(found)}")
    if len(rain) > 1:
        raise ValueError(f"{name}: say which series is the rain: {rain}")
    return found[rain[0]]


def _stamp(text: str, name: str) -> np.datetime64:
    """A D or E part as a date; 2400 is the end of its day, so it needs no case of its own."""
    match = STAMP.match(text.strip())
    if match is None or match[2].upper() not in MONTHS:
        raise ValueError(f"{name}: {text!r} in a grid's pathname is not a date and time")
    month = MONTHS.index(match[2].upper()) + 1
    day = np.datetime64(f"{match[3]}-{month:02d}-{int(match[1]):02d}", "s")
    return day + np.timedelta64(
        int(match[4]) * SECONDS_PER_HOUR + int(match[5]) * int(SECONDS_PER_MINUTE), "s"
    )


def _period(pathname: DssPathname, spec: RainSpec, name: str) -> tuple[np.datetime64, np.datetime64]:
    opens = _stamp(pathname.d, name)
    closes = _stamp(pathname.e, name) if pathname.e else opens
    if closes != opens:
        return opens, closes
    if spec.interval_min is None:
        raise ValueError(
            f"{name}: these grids are instantaneous, with one time each and no period: set the interval by hand"
        )
    length = np.timedelta64(round(spec.interval_min * SECONDS_PER_MINUTE), "s")
    return (opens - length, opens) if spec.stamp == "end" else (opens, opens + length)


def _depth(record: GridRecord, period_min: float, units: str) -> np.ndarray:
    """Depth fallen in one frame, northern row first."""
    stored = record.values.astype(np.float64)
    if record.null_value != UNSET_NULL:
        stored[stored == record.null_value] = np.nan
    return depth_in_mm(stored[np.newaxis, ::-1], record.units, units, np.array([period_min]))[0]


def _cut_to_rain(depth: np.ndarray) -> bool:
    """True when nothing shows this frame held more than its wet cells, so the ground outside it is dry."""
    wet = np.nan_to_num(depth) > 0.0
    if not wet.any():
        return True
    return bool(wet[0].any() and wet[-1].any() and wet[:, 0].any() and wet[:, -1].any())


def _stack(depths: list[np.ndarray], records: list[GridRecord]) -> tuple[np.ndarray, int, int]:
    """(frames, rows, columns) over the union of the extents, and that union's western and northern cell edges."""
    held = [record for record in records if record.values.size]
    left = min(record.lower_left_x for record in held)
    bottom = min(record.lower_left_y for record in held)
    right = max(record.lower_left_x + record.values.shape[1] for record in held)
    top = max(record.lower_left_y + record.values.shape[0] for record in held)
    stack = np.empty((len(records), top - bottom, right - left))
    for frame, (depth, record) in enumerate(zip(depths, records, strict=True)):
        stack[frame] = 0.0 if _cut_to_rain(depth) else np.nan
        if depth.size:
            row = top - record.lower_left_y - depth.shape[0]
            column = record.lower_left_x - left
            stack[frame, row : row + depth.shape[0], column : column + depth.shape[1]] = depth
    return stack, left, top


def _crs(record: GridRecord, name: str) -> str:
    text = record.srs.strip()
    if not text and record.grid_type in HRAP_TYPES:
        text = HRAP_WKT
    if not text and record.grid_type in ALBERS_TYPES:
        text = SHG_WKT
    if text:
        try:
            pyproj.CRS.from_user_input(text)
        except pyproj.exceptions.CRSError as problem:
            raise ValueError(
                f"{name}: the coordinate system of these grids cannot be read: {text[:80]}"
            ) from problem
    return text


def _one_grid(records: list[GridRecord], name: str) -> GridRecord:
    """The first record that has cells, once all of them are known to share one lattice and one system."""
    held = [record for record in records if record.values.size]
    if not held:
        raise ValueError(f"{name}: these grids hold no cells")
    first = held[0]
    for record in held:
        same = (record.cell_size, record.x_cell_zero, record.y_cell_zero, record.srs)
        if same != (first.cell_size, first.x_cell_zero, first.y_cell_zero, first.srs):
            raise ValueError(f"{name}: {record.pathname} is not on the same grid as {first.pathname}")
    return first


@RAIN_READERS.register(DSS)
def read_dss_grid(path: Path, spec: RainSpec) -> RainFrames:
    with _open(path) as dss:
        pathnames = _pick(_series(dss.grid_pathnames()), spec.variable, path.name)
        if len({pathname.a.casefold() for pathname in pathnames}) > 1:
            raise ValueError(
                f"{path.name}: this series runs under more than one A part: {sorted({p.a for p in pathnames})}"
            )
        timed = sorted(((_period(p, spec, path.name), p) for p in pathnames), key=lambda item: item[0])
        records = [dss.read_grid(pathname) for _, pathname in timed]
    first = _one_grid(records, path.name)
    starts = np.array([period[0] for period, _ in timed], dtype="datetime64[s]")
    ends = np.array([period[1] for period, _ in timed], dtype="datetime64[s]")
    origin = starts[0]
    one_minute = np.timedelta64(int(SECONDS_PER_MINUTE), "s")
    starts_min, ends_min = (starts - origin) / one_minute, (ends - origin) / one_minute
    grids = [
        _depth(record, float(end - start), spec.units)
        for record, start, end in zip(records, starts_min, ends_min, strict=True)
    ]
    depths, left, top = _stack(grids, records)
    west = first.x_cell_zero + left * first.cell_size
    north = first.y_cell_zero + top * first.cell_size
    crs = _crs(first, path.name)
    return RainFrames(
        depths, starts_min, ends_min, west, north, first.cell_size, first.cell_size, crs, origin
    )


def dss_choices(path: Path) -> list[str]:
    with _open(path) as dss:
        return sorted(series for series in _series(dss.grid_pathnames()) if _is_rain(series))


RAIN_CHOICES[DSS] = dss_choices
