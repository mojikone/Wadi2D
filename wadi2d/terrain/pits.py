"""Pits of the ground as the cells hold it (W85): closed sinks, small in plan and deep.

A cell's table lets water stand below its lowest face invert, and water there can leave over no face: dead storage.
Where it is deep on a sliver of the plan, the step rule reads a depth no ground has: on Block 2 one hole of the
terrain model, 123 m deep and 15 m wide, set the time step of 35 of a run's 48 hours. A real pond or a dam's pool is
a sink too; it is large in plan, and that is the difference this reads.

How: the cells are a graph, a cell's lowest pixel its height, a face's invert the pass between two cells, the cells
on the domain's edge the outlets. The level at which each cell's water first reaches an outlet (its spill level) is
the smallest over all ways out of the highest pass on the way, found by one priority flood. A sink is the cells that
share a spill level across faces below it; it is a pit when its lowest point lies ``terrain.pit_min_depth`` below
that level and its water surface there covers less than ``terrain.pit_max_cells`` cells.

``terrain.pit_check`` names them before a run; ``terrain.fill_pits`` raises the pixels below the spill level in each
of a pit's cells to it, as ``fill`` terrain objects, so every reading of the ground takes the same edit. Uniform
grids only: a quadtree's tables are not read here.

Interface: :class:`Pit`, :func:`find_pits`, :func:`fill_objects`, :func:`without_fills`, :func:`pit_notes`,
:func:`write_pits`.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import shapely
from numba import njit

from wadi2d.config.schema import FILL_KIND, PIT_FILL_NAME, Terrain, TerrainObject
from wadi2d.solver.layout import CLOSED, TILE
from wadi2d.solver.state import plan_of
from wadi2d.tables.builder import GridTables, hbar_at_level

FILE = "terrain_checks.gpkg"
LAYER = "pits"
COLUMNS = {
    "depth_m": float,
    "area_m2": float,
    "volume_m3": float,
    "spill_m": float,
    "bottom_m": float,
    "cells": int,
    "filled": int,
}
MAX_LISTED = 5
"""Pits named one by one in a run's warnings, the deepest first; the rest are counted and lie in the layer."""
OPEN = 0.5 * CLOSED
"""A face invert under this is a face water can cross."""


@dataclass(frozen=True)
class Pit:
    """A small deep sink: its deepest cell, how far below its spill level its lowest point lies, its water surface and
    volume at that level, and its cells as (row, column) of the grid."""

    x: float
    y: float
    depth_m: float
    area_m2: float
    volume_m3: float
    spill_m: float
    bottom_m: float
    cells: tuple[tuple[int, int], ...]


@njit(cache=True)
def _spill(zmin, active, passx, passy):
    """The level at which each cell's water first reaches the domain's edge: a priority flood over cells and faces.

    ``passx[j, i]`` is the invert of the face between (j, i-1) and (j, i), ``passy[j, i]`` between (j-1, i) and (j, i),
    inf where no water crosses."""
    ny, nx = zmin.shape
    spill = np.full((ny, nx), np.inf)
    heap = [(0.0, 0) for _ in range(0)]
    for j in range(ny):
        for i in range(nx):
            if not active[j, i]:
                continue
            edge = j == 0 or i == 0 or j == ny - 1 or i == nx - 1
            if not edge:
                edge = not (active[j - 1, i] and active[j + 1, i] and active[j, i - 1] and active[j, i + 1])
            if edge:
                spill[j, i] = zmin[j, i]
                heapq.heappush(heap, (zmin[j, i], j * nx + i))
    while len(heap) > 0:
        level, c = heapq.heappop(heap)
        j, i = c // nx, c % nx
        if level > spill[j, i]:
            continue
        for side in range(4):
            if side == 0:
                jn, i_n, p = j, i - 1, passx[j, i]
            elif side == 1:
                jn, i_n = j, i + 1
                p = passx[j, i + 1] if i + 1 < nx else np.inf
            elif side == 2:
                jn, i_n, p = j - 1, i, passy[j, i]
            else:
                jn, i_n = j + 1, i
                p = passy[j + 1, i] if j + 1 < ny else np.inf
            if jn < 0 or i_n < 0 or jn >= ny or i_n >= nx or not active[jn, i_n] or p == np.inf:
                continue
            reach = max(level, p, zmin[jn, i_n])
            if reach < spill[jn, i_n]:
                spill[jn, i_n] = reach
                heapq.heappush(heap, (reach, jn * nx + i_n))
    return spill


@njit(cache=True)
def _sinks(spill, zmin, active, passx, passy, min_depth):
    """Label the sinks that hold a cell ``min_depth`` deep: the cells joined to it across faces below its spill level
    that share that level. Returns (label per cell, number of sinks)."""
    ny, nx = zmin.shape
    label = np.zeros((ny, nx), np.int32)
    stack = np.empty(ny * nx, np.int64)
    count = 0
    for j0 in range(ny):
        for i0 in range(nx):
            if not active[j0, i0] or label[j0, i0] != 0 or not spill[j0, i0] - zmin[j0, i0] >= min_depth:
                continue
            level = spill[j0, i0]
            if level == np.inf:
                continue
            count += 1
            label[j0, i0] = count
            stack[0] = j0 * nx + i0
            top = 1
            while top > 0:
                top -= 1
                j, i = stack[top] // nx, stack[top] % nx
                for side in range(4):
                    if side == 0:
                        jn, i_n, p = j, i - 1, passx[j, i]
                    elif side == 1:
                        jn, i_n = j, i + 1
                        p = passx[j, i + 1] if i + 1 < nx else np.inf
                    elif side == 2:
                        jn, i_n, p = j - 1, i, passy[j, i]
                    else:
                        jn, i_n = j + 1, i
                        p = passy[j + 1, i] if j + 1 < ny else np.inf
                    if jn < 0 or i_n < 0 or jn >= ny or i_n >= nx or p > level:
                        continue
                    if (
                        active[jn, i_n]
                        and label[jn, i_n] == 0
                        and spill[jn, i_n] == level
                        and zmin[jn, i_n] < level
                    ):
                        label[jn, i_n] = count
                        stack[top] = jn * nx + i_n
                        top += 1
    return label, count


def spill_levels(tables: GridTables) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(spill level per cell, pass of each west face, pass of each north face), absolute, inf where there is none."""
    grid = tables.grid
    zmin = np.asarray(tables.zmin, np.float64)
    passes = []
    for fr in (tables.frx, tables.fry):
        over = grid.from_tiles(np.asarray(fr[: grid.ntiles]), fill=CLOSED).astype(np.float64)
        passes.append(np.where(grid.mask & (over < OPEN), zmin + over, np.inf))
    return _spill(zmin, grid.mask, passes[0], passes[1]), passes[0], passes[1]


def find_pits(tables: GridTables, cfg: Terrain) -> list[Pit]:
    """The pits of the tables' ground, the deepest first; none on a quadtree, whose tables this does not read."""
    grid = tables.grid
    if getattr(grid, "quad", False):
        return []
    zmin = np.asarray(tables.zmin, np.float64)
    spill, passx, passy = spill_levels(tables)
    label, count = _sinks(spill, zmin, grid.mask, passx, passy, float(cfg.pit_min_depth))
    if count == 0:
        return []
    jj, ii = np.nonzero(label)
    which = label[jj, ii]
    level = spill[jj, ii]
    t = grid.tile_of[jj // TILE, ii // TILE]
    hc = np.asarray(tables.hc[t, jj % TILE, ii % TILE], np.float64)
    dtab = np.asarray(tables.dtab[t, jj % TILE, ii % TILE], np.float64)
    hbar = hbar_at_level(level, zmin[jj, ii], hc, dtab)
    cell = grid.dx * grid.dx
    area = np.bincount(which, plan_of(hbar, hc, dtab) * cell, count + 1)
    volume = np.bincount(which, hbar * cell, count + 1)
    order = np.argsort(which, kind="stable")
    cuts = np.searchsorted(which[order], np.arange(1, count + 2))
    pits = []
    for n in range(1, count + 1):
        if area[n] >= cfg.pit_max_cells * cell:
            continue
        mine = order[cuts[n - 1] : cuts[n]]
        deep = mine[int(np.argmin(zmin[jj[mine], ii[mine]]))]
        x, y = grid.xy_of(jj[deep], ii[deep])
        bottom = float(zmin[jj[deep], ii[deep]])
        cells = tuple((int(j), int(i)) for j, i in zip(jj[mine], ii[mine], strict=True))
        top = float(level[deep])
        pits.append(
            Pit(float(x), float(y), top - bottom, float(area[n]), float(volume[n]), top, bottom, cells)
        )
    return sorted(pits, key=lambda p: -p.depth_m)


def fill_objects(pits: list[Pit], tables: GridTables) -> list[TerrainObject]:
    """One ``fill`` per cell of every pit: the cell's square, raised to the pit's spill level. A pixel under that
    level in a cell of the sink can drain over no face, so nothing that drains is touched."""
    grid = tables.grid
    out = []
    for n, pit in enumerate(pits, 1):
        for m, (j, i) in enumerate(pit.cells, 1):
            west, north = grid.x0 + i * grid.dx, grid.y0 - j * grid.dx
            ring = [
                (west, north),
                (west + grid.dx, north),
                (west + grid.dx, north - grid.dx),
                (west, north - grid.dx),
            ]
            name = f"{PIT_FILL_NAME} {n}" if len(pit.cells) == 1 else f"{PIT_FILL_NAME} {n}.{m}"
            out.append(TerrainObject(kind=FILL_KIND, name=name, coordinates=ring, z_constant=pit.spill_m))
    return out


def is_pit_fill(obj: TerrainObject) -> bool:
    """A fill the engine made for a pit, as against one a job gave by hand."""
    return obj.kind == FILL_KIND and obj.name.startswith(PIT_FILL_NAME)


def without_fills(objects: list[TerrainObject]) -> list[TerrainObject]:
    """A job's own objects: the pit fills of an earlier resolve taken out, so resolving twice gives the same job."""
    return [o for o in objects if not is_pit_fill(o)]


def pit_notes(pits: list[Pit], filled: bool, dx: float) -> list[str]:
    """A run's warnings: the deepest pits by name, the rest counted."""
    if not pits:
        return []
    notes = []
    for p in pits[:MAX_LISTED]:
        what = "filled to its spill level" if filled else "water there can leave over no face"
        notes.append(
            f"a pit in the ground at ({p.x:.0f}, {p.y:.0f}): {p.depth_m:.1f} m deep below its spill level of "
            f"{p.spill_m:.2f} m, {p.area_m2:.0f} m2 of water surface there ({p.area_m2 / (dx * dx):.2f} cells), "
            f"{p.volume_m3:.0f} m3, in {len(p.cells)} cell{'s' if len(p.cells) != 1 else ''}: {what}"
        )
    more = len(pits) - MAX_LISTED
    total = sum(p.volume_m3 for p in pits)
    if filled:
        notes.append(
            f"{len(pits)} pits filled, {total:.0f} m3 in all (terrain.fill_pits); they lie in {FILE}"
        )
    else:
        rest = f"{more} more pits; " if more > 0 else ""
        notes.append(
            f"{rest}{len(pits)} pits hold {total:.0f} m3 of dead storage, see {FILE}. A hole of the terrain model stands "
            "like this, and deep water on a sliver of a cell can set the time step of the whole run: look at the "
            "ground there, and tick Fill pits (terrain.fill_pits) if they are not real"
        )
    return notes


def write_pits(out: Path, pits: list[Pit], crs: str, filled: bool) -> Path | None:
    """The pits as points in ``terrain_checks.gpkg``, an old file of an earlier run replaced; None when there are none
    and no file from before."""
    from wadi2d.io.geopackage import POINTS, VectorLayer, add_layer, write_geopackage

    path = out / FILE
    if not pits and not path.is_file():
        return None
    rows = [
        (round(p.depth_m, 2), round(p.area_m2, 1), round(p.volume_m3, 1), round(p.spill_m, 3), round(p.bottom_m, 3),
         len(p.cells), int(filled))
        for p in pits
    ]  # fmt: skip
    points = [shapely.Point(p.x, p.y) for p in pits]
    layer = VectorLayer(LAYER, COLUMNS, rows, points, POINTS)
    if path.is_file():  # in place: QGIS may hold the last run's file open
        add_layer(path, layer, crs)
    else:
        write_geopackage(path, [layer], crs)
    return path if pits else None
