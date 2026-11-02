"""H1 to H6 at the 5 m pixel from the 5-minute frames: pixel depth x interpolated velocity, at the same moment.

Depth at a pixel is the cell's water level less the pixel's ground, as HEC-RAS Mapper and the Majlas script read it, so a
bank above the level stays dry. Velocity is interpolated to the pixel from cell-corner values, each the mean of the wet
cells around that corner, so dry neighbours do not pull it down. Each frame updates max depth, max velocity and max
depth x velocity per pixel; the class comes from those three. Only cells that ever reach mean depth DEPTH_MIN are kept,
so the job is about 240 M pixels. Writes terrain/pixel_hazard_5m.tif, terrain/pixel_depth_5m.tif, pixel_hazard_stats.json.
Usage: s06_pixel_hazard.py [frames], for a timing trial on the first frames after hour 6.
"""

from __future__ import annotations

import json
import queue
import sys
import threading
import time
from pathlib import Path

import cupy as cp
import h5py
import numpy as np
import rasterio
from rasterio.transform import from_origin

HERE = Path(__file__).resolve().parent
RUN = HERE / "runs" / "full_30m_200yr_5min"
MAPS = RUN / "maps"
DEM = HERE / "terrain" / "NSA5_COP30_blend.tif"
LIMITS = [(0.3, 0.3, 2.0), (0.6, 0.5, 2.0), (0.6, 1.2, 2.0), (1.0, 2.0, 2.0), (4.0, 4.0, 4.0)]  # D x V, depth, speed
DEPTH_MIN = 0.05  # m
SCALE = 6
BATCH = 1_500_000  # cells per GPU batch of the pixel update
LEVEL_JUMP = 2.0  # m; a neighbour further from this cell's level than this is not interpolated towards: a bank stays a bank


def read(name):
    with rasterio.open(MAPS / f"{name}.tif") as s:
        return s.read(1, masked=True).filled(0.0).astype("float32"), s.transform


def pixels_of_cells(rows, cols, tr):
    """Ground of the 36 pixels of each kept cell, N x 36; NaN outside the terrain."""
    with rasterio.open(DEM) as z:
        dem = z.read(1, masked=True).filled(np.nan)
        left, top = z.transform.c, z.transform.f
    pix = 5.0
    r0 = np.rint((top - (tr.f + rows * tr.e)) / pix).astype(np.int64)
    c0 = np.rint((tr.c + cols * tr.a - left) / pix).astype(np.int64)
    sub_r, sub_c = np.meshgrid(np.arange(SCALE), np.arange(SCALE), indexing="ij")
    rr = r0[:, None] + sub_r.ravel()[None, :]
    cc = c0[:, None] + sub_c.ravel()[None, :]
    ok = (rr >= 0) & (rr < dem.shape[0]) & (cc >= 0) & (cc < dem.shape[1])
    out = np.full(rr.shape, np.nan, "float32")
    out[ok] = dem[rr[ok], cc[ok]]
    del dem
    return out, r0, c0


def corner_basis() -> np.ndarray:
    """Weights of the four cell corners at the 36 pixel centres, 36 x 4: NW, NE, SW, SE."""
    f = (np.arange(SCALE) + 0.5) / SCALE
    fy, fx = np.meshgrid(f, f, indexing="ij")
    weights = np.stack([(1 - fy) * (1 - fx), (1 - fy) * fx, fy * (1 - fx), fy * fx], axis=-1).reshape(-1, 4).astype("float32")
    assert np.allclose(weights.sum(axis=1), 1.0)
    return weights


def corners(s: cp.ndarray) -> cp.ndarray:
    """Corner values of a speed field, the mean of the wet cells that meet there; shape ny + 1, nx + 1."""
    ny, nx = s.shape
    wet = (s > 0).astype(cp.float32)
    num = cp.zeros((ny + 1, nx + 1), cp.float32)
    den = cp.zeros((ny + 1, nx + 1), cp.float32)
    for dy in (0, 1):
        for dx in (0, 1):
            num[dy : dy + ny, dx : dx + nx] += s
            den[dy : dy + ny, dx : dx + nx] += wet
    return num / cp.maximum(den, 1.0)


def level_corners(level: cp.ndarray, wet: cp.ndarray) -> tuple:
    """Water level at a cell's four corners, NW NE SW SE, each the mean of this cell and the neighbours that meet there.

    A neighbour counts only if it is wet and within LEVEL_JUMP of this cell, so the surface slopes along connected flow
    and is never carried over a bank.
    """

    def seen(dy: int, dx: int) -> cp.ndarray:
        other = cp.roll(level, (dy, dx), axis=(0, 1))
        wet_other = cp.roll(wet, (dy, dx), axis=(0, 1))
        return cp.where(wet_other & (cp.abs(other - level) < LEVEL_JUMP), other, level)

    north, south, west, east = seen(1, 0), seen(-1, 0), seen(0, 1), seen(0, -1)
    return (
        0.25 * (level + north + west + seen(1, 1)),
        0.25 * (level + north + east + seen(1, -1)),
        0.25 * (level + south + west + seen(-1, 1)),
        0.25 * (level + south + east + seen(-1, -1)),
    )


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    t0 = time.time()
    mean, tr = read("max_mean_depth")
    depth_max, _ = read("max_depth")
    level_max, _ = read("max_level")
    keep = mean > DEPTH_MIN
    rows, cols = np.nonzero(keep)
    zmin = (level_max - depth_max)[keep]
    index = np.full(keep.shape, -1, np.int32)
    index[keep] = np.arange(rows.size)
    print(f"kept cells {rows.size:,}, pixels {rows.size * SCALE**2 / 1e6:,.0f} M", flush=True)
    z, r0, c0 = pixels_of_cells(rows, cols, tr)
    del mean, depth_max, level_max
    print(f"ground read in {time.time() - t0:.0f} s", flush=True)

    n = rows.size
    gz = np.nan_to_num(z, nan=1e6)
    del z
    cells = []
    for a in range(0, n, BATCH):
        b = min(a + BATCH, n)
        cells.append((a, b, cp.asarray(gz[a:b]), cp.asarray(zmin[a:b]), cp.asarray(rows[a:b]), cp.asarray(cols[a:b])))
    del gz
    dmax = [cp.zeros((b - a, SCALE**2), cp.float32) for a, b, *_ in cells]
    vmax = [cp.zeros_like(x) for x in dmax]
    dvmax = [cp.zeros_like(x) for x in dmax]
    basis = cp.asarray(corner_basis())
    keep_gpu = cp.asarray(keep)
    zmin_grid = cp.zeros(keep.shape, cp.float32)
    zmin_grid[cp.asarray(rows), cp.asarray(cols)] = cp.asarray(zmin)

    frames: queue.Queue = queue.Queue(maxsize=3)

    def reader() -> None:
        with h5py.File(RUN / "results.h5", "r") as f:
            names = sorted(f["maps"].keys())
            if limit:
                names = names[72 : 72 + limit]
            for name in names:
                g = f["maps"][name]
                frames.put((name, g["depth"][:], g["speed"][:]))
        frames.put(None)

    threading.Thread(target=reader, daemon=True).start()
    count = 0
    t1 = time.time()
    while (item := frames.get()) is not None:
        _name, d_np, s_np = item
        d = cp.asarray(d_np)
        s = cp.asarray(s_np) * keep_gpu * (d > DEPTH_MIN)  # as the run's maxima: a film has no meaningful speed
        c = corners(s)
        wet_grid = (d > 0) & keep_gpu
        nw, ne, sw, se = level_corners(zmin_grid + d, wet_grid)
        for k, (_a, _b, gz_k, zmin_k, r_k, c_k) in enumerate(cells):
            wet = d[r_k, c_k] > 0
            surface = cp.stack([nw[r_k, c_k], ne[r_k, c_k], sw[r_k, c_k], se[r_k, c_k]], axis=1) @ basis.T
            depth = cp.maximum(surface - gz_k, 0.0)
            depth = depth * wet[:, None]
            quad = cp.stack([c[r_k, c_k], c[r_k, c_k + 1], c[r_k + 1, c_k], c[r_k + 1, c_k + 1]], axis=1)
            speed = quad @ basis.T
            speed = speed * (depth >= DEPTH_MIN)
            dmax[k] = cp.maximum(dmax[k], depth)
            vmax[k] = cp.maximum(vmax[k], speed)
            dvmax[k] = cp.maximum(dvmax[k], depth * speed)
        count += 1
        if count % 20 == 0 or limit:
            print(f"frame {count}, {(time.time() - t1) / count:.2f} s each", flush=True)

    d_all = np.concatenate([cp.asnumpy(x) for x in dmax])
    v_all = np.concatenate([cp.asnumpy(x) for x in vmax])
    dv_all = np.concatenate([cp.asnumpy(x) for x in dvmax])
    print(f"max depth {d_all.max():.1f}, speed {v_all.max():.1f}, d x v {dv_all.max():.1f}", flush=True)
    cls = np.ones(d_all.shape, np.uint8)
    for i, (dv_lim, d_lim, v_lim) in enumerate(LIMITS, start=1):
        above = (dv_all > dv_lim) | (d_all > d_lim) | (v_all > v_lim)
        cls = np.where(above & (cls == i), i + 1, cls).astype(np.uint8)
    cls[d_all < DEPTH_MIN] = 0
    km2 = 25e-6
    stats = {f"H{k}": float((cls == k).sum() * km2) for k in range(1, 7)}
    print("pixel classes km2", {k: round(a, 1) for k, a in stats.items()}, flush=True)
    if limit:
        return
    ny, nx = keep.shape
    sub_r, sub_c = np.meshgrid(np.arange(SCALE), np.arange(SCALE), indexing="ij")
    with rasterio.open(DEM) as z_src:
        shape, transform, crs = z_src.shape, z_src.transform, z_src.crs
    rr = (r0[:, None] + sub_r.ravel()[None, :]).ravel()
    cc = (c0[:, None] + sub_c.ravel()[None, :]).ravel()
    ok = (rr >= 0) & (rr < shape[0]) & (cc >= 0) & (cc < shape[1])
    out = np.zeros(shape, np.uint8)
    out[rr[ok], cc[ok]] = cls.ravel()[ok]
    profile = {"driver": "GTiff", "height": shape[0], "width": shape[1], "count": 1, "crs": crs, "transform": transform,
               "tiled": True, "blockxsize": 512, "blockysize": 512, "compress": "deflate", "BIGTIFF": "YES"}  # fmt: skip
    with rasterio.open(HERE / "terrain" / "pixel_hazard_sloped_5m.tif", "w", dtype="uint8", nodata=0, **profile) as o:
        o.write(out, 1)
    del out
    deep = np.full(shape, -9999.0, "float32")
    deep[rr[ok], cc[ok]] = np.where(cls.ravel()[ok] > 0, d_all.ravel()[ok], -9999.0)
    with rasterio.open(HERE / "terrain" / "pixel_depth_sloped_5m.tif", "w", dtype="float32", nodata=-9999.0, **profile) as o:
        o.write(deep, 1)
    (HERE / "pixel_hazard_sloped_stats.json").write_text(
        json.dumps({"class_km2": stats, "frames": count, "kept_cells": int(n), "limits": LIMITS, "depth_min_m": DEPTH_MIN}, indent=1),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
