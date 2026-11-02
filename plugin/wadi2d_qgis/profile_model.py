# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The points of one profile, without Qt: drag, add, delete, type, undo.

Each series is its own list of points, sorted by station. The table is the union of their stations, and a series with
no point at a station shows a blank, which the engine reads between its neighbours, as the plot draws it. What cannot
be built is said in ``problems``: the same refusals the engine makes, so a dead end is met before the run.
"""

from __future__ import annotations

from copy import deepcopy

from .profile_table import BED, LEFT, RIGHT, STATION, STATION_DECIMALS, Seed, interp

MIN_GAP = 0.01
"""Closest two points of one series may stand, m: stations must increase."""
TOPS = (LEFT, RIGHT)
LABELS = {BED: "bed", LEFT: "left top", RIGHT: "right top"}
SAME_LEVEL = 1e-9


def _station(value: float) -> float:
    return round(float(value), STATION_DECIMALS)


class ProfileModel:
    """``keys`` in table order; ``length`` of the line. Past the line a table may run on: the engine warns of that."""

    def __init__(self, seed: Seed, length: float, labels: dict[str, str] | None = None) -> None:
        self.points = {
            key: [[_station(s), float(z)] for s, z in found] for key, found in seed.points.items()
        }
        self.keys = tuple(self.points)
        self.length = float(length)
        self.others = deepcopy(seed.others)
        self.labels = {**LABELS, **(labels or {})}
        self.tied = False
        self._undo: list[dict] = []
        self._redo: list[dict] = []
        self._open: dict | None = None
        self._saved = deepcopy(self.points)

    @property
    def limit(self) -> float:
        """The last station a point may take."""
        last = max((found[-1][0] for found in self.points.values() if found), default=0.0)
        return max(self.length, last)

    @property
    def dirty(self) -> bool:
        return self.points != self._saved

    def mark_saved(self) -> None:
        self._saved = deepcopy(self.points)

    # Undo: one step per drag or typed cell, however many points it moved.

    def begin(self) -> None:
        if self._open is None:
            self._open = deepcopy(self.points)

    def end(self) -> None:
        if self._open is not None and self._open != self.points:
            self._undo.append(self._open)
            self._redo.clear()
        self._open = None

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(deepcopy(self.points))
        self.points = self._undo.pop()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(deepcopy(self.points))
        self.points = self._redo.pop()
        return True

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    # What is there.

    def stations(self) -> list[float]:
        return sorted({s for found in self.points.values() for s, _z in found})

    def level(self, key: str, s: float) -> float | None:
        """The level the engine reads for this series at ``s``; None with no points."""
        found = self.points[key]
        return interp(found, s) if found else None

    def at(self, key: str, s: float) -> int | None:
        """The index of this series' point at station ``s``, or None."""
        return next((n for n, point in enumerate(self.points[key]) if point[0] == _station(s)), None)

    def rows(self) -> list[dict]:
        """The table: one row per station, a blank where a series has no point there, the other columns kept."""
        stations = sorted({*self.stations(), *self.others})
        rows = []
        for s in stations:
            row: dict = {STATION: s}
            for key in self.keys:
                index = self.at(key, s)
                row[key] = None if index is None else self.points[key][index][1]
            rows.append({**row, **self.others.get(s, {})})
        return rows

    def _partners(self, key: str) -> list[str]:
        """The series that move with this one."""
        if self.tied and key in TOPS and set(TOPS) <= set(self.keys):
            return [other for other in TOPS if other != key]
        return []

    # Edits. Each returns what went wrong in words, or an empty string.

    def _pinned(self, station: float) -> bool:
        """The two ends of the line stay at the ends, so the profile keeps covering it."""
        return station <= 0.0 or station == _station(self.length)

    def drag(self, key: str, index: int, station: float, level: float) -> None:
        """Move one point; it stops short of its neighbours and of the ends of the line."""
        found = self.points[key]
        old = found[index][0]
        for partner in self._partners(key):
            mate = self.at(partner, old)
            if mate is not None:
                self._place(partner, mate, station, level)
        self._place(key, index, station, level)

    def _place(self, key: str, index: int, station: float, level: float) -> None:
        found = self.points[key]
        old = found[index][0]
        if self._pinned(old):
            station = old
        low = found[index - 1][0] + MIN_GAP if index > 0 else 0.0
        high = found[index + 1][0] - MIN_GAP if index + 1 < len(found) else self.limit
        found[index] = [_station(min(max(station, low), high)), float(level)]

    def add(self, key: str, station: float, level: float) -> int:
        """A new point, or a new level on the point already at this station. Returns its index."""
        station = _station(min(max(station, 0.0), self.limit))
        for name in (key, *self._partners(key)):
            found = self.points[name]
            near = next((n for n, point in enumerate(found) if abs(point[0] - station) < MIN_GAP), None)
            if near is None:
                found.append([station, float(level)])
                found.sort()
            else:
                found[near][1] = float(level)
        return next(n for n, point in enumerate(self.points[key]) if abs(point[0] - station) < MIN_GAP)

    def remove(self, key: str, index: int) -> str:
        """Delete a point; a series keeps at least one."""
        found = self.points[key]
        if len(found) <= 1:
            return f"The {self.labels[key]} needs at least one point."
        station = found[index][0]
        for partner in self._partners(key):
            mate = self.at(partner, station)
            if mate is not None and len(self.points[partner]) > 1:
                del self.points[partner][mate]
        del found[index]
        return ""

    def set_level(self, key: str, station: float, level: float | None) -> str:
        """A typed cell: a number sets the point, a blank takes it away."""
        index = self.at(key, station)
        if level is None:
            return "" if index is None else self.remove(key, index)
        self.add(key, station, level)
        return ""

    def add_station(self, station: float) -> str:
        """A new row: every series gets a point at the level it already has there, so no line moves."""
        station = _station(station)
        if station < 0.0:
            return "A station cannot be negative."
        if station in self.stations():
            return f"Station {station:g} is already in the table."
        for key in self.keys:
            level = self.level(key, station)
            if level is not None:
                self.points[key].append([station, level])
                self.points[key].sort()
        return ""

    def move_station(self, old: float, new: float) -> str:
        """A typed station: the whole row moves."""
        new = _station(new)
        if new < 0.0:
            return "A station cannot be negative."
        if new != _station(old) and new in self.stations():
            return f"Station {new:g} is already in the table."
        for key in self.keys:
            index = self.at(key, old)
            if index is not None:
                self.points[key][index][0] = new
                self.points[key].sort()
        return ""

    def remove_station(self, station: float) -> str:
        """Delete a row; a series left with no point refuses, and nothing moves."""
        having = [key for key in self.keys if self.at(key, station) is not None]
        short = [key for key in having if len(self.points[key]) <= 1]
        if short:
            return f"The {self.labels[short[0]]} needs at least one point."
        for key in having:
            del self.points[key][self.at(key, station)]
        return ""

    def tops_alike(self) -> bool:
        """Both tops the same at every point: the start of a channel with dykes given one top."""
        if not set(TOPS) <= set(self.keys):
            return False
        left, right = self.points[LEFT], self.points[RIGHT]
        return len(left) == len(right) and all(
            a[0] == b[0] and abs(a[1] - b[1]) < SAME_LEVEL for a, b in zip(left, right, strict=True)
        )

    # What the engine would refuse.

    def problems(self) -> list[str]:
        """Why this cannot be saved, in plain words."""
        found = [f"The {self.labels[key]} has no points." for key in self.keys if not self.points[key]]
        if found or BED not in self.keys:
            return found
        stations = sorted({0.0, self.length, *self.stations()})
        for key in self.keys:
            if key == BED:
                continue
            for s in stations:
                top, bed = self.level(key, s), self.level(BED, s)
                if top is not None and bed is not None and top < bed:
                    found.append(f"The {self.labels[key]} is below the bed at station {s:g}.")
                    break
        return found
