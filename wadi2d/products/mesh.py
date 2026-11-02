"""The pixel maps of a run on a mesh: one pass per cell size, joined so the surface does not jump at a level interface.

A coarse cell is one body of water: spreading its mean depth over the fine raster cells it paints would hold that depth
on every part of it, the bank included. So each size keeps its own cells, at its own pixels per cell, and fills each cell
with the water that cell holds, as :mod:`wadi2d.products.pixels` does on a uniform grid.

The join is in the corners. Each size works on a lattice of its own cell size, and the cells around its own that belong
to other sizes stand in as ghosts. A finer neighbour stands in as the mean of its cells. A coarser one stands in through
its own sloped surface, read at the ghost's centre, which is why the passes run from coarse to fine. A plain copy of the
coarse level would sit a quarter of a fine cell of slope off, and draw a step along every interface. On a plane both sides
then read the same line, and a face between two sizes is linked by the ground of the fine faces along it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage

from wadi2d.config.constants import M2_PER_KM2
from wadi2d.config.schema import Pixels, RunConfig
from wadi2d.grid.quad import QuadGrid
from wadi2d.io.geotiff import raster_profile, write_band
from wadi2d.products.ground import CellPixels, read_cells
from wadi2d.products.hazard import DRY, class_names, classify
from wadi2d.products.pixels import PixelMaxima, to_host
from wadi2d.solver.layout import CLOSED, TILE, TILE2
from wadi2d.tables import GridTables

INSIDE = -np.inf
"""The sill of a line inside one coarse cell: there is no face there, and no ground to hold water apart."""


def _sill(zmin, over):
    return np.where(over >= CLOSED, np.inf, zmin + over)


def mesh_sills(tables: GridTables, datum: float) -> tuple[np.ndarray, np.ndarray]:
    """The ground of every west and north face on the finest raster, over ``datum``; a closed face is infinitely high.

    Lines inside a coarse cell hold ``INSIDE``. The closed side of a coarse tile takes its fine faces, which is where the
    water really crosses; east and south ones sit in the extra table tiles.
    """
    grid: QuadGrid = tables.grid
    zmin = grid.to_tiles(tables.zmin, np.float64) - datum
    west = np.full(grid.shape, INSIDE, np.float64)
    north = west.copy()
    for t in range(1, grid.ntiles):
        size = 1 << int(grid.level[t])
        y, x = int(grid.tiles[t, 0]) * TILE, int(grid.tiles[t, 1]) * TILE
        span = TILE * size
        west[y : y + span, x : x + span : size] = np.repeat(_sill(zmin[t], tables.frx[t]), size, axis=0)
        north[y : y + span : size, x : x + span] = np.repeat(_sill(zmin[t], tables.fry[t]), size, axis=1)
    for row in grid.interfaces[
        grid.interfaces[:, 1] >= 2
    ]:  # a west or north one is the fine tile's own, written above
        t, side, coarse, base = int(row[0]), int(row[1]), int(row[2]), int(row[5])
        y, x = int(grid.tiles[t, 0]) * TILE, int(grid.tiles[t, 1]) * TILE
        at = (base // TILE2, (base % TILE2) // TILE)
        cells = int(row[4]) + np.arange(TILE) // 2
        if side == 2:
            west[y : y + TILE, x + TILE] = _sill(zmin[coarse][cells, 0], tables.frx[at])
        else:
            north[y + TILE, x : x + TILE] = _sill(zmin[coarse][0, cells], tables.fry[at])
    return west.astype(np.float32), north.astype(np.float32)


def halved(a: np.ndarray) -> np.ndarray:
    """Sum over squares of two."""
    ny, nx = a.shape[0] // 2, a.shape[1] // 2
    return a.reshape(ny, 2, nx, 2).sum(axis=(1, 3))


def pyramid(a: np.ndarray, top: int) -> list[np.ndarray]:
    """``a``, then its sums over squares of two, four, ...; float64, so a mean of equal values gives that value."""
    out = [a.astype(np.float64)]
    for _ in range(top):
        out.append(halved(out[-1]))
    return out


def sill_lattice(sill: np.ndarray, s: int, axis: int) -> np.ndarray:
    """The lowest ground along each west (axis 1) or north (axis 0) side of a lattice of cells 2^s wide."""
    size = 1 << s
    if s == 0:
        return sill
    if axis == 1:
        edges = sill[:, ::size]
        return edges.reshape(edges.shape[0] // size, size, edges.shape[1]).min(axis=1)
    edges = sill[::size, :]
    return edges.reshape(edges.shape[0], edges.shape[1] // size, size).min(axis=2)


@dataclass
class Pass:
    """One cell size."""

    s: int
    cells: CellPixels
    maxima: PixelMaxima
    coarser: list[tuple[np.ndarray, np.ndarray, int, np.ndarray, np.ndarray, np.ndarray]]
    """Per coarser size: ghost rows and columns, that size, the owner's place in that pass, and the weights' fractions."""


def own_cells(size_raster: np.ndarray, keep: np.ndarray, s: int) -> np.ndarray:
    """The kept cells of size ``s`` on the lattice of that size."""
    step = 1 << s
    return (size_raster[::step, ::step] == s) & keep[::step, ::step]


class MeshMaxima:
    """Owns one ``PixelMaxima`` per cell size; maps arrive painted on the finest raster."""

    def __init__(
        self, xp, grid: QuadGrid, parts: dict[int, CellPixels], keep, zmin, sills, rule: Pixels
    ) -> None:
        self.xp, self.rule, self.grid = xp, rule, grid
        self.top = int(grid.level.max())
        self.keep = keep
        self.zmin = zmin
        size = np.broadcast_to(grid.level[:, None, None], (grid.ntiles, TILE, TILE))
        self.size = grid.from_tiles(size.astype(np.int32), -1)
        self.index = {s: self._places(part, s) for s, part in parts.items()}
        self.passes: dict[int, Pass] = {}
        any_kept = pyramid(keep, self.top)
        for s in sorted(parts, reverse=True):
            self.passes[s] = self._build(s, parts[s], any_kept[s] > 0.0, sills)

    def _places(self, part: CellPixels, s: int) -> np.ndarray:
        step = 1 << s
        place = np.full((self.keep.shape[0] // step, self.keep.shape[1] // step), -1, np.int32)
        place[part.rows, part.cols] = np.arange(part.rows.size, dtype=np.int32)
        return place

    def _build(self, s: int, part: CellPixels, any_kept: np.ndarray, sills) -> Pass:
        step = 1 << s
        own = own_cells(self.size, self.keep, s)
        ring = ndimage.binary_dilation(own, structure=np.ones((3, 3), bool)) & ~own & any_kept
        rows, cols = np.nonzero(ring)
        owner = self.size[rows * step, cols * step]
        coarser = []
        for t in sorted({int(v) for v in owner if v > s}):
            pick = owner == t
            scale = 1 << (t - s)
            r, c = rows[pick], cols[pick]
            place = self.index[t][r // scale, c // scale]
            fy = ((r % scale) + 0.5) / scale
            fx = ((c % scale) + 0.5) / scale
            good = place >= 0
            coarser.append((r[good], c[good], t, place[good], fy[good], fx[good]))
        sx, sy = sill_lattice(sills[0], s, 1), sill_lattice(sills[1], s, 0)
        shape = own.shape
        zeros = np.zeros(shape, np.float32)
        maxima = PixelMaxima(self.xp, part, zeros, sx, sy, own | ring, self.rule, ghosts=(rows, cols))
        return Pass(s, part, maxima, coarser)

    def _ghosts(self, p: Pass, level: np.ndarray, speed: np.ndarray, offsets: np.ndarray) -> None:
        """A coarser neighbour, read through its own surface at the ghost's centre, with its fill offset as it stands."""
        for r, c, t, place, fy, fx in p.coarser:
            done = self.passes[t].maxima
            offsets[r, c] = to_host(done.offset[place])
            weights = ((1 - fy) * (1 - fx), (1 - fy) * fx, fy * (1 - fx), fy * fx)
            for target, corners in ((level, done.corners[0]), (speed, done.corners[1])):
                values = [to_host(corner[place]) for corner in corners]
                target[r, c] = sum(w * v for w, v in zip(weights, values, strict=True))

    def add(self, depth, mean_depth, speed, moment: bool = True) -> None:
        """One map, painted on the finest raster."""
        wet = (depth > 0.0) & self.keep
        water = wet.astype(np.float64)
        sum_wet = pyramid(water, self.top)
        sum_level = pyramid((self.zmin + depth) * water, self.top)
        sum_depth = pyramid(depth * water, self.top)
        sum_mean = pyramid(mean_depth * self.keep, self.top)
        sum_speed = pyramid(speed * self.keep, self.top)
        for s in sorted(self.passes, reverse=True):
            count = float(1 << (2 * s))
            held = np.maximum(sum_wet[s], 1.0)
            level = (sum_level[s] / held).astype(np.float32)
            d = (sum_depth[s] / held).astype(np.float32)
            h = (sum_mean[s] / count).astype(np.float32)
            v = (sum_speed[s] / count).astype(np.float32)
            p = self.passes[s]
            offsets = np.full(level.shape, np.nan, np.float32)  # a finer neighbour runs later: its offset is not known
            self._ghosts(p, level, v, offsets)
            p.maxima.add(d, h, v, moment, level=level, offsets=offsets)

    def lift_dv(self, run_hazard) -> None:
        sums = pyramid(run_hazard, self.top)
        for s, p in self.passes.items():
            p.maxima.lift_dv((sums[s] / float(1 << (2 * s))).astype(np.float32))

    def result(self) -> dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]]:
        return {s: p.maxima.result() for s, p in self.passes.items()}


@dataclass
class MeshResult:
    """Per cell size, its cells and its (cells, pixels) values."""

    cells: dict[int, CellPixels]
    classes: dict[int, np.ndarray]
    depth: dict[int, np.ndarray]
    speed: dict[int, np.ndarray]
    dv: dict[int, np.ndarray]
    maps: int

    @property
    def kept(self) -> int:
        return sum(part.rows.size for part in self.cells.values())

    @property
    def pixel(self) -> float:
        return next(iter(self.cells.values())).pixel


def read_parts(cfg: RunConfig, tables: GridTables, keep: np.ndarray, tick) -> dict[int, CellPixels]:
    """The pixels of the kept cells, size by size; one datum, or the surfaces would not meet."""
    grid: QuadGrid = tables.grid
    size = grid.from_tiles(
        np.broadcast_to(grid.level[:, None, None], (grid.ntiles, TILE, TILE)).astype(np.int32), -1
    )
    datum = float(tables.zmin[keep].min()) if keep.any() else 0.0
    parts = {}
    for s in range(int(grid.level.max()) + 1):
        own = own_cells(size, keep, s)
        if own.any():
            parts[s] = read_cells(cfg, tables, own, tick, 1 << s, datum)
    return parts


def spread(parts: dict[int, CellPixels], values: dict[int, np.ndarray], fill: float, dtype) -> np.ndarray:
    """Cells of every size as one raster at the common pixel, over the kept cells' bounding box."""
    box = _box(parts)
    out = np.full((box[1] - box[0], box[3] - box[2]), fill, dtype)
    for s, part in parts.items():
        k = part.k
        down, across = np.meshgrid(np.arange(k), np.arange(k), indexing="ij")
        rows = (part.rows * k - box[0])[:, None] + down.ravel()[None, :]
        cols = (part.cols * k - box[2])[:, None] + across.ravel()[None, :]
        out[rows, cols] = values[s]
    return out


def _box(parts: dict[int, CellPixels]) -> tuple[int, int, int, int]:
    """(top, bottom, left, right) of the kept cells, in pixels from the grid origin."""
    top = min(int(p.rows.min()) * p.k for p in parts.values())
    bottom = max((int(p.rows.max()) + 1) * p.k for p in parts.values())
    left = min(int(p.cols.min()) * p.k for p in parts.values())
    right = max((int(p.cols.max()) + 1) * p.k for p in parts.values())
    return top, bottom, left, right


def write_mesh_pixels(cfg, tables, crs, found: MeshResult, folder, tags, files: dict[str, str]) -> dict:
    """The rasters of record and the statistics, as ``write_pixels`` writes them."""
    rule = cfg.outputs.pixels
    grid = tables.grid
    box = _box(found.cells)
    pixel = found.pixel
    x0, y0 = grid.x0 + box[2] * pixel, grid.y0 - box[0] * pixel
    classes = spread(found.cells, found.classes, DRY, np.uint8)
    profile = raster_profile(classes.shape, pixel, x0, y0, crs)
    write_band(folder / files["hazard"], classes, profile, DRY, tags)
    nothing = files["nodata"]
    for name, values in (
        (files["depth"], found.depth),
        (files["speed"], found.speed),
        (files["dv"], found.dv),
    ):
        marked = {s: np.where(found.classes[s] > DRY, v, nothing) for s, v in values.items()}
        write_band(folder / name, spread(found.cells, marked, nothing, np.float32), profile, nothing, tags)
    km2 = pixel**2 / M2_PER_KM2
    highest = {
        name: max(float(v.max(initial=0.0)) for v in values.values())
        for name, values in (("depth", found.depth), ("speed", found.speed), ("dv", found.dv))
    }
    stats = {
        "class_km2": {
            name: round(float((classes == k + 1).sum()) * km2, 4) for k, name in enumerate(class_names(rule))
        },
        "maps": found.maps,
        "kept_cells": found.kept,
        "pixel_m": pixel,
        "limits": rule.hazard_limits,
        "depth_floor_m": rule.depth_floor,
        "depth_max_m": highest["depth"],
        "speed_max_ms": highest["speed"],
        "dv_max_m2s": highest["dv"],
        "origin": [x0, y0],
        "cell_sizes_m": sorted(grid.dx * (1 << s) for s in found.cells),
    }
    return {"stats": stats, "classes": classes, "profile": profile}


def classes_of(depth, speed, dv, rule: Pixels) -> dict[int, np.ndarray]:
    return {s: classify(depth[s], speed[s], dv[s], rule) for s in depth}


__all__ = [
    "MeshMaxima",
    "MeshResult",
    "classes_of",
    "mesh_sills",
    "read_parts",
    "spread",
    "write_mesh_pixels",
]
