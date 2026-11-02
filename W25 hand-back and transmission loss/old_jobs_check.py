"""Old jobs give their numbers to the last digit: run a set of jobs and fingerprint everything they write.

Run it once with the code of `main` before this work and once with this branch, then compare:

    python old_jobs_check.py run <label> <work folder>       # the wadi2d on sys.path is the one tested
    python old_jobs_check.py prints <label> <work folder>     # fingerprint runs already made
    python old_jobs_check.py compare <a.json> <b.json> [<a_again.json>]

A second run of the base code shows what the base code does not repeat by itself: the rain and inflow sums are
credited at progress ticks, which the wall clock times, so their last digit can move from run to run.

Every dataset and numeric attribute of results.h5, every GeoTIFF band under the run folder, every series CSV and the
numbers of the done event are hashed one by one, so a difference names itself. Run times are left out; nothing else.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import h5py
import numpy as np
import rasterio

HERE = Path(__file__).resolve().parent
BLOCK2_JOB = (
    HERE.parent / "W1 research and design note" / "validation" / "block2_full" / "jobs" / "arf_b20_n100.json"
)
TIMING = {"loop_s", "tables_s", "wall"}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def fingerprint(out: Path) -> dict[str, str]:
    prints: dict[str, str] = {}
    with h5py.File(out / "results.h5", "r") as f:

        def visit(name, item):
            if isinstance(item, h5py.Dataset):
                prints[f"h5:{name}"] = digest(np.ascontiguousarray(item[()]).tobytes())

        f.visititems(visit)
        for key, value in sorted(f.attrs.items()):
            if key != "config" and isinstance(value, (int, float, np.number)):
                prints[f"h5.attr:{key}"] = repr(float(value))
    for tif in sorted(out.rglob("*.tif")):
        if "live" in tif.parts:
            continue
        with rasterio.open(tif) as src:
            h = hashlib.sha256()
            for _index, window in src.block_windows(1):
                h.update(src.read(window=window).tobytes())
            prints[f"tif:{tif.relative_to(out).as_posix()}"] = h.hexdigest()[:16]
    for csv in sorted((out / "series").glob("*.csv")):
        prints[f"csv:{csv.name}"] = digest(csv.read_bytes())
    events = [json.loads(s) for s in (out / "progress.jsonl").read_text(encoding="utf-8").splitlines()]
    done = [e for e in events if e["ev"] == "done"][-1]
    for key, value in sorted(done.items()):
        if key in TIMING or key == "ev":
            continue
        if key == "balance":
            for name, figure in sorted(value.items()):
                prints[f"done.balance:{name}"] = repr(figure)
        else:
            prints[f"done:{key}"] = repr(value)
    return prints


def jobs(work: Path):
    """(name, job) pairs; everything they read is written here first, the same bytes for both codes."""
    sys.path.insert(0, str(HERE.parent))
    from tests.engine.conftest import X0, Y0, job, write_dem
    from tests.engine.test_run import full_job, valley
    from wadi2d.config.schema import RunConfig

    work.mkdir(parents=True, exist_ok=True)
    valley_dem = write_dem(work / "valley.tif", valley(256, 192, 2.0), 2.0)
    yield "valley_rain_cn_cpu", full_job(valley_dem, "cpu", 2400.0)
    yield "valley_rain_cn_gpu", full_job(valley_dem, "gpu", 2400.0)
    base = full_job(valley_dem, "gpu", 2400.0).model_dump()
    base["storm"] = {
        "kind": "hyetograph",
        "hyetograph_min": [10.0, 20.0, 30.0],
        "hyetograph_mm": [5.0, 20.0, 5.0],
    }
    base["numerics"]["local_time_stepping"] = True
    yield "valley_hyetograph_lts_gpu", RunConfig.model_validate(base)
    plane = write_dem(work / "plane.tif", np.tile(100.0 - 0.01 * (np.arange(256) + 0.5) * 2.0, (64, 1)), 2.0)
    ring = [
        (X0 + 300.0, Y0 - 4.0),
        (X0 + 500.0, Y0 - 4.0),
        (X0 + 500.0, Y0 - 124.0),
        (X0 + 300.0, Y0 - 124.0),
    ]
    yield "plane_table_inflow_stage_initial_cpu", job(
        plane, 128, 32, 4.0,
        terrain={"manning": 0.03},
        hydrology={"inflows": [{"name": "F", "x": X0 + 40.0, "y": Y0 - 64.0, "times_s": [0.0, 600.0, 1200.0],
                                "flows": [0.0, 8.0, 0.0]}]},
        initial_levels=[{"coordinates": ring, "level": 97.0}],
        boundaries=[{"kind": "stage", "stage": 96.5, "coordinates": [(X0 + 510.0, Y0), (X0 + 510.0, Y0 - 128.0)]}],
        run={"duration_s": 3000.0, "backend": "cpu"},
    )  # fmt: skip
    from tests.engine.test_mesh_paths import BASIN, MESH, NX, NY, _west, flat

    basin = work / "one.basin"
    basin.write_text(BASIN, encoding="utf-8")
    mesh_dir = work / "mesh"
    mesh_dir.mkdir(exist_ok=True)
    yield "mesh_lumped_hms_cpu", job(
        flat(mesh_dir), NX, NY, 4.0, mesh=MESH,
        storm={"kind": "uniform", "depth_mm": 20.0, "duration_min": 20.0},
        hydrology={"hms_basin": str(basin), "polygons": str(_west(mesh_dir)),
                   "subbasins": [{"name": "West", "mode": "lumped", "outlet": (X0 + 300.0, Y0 - 120.0)}],
                   "inject_radius": 12.0},
        run={"duration_s": 3600.0, "backend": "cpu", "source_every_s": 60.0},
    )  # fmt: skip
    if BLOCK2_JOB.is_file():
        data = json.loads(BLOCK2_JOB.read_text(encoding="utf-8"))
        data["grid"]["dx"] = 40.0
        data["grid"]["cache_dir"] = str(work / "cache_block2")
        data["run"]["duration_s"] = 6 * 3600.0
        data["run"]["backend"] = "gpu"
        data["run"]["checkpoint_every_s"] = 0.0
        data["outputs"]["live_every_s"] = 0.0
        yield "block2_hybrid_40m_6h_gpu", RunConfig.model_validate(data)


def run(label: str, work: Path) -> None:
    import wadi2d
    from wadi2d.run import resolve_paths, run_job

    result = {"wadi2d": wadi2d.__file__, "jobs": {}}
    for name, cfg in jobs(work):
        if name.startswith("block2"):
            cfg = resolve_paths(cfg, BLOCK2_JOB.parent)
        out = work / label / name
        summary = run_job(cfg, out)
        result["jobs"][name] = {
            "exit": summary.exit_code,
            "message": summary.message,
            "prints": fingerprint(out),
        }
        print(name, summary.exit_code, summary.message, flush=True)
    (HERE / f"old_jobs_{label}.json").write_text(json.dumps(result, indent=1), encoding="utf-8")


def prints(label: str, work: Path) -> None:
    """Fingerprint runs already made, by their folders: a run need not be repeated to be checked."""
    import wadi2d

    result = {"wadi2d": wadi2d.__file__, "jobs": {}}
    for out in sorted(p for p in (work / label).iterdir() if (p / "results.h5").is_file()):
        events = [json.loads(s) for s in (out / "progress.jsonl").read_text(encoding="utf-8").splitlines()]
        done = [e for e in events if e["ev"] == "done"][-1]
        result["jobs"][out.name] = {"exit": done["code"], "message": "", "prints": fingerprint(out)}
    (HERE / f"old_jobs_{label}.json").write_text(json.dumps(result, indent=1), encoding="utf-8")


def compare(a: Path, b: Path, noise: Path | None = None) -> int:
    left, right = (json.loads(p.read_text(encoding="utf-8")) for p in (a, b))
    again = json.loads(noise.read_text(encoding="utf-8")) if noise is not None else {"jobs": {}}
    print(f"{a.name}: {left['wadi2d']}\n{b.name}: {right['wadi2d']}")
    bad = 0
    for name in sorted(set(left["jobs"]) | set(right["jobs"])):
        x, y = left["jobs"].get(name), right["jobs"].get(name)
        if x is None or y is None:
            print(f"{name}: only in one run")
            bad += 1
            continue
        keys = set(x["prints"]) | set(y["prints"])
        differ = sorted(k for k in keys if x["prints"].get(k) != y["prints"].get(k))
        z = again["jobs"].get(name, {"prints": x["prints"]})["prints"]
        unstable = {k for k in differ if z.get(k) != x["prints"].get(k)}
        same = len(keys) - len(differ)
        print(f"{name}: exit {x['exit']} / {y['exit']}, {same} of {len(keys)} items identical")
        for key in differ:
            why = "  (the base code itself does not repeat this one)" if key in unstable else ""
            print(f"    differs: {key}: {x['prints'].get(key)} / {y['prints'].get(key)}{why}")
        bad += len(set(differ) - unstable) + (x["exit"] != y["exit"])
    return 1 if bad else 0


if __name__ == "__main__":
    if sys.argv[1] == "run":
        run(sys.argv[2], Path(sys.argv[3]))
    elif sys.argv[1] == "prints":
        prints(sys.argv[2], Path(sys.argv[3]))
    else:
        noise = Path(sys.argv[4]) if len(sys.argv) > 4 else None
        sys.exit(compare(Path(sys.argv[2]), Path(sys.argv[3]), noise))
