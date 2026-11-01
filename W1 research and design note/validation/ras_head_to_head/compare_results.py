"""Results, RAS against Wadi2D, on the same lattice: level, depth, extent, discharge, timing, velocity, run time.

usage: compare_results.py RAS_FOLDER WADI_RUN --dx 10 --out results_10m_swe_em.json [--png fig.png]
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import h5py
import numpy as np
import rasterio

import case

BASE = "Results/Unsteady/Output/Output Blocks/Base Output"
TS = BASE + "/Unsteady Time Series"
SUM2D = BASE + "/Summary Output/2D Flow Areas/Fan"


def stats(a: np.ndarray) -> dict[str, float]:
    a = np.asarray(a, np.float64)
    a = a[np.isfinite(a)]
    if a.size == 0:
        return {"n": 0}
    q = np.percentile(a, [1, 5, 25, 50, 75, 95, 99])
    return {
        "n": int(a.size), "mean": float(a.mean()), "rms": float(np.sqrt((a**2).mean())),
        "mae": float(np.abs(a).mean()), "p1": float(q[0]), "p5": float(q[1]), "p25": float(q[2]),
        "p50": float(q[3]), "p75": float(q[4]), "p95": float(q[5]), "p99": float(q[6]),
    }  # fmt: skip


class Ras:
    """A RAS run mapped onto the (n, n) lattice, row 0 north."""

    def __init__(self, folder: Path, dx: float) -> None:
        self.dx, self.n = dx, round(case.SIDE / dx)
        n = self.n
        with h5py.File(folder / "Fan.p01.hdf", "r") as f:
            m = f["Geometry/2D Flow Areas/Fan"]
            c = int(f["Geometry/2D Flow Areas/Attributes"]["Cell Count"][0])
            cc = m["Cells Center Coordinate"][:c]
            self.col = np.round((cc[:, 0] - case.X0) / dx - 0.5).astype(int)
            self.row = np.round((case.Y0 - cc[:, 1]) / dx - 0.5).astype(int)
            self.zmin = self._g(m["Cells Minimum Elevation"][:c])
            self.ncell = c
            info = m["Cells Volume Elevation Info"][:c]
            val = m["Cells Volume Elevation Values"][:]
            self.fcell = m["Faces Cell Indexes"][:]
            s = f[SUM2D]
            self.wse_max = self._g(s["Maximum Water Surface"][0, :c])
            ts = f[TS]
            self.t = ts["Time"][:] * 86400.0
            self.wse = ts["2D Flow Areas/Fan/Water Surface"][:, :c].astype(np.float64)
            self.vx = ts["2D Flow Areas/Fan/Cell Velocity - Velocity X"][:, :c].astype(np.float64)
            self.vy = ts["2D Flow Areas/Fan/Cell Velocity - Velocity Y"][:, :c].astype(np.float64)
            self.face_flow = ts["2D Flow Areas/Fan/Face Flow"][:].astype(np.float64)
            rl = ts["2D Flow Areas/Fan/Reference Lines"]
            names = [x.decode() if isinstance(x, bytes) else str(x) for x in np.ravel(rl["Name"][:])]
            self.ref_names = [x.split("|")[0].strip() for x in names]
            self.ref_flow = rl["Flow"][:].astype(np.float64)
            bc = ts["Boundary Conditions"]
            self.bc_out = {k: bc[k][:, 1].astype(np.float64) for k in ("OutEast", "OutNorth", "Inflow")}
            sm = f["Results/Unsteady/Summary"].attrs
            self.summary = {k: (sm[k].decode() if isinstance(sm[k], bytes) else sm[k]) for k in ("Computation Time Total", "Solution")}
            pa = f["Plan Data/Plan Parameters"].attrs
            self.equation = pa["2D Equation Set"][0].decode()
            self.cores = int(pa["2D Cores (per mesh)"][0])
            self.version = f.attrs["File Version"].decode()
            va = f["Results/Unsteady/Summary/Volume Accounting"].attrs
            self.va = {k: float(va[k]) for k in ("Error Percent", "Volume Ending", "Total Boundary Flux of Water In", "Total Boundary Flux of Water Out")}
        self.tmin = self._mean_depth_tables(info, val)

    def _g(self, a: np.ndarray) -> np.ndarray:
        out = np.full((self.n, self.n), np.nan)
        out[self.row, self.col] = a
        return out

    def _mean_depth_tables(self, info, val):
        self.info, self.val = info, val.astype(np.float64)
        return None

    def mean_depth(self, wse: np.ndarray) -> np.ndarray:
        """Cell volume over plan area at a level given per RAS cell index order."""
        out = np.zeros(self.ncell)
        for c in range(self.ncell):
            s, m = self.info[c]
            z, v = self.val[s : s + m, 0], self.val[s : s + m, 1]
            out[c] = np.interp(wse[c], z, v) + max(wse[c] - z[-1], 0.0) * self.dx**2
        return out / self.dx**2

    def section_flow(self, off: float, a: float, b: float) -> np.ndarray:
        """Eastward discharge across the lattice line ``off`` m east of the west edge, y from a to b m south."""
        c1 = round(off / self.dx)
        r0, r1 = round(a / self.dx), round(b / self.dx)
        id_of = np.full((self.n, self.n), -1)
        id_of[self.row, self.col] = np.arange(self.ncell)
        total = np.zeros(self.face_flow.shape[0])
        fc = self.fcell
        west = id_of[r0:r1, c1 - 1]
        east = id_of[r0:r1, c1]
        lookup = {(int(x), int(y)): i for i, (x, y) in enumerate(fc)}
        found = 0
        for w, e in zip(west, east, strict=True):
            if (w, e) in lookup:
                total += self.face_flow[:, lookup[(w, e)]]
                found += 1
            elif (e, w) in lookup:
                total -= self.face_flow[:, lookup[(e, w)]]
                found += 1
        if found != r1 - r0:
            raise ValueError(f"{found} faces of {r1 - r0}")
        return total


class Wadi:
    def __init__(self, folder: Path, n: int, dx: float) -> None:
        self.folder = folder
        with h5py.File(folder / "results.h5", "r") as f:
            x0, y0 = float(f.attrs["x0"]), float(f.attrs["y0"])
            self.oi, self.oj = round((case.X0 - x0) / dx), round((y0 - case.Y0) / dx)
            self.n = n
            cut = (slice(self.oj, self.oj + n), slice(self.oi, self.oi + n))
            self.depth = f["maxima/depth"][cut].astype(np.float64)
            self.mean_depth = f["maxima/mean_depth"][cut].astype(np.float64)
            self.speed = f["maxima/speed"][cut].astype(np.float64)
            self.arrival = f["maxima/arrival"][cut].astype(np.float64)
            self.snaps = {}
            for key in f["maps"]:
                g = f["maps"][key]
                self.snaps[float(g.attrs["t_s"])] = {k: g[k][cut].astype(np.float64) for k in ("depth", "mean_depth", "speed")}
        with rasterio.open(folder / "maps" / "max_level.tif") as d:
            t = d.transform
            c0, r0 = round((case.X0 - t.c) / t.a), round((t.f - case.Y0) / -t.e)
            a = d.read(1, masked=True).astype(np.float64).filled(np.nan)
            self.level = a[r0 : r0 + n, c0 : c0 + n]
        self.zmin = self.level - self.depth
        self.done = json.loads((folder / "progress.jsonl").read_text(encoding="utf-8").strip().split("\n")[-1])

    def series(self, name: str) -> tuple[np.ndarray, np.ndarray]:
        with open(self.folder / "series" / f"line_{name}.csv", encoding="utf-8") as f:
            rows = list(csv.reader(f))[1:]
        a = np.array(rows, dtype=np.float64)
        return a[:, 0], a[:, 1]


def pixel_extent(level: np.ndarray, dx: float, depth: float) -> np.ndarray:
    """0.5 m wet mask from a cell level grid; NaN level means dry."""
    k = round(dx / 0.5)
    with rasterio.open(case.DEM) as d:
        z = d.read(1).astype(np.float64)
        t = d.transform
    c0, r0 = round((case.X0 - t.c) / t.a), round((t.f - case.Y0) / -t.e)
    n = level.shape[0] * k
    z = z[r0 : r0 + n, c0 : c0 + n]
    lev = np.repeat(np.repeat(level, k, axis=0), k, axis=1)
    return lev - z >= depth


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("ras_folder")
    ap.add_argument("wadi_run")
    ap.add_argument("--dx", type=float, required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--png", default=None)
    a = ap.parse_args()
    dx = a.dx
    r = Ras(Path(a.ras_folder), dx)
    w = Wadi(Path(a.wadi_run), r.n, dx)
    out: dict = {
        "ras_version": r.version, "ras_equation": r.equation, "ras_cores": r.cores, "dx": dx,
        "ras_summary": {k: str(v) for k, v in r.summary.items()}, "ras_volume": r.va,
        "wadi_done": {k: w.done.get(k) for k in ("steps", "loop_s", "tables_s", "dt_min", "wet_area_km2", "balance")},
    }  # fmt: skip

    # levels ------------------------------------------------------------
    ras_d = r.wse_max - r.zmin
    wad_d = w.depth
    both = (ras_d >= 0.1) & (wad_d >= 0.1)
    deep = (ras_d >= 0.5) & (wad_d >= 0.5)
    out["max_level_wadi_minus_ras_m"] = {"wet_both_0.1": stats((w.level - r.wse_max)[both]), "deep_both_0.5": stats((w.level - r.wse_max)[deep])}
    out["max_depth_over_cell_min_wadi_minus_ras_m"] = stats((wad_d - ras_d)[both])
    ras_hbar = r._g(r.mean_depth(r.wse_max[r.row, r.col]))
    hb = (ras_hbar >= 0.02) & (w.mean_depth >= 0.02)
    out["max_mean_depth_wadi_minus_ras_m"] = stats((w.mean_depth - ras_hbar)[hb])
    out["max_mean_depth_sum_m3"] = {"ras": float(np.nansum(ras_hbar) * dx**2), "wadi": float(np.nansum(w.mean_depth) * dx**2)}

    # extent ------------------------------------------------------------
    ext = {}
    for th in (0.1, 0.3, 1.0):
        ar, aw = ras_d >= th, wad_d >= th
        ext[f"cell_depth>={th}"] = {
            "F": float((ar & aw).sum() / max((ar | aw).sum(), 1)),
            "ras_km2": float(ar.sum() * dx**2 / 1e6), "wadi_km2": float(aw.sum() * dx**2 / 1e6),
        }  # fmt: skip
    for th in (0.05, 0.1, 0.3):
        lr = np.where(ras_d > 0.0, r.wse_max, np.nan)
        lw = np.where(wad_d > 0.0, w.level, np.nan)
        pr, pw = pixel_extent(lr, dx, th), pixel_extent(lw, dx, th)
        ext[f"pixel_depth>={th}"] = {
            "F": float((pr & pw).sum() / max((pr | pw).sum(), 1)),
            "ras_km2": float(pr.sum() * 0.25 / 1e6), "wadi_km2": float(pw.sum() * 0.25 / 1e6),
        }  # fmt: skip
    out["extent"] = ext

    # discharge ---------------------------------------------------------
    sec = {}
    series = {}
    for name, (off, ya, yb) in case.SECTIONS.items():
        qr = r.section_flow(off, ya, yb)
        tw, qw = w.series(name)
        qw5 = np.interp(r.t, tw, qw)
        ref = r.ref_flow[:, r.ref_names.index(name)] if name in r.ref_names else None
        ipr, ipw = int(np.argmax(qr)), int(np.argmax(qw))
        vr = float(np.trapezoid(qr, r.t))
        vw = float(np.trapezoid(qw, tw))
        half_r = float(np.interp(0.5 * qr.max(), qr[: ipr + 1], r.t[: ipr + 1]))
        half_w = float(np.interp(0.5 * qw.max(), qw[: ipw + 1], tw[: ipw + 1]))
        sec[name] = {
            "peak_ras": float(qr.max()), "peak_ras_refline": None if ref is None else float(ref.max()),
            "peak_wadi": float(qw.max()), "peak_diff_pct": float(100 * (qw.max() / qr.max() - 1)),
            "t_peak_ras_min": float(r.t[ipr] / 60), "t_peak_wadi_min": float(tw[ipw] / 60),
            "t_half_rise_ras_min": half_r / 60, "t_half_rise_wadi_min": half_w / 60,
            "volume_ras_m3": vr, "volume_wadi_m3": vw,
            "nse_5min": float(1 - ((qw5 - qr) ** 2).sum() / ((qr - qr.mean()) ** 2).sum()),
        }  # fmt: skip
        series[name] = (r.t, qr, tw, qw)
    out["sections"] = sec
    out["ras_boundary_peaks"] = {k: float(v.max()) for k, v in r.bc_out.items()}

    # timing: arrival of 0.1 m over the cell's lowest point --------------
    d_ts = r.wse - r.zmin[r.row, r.col][None, :]
    arr = np.full(r.ncell, np.nan)
    for c in range(r.ncell):
        hit = np.nonzero(d_ts[:, c] >= 0.1)[0]
        if hit.size and hit[0] > 0:
            i = hit[0]
            arr[c] = np.interp(0.1, d_ts[i - 1 : i + 1, c], r.t[i - 1 : i + 1])
    arr_g = r._g(arr)
    ok = np.isfinite(arr_g) & (w.arrival >= 0.0)
    out["arrival_wadi_minus_ras_min"] = stats((w.arrival - arr_g)[ok] / 60.0)

    # speed: the same 5-min sampling on both sides ------------------------
    tt = sorted(w.snaps)
    sp = np.sqrt(r.vx**2 + r.vy**2)
    max_r = np.zeros(r.ncell)
    wmax = np.zeros((r.n, r.n))
    for i, t in enumerate(r.t):
        key = tt[int(np.argmin(np.abs(np.array(tt) - t)))]
        s = w.snaps[key]
        wmax = np.maximum(wmax, np.where(s["mean_depth"] >= 0.1, s["speed"], 0.0))
        dd = d_ts[i]
        max_r = np.maximum(max_r, np.where(dd >= 0.1, sp[i], 0.0))
    max_rg = r._g(max_r)
    sel = (max_rg > 0.0) & (wmax > 0.0) & (ras_d >= 0.5) & (wad_d >= 0.5)
    out["max_speed_5min_wadi_minus_ras_mps"] = stats((wmax - max_rg)[sel])
    out["max_speed_5min_ratio_wadi_over_ras"] = stats((wmax / np.maximum(max_rg, 1e-6))[sel])
    out["max_speed_means_mps"] = {"ras": float(max_rg[sel].mean()), "wadi": float(wmax[sel].mean())}

    # is the level bias a matter of flow direction on the square grid? (design note section 8)
    i_pk = int(np.argmin(np.abs(r.t - 1.75 * 3600.0)))
    vx, vy = r._g(r.vx[i_pk]), r._g(r.vy[i_pk])
    ang = np.degrees(np.arctan2(np.abs(vy), np.abs(vx)))
    ang = np.minimum(ang, 90.0 - ang)  # 0 along an axis, 45 on the diagonal
    dlev = w.level - r.wse_max
    by = {}
    for lo, hi in ((0, 15), (15, 30), (30, 45.01)):
        s = deep & (ang >= lo) & (ang < hi)
        by[f"{lo}-{hi:g} deg off axis"] = stats(dlev[s])
    out["level_diff_by_flow_angle_deep_cells_m"] = by

    text = json.dumps(out, indent=1)
    print(text)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    if a.png:
        figure(a.png, r, w, ras_d, wad_d, series, dx)


def figure(path, r, w, ras_d, wad_d, series, dx) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(2, 3, figsize=(16, 10))
    ext = (0, case.SIDE, 0, case.SIDE)
    for x, d, t in ((ax[0, 0], ras_d, f"{r.version.split(' Sept')[0]} {r.equation}"), (ax[0, 1], wad_d, "Wadi2D")):
        im = x.imshow(np.where(d >= 0.1, d, np.nan), extent=ext, vmin=0, vmax=4, cmap="viridis", interpolation="nearest")
        x.set_title(f"{t}: max depth over cell low point, m ({dx:g} m cells)")
        plt.colorbar(im, ax=x, shrink=0.75)
    dl = np.where((ras_d >= 0.1) & (wad_d >= 0.1), w.level - r.wse_max, np.nan)
    im = ax[0, 2].imshow(dl, extent=ext, vmin=-0.5, vmax=0.5, cmap="RdBu_r", interpolation="nearest")
    ax[0, 2].set_title("Wadi2D minus RAS, max level, m")
    plt.colorbar(im, ax=ax[0, 2], shrink=0.75)
    for x, (name, (tr, qr, tw, qw)) in zip(ax[1], series.items(), strict=True):
        x.plot(tr / 3600, qr, label="RAS", color="#1f4e79")
        x.plot(tw / 3600, qw, label="Wadi2D", color="#c8501e")
        x.set_title(f"{name}: discharge, m3/s")
        x.set_xlabel("hours")
        x.grid(alpha=0.3)
        x.legend()
    plt.tight_layout()
    plt.savefig(path, dpi=70)


if __name__ == "__main__":
    main()
