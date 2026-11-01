"""N03 open issue 1: how does RAS 6.6 sample the terrain for cells and faces? Test candidate rules on a real file.

usage: probe_sampling.py RAS_FOLDER --dx 20
Uses RAS's own stored terrain (1/32 m steps) so that the rounding is not mistaken for a sampling rule.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import h5py
import numpy as np
import rasterio

import case


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("ras_folder")
    ap.add_argument("--dx", type=float, default=20.0)
    a = ap.parse_args()
    dx = a.dx
    k = round(dx / 0.5)
    with rasterio.open(Path("ras_common/Terrain/Terrain.fan_window_0p5m.tif")) as d:
        q = d.read(1).astype(np.float64)
        t = d.transform
    with rasterio.open(case.DEM) as d:
        src = d.read(1).astype(np.float64)
    print("terrain rounding: step", np.median(np.diff(np.unique(q[1000:1200, 1000:1200]))),
          "rms vs source mm", 1000 * np.sqrt(np.mean((q - src) ** 2)))  # fmt: skip
    c0 = round((case.X0 - t.c) / t.a)
    r0 = round((t.f - case.Y0) / -t.e)
    with h5py.File(Path(a.ras_folder) / "Fan.g01.hdf", "r") as f:
        m = f["Geometry/2D Flow Areas/Fan"]
        n = int(f["Geometry/2D Flow Areas/Attributes"]["Cell Count"][0])
        cc = m["Cells Center Coordinate"][:n]
        cz = m["Cells Minimum Elevation"][:n].astype(np.float64)
        info = m["Cells Volume Elevation Info"][:n]
        val = m["Cells Volume Elevation Values"][:].astype(np.float64)
        fcell = m["Faces Cell Indexes"][:]
        fmin = m["Faces Minimum Elevation"][:].astype(np.float64)
        fi = m["Faces Area Elevation Info"][:]
        fv = m["Faces Area Elevation Values"][:].astype(np.float64)
    col = np.round((cc[:, 0] - case.X0) / dx - 0.5).astype(int)
    row = np.round((case.Y0 - cc[:, 1]) / dx - 0.5).astype(int)
    rng = np.random.default_rng(1)
    pick = rng.choice(np.nonzero((row > 1) & (row < row.max() - 1) & (col > 1) & (col < col.max() - 1))[0], 1500, False)

    def window(c, dr0, dr1, dc0, dc1, arr=q):
        r = r0 + row[c] * k
        s = c0 + col[c] * k
        return arr[r + dr0 : r + k + dr1, s + dc0 : s + k + dc1]

    rules = {
        "exact k x k": (0, 0, 0, 0),
        "grown 1 all round": (-1, 1, -1, 1),
        "grown E,S": (0, 1, 0, 1),
        "grown W,N": (-1, 0, -1, 0),
        "grown E,N": (-1, 0, 0, 1),
        "grown W,S": (0, 1, -1, 0),
        "shift E,S": (1, 1, 1, 1),
        "shift W,N": (-1, -1, -1, -1),
    }
    print("\ncell zmin: RAS minus rule, mm")
    for name, (a0, a1, b0, b1) in rules.items():
        d = np.array([cz[c] - window(c, a0, a1, b0, b1).min() for c in pick]) * 1000
        print(f"  {name:20s} mean {d.mean():8.2f} rms {np.sqrt((d**2).mean()):8.2f} p50 {np.median(d):8.2f}")

    # corners of pixel squares: the terrain surface read with bilinear interpolation at pixel corners
    corner = 0.25 * (q[:-1, :-1] + q[1:, :-1] + q[:-1, 1:] + q[1:, 1:])  # corner (r+1, c+1) of pixel (r, c)
    d = []
    for c in pick:
        r = r0 + row[c] * k
        s = c0 + col[c] * k
        d.append(cz[c] - corner[r - 1 : r + k, s - 1 : s + k].min())
    d = np.array(d) * 1000
    print(f"  {'bilinear at corners':20s} mean {d.mean():8.2f} rms {np.sqrt((d**2).mean()):8.2f}")

    print("\ncell volume: RAS minus rule as mean depth, mm; top = last breakpoint only")
    for name, (a0, a1, b0, b1) in rules.items():
        all_d, top = [], []
        for c in pick:
            p = window(c, a0, a1, b0, b1).ravel()
            s, m_ = info[c]
            z, v = val[s : s + m_, 0], val[s : s + m_, 1]
            frac = dx * dx / p.size
            vp = np.maximum(z[:, None] - p[None, :], 0.0).sum(axis=1) * frac
            all_d.append((v - vp) / dx**2)
            top.append((v[-1] - vp[-1]) / dx**2)
        all_d = np.concatenate(all_d) * 1000
        top = np.array(top) * 1000
        print(f"  {name:20s} all: mean {all_d.mean():8.3f} rms {np.sqrt((all_d**2).mean()):8.3f}   top: mean {top.mean():8.3f} rms {np.sqrt((top**2).mean()):8.3f}")

    print("\nOne cell, breakpoints against the exact k x k pixels")
    c = int(pick[3])
    p = window(c, 0, 0, 0, 0).ravel()
    s, m_ = info[c]
    tab = val[s : s + m_]
    vp = np.maximum(tab[:, 0][:, None] - p[None, :], 0.0).sum(axis=1) * 0.25
    print("  zmin pixels", p.min(), "RAS", cz[c], "max", p.max(), "rows", m_)
    for (z, v), w in list(zip(tab, vp, strict=True))[:: max(m_ // 10, 1)]:
        print(f"  z {z:9.3f} V RAS {v:10.3f} pixels {w:10.3f} ratio {v / max(w, 1e-9):7.4f}")

    print("\nFirst breakpoint against stored minima, faces and cells")
    first = np.array([fv[s, 0] for s, _ in fi])
    print("  face table z0 minus Faces Minimum Elevation, max abs", np.abs(first - fmin).max())
    print("  cell table z0 minus Cells Minimum Elevation, max abs", np.abs(val[info[:, 0], 0] - cz).max())

    # faces: quantized profile rules
    print("\nface invert: RAS minus rule, mm, on the rounded terrain")
    inner = (fcell[:, 0] >= 0) & (fcell[:, 1] >= 0) & (fcell[:, 0] < n) & (fcell[:, 1] < n)
    idx = rng.choice(np.nonzero(inner)[0], 3000, False)
    res = {x: [] for x in ("max2", "min2", "mean2", "min4 (+1 either side)", "line samples dx/2")}
    for f_i in idx:
        ac, bc = fcell[f_i]
        ra, ca, rb, cb = row[ac], col[ac], row[bc], col[bc]
        if ra == rb:
            w = min(ca, cb)
            r = r0 + ra * k
            c = c0 + (w + 1) * k
            pa, pb = q[r : r + k, c - 1], q[r : r + k, c]
            ext_a, ext_b = q[r - 1 : r + k + 1, c - 1], q[r - 1 : r + k + 1, c]
        elif ca == cb:
            nn = min(ra, rb)
            r = r0 + (nn + 1) * k
            c = c0 + ca * k
            pa, pb = q[r - 1, c : c + k], q[r, c : c + k]
            ext_a, ext_b = q[r - 1, c - 1 : c + k + 1], q[r, c - 1 : c + k + 1]
        else:
            continue
        z = fmin[f_i]
        res["max2"].append(z - np.maximum(pa, pb).min())
        res["min2"].append(z - np.minimum(pa, pb).min())
        res["mean2"].append(z - (0.5 * (pa + pb)).min())
        res["min4 (+1 either side)"].append(z - min(ext_a.min(), ext_b.min()))
        m1 = 0.25 * (ext_a[:-1] + ext_a[1:] + ext_b[:-1] + ext_b[1:])
        res["line samples dx/2"].append(z - np.concatenate([m1, 0.5 * (pa + pb)]).min())
    for name, v in res.items():
        v = np.array(v) * 1000
        print(f"  {name:24s} mean {v.mean():8.2f} rms {np.sqrt((v**2).mean()):8.2f} p50 {np.median(v):8.2f}")

    # face area and perimeter from the half-pixel bilinear profile: is the whole face table reproduced?
    print("face table from the bilinear profile at half-pixel spacing (on the rounded terrain)")
    pick_f = rng.choice(np.nonzero(inner)[0], 2500, False)
    dA, dP, k_single, k_pixelsum, k_table = [], [], [], [], []
    ds = 0.25
    for f_i in pick_f:
        ac, bc = fcell[f_i]
        ra, ca, rb, cb = row[ac], col[ac], row[bc], col[bc]
        if ra == rb:
            w = min(ca, cb)
            r = r0 + ra * k
            c = c0 + (w + 1) * k
            ea, eb = q[r - 1 : r + k + 1, c - 1], q[r - 1 : r + k + 1, c]
        elif ca == cb:
            nn = min(ra, rb)
            r = r0 + (nn + 1) * k
            c = c0 + ca * k
            ea, eb = q[r - 1, c - 1 : c + k + 1], q[r, c - 1 : c + k + 1]
        else:
            continue
        prof = np.empty(2 * k + 1)
        prof[::2] = 0.25 * (ea[:-1] + ea[1:] + eb[:-1] + eb[1:])
        prof[1::2] = 0.5 * (ea[1:-1] + eb[1:-1])
        s_, m_ = fi[f_i]
        z, area, per = fv[s_ : s_ + m_, 0], fv[s_ : s_ + m_, 1], fv[s_ : s_ + m_, 2]
        for zz, aa, pp in zip(z[1:], area[1:], per[1:], strict=True):
            lo, hi = prof[:-1], prof[1:]
            d0, d1 = zz - lo, zz - hi
            both = (d0 > 0) & (d1 > 0)
            one = (d0 > 0) ^ (d1 > 0)
            sl = np.abs(hi - lo)
            frac = np.where(one, np.maximum(d0, d1) / np.maximum(sl, 1e-12), 0.0)
            a_ = ds * (0.5 * (d0 + d1) * both).sum() + ds * (0.5 * np.maximum(d0, d1) * frac * one).sum()
            p_ = (np.sqrt(ds**2 + sl**2) * (both + frac * one)).sum()
            dA.append(aa - a_)
            dP.append(pp - p_)
            if aa > 0.05 * dx:
                dep = np.maximum(zz - prof, 0.0)
                ks = ds * (dep ** (5 / 3)).sum()
                wet = ds * (dep > 0).sum()
                k_pixelsum.append(ks)
                k_single.append(aa * (aa / pp) ** (2 / 3))
                k_table.append(aa * (aa / max(wet, 1e-9)) ** (2 / 3))
    dA, dP = np.array(dA), np.array(dP)
    print(f"  area RAS minus rule, mean-depth mm: mean {1000 * dA.mean() / dx:.3f} rms {1000 * np.sqrt((dA**2).mean()) / dx:.3f}; rel to table rows n={dA.size}")
    print(f"  perimeter RAS minus rule, m: mean {dP.mean():.4f} rms {np.sqrt((dP**2).mean()):.4f}")
    ks, ksi, kw = np.array(k_pixelsum), np.array(k_single), np.array(k_table)
    print(f"  K sum over 0.25 m segments / RAS K, median {np.median(ks / ksi):.3f}")
    print(f"  K with R = A / wet width (no bump length) / RAS K, median {np.median(kw / ksi):.3f}")
    print(f"  K sum / K with R = A / wet width, median {np.median(ks / kw):.3f}")


if __name__ == "__main__":
    main()
