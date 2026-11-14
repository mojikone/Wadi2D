"""The synthetic gorges of W48 and W49 for the gorge rows (W52): jobs, runs and the reading, from this worktree.

The ground (0.5 m DEMs, thalweg files, domains) and the reference runs on squares are read where W48 and W49 left
them, in the main checkout, and nothing is written there: the jobs, caches and runs of W52 live under this folder
(`jobs/` in git, `runs/` and `cache/` not). The engine runs as `python -m wadi2d.engine.cli` from this checkout, so
the code under test is this branch's, whatever `wadi2d.exe` of the venv imports.

Cases: `narrow` (straight), `narrow_gentle` (sine, radius 729 m at the bends), `narrow_sine` (radius 243 m): a 12 m
bed, walls rising 7 m over 1.5 m each side, a 10 m ledge, hills at 50 %, 1 % along the channel, n 0.05, a steady
300 m3/s. The reading is W48's `gorge_reading.py`: the final surface over the 0.5 m DEM between 1 and 8 km, the
level 3 m either side of the axis; here also the water held between 1 and 7 km, clear of the pond the 20 m squares
make where the strip ends (7.8 km).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MAIN = Path(os.environ.get("WADI2D_MAIN", r"D:\Mojtaba\Renardet\Wadi2D"))
"""The main checkout, where the untracked ground and reference runs are; read only."""
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "W46 centre-based mesh generator"))
sys.path.insert(0, str(ROOT / "W47 face level carried to the face"))
sys.path.insert(0, str(ROOT / "W48 aligned cells race excess"))
import gorge_reading as gr  # noqa: E402  (registers the gorge cases)
import wave_probe as wp  # noqa: E402

W49 = MAIN / "W49 local hydraulic radius face table" / "probe_top_fix"
W48 = MAIN / "W48 aligned cells race excess" / "probe"
GROUND = {"narrow": W49 / "narrow", "narrow_sine": W49 / "narrow_sine", "narrow_gentle": W48 / "narrow_gentle"}
"""Where each case's dem.tif, thalweg.gpkg and domain.geojson are."""
REFERENCE = {"narrow": W49 / "narrow", "narrow_sine": W49 / "narrow_sine", "narrow_gentle": HERE / "runs" / "narrow_gentle"}
"""Where each case's runs on squares with the local radius are (W49 ran no gentle sine: its squares are run here)."""
RUNS = HERE / "runs"
JOBS = HERE / "jobs"
wp.MESHES.update({"sq2": (2.0, False), "ce5": (5.0, True)})


def job(case: str, mesh: str, tag: str = "", strips: dict | None = None, tables: dict | None = None, **top) -> tuple[str, dict]:
    """A steady job of a case on a mesh of `wave_probe.MESHES`, the ground read from the main checkout, the cache
    here; `strips` and `tables` are merged into their sections, `top` into the job. Returns its name and the job."""
    wp.OUT = RUNS  # never the folders of W46, W48 or W49
    data = wp.job(case, "steady", mesh)
    ground = GROUND[case]
    data["grid"]["domain"] = str(ground / "domain.geojson")
    data["grid"]["cache_dir"] = str(HERE / "cache" / case)
    data["terrain"]["dem"] = str(ground / "dem.tif")
    data["outputs"]["map_every_s"] = 10_800.0
    data["tables"] = {"face_conveyance": "local_radius", **(tables or {})}
    if "strips" in data:
        data["strips"]["banks"] = str(ground / "thalweg.gpkg")
        data["strips"].update(strips or {})
    for key, value in top.items():
        data.setdefault(key, {}).update(value)
    name = f"{case}_{mesh}{('_' + tag) if tag else ''}"
    data["project"]["name"] = f"w52_{name}"
    return name, data


def run(name: str, data: dict, case: str, force: bool = False, runner: list[str] | None = None) -> dict:
    """Run a job through this checkout's engine unless its results are there; the 'done' line of its progress."""
    folder = RUNS / case / name
    JOBS.mkdir(parents=True, exist_ok=True)
    path = JOBS / f"{name}.json"
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    if force or not (folder / "results.h5").is_file():
        folder.parent.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, PYTHONPATH=str(ROOT))
        t0 = time.perf_counter()
        command = runner or [sys.executable, "-m", "wadi2d.engine.cli"]
        done = subprocess.run([*command, "run", str(path), "--out", str(folder)], capture_output=True, text=True, cwd=ROOT, env=env)
        (JOBS / f"{name}.log").write_text(done.stdout + "\n" + done.stderr, encoding="utf-8")
        print(f"{name}: exit {done.returncode} in {time.perf_counter() - t0:.0f} s", flush=True)
    return done_line(folder)


def done_line(folder: Path) -> dict:
    progress = folder / "progress.jsonl"
    if not progress.is_file():
        return {}
    lines = progress.read_text(encoding="utf-8").splitlines()
    done = [json.loads(s) for s in lines if '"done"' in s[:14]]
    out = done[-1] if done else {}
    strips = [json.loads(s) for s in lines if '"ev": "strips"' in s]
    if strips:
        out["strips"] = {k: strips[-1].get(k) for k in ("cells", "triangles", "replaced", "rules")}
    return out


def read(case: str, runs: dict[str, Path], reference: Path | None = None, x_to: float = gr.X_TO) -> dict:
    """W48's reading of runs of one case against the 2 m squares of the same table rule: depth on the axis (the
    level 3 m either side of it, the median between 1 and 8 km), the level against the reference, and the water
    held between 1 and 7 km against it."""
    import rasterio
    from rasterio.windows import from_bounds

    c = wp.CASES[case]
    reference = reference or (REFERENCE[case] / f"{case}_steady_sq2")
    with rasterio.open(GROUND[case] / "dem.tif") as src:
        win = from_bounds(wp.X0 + gr.X_FROM, wp.Y0, wp.X0 + x_to, wp.Y0 + wp.WIDTH, src.transform).round_offsets().round_lengths()
        z = src.read(1, window=win).astype(np.float64)
        tr = src.window_transform(win)
        pix = src.res[0]
    pts, arc = wp.curve(c["amp"])
    x = wp.X0 + np.arange(gr.X_FROM + 50.0, x_to - 50.0, 5.0)
    k = np.searchsorted(pts[:, 0], x)
    tang = pts[np.minimum(k + 1, len(pts) - 1)] - pts[np.maximum(k - 1, 0)]
    tang /= np.hypot(tang[:, 0], tang[:, 1])[:, None]
    nrm = np.column_stack((-tang[:, 1], tang[:, 0]))
    axis = pts[k]
    bed = 200.0 - arc[k] * wp.S_BED
    upto7 = (tr.c + (np.arange(z.shape[1]) + 0.5) * tr.a) <= wp.X0 + 7000.0

    def one(folder: Path) -> tuple[dict, np.ndarray]:
        s = gr.surface(folder, z.shape, tr)
        depth = np.clip(s - z, 0.0, None)
        lv = []
        for sign in (-1.0, 1.0):
            q = axis + sign * gr.SIDE_M * nrm
            col = np.clip(((q[:, 0] - tr.c) / tr.a).astype(int), 0, z.shape[1] - 1)
            row = np.clip(((q[:, 1] - tr.f) / tr.e).astype(int), 0, z.shape[0] - 1)
            lv.append(s[row, col])
        lev = 0.5 * (lv[0] + lv[1])
        return {
            "depth_axis_m": float(np.nanmedian(lev - bed)),
            "water_m3": float(np.nansum(depth)) * pix * pix,
            "water_1_7km_m3": float(np.nansum(depth[:, upto7])) * pix * pix,
        }, lev

    ref, ref_lev = one(reference)
    out = {"sq2": ref}
    for label, folder in runs.items():
        if not (folder / "results.h5").is_file():
            continue
        r, lev = one(folder)
        r["level_vs_sq2_m"] = float(np.nanmedian(lev - ref_lev))
        r["water_vs_sq2"] = r["water_m3"] / ref["water_m3"] - 1
        r["water_1_7km_vs_sq2"] = r["water_1_7km_m3"] / ref["water_1_7km_m3"] - 1
        done = done_line(folder)
        if done:
            r |= {"steps": done.get("steps"), "loop_s": done.get("loop_s"), "tables_s": done.get("tables_s"), "dt_min_s": done.get("dt_min"),
                  "mass_error": done.get("balance", {}).get("relative_error")}
            if "strips" in done:
                r["strip_cells"] = done["strips"]["cells"]
        out[label] = r
    return out


def show(case: str, res: dict) -> None:
    print(f"\n{case}: steady 300 m3/s; depth on the axis 1 to 8 km, level against the 2 m squares, water held 1 to 7 km against them, steps, loop s, smallest step s")
    for label, r in res.items():
        if "level_vs_sq2_m" not in r:
            print(f"  {label:22s} depth {r['depth_axis_m']:.3f} m  (reference)")
            continue
        steps = f"{r['steps']:>7d}" if r.get("steps") else "      ?"
        print(f"  {label:22s} depth {r['depth_axis_m']:.3f} m  level {r['level_vs_sq2_m']:+.3f} m  water {100 * r['water_1_7km_vs_sq2']:+.2f} %"
              f"  {steps}  {r.get('loop_s') or 0:6.1f}  {r.get('dt_min_s') or 0:.3f}" + (f"  strip cells {r['strip_cells']}" if "strip_cells" in r else ""))
