"""Made-up cases for the aligned mesh's excess on the Faydh 01 race (W57, 2026-11-14).

The race (rain on the grid, peak at the dam axis) reads the centre mesh +3.5 % at 20 m and about +2 % at 10 m over
the converged 5 m squares, the 20 m squares -3.3 %. Steady gorges, straight or bending, do not reproduce it (W48,
W52). Four unsteady cases, cheapest first, each on squares 20, 10, 5, 2 m and the centre mesh 30, 20, 10, 5 m:

1. `wave`: a flash flood (50 -> 2,000 -> 50 m3/s, 40 min up, 80 min down) down W48's narrow tight-sine gorge
   (12 m bed, 7 m walls over 1.5 m, a 10 m ledge, hills at 50 %, radius 243 m at the bends, 1 %, n 0.05);
2. `junction45`, `junction90`: a tributary gorge joining a main gorge at 45 or 90 degrees, both with inflows;
3. `rain`, `rain_straight`: rain on the grid (70 mm in 4 h, 30 mm of it in 20 min) on the narrow gorge valleys,
   hills at 50 % draining into the one aligned gorge, tight sine and straight;
4. `plain`: the gorge opening into a wide plain and narrowing again, a flash flood through it.

Ground, the engine as `python -m wadi2d.engine.cli` from this worktree; runs and caches under `runs/` and `cache/`
here (out of git). The W48/W49 grounds are read from the main checkout, never written.

    .venv\\Scripts\\python "W57 made-up cases for the race excess\\race_cases.py" <case> [ground|run|report] [meshes...]
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
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "W46 centre-based mesh generator"))
import wave_probe as wp  # noqa: E402

W49 = MAIN / "W49 local hydraulic radius face table" / "probe_top_fix"
RUNS = HERE / "runs"
GROUND = HERE / "ground"
MESHES = {"sq20": (20.0, False), "sq10": (10.0, False), "sq5": (5.0, False), "sq2": (2.0, False),
          "ce30": (30.0, True), "ce20": (20.0, True), "ce10": (10.0, True), "ce5": (5.0, True)}
NARROW = dict(bed_half=6.0, bank_run=1.5, depth=7.0, plain_w=10.0, plain_slope=0.05, hill=0.5)
FLASH = dict(times_s=[0.0, 1_800.0, 4_200.0, 9_000.0, 14_400.0], flows=[50.0, 50.0, 2_000.0, 50.0, 50.0])
"""A Faydh-sized flash flood: 2,000 m3/s, 40 min up, 80 min down, half-peak width 60 min (Faydh's 50)."""

import ground as gd  # noqa: E402


def junction_job(case: str, mesh: str) -> dict:
    """Inflows at both heads, 0.6 and 0.4 of the flash flood, peaking together; lines on each reach."""
    c = CASES[case]
    dx, centres = MESHES[mesh]
    g = Path(c["ground"])
    geo = gd.junction_lines(c["angle"])
    flows = np.asarray(FLASH["flows"])
    data = {
        "project": {"name": f"w57_{case}_{mesh}", "description": "W57 made-up case: a tributary junction"},
        "grid": {"dx": dx, "domain": str(g / "domain.geojson"), "cache_dir": str(HERE / "cache" / case)},
        "terrain": {"dem": str(g / "dem.tif"), "pixel_stride": 1, "manning": wp.MANNING},
        "storm": {"kind": "none"},
        "hydrology": {"inflows": [
            {"name": "main", "x": geo["main_in"][0], "y": geo["main_in"][1], "times_s": FLASH["times_s"], "flows": list(0.6 * flows)},
            {"name": "trib", "x": geo["trib_in"][0], "y": geo["trib_in"][1], "times_s": FLASH["times_s"], "flows": list(0.4 * flows)},
        ], "inject_radius": 60.0},
        "boundaries": [{"kind": "normal", "slope": wp.S_BED, "coordinates": geo["boundary"]}],
        "outputs": {"map_every_s": 0.0, "series_every_s": 30.0, "live_every_s": 0.0,
                    "lines": [{"name": n, "coordinates": xy} for n, xy in geo["lines"].items()], "pixels": {"enabled": False}},
        "run": {"duration_s": c["duration"], "backend": "gpu", "source_every_s": 30.0, "checkpoint_every_s": 0.0},
    }
    if centres:
        data["strips"] = {"enabled": True, "generator": "centres", "banks": str(g / "thalweg.gpkg"), "along": dx}
    return data


def rotated_job(case: str, mesh: str) -> dict:
    """The rain case on W48's straight valley turned `angle` degrees off the lattice: the answer is the straight
    valley's on the lattice, so each mesh's error is its own."""
    c = CASES[case]
    dx, centres = MESHES[mesh]
    g = Path(c["ground"])
    geo = gd.rotated_lines(c["angle"], wp.SECTIONS)
    f = wp.FORCINGS["rain"]
    storm = {"kind": "hyetograph", "hyetograph_min": f["hyetograph_min"], "hyetograph_mm": f["hyetograph_mm"]}
    hydrology: dict = {}
    if c["forcing"] == "flash":
        fr = gd.rotated_frame(c["angle"])
        xin, yin = fr["o"] + wp.INFLOW_S * fr["d"]
        flows = [c["base"] if i in (0, 1, 3, 4) else q * c["scale"] for i, q in enumerate(FLASH["flows"])]
        storm = {"kind": "none"}
        hydrology = {"inflows": [{"name": "head", "x": float(xin), "y": float(yin), "times_s": FLASH["times_s"], "flows": flows}], "inject_radius": 60.0}
    data = {
        "project": {"name": f"w57_{case}_{mesh}", "description": "W57 made-up case: the straight valley turned off the lattice"},
        "grid": {"dx": dx, "domain": str(g / "domain.geojson"), "cache_dir": str(HERE / "cache" / case)},
        "terrain": {"dem": str(g / "dem.tif"), "pixel_stride": 1, "manning": wp.MANNING},
        "storm": storm,
        "hydrology": hydrology,
        "boundaries": [{"kind": "normal", "slope": wp.S_BED, "coordinates": geo["boundary"]}],
        "outputs": {"map_every_s": 0.0, "series_every_s": 30.0, "live_every_s": 0.0,
                    "lines": [{"name": n, "coordinates": xy} for n, xy in geo["lines"].items()], "pixels": {"enabled": False}},
        "run": {"duration_s": c["duration"], "backend": "gpu", "source_every_s": 30.0, "checkpoint_every_s": 0.0},
    }
    if centres:
        data["strips"] = {"enabled": True, "generator": "centres", "banks": str(g / "thalweg.gpkg"), "along": dx}
    return data


PLAIN_SECTIONS = {"s1": 1_500.0, "s2": 4_000.0, "s3": 7_500.0}
"""Above the plain, in its middle, and 2.4 km below it in the gorge again."""


CASES: dict[str, dict] = {
    "wave": dict(ground=W49 / "narrow_sine", amp=wp.AMP, forcing="flash", duration=14_400.0),
    "wave_low": dict(ground=W49 / "narrow_sine", amp=wp.AMP, forcing="flash", duration=14_400.0, scale=0.05, base=2.0),
    # the same flash flood at the rain case's own size: 2 -> 100 -> 2 m3/s, no rain (is it the rain or the low flow?)
    "rain": dict(ground=W49 / "narrow_sine", amp=wp.AMP, forcing="rain", duration=21_600.0),
    "rain_straight": dict(ground=W49 / "narrow", amp=0.0, forcing="rain", duration=21_600.0),
    "rain_rot30": dict(ground=GROUND / "rain_rot30", angle=30.0, forcing="rain", duration=21_600.0, job=rotated_job,
                       make_ground=lambda case: gd.rotated_ground(case, 30.0)),
    # the low inflow wave (no rain) down the straight valley, on the lattice and turned 30 degrees: channel or hills?
    "wave_low_straight": dict(ground=W49 / "narrow", amp=0.0, forcing="flash", duration=14_400.0, scale=0.05, base=2.0),
    "wave_low_rot30": dict(ground=GROUND / "rain_rot30", angle=30.0, forcing="flash", duration=14_400.0, scale=0.05, base=2.0,
                           job=rotated_job),
    # the rain split: 70 mm within 30 m of the axis only (bed, walls, ledge) or beyond it only (the hills)
    **{f"split_{w}_{k}": dict(ground=gr, angle=ang, forcing="rain", duration=21_600.0, split=w, cache_of=base,
                              **({"job": rotated_job} if ang else {"amp": 0.0}))
       for w in ("near", "hills") for k, gr, ang, base in (("straight", W49 / "narrow", 0.0, "rain_straight"),
                                                          ("rot30", GROUND / "rain_rot30", 30.0, "rain_rot30"))},
    # diagnosis variants of the rain case: one kernel or table switch at a time
    "rain_nocarry": dict(ground=W49 / "narrow_sine", amp=wp.AMP, forcing="rain", duration=21_600.0,
                         overrides={"numerics": {"face_depth_carry": False}}),
    "rain_stripsum": dict(ground=W49 / "narrow_sine", amp=wp.AMP, forcing="rain", duration=21_600.0,
                          overrides={"tables": {"face_conveyance": "strips"}}),
    "junction45": dict(ground=GROUND / "junction45", angle=45.0, forcing="flash", duration=14_400.0, job=junction_job,
                       make_ground=lambda case: gd.junction_ground(case, 45.0),
                       lines=("main_up", "trib", "main_dn", "outlet"), outlet="outlet", storage_between=(("main_up", "trib"), "outlet")),
    "junction90": dict(ground=GROUND / "junction90", angle=90.0, forcing="flash", duration=14_400.0, job=junction_job,
                       make_ground=lambda case: gd.junction_ground(case, 90.0),
                       lines=("main_up", "trib", "main_dn", "outlet"), outlet="outlet", storage_between=(("main_up", "trib"), "outlet")),
    "plain": dict(ground=GROUND / "plain", amp=gd.PLAIN_AMP, forcing="flash", duration=14_400.0, sections=PLAIN_SECTIONS,
                  make_ground=gd.plain_ground),
}


# ---------------------------------------------------------------- jobs and runs


def job(case: str, mesh: str) -> dict:
    c = CASES[case]
    dx, centres = MESHES[mesh]
    g = Path(c["ground"])
    if c.get("job"):
        return c["job"](case, mesh)
    pts, arc = wp.curve(c["amp"])
    xin, yin = wp.point_at(wp.INFLOW_S, pts, arc)
    hydrology: dict = {}
    if c["forcing"] == "flash":
        storm = {"kind": "none"}
        flash = dict(FLASH, flows=list(np.asarray(FLASH["flows"]) * c.get("scale", 1.0)))
        if c.get("base") is not None:
            flash["flows"] = [c["base"] if i in (0, 1, 3, 4) else q for i, q in enumerate(flash["flows"])]
        hydrology = {"inflows": [{"name": "head", "x": xin, "y": yin, **flash}], "inject_radius": 60.0}
    else:
        f = wp.FORCINGS["rain"]
        storm = {"kind": "hyetograph", "hyetograph_min": f["hyetograph_min"], "hyetograph_mm": f["hyetograph_mm"]}
    data = {
        "project": {"name": f"w57_{case}_{mesh}", "description": "W57 made-up case for the race excess"},
        "grid": {"dx": dx, "domain": str(g / "domain.geojson"), "cache_dir": str(HERE / "cache" / case)},
        "terrain": {"dem": str(g / "dem.tif"), "pixel_stride": 1, "manning": wp.MANNING},
        "storm": storm,
        "hydrology": hydrology,
        "boundaries": [{"kind": "normal", "slope": wp.S_BED, "coordinates": [[wp.X0 + wp.LENGTH - 5.0, wp.Y0], [wp.X0 + wp.LENGTH - 5.0, wp.Y0 + wp.WIDTH]]}],
        "outputs": {
            "map_every_s": 0.0, "series_every_s": 30.0, "live_every_s": 0.0,
            "lines": [{"name": n, "coordinates": [[wp.X0 + s, wp.Y0], [wp.X0 + s, wp.Y0 + wp.WIDTH]]} for n, s in c.get("sections", wp.SECTIONS).items()],
            "pixels": {"enabled": False},
        },
        "run": {"duration_s": c["duration"], "backend": "gpu", "source_every_s": 30.0, "checkpoint_every_s": 0.0},
    }
    if centres:
        data["strips"] = {"enabled": True, "generator": "centres", "banks": str(g / "thalweg.gpkg"), "along": dx}
    for key, value in c.get("overrides", {}).items():
        data.setdefault(key, {}).update(value)
    return data


def run(case: str, mesh: str, force: bool = False, backend: str | None = None) -> None:
    folder = RUNS / case / mesh
    if (folder / "results.h5").is_file() and not force:
        return
    data = job(case, mesh)
    c = CASES[case]
    if c.get("split"):
        grid = gd.split_grid(HERE / "cache" / "splits", Path(c["ground"]) / "dem.tif", c.get("angle", 0.0), c["split"])
        data["storm"] = {"kind": "hypothetical", "depth_mm": 70.0, "duration_min": 240.0, "time_percent": wp.PATTERN_T,
                         "depth_percent": wp.PATTERN_D, "depth_grid": str(grid)}
    if c.get("cache_of"):
        data["grid"]["cache_dir"] = str(HERE / "cache" / c["cache_of"])
    if backend:
        data["run"]["backend"] = backend
    folder.parent.mkdir(parents=True, exist_ok=True)
    path = RUNS / case / f"{mesh}.json"
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    t0 = time.perf_counter()
    done = subprocess.run([sys.executable, "-m", "wadi2d.engine.cli", "run", str(path), "--out", str(folder)],
                          capture_output=True, text=True, cwd=ROOT, env=env)
    (RUNS / case / f"{mesh}.log").write_text(done.stdout + "\n" + done.stderr, encoding="utf-8")
    print(f"{case} {mesh}: exit {done.returncode} in {time.perf_counter() - t0:.0f} s", flush=True)
    if done.returncode:
        print(done.stderr[-2000:], flush=True)


# ---------------------------------------------------------------- reading


def series(folder: Path, line: str) -> tuple[np.ndarray, np.ndarray]:
    a = np.loadtxt(folder / "series" / f"line_{line}.csv", delimiter=",", skiprows=1, ndmin=2)
    return a[:, 0], np.abs(a[:, 1])


def read(case: str, meshes: list[str]) -> dict:
    c = CASES[case]
    lines = c.get("lines", ("s1", "s2", "s3"))
    up, out_line = c.get("storage_between", ("s1", "s3"))
    res: dict = {}
    for mesh in meshes:
        folder = RUNS / case / mesh
        prog = folder / "progress.jsonl"
        if not prog.is_file():
            continue
        text = prog.read_text(encoding="utf-8").splitlines()
        done = [json.loads(s) for s in text if '"done"' in s[:14]]
        if not done:
            continue
        built = [json.loads(s) for s in text if '"ev": "strips"' in s]
        r: dict = {}
        for name in lines:
            t, q = series(folder, name)
            r[name] = {"peak": float(q.max()), "at_min": float(t[q.argmax()] / 60.0), "volume_m3": float(np.trapezoid(q, t))}
        if c["forcing"] != "rain":
            ups = (up,) if isinstance(up, str) else up
            t1, q1 = series(folder, ups[0])
            for extra in ups[1:]:
                te, qe = series(folder, extra)
                q1 = q1 + np.interp(t1, te, qe)
            t3, q3 = series(folder, out_line)
            q3 = np.interp(t1, t3, q3)
            stored = np.concatenate(([0.0], np.cumsum(0.5 * (q1[1:] - q3[1:] + q1[:-1] - q3[:-1]) * np.diff(t1))))
            r["stored_max_m3"] = float(stored.max())
        d = done[-1]
        r |= {"steps": d["steps"], "loop_s": d["loop_s"], "tables_s": d.get("tables_s"), "dt_min": d.get("dt_min"),
              "mass_error": d["balance"]["relative_error"], "storage_end_m3": d["balance"]["storage_end_m3"]}
        if built:
            r["strip_cells"] = built[-1].get("cells")
        res[mesh] = r
    return res


def report(case: str, meshes: list[str]) -> dict:
    res = read(case, meshes)
    c = CASES[case]
    ref_name = next((m for m in ("sq2", "sq5") if m in res), None)
    out_line = c.get("outlet", "s3")
    if not ref_name:
        print("no reference run")
        return res
    ref = res[ref_name]
    print(f"\n{case}: peak at {out_line} against {ref_name} ({ref[out_line]['peak']:.1f} m3/s at {ref[out_line]['at_min']:.1f} min)")
    for mesh, r in res.items():
        p = r[out_line]
        rel = 100 * (p["peak"] / ref[out_line]["peak"] - 1)
        others = "  ".join(f"{n} {100 * (r[n]['peak'] / ref[n]['peak'] - 1):+.2f} %" for n in c.get("lines", ("s1", "s2", "s3")) if n != out_line)
        st = f"  stored {100 * (r['stored_max_m3'] / ref['stored_max_m3'] - 1):+.2f} %" if "stored_max_m3" in r else ""
        vol = f"  vol {100 * (p['volume_m3'] / ref[out_line]['volume_m3'] - 1):+.2f} %"
        print(f"  {mesh:5s} {p['peak']:8.1f} {rel:+6.2f} %  t {p['at_min'] - ref[out_line]['at_min']:+5.1f} min{st}{vol}  [{others}]"
              f"  steps {r['steps']}  loop {r['loop_s']:.0f} s" + (f"  strip {r['strip_cells']}" if r.get("strip_cells") else ""))
    (RUNS / case).mkdir(parents=True, exist_ok=True)
    (RUNS / case / "report.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    (HERE / f"{case}.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    return res


if __name__ == "__main__":
    case = sys.argv[1]
    what = [a for a in sys.argv[2:] if a in ("ground", "run", "report")] or ["run", "report"]
    meshes = [a for a in sys.argv[2:] if a in MESHES] or list(MESHES)
    backend = "cpu" if "--cpu" in sys.argv else None
    if "ground" in what and CASES[case].get("make_ground"):
        CASES[case]["make_ground"](case)
    if "run" in what:
        for mesh in meshes:
            run(case, mesh, force="--force" in sys.argv, backend=backend)
    if "report" in what:
        report(case, meshes)
