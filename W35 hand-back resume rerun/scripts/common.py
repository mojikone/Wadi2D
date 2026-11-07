"""Shared pieces of the W32 combination tests: paths, the Bidah job template, running the engine, reading a run.

Every run goes through ``wadi2d.engine.cli.main`` in a subprocess of the project venv, with this worktree first on the
path, so the engine under test is this checkout's. Nothing here writes outside the run folder it is given.
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
REPO = HERE.parents[1]
VENV = REPO / ".venv" / "Scripts" / "python.exe"
if not VENV.exists():
    VENV = Path(r"D:\Mojtaba\Renardet\Wadi2D\.venv\Scripts\python.exe")
BLOCK = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology")
VALIDATION = REPO / "W1 research and design note" / "validation" / "block2_full"
DEM_5M = BLOCK / "Terrain" / "GGC_2_MERGE_HDSM_5.tif"
CN = BLOCK / "HEC_HMS_Block_02" / "Hydrology Data" / "CN_Include_Hill_Area.tif"
DOMAIN_BIDAH = VALIDATION / "domain_Bidah03.geojson"
DAM_JOB = VALIDATION / "jobs" / "dam_Bidah03_100yr_20.json"
STORM_JOB = VALIDATION / "jobs" / "c10_A74_h100.json"
OUTLETS = [
    {"kind": "normal", "slope": 0.008, "coordinates": [[440290.0, 2725700.0], [440290.0, 2728700.0]]},
    {"kind": "normal", "slope": 0.008, "coordinates": [[437300.0, 2728690.0], [440300.0, 2728690.0]]},
]
AXIS = [[438259.32, 2727264.77], [438807.68, 2726752.81]]
DAM_LINE = [[438100.0, 2727420.0], [438259.32, 2727264.77], [438807.68, 2726752.81], [438870.0, 2726640.0]]
"""W1's Bidah 03 design line: the axis with both ends carried up the abutments."""
BIDAH_AREA_KM2 = 20.971


def dam_objects(named: bool = True) -> list[dict]:
    """The dam's three crest pieces and its spillway from the W1 routing job; the longest piece is the dam, as W27 did."""
    job = json.loads(DAM_JOB.read_text(encoding="utf-8"))
    crests = [o for o in job["terrain"]["objects"] if o["kind"] == "crest_line"]
    spillway = next(o for o in job["terrain"]["objects"] if o["kind"] == "spillway")
    longest = max(crests, key=lambda o: len(o["coordinates"]))
    out = []
    for n, o in enumerate(crests, 1):
        piece = dict(o)
        if named:
            piece["name"] = "Bidah 03" if o is longest else f"saddle {n}"
        out.append(piece)
    out.append(dict(spillway))
    return out


def design_storm(area_km2: float = BIDAH_AREA_KM2) -> dict:
    """Block 2's 100-yr storm of the W1 jobs, read at the Bidah drainage area."""
    storm = dict(json.loads(STORM_JOB.read_text(encoding="utf-8"))["storm"])
    storm["storm_area_km2"] = area_km2
    return storm


def bidah_job(name: str, cache: Path, dx: float = 20.0, hours: float = 3.0, backend: str = "auto", **parts) -> dict:
    """Block 2's ground around Bidah at ``dx``, the dam objects, the CN raster, W27's outlets; 60 mm in an hour unless
    ``storm`` is given."""
    job = {
        "project": {"name": name, "description": "W32 combinations test"},
        "grid": {"dx": dx, "domain": str(DOMAIN_BIDAH), "cache_dir": str(cache)},
        "terrain": {"dem": str(DEM_5M), "manning": 0.05, "cn_raster": str(CN), "objects": dam_objects()},
        "storm": {"kind": "uniform", "depth_mm": 60.0, "duration_min": 60.0},
        "hydrology": {},
        "boundaries": OUTLETS,
        "outputs": {
            "map_every_s": 0.0, "live_every_s": 0.0, "series_every_s": 60.0,
            "pixels": {"enabled": False}, "smooth": {"enabled": False},
            "lines": [{"name": "Bidah 03", "coordinates": DAM_LINE}, {"name": "axis", "coordinates": AXIS}],
        },
        "run": {"duration_s": hours * 3600.0, "backend": backend, "source_every_s": 30.0, "checkpoint_every_s": 0.0},
    }  # fmt: skip
    for key, value in parts.items():
        if isinstance(value, dict) and isinstance(job.get(key), dict):
            job[key].update(value)
        else:
            job[key] = value
    return job


def write(job: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(job, indent=1), encoding="utf-8")
    return path


def engine(*args: str, log: Path | None = None, env: dict | None = None) -> tuple[int, float, str]:
    """``wadi2d <args>`` on this checkout's engine; returns exit code, wall seconds, and the text written."""
    code = (
        f"import sys; sys.path.insert(0, r'{REPO}'); from wadi2d.engine.cli import main; "
        f"sys.argv = ['wadi2d', *{list(args)!r}]; raise SystemExit(main())"
    )
    merged = dict(os.environ)
    if env:
        merged.update(env)
    start = time.monotonic()
    done = subprocess.run([str(VENV), "-c", code], capture_output=True, text=True, env=merged)
    wall = time.monotonic() - start
    text = done.stdout + done.stderr
    if log is not None:
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(text, encoding="utf-8")
    return done.returncode, wall, text


def python(code: str, *args: str, log: Path | None = None) -> tuple[int, float, str]:
    """Any code on the project venv with this checkout first on the path; the last JSON line is the answer."""
    head = f"import sys; sys.path.insert(0, r'{REPO}')\n"
    start = time.monotonic()
    done = subprocess.run([str(VENV), "-c", head + code, *[str(a) for a in args]], capture_output=True, text=True)
    wall = time.monotonic() - start
    text = done.stdout + done.stderr
    if log is not None:
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(text, encoding="utf-8")
    return done.returncode, wall, text


def last_json(text: str) -> dict:
    for line in reversed(text.splitlines()):
        if line.startswith(("{", "[")):
            return json.loads(line)
    return {}


def run(job: Path, out: Path, resume: bool = False, env: dict | None = None) -> tuple[int, float]:
    args = ["run", str(job), "--out", str(out)] + (["--resume"] if resume else [])
    code, wall, _ = engine(*args, log=out / "w32_engine.log", env=env)
    return code, wall


def events(folder: Path, kind: str) -> list[dict]:
    path = Path(folder) / "progress.jsonl"
    if not path.exists():
        return []
    return [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if f'"{kind}"' in s[:30]]


def done_event(folder: Path) -> dict:
    found = events(folder, "done")
    return found[-1] if found else {}


def balance(folder: Path) -> dict:
    return done_event(folder).get("balance", {})


def start_event(folder: Path) -> dict:
    found = events(folder, "start")
    return found[-1] if found else {}


def warnings(folder: Path) -> list[str]:
    return [e.get("message", "") for e in events(folder, "warn")]


def series(folder: Path, name: str) -> list[dict]:
    with (Path(folder) / "series" / f"{name}.csv").open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def peak(folder: Path, name: str, column: str | None = None) -> tuple[float, float]:
    """Largest |value| of a series and the hour it stands at."""
    rows = series(folder, name)
    column = column or next(k for k in rows[0] if k != "t_s")
    best = max(rows, key=lambda r: abs(float(r[column])))
    return abs(float(best[column])), float(best["t_s"]) / 3600.0


def volume(folder: Path, name: str, column: str) -> float:
    rows = series(folder, name)
    body = [(float(r["t_s"]), float(r[column])) for r in rows]
    return sum(0.5 * (a[1] + b[1]) * (b[0] - a[0]) for a, b in zip(body, body[1:], strict=False))


def line_peaks(folder: Path) -> dict[str, tuple[float, float]]:
    out = {}
    for f in sorted((Path(folder) / "series").glob("line_*.csv")):
        out[f.stem[5:]] = peak(folder, f.stem, "discharge_m3s")
    return out


def dump(obj, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")


def say(text: str) -> None:
    print(text, flush=True)


if __name__ == "__main__":
    print(REPO, VENV, sys.version)
