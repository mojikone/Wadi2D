"""Sub-grid tables, RAS against wadi2d.tables, per N03's protocol. Residual distributions, not pass or fail.

usage: compare_tables.py RAS_FOLDER --dx 10 --out tables_10m.json

Both models see the same 0.5 m pixels, and the RAS cells are the Wadi2D cells (checked here, not assumed).
Three things are compared:
  cells: zmin; volume at RAS's own breakpoints, against wadi2d.tables and against the pixels directly
  faces: invert; area at RAS's breakpoints, read the way the solver reads the Wadi2D table; conveyance
  sampling: which pixel rule reproduces RAS's face invert (N03 open issue 1)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import h5py
import numpy as np
import rasterio

import case
from wadi2d.config.schema import Tables
from wadi2d.grid.tiles import TileGrid
from wadi2d.tables import build_tables, hbar_at_level
from wadi2d.terrain import RasterBed


def pct(a: np.ndarray, scale: float = 1.0) -> dict[str, float]:
    a = np.asarray(a, dtype=np.float64) * scale
    q = np.nanpercentile(a, [0.1, 1, 5, 50, 95, 99, 99.9])
    return {
        "n": int(np.isfinite(a).sum()),
        "mean": float(np.nanmean(a)),
        "rms": float(np.sqrt(np.nanmean(a**2))),
        "abs95": float(np.nanpercentile(np.abs(a), 95)),
        "p0.1": float(q[0]), "p1": float(q[1]), "p5": float(q[2]), "p50": float(q[3]),
        "p95": float(q[4]), "p99": float(q[5]), "p99.9": float(q[6]),
    }  # fmt: skip


def dem_pixels() -> np.ndarray:
    """Pixels of the mesh footprint plus one row and column all round, as (rows, cols), north up."""
    with rasterio.open(case.DEM) as d:
        z = d.read(1).astype(np.float64)
        t = d.transform
    c0 = round((case.X0 - t.c) / t.a)
    r0 = round((t.f - case.Y0) / -t.e)
    n = round(case.SIDE / t.a)
    return z[r0 - 1 : r0 + n + 1, c0 - 1 : c0 + n + 1]


def wadi_tables(dx: float):
    with RasterBed(case.DEM) as bed:
        w = bed.snap((case.X0, case.Y0 - case.SIDE, case.X0 + case.SIDE, case.Y0), dx)
        mask = bed.active_mask(w, dx)
        grid = TileGrid.from_mask(mask, w.x0, w.y0, dx)
        bed.bind(grid.x0, grid.y0)
        return grid, build_tables(grid, bed, Tables(), case.MANNING)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("ras_folder")
    ap.add_argument("--dx", type=float, default=10.0)
    ap.add_argument("--out", default=None)
    ap.add_argument("--cache", default=None, help="take the face tables from this grid cache file")
    a = ap.parse_args()
    dx = a.dx
    k = round(dx / 0.5)
    n = round(case.SIDE / dx)
    with h5py.File(Path(a.ras_folder) / "Fan.g01.hdf", "r") as f:
        ver = f.attrs["File Version"].decode()
        m = f["Geometry/2D Flow Areas/Fan"]
        ncell = int(f["Geometry/2D Flow Areas/Attributes"]["Cell Count"][0])
        cc = m["Cells Center Coordinate"][:ncell]
        cz = m["Cells Minimum Elevation"][:ncell].astype(np.float64)
        cinfo = m["Cells Volume Elevation Info"][:ncell]
        cval = m["Cells Volume Elevation Values"][:].astype(np.float64)
        fcell = m["Faces Cell Indexes"][:]
        fnl = m["Faces NormalUnitVector and Length"][:]
        finfo = m["Faces Area Elevation Info"][:]
        fval = m["Faces Area Elevation Values"][:].astype(np.float64)
        fz_name = "Faces Minimum Elevation" if "Faces Minimum Elevation" in m else "Faces Low Elevation Centroid"
        fmin_ds = m[fz_name][:].astype(np.float64) if fz_name in m else None
        names = list(m.keys())
    print(ver, "datasets", [x for x in names if x.startswith("Faces")])

    col = np.round((cc[:, 0] - case.X0) / dx - 0.5).astype(int)
    row = np.round((case.Y0 - cc[:, 1]) / dx - 0.5).astype(int)
    off = np.abs(cc[:, 0] - (case.X0 + (col + 0.5) * dx)) + np.abs(cc[:, 1] - (case.Y0 - (row + 0.5) * dx))
    print("cell centre offset from lattice, max", off.max(), "cells", ncell, "lattice", n * n)
    if ncell != n * n or len(np.unique(row * n + col)) != ncell or off.max() > 1e-3:
        raise SystemExit("RAS cells are not the lattice")

    px = dem_pixels()
    grid, t = wadi_tables(dx)
    if a.cache:
        with h5py.File(a.cache, "r") as c:
            t.ftabx, t.ftaby = c["ftabx"][()], c["ftaby"][()]
    oj = round((grid.y0 - case.Y0) / dx)  # padded rows north of the mesh
    oi = round((case.X0 - grid.x0) / dx)

    hc = grid.from_tiles(t.hc)
    dtab = grid.from_tiles(t.dtab)
    out: dict = {"ras": ver, "dx": dx, "cells": ncell}

    # cells --------------------------------------------------------------
    zmin_px = np.empty(ncell)
    dz_tab = []  # RAS minus wadi2d.tables, volume as mean depth over the cell, m
    dz_pix = []  # RAS minus pixels directly
    dz_self = []  # wadi2d.tables minus pixels directly: the 16-row table against its own source
    rel_tab, rel_pix = [], []
    level_tab = []
    for c in range(ncell):
        r0, c0 = 1 + row[c] * k, 1 + col[c] * k
        p = px[r0 : r0 + k, c0 : c0 + k].ravel()
        zmin_px[c] = p.min()
        s, cnt = cinfo[c]
        tab = cval[s : s + cnt]
        z, v = tab[:, 0], tab[:, 1]
        vp = np.maximum(z[:, None] - p[None, :], 0.0).sum(axis=1) * 0.25
        j, i = row[c] + oj, col[c] + oi
        hb = hbar_at_level(z, t.zmin[j, i], np.full(z.shape, hc[j, i]), np.broadcast_to(dtab[j, i], (*z.shape, dtab.shape[-1])))
        vw = hb * dx * dx
        dz_tab.append((v - vw) / dx**2)
        dz_pix.append((v - vp) / dx**2)
        dz_self.append((vw - vp) / dx**2)
        big = vp > 0.05 * dx**2
        rel_tab.append((v[big] - vw[big]) / vp[big])
        rel_pix.append((v[big] - vp[big]) / vp[big])
        level_tab.append(cnt)
    out["cell_table_rows_ras"] = pct(np.array(level_tab))
    out["cell_zmin_ras_minus_pixels_mm"] = pct(cz - zmin_px, 1000)
    out["cell_zmin_wadi_minus_pixels_mm"] = pct(t.zmin[row + oj, col + oi] - zmin_px, 1000)
    out["cell_volume_table_minus_pixels_mean_depth_mm"] = pct(np.concatenate(dz_self), 1000)
    out["cell_volume_ras_minus_pixels_mean_depth_mm"] = pct(np.concatenate(dz_pix), 1000)
    out["cell_volume_ras_minus_table_mean_depth_mm"] = pct(np.concatenate(dz_tab), 1000)
    out["cell_volume_ras_minus_pixels_rel_pct_over_5cm"] = pct(np.concatenate(rel_pix), 100)
    out["cell_volume_ras_minus_table_rel_pct_over_5cm"] = pct(np.concatenate(rel_tab), 100)

    # faces --------------------------------------------------------------
    inner = (fcell[:, 0] >= 0) & (fcell[:, 1] >= 0) & (fcell[:, 0] < ncell) & (fcell[:, 1] < ncell)
    idx = np.nonzero(inner)[0]
    fx = grid.from_tiles(t.ftabx)
    fy = grid.from_tiles(t.ftaby)
    ex = grid.from_tiles(t.efx)
    ey = grid.from_tiles(t.efy)
    frx = grid.from_tiles(t.frx)
    fry = grid.from_tiles(t.fry)
    rows = fx.shape[2]
    grid_r = (np.arange(rows) / (rows - 1)) ** 2
    zf_ras = np.full(idx.size, np.nan)
    zf_wadi = np.full(idx.size, np.nan)
    cand = {name: np.full(idx.size, np.nan) for name in ("max", "min", "mean", "side_a", "side_b")}
    d_area, d_area_rel, ratio_k, depths_k, wet_w = [], [], [], [], []
    d_per = []
    for q, f_i in enumerate(idx):
        a_c, b_c = fcell[f_i]
        ra, ca, rb, cb = row[a_c], col[a_c], row[b_c], col[b_c]
        if ra == rb:  # x face, between columns
            west = min(ca, cb)
            jj, ii = ra + oj, west + 1 + oi
            tab, top, zf = fx[jj, ii], ex[jj, ii], t.zmin[jj, ii] + frx[jj, ii]
            r0 = 1 + ra * k
            c = 1 + (west + 1) * k
            pa, pb = px[r0 : r0 + k, c - 1], px[r0 : r0 + k, c]
        elif ca == cb:  # y face, between rows
            north = min(ra, rb)
            jj, ii = north + 1 + oj, ca + oi
            tab, top, zf = fy[jj, ii], ey[jj, ii], t.zmin[jj, ii] + fry[jj, ii]
            c0 = 1 + ca * k
            r = 1 + (north + 1) * k
            pa, pb = px[r - 1, c0 : c0 + k], px[r, c0 : c0 + k]
        else:
            continue
        s, cnt = finfo[f_i]
        ftab = fval[s : s + cnt]
        z, area, per, man = ftab[:, 0], ftab[:, 1], ftab[:, 2], ftab[:, 3]
        zf_ras[q] = z[0]
        zf_wadi[q] = zf
        cand["max"][q] = np.maximum(pa, pb).min()
        cand["min"][q] = np.minimum(pa, pb).min()
        cand["mean"][q] = (0.5 * (pa + pb)).min()
        cand["side_a"][q] = pa.min()
        cand["side_b"][q] = pb.min()
        e = z - zf
        use = (e >= 0.0) & (e <= top)
        if not use.any():
            continue
        er = float(top) * grid_r
        aw = np.interp(e[use], er, tab[:, 0])
        kw = np.interp(e[use], er, tab[:, 1]) ** (5.0 / 3.0)
        d_area.append((area[use] - aw) / dx)  # as a mean depth over the face
        big = aw > 0.05 * dx
        d_area_rel.append((area[use][big] - aw[big]) / aw[big])
        pos = area[use] > 0.0
        kr = area[use] * (area[use] / np.maximum(per[use], 1e-9)) ** (2.0 / 3.0) / man[use]
        good = pos & (kw > 0.0) & big
        ratio_k.append(kw[good] / kr[good])
        depths_k.append(aw[good] / dx)
    done = np.isfinite(zf_ras)
    out["faces_compared"] = int(done.sum())
    out["face_invert_ras_minus_wadi_mm"] = pct(zf_ras[done] - zf_wadi[done], 1000)
    sampling = {}
    for name, v in cand.items():
        d = (zf_ras[done] - v[done]) * 1000
        sampling[name] = {"mean_mm": float(d.mean()), "rms_mm": float(np.sqrt((d**2).mean())), "abs95_mm": float(np.percentile(np.abs(d), 95))}
    out["face_invert_rule"] = sampling
    out["face_area_ras_minus_wadi_mean_depth_mm"] = pct(np.concatenate(d_area), 1000)
    out["face_area_ras_minus_wadi_rel_pct_over_5cm"] = pct(np.concatenate(d_area_rel), 100)
    kr_all = np.concatenate(ratio_k)
    dep = np.concatenate(depths_k)
    bins = [0.05, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0]
    out["K_wadi_over_K_ras_by_mean_face_depth"] = {
        f"{lo}-{hi} m": pct(kr_all[(dep >= lo) & (dep < hi)]) for lo, hi in zip(bins[:-1], bins[1:], strict=True)
        if ((dep >= lo) & (dep < hi)).any()
    }
    text = json.dumps(out, indent=1)
    print(text)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
