"""A dam's pool on the grid as an element of record (W106, gap 8 of W104): its inflow by the pool's own balance and its
outflow over the crest, so that a run with the dams as 2D pools lines up, dam by dam, with one whose dams are lumped
reservoirs.

The pool is W79's and W104's: the ground under the dam's crest + ``ABOVE_CREST_M`` behind its crest lines, read on the
DEM at ``PIXEL_M``, the side that is held (it does not reach the window's edge, which widens until it does not), widened
by ``WIDEN_M``. Its water at every saved map is the squares' mean depth times their area plus each aligned cell's by its
centroid. The outflow is the result line named as the dam (W1's line along the crest); with none, the record says so
and the inflow is the change of the water alone. The inflow over an interval between two maps is the change of the water
plus the outflow between them, over the interval: a mean over the map interval, 15 min on Block 2.

A dam a lumped reservoir of the same name routes in the run (``series/network_<dam>.csv``) is the reservoir's, not a
pool's, and is left out. Nothing here changes the run.

Interface: :func:`pool_records`, :data:`POOL_KIND`, :data:`FILE`.
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
from pathlib import Path

import numpy as np
import shapely
from scipy import ndimage

from wadi2d.io.results import safe_name, write_series_csv

POOL_KIND = "pool"
"""``series/pool_<dam>.csv``: t_s (the end of each map interval), inflow_m3s, outflow_m3s, storage_m3."""
FILE = "pools.json"
DAM_KINDS = ("crest_line", "embankment")
ABOVE_CREST_M = 0.3
WIDEN_M = 60.0
PIXEL_M = 5.0
WINDOW_M = (3000.0, 12000.0)
"""The first and the widest half-size of the window round a dam's lines, m: a reservoir held within 24 km."""
WALL_M = 6.0


PART = re.compile(r"\s+part\s+\d+$", re.IGNORECASE)
"""A dam drawn in pieces names them "<dam> part 2" and so on (W79, W104): one dam, one pool."""


def _dams(cfg) -> dict[str, list]:
    """The named dams of the job: crest lines and embankments with a spillway within ``basin.dam_join_m`` (the
    generated basin's own test of a dam) or a result line of the same name (its outflow). A road or a dyke drawn as a
    crest line, or Suggest's crests, have neither and make no pool."""
    from wadi2d.basin.reservoirs import spillways_of

    found: dict[str, list] = {}
    for obj in cfg.terrain.objects:
        if obj.kind in DAM_KINDS and obj.name:
            found.setdefault(PART.sub("", obj.name.strip()), []).append(obj)
    lines = {line.name for line in cfg.outputs.lines}
    return {
        name: pieces for name, pieces in found.items()
        if name in lines or any(spillways_of(piece, cfg, cfg.basin) for piece in pieces)
    }  # fmt: skip


def _top(pieces) -> float:
    from wadi2d.basin.reservoirs import crest_of

    return max(crest_of(piece) for piece in pieces)


def pool_mask(cfg, pieces, level: float) -> tuple[np.ndarray, tuple[float, float, float]] | None:
    """The held side behind a dam's lines at ``level``, widened by ``WIDEN_M``, on a ``PIXEL_M`` raster: the mask and
    the raster's (west, north, pixel); None when no side is held within the widest window. The ground is read through
    the run's chunk store of the DEM when there is one (W84), as the delineation reads it."""
    from wadi2d.demstore import cache_folder, open_bed
    from wadi2d.demstore.coarse import read_coarse_from

    with open_bed(cfg, cache_folder(cfg), stride=1) as bed:
        return _pool_mask(lambda *window: read_coarse_from(bed, cfg.terrain.dem, *window, PIXEL_M, 1),
                          cfg.terrain.dem, pieces, level)  # fmt: skip


def _pool_mask(read, dem: str, pieces, level: float):
    import rasterio
    from rasterio import features
    from rasterio.transform import Affine

    lines = [shapely.LineString(p.coordinates) for p in pieces]
    xmin, ymin, xmax, ymax = shapely.union_all(lines).bounds
    with rasterio.open(dem) as src:
        bounds = src.bounds
    half = WINDOW_M[0]
    while half <= WINDOW_M[1]:
        x0 = max(np.floor((xmin - half) / PIXEL_M) * PIXEL_M, bounds.left)
        y0 = min(np.ceil((ymax + half) / PIXEL_M) * PIXEL_M, bounds.top)
        nx = int(np.ceil((min(xmax + half, bounds.right) - x0) / PIXEL_M))
        ny = int(np.ceil((y0 - max(ymin - half, bounds.bottom)) / PIXEL_M))
        z = read(x0, y0, ny, nx)
        transform = Affine(PIXEL_M, 0.0, x0, 0.0, -PIXEL_M, y0)
        wall = features.rasterize([(line.buffer(WALL_M), 1) for line in lines], out_shape=z.shape, transform=transform,
                                  fill=0, all_touched=True, dtype="uint8").astype(bool)  # fmt: skip
        wet = np.isfinite(z) & (z < level) & ~wall
        label, _count = ndimage.label(wet)
        edge = set(np.unique(np.concatenate([label[0], label[-1], label[:, 0], label[:, -1]])).tolist())
        beside = np.unique(label[ndimage.binary_dilation(wall, iterations=2) & (label > 0)]).tolist()
        held = [k for k in beside if k not in edge]
        reaches = [k for k in beside if k in edge]
        if held and reaches:  # one side held, the other runs off down the valley: the held one is the pool
            sizes = {k: int(np.count_nonzero(label == k)) for k in held}
            pool = label == max(sizes, key=sizes.get)
            radius = int(round(WIDEN_M / PIXEL_M))
            disk = np.hypot(*np.mgrid[-radius : radius + 1, -radius : radius + 1]) <= radius
            return ndimage.binary_dilation(pool, structure=disk), (x0, y0, PIXEL_M)
        half *= 2.0
    return None


def _strip_cells(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None:
    """The aligned cells of a run, from ``maps/strip_mesh.gpkg``: index, area, centroid x and y."""
    if not path.is_file():
        return None
    with sqlite3.connect(path) as db:
        rows = db.execute("SELECT cell, area_m2, geom FROM strip_cells").fetchall()
    cells, areas, xs, ys = [], [], [], []
    for cell, area, blob in rows:
        flags = blob[3]
        envelope = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}.get((flags >> 1) & 0b111, 0)
        centroid = shapely.from_wkb(bytes(blob[8 + envelope :])).centroid
        cells.append(int(cell))
        areas.append(float(area))
        xs.append(centroid.x)
        ys.append(centroid.y)
    return np.asarray(cells), np.asarray(areas), np.asarray(xs), np.asarray(ys)


def _inside(mask: np.ndarray, frame: tuple[float, float, float], x: np.ndarray, y: np.ndarray) -> np.ndarray:
    x0, y0, pixel = frame
    col = np.floor((x - x0) / pixel).astype(np.int64)
    row = np.floor((y0 - y) / pixel).astype(np.int64)
    ok = (row >= 0) & (row < mask.shape[0]) & (col >= 0) & (col < mask.shape[1])
    out = np.zeros(x.shape, bool)
    out[ok] = mask[row[ok], col[ok]]
    return out


def _line_flow(out: Path, name: str) -> tuple[np.ndarray, np.ndarray] | None:
    path = out / "series" / f"line_{safe_name(name)}.csv"
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as f:
        rows = list(csv.reader(f))
    head, data = rows[0], np.array(rows[1:], float)
    if "discharge_m3s" not in head or data.size == 0:
        return None
    t, q = data[:, 0], data[:, head.index("discharge_m3s")]
    return t, (1.0 if np.trapezoid(q, t) >= 0.0 else -1.0) * q


def _balance(t: np.ndarray, storage: np.ndarray, line) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per map interval: its end, the inflow by balance and the mean outflow, m3/s."""
    ends, inflow, outflow = [], [], []
    for k in range(1, t.size):
        a, b = t[k - 1], t[k]
        if b <= a:
            continue
        left = 0.0
        if line is not None:
            tq, q = line
            inside = (tq >= a) & (tq <= b)
            left = float(np.trapezoid(q[inside], tq[inside])) if inside.sum() > 1 else 0.0
        ends.append(b)
        inflow.append((storage[k] - storage[k - 1] + left) / (b - a))
        outflow.append(left / (b - a))
    return np.asarray(ends), np.asarray(inflow), np.asarray(outflow)


def pool_records(cfg, out: Path | str, into: Path | str | None = None) -> list[dict]:
    """``series/pool_<dam>.csv`` for every named dam on the grid of a finished run, and ``pools.json``: what was read
    and how, written in the run folder, or in ``into`` for a run that is only read. Returns the records."""
    import h5py

    out = Path(out)
    into = out if into is None else Path(into)
    dams = {name: pieces for name, pieces in _dams(cfg).items()
            if not (out / "series" / f"network_{safe_name(name)}.csv").is_file()}  # fmt: skip
    results = out / "results.h5"
    if not dams or cfg.terrain.dem is None or not results.is_file():
        return []
    strip = _strip_cells(out / "maps" / "strip_mesh.gpkg")
    records = []
    with h5py.File(results, "r") as f:
        if "mask" not in f or "maps" not in f:
            return []
        mask = f["mask"][:].astype(bool)
        x0, y0, dx = (float(f.attrs[k]) for k in ("x0", "y0", "dx"))
        names = sorted(f["maps"].keys(), key=lambda n: float(f["maps"][n].attrs.get("t_s", int(n[1:]))))
        jj, ii = np.nonzero(mask)
        cx, cy = x0 + (ii + 0.5) * dx, y0 - (jj + 0.5) * dx
        pools: dict[str, tuple] = {}
        for name, pieces in dams.items():
            level = _top(pieces) + ABOVE_CREST_M
            found = pool_mask(cfg, pieces, level)
            if found is None:
                records.append({"dam": name, "read": "no pool: the ground under the crest is held on no side"})
                continue
            pool, frame = found
            here = _inside(pool, frame, cx, cy)
            on_strip = None
            if strip is not None:
                take = _inside(pool, frame, strip[2], strip[3])
                on_strip = (strip[0][take], strip[1][take])
            pools[name] = (level, pool, frame, jj[here], ii[here], on_strip)
        t, stored = [0.0], {name: [0.0] for name in pools}
        for map_name in names:  # each map read once for every dam
            group = f["maps"][map_name]
            depth = group["mean_depth"][:]
            along = np.asarray(group["strip_mean_depth"][:]).reshape(-1) if "strip_mean_depth" in group else None
            t.append(float(group.attrs.get("t_s", int(map_name[1:]))))
            for name, (_level, _pool, _frame, sj, si, on_strip) in pools.items():
                water = float(depth[sj, si].sum()) * dx * dx
                if on_strip is not None and along is not None:
                    water += float((along[on_strip[0]] * on_strip[1]).sum())
                stored[name].append(water)
        for name, (level, pool, frame, sj, _si, on_strip) in pools.items():
            t_arr, s_arr = np.asarray(t), np.asarray(stored[name])
            line = _line_flow(out, name)
            ends, inflow, outflow = _balance(t_arr, s_arr, line)
            write_series_csv(into / "series" / f"{POOL_KIND}_{safe_name(name)}.csv", ends,
                             {"inflow_m3s": inflow, "outflow_m3s": outflow, "storage_m3": s_arr[1:][: ends.size]})  # fmt: skip
            peak = int(np.argmax(inflow)) if inflow.size else None
            records.append({
                "dam": name, "level_m": round(level, 3), "pool_km2": round(float(pool.sum()) * frame[2] ** 2 / 1e6, 4),
                "cells": int(sj.size), "aligned_cells": 0 if on_strip is None else int(on_strip[0].size),
                "outflow_line": name if line is not None else None,
                "read": "pool balance: the change of the water in the pool between two saved maps plus the outflow on "
                        "the dam line between them" + ("" if line is not None else "; no dam line, so no outflow"),
                "peak_inflow_m3s": None if peak is None else round(float(inflow[peak]), 3),
                "peak_inflow_h": None if peak is None else round(float(ends[peak]) / 3600.0, 3),
                # the dam line's own peak, at the series step, as a lumped reservoir's outflow peak is read
                "peak_outflow_m3s": round(float(np.max(line[1])), 3) if line is not None and line[1].size else None,
            })  # fmt: skip
    into.mkdir(parents=True, exist_ok=True)
    (into / FILE).write_text(json.dumps({"rule": __doc__.split("\n\n")[1], "dams": records}, indent=1), encoding="utf-8")
    return records
