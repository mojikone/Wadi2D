"""One configuration, RAS against Wadi2D against the HMS-equivalent, on the same lattice and the same faces.

Run with the project venv and PYTHONPATH on the frozen engine:
    compare.py NAME          NAME is a key of case.CONFIGS; folders ras_NAME and wadi_runs/NAME
"""

from __future__ import annotations

import csv
import json
import sys
from types import SimpleNamespace

import h5py
import numpy as np
import rasterio
from scipy import ndimage

import case

sys.path.insert(0, str(case.ENGINE))
from wadi2d.hydrology.transforms import ScsUnitHydrograph, convolve  # noqa: E402
from wadi2d.terrain.crest import NORTH, staircase  # noqa: E402

BASE = "Results/Unsteady/Output/Output Blocks/Base Output"
TS = BASE + "/Unsteady Time Series"
SUM2D = BASE + "/Summary Output/2D Flow Areas/Bidah"
G = 9.80665
DT5 = 5.0


def stats(a: np.ndarray) -> dict[str, float]:
    a = np.asarray(a, np.float64)
    a = a[np.isfinite(a)]
    if a.size == 0:
        return {"n": 0}
    q = np.percentile(a, [5, 50, 95])
    return {"n": int(a.size), "mean": float(a.mean()), "rms": float(np.sqrt((a**2).mean())),
            "p5": float(q[0]), "p50": float(q[1]), "p95": float(q[2])}  # fmt: skip


class Lattice:
    def __init__(self, dx: float) -> None:
        coarse = np.load(case.HERE / "mask_20m.npy")
        k = round(case.COARSE / dx)
        self.dx, self.k = dx, k
        self.mask = np.repeat(np.repeat(coarse, k, axis=0), k, axis=1)
        self.shape = self.mask.shape


class Ras:
    def __init__(self, name: str, lat: Lattice) -> None:
        self.lat = lat
        dx = lat.dx
        with h5py.File(case.HERE / f"ras_{name}" / "Bidah.p01.hdf", "r") as f:
            m = f["Geometry/2D Flow Areas/Bidah"]
            c = int(f["Geometry/2D Flow Areas/Attributes"]["Cell Count"][0])
            self.ncell = c
            cc = m["Cells Center Coordinate"][:c]
            self.col = np.round((cc[:, 0] - case.X0) / dx - 0.5).astype(int)
            self.row = np.round((case.Y0 - cc[:, 1]) / dx - 0.5).astype(int)
            self.area = m["Cells Surface Area"][:c]
            self.manning = m["Cells Center Manning's n"][:c] if "Cells Center Manning's n" in m else None
            self.zmin = self.grid(m["Cells Minimum Elevation"][:c])
            self.info = m["Cells Volume Elevation Info"][:c]
            self.val = m["Cells Volume Elevation Values"][:].astype(np.float64)
            self.faces = m["Faces Cell Indexes"][:]
            self.wse_max = self.grid(f[SUM2D]["Maximum Water Surface"][0, :c])
            ts = f[TS]
            self.t = ts["Time"][:] * 86400.0
            g = ts["2D Flow Areas/Bidah"]
            self.wse_end = g["Water Surface"][-1, :c].astype(np.float64)
            self._h5 = (name,)
            sm = f["Results/Unsteady/Summary"].attrs
            self.summary = {k: (sm[k].decode() if isinstance(sm[k], bytes) else str(sm[k]))
                            for k in ("Computation Time Total", "Solution")}  # fmt: skip
            pa = f["Plan Data/Plan Parameters"].attrs
            self.equation = pa["2D Equation Set"][0].decode()
            self.cores = int(pa["2D Cores (per mesh)"][0])
            self.version = f.attrs["File Version"].decode()
            va = f["Results/Unsteady/Summary/Volume Accounting"].attrs
            self.va = {k: float(v) for k, v in va.items() if not isinstance(v, (bytes, str))}
            self.bc = {}
            bc = ts["Boundary Conditions"]
            for k in ("OutEast", "OutNorth"):
                self.bc[k] = bc[k][:, 1].astype(np.float64)
        self.name = name

    def grid(self, a: np.ndarray) -> np.ndarray:
        out = np.full(self.lat.shape, np.nan)
        out[self.row, self.col] = a
        return out

    def face_flows(self, ids: np.ndarray) -> np.ndarray:
        with h5py.File(case.HERE / f"ras_{self.name}" / "Bidah.p01.hdf", "r") as f:
            d = f[TS]["2D Flow Areas/Bidah"]["Face Flow"]
            order = np.argsort(ids)
            part = d[:, ids[order]].astype(np.float64)
        out = np.empty_like(part)
        out[:, order] = part
        return out

    def section(self, pairs: list[tuple[int, int, float]]) -> np.ndarray:
        """Sum of the flows over (cell a, cell b, sign); a RAS face's flow is positive from its first to its second cell."""
        lookup = {(int(a), int(b)): k for k, (a, b) in enumerate(self.faces)}
        ids, signs = [], []
        for a, b, s in pairs:
            if (a, b) in lookup:
                ids.append(lookup[(a, b)])
                signs.append(s)
            elif (b, a) in lookup:
                ids.append(lookup[(b, a)])
                signs.append(-s)
            else:
                raise ValueError(f"no face between {a} and {b}")
        return (self.face_flows(np.array(ids)) * np.array(signs)).sum(axis=1)

    def mean_depth(self, wse: np.ndarray) -> np.ndarray:
        """Cell volume over plan area, at a level per RAS cell."""
        out = np.zeros(self.ncell)
        for c in range(self.ncell):
            s, n = self.info[c]
            z, v = self.val[s : s + n, 0], self.val[s : s + n, 1]
            out[c] = np.interp(wse[c], z, v) + max(wse[c] - z[-1], 0.0) * self.area[c]
        return out / self.area


class Wadi:
    def __init__(self, name: str, lat: Lattice) -> None:
        self.folder = case.HERE / "wadi_runs" / name
        self.lat = lat
        dx = lat.dx
        n = lat.shape
        with h5py.File(self.folder / "results.h5", "r") as f:
            self.x0, self.y0 = float(f.attrs["x0"]), float(f.attrs["y0"])
            self.full_shape = f["maxima/depth"].shape
            self.oi, self.oj = round((case.X0 - self.x0) / dx), round((self.y0 - case.Y0) / dx)
            self.depth = self.paste(f["maxima/depth"][:])
            self.mean_depth = self.paste(f["maxima/mean_depth"][:])
            self.speed = self.paste(f["maxima/speed"][:])
            keys = sorted(f["maps"], key=lambda k: float(f["maps"][k].attrs["t_s"]))
            g = f["maps"][keys[-1]]
            self.mean_end = self.paste(g["mean_depth"][:])
            self.t_end = float(g.attrs["t_s"])
            self.attrs = {k: f.attrs[k] for k in ("rain_m3", "outflow_m3", "storage_end_m3", "relative_error", "steps")}
        with rasterio.open(self.folder / "maps" / "max_level.tif") as d:
            t = d.transform
            # the map is cropped to the active cells, so it may start inside the lattice on any side
            c0, r0 = round((t.c - case.X0) / t.a), round((case.Y0 - t.f) / -t.e)
            a = d.read(1, masked=True).astype(np.float64).filled(np.nan)
            self.level = np.full(n, np.nan)
            jj, ii = np.nonzero(np.isfinite(a))
            jj2, ii2 = jj + r0, ii + c0
            keep = (jj2 >= 0) & (jj2 < n[0]) & (ii2 >= 0) & (ii2 < n[1])
            self.level[jj2[keep], ii2[keep]] = a[jj[keep], ii[keep]]
            self.level_outside = int((~keep).sum())
        self.done = json.loads((self.folder / "progress.jsonl").read_text(encoding="utf-8").strip().split("\n")[-1])

    def paste(self, a: np.ndarray) -> np.ndarray:
        """A grid of the run on the lattice. The run's grid starts at its own domain, not at the lattice origin."""
        n = self.lat.shape
        out = np.full(n, np.nan)
        j0, j1 = max(self.oj, 0), min(self.oj + n[0], a.shape[0])
        i0, i1 = max(self.oi, 0), min(self.oi + n[1], a.shape[1])
        out[j0 - self.oj : j1 - self.oj, i0 - self.oi : i1 - self.oi] = a[j0:j1, i0:i1]
        return out

    def series(self, name: str) -> tuple[np.ndarray, np.ndarray]:
        with open(self.folder / "series" / f"line_{name}.csv", encoding="utf-8") as f:
            a = np.array(list(csv.reader(f))[1:], np.float64)
        return a[:, 0], a[:, 1]


def face_pairs(coords, w: Wadi, id_of: np.ndarray) -> list[tuple[int, int, float]]:
    """The lattice faces of Wadi2D's own staircase for this line, as pairs of RAS cells with Wadi2D's sign."""
    grid = SimpleNamespace(x0=w.x0, y0=w.y0, dx=w.lat.dx, shape=w.full_shape)
    st = staircase(grid, coords)
    out = []
    for axis, j, i, side in zip(st.axis, st.j, st.i, st.side, strict=True):
        row, col = int(j) - w.oj, int(i) - w.oi
        a = (row - 1, col) if axis == NORTH else (row, col - 1)  # the face's positive normal runs from a to (row, col)
        ida, idb = id_of[a], id_of[row, col]
        if ida >= 0 and idb >= 0:
            out.append((int(ida), int(idb), float(side)))
    return out


def equivalent_lag(t: np.ndarray, q: np.ndarray, area: float, excess: np.ndarray, n_times: int) -> dict:
    """The SCS lag that best fits a hydrograph, least squares on 5 min steps, as block2_full s26."""
    tm = np.arange(n_times) * DT5 * 60.0
    keep = tm <= t.max()
    q5 = np.interp(tm[keep], t, q)
    best = (1e30, 0.0, 0.0)
    for lag in np.arange(5.0, 240.0, 1.0):
        uh = ScsUnitHydrograph(float(lag)).unit_hydrograph(area, DT5)
        f = convolve(excess, uh, n_times)[keep]
        err = float(((f - q5) ** 2).sum())
        if err < best[0]:
            best = (err, float(lag), float(f.max()))
    return {"lag_min": best[1], "fit_peak": best[2], "peak_5min": float(q5.max()),
            "rmse": float(np.sqrt(best[0] / keep.sum()))}  # fmt: skip


def shape(t, q) -> dict:
    i = int(np.argmax(q))
    half = float(np.interp(0.5 * q.max(), q[: i + 1], t[: i + 1]))
    return {"peak": float(q.max()), "t_peak_h": float(t[i] / 3600.0), "volume_m3": float(np.trapezoid(q, t)),
            "t_half_rise_h": half / 3600.0}  # fmt: skip


def nse(obs: np.ndarray, sim: np.ndarray) -> float:
    return float(1.0 - ((sim - obs) ** 2).sum() / ((obs - obs.mean()) ** 2).sum())


def pixel_wet(level: np.ndarray, lat: Lattice, depth: float) -> np.ndarray:
    """Wet mask on the 0.5 m pixels from a cell level grid; NaN means dry."""
    k = round(lat.dx / 0.5)
    with rasterio.open(case.DEM) as d:
        t = d.transform
        c0, r0 = round((case.X0 - t.c) / t.a), round((t.f - case.Y0) / -t.e)
        w = rasterio.windows.Window(c0, r0, lat.shape[1] * k, lat.shape[0] * k)
        z = d.read(1, window=w)
    out = np.zeros(z.shape, bool)
    # row by row of cells, so the level is not repeated in memory for the whole grid
    for j in range(lat.shape[0]):
        lev = np.repeat(level[j], k)
        s = slice(j * k, (j + 1) * k)
        with np.errstate(invalid="ignore"):
            out[s] = (lev[None, :] - z[s]) >= depth
    return out


def cell_classes(lat: Lattice) -> tuple[np.ndarray, np.ndarray]:
    """Drainage area per cell, the largest in it, km2, from the HMS 5 m raster; and relief inside the cell, m."""
    tag = case.HERE / f"classes_{lat.dx:g}m.npz"
    if tag.exists():
        z = np.load(tag)
        return z["acc"], z["relief"]
    bounds = (case.X0, case.Y0 - lat.shape[0] * lat.dx, case.X0 + lat.shape[1] * lat.dx, case.Y0)
    ny, nx = lat.shape
    with rasterio.open(case.ACC) as d:
        w = rasterio.windows.from_bounds(*bounds, d.transform).round_offsets().round_lengths()
        a = d.read(1, window=w, masked=True).filled(0.0).astype(np.float64) * case.ACC_CELL_KM2
        t = d.window_transform(w)
    jj, ii = np.indices(a.shape)
    x = t.c + (ii + 0.5) * t.a
    y = t.f + (jj + 0.5) * t.e
    row = np.floor((case.Y0 - y) / lat.dx).astype(int)
    col = np.floor((x - case.X0) / lat.dx).astype(int)
    keep = (row >= 0) & (row < ny) & (col >= 0) & (col < nx)
    acc = np.zeros(lat.shape)
    np.maximum.at(acc, (row[keep], col[keep]), a[keep])
    k = round(lat.dx / 0.5)
    with rasterio.open(case.DEM) as d:
        t = d.transform
        c0, r0 = round((case.X0 - t.c) / t.a), round((t.f - case.Y0) / -t.e)
        z = d.read(1, window=rasterio.windows.Window(c0, r0, nx * k, ny * k)).astype(np.float32)
    z = z.reshape(ny, k, nx, k)
    relief = z.max(axis=(1, 3)) - z.min(axis=(1, 3))
    np.savez_compressed(tag, acc=acc, relief=relief)
    return acc, relief


def closed_edge(lat: Lattice, d: np.ndarray, hbar: np.ndarray) -> dict:
    """Water against the walls: the edge cells away from the outlets; ``hbar`` is the max mean depth, a real volume."""
    m = lat.mask
    edge = m & ~ndimage.binary_erosion(m, border_value=0)
    dx = lat.dx
    # outlet cells: the east column and the north row of the box
    outlet = np.zeros_like(m)
    i_w = round((case.BOX_WEST - case.X0) / dx)
    j_s = round((case.Y0 - case.BOX_SOUTH) / dx)
    outlet[0, i_w:] = True
    outlet[:j_s, -1] = True
    closed = edge & ~ndimage.binary_dilation(outlet, iterations=2)
    v = d[closed]
    j, i = np.unravel_index(np.nanargmax(np.where(closed, d, -1.0)), d.shape)
    h = hbar[closed]
    return {"cells": int(closed.sum()), "over_1m": int((v > 1.0).sum()), "over_3m": int((v > 3.0).sum()),
            "deepest_m": float(np.nanmax(v)), "deepest_x": case.X0 + (i + 0.5) * dx, "deepest_y": case.Y0 - (j + 0.5) * dx,
            "max_mean_depth_m": float(np.nanmax(h)), "mean_depth_over_0.5m_cells": int((h > 0.5).sum()),
            "volume_at_max_m3": float(np.nansum(h) * dx**2)}  # fmt: skip


def main() -> None:
    name = sys.argv[1]
    cfg = case.CONFIGS[name]
    lat = Lattice(cfg["dx"])
    dx = lat.dx
    r = Ras(name, lat)
    w = Wadi(name, lat)
    id_of = np.full(lat.shape, -1, np.int64)
    id_of[r.row, r.col] = np.arange(r.ncell)
    out: dict = {"name": name, **cfg, "ras_version": r.version, "ras_equation": r.equation, "ras_cores": r.cores,
                 "ras_summary": r.summary, "ras_volume": r.va, "wadi_attrs": {k: float(v) for k, v in w.attrs.items()},
                 "wadi_done": {k: w.done.get(k) for k in ("steps", "loop_s", "tables_s", "dt_min", "wet_area_km2")}}  # fmt: skip
    # the two models hold the same cells
    interior_ras = id_of >= 0
    out["cells"] = {"lattice": int(lat.mask.sum()), "ras": int(r.ncell), "equal_mask": bool((interior_ras == lat.mask).all()),
                    "ras_area_min": float(r.area.min()), "ras_area_max": float(r.area.max()),
                    "ras_manning": None if r.manning is None else [float(r.manning.min()), float(r.manning.max())]}  # fmt: skip
    wet = np.isfinite(w.level)
    out["cells"]["wadi_wet_cells_inside_lattice"] = int((wet & lat.mask).sum())
    out["cells"]["wadi_wet_cells_outside_lattice"] = int((wet & ~lat.mask).sum())

    # rain ---------------------------------------------------------------
    mm = np.loadtxt(case.HERE / "excess_5min.csv", delimiter=",", skiprows=1)[:, 1]
    depth = float(mm.sum()) / 1000.0
    ras_rain = r.va["Precipitation Excess (m^3)"] * 1000.0
    wadi_rain = float(w.attrs["rain_m3"])
    out["rain"] = {"target_m3": depth * float(r.area.sum()), "ras_m3": ras_rain, "wadi_m3": wadi_rain,
                   "ras_area_km2": float(r.area.sum() / 1e6), "wadi_over_ras": wadi_rain / ras_rain}  # fmt: skip

    # sections -----------------------------------------------------------
    hms = np.loadtxt(case.HERE / "hms_equiv.csv", delimiter=",", skiprows=1)
    excess = np.zeros(576)
    excess[: mm.size] = mm
    n_times = 577
    sec = {}
    series = {}
    for key, coords in case.SECTIONS.items():
        pairs = face_pairs(coords, w, id_of)
        qr = r.section(pairs)
        tw, qw = w.series(key)
        qw_r = np.interp(r.t, tw, qw)
        sr, sw = shape(r.t, qr), shape(tw, qw)
        vs = sw["volume_m3"] / sr["volume_m3"]
        area_sec = sr["volume_m3"] / (mm.sum() / 1000.0) / 1e6
        area_w = sw["volume_m3"] / (mm.sum() / 1000.0) / 1e6
        sec[key] = {"faces": len(pairs), "ras": sr, "wadi": sw, "peak_ratio_wadi_over_ras": sw["peak"] / sr["peak"],
                    "volume_ratio_wadi_over_ras": vs, "nse_ras_as_obs": nse(qr, qw_r),
                    "t_shift_peak_min": (sw["t_peak_h"] - sr["t_peak_h"]) * 60.0,
                    "area_by_volume_km2": {"ras": area_sec, "wadi": area_w},
                    "lag_ras_own_area": equivalent_lag(r.t, qr, area_sec, excess, n_times),
                    "lag_wadi_own_area": equivalent_lag(tw, qw, area_w, excess, n_times),
                    "lag_ras_hms_area": equivalent_lag(r.t, qr, case.AREA_KM2, excess, n_times),
                    "lag_wadi_hms_area": equivalent_lag(tw, qw, case.AREA_KM2, excess, n_times)}  # fmt: skip
        series[key] = (r.t, qr, tw, qw)
    hs = shape(hms[:, 0], hms[:, 1])
    out["hms_equiv"] = hs
    out["sections"] = sec
    out["ratios_to_hms"] = {k: {"ras": v["ras"]["peak"] / hs["peak"], "wadi": v["wadi"]["peak"] / hs["peak"]}
                            for k, v in sec.items()}  # fmt: skip
    out["ras_outlets"] = {k: {"peak": float(v.max()), "volume_m3": float(np.trapezoid(np.abs(v), r.t))} for k, v in r.bc.items()}

    # levels -------------------------------------------------------------
    rd = r.wse_max - r.zmin
    wd = w.depth
    dl = w.level - r.wse_max
    deep = (rd >= 0.5) & (wd >= 0.5)
    shallow = (rd < 0.5) & (wd < 0.5) & (rd >= 0.02) & (wd >= 0.02)
    out["levels_m"] = {"deep_both_0.5": stats(dl[deep]), "shallow_0.02_to_0.5": stats(dl[shallow]),
                       "all_wet_0.02": stats(dl[(rd >= 0.02) & (wd >= 0.02)])}  # fmt: skip
    rhb = r.grid(r.mean_depth(r.wse_max[r.row, r.col]))
    hb = (rhb >= 0.02) & (w.mean_depth >= 0.02)
    # wadi or hillslope by drainage area, which neither model sets; the extra row of the outlet stays out
    acc, relief = cell_classes(lat)
    wadi = ndimage.binary_dilation(acc >= case.WADI_KM2, iterations=max(1, round(40.0 / dx))) & lat.mask
    hill = lat.mask & ~wadi
    dmd = w.mean_depth - rhb
    classes = {"wadi_area_km2": float(wadi.sum() * dx**2 / 1e6), "hill_area_km2": float(hill.sum() * dx**2 / 1e6)}
    classes["wadi_deep_both_0.5"] = {"level": stats(dl[wadi & deep]), "mean_depth": stats(dmd[wadi & deep])}
    sh = hill & (rd < 0.5) & (wd < 0.5) & (rd >= 0.02) & (wd >= 0.02)
    classes["hill_shallow_both_under_0.5"] = {"level": stats(dl[sh]), "mean_depth": stats(dmd[sh])}
    classes["hill_all"] = {"level": stats(dl[hill]), "mean_depth": stats(dmd[hill]),
                           "ras_mean_depth_mean": float(np.nanmean(rhb[hill])), "wadi_mean_depth_mean": float(np.nanmean(w.mean_depth[hill])),
                           "ras_depth_mean": float(np.nanmean(rd[hill])), "wadi_depth_mean": float(np.nanmean(wd[hill]))}  # fmt: skip
    for lo, hi in ((0.0, 2.0), (2.0, 5.0), (5.0, 10.0), (10.0, 1e3)):
        c = hill & (relief >= lo) & (relief < hi)
        classes[f"hill_relief_{lo:g}_{hi:g}m"] = {"cells": int(c.sum()), "level_mean": float(np.nanmean(dl[c])),
                                                  "ras_depth": float(np.nanmean(rd[c])), "wadi_depth": float(np.nanmean(wd[c])),
                                                  "ras_mean_depth": float(np.nanmean(rhb[c])), "wadi_mean_depth": float(np.nanmean(w.mean_depth[c]))}  # fmt: skip
    fan = np.zeros_like(lat.mask)
    fan[:, round((case.FAN_WEST - case.X0) / dx) :] = True
    classes["fan_wadi_deep_both_0.5"] = {"level": stats(dl[wadi & deep & fan]), "mean_depth": stats(dmd[wadi & deep & fan])}
    classes["gorge_wadi_deep_both_0.5"] = {"level": stats(dl[wadi & deep & ~fan]), "mean_depth": stats(dmd[wadi & deep & ~fan])}
    # speed in the wadi: the plan area of fast water
    classes["wadi_max_speed_wadi2d_mps_mean"] = float(np.nanmean(w.speed[wadi & deep]))
    out["cell_classes"] = classes
    out["max_mean_depth_m"] = {"wadi_minus_ras": stats((w.mean_depth - rhb)[hb]),
                               "shallow_wadi_minus_ras": stats((w.mean_depth - rhb)[shallow]),
                               "ras_shallow_median": float(np.nanmedian(rhb[shallow])),
                               "wadi_shallow_median": float(np.nanmedian(w.mean_depth[shallow]))}  # fmt: skip

    # extent --------------------------------------------------------------
    ext = {}
    for th in (0.1, 0.3, 1.0):
        ar, aw = rd >= th, wd >= th
        ext[f"cell_depth>={th}"] = {"F": float((ar & aw).sum() / max((ar | aw).sum(), 1)),
                                    "ras_km2": float(ar.sum() * dx**2 / 1e6), "wadi_km2": float(aw.sum() * dx**2 / 1e6)}  # fmt: skip
    for th in (0.1, 0.3):
        pr = pixel_wet(np.where(rd > 0.0, r.wse_max, np.nan), lat, th)
        pw = pixel_wet(np.where(wd > 0.0, w.level, np.nan), lat, th)
        ext[f"pixel_depth>={th}"] = {"F": float((pr & pw).sum() / max((pr | pw).sum(), 1)),
                                     "ras_km2": float(pr.sum() * 0.25 / 1e6), "wadi_km2": float(pw.sum() * 0.25 / 1e6)}  # fmt: skip
        c = round((case.FAN_WEST - case.X0) / 0.5)
        a, b = pr[:, c:], pw[:, c:]
        ext[f"fan_pixel_depth>={th}"] = {"F": float((a & b).sum() / max((a | b).sum(), 1)),
                                         "ras_km2": float(a.sum() * 0.25 / 1e6), "wadi_km2": float(b.sum() * 0.25 / 1e6)}  # fmt: skip
        del a, b
        del pr, pw
    out["extent"] = ext

    # closed edges --------------------------------------------------------
    out["closed_edges"] = {"ras": closed_edge(lat, rd, rhb), "wadi": closed_edge(lat, wd, w.mean_depth)}
    end_r = r.mean_depth(r.wse_end) * r.area
    out["stored_at_end_m3"] = {"ras": float(end_r.sum()), "wadi": float(np.nansum(w.mean_end) * dx**2)}

    text = json.dumps(out, indent=1)
    (case.HERE / f"results_{name}.json").write_text(text, encoding="utf-8")
    np.savez_compressed(case.HERE / f"series_{name}.npz", **{f"{k}_{n}": v for k, s in series.items()
                                                             for n, v in zip(("tr", "qr", "tw", "qw"), s, strict=True)})  # fmt: skip
    print(text)
    figure(name, series, hms, lat, dl, rd, wd)


def figure(name, series, hms, lat, dl, rd, wd) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(2, 3, figsize=(17, 10))
    for x, (key, (tr, qr, tw, qw)) in zip(ax[0], series.items(), strict=False):
        x.plot(tr / 3600, qr, label="HEC-RAS 6.6", color="#1f4e79")
        x.plot(tw / 3600, qw, label="Wadi2D", color="#c8501e")
        x.plot(hms[:, 0] / 3600, hms[:, 1], label="HMS-equivalent, S13", color="#555555", ls="--")
        x.set_xlim(10, 20)
        x.set_title(f"{key}: discharge, m3/s")
        x.set_xlabel("hours")
        x.grid(alpha=0.3)
        x.legend()
    ext = (case.X0, case.X0 + lat.shape[1] * lat.dx, case.Y0 - lat.shape[0] * lat.dx, case.Y0)
    im = ax[0, 2].imshow(np.where(rd >= 0.1, rd, np.nan), extent=ext, vmin=0, vmax=4, cmap="viridis", interpolation="nearest")
    ax[0, 2].set_title("RAS max depth over cell low point, m")
    plt.colorbar(im, ax=ax[0, 2], shrink=0.6)
    im = ax[1, 0].imshow(np.where(wd >= 0.1, wd, np.nan), extent=ext, vmin=0, vmax=4, cmap="viridis", interpolation="nearest")
    ax[1, 0].set_title("Wadi2D max depth over cell low point, m")
    plt.colorbar(im, ax=ax[1, 0], shrink=0.6)
    im = ax[1, 1].imshow(np.where((rd >= 0.02) & (wd >= 0.02), dl, np.nan), extent=ext, vmin=-0.5, vmax=0.5, cmap="RdBu_r", interpolation="nearest")
    ax[1, 1].set_title("Wadi2D minus RAS, max level, m")
    plt.colorbar(im, ax=ax[1, 1], shrink=0.6)
    ax[1, 2].hist(dl[(rd >= 0.5) & (wd >= 0.5)], bins=80, range=(-1.5, 1.5), alpha=0.6, label="deep cells")
    ax[1, 2].hist(dl[(rd < 0.5) & (wd < 0.5) & (rd >= 0.02) & (wd >= 0.02)], bins=80, range=(-1.5, 1.5), alpha=0.6, label="shallow")
    ax[1, 2].set_title("Wadi2D minus RAS, max level, m")
    ax[1, 2].legend()
    plt.tight_layout()
    plt.savefig(case.HERE / f"fig_{name}.png", dpi=70)


if __name__ == "__main__":
    main()
