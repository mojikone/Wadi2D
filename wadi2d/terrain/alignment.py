"""Where a point sits on a polyline: its station, its signed offset, how far past the end.

Offsets are positive to the right looking along increasing station. Station and offset come from the nearest point
on the line, so on the outside of a bend the pixels fan round the vertex and an offset is a true distance. Past an
end the station holds at the end, ``beyond`` says how far out along the end tangent the point lies, and the offset
is measured square to that tangent.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import shapely

from wadi2d.terrain.crest import line_lengths

EPS_LENGTH = 1e-9


@dataclass(frozen=True)
class Located:
    """Points placed on an alignment."""

    s: np.ndarray
    offset: np.ndarray
    beyond: np.ndarray


class Alignment:
    """A polyline with stations. Repeated vertices are dropped."""

    def __init__(self, coordinates: Sequence[tuple[float, float]]) -> None:
        points = np.asarray(coordinates, dtype=np.float64)[:, :2]
        keep = np.concatenate(([True], np.hypot(*np.diff(points, axis=0).T) > EPS_LENGTH))
        self.points = points[keep]
        if len(self.points) < 2:
            raise ValueError("an alignment needs two different vertices")
        self.stations = line_lengths(self.points)
        self.length = float(self.stations[-1])
        steps = np.diff(self.points, axis=0)
        self.tangents = steps / np.hypot(*steps.T)[:, None]
        self.line = shapely.LineString(self.points)

    def _segment(self, s: np.ndarray) -> np.ndarray:
        return np.clip(np.searchsorted(self.stations, s, side="right") - 1, 0, len(self.tangents) - 1)

    def point_at(self, s: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Coordinates of stations on the line."""
        s = np.asarray(s, dtype=np.float64)
        seg = self._segment(s)
        along = s - self.stations[seg]
        origin = self.points[seg]
        return origin[..., 0] + along * self.tangents[seg, 0], origin[..., 1] + along * self.tangents[seg, 1]

    def offset_at(self, s: np.ndarray, offset: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Coordinates at stations ``s``, ``offset`` to the right of the line."""
        s = np.asarray(s, dtype=np.float64)
        x, y = self.point_at(s)
        seg = self._segment(s)
        return x + offset * self.tangents[seg, 1], y - offset * self.tangents[seg, 0]

    def locate(self, x: np.ndarray, y: np.ndarray) -> Located:
        """Station, offset and distance past the end of each point."""
        x, y = np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)
        s = np.asarray(shapely.line_locate_point(self.line, shapely.points(x, y)), dtype=np.float64)
        px, py = self.point_at(s)
        rx, ry = x - px, y - py
        seg = self._segment(s)
        tx, ty = self.tangents[seg, 0], self.tangents[seg, 1]
        across = rx * ty - ry * tx
        along = rx * tx + ry * ty
        past = np.where(s <= 0.0, -along, np.where(s >= self.length, along, 0.0))
        beyond = np.maximum(past, 0.0)
        side = np.where(across >= 0.0, 1.0, -1.0)
        offset = np.where(beyond > 0.0, across, side * np.hypot(rx, ry))
        return Located(s, offset, beyond)

    def distance(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        return np.asarray(shapely.distance(self.line, shapely.points(x, y)), dtype=np.float64)

    def samples(self, step: float) -> np.ndarray:
        """Stations about ``step`` apart, both ends included."""
        return np.linspace(0.0, self.length, max(int(np.ceil(self.length / step)), 1) + 1)
