"""Pour points: where the user wants a subbasin to end.

Three sources, in the order a shared pixel is settled: the dams of the job (crest lines), a point layer, the design lines
and points of the job. A line lands on the pixel of largest drainage area it touches, the wadi it crosses. A point moves to
the nearest stream pixel within ``snap_m``, as Jenson snapping does; with no stream that near it takes the largest drainage
area in reach, and a stream is forced from there down.

Interface: :class:`PourPoint`, :func:`gather`, :func:`crossing`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import shapely

from wadi2d.basin.delineate import Surface
from wadi2d.basin.kernels import NONE
from wadi2d.config.schema import BasinSettings, RunConfig
from wadi2d.terrain.vector import read_features

KIND_DAM, KIND_LAYER, KIND_LINE, KIND_POINT = "dam", "layer", "design_line", "design_point"
NAME_FIELDS = ("name", "Name", "NAME")


@dataclass
class PourPoint:
    """A pixel the network must break at."""

    name: str
    kind: str
    pixel: int
    x: float
    y: float
    aliases: list[str] = field(default_factory=list)


def crossing(surface: Surface, coordinates: list[tuple[float, float]]) -> int:
    """The pixel of largest drainage area on a line, NONE off the ground."""
    pixels = surface.line_pixels(coordinates)
    return NONE if pixels.size == 0 else int(pixels[np.argmax(surface.count[pixels])])


def stream_limit(surface: Surface, settings: BasinSettings) -> float | None:
    """The drainage area that makes a stream, pixels; None when streams start at pour points only."""
    threshold = settings.stream_threshold_km2
    return None if threshold is None else threshold / surface.km2_per_pixel


def _within(surface: Surface, pixel: int, radius: float) -> np.ndarray:
    """Flat pixels on ground within ``radius`` of a pixel, nearest first."""
    reach = int(np.ceil(radius / surface.pixel))
    ny, nx = surface.shape
    row, col = divmod(pixel, nx)
    rows, cols = np.mgrid[
        max(row - reach, 0) : min(row + reach + 1, ny), max(col - reach, 0) : min(col + reach + 1, nx)
    ]
    rows, cols = rows.ravel(), cols.ravel()
    squared = (rows - row) ** 2 + (cols - col) ** 2
    kept = (squared * surface.pixel**2 <= radius**2) & surface.valid[rows * nx + cols]
    nearest = np.argsort(squared[kept], kind="stable")
    return (rows[kept] * nx + cols[kept])[nearest]


def snapped(surface: Surface, x: float, y: float, settings: BasinSettings) -> int:
    """Where a point lands; NONE off the ground."""
    pixel = surface.flat(x, y)
    if pixel == NONE:
        return NONE
    near = _within(surface, pixel, settings.snap_m)
    if near.size == 0:
        return NONE
    limit = stream_limit(surface, settings)
    if limit is not None:
        on_stream = near[surface.count[near] >= limit]
        if on_stream.size:
            return int(on_stream[0])
    return int(near[np.argmax(surface.count[near])])


def _is_ring(coordinates: list[tuple[float, float]]) -> bool:
    return shapely.LineString(coordinates).is_ring


def _dams(cfg: RunConfig, surface: Surface, settings: BasinSettings, notes: list[str]) -> list[PourPoint]:
    """Crest lines across a stream. One that crosses none, a saddle dam, makes no node and is reported."""
    threshold = settings.stream_threshold_km2 or settings.min_subbasin_km2
    found: list[PourPoint] = []
    dams = [o for o in cfg.terrain.objects if o.kind == "crest_line"]
    for index, obj in enumerate(dams, 1):
        name = obj.name or f"Dam{index}"
        pixel = crossing(surface, obj.coordinates)
        if pixel == NONE:
            notes.append(f"crest line {name} is off the ground: no node")
        elif surface.count[pixel] * surface.km2_per_pixel < threshold:
            notes.append(
                f"crest line {name} crosses no stream of {threshold:g} km2: no node, add a pour point if wanted"
            )
        else:
            found.append(PourPoint(name, KIND_DAM, pixel, *map(float, surface.xy(pixel))))
    return found


def _layer(path: str | Path, surface: Surface, settings: BasinSettings, notes: list[str]) -> list[PourPoint]:
    """A point layer; a feature's ``name`` field names its junction."""
    found: list[PourPoint] = []
    for index, (properties, shape) in enumerate(read_features(path, surface.crs), 1):
        name = next((str(properties[key]) for key in NAME_FIELDS if properties.get(key)), f"P{index}")
        for point in shapely.get_parts(shape):
            pixel = snapped(surface, point.x, point.y, settings)
            if pixel == NONE:
                notes.append(f"pour point {name} is off the ground: dropped")
            else:
                found.append(PourPoint(name, KIND_LAYER, pixel, point.x, point.y))
    return found


def _design(cfg: RunConfig, surface: Surface, settings: BasinSettings, notes: list[str]) -> list[PourPoint]:
    """Design lines and points of the job. A closed line is a ring round a catchment, not a section across a wadi."""
    found: list[PourPoint] = []
    for line in cfg.outputs.lines:
        if _is_ring(line.coordinates):
            notes.append(f"design line {line.name} is closed: not a pour point")
            continue
        pixel = crossing(surface, line.coordinates)
        if pixel == NONE:
            notes.append(f"design line {line.name} is off the ground: dropped")
        else:
            found.append(PourPoint(line.name, KIND_LINE, pixel, *map(float, surface.xy(pixel))))
    for point in cfg.outputs.points:
        pixel = snapped(surface, point.x, point.y, settings)
        if pixel == NONE:
            notes.append(f"design point {point.name} is off the ground: dropped")
        else:
            found.append(PourPoint(point.name, KIND_POINT, pixel, point.x, point.y))
    return found


def gather(
    cfg: RunConfig, surface: Surface, settings: BasinSettings, layer: str | Path | None, notes: list[str]
) -> dict[int, PourPoint]:
    """Every pour point by pixel; one landing on a pixel already held becomes an alias there."""
    found = _dams(cfg, surface, settings, notes)
    if layer is not None:
        found += _layer(layer, surface, settings, notes)
    found += _design(cfg, surface, settings, notes)
    points: dict[int, PourPoint] = {}
    for point in found:
        held = points.get(point.pixel)
        if held is None:
            points[point.pixel] = point
        elif point.name != held.name:
            held.aliases.append(point.name)
    return points
