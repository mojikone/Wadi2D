"""Corner cutting on rings: a staircase of cells becomes a curve. Pure geometry."""

from __future__ import annotations

import numpy as np
import shapely

QUARTER = 0.25
"""Each corner is replaced by two points this far along its edges."""


def chaikin(ring: np.ndarray, passes: int) -> np.ndarray:
    """A closed ring, first point repeated, after ``passes`` rounds of corner cutting."""
    points = ring[:-1]
    for _ in range(passes):
        following = np.roll(points, -1, axis=0)
        early = (1.0 - QUARTER) * points + QUARTER * following
        late = QUARTER * points + (1.0 - QUARTER) * following
        points = np.empty((2 * early.shape[0], 2))
        points[0::2], points[1::2] = early, late
    return np.vstack((points, points[0]))


def _smooth_polygon(polygon: shapely.Polygon, passes: int) -> shapely.Polygon:
    shell = chaikin(shapely.get_coordinates(polygon.exterior), passes)
    holes = [chaikin(shapely.get_coordinates(ring), passes) for ring in polygon.interiors]
    return shapely.Polygon(shell, holes)


def chaikin_rings(geometry: shapely.Geometry, passes: int) -> shapely.Geometry:
    """Every ring of a polygon or multipolygon, smoothed."""
    parts = [_smooth_polygon(p, passes) for p in shapely.get_parts(geometry)]
    return shapely.make_valid(shapely.MultiPolygon(parts))
