"""A deep narrow gorge on synthetic ground, straight and sinuous, at a steady 300 m3/s (W48, 2026-11-08).

On Faydh the aligned strip holds its level 0.3 m low where the gorge is about 20 m wide and 4.6 to 4.8 m deep, and is
right where the channel is wide; the squares are right in both. This builds that section on the W46 probe's valley
(1 % bed slope, 8.4 km, 0.5 m DEM): a 12 m bed, walls rising 7 m over 1.5 m each side, a 10 m ledge, hills at 50 %;
straight along the lattice and on the probe's sine wave (150 m amplitude, 1,200 m wavelength). Meshes: squares at
20, 10, 5 and 2 m, the centre mesh at 20 and 10 m. Read: the stored water at the end and the level on the axis
between 1 and 8 km, against the 2 m squares.

    .venv\\Scripts\\python "W48 aligned cells race excess\\narrow_gorge.py" [narrow narrow_sine] [ground run report]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "W46 centre-based mesh generator"))
sys.path.insert(0, str(ROOT / "W47 face level carried to the face"))
import steady_surfaces as ss  # noqa: E402
import wave_probe as wp  # noqa: E402

wp.OUT = Path(__file__).resolve().parent / "probe"
wp.CASES["narrow"] = dict(bed_half=6.0, bank_run=1.5, depth=7.0, plain_w=10.0, plain_slope=0.05, hill=0.5, amp=0.0)
wp.CASES["narrow_sine"] = dict(bed_half=6.0, bank_run=1.5, depth=7.0, plain_w=10.0, plain_slope=0.05, hill=0.5, amp=wp.AMP)
wp.CASES["narrow_gentle"] = dict(bed_half=6.0, bank_run=1.5, depth=7.0, plain_w=10.0, plain_slope=0.05, hill=0.5, amp=50.0)
"""The same gorge on a gentler sine, 50 m amplitude: radius 729 m at the bends against 243."""
wp.MESHES["sq2"] = (2.0, False)
wp.MESHES["ce5"] = (5.0, True)
MESHES = tuple(a for a in ("sq20", "ce20", "sq10", "ce10", "sq5", "ce5", "sq2") if "--only" not in __import__("sys").argv or a in __import__("sys").argv)


def build_and_run(case: str) -> None:
    if not (wp.OUT / case / "dem.tif").is_file():
        wp.ground(case)
    for mesh in MESHES:
        data = wp.job(case, "steady", mesh)
        data["outputs"]["map_every_s"] = 10_800.0
        path = wp.OUT / case / f"{wp.name_of(case, 'steady', mesh)}.json"
        path.write_text(json.dumps(data, indent=1), encoding="utf-8")
        wp.run(case, "steady", mesh)


def axis_level(run: Path, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    import fiona
    import shapely

    level, ltr, _t = ss.final_lattice_level(run)
    col = np.clip(((xs - ltr.c) / ltr.a).astype(int), 0, level.shape[1] - 1)
    row = np.clip(((ys - ltr.f) / ltr.e).astype(int), 0, level.shape[0] - 1)
    out = level[row, col].copy()
    strip = run / "maps" / "strip_mesh.gpkg"
    if strip.is_file():
        g, lev = [], []
        with fiona.open(strip, layer="strip_cells") as src:
            for feat in src:
                g.append(shapely.geometry.shape(feat["geometry"]))
                lev.append(feat["properties"]["level_end_m"])
        hits = shapely.STRtree(g).query(shapely.points(np.column_stack((xs, ys))), predicate="within")
        out[hits[0]] = np.asarray(lev)[hits[1]]
    return out


def report(case: str) -> dict:
    work = wp.OUT / case
    c = wp.CASES[case]
    x = wp.X0 + np.arange(1000.0, 8000.0, 5.0)
    y = wp.centreline(x, c["amp"])
    # the axis point is on the curve, the bed there is 200 - arc * S
    pts, arc = wp.curve(c["amp"])
    s_of_x = np.interp(x, pts[:, 0], arc)
    bed = 200.0 - s_of_x * wp.S_BED
    res = {}
    ref = None
    for mesh in ("sq2", *[m for m in MESHES if m != "sq2"]):
        run = work / wp.name_of(case, "steady", mesh)
        if not (run / "results.h5").is_file():
            continue
        prog = [json.loads(s) for s in (run / "progress.jsonl").read_text().splitlines() if '"done"' in s[:14]][-1]
        lev = axis_level(run, x, y)
        r = {"depth_axis_m": float(np.nanmedian(lev - bed)), "stored_m3": prog["balance"]["storage_end_m3"]}
        if mesh == "sq2":
            ref = (lev, r)
        else:
            r["level_vs_sq2_m"] = float(np.nanmedian(lev - ref[0]))
            r["stored_vs_sq2"] = r["stored_m3"] / ref[1]["stored_m3"] - 1
        res[mesh] = r
    print(f"\n{case}: steady 300 m3/s; depth on the axis, level and stored water against the 2 m squares")
    for mesh, r in res.items():
        tail = f"  level {r['level_vs_sq2_m']:+.3f} m  stored {100 * r['stored_vs_sq2']:+.2f} %" if "level_vs_sq2_m" in r else "  (reference)"
        print(f"  {mesh:5s} depth {r['depth_axis_m']:.3f} m{tail}")
    (work / "narrow_gorge.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    return res


if __name__ == "__main__":
    cases = [a for a in sys.argv[1:] if a in wp.CASES] or ["narrow", "narrow_sine"]
    steps = [a for a in sys.argv[1:] if a in ("run", "report")] or ["run", "report"]
    for case in cases:
        if "run" in steps:
            build_and_run(case)
        if "report" in steps:
            report(case)
