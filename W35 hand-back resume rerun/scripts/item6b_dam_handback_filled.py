"""Item 6, second attempt, after the first showed the two pools did not start alike and the upper water did not reach
the pool over the grid.

What the first attempt found (``item6_dam_handback.json``): the generated reservoir starts at its spillway crest
(``initial_elevation_m`` 100.0 m, the pool table runs from 86.96 m), while the grid pool starts dry, 3.6 Mm3 below the
spillway; and with every subbasin above the dam in 2D the resolver builds lines at J2, J3 and J4 as well, so the upper
water reaches the pool through the lumped reaches R2 to R4 and only S2 crosses the grid line. So here:

- only S2, the subbasin draining straight to the dam, is rain-on-grid; S3 to S8 stay lumped in every run;
- the grid runs start with the pool filled to the reservoir's own initial level, through ``initial_levels`` on a polygon
  bounded by the crest line and reaching 3 km up the valley;
- the lumped-pool run keeps the basin with reaches (one line, at Bidah 03); the grid-pool runs take the basin with no
  reaches (the lumped upper subbasins enter the grid at J2, J3, J4 and run to the pool over the ground), once with the
  crest lines of W27 and once with the main crest line replaced by a W8 embankment.

The number compared is the dam's outflow: the rated lumped pool against the ``below`` line 150 m downstream of the crest.
The pool inflows differ by the routing of the upper water, reaches against grid, which W25 measured on R1 as a method
difference; it is reported, not hidden.

    python item6b_dam_handback_filled.py <scratch folder>   (after item2_gridded.py and item6_dam_handback.py)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402
import jobs  # noqa: E402
from item6_dam_handback import embankment_objects, pool_series  # noqa: E402

RESULTS = Path(__file__).resolve().parents[1] / "results"
HOURS = 36.0
UP_M = 3000.0


def pool_ring() -> list[list[float]]:
    """The valley above the crest: the dam line moved 10 m upstream as the downstream edge, 3 km up as the other."""
    near = [p for p in jobs._shifted_many(c.DAM_LINE, -10.0)]
    far = [p for p in jobs._shifted_many(c.DAM_LINE, -UP_M)]
    return near + far[::-1] + [near[0]]


def main(scratch: Path) -> None:
    cache = scratch / "cache"
    basin = scratch / "basin2" / "basin" / "basin.json"
    basin_nr = scratch / "basin_noreach" / "basin" / "basin.json"
    reservoir = next(e for e in jobs.elements(basin, "reservoir") if e["name"] == jobs.RESERVOIR)
    level = reservoir["parameters"]["initial_elevation_m"]["value"]
    arm = next(e["name"] for e in jobs.elements(basin, "subbasin") if e["downstream"] == jobs.RESERVOIR)
    ring = pool_ring()
    report: dict = {"initial_level_m": level, "arm_in_2d": arm, "pool_ring": ring}
    runs = {}
    cases = {
        "handback": (basin, {}),
        "grid": (basin_nr, {"initial_levels": [{"coordinates": ring, "level": level}]}),
        "grid_embankment": (basin_nr, {"initial_levels": [{"coordinates": ring, "level": level}], "terrain": {"objects": embankment_objects()}}),
    }
    for label, (which, parts) in cases.items():
        job = jobs.lumped_default(label, which, cache, dx=20.0, hours=HOURS, two_d=[arm], **parts)
        path = c.write(job, scratch / "item6b" / f"{label}.json")
        c.write(job, RESULTS.parent / "jobs" / "item6b" / f"{label}.json")
        code, wall = c.run(path, scratch / "item6b" / label)
        r = jobs.read_run(scratch / "item6b" / label)
        r["wall_s"] = round(wall, 1)
        r["pool"] = pool_series(scratch / "item6b" / label) if (scratch / "item6b" / label / "series" / "point_pool.csv").exists() else None
        r["message"] = c.done_event(scratch / "item6b" / label).get("message") or (c.events(scratch / "item6b" / label, "error") or [{}])[-1].get("message")
        if (scratch / "item6b" / label / "series" / "line_below.csv").exists():
            r["below_m3"] = abs(c.volume(scratch / "item6b" / label, "line_below", "discharge_m3s"))
        runs[label] = r
        c.say(f"{label}: exit {code}; lines {r['lines']}; network {r['network'].get(jobs.RESERVOIR)}; handbacks {r['handbacks']}; pool {r['pool']}; below_m3 {r.get('below_m3')}")
        c.say(f"   balance {r['balance']}")
    report["runs"] = runs

    checks = []

    def check(name, ok, detail=""):
        checks.append({"check": name, "pass": bool(ok), "detail": str(detail)[:300]})
        c.say(f"{'PASS' if ok else 'FAIL'} {name} {detail}")

    hb, gr, ge = runs["handback"], runs["grid"], runs["grid_embankment"]
    check("handback run finished", hb["exit"] == 0, hb["message"])
    check("one hand-back line, at the reservoir", hb["basin_event"].get("handbacks") == [jobs.RESERVOIR], hb["basin_event"].get("handbacks"))
    check("handback: grid error closes", abs(hb["balance"].get("relative_error", 1.0)) < 1e-6, hb["balance"].get("relative_error"))
    check("handback: the whole closes to the routing defect", abs(hb["balance"].get("whole_relative_error", 1.0)) < 1e-2, (hb["balance"].get("whole_relative_error"), hb["balance"].get("routing_defect_m3")))
    for label, r in (("grid", gr), ("grid_embankment", ge)):
        check(f"{label} run finished", r["exit"] == 0, r["message"])
        check(f"{label}: no hand-back built", r["basin_event"].get("handbacks") == [], r["basin_event"].get("handbacks"))
        check(f"{label}: the pool started at the reservoir's level", r["balance"].get("storage_start_m3", 0) > 1e6, r["balance"].get("storage_start_m3"))
        check(f"{label}: grid error closes", abs(r["balance"].get("relative_error", 1.0)) < 1e-6, r["balance"].get("relative_error"))
    rated = hb["network"].get(jobs.RESERVOIR, {})
    if rated and gr["lines"].get("below"):
        qa, qb, qe = rated["outflow"][0], gr["lines"]["below"][0], ge["lines"]["below"][0]
        va, vb, ve = rated["outflow_m3"], gr.get("below_m3", 0.0), ge.get("below_m3", 0.0)
        report["comparison"] = {
            "pool_inflow": {"handback_crossing_S2": hb["handbacks"].get(jobs.RESERVOIR), "lumped_reservoir_inflow": rated["inflow"]},
            "outflow_peak_m3s_at_h": {"rated_lumped": rated["outflow"], "grid_crest_faces": gr["lines"]["below"], "grid_embankment": ge["lines"]["below"]},
            "outflow_volume_m3": {"rated_lumped": va, "grid_crest_faces": vb, "grid_embankment": ve},
            "pool_level": {"grid": gr["pool"], "grid_embankment": ge["pool"]},
            "ratios": {"grid/rated_peak": qb / qa if qa else None, "embankment/rated_peak": qe / qa if qa else None,
                       "grid/rated_volume": vb / va if va else None, "embankment/rated_volume": ve / va if va else None},
        }  # fmt: skip
        c.say(f"comparison: {json.dumps(report['comparison'], default=str)}")
        check("rated outflow against the crest faces within 10 % at the peak (rule set before the run)", qa > 0 and abs(qb / qa - 1.0) < 0.10, f"rated {qa:.1f} at {rated['outflow'][1]:.2f} h, crest faces {qb:.1f} at {gr['lines']['below'][1]:.2f} h, {qb / qa - 1.0:+.1%}")
        check("embankment within 10 % of the rated outflow at the peak", qa > 0 and abs(qe / qa - 1.0) < 0.10, f"rated {qa:.1f}, embankment {qe:.1f} at {ge['lines']['below'][1]:.2f} h, {qe / qa - 1.0:+.1%}")
        check("spilled volumes within 10 %", va > 0 and abs(vb / va - 1.0) < 0.10, f"rated {va:.0f}, crest faces {vb:.0f}, embankment {ve:.0f}")
    report["checks"] = checks
    report["passed"] = sum(k["pass"] for k in checks)
    report["failed"] = sum(not k["pass"] for k in checks)
    c.dump(report, RESULTS / "item6b_dam_handback_filled.json")
    c.say(f"item 6b: {report['passed']} passed, {report['failed']} failed")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
