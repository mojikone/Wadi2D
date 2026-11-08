"""The synthetic gorges read properly (W48): the first report sampled the axis, which is the strip's thalweg face, so
its points fell on a face and missed the strip's cells; and it compared the whole domain's storage, inflow zone
included. Here the final water surface (strip cells at their final level, squares from the last frame) is laid over
the 0.5 m DEM between 1 and 8 km and the water counted pixel by pixel; the level is read 3 m either side of the axis.

    .venv\\Scripts\\python "W48 aligned cells race excess\\gorge_reading.py" [case ...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import fiona
import numpy as np
import rasterio
import shapely
from rasterio import features
from rasterio.windows import from_bounds

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "W46 centre-based mesh generator"))
sys.path.insert(0, str(ROOT / "W47 face level carried to the face"))
import steady_surfaces as ss  # noqa: E402
import wave_probe as wp  # noqa: E402

HERE = Path(__file__).resolve().parent
wp.OUT = HERE / "probe"
sys.path.insert(0, str(HERE))
import narrow_gorge  # noqa: E402,F401  (registers the gorge cases)

MESHES = ("sq20", "ce20", "sq10", "ce10", "sq5", "ce5", "sq2")
X_FROM, X_TO = 1000.0, 8000.0
SIDE_M = 3.0


def surface(run: Path, shape, tr) -> np.ndarray:
    level, ltr, _t = ss.final_lattice_level(run)
    xs = tr.c + (np.arange(shape[1]) + 0.5) * tr.a
    ys = tr.f + (np.arange(shape[0]) + 0.5) * tr.e
    col = np.clip(((xs - ltr.c) / ltr.a).astype(int), 0, level.shape[1] - 1)
    row = np.clip(((ys - ltr.f) / ltr.e).astype(int), 0, level.shape[0] - 1)
    s = level[row[:, None], col[None, :]]
    strip = run / "maps" / "strip_mesh.gpkg"
    if strip.is_file():
        g, lev = [], []
        with fiona.open(strip, layer="strip_cells") as src:
            for feat in src:
                g.append(shapely.geometry.shape(feat["geometry"]))
                lev.append(feat["properties"]["level_end_m"])
        owner = features.rasterize(((gg, k) for k, gg in enumerate(g)), out_shape=shape, transform=tr, fill=-1, dtype="int32")
        s = np.where(owner >= 0, np.asarray(lev)[np.clip(owner, 0, None)], s)
    return s


def read(case: str) -> dict:
    work = wp.OUT / case
    c = wp.CASES[case]
    with rasterio.open(work / "dem.tif") as src:
        win = from_bounds(wp.X0 + X_FROM, wp.Y0, wp.X0 + X_TO, wp.Y0 + wp.WIDTH, src.transform).round_offsets().round_lengths()
        z = src.read(1, window=win).astype(np.float64)
        tr = src.window_transform(win)
        pix = src.res[0]
    pts, arc = wp.curve(c["amp"])
    x = wp.X0 + np.arange(X_FROM + 50.0, X_TO - 50.0, 5.0)
    k = np.searchsorted(pts[:, 0], x)
    tang = pts[np.minimum(k + 1, len(pts) - 1)] - pts[np.maximum(k - 1, 0)]
    tang /= np.hypot(tang[:, 0], tang[:, 1])[:, None]
    nrm = np.column_stack((-tang[:, 1], tang[:, 0]))
    axis = pts[k]
    bed = 200.0 - arc[k] * wp.S_BED
    res = {}
    ref_w, ref_l = None, None
    for mesh in ("sq2", *[m for m in MESHES if m != "sq2"]):
        run = work / wp.name_of(case, "steady", mesh)
        if not (run / "results.h5").is_file():
            continue
        s = surface(run, z.shape, tr)
        water = float(np.nansum(np.clip(s - z, 0.0, None))) * pix * pix
        lv = []
        for sign in (-1.0, 1.0):
            q = axis + sign * SIDE_M * nrm
            col = np.clip(((q[:, 0] - tr.c) / tr.a).astype(int), 0, z.shape[1] - 1)
            row = np.clip(((q[:, 1] - tr.f) / tr.e).astype(int), 0, z.shape[0] - 1)
            lv.append(s[row, col])
        lev = 0.5 * (lv[0] + lv[1])
        r = {"water_m3": water, "depth_axis_m": float(np.nanmedian(lev - bed))}
        if mesh == "sq2":
            ref_w, ref_l = water, lev
        else:
            r["water_vs_sq2"] = water / ref_w - 1
            r["level_vs_sq2_m"] = float(np.nanmedian(lev - ref_l))
        res[mesh] = r
    print(f"\n{case}: steady 300 m3/s, 1 to 8 km; depth on the axis, and against the 2 m squares the level and the water held")
    for mesh, r in res.items():
        tail = f"  level {r['level_vs_sq2_m']:+.3f} m  water {100 * r['water_vs_sq2']:+.2f} %" if "water_vs_sq2" in r else "  (reference)"
        print(f"  {mesh:5s} depth {r['depth_axis_m']:.3f} m{tail}")
    (work / "gorge_reading.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    return res


if __name__ == "__main__":
    for case in [a for a in sys.argv[1:] if a in wp.CASES] or ["narrow", "narrow_sine", "narrow_gentle"]:
        read(case)
