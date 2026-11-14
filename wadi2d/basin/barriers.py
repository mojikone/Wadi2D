"""Walls and burn lines in the delineation (W73): the job's terrain objects with ``delineate`` on edit the ground the
basin generator reads, as HEC-HMS's terrain reconditioning does, and nothing else.

Two kinds of edit, settled at the analysis pixel:

- a **cut** lowers a pixel: a burn line to its invert or by its depth, a channel to its section. Cuts go in before the
  least-cost breach, so the breach follows them.
- a **raise** lifts a pixel: a wall to its own top (or the ground plus ``basin.wall_raise_m``), a crest line to its
  crest, an embankment or a dyke to its built ground. Raises go in after the breach, because WhiteboxTools' least-cost
  breach would cut through a wall closing a depression; the depressions a raise closes are filled instead, and the D8
  lines are taken on the filled ground.

A wall is the 4-connected line of pixels it touches, so no D8 step slips between two corner pixels. A pixel any object
cuts is never raised: where a burn line crosses a wall the burn wins, as in HMS. The DEM file is only read.

Interface: :class:`GroundEdits`, :func:`ground_edits`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

import numpy as np
import shapely
from rasterio import features
from rasterio.transform import Affine

from wadi2d.config.schema import SHAPED_KINDS, BasinSettings, RunConfig, TerrainObject
from wadi2d.terrain.crest import elevations_along
from wadi2d.terrain.earthworks import Shape, ShapeEdit
from wadi2d.terrain.objects import BurnLine

RAISED_KINDS = ("wall", "crest_line")


@dataclass
class GroundEdits:
    """What the objects do to the analysis raster; None where no object does it."""

    cut: np.ndarray | None = None
    """Ground after every cut, m; NaN off the ground."""
    raised: np.ndarray | None = None
    """The level a pixel is raised to, m; NaN where nothing raises it."""
    names: list[str] = field(default_factory=list)
    """The objects applied, in job order."""

    @property
    def empty(self) -> bool:
        return self.cut is None and self.raised is None


def _four_connected(mask: np.ndarray) -> np.ndarray:
    """Close every diagonal step of a line with one of its corner pixels, so D8 cannot pass between them."""
    out = mask.copy()
    a, b = out[:-1, :-1], out[1:, 1:]
    c, d = out[:-1, 1:], out[1:, :-1]
    leak = a & b & ~c & ~d
    out[:-1, 1:] |= leak
    leak = c & d & ~out[:-1, :-1] & ~out[1:, 1:]
    out[:-1, :-1] |= leak
    return out


def _line_pixels(obj: TerrainObject, shape: tuple[int, int], x0: float, y0: float, pixel: float):
    """Rows and columns of the 4-connected line of pixels under an object, and their stations along it."""
    line = shapely.LineString(obj.coordinates)
    ny, nx = shape
    xmin, ymin, xmax, ymax = line.bounds
    col0 = max(int(np.floor((xmin - x0) / pixel)) - 1, 0)
    row0 = max(int(np.floor((y0 - ymax) / pixel)) - 1, 0)
    col1 = min(int(np.floor((xmax - x0) / pixel)) + 2, nx)
    row1 = min(int(np.floor((y0 - ymin) / pixel)) + 2, ny)
    if col1 <= col0 or row1 <= row0:
        return np.empty(0, np.int64), np.empty(0, np.int64), np.empty(0)
    hit = features.rasterize(
        [line],
        out_shape=(row1 - row0, col1 - col0),
        transform=Affine(pixel, 0.0, x0 + col0 * pixel, 0.0, -pixel, y0 - row0 * pixel),
        all_touched=True,
        dtype=np.uint8,
    ).astype(bool)
    rows, cols = np.nonzero(_four_connected(hit))
    rows, cols = rows + row0, cols + col0
    s = shapely.line_locate_point(line, shapely.points(x0 + (cols + 0.5) * pixel, y0 - (rows + 0.5) * pixel))
    return rows, cols, np.asarray(s, dtype=np.float64)


def _raise_line(
    obj: TerrainObject, z: np.ndarray, raised: np.ndarray, x0: float, y0: float, pixel: float, lift: float
) -> None:
    rows, cols, s = _line_pixels(obj, z.shape, x0, y0, pixel)
    ground = z[rows, cols]
    on = np.isfinite(ground)
    rows, cols, s, ground = rows[on], cols[on], s[on], ground[on]
    if obj.z is None and obj.z_constant is None:
        level = ground + lift
    else:
        level = np.maximum(elevations_along(obj.coordinates, obj.z, obj.z_constant, s), ground)
    raised[rows, cols] = np.fmax(raised[rows, cols], level)


def _edited(obj: TerrainObject, z: np.ndarray, x0: float, y0: float, pixel: float, cfg: RunConfig) -> np.ndarray:
    """The ground with one pixel edit of the 2D's own applied."""
    grid = SimpleNamespace(x0=x0, y0=y0)
    if obj.kind == "burn_line":
        edit = BurnLine().pixels(obj, grid, pixel, cfg.terrain)
    else:
        edit = ShapeEdit(Shape.of(obj), grid, pixel)
    ground = np.isfinite(z)
    work = np.where(ground, z, np.nanmean(z))
    edit(work, 0, 0)
    return np.where(ground, work, np.nan)


def ground_edits(
    cfg: RunConfig, z: np.ndarray, pixel: float, x0: float, y0: float, settings: BasinSettings, notes: list[str]
) -> GroundEdits:
    """The cuts and raises of every object of the job that delineates."""
    objects = [o for o in cfg.terrain.objects if o.delineates]
    if not objects:
        return GroundEdits()
    cut = z.copy()
    raised = np.full(z.shape, np.nan)
    names: list[str] = []
    for index, obj in enumerate(objects, 1):
        name = obj.name or f"{obj.kind} {index}"
        before_raise, before_cut = np.isfinite(raised).sum(), np.count_nonzero(cut < z)
        if obj.kind in RAISED_KINDS:
            _raise_line(obj, z, raised, x0, y0, pixel, settings.wall_raise_m)
        elif obj.kind == "burn_line" or obj.kind in SHAPED_KINDS:
            edited = _edited(obj, z, x0, y0, pixel, cfg)
            cut = np.fmin(cut, edited)
            up = edited > z
            raised[up] = np.fmax(raised[up], edited[up])
        if np.isfinite(raised).sum() == before_raise and np.count_nonzero(cut < z) == before_cut:
            notes.append(f"{name} ({obj.kind}) is ticked for delineation but touches no pixel of the analysis raster")
        names.append(name)
    lowered = cut < z
    raised[lowered] = np.nan  # a burn wins over a wall
    has_cut, has_raise = bool(lowered.any()), bool(np.isfinite(raised).any())
    notes.append(f"delineated with {', '.join(names)} applied to the ground (W73)")
    return GroundEdits(cut if has_cut else None, raised if has_raise else None, names)
