"""A light time slider beside the full one: ``frames_light.nc``, safe to turn on in QGIS.

Usage: s14_light_slider.py <run number> ... The full ``frames.nc`` (``wadi2d frames``) holds every 15-min map on every
square cell of the domain (2.9 M cells, 193 frames, 2.3 GB for run 1) and none of the aligned cells. This file holds:
- every 4th saved map (hourly) and the last;
- only the cells whose maximum mean depth (water volume over cell area) reached 0.1 m (squares from
  ``maxima/mean_depth``, aligned cells from ``maxima/strip_mean_depth``): the flooded cells, not the rain sheet on the
  hills, whose depth above a steep cell's lowest pixel passes 0.1 m almost everywhere;
- the aligned (strip) cells too, as polygons of their own (``maps/strip_mesh.gpkg``), from the strip's own frames
  (``maps/<t>/strip_depth``, ``strip_speed``), so the wadis are not blank.
Depth, speed and hazard as in ``frames.nc`` (the same writer's names and rule: below the depth floor a cell is empty).
The format is the engine's (``wadi2d.products.time_slider``): CF UGRID through h5py, with up to N nodes per face.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import h5py
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from w79 import RUN_NAMES, RUNS  # noqa: E402

from wadi2d.config.schema import RunConfig  # noqa: E402
from wadi2d.products import time_slider as ts  # noqa: E402
from wadi2d.products.frames import frame_names  # noqa: E402
from wadi2d.products.hazard import classify  # noqa: E402

EVERY = 4
WET_M = 0.1
OUT_NAME = "frames_light.nc"


def squares(mask: np.ndarray, keep: np.ndarray, x0: float, y0: float, dx: float):
    rows, cols = np.nonzero(mask & keep)
    mesh = ts._mesh(rows, cols, np.ones(rows.size, np.int64), mask.shape, x0, y0, dx)
    return rows, cols, mesh.x, mesh.y, mesh.faces


def strip_polygons(folder: Path, keep_cells: np.ndarray):
    import geopandas as gpd
    import shapely

    cells = gpd.read_file(folder / "maps" / "strip_mesh.gpkg", layer="strip_cells", columns=["cell"])
    cells = cells[np.isin(cells["cell"].to_numpy(), keep_cells)]
    xs, ys, faces, order = [], [], [], []
    start = 0
    for cell, geom in zip(cells["cell"].to_numpy(), cells.geometry, strict=True):
        if geom.geom_type == "MultiPolygon":
            geom = max(geom.geoms, key=lambda g: g.area)
        geom = shapely.geometry.polygon.orient(geom, 1.0)  # counter-clockwise, as the squares
        ring = np.asarray(geom.exterior.coords)[:-1]
        xs.append(ring[:, 0])
        ys.append(ring[:, 1])
        faces.append(np.arange(start, start + len(ring)))
        start += len(ring)
        order.append(cell)
    return np.asarray(order), np.concatenate(xs), np.concatenate(ys), faces


def write(folder: Path) -> dict:
    t0 = time.time()
    cfg = RunConfig.model_validate_json((folder / "config.resolved.json").read_text(encoding="utf-8"))
    rule = cfg.outputs.pixels
    results = folder / "results.h5"
    names = frame_names(results)
    chosen = names[::EVERY] + ([names[-1]] if (len(names) - 1) % EVERY else [])
    with h5py.File(results, "r") as f:
        mask = f["mask"][:].astype(bool)
        x0, y0, dx = (float(f.attrs[k]) for k in ("x0", "y0", "dx"))
        crs = str(f.attrs.get("crs", ""))
        top = f["maxima"]["mean_depth"][:]
        strip_top = f["maxima"]["strip_mean_depth"][0] if "strip_mean_depth" in f["maxima"] else np.zeros(0)
    rows, cols, sx, sy, sfaces = squares(mask, top >= WET_M, x0, y0, dx)
    strip_cells = np.nonzero(strip_top >= WET_M)[0]
    order, px, py, pfaces = strip_polygons(folder, strip_cells) if strip_cells.size else (np.zeros(0, int), [], [], [])
    corners = max(4, max((len(p) for p in pfaces), default=4))
    n_sq, n_strip = sfaces.shape[0], len(pfaces)
    faces = np.full((n_sq + n_strip, corners), -1, np.int32)
    faces[:n_sq, :4] = sfaces
    base = sx.size
    for k, p in enumerate(pfaces):
        faces[n_sq + k, : len(p)] = p + base
    x = np.concatenate([sx, px]) if n_strip else sx
    y = np.concatenate([sy, py]) if n_strip else sy
    every = np.arange(faces.shape[0])  # the file's face count: the squares, then the aligned cells
    mesh = ts.CellMesh(every, every, x, y, faces)
    path = folder / OUT_NAME
    tmp = folder / "frames_light.tmp.nc"
    tmp.unlink(missing_ok=True)
    original = ts.CORNER_DIM
    _create_with_corners(tmp, mesh, ts.frame_seconds(chosen), crs, corners)
    with h5py.File(results, "r") as src, h5py.File(tmp, "r+", libver="earliest") as f:
        for index, name in enumerate(chosen):
            group = src["maps"][name]
            d = group["depth"][:][rows, cols].astype(np.float32)
            s = group["speed"][:][rows, cols].astype(np.float32)
            if n_strip and "strip_depth" in group:
                d = np.concatenate([d, group["strip_depth"][0][order].astype(np.float32)])
                s = np.concatenate([s, group["strip_speed"][0][order].astype(np.float32)])
            elif n_strip:
                d = np.concatenate([d, np.zeros(n_strip, np.float32)])
                s = np.concatenate([s, np.zeros(n_strip, np.float32)])
            hazard = classify(d, s, d * s, rule).astype(np.float32)
            dry = d < rule.depth_floor
            for key, values in (("depth", d), ("speed", s), ("hazard", hazard)):
                f[key][index, :] = np.where(dry, ts.FILL, values)
    tmp.replace(path)
    assert ts.CORNER_DIM == original
    full = folder / ts.FRAMES_FILE
    return {"file": str(path), "bytes": path.stat().st_size, "frames": len(chosen), "squares": int(n_sq),
            "aligned_cells": int(n_strip), "max_nodes": int(corners), "write_s": round(time.time() - t0, 1),
            "full_file_bytes": full.stat().st_size if full.is_file() else None, "full_frames": len(names),
            "full_cells": int(mask.sum())}


def _create_with_corners(path: Path, mesh, times, crs: str, corners: int) -> None:
    """The engine's ``_create`` with as many corners per face as the widest aligned cell has."""
    real = ts._dimension

    def dimension(f, name, size):
        return real(f, name, corners if name == ts.CORNER_DIM else size)

    ts._dimension = dimension
    try:
        ts._create(path, mesh, times, crs)
    finally:
        ts._dimension = real


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        report = write(RUNS / RUN_NAMES[int(arg)])
        (RUNS / RUN_NAMES[int(arg)] / "frames_light.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
        print(json.dumps(report))
