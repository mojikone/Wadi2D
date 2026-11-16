# Wadi2D. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The run's cell maps over the cells an aligned strip replaced (W86).

``maps/max_depth.tif`` and its fellows are written on the lattice, and the squares a strip replaced are outside the
lattice's mask: on Block 2's aligned mesh every wadi was blank in them, the one place the flood is. Here a replaced
square takes the value of the strip cell whose ring holds the square's centre, the usual rule for a polygon on a
raster, so the maps show the strip's own numbers at the lattice's cell size. The strip's own cells and faces stay in
``strip_mesh.gpkg``; the pixel maps read the strip at the terrain pixel.
"""

from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import rasterio

from wadi2d.io.geotiff import write_map

STRIP_FIELDS = {
    "max_depth": "strip_depth",
    "max_speed": "strip_speed",
    "hazard": "strip_hazard",
    "max_mean_depth": "strip_mean_depth",
}
"""The cell maps a strip has a value for, and that value's name among the strip's maxima. A strip keeps no
arrival time, so ``arrival`` stays blank on its cells."""
LEVEL = "max_level"


def strip_on_lattice(tables) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    """(rows, columns, strip cell) of the squares a strip replaced whose centre a strip cell's ring holds; None on a
    run without a strip."""
    from wadi2d.strips.tables import _owners_of

    strip = getattr(tables, "strip", None)
    if strip is None:
        return None
    rows, cols = (np.asarray(a) for a in strip.strip.masked)
    none = np.zeros(0, np.int64)
    if rows.size == 0 or strip.mesh.real == 0:
        return none, none, none
    grid, geo = tables.grid, strip.strip.geometry
    top, left = int(rows.min()), int(cols.min())
    shape = (int(rows.max()) - top + 1, int(cols.max()) - left + 1)
    # a raster whose pixels are the lattice's cells: a pixel's centre is a cell's centre
    owner = _owners_of(
        geo.ring_start, geo.ring_node, geo.x, geo.y, np.arange(strip.mesh.real), grid.x0 + left * grid.dx,
        grid.y0 - top * grid.dx, grid.dx, *shape, 0, 0, *shape,
    )  # fmt: skip
    cell = owner[rows - top, cols - left]
    held = cell >= 0
    return rows[held], cols[held], cell[held]


def paint_strip(maps: dict, strip_maxima: dict, where, zmin: np.ndarray) -> np.ndarray:
    """The strip's maxima written into the lattice ``maps`` (name: (data, valid)) at the squares of ``where``, in
    place; returns the mask of those squares, which a map then holds beside the lattice's own cells."""
    rows, cols, cell = where
    first = next(iter(maps.values()))[0]
    also = np.zeros(first.shape, bool)
    also[rows, cols] = True
    depth = np.asarray(strip_maxima["strip_depth"]).reshape(-1)[cell]
    for name, (data, valid) in maps.items():
        if name == LEVEL:
            data[rows, cols] = zmin[cell] + depth
            valid[rows, cols] = depth > 0.0
        elif name in STRIP_FIELDS and STRIP_FIELDS[name] in strip_maxima:
            data[rows, cols] = np.asarray(strip_maxima[STRIP_FIELDS[name]]).reshape(-1)[cell]
            if valid is not None:
                valid[rows, cols] = True
        elif valid is not None:
            valid[rows, cols] = False
    return also


def lattice_maps(fields: dict, zmin: np.ndarray) -> dict:
    """The cell maps of a run from its maxima, name: (data, valid): what ``maps/`` holds."""
    depth = fields["depth"]
    return {
        "max_depth": (depth.copy(), None),
        LEVEL: (zmin + depth, depth > 0.0),
        "max_speed": (fields["speed"].copy(), None),
        "hazard": (fields["hazard"].copy(), None),
        "arrival": (fields["arrival"].copy(), fields["arrival"] >= 0.0),
        "max_mean_depth": (fields["mean_depth"].copy(), None),
    }


FLOORED = ("max_depth", LEVEL, "max_speed", "hazard", "max_mean_depth")
"""The cell maps a depth floor empties where the cell never reached it (W101); the arrival has its own depth."""


def floored(maps: dict, floor: float | None) -> dict:
    """The cell maps with a cell whose largest depth stays under ``floor`` made invalid in the floored ones; the same
    maps when ``floor`` is None."""
    if floor is None:
        return maps
    dry = maps["max_depth"][0] < floor
    out = dict(maps)
    for name in FLOORED:
        if name in out:
            data, valid = out[name]
            out[name] = (data, ~dry if valid is None else (valid & ~dry))
    return out


def write_cell_maps(
    folder: Path, maps: dict, grid, crs, tags, also: np.ndarray | None = None, floor: float | None = None
) -> None:
    """``floor``: a cell whose largest depth stays under it is left out of the floored maps (W101,
    ``outputs.pixels.cell_depth_floor``); None keeps every cell, as before."""
    for name, (data, valid) in floored(maps, floor).items():
        if valid is None and also is not None and name not in STRIP_FIELDS:
            valid = ~also  # a map the strip has no value for stays blank on its cells
        write_map(folder / f"{name}.tif", data, grid, crs, valid, tags, also)


def remake_cell_maps(run: Path, tables, crs) -> int:
    """The cell maps of a finished run written again from its results, the strip's cells filled; the count of
    squares filled, 0 on a run without a strip (whose maps are left as they are)."""
    where = strip_on_lattice(tables)
    if where is None or where[0].size == 0:
        return 0
    with h5py.File(run / "results.h5", "r") as f:
        group = f["maxima"]
        if "strip_depth" not in group:
            return 0
        fields = {name: group[name][:] for name in ("depth", "speed", "hazard", "arrival", "mean_depth")}
        strip_maxima = {name: group[name][:] for name in group if name.startswith("strip_")}
    folder = run / "maps"
    tags = None
    if (folder / "max_depth.tif").is_file():
        with rasterio.open(folder / "max_depth.tif") as src:
            tags = src.tags() or None
    maps = lattice_maps(fields, tables.zmin)
    also = paint_strip(maps, strip_maxima, where, tables.strip.mesh.zmin)
    write_cell_maps(folder, maps, tables.grid, crs, tags, also)
    return int(where[0].size)


__all__ = ["floored", "lattice_maps", "paint_strip", "remake_cell_maps", "strip_on_lattice", "write_cell_maps"]
