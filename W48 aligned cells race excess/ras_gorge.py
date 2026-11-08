"""HEC-RAS 6.6 on W48's synthetic deep narrow gorge, to test the aligned mesh against an independent solver (W48).

His question: is the aligned mesh perhaps the right answer and the squares the wrong one? The gorge on the tight sine
(radius 243 m at the bends; a 12 m bed, walls rising 7 m over 1.5 m, 1 % slope, n 0.05), a steady 300 m3/s ramped up
over the first hour. HEC-RAS 6.6, SWE-EM, three meshes written as seeds:

* `sq5`: 5 m squares, HEC-RAS's own fine reference;
* `sq20`: 20 m squares;
* `al20`: 20 m cells aligned on the thalweg the way a HEC-RAS breakline makes them, seeds mirrored at half a cell
  either side of the centreline every 20 m along it, the lattice beyond 1.5 cells; `al10` the same at 10 m.

The domain is the gorge with 60 m either side of the centreline, a flow hydrograph across its upstream end and normal
depth across its downstream end. Read between 1 and 8 km: the final water surface, each 0.5 m pixel taking the level
of the cell whose centre is nearest (HEC-RAS cells are the Voronoi cells of their seeds), the water held, and the level
3 m either side of the axis; beside Wadi2D's runs of the same gorge.

    .venv\\Scripts\\python "W48 aligned cells race excess\\ras_gorge.py" [terrain build run report] [sq5 sq20 al20 al10]
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import shapely

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
RAS_TEXT = ROOT / "W1 research and design note" / "validation" / "ras_rain_on_grid"
sys.path.insert(0, str(RAS_TEXT))
sys.path.insert(0, str(ROOT / "W46 centre-based mesh generator"))
import ras_text as rt  # noqa: E402
import wave_probe as wp  # noqa: E402

wp.OUT = HERE / "probe"
sys.path.insert(0, str(HERE))
import narrow_gorge  # noqa: E402,F401  (registers the gorge cases)

CASE = next((a for a in sys.argv[1:] if a in wp.CASES), "narrow_sine")
WORK = HERE / ("ras" if CASE == "narrow_sine" else f"ras_{CASE}")
"""The tight sine keeps the first folder; another gorge (`narrow`, straight) gets its own."""
RAS = r"C:\Program Files (x86)\HEC\HEC-RAS\6.6\Ras.exe"
RASPROCESS = r"C:\Program Files (x86)\HEC\HEC-RAS\6.6\RasProcess.exe"
HALF_M = 60.0
X_IN, X_OUT = 150.0, wp.LENGTH - 150.0
"""The gorge ends pulled in: on the sine the 60 m offsets at an end lean up to 47 m along x, and must stay on the DEM."""
DURATION_H = 5
MESHES = {"sq5": (5.0, False, "1SEC"), "sq20": (20.0, False, "4SEC"), "al20": (20.0, True, "4SEC"), "al10": (10.0, True, "2SEC")}
NAME = "Gorge"


def centreline() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    c = wp.CASES[CASE]
    pts, arc = wp.curve(c["amp"])
    keep = (pts[:, 0] >= wp.X0 + X_IN) & (pts[:, 0] <= wp.X0 + X_OUT)
    p, a = pts[keep], arc[keep]
    t = np.gradient(p, axis=0)
    t /= np.hypot(t[:, 0], t[:, 1])[:, None]
    n = np.column_stack((-t[:, 1], t[:, 0]))
    return p, a - a[0], n


def perimeter() -> tuple[np.ndarray, dict[str, np.ndarray]]:
    p, _a, n = centreline()
    left = p + HALF_M * n
    right = p - HALF_M * n
    ring = np.vstack((left, right[::-1], left[:1]))
    ring = ring[:: max(1, len(ring) // 2000)] if len(ring) > 4000 else ring
    if not np.allclose(ring[-1], ring[0]):
        ring = np.vstack((ring, ring[:1]))
    bc = {"Inflow": np.array([right[0], left[0]]), "Outflow": np.array([left[-1], right[-1]])}
    return ring, bc


def seeds(dx: float, aligned: bool) -> np.ndarray:
    ring, _bc = perimeter()
    poly = shapely.Polygon(ring)
    inner = poly.buffer(-0.3 * dx)
    shapely.prepare(inner)
    xs = np.arange(ring[:, 0].min() + 0.5 * dx, ring[:, 0].max(), dx)
    ys = np.arange(ring[:, 1].min() + 0.5 * dx, ring[:, 1].max(), dx)
    gx, gy = np.meshgrid(xs, ys)
    lattice = np.column_stack((gx.ravel(), gy.ravel()))
    if not aligned:
        pts = lattice
    else:
        p, a, n = centreline()
        line = shapely.LineString(p)
        far = shapely.distance(line, shapely.points(lattice)) > 1.5 * dx
        s = np.arange(0.5 * dx, a[-1], dx)
        cx = np.interp(s, a, p[:, 0])
        cy = np.interp(s, a, p[:, 1])
        nx = np.interp(s, a, n[:, 0])
        ny = np.interp(s, a, n[:, 1])
        nn = np.hypot(nx, ny)
        nx, ny = nx / nn, ny / nn
        pair = np.vstack((np.column_stack((cx + 0.5 * dx * nx, cy + 0.5 * dx * ny)), np.column_stack((cx - 0.5 * dx * nx, cy - 0.5 * dx * ny))))
        pts = np.vstack((pair, lattice[far]))
    keep = shapely.contains_xy(inner, pts[:, 0], pts[:, 1])
    return pts[keep]


def flow_text() -> str:
    step_min = 5
    t = np.arange(0.0, DURATION_H * 60.0 + 0.1, step_min)
    q = np.minimum(t / 60.0, 1.0) * 300.0
    loc = "Boundary Location=                ,                ,        ,        ,                ,"
    u = ["Flow Title=Gorge steady 300", "Program Version=6.60", "Use Restart= 0 "]
    u += [f"{loc}{NAME:<16},                ,{'Inflow':<32},                                ",
          f"Interval={step_min}MIN", f"Flow Hydrograph= {len(q)} "]
    for i in range(0, len(q), 10):
        u.append("".join(rt.f8(float(v)) for v in q[i : i + 10]))
    u += ["Stage Hydrograph TW Check=0", f"Flow Hydrograph Slope= {wp.S_BED} ", "DSS Path=", "Use DSS=False",
          "Use Fixed Start Time=False", "Fixed Start Date/Time=,", "Is Critical Boundary=False", "Critical Boundary Flow="]
    u += [f"{loc}{NAME:<16},                ,{'Outflow':<32},                                ", f"Friction Slope={wp.S_BED},0"]
    tail = (rt.COMMON / "template.u").read_text(encoding=rt.ENC).replace("\r\n", "\n").split("\n")
    start = next(i for i, x in enumerate(tail) if x.startswith("Met Point Raster Parameters"))
    stop = next(i for i in range(start, len(tail)) if tail[i].startswith("Boundary Location"))
    return "\r\n".join(u + tail[start:stop])


def terrain() -> Path:
    out = WORK / "terrain" / "Terrain.hdf"
    if out.is_file():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    prj = rt.COMMON / "Projection UTM40.prj"
    subprocess.run([RASPROCESS, "CreateTerrain", "units=Meter", "stitch=false", f"prj={prj}", f"out={out}",
                    str(wp.OUT / CASE / "dem.tif")], check=True)
    print("terrain written", out)
    return out


def build(mesh: str) -> Path:
    dx, aligned, step = MESHES[mesh]
    ring, bc = perimeter()
    pts = seeds(dx, aligned)
    p = rt.Project(name=NAME, title=f"W48 gorge {mesh}", perimeter=ring, seeds=pts, dx=dx, manning=wp.MANNING,
                   rain_interval="5MIN", rain_mm=np.zeros(2), duration_h=DURATION_H, equation=2, cores=8, step=step,
                   map_interval="30MIN", terrain_rel=r"..\terrain\Terrain.hdf", bc_lines=bc, slope_out=wp.S_BED)
    folder = WORK / f"ras_{mesh}"
    rt.write(p, folder)
    (folder / f"{NAME}.u01").write_text(flow_text(), encoding=rt.ENC, newline="")
    print(f"{mesh}: {len(pts)} seeds written to {folder}")
    return folder


def run(mesh: str) -> None:
    folder = WORK / f"ras_{mesh}"
    t0 = time.perf_counter()
    with open(folder / "ras_stdout.txt", "w") as out:
        rc = subprocess.run([RAS, "-c", str(folder / f"{NAME}.prj"), str(folder / f"{NAME}.p01")], stdout=out, stderr=subprocess.STDOUT, check=False).returncode
    print(f"{mesh}: Ras.exe exit {rc} in {time.perf_counter() - t0:.0f} s", flush=True)


def ras_surface(mesh: str, z: np.ndarray, tr) -> tuple[np.ndarray, dict]:
    import h5py
    from scipy.spatial import cKDTree

    folder = WORK / f"ras_{mesh}"
    with h5py.File(folder / f"{NAME}.p01.hdf", "r") as f:
        ncell = int(f["Geometry/2D Flow Areas/Attributes"]["Cell Count"][0])
        cc = f[f"Geometry/2D Flow Areas/{NAME}/Cells Center Coordinate"][:ncell]
        ts = f[f"Results/Unsteady/Output/Output Blocks/Base Output/Unsteady Time Series/2D Flow Areas/{NAME}/Water Surface"]
        wse = ts[-1, :ncell].astype(np.float64)
        va = f["Results/Unsteady/Summary/Volume Accounting"].attrs
        info = {"cells": ncell, "volume_error_percent": float(va["Error Percent"]),
                "compute_time": f["Results/Unsteady/Summary"].attrs["Computation Time Total"].decode()}
    xs = tr.c + (np.arange(z.shape[1]) + 0.5) * tr.a
    ys = tr.f + (np.arange(z.shape[0]) + 0.5) * tr.e
    gx, gy = np.meshgrid(xs, ys)
    _d, k = cKDTree(cc).query(np.column_stack((gx.ravel(), gy.ravel())))
    return wse[k].reshape(z.shape), info


def report() -> dict:
    import rasterio
    from rasterio.windows import from_bounds

    import gorge_reading as gr

    work = wp.OUT / CASE
    with rasterio.open(work / "dem.tif") as src:
        win = from_bounds(wp.X0 + gr.X_FROM, wp.Y0, wp.X0 + gr.X_TO, wp.Y0 + wp.WIDTH, src.transform).round_offsets().round_lengths()
        z = src.read(1, window=win).astype(np.float64)
        tr = src.window_transform(win)
        pix = src.res[0]
    pts, arc = wp.curve(wp.CASES[CASE]["amp"])
    x = wp.X0 + np.arange(gr.X_FROM + 50.0, gr.X_TO - 50.0, 5.0)
    k = np.searchsorted(pts[:, 0], x)
    tang = pts[np.minimum(k + 1, len(pts) - 1)] - pts[np.maximum(k - 1, 0)]
    tang /= np.hypot(tang[:, 0], tang[:, 1])[:, None]
    nrm = np.column_stack((-tang[:, 1], tang[:, 0]))
    axis = pts[k]
    bed = 200.0 - arc[k] * wp.S_BED

    def read_level(s):
        lv = []
        for sign in (-1.0, 1.0):
            q = axis + sign * gr.SIDE_M * nrm
            col = np.clip(((q[:, 0] - tr.c) / tr.a).astype(int), 0, z.shape[1] - 1)
            row = np.clip(((q[:, 1] - tr.f) / tr.e).astype(int), 0, z.shape[0] - 1)
            lv.append(s[row, col])
        return 0.5 * (lv[0] + lv[1])

    surfaces = {}
    infos = {}
    for mesh in MESHES:
        if (WORK / f"ras_{mesh}" / f"{NAME}.p01.hdf").is_file():
            try:
                surfaces[f"RAS {mesh}"], infos[f"RAS {mesh}"] = ras_surface(mesh, z, tr)
            except KeyError as error:
                print(f"RAS {mesh}: no results ({error})")
    for mesh in ("sq2", "sq5", "sq20", "ce20", "ce10"):
        run_dir = work / wp.name_of(CASE, "steady", mesh)
        if (run_dir / "results.h5").is_file():
            surfaces[f"Wadi2D {mesh}"] = gr.surface(run_dir, z.shape, tr)
    ref_key = "RAS sq5"
    out = {}
    ref = surfaces.get(ref_key)
    print(f"\n{CASE}: steady 300 m3/s, 1 to 8 km, against HEC-RAS 6.6 SWE-EM at 5 m: level 3 m either side of the axis, water held")
    for key, s in surfaces.items():
        water = float(np.nansum(np.clip(s - z, 0.0, None))) * pix * pix
        lev = read_level(s)
        r = {"water_m3": water, "depth_axis_m": float(np.nanmedian(lev - bed)), **infos.get(key, {})}
        if ref is not None:
            r["level_vs_ras5_m"] = float(np.nanmedian(lev - read_level(ref)))
            r["water_vs_ras5"] = water / (float(np.nansum(np.clip(ref - z, 0.0, None))) * pix * pix) - 1
        out[key] = r
        extra = f"  ({r['cells']} cells, volume error {r['volume_error_percent']:.4f} %, {r['compute_time']})" if "cells" in r else ""
        tail = f"  level {r['level_vs_ras5_m']:+.3f} m  water {100 * r['water_vs_ras5']:+.2f} %" if ref is not None else ""
        print(f"  {key:14s} depth {r['depth_axis_m']:.3f} m{tail}{extra}")
    (WORK / "ras_gorge.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    steps = [a for a in sys.argv[1:] if a in ("terrain", "build", "run", "report")] or ["terrain", "build", "run", "report"]
    meshes = [a for a in sys.argv[1:] if a in MESHES] or list(MESHES)
    if "terrain" in steps:
        terrain()
    for mesh in meshes:
        if "build" in steps:
            build(mesh)
        if "run" in steps:
            run(mesh)
    if "report" in steps:
        report()
