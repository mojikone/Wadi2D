"""Item 2: a generated basin (D6) with a gridded storm (D5) on Bidah.

The basin is generated at 2 km2 as W27 did. Two runs under the 100-yr design storm at the Bidah area, then the same two
with that storm written out as 5-minute GeoTIFF frames the way W20 did (``build_storm`` on the resolved job, one 2 x 2
pixel raster per period): all lumped by default, and one subbasin above the first reach junction in 2D. The rain-once
check must pass, the lumped hills and the 2D ground must take the same water from the frames as from the storm, and the
dam peaks must agree.

    python item2_gridded.py <scratch folder>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402
import jobs  # noqa: E402

FRAMES = """
import json, sys
from pathlib import Path
import numpy as np, rasterio
from rasterio.transform import from_origin
from wadi2d.config.schema import RunConfig
from wadi2d.forcing import build_storm
cfg = RunConfig.model_validate_json(Path(sys.argv[1]).read_text(encoding="utf-8"))
step = float(sys.argv[3]); storm = build_storm(cfg)
folder = Path(sys.argv[2]); folder.mkdir(exist_ok=True)
n = int(np.ceil(cfg.storm.duration_min / step))
for k, depth in enumerate(storm.increments(step, n)):
    with rasterio.open(folder / f"r{k:04d}.tif", "w", driver="GTiff", height=2, width=2, count=1, dtype="float64",
                       crs=sys.argv[4], transform=from_origin(*[float(v) for v in sys.argv[5:9]])) as dst:
        dst.write(np.full((2, 2), depth), 1)
print(json.dumps({"frames": n, "total": storm.total_depth}))
"""
RESULTS = Path(__file__).resolve().parents[1] / "results"


def main(scratch: Path) -> None:
    report: dict = {}
    gen = jobs.generate(scratch, "basin2", threshold=2.0)
    report["generation"] = gen
    c.say(f"generated: {jobs.summary(gen)}")
    basin = Path(gen["basin"])
    model = jobs.model(basin)
    subs = [e["name"] for e in model["elements"] if e["kind"] == "subbasin"]
    routes = {r["junction"]: r for r in model["routes"]}
    reach_junction = next(j for j, r in routes.items() if r["route"] == "reach")
    arm = next(e["name"] for e in model["elements"] if e["kind"] == "subbasin" and e["downstream"] == reach_junction)
    report["arm_in_2d"] = {"subbasin": arm, "junction": reach_junction}
    cache = scratch / "cache"

    runs = {}
    for label, two_d in (("storm_lumped", []), ("storm_arm2d", [arm])):
        job = c.write(jobs.lumped_default(label, basin, cache, two_d=two_d), scratch / "item2" / f"{label}.json")
        code, wall = c.run(job, scratch / "item2" / label)
        runs[label] = jobs.read_run(scratch / "item2" / label)
        runs[label]["wall_s"] = round(wall, 1)
        c.say(f"{label}: exit {code}, {runs[label]['balance']}")

    # the same storm as frames, from the resolved job of the lumped run, on a 2 x 2 pixel grid over the domain
    resolved = scratch / "item2" / "storm_lumped" / "config.resolved.json"
    bounds = json.loads(c.DOMAIN_BIDAH.read_text(encoding="utf-8"))
    xs = [p[0] for f in bounds["features"] for ring in f["geometry"]["coordinates"] for p in ring]
    ys = [p[1] for f in bounds["features"] for ring in f["geometry"]["coordinates"] for p in ring]
    pixel = max(max(xs) - min(xs), max(ys) - min(ys)) / 2.0 + 2000.0
    folder = scratch / "item2" / "rain_frames"
    code, wall, text = c.python(FRAMES, resolved, folder, 5.0, "EPSG:32640", min(xs) - 1000.0, max(ys) + 1000.0, pixel, pixel)
    frames = c.last_json(text)
    report["frames"] = {**frames, "exit": code, "folder": str(folder)}
    c.say(f"frames: {frames}")

    gridded = {"kind": "gridded", "rain_file": str(folder), "rain_interval_min": 5.0, "rain_units": "mm"}
    for label, two_d in (("frames_lumped", []), ("frames_arm2d", [arm])):
        job = jobs.lumped_default(label, basin, cache, two_d=two_d)
        job["storm"] = gridded
        path = c.write(job, scratch / "item2" / f"{label}.json")
        code, wall = c.run(path, scratch / "item2" / label)
        runs[label] = jobs.read_run(scratch / "item2" / label)
        runs[label]["wall_s"] = round(wall, 1)
        c.say(f"{label}: exit {code}, {runs[label]['balance']}")
    report["runs"] = runs

    checks = []

    def check(name, ok, detail=""):
        checks.append({"check": name, "pass": bool(ok), "detail": str(detail)[:300]})
        c.say(f"{'PASS' if ok else 'FAIL'} {name} {detail}")

    for label in runs:
        check(f"{label} finished", runs[label]["exit"] == 0, runs[label]["exit"])
        check(f"{label} mass closes", abs(runs[label]["balance"].get("relative_error", 1.0)) < 1e-6, runs[label]["balance"].get("relative_error"))
        check(f"{label} rain-once: no overlap stop or warning", not [w for w in runs[label]["warnings"] if "both" in w or "overlap" in w.lower()], runs[label]["warnings"][:3])
    ev = runs["storm_lumped"]["basin_event"]
    check("lumped by default: every subbasin lumped", set(ev.get("lumped", [])) == set(subs), (len(ev.get("lumped", [])), len(subs)))
    for a, b in (("storm_lumped", "frames_lumped"), ("storm_arm2d", "frames_arm2d")):
        ba, bb = runs[a]["balance"], runs[b]["balance"]
        check(f"{b}: hills took the same water as {a}", abs(bb.get("inflow_m3", 0) / max(ba.get("inflow_m3", 1), 1) - 1.0) < 1e-3, (ba.get("inflow_m3"), bb.get("inflow_m3")))
        check(f"{b}: grid took the same rain as {a}", abs(bb.get("rain_m3", 0) / max(ba.get("rain_m3", 1), 1) - 1.0) < 1e-3, (ba.get("rain_m3"), bb.get("rain_m3")))
        for line in ("Bidah_03", "above", "below"):
            pa, pb = runs[a]["lines"].get(line, (0, 0))[0], runs[b]["lines"].get(line, (0, 0))[0]
            if pa > 1.0:
                check(f"{b}: line {line} peak as {a} within 0.5 %", abs(pb / pa - 1.0) < 0.005, (round(pa, 2), round(pb, 2)))
        na, nb = runs[a]["network"].get(jobs.RESERVOIR, {}), runs[b]["network"].get(jobs.RESERVOIR, {})
        if na:
            check(f"{b}: reservoir inflow peak as {a} within 0.5 %", abs(nb["inflow"][0] / na["inflow"][0] - 1.0) < 0.005, (na["inflow"], nb["inflow"]))
    for a in ("storm_arm2d", "frames_arm2d"):
        ba = runs[a]["balance"]
        check(f"{a}: a hand-back line was built at {reach_junction}", runs[a]["basin_event"].get("handbacks") == [reach_junction], runs[a]["basin_event"].get("handbacks"))
        check(f"{a}: the whole closes to the routing defect", abs(ba.get("whole_relative_error", 1.0)) < 1e-2, ba.get("whole_relative_error"))
    report["checks"] = checks
    report["passed"] = sum(k["pass"] for k in checks)
    report["failed"] = sum(not k["pass"] for k in checks)
    c.dump(report, RESULTS / "item2_gridded.json")
    for label in runs:
        c.write(json.loads((scratch / "item2" / f"{label}.json").read_text(encoding="utf-8")), RESULTS.parent / "jobs" / "item2" / f"{label}.json")
    c.say(f"item 2: {report['passed']} passed, {report['failed']} failed")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
