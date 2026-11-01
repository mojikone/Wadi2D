"""The hydraulic jump at the fan head, read from existing outputs, no extra run.

The thalweg is the path of largest RAS discharge concentration: from the wadi above the fan to the outlet, by the
highest max mean depth per lattice step. Along it, at the time of the section peak, both models give a Froude number
from speed and wet depth (cell mean depth over wet plan share). A jump shows as F falling through 1 with depth rising.

usage: jump.py NAME
"""

from __future__ import annotations

import json
import sys

import h5py
import numpy as np
from scipy import ndimage

import case

sys.path.insert(0, str(case.HERE))
from compare import TS, Lattice, Ras, Wadi  # noqa: E402

G = 9.80665
START = (434413.0, 2726053.0)  # the 5 km2 point of the convergence runs, far up the gorge
END = (439000.0, 2727600.0)  # on the fan, just above the outlet


def path(score: np.ndarray, lat: Lattice) -> tuple[np.ndarray, np.ndarray]:
    """Least-cost walk from START to END; the cost is low where the max depth is high."""
    from skimage.graph import route_through_array

    def rc(p):
        return round((case.Y0 - p[1]) / lat.dx - 0.5), round((p[0] - case.X0) / lat.dx - 0.5)

    cost = 1.0 / np.maximum(np.nan_to_num(score), 0.02) ** 2
    cost[~lat.mask] = 1e9
    idx, _ = route_through_array(cost, rc(START), rc(END), fully_connected=True, geometric=True)
    a = np.array(idx)
    return a[:, 0], a[:, 1]


def main() -> None:
    name = sys.argv[1]
    cfg = case.CONFIGS[name]
    lat = Lattice(cfg["dx"])
    dx = lat.dx
    r = Ras(name, lat)
    w = Wadi(name, lat)
    res = json.loads((case.HERE / f"results_{name}.json").read_text(encoding="utf-8"))
    tp_ras = res["sections"]["axis"]["ras"]["t_peak_h"] * 3600.0
    tp_wad = res["sections"]["axis"]["wadi"]["t_peak_h"] * 3600.0
    with h5py.File(case.HERE / f"ras_{name}" / "Bidah.p01.hdf", "r") as f:
        g = f[TS]["2D Flow Areas/Bidah"]
        k = int(np.argmin(np.abs(r.t - tp_ras)))
        wse = g["Water Surface"][k, : r.ncell].astype(np.float64)
        vx = g["Cell Velocity - Velocity X"][k, : r.ncell].astype(np.float64)
        vy = g["Cell Velocity - Velocity Y"][k, : r.ncell].astype(np.float64)
    hbar_r = r.grid(r.mean_depth(wse))
    speed_r = r.grid(np.hypot(vx, vy))
    level_r = r.grid(wse)
    with h5py.File(w.folder / "results.h5", "r") as f:
        keys = sorted(f["maps"], key=lambda q: float(f["maps"][q].attrs["t_s"]))
        ts = np.array([float(f["maps"][q].attrs["t_s"]) for q in keys])
        q = keys[int(np.argmin(np.abs(ts - tp_wad)))]
        m = f["maps"][q]
        hbar_w = w.paste(m["mean_depth"][:])
        speed_w = w.paste(m["speed"][:])
        depth_w = w.paste(m["depth"][:])
        t_w = float(m.attrs["t_s"])
    level_w = w.level - w.depth + depth_w
    # wet depth over a 5-cell band across the flow would need the flow direction; the cell value is read directly
    jj, ii = path(np.maximum(np.nan_to_num(r.wse_max - r.zmin), np.nan_to_num(w.depth)), lat)
    s = np.concatenate(([0.0], np.cumsum(np.hypot(np.diff(jj), np.diff(ii)) * dx)))
    x = case.X0 + (ii + 0.5) * dx
    y = case.Y0 - (jj + 0.5) * dx
    zr = r.zmin[jj, ii]
    dr = np.maximum(level_r[jj, ii] - zr, 1e-3)
    dw = np.maximum(depth_w[jj, ii], 1e-3)
    fr = speed_r[jj, ii] / np.sqrt(G * np.maximum(hbar_r[jj, ii], 1e-3))
    fw = speed_w[jj, ii] / np.sqrt(G * np.maximum(hbar_w[jj, ii], 1e-3))
    win = max(3, round(100.0 / dx))
    fr_s = ndimage.uniform_filter1d(fr, win, mode="nearest")
    fw_s = ndimage.uniform_filter1d(fw, win, mode="nearest")

    def drops(f: np.ndarray) -> list[dict]:
        out = []
        for k in np.nonzero((f[:-1] > 1.0) & (f[1:] <= 1.0))[0]:
            out.append({"s_m": float(s[k]), "x": float(x[k]), "y": float(y[k])})
        return out

    result = {"name": name, "t_ras_h": float(r.t[int(np.argmin(np.abs(r.t - tp_ras)))] / 3600), "t_wadi_h": t_w / 3600.0,
              "path_cells": int(jj.size), "path_length_m": float(s[-1]), "smooth_m": float(win * dx),
              "ras_F_falls_through_1": drops(fr_s), "wadi_F_falls_through_1": drops(fw_s),
              "ras_mean_F": float(np.nanmean(fr)), "wadi_mean_F": float(np.nanmean(fw)),
              "ras_max_F_smoothed": float(np.nanmax(fr_s)), "wadi_max_F_smoothed": float(np.nanmax(fw_s)),
              "level_diff_on_path_m": {"mean": float(np.nanmean(level_w[jj, ii] - level_r[jj, ii])),
                                       "rms": float(np.sqrt(np.nanmean((level_w[jj, ii] - level_r[jj, ii]) ** 2)))},
              "bed_slope_by_500m": [float(v) for v in np.round(-np.diff(zr[:: round(500 / dx)]) / 500.0, 4)]}  # fmt: skip
    (case.HERE / f"jump_{name}.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    np.savetxt(case.HERE / f"thalweg_{name}.csv", np.column_stack((s, x, y, zr, level_r[jj, ii], level_w[jj, ii], fr_s, fw_s)),
               delimiter=",", header="s_m,x,y,z_low_ras,level_ras,level_wadi,froude_ras,froude_wadi", comments="", fmt="%.3f")  # fmt: skip
    print(json.dumps(result, indent=1))

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(3, 1, figsize=(13, 10), sharex=True)
    ax[0].plot(s, zr, color="#777777", label="cell low point, RAS")
    ax[0].plot(s, level_r[jj, ii], color="#1f4e79", label="RAS level at peak")
    ax[0].plot(s, level_w[jj, ii], color="#c8501e", label="Wadi2D level at peak")
    ax[0].legend()
    ax[0].set_ylabel("m")
    ax[1].plot(s, dr, color="#1f4e79", label="RAS depth over low point")
    ax[1].plot(s, dw, color="#c8501e", label="Wadi2D")
    ax[1].legend()
    ax[1].set_ylabel("m")
    ax[2].plot(s, fr_s, color="#1f4e79", label=f"RAS Froude, {win * dx:g} m mean")
    ax[2].plot(s, fw_s, color="#c8501e", label="Wadi2D")
    ax[2].axhline(1.0, color="k", lw=0.7)
    ax[2].set_xlabel("distance along the thalweg, m")
    ax[2].legend()
    for a in ax:
        a.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(case.HERE / f"fig_jump_{name}.png", dpi=70)


if __name__ == "__main__":
    main()
