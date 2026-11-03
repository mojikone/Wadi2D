"""Item 6: the hand-back at a dam against the same flood through the crest faces.

Three runs of the same 100-yr flood, every subbasin above Bidah 03 as rain-on-grid, 20 m, 36 h, nothing tuned:

- ``handback``: the basin of W27 (threshold 2 km2, reaches). The resolver builds the hand-back line three cells up the
  axis; the flood leaves the grid there into the lumped pool, whose rating is the spillway object (Q = C L H^1.5), and
  the pool's outflow runs the lumped reach R1. The number is the reservoir's outflow series.
- ``grid``: the same ground and flood on a basin generated with no reaches (``min_reach_m`` 5000: every junction's route
  is ``none``, so no line is built and the reservoir passes on nothing lumped). The pool fills on the grid and the flood
  passes the spillway and the crest faces; the ``below`` line 150 m downstream of the crest reads it.
- ``grid_embankment``: ``grid`` with the main crest line replaced by a W8 ``embankment`` object on the same alignment
  (crest 105 m, 8 m wide, 2:1 faces), so the crest faces are the eased ones of the shaped objects.

Also tried: a user-drawn hand-back line below the crest into R1 on the first basin (``handback_below``), to see whether the
resolver and the user's line can share a dam; recorded whatever the engine says.

    python item6_dam_handback.py <scratch folder>   (after item2_gridded.py)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402
import jobs  # noqa: E402

RESULTS = Path(__file__).resolve().parents[1] / "results"
HOURS = 36.0


def embankment_objects() -> list[dict]:
    objects = jobs.c.dam_objects()
    main = next(o for o in objects if o.get("name") == "Bidah 03")
    replaced = {
        "kind": "embankment", "name": "Bidah 03", "coordinates": main["coordinates"], "z_constant": main["z_constant"],
        "section": {"width": 8.0, "left_slope": 2.0, "right_slope": 2.0},
    }  # fmt: skip
    return [replaced if o is main else o for o in objects]


def pool_series(folder: Path) -> dict:
    rows = c.series(folder, "point_pool")
    column = next((k for k in rows[0] if "level" in k), None) or next(k for k in rows[0] if k != "t_s")
    best = max(rows, key=lambda r: float(r[column]))
    return {"column": column, "max": float(best[column]), "at_h": float(best["t_s"]) / 3600.0}


def main(scratch: Path) -> None:
    cache = scratch / "cache"
    basin = scratch / "basin2" / "basin" / "basin.json"
    report: dict = {}
    no_reach = jobs.generate(scratch, "basin_noreach", threshold=2.0, min_reach_m=5000.0)
    report["generation_no_reach"] = no_reach
    c.say(f"no-reach basin: {jobs.summary(no_reach)}")
    basin_nr = Path(no_reach["basin"])
    routes = {r["junction"]: r["route"] for r in jobs.model(basin_nr)["routes"]}
    report["no_reach_routes"] = routes

    runs = {}
    cases = {
        "handback": (basin, {}),
        "grid": (basin_nr, {}),
        "grid_embankment": (basin_nr, {"terrain": {"objects": embankment_objects()}}),
    }
    for label, (which, parts) in cases.items():
        job = jobs.two_d_above_dam(label, which, cache, dx=20.0, hours=HOURS, **parts)
        path = c.write(job, scratch / "item6" / f"{label}.json")
        c.write(job, RESULTS.parent / "jobs" / "item6" / f"{label}.json")
        code, wall = c.run(path, scratch / "item6" / label)
        r = jobs.read_run(scratch / "item6" / label)
        r["wall_s"] = round(wall, 1)
        r["pool"] = pool_series(scratch / "item6" / label) if (scratch / "item6" / label / "series" / "point_pool.csv").exists() else None
        r["message"] = c.done_event(scratch / "item6" / label).get("message") or (c.events(scratch / "item6" / label, "error") or [{}])[-1].get("message")
        runs[label] = r
        c.say(f"{label}: exit {code}; lines {r['lines']}; network {r['network'].get(jobs.RESERVOIR)}; handbacks {r['handbacks']}; pool {r['pool']}")
        c.say(f"   balance {r['balance']}")

    # the user's own line below the crest, into R1, on the basin that has reaches
    reaches = [e["name"] for e in jobs.elements(basin, "reach")]
    below_reach = next((e["name"] for e in jobs.elements(basin, "reach") if e.get("upstream") == jobs.RESERVOIR), None)
    reservoir = next(e for e in jobs.elements(basin, "reservoir") if e["name"] == jobs.RESERVOIR)
    if below_reach is None:
        below_reach = next((r for r in reaches if reservoir.get("downstream") == r), reaches[0] if reaches else None)
    report["reach_below_dam"] = {"chosen": below_reach, "reservoir_downstream": reservoir.get("downstream"), "reaches": reaches}
    if below_reach:
        job = jobs.two_d_above_dam("handback_below", basin, cache, dx=20.0, hours=HOURS)
        job["hydrology"]["handbacks"] = [{"name": "below crest", "coordinates": jobs.BELOW, "element": below_reach}]
        path = c.write(job, scratch / "item6" / "handback_below.json")
        c.write(job, RESULTS.parent / "jobs" / "item6" / "handback_below.json")
        code, wall = c.run(path, scratch / "item6" / "handback_below")
        r = jobs.read_run(scratch / "item6" / "handback_below")
        r["wall_s"] = round(wall, 1)
        r["message"] = c.done_event(scratch / "item6" / "handback_below").get("message") or (c.events(scratch / "item6" / "handback_below", "error") or [{}])[-1].get("message")
        log = (scratch / "item6" / "handback_below" / "w32_engine.log").read_text(encoding="utf-8", errors="replace")
        r["engine_said"] = log[-700:]
        runs["handback_below"] = r
        c.say(f"handback_below: exit {code}; {r['message']}; lines {r['lines']}; handbacks {r['handbacks']}")
    report["runs"] = runs

    checks = []

    def check(name, ok, detail=""):
        checks.append({"check": name, "pass": bool(ok), "detail": str(detail)[:300]})
        c.say(f"{'PASS' if ok else 'FAIL'} {name} {detail}")

    hb, gr, ge = runs["handback"], runs["grid"], runs["grid_embankment"]
    check("handback run finished", hb["exit"] == 0, hb["message"])
    check("a hand-back line was built at the reservoir and nowhere else", hb["basin_event"].get("handbacks") == [jobs.RESERVOIR], hb["basin_event"].get("handbacks"))
    check("handback: grid error closes", abs(hb["balance"].get("relative_error", 1.0)) < 1e-6, hb["balance"].get("relative_error"))
    check("handback: the whole closes to the routing defect", abs(hb["balance"].get("whole_relative_error", 1.0)) < 1e-2, (hb["balance"].get("whole_relative_error"), hb["balance"].get("routing_defect_m3")))
    check("handback: nothing passes the line on the grid (below reads under 1 % of the crossing)", hb["lines"].get("below", (0, 0))[0] < 0.01 * hb["handbacks"].get(jobs.RESERVOIR, {}).get("crossed", (1e9, 0))[0], (hb["lines"].get("below"), hb["handbacks"].get(jobs.RESERVOIR)))
    for label, r in (("grid", gr), ("grid_embankment", ge)):
        check(f"{label} run finished", r["exit"] == 0, r["message"])
        check(f"{label}: no hand-back built", r["basin_event"].get("handbacks") == [], r["basin_event"].get("handbacks"))
        check(f"{label}: grid error closes", abs(r["balance"].get("relative_error", 1.0)) < 1e-6, r["balance"].get("relative_error"))
    rated = hb["network"].get(jobs.RESERVOIR, {})
    if rated and gr["lines"].get("below"):
        qa, qb, qe = rated["outflow"][0], gr["lines"]["below"][0], ge["lines"]["below"][0]
        va = rated["outflow_m3"]
        vb = c.volume(scratch / "item6" / "grid", "line_below", "discharge_m3s")
        ve = c.volume(scratch / "item6" / "grid_embankment", "line_below", "discharge_m3s")
        report["comparison"] = {
            "inflow_to_pool": {"handback_crossed": hb["handbacks"].get(jobs.RESERVOIR), "grid_above_line": gr["lines"].get("above"), "handback_above_line": hb["lines"].get("above")},
            "outflow_peak_m3s": {"rated_lumped": rated["outflow"], "grid_crest_faces": gr["lines"]["below"], "grid_embankment": ge["lines"]["below"]},
            "outflow_volume_m3": {"rated_lumped": va, "grid_crest_faces": abs(vb), "grid_embankment": abs(ve)},
            "pool": {"grid": gr["pool"], "grid_embankment": ge["pool"]},
            "ratios": {"grid/rated_peak": qb / qa if qa else None, "embankment/rated_peak": qe / qa if qa else None,
                       "grid/rated_volume": abs(vb) / va if va else None, "embankment/rated_volume": abs(ve) / va if va else None},
        }  # fmt: skip
        c.say(f"comparison: {json.dumps(report['comparison'], default=str)}")
        check("rated outflow against the crest faces within 10 % at the peak (a reading, the rule set before the run)", qa > 0 and abs(qb / qa - 1.0) < 0.10, f"rated {qa:.1f}, crest faces {qb:.1f}, {qb / qa - 1.0:+.1%}")
        check("embankment within 10 % of the rated outflow at the peak", qa > 0 and abs(qe / qa - 1.0) < 0.10, f"rated {qa:.1f}, embankment {qe:.1f}, {qe / qa - 1.0:+.1%}")
        check("the pool took the same flood: above-line peaks within 3 %", abs(gr["lines"]["above"][0] / hb["lines"]["above"][0] - 1.0) < 0.03, (hb["lines"]["above"], gr["lines"]["above"]))
    if "handback_below" in runs:
        r = runs["handback_below"]
        check("a user line below the crest into the reach: the engine answers in words or runs", r["exit"] in (0, 2), (r["exit"], r["message"]))
    report["checks"] = checks
    report["passed"] = sum(k["pass"] for k in checks)
    report["failed"] = sum(not k["pass"] for k in checks)
    c.dump(report, RESULTS / "item6_dam_handback.json")
    c.say(f"item 6: {report['passed']} passed, {report['failed']} failed")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
