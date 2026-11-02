"""A cross-section along an alignment: every value at every station, from the three ways of giving it.

A value comes from the first of these that has it: the section table, the vertex profile of the line, the constants
on the object, the design rule (a bed from a level and a slope; a top as freeboard above the water). Between stations
every value is read linearly, so two different sections join without a step; past the last station it holds.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
from pydantic import ValidationError

from wadi2d.config.schema import RunConfig, Section, SectionRow, TerrainObject
from wadi2d.terrain.crest import line_lengths

LEFT, RIGHT = 0, 1
SIDES = ("left", "right")
TABLE_ENCODING = "utf-8-sig"
"""Spreadsheets save CSV with a byte-order mark."""
SEPARATORS = ";,\t"


@dataclass
class SectionAt:
    """The section at many points, one side each. An embankment's crest is ``crest`` either side of the line."""

    bed: np.ndarray
    half: np.ndarray
    top: np.ndarray
    inner: np.ndarray
    crest: np.ndarray
    outer: np.ndarray

    def pick(self, mask: np.ndarray) -> SectionAt:
        return SectionAt(self.bed[mask], self.half[mask], self.top[mask], self.inner[mask], self.crest[mask], self.outer[mask])


@dataclass(frozen=True)
class Profile:
    """Section values at stations; the side arrays are (2, n), left then right."""

    station: np.ndarray
    bed: np.ndarray
    half: np.ndarray
    top: np.ndarray
    inner: np.ndarray
    crest: np.ndarray
    outer: np.ndarray

    def at(self, s: np.ndarray, right: np.ndarray | bool) -> SectionAt:
        """Interpolate to stations ``s``; ``right`` picks the side of each."""
        s = np.asarray(s, dtype=np.float64)
        right = np.broadcast_to(right, s.shape)

        def line(values: np.ndarray) -> np.ndarray:
            return np.interp(s, self.station, values)

        def sided(values: np.ndarray) -> np.ndarray:
            return np.where(right, line(values[RIGHT]), line(values[LEFT]))

        return SectionAt(
            line(self.bed),
            line(self.half),
            sided(self.top),
            sided(self.inner),
            sided(self.crest),
            sided(self.outer),
        )


def read_table(path: str | Path) -> list[SectionRow]:
    """The rows of a CSV section table; a wrong table is refused in plain words."""
    source = Path(path)
    lines = source.read_text(encoding=TABLE_ENCODING).splitlines()
    head = lines[0] if lines else ""
    reader = csv.DictReader(lines, delimiter=max(SEPARATORS, key=head.count))
    names = [(name or "").strip().lower() for name in reader.fieldnames or []]
    if "station" not in names:
        raise ValueError(f"section table {source.name}: the first line must name a 'station' column")
    unknown = sorted(set(names) - set(SectionRow.model_fields))
    if unknown:
        known = ", ".join(SectionRow.model_fields)
        raise ValueError(f"section table {source.name}: unknown column {unknown[0]}; the columns are {known}")
    rows = []
    for number, raw in enumerate(reader, start=2):
        cells = {name.strip().lower(): (value or "").strip() for name, value in raw.items() if name}
        if not any(cells.values()):
            continue
        try:
            rows.append(SectionRow(**{name: float(value) for name, value in cells.items() if value}))
        except (ValueError, ValidationError) as error:
            raise ValueError(f"section table {source.name}, line {number}: {error}") from error
    if not rows:
        raise ValueError(f"section table {source.name} has no rows")
    return rows


def with_tables(cfg: RunConfig) -> RunConfig:
    """The job with every section table read into its object, so the hashes and the saved job hold the numbers."""
    objects = []
    for obj in cfg.terrain.objects:
        section = obj.section
        if section is not None and section.table is not None and not section.rows:
            rows = [row.model_dump() for row in read_table(section.table)]
            filled = Section.model_validate({**section.model_dump(), "rows": rows})
            obj = obj.model_copy(update={"section": filled})
        objects.append(obj)
    return cfg.model_copy(update={"terrain": cfg.terrain.model_copy(update={"objects": objects})})


def _column(rows: list[SectionRow], *names: str) -> tuple[np.ndarray, np.ndarray] | None:
    """Stations and values of the first named column with a value on each row; None when no row has one."""
    stations, values = [], []
    for row in rows:
        found = next((getattr(row, n) for n in names if getattr(row, n) is not None), None)
        if found is not None:
            stations.append(row.station)
            values.append(found)
    return (np.array(stations), np.array(values)) if values else None


def _value(stations: np.ndarray, rows: list[SectionRow], constant: float, name: str) -> np.ndarray:
    column = _column(rows, name)
    return np.full(stations.shape, float(constant)) if column is None else np.interp(stations, *column)


def _stations(obj: TerrainObject, section: Section, length: float) -> np.ndarray:
    known = [0.0, length, *(row.station for row in section.rows)]
    if obj.z is not None:
        known.extend(line_lengths(obj.coordinates))
    return np.unique(np.array(known, dtype=np.float64))


def _line_profile(obj: TerrainObject, stations: np.ndarray) -> np.ndarray | None:
    if obj.z is not None:
        return np.interp(stations, line_lengths(obj.coordinates), np.asarray(obj.z, dtype=np.float64))
    if obj.z_constant is not None:
        return np.full(stations.shape, float(obj.z_constant))
    return None


def _bed(obj: TerrainObject, section: Section, stations: np.ndarray) -> np.ndarray | None:
    column = _column(section.rows, "bed_z")
    if column is not None:
        return np.interp(stations, *column)
    profile = None if obj.kind == "embankment" else _line_profile(obj, stations)
    if profile is not None:
        return profile
    if section.bed_z is not None:
        return np.full(stations.shape, section.bed_z)
    if section.bed_start_z is not None and section.bed_slope is not None:
        return section.bed_start_z - section.bed_slope * stations
    return None


def _designed_top(section: Section, stations: np.ndarray, bed: np.ndarray | None) -> np.ndarray | None:
    """The top as freeboard above the water: a water column in the table, or a depth above the bed."""
    if section.freeboard is None:
        return None
    water = _column(section.rows, "water_z")
    if water is not None:
        return np.interp(stations, *water) + section.freeboard
    if bed is None or section.water_depth is None:
        return None
    return bed + section.water_depth + section.freeboard


def _top(obj, section: Section, stations: np.ndarray, bed: np.ndarray | None, side: str) -> np.ndarray | None:
    name = f"{side}_top_z"
    column = _column(section.rows, name, "crest_z")
    if column is not None:
        return np.interp(stations, *column)
    constant = getattr(section, name)
    constant = constant if constant is not None else section.crest_z
    if constant is not None:
        return np.full(stations.shape, float(constant))
    profile = _line_profile(obj, stations) if obj.kind == "embankment" else None
    return profile if profile is not None else _designed_top(section, stations, bed)


def _sided(section: Section, stations: np.ndarray, pattern: str) -> np.ndarray:
    names = [pattern.format(side) for side in SIDES]
    return np.array([_value(stations, section.rows, getattr(section, n), n) for n in names])


def build_profile(obj: TerrainObject, length: float) -> Profile:
    """Every value of a shaped object at every station it needs; an object that cannot be built is refused."""
    section = obj.section or Section()
    title = obj.name or obj.kind
    stations = _stations(obj, section, length)
    bed = _bed(obj, section, stations)
    half = 0.5 * _value(stations, section.rows, section.width, "width")
    inner = _sided(section, stations, "{}_slope")
    crest = _sided(section, stations, "{}_crest_width")
    outer = _sided(section, stations, "{}_outer_slope")
    if obj.kind != "embankment" and bed is None:
        raise ValueError(f"{title}: the section gives no bed elevation")
    if obj.kind == "channel":
        top = np.array([bed, bed])
    else:
        tops = [_top(obj, section, stations, bed, side) for side in SIDES]
        if tops[0] is None or tops[1] is None:
            raise ValueError(f"{title}: the section gives no top elevation on both banks")
        top = np.array(tops)
    if obj.kind == "embankment":
        return Profile(stations, top.min(axis=0), half, top, np.zeros_like(inner), np.array([half, half]), inner)
    below = np.flatnonzero((top < bed).any(axis=0))
    if below.size:
        raise ValueError(f"{title}: the top is below the bed at station {stations[below[0]]:g}")
    return Profile(stations, bed, half, top, inner, crest, outer)


def lowered(section: SectionAt, mask: np.ndarray, level: float) -> SectionAt:
    """The same section with its top no higher than ``level`` where ``mask`` holds."""
    return replace(section, top=np.where(mask, np.minimum(section.top, level), section.top))
