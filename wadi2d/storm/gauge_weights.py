"""How gauges share a place: nearest gauge, and inverse distance. Interface: :func:`nearest`, :func:`inverse_distance`,
:func:`thiessen_shares`, :func:`polygon_points`.

**Thiessen.** A place takes its nearest gauge; a tie goes to the gauge listed first. Over a polygon the share of a gauge
is the exact area of the polygon nearer to it than to any other, cut out by the perpendicular bisectors.

**Inverse distance**, as HEC-HMS's method of that name: ``w_g = d_g^-p / sum(d^-p)`` over the gauges that count, with
``p`` 2 in HMS. The gauges that count are those within the search radius; with ``quadrants`` on, only the nearest of
them in each of the four quadrants made by a north-south and an east-west axis through the place, so a cluster on one
side counts once. A place standing on a gauge takes that gauge alone. A place with no gauge within the radius takes its
nearest gauge, and the caller is told how many did: no rain at all would be the worse answer.

Coordinates are plane metres in one system; nothing here knows a CRS.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import shapely

FloatArray = np.ndarray
CHUNK = 500_000
"""Places worked on at once, so memory stays bounded on any domain."""
REACH = 4.0
"""How far a bisector's half-plane is drawn, in diagonals of the box that holds the polygon and the gauges."""
QUADRANTS = ((True, True), (False, True), (False, False), (True, False))
"""(east of the place, north of it): north-east, north-west, south-west, south-east."""


def _distances(x: np.ndarray, y: np.ndarray, gauges: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    east = gauges[None, :, 0] - x[:, None]
    north = gauges[None, :, 1] - y[:, None]
    return np.hypot(east, north), east, north


def nearest(x: np.ndarray, y: np.ndarray, gauges: np.ndarray) -> np.ndarray:
    """The index of each place's nearest gauge; a tie goes to the gauge listed first."""
    x, y = np.asarray(x, np.float64).ravel(), np.asarray(y, np.float64).ravel()
    out = np.empty(x.size, np.int64)
    for start in range(0, x.size, CHUNK):
        part = slice(start, start + CHUNK)
        out[part] = np.argmin(_distances(x[part], y[part], gauges)[0], axis=1)
    return out


def _chunk_weights(x, y, gauges, power: float, radius: float | None, quadrants: bool) -> tuple[np.ndarray, int]:
    distance, east, north = _distances(x, y, gauges)
    counts = np.ones_like(distance, dtype=bool) if radius is None else distance <= radius
    lost = ~counts.any(axis=1)
    if quadrants:
        kept = np.zeros_like(counts)
        rows = np.arange(x.size)
        for is_east, is_north in QUADRANTS:
            inside = counts & ((east >= 0.0) == is_east) & ((north >= 0.0) == is_north)
            best = np.argmin(np.where(inside, distance, np.inf), axis=1)
            has = inside.any(axis=1)
            kept[rows[has], best[has]] = True
        counts = kept
    closest = np.argmin(distance, axis=1)
    on_gauge = distance[np.arange(x.size), closest] == 0.0
    with np.errstate(divide="ignore"):
        raw = np.where(counts, distance**-power, 0.0)
    alone = lost | on_gauge
    raw[alone] = 0.0
    raw[alone, closest[alone]] = 1.0
    return raw / raw.sum(axis=1, keepdims=True), int(np.count_nonzero(lost))


def inverse_distance(
    x: np.ndarray,
    y: np.ndarray,
    gauges: np.ndarray,
    power: float = 2.0,
    radius: float | None = None,
    quadrants: bool = True,
) -> tuple[np.ndarray, int]:
    """(weights, places) : one row of gauge weights per place, each summing to 1, and how many places had no gauge
    within the radius and took their nearest one."""
    x, y = np.asarray(x, np.float64).ravel(), np.asarray(y, np.float64).ravel()
    out = np.empty((x.size, gauges.shape[0]), np.float32 if x.size > CHUNK else np.float64)
    lost = 0
    for start in range(0, x.size, CHUNK):
        part = slice(start, start + CHUNK)
        out[part], missed = _chunk_weights(x[part], y[part], gauges, power, radius, quadrants)
        lost += missed
    return out, lost


def _nearer_side(mine: np.ndarray, other: np.ndarray, reach: float) -> Any:
    """The half of the plane nearer to ``mine`` than to ``other``, as a square of side 2 ``reach`` cut by their bisector."""
    way = (other - mine) / np.hypot(*(other - mine))
    across = np.array([-way[1], way[0]])
    middle = 0.5 * (mine + other)
    corners = [middle + reach * across, middle - reach * across, middle - reach * across - reach * way, middle + reach * across - reach * way]
    return shapely.Polygon(corners)


def thiessen_shares(polygon: Any, gauges: np.ndarray) -> FloatArray:
    """The share of a polygon's area nearest to each gauge: exact, and summing to 1. Gauges on one spot leave it all to
    the one listed first, as :func:`nearest` does."""
    count = gauges.shape[0]
    whole = float(shapely.area(polygon))
    if whole <= 0.0:
        raise ValueError("a polygon with no area has no Thiessen shares")
    west, south, east, north = shapely.bounds(polygon)
    wide = max(east, float(gauges[:, 0].max())) - min(west, float(gauges[:, 0].min()))
    high = max(north, float(gauges[:, 1].max())) - min(south, float(gauges[:, 1].min()))
    reach = REACH * max(float(np.hypot(wide, high)), 1.0)
    areas = np.zeros(count)
    for g in range(count):
        part = polygon
        for h in range(count):
            if h == g:
                continue
            if np.array_equal(gauges[g], gauges[h]):
                part = shapely.Polygon() if h < g else part
                continue
            part = shapely.intersection(part, _nearer_side(gauges[g], gauges[h], reach))
            if shapely.is_empty(part):
                break
        areas[g] = float(shapely.area(part))
    return areas / areas.sum()


def polygon_points(polygon: Any, wanted: int) -> tuple[np.ndarray, np.ndarray]:
    """About ``wanted`` points on a square lattice inside a polygon; the polygon's own inner point if the lattice misses it."""
    west, south, east, north = shapely.bounds(polygon)
    step = float(np.sqrt(max(float(shapely.area(polygon)), 0.0) / wanted)) or 1.0
    xs = np.arange(west + 0.5 * step, east, step)
    ys = np.arange(south + 0.5 * step, north, step)
    gx, gy = np.meshgrid(xs, ys)
    inside = shapely.contains_xy(polygon, gx.ravel(), gy.ravel())
    if not inside.any():
        point = shapely.point_on_surface(polygon)
        return np.array([shapely.get_x(point)]), np.array([shapely.get_y(point)])
    return gx.ravel()[inside], gy.ravel()[inside]
