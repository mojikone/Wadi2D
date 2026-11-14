"""The owner's gridded storms through the engine on Bidah 03 at 30 m, one process per run, as W39 ran RP200.

usage: run_engine.py CODE_DIR OUT_ROOT SUMMARY.json SET [SET ...]      (venv python)

CODE_DIR is the checkout whose engine runs (this one, or an export of the base commit for the same-numbers check);
OUT_ROOT takes the run folders and the grid cache, and must lie outside the owner's folders. Sets:

- ``all24``: full 2D, rain-on-grid everywhere with the project CN grid, each of the 24 files, GPU, no area reduction.
- ``cpu``: two of them on the CPU twin.
- ``hms``: the hybrid on the HMS route, S13 lumped and the other 17 subbasins rain-on-grid, with and without the
  area reduction at S13's own 20.971 km2.
- ``arf``: full 2D with the area reduction at 20.971 km2, four storms, NetCDF and DSS.
- ``base``: the three jobs of the same-numbers check, no area reduction.

Every job is W39's: Bidah 03's domain, 30 m cells, the 5 m DEM, the two ``normal`` outlets at slope 0.01, the
``Bidah 03`` dam line, 30 h (48 h on the HMS route, from the control file), pixel products off.
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BLOCK = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology")
GRID = BLOCK / "Grid"
HMS = BLOCK / "HEC_HMS_Block_02"
VALIDATION = REPO / "W1 research and design note" / "validation" / "block2_full"
NAMES = ("RP5", "RP10", "RP25", "RP50", "RP100", "RP200", "RP500", "RP1000", "RP2000", "RP5000", "RP10000", "PMP")
DX = 30.0
HOURS = 30.0
LINE = "Bidah 03"
S13_KM2 = 20.971
FOREIGN_ENV = ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA", "GDAL_DRIVER_PATH")


def rain_file(name: str, fmt: str) -> Path:
    folder, suffix = ("netCDF", ".nc") if fmt == "nc" else ("DSS", ".dss")
    return GRID / folder / f"Precipitation_{name}_10min{suffix}"


def engine(code: Path, *args: str, timeout: float = 7200.0) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in FOREIGN_ENV}
    env["PYTHONPATH"] = str(code)
    return subprocess.run(
        [sys.executable, "-m", "wadi2d.engine.cli", *args], capture_output=True, text=True, env=env, cwd=str(code),
        timeout=timeout,
    )  # fmt: skip


def hms_import(code: Path, root: Path) -> dict:
    """The HMS project as a job: the network, the polygons, the control file's 48 h, and the ARF FM table."""
    out = root / "hms_import.json"
    if not out.is_file():
        done = engine(code, "hms-import", str(HMS), "--basin", "Basin_1.basin", "--met", "FM_100yr.met",
                      "--control", "Control_1.control", "--out", str(out))  # fmt: skip
        if done.returncode:
            raise RuntimeError(done.stderr[-2000:])
    return json.loads(out.read_text(encoding="utf-8"))


def base_job(root: Path, name: str) -> dict:
    dam = json.loads((VALIDATION / "jobs" / "dam_Bidah03_100yr_20.json").read_text(encoding="utf-8"))
    lines = json.loads((VALIDATION / "jobs" / "c10_A74_h100.json").read_text(encoding="utf-8"))["outputs"]["lines"]
    line = next(k for k in lines if k["name"] == LINE)
    return {
        "project": {"name": name},
        "grid": {"dx": DX, "cache_dir": str(root / "cache"), "domain": str(VALIDATION / "domain_Bidah03.geojson")},
        "terrain": {
            "dem": str(BLOCK / "Terrain" / "GGC_2_MERGE_HDSM_5.tif"),
            "manning": 0.035,
            "cn_raster": str(HMS / "Hydrology Data" / "CN_Include_Hill_Area.tif"),
        },
        "hydrology": {},
        "boundaries": [{"kind": "normal", "coordinates": k["coordinates"], "slope": 0.01} for k in dam["boundaries"]],
        "outputs": {"lines": [{"name": LINE, "coordinates": line["coordinates"]}], "map_every_s": 900.0,
                    "pixels": {"enabled": False}},
        "run": {"duration_s": HOURS * 3600.0},
    }  # fmt: skip


def make_job(code: Path, root: Path, run: dict) -> dict:
    job = base_job(root, run["name"])
    storm = {"kind": "gridded", "rain_file": str(rain_file(run["storm"], run["fmt"])), "rain_units": "auto",
             "rain_stamp": "end"}  # fmt: skip
    imported = hms_import(code, root) if run["mode"] == "hms" or run.get("area") else None
    if run.get("area"):
        storm.update(storm_area_km2=run["area"], arf=imported["storm"]["arf"])
    job["storm"] = storm
    if run["mode"] == "hms":
        hydrology = imported["hydrology"]
        for sub in hydrology["subbasins"]:
            sub["mode"] = "lumped" if sub["name"] == "S13" else "2d"
        job["hydrology"] = hydrology
        job["run"]["duration_s"] = imported["run"]["duration_s"]
    return job


def hydrograph(path: Path, column: str) -> dict:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    t = [float(r["t_s"]) for r in rows]
    q = [abs(float(r[column])) for r in rows]
    k = max(range(len(q)), key=q.__getitem__)
    volume = sum(0.5 * (q[i] + q[i + 1]) * (t[i + 1] - t[i]) for i in range(len(q) - 1))
    return {"peak_m3s": q[k], "peak_h": t[k] / 3600.0, "volume_m3": volume}


def one(code: Path, root: Path, run: dict) -> dict:
    out = root / run["name"]
    out.mkdir(parents=True, exist_ok=True)
    job_path = out / "job.json"
    job_path.write_text(json.dumps(make_job(code, root, run), indent=1), encoding="utf-8")
    t0 = time.monotonic()
    done = engine(code, "run", str(job_path), "--out", str(out), "--backend", run["backend"])
    entry = {**run, "exit_code": done.returncode, "wall_s": round(time.monotonic() - t0, 1)}
    events = [json.loads(s) for s in (out / "progress.jsonl").read_text(encoding="utf-8").splitlines()] if (out / "progress.jsonl").is_file() else []
    by = lambda kind: [e for e in events if e.get("ev") == kind]  # noqa: E731
    if done.returncode:
        entry["error"] = (by("error") or [{"message": done.stderr[-800:]}])[-1].get("message")
        return entry
    end = by("done")[-1]
    entry.update(
        backend_used=by("start")[-1]["backend"], cells=by("start")[-1]["cells"], steps=end["steps"],
        loop_s=end["loop_s"], balance=end["balance"],
        line=hydrograph(out / "series" / "line_Bidah_03.csv", "discharge_m3s"),
        area_reduction=[{k: e[k] for k in ("factor", "storm_area_km2", "arf_table_type")}
                        for e in events if e.get("kind") == "area_reduction"],
        warnings=[e["message"] for e in by("warn")],
    )  # fmt: skip
    design = out / "series" / "design_Bidah_03.csv"
    if design.is_file():
        entry["design_line"] = hydrograph(design, "total_m3s")
    network = out / "series" / "network_S13.csv"
    if network.is_file():
        entry["network_S13"] = hydrograph(network, "outflow_m3s")
    return entry


def plan(sets: list[str]) -> list[dict]:
    runs: list[dict] = []
    full = lambda storm, fmt, backend="gpu", area=None, tag="full": {  # noqa: E731
        "name": f"{tag}_{storm}_{fmt}" + ("_arf" if area else "") + ("_cpu" if backend == "cpu" else ""),
        "mode": "hms" if tag == "hms" else "full", "storm": storm, "fmt": fmt, "backend": backend, "area": area,
    }
    if "all24" in sets:
        runs += [full(name, fmt) for name in NAMES for fmt in ("nc", "dss")]
    if "cpu" in sets:
        runs += [full("RP100", "nc", "cpu"), full("PMP", "dss", "cpu")]
    if "arf" in sets:
        runs += [full(name, fmt, area=S13_KM2) for name in ("RP10", "RP100", "RP10000", "PMP") for fmt in ("nc", "dss")]
    if "hms" in sets:
        for storm, fmt in (("RP100", "nc"), ("RP100", "dss"), ("PMP", "nc")):
            runs += [full(storm, fmt, tag="hms"), full(storm, fmt, area=S13_KM2, tag="hms")]
        runs += [full("RP100", "nc", "cpu", area=S13_KM2, tag="hms")]
    if "base" in sets:
        runs += [full("RP200", "nc"), full("RP200", "dss"), full("RP100", "nc", tag="hms")]
    return runs


def main() -> None:
    code, root, target = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), Path(sys.argv[3])
    root.mkdir(parents=True, exist_ok=True)
    found = json.loads(target.read_text(encoding="utf-8")) if target.is_file() else {}
    found["code"] = str(code)
    for run in plan(sys.argv[4:]):
        entry = found.setdefault("runs", {})[run["name"]] = one(code, root, run)
        peak = entry.get("line", {}).get("peak_m3s")
        print(f"{run['name']}: exit {entry['exit_code']}, {entry.get('backend_used')}, peak {peak}, {entry['wall_s']} s "
              f"{entry.get('error', '')}", flush=True)  # fmt: skip
        target.write_text(json.dumps(found, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
