"""W105 (c): every job file in the repository with a lumped network, read by the engine before W105 and after it.

``dump <code root> <out.json>`` reads each job with the engine found at ``<code root>`` (a frozen copy of the base
commit, or this branch) and writes, per job: its hash, the job as the engine resolves it (``_resolved``: on an HMS job
with the lumped water on the network, the inflows it makes), each lumped subbasin's rain depth over the event, and each
hydrograph entering the grid (peak, volume, the point, the entry rule). No grid, no solver, no GPU. ``compare <before>
<after> <out.json>`` lists what differs, job by job, and whether the job states storm areas or inflows of its own.

Run from the repository root with the venv, once per code root:
``.venv\\Scripts\\python "W105 dams end the lumped model\\scripts\\old_jobs.py" dump <root> <file>``.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def job_files() -> list[Path]:
    """Every tracked JSON file that is a job: a ``hydrology`` and a ``terrain`` section, with a lumped network."""
    names = subprocess.run(["git", "ls-files", "*.json"], cwd=REPO, capture_output=True, text=True, check=True).stdout
    found = []
    for name in names.splitlines():
        path = REPO / name
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict) or not isinstance(data.get("hydrology"), dict) or "terrain" not in data:
            continue
        h = data["hydrology"]
        if h.get("hms_basin") or h.get("basin_json"):
            found.append(path)
    return found


def states(data: dict) -> dict:
    h = data.get("hydrology") or {}
    return {
        "storm_areas": any(s.get("storm_area_km2") is not None for s in h.get("subbasins") or []),
        "inflows": bool(h.get("inflows")),
        "lumped_entry": h.get("lumped_entry", "outlet"),
        "lumped_curve": ((data.get("storm") or {}).get("area_reduction") or {}).get("lumped", {}) is not None
        and (((data.get("storm") or {}).get("area_reduction") or {}).get("lumped") or {}).get("form") == "curve",
    }


def dump(root: Path, out: Path) -> None:
    sys.path.insert(0, str(root))
    import numpy as np
    import rasterio

    from wadi2d import run as R
    from wadi2d.forcing import build_storm

    assert Path(R.__file__).resolve().is_relative_to(root.resolve()), R.__file__
    result = {"root": str(root), "jobs": {}}
    for path in job_files():
        key = str(path.relative_to(REPO))
        data = json.loads(path.read_text(encoding="utf-8"))
        row = {"states": states(data)}
        t0 = time.monotonic()
        try:
            cfg = R.load_job(path)
            crs = ""
            if cfg.terrain.dem is not None and Path(cfg.terrain.dem).is_file():
                with rasterio.open(cfg.terrain.dem) as dem:
                    crs = dem.crs.to_wkt() if dem.crs is not None else ""
            row["hash"] = R.job_hash(cfg)
            resolved = R._resolved(cfg, crs)[0]
            row["resolved_hydrology"] = json.loads(resolved.hydrology.model_dump_json())
            storm = build_storm(resolved)
            basin, hms_basin, decided = R._lumped_basin(resolved, crs)
            if storm is not None:
                rain = R._lumped_rain(resolved, storm, basin, hms_basin, crs, decided)
                steps = int(np.ceil(resolved.run.duration_s / 60.0 / resolved.hydrology.time_step_min))
                row["depth_mm"] = {
                    name: float(rain.over(name).increments(resolved.hydrology.time_step_min, steps).sum())
                    for name in basin.subbasins
                }
            if not resolved.run.lumped_only:
                flows = R._network(resolved, storm, crs)[0]
                entry = {i.name: i.entry for i in resolved.hydrology.inflows}
                row["entries"] = {
                    name: {"point": [float(point[0]), float(point[1])] if point is not None else None,
                           "peak": float(np.max(q)) if len(q) else 0.0,
                           "volume": float(np.trapezoid(np.asarray(q, float), np.asarray(t, float))) if len(q) else 0.0,
                           "rule": entry.get(name)}
                    for name, point, t, q in flows
                }  # fmt: skip
        except Exception as error:  # a job whose files are not on this machine, or that the engine refuses
            row["error"] = f"{type(error).__name__}: {error}"
            row["trace"] = traceback.format_exc(limit=3)
        row["seconds"] = round(time.monotonic() - t0, 2)
        result["jobs"][key] = row
        print(key, "error" if "error" in row else "ok", row["seconds"], flush=True)
    out.write_text(json.dumps(result, indent=1), encoding="utf-8")


def _close(a, b, rel: float = 1e-12) -> bool:
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_close(a[k], b[k], rel) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_close(x, y, rel) for x, y in zip(a, b, strict=True))
    if isinstance(a, float) and isinstance(b, float):
        return abs(a - b) <= rel * max(abs(a), abs(b), 1e-30)
    return a == b


def compare(before: Path, after: Path, out: Path) -> None:
    old = json.loads(before.read_text(encoding="utf-8"))["jobs"]
    new = json.loads(after.read_text(encoding="utf-8"))["jobs"]
    rows = {}
    for key in sorted(old):
        a, b = old[key], new.get(key, {})
        row = {"states": a["states"]}
        if "error" in a or "error" in b:
            row["error_before"], row["error_after"] = a.get("error"), b.get("error")
            row["same"] = a.get("error") == b.get("error")
        else:
            after = b.get("resolved_hydrology") or {}
            if after.get("last_points", "set") is None and "last_points" not in (a.get("resolved_hydrology") or {}):
                b = {**b, "resolved_hydrology": {k: v for k, v in after.items() if k != "last_points"}}  # the new field, unset
            moved = [part for part in ("hash", "resolved_hydrology", "depth_mm", "entries") if not _close(a.get(part), b.get(part))]
            row["moved"] = moved
            row["same"] = not moved
            if "depth_mm" in moved:
                row["depth_changed"] = {n: [a["depth_mm"][n], b["depth_mm"].get(n)] for n in a["depth_mm"]
                                        if not _close(a["depth_mm"][n], b["depth_mm"].get(n))}  # fmt: skip
            if "entries" in moved:
                row["entries_before"] = sorted(a.get("entries") or {})
                row["entries_after"] = sorted(b.get("entries") or {})
        rows[key] = row
    summary = {
        "jobs": len(rows),
        "same": sum(1 for r in rows.values() if r["same"]),
        "read": sum(1 for r in rows.values() if "moved" in r),
        "errors_both": sum(1 for r in rows.values() if "error_before" in r),
        "moved": {k: r for k, r in rows.items() if not r["same"]},
    }
    out.write_text(json.dumps({"summary": summary, "jobs": rows}, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "moved"}, indent=1))
    for key, row in summary["moved"].items():
        print("MOVED", key, json.dumps({k: v for k, v in row.items() if k in ("states", "moved", "error_before", "error_after")}))


if __name__ == "__main__":
    if sys.argv[1] == "dump":
        dump(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        compare(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
