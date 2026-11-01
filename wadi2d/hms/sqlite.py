"""The basin ``.sqlite``: subbasin polygons, reach lines and the terrain statistics HMS computed.

Interface: :func:`connect`, :func:`subbasin_polygons`, :func:`reach_lines`, :func:`subbasin_statistics`,
:func:`reach_statistics`. The file is opened read-only and immutable, so SQLite neither writes nor creates a
journal beside it. Geometry is returned as the stored WKB; ``.shape()`` decodes it with shapely on request.

``reach2d`` holds more than the reach elements: stream links named after a subbasin and repeated names
occur, and only some rows carry ``length`` and ``slope``. Pass ``names`` to :func:`reach_lines` to keep the
rows of given reaches.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SUBBASIN_TABLE = "subbasin2d"
REACH_TABLE = "reach2d"
SUBBASIN_STATISTICS_TABLE = "subbasin_statistics"
REACH_STATISTICS_TABLE = "reach_statistics"
READ_ONLY_QUERY = "?mode=ro&immutable=1"


def connect(path: str | Path) -> sqlite3.Connection:
    """Open the file read-only and immutable; a missing file raises instead of being created."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    return sqlite3.connect(f"{source.resolve().as_uri()}{READ_ONLY_QUERY}", uri=True)


def _number(value: Any) -> float | None:
    """The statistics columns are VARCHAR: numbers arrive as text, or as nothing."""
    return None if value is None or value == "" else float(value)


def _shape(wkb: bytes) -> Any:
    import shapely

    return shapely.from_wkb(wkb)


@dataclass(frozen=True)
class SubbasinPolygon:
    """A row of ``subbasin2d``; the polygon may be multi-part."""

    name: str
    wkb: bytes
    centroid_x: float | None
    centroid_y: float | None
    area_sqkm: float | None

    def shape(self) -> Any:
        """The geometry as a shapely object."""
        return _shape(self.wkb)


@dataclass(frozen=True)
class ReachLine:
    """A row of ``reach2d``."""

    name: str
    wkb: bytes
    length: float | None
    slope: float | None

    def shape(self) -> Any:
        """The geometry as a shapely object."""
        return _shape(self.wkb)


@dataclass(frozen=True)
class SubbasinStatistics:
    """A row of ``subbasin_statistics``; flowpath lengths in ``length_units``."""

    name: str
    longest_length: float | None
    longest_slope: float | None
    centroidal_length: float | None
    centroidal_slope: float | None
    length_10_85: float | None
    slope_10_85: float | None
    basin_slope: float | None
    basin_relief: float | None
    length_units: str | None


@dataclass(frozen=True)
class ReachStatistics:
    """A row of ``reach_statistics``."""

    name: str
    length: float | None
    slope: float | None
    relief: float | None
    sinuosity: float | None
    length_units: str | None


def subbasin_polygons(path: str | Path) -> list[SubbasinPolygon]:
    """Every row of ``subbasin2d``, ordered by name."""
    query = f"select name, GEOMETRY, centroid_x, centroid_y, area_sqkm from {SUBBASIN_TABLE} order by name"
    with connect(path) as connection:
        return [SubbasinPolygon(*row) for row in connection.execute(query)]


def reach_lines(path: str | Path, names: Iterable[str] | None = None) -> list[ReachLine]:
    """Rows of ``reach2d``, all of them or only those named in ``names``."""
    query = f"select name, GEOMETRY, length, slope from {REACH_TABLE} order by rowid"
    wanted = None if names is None else set(names)
    with connect(path) as connection:
        rows = [ReachLine(*row) for row in connection.execute(query)]
    return [row for row in rows if wanted is None or row.name in wanted]


def subbasin_statistics(path: str | Path) -> dict[str, SubbasinStatistics]:
    """``subbasin_statistics`` by subbasin name, the text columns as numbers."""
    query = f"""select subbasin_name, longest_length, longest_slope, centroidal_length, centroidal_slope,
                "10_85_length", "10_85_slope", basin_slope, basin_relief, length_units
                from {SUBBASIN_STATISTICS_TABLE}"""
    with connect(path) as connection:
        rows = connection.execute(query).fetchall()
    return {
        row[0]: SubbasinStatistics(row[0], *[_number(value) for value in row[1:9]], row[9]) for row in rows
    }


def reach_statistics(path: str | Path) -> dict[str, ReachStatistics]:
    """``reach_statistics`` by reach name, the text columns as numbers."""
    query = f"""select reach_name, reach_length, reach_slope, reach_relief, reach_sinuosity, length_units
                from {REACH_STATISTICS_TABLE}"""
    with connect(path) as connection:
        rows = connection.execute(query).fetchall()
    return {row[0]: ReachStatistics(row[0], *[_number(value) for value in row[1:5]], row[5]) for row in rows}
