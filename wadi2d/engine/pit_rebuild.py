"""What the build with the pit fills can take from the build before them (W91).

``terrain.fill_pits`` finds the pits on the tables of the job as given and builds the tables again with a ``fill`` for
every cell of every pit (W85). The fills are a few hundred cells of millions: on Block 2 the second build cost as much
as the first, 11 minutes of tables and 2.5 of strip. A fill raises pixels whose centre lies inside its cell's square
and nothing else, so of the second build only these change:

* the tiles whose pixel window holds a filled pixel (:func:`fill_tiles`); every other tile reads the same pixels
  through the same edits and gets the same slots, and the faces are closed again on the whole grid;
* the strip's tables, only when a fill lies within a strip cell's reach (:func:`strip_untouched`): its cells read
  the pixels under them, its faces the pixels along them and, for the local hydraulic radius, past their ends, its
  ghosts the tables of the squares beside it;
* never the strip's mesh: its lines are the job's crests and walls and the banks file's thalwegs, its floors the raw
  DEM's.

Each is the whole build's to the digit; ``tests/engine/test_pit_rebuild.py`` holds that against a whole build.

Interface: :func:`fills_follow`, :func:`fill_tiles`, :func:`strip_untouched`.
"""

from __future__ import annotations

import numpy as np
import shapely

from wadi2d.config.schema import RunConfig
from wadi2d.tables.builder import GridTables, tile_margin, tiles_reading
from wadi2d.terrain.pits import is_pit_fill

STRIP_PAD_CELLS = 3.0
"""How near a fill may come to a strip cell, in cells, before the strip's tables are built again, beyond the local
hydraulic radius's reach: a ghost is the square beside a cell, the strip's faces read their own line; one cell more
than either needs."""


def fills_follow(cfg: RunConfig) -> bool:
    """Whether a build of this job is the one before pit fills: they are asked for and not in the job yet."""
    return cfg.terrain.fill_pits and not any(is_pit_fill(o) for o in cfg.terrain.objects)


def _fill_bounds(cfg: RunConfig) -> np.ndarray:
    """(n, 4) of (xmin, ymin, xmax, ymax), one row per pit fill of the job."""
    rows = [shapely.Polygon(o.coordinates).bounds for o in cfg.terrain.objects if is_pit_fill(o)]
    return np.asarray(rows, np.float64).reshape(-1, 4)


def fill_tiles(cfg: RunConfig, base: GridTables | None, grid, bed) -> set[int] | None:
    """The tiles to build again on ``base``, the tables of this job before its fills; None when the whole grid must
    be built: no base, a base read from the cache (it holds no raw faces), another grid, or a job without fills."""
    if base is None or getattr(base, "raw", None) is None or getattr(grid, "quad", False):
        return None
    if base.grid.shape != grid.shape or not np.array_equal(base.grid.mask, grid.mask):
        return None
    bounds = _fill_bounds(cfg)
    if bounds.shape[0] == 0:
        return None
    p = bed.pixel
    k = round(grid.dx / p)
    # the pixels each fill can raise, a pixel more each way than its outline's box: the edit takes centres inside it
    c0 = np.floor((bounds[:, 0] - grid.x0) / p) - 1
    c1 = np.ceil((bounds[:, 2] - grid.x0) / p) + 1
    r0 = np.floor((grid.y0 - bounds[:, 3]) / p) - 1
    r1 = np.ceil((grid.y0 - bounds[:, 1]) / p) + 1
    boxes = np.stack((r0, c0, r1, c1), axis=1).astype(np.int64)
    return tiles_reading(grid, k, tile_margin(cfg.tables, bed), boxes)


def strip_untouched(cfg: RunConfig, base: GridTables | None, strip) -> bool:
    """Whether the strip's tables of ``base`` are this job's: the same mesh, and no pit fill near any of its cells."""
    held = getattr(base, "strip_mesh", None) if base is not None else None
    if held is None or held[1] is not strip or getattr(base, "strip", None) is None:
        return False
    bounds = _fill_bounds(cfg)
    if bounds.shape[0] == 0:
        return False  # no fills: nothing to take, and nothing here says the job is base's
    t = cfg.tables
    reach = t.local_radius_beta * t.face_depth_max if t.face_conveyance == "local_radius" else 0.0
    pad = reach + STRIP_PAD_CELLS * cfg.grid.dx
    geo = strip.geometry
    starts = np.asarray(geo.ring_start[:-1], np.int64)
    xs, ys = geo.x[geo.ring_node], geo.y[geo.ring_node]
    cells = shapely.box(
        np.minimum.reduceat(xs, starts), np.minimum.reduceat(ys, starts),
        np.maximum.reduceat(xs, starts), np.maximum.reduceat(ys, starts),
    )  # fmt: skip
    fills = shapely.box(bounds[:, 0], bounds[:, 1], bounds[:, 2], bounds[:, 3])
    near = shapely.STRtree(cells).query(fills, predicate="dwithin", distance=pad)
    return near.size == 0
