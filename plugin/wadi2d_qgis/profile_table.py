# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""A saved profile: a section table on disk, in the columns the engine reads, and how a line finds its own.

Pure Python, no QGIS and no engine: this side only has to write what ``wadi2d.terrain.sections.read_table`` reads. The
file is the record. Nothing is kept in the project except a chosen folder, so a reopened project finds its profiles.

A value comes from the same place the engine takes it, in the same order, so opening a line and saving it changes
nothing: a table, then Z on the vertices or a constant, then the design rule. What gives no level starts on the ground.
"""

from __future__ import annotations

import csv
import itertools
import re
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path

from .boundary_rows import line_label
from .job_builder import Feature, LayerError
from .shaped import TOP

STATION = "station"
BED = "bed_z"
CREST = "crest_z"
LEFT = "left_top_z"
RIGHT = "right_top_z"
WATER = "water_z"
LEVELS = (BED, CREST, LEFT, RIGHT)
"""The columns the editor owns; every other column of a table is kept as it stands."""

ENCODING = "utf-8-sig"
SEPARATORS = ";,\t"
"""As the engine reads a table: spreadsheets save a byte-order mark, and semicolons in some locales."""
NUMBER_FORMAT = ".10g"
STATION_DECIMALS = 3
"""Stations are compared at this many decimals, so a row of the table is one station for every series."""
SAME_VERTEX = 1e-6

EDGE_KINDS = ("crest_line", "spillway", "burn_line")
"""Kinds with one elevation per vertex and no section table."""
FOLDER_PROPERTY = "wadi2d/profile_folder"
FOLDER_SUFFIX = "_profiles"
FILE_NAME = "{kind}_line_{key}.csv"
OLD_SUFFIX = ".dropped"
MEMORY_FOLDER = "wadi2d_profiles"
_UNSAFE = re.compile(r"[^\w.-]+")


@dataclass
class Seed:
    """The profile a line has now: points per series, the other columns by station, and what to tell the user."""

    points: dict[str, list[tuple[float, float]]]
    others: dict[float, dict[str, float]] = field(default_factory=dict)
    note: str = ""


@dataclass(frozen=True)
class Line:
    """One line of a layer as the editor needs it. ``coordinates`` may carry Z; ``table`` is the table in force."""

    key: str
    fid: int
    label: str
    kind: str
    coordinates: list
    properties: dict
    table: str | None = None

    def stations(self) -> list[float]:
        return vertex_stations(self.coordinates)

    @property
    def length(self) -> float:
        return self.stations()[-1]


def vertex_stations(coordinates: list) -> list[float]:
    """Distance along a polyline at each vertex, m."""
    stations = [0.0]
    for (x0, y0, *_), (x1, y1, *_) in itertools.pairwise(coordinates):
        stations.append(stations[-1] + ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5)
    return stations


def point_at(coordinates: list, stations: list[float], s: float) -> tuple[float, float]:
    """The point at station ``s`` of a polyline; past an end, that end."""
    if s <= stations[0]:
        return coordinates[0][0], coordinates[0][1]
    for n in range(1, len(stations)):
        if s <= stations[n]:
            run = stations[n] - stations[n - 1]
            share = (s - stations[n - 1]) / run if run > 0.0 else 0.0
            (x0, y0, *_), (x1, y1, *_) = coordinates[n - 1], coordinates[n]
            return x0 + share * (x1 - x0), y0 + share * (y1 - y0)
    return coordinates[-1][0], coordinates[-1][1]


def interp(points: list, s: float) -> float:
    """The level at ``s`` between points sorted by station; past either end it holds, as the engine reads it."""
    if s <= points[0][0]:
        return points[0][1]
    if s >= points[-1][0]:
        return points[-1][1]
    for (s0, z0), (s1, z1) in itertools.pairwise(points):
        if s <= s1:
            return z0 + (s - s0) / (s1 - s0) * (z1 - z0) if s1 > s0 else z1
    return points[-1][1]


def _cell(text: str):
    return float(text) if text else None


def read_rows(path: Path | str) -> list[dict]:
    """The rows of a section table as a list of dicts of numbers; a blank cell is None."""
    source = Path(path)
    lines = source.read_text(encoding=ENCODING).splitlines()
    head = lines[0] if lines else ""
    reader = csv.DictReader(lines, delimiter=max(SEPARATORS, key=head.count))
    rows = []
    for number, raw in enumerate(reader, start=2):
        cells = {(name or "").strip().lower(): (value or "").strip() for name, value in raw.items() if name}
        if not any(cells.values()):
            continue
        if not cells.get(STATION):
            raise ValueError(f"section table {source.name}, line {number}: every row needs a station")
        try:
            rows.append({name: _cell(value) for name, value in cells.items()})
        except ValueError as error:
            raise ValueError(f"section table {source.name}, line {number}: {error}") from error
    return rows


def _text(value) -> str:
    return "" if value is None else format(value, NUMBER_FORMAT)


def write_rows(path: Path | str, rows: list[dict]) -> Path:
    """Rows to a CSV the engine reads: the station, the levels, then the other columns as they came."""
    names = [name for row in rows for name in row]
    others = list(dict.fromkeys(name for name in names if name != STATION and name not in LEVELS))
    columns = [STATION, *(name for name in LEVELS if name in names), *others]
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(columns)
        for row in rows:
            writer.writerow(_text(row.get(name)) for name in columns)
    return target


def _column(rows: list[dict], *names: str) -> list[tuple[float, float]]:
    """Stations and values of the first named column with a value on each row."""
    found = []
    for row in rows:
        value = next((row[name] for name in names if row.get(name) is not None), None)
        if value is not None:
            found.append((row[STATION], value))
    return found


def _line_levels(line: Line) -> list[tuple[float, float]]:
    """The line's own level, as ``_object`` and ``shaped_object`` choose it: a constant, then Z on the vertices."""
    stations = line.stations()
    constant = line.properties.get(CREST)
    if constant is not None:
        return [(stations[0], constant), (stations[-1], constant)]
    if line.coordinates and all(len(point) == 3 for point in line.coordinates):
        return _distinct(list(zip(stations, (point[2] for point in line.coordinates), strict=True)))
    return []


def _distinct(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """A repeated vertex gives one point: stations must increase."""
    kept: list[tuple[float, float]] = []
    for s, z in points:
        if not kept or s > kept[-1][0]:
            kept.append((s, z))
    return kept


def _bed(line: Line, rows: list[dict]) -> list[tuple[float, float]]:
    found = _column(rows, BED) or _line_levels(line)
    if found:
        return found
    start, fall = line.properties.get("bed_start_z"), line.properties.get("bed_slope")
    if start is None or fall is None:
        return []
    return [(0.0, start), (line.length, start - fall * line.length)]


def _designed_top(line: Line, rows: list[dict], bed: list) -> list[tuple[float, float]]:
    """The top as freeboard above the water: a water column, or a depth above the bed."""
    freeboard = line.properties.get("freeboard")
    if freeboard is None:
        return []
    water = _column(rows, WATER)
    if water:
        return [(s, z + freeboard) for s, z in water]
    depth = line.properties.get("water_depth")
    return [(s, z + depth + freeboard) for s, z in bed] if depth is not None and bed else []


def _top(line: Line, rows: list[dict], bed: list, name: str) -> list[tuple[float, float]]:
    column = _column(rows, name, CREST)
    if column:
        return column
    props = line.properties
    own = props.get(name) if name != CREST else None  # crest_z on the line is its level, read below
    constant = own if own is not None else props.get(TOP)
    if constant is not None:
        return [(0.0, constant), (line.length, constant)]
    return (_line_levels(line) if line.kind == "embankment" else []) or _designed_top(line, rows, bed)


def series_keys(kind: str, rows: list[dict]) -> tuple[str, ...]:
    """What is edited on a kind. An embankment with a top for each side in its table keeps the two."""
    if kind == "channel":
        return (BED,)
    if kind == "channel_dyke":
        return (BED, LEFT, RIGHT)
    if kind == "embankment" and any(row.get(LEFT) is not None or row.get(RIGHT) is not None for row in rows):
        return (LEFT, RIGHT)
    return (CREST,)


def _on_ground(line: Line, ground: list, floor: list) -> list[tuple[float, float]]:
    """Points on the ground at the vertices, never under ``floor``: where a line with no level starts."""
    if not ground:
        return []
    points = [(s, interp(ground, s)) for s in line.stations()]
    return _distinct([(s, max(z, interp(floor, s)) if floor else z) for s, z in points])


def seed(line: Line, ground: list, rows: list[dict] | None = None) -> Seed:
    """The profile the engine would build for this line today. ``ground``: (station, level) along the line."""
    rows = rows or []
    keys = series_keys(line.kind, rows)
    points: dict[str, list[tuple[float, float]]] = {}
    if BED in keys:
        points[BED] = _bed(line, rows)
    for key in keys:
        if key in (LEFT, RIGHT):
            points[key] = _top(line, rows, points.get(BED, []), key)
        elif key == CREST:
            own = _column(rows, CREST) or _line_levels(line)
            points[key] = _top(line, rows, [], key) if line.kind == "embankment" else own
    empty = [key for key, found in points.items() if not found]
    for key in empty:
        points[key] = _on_ground(line, ground, points.get(BED, []) if key != BED else [])
    note = "No level given yet: these points start on the ground. Drag them to the design." if empty else ""
    return Seed(points, _other_columns(rows), note)


def _other_columns(rows: list[dict]) -> dict[float, dict[str, float]]:
    """What a table holds beyond the levels, by station, with the blanks left out. A top in crest_z is a level."""
    others = {}
    for row in rows:
        kept = {
            name: value
            for name, value in row.items()
            if name != STATION and name not in LEVELS and value is not None
        }
        if kept:
            others[round(row[STATION], STATION_DECIMALS)] = kept
    return others


def with_levels(coordinates: list, points: list) -> list[list[float]]:
    """Each vertex with its level, plus a vertex on the line at every profile station between two vertices."""
    stations = vertex_stations(coordinates)
    length = stations[-1]
    wanted = sorted({*stations, *(s for s, _z in points if 0.0 < s < length)})
    merged: list[float] = []
    for s in wanted:
        if not merged or s - merged[-1] > SAME_VERTEX:
            merged.append(s)
    return [[*point_at(coordinates, stations, s), interp(points, s)] for s in merged]


def apply_levels(feature: Feature, table: str | None) -> Feature:
    """A crest line, spillway or burn line with its saved profile on its vertices; with none, as it came."""
    if not table:
        return feature
    try:
        points = _column(read_rows(table), CREST)
    except (OSError, ValueError) as error:
        raise LayerError(f"The saved profile {Path(table).name} cannot be read: {error}") from error
    if not points:
        raise LayerError(f"The saved profile {Path(table).name} holds no elevations.")
    properties = {key: value for key, value in feature.properties.items() if key != CREST}
    return replace(feature, coordinates=with_levels(feature.coordinates, points), properties=properties)


def keyed(features: list[Feature]) -> list[tuple[str, int, Feature]]:
    """(key, feature id, feature) for each part, the id taken back out, so what goes on is what came from the layer."""
    seen: dict[int, int] = {}
    found = []
    for feature in features:
        fid = feature.properties["fid"]
        seen[fid] = seen.get(fid, 0) + 1
        key = str(fid) if seen[fid] == 1 else f"{fid}_part{seen[fid]}"
        properties = {name: value for name, value in feature.properties.items() if name != "fid"}
        found.append((key, fid, replace(feature, properties=properties)))
    return found


def part_label(number: int, feature: Feature, key: str) -> str:
    """How the editor names a line: its name or its number; a part after the first says so."""
    name = line_label(number, feature.properties.get("name"))
    part = key.partition("_part")[2]
    return f"{name}, part {part}" if part else name


def profile_folder(layer) -> Path:
    """Where this layer's profiles live: the folder chosen for it, else beside its file.

    A layer with no file dies with the session, and its profiles go to the temporary folder with it.
    """
    chosen = layer.customProperty(FOLDER_PROPERTY)
    if chosen:
        return Path(str(chosen))
    parts = layer.source().split("|")
    path = Path(parts[0])
    if not path.is_file():
        return Path(tempfile.gettempdir()) / MEMORY_FOLDER / _UNSAFE.sub("_", layer.id())
    inner = next((part.split("=", 1)[1] for part in parts[1:] if part.startswith("layername=")), "")
    return path.parent / ("_".join(filter(None, (path.stem, inner))) + FOLDER_SUFFIX)


def profile_path(folder: Path, kind: str, key: str) -> Path:
    return Path(folder) / FILE_NAME.format(kind=kind, key=key)


class ProfileStore:
    """Which line has a saved profile. ``draft`` stands in for one line while the editor previews unsaved points."""

    def __init__(self) -> None:
        self.draft: tuple[str, str, str] | None = None

    def table(self, layer, kind: str, key: str) -> str | None:
        """The table that outranks every other route for this line, or None."""
        if self.draft is not None and self.draft[:2] == (kind, key):
            return self.draft[2]
        path = profile_path(profile_folder(layer), kind, key)
        return str(path) if path.is_file() else None

    def count(self, layer, kind: str) -> int:
        folder = profile_folder(layer)
        return len(list(folder.glob(FILE_NAME.format(kind=kind, key="*")))) if folder.is_dir() else 0

    def drop(self, layer, kind: str, key: str) -> None:
        """Take a saved profile out of use, leaving the file beside the others under another name."""
        path = profile_path(profile_folder(layer), kind, key)
        if path.is_file():
            path.replace(path.with_name(path.name + OLD_SUFFIX))

