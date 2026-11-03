"""Item 3: a generated basin with the quadtree mesh on. The 100-yr storm, every subbasin above the dam as rain-on-grid,
the rest lumped, the hand-back built at the reservoir; uniform 10 m against the mesh 10 to 40 m, local stepping off and
on. Rule, set before the run: the peaks at the dam-side lines and at the hand-back within the mesh's known 2.4 %.

    python item3_mesh.py <scratch folder>   (after item2_gridded.py: its basin is reused)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402
import jobs  # noqa: E402

RESULTS = Path(__file__).resolve().parents[1] / "results"
RULE = 0.024
HOURS = 30.0


def main(scratch: Path) -> None:
    basin = scratch / "basin2" / "basin" / "basin.json"
    cache = scratch / "cache"
    report: dict = {"basin": str(basin), "two_d": jobs.upstream_subbasins(basin, jobs.RESERVOIR)}
    cases = {
        "uniform10": {},
        "mesh10_40": {"mesh": {"enabled": True, "coarse_dx": 40.0}},
        "mesh10_40_lts": {"mesh": {"enabled": True, "coarse_dx": 40.0}, "numerics": {"local_time_stepping": True}},
    }
    runs = {}
    for label, parts in cases.items():
        job = jobs.two_d_above_dam(label, basin, cache, dx=10.0, hours=HOURS, **parts)
        path = c.write(job, scratch / "item3" / f"{label}.json")
        code, wall = c.run(path, scratch / "item3" / label)
        runs[label] = jobs.read_run(scratch / "item3" / label)
        runs[label]["wall_s"] = round(wall, 1)
        c.say(f"{label}: exit {code}, cells {runs[label]['cells']}, lines {runs[label]['lines']}, handbacks {runs[label]['handbacks']}")
        c.write(job, RESULTS.parent / "jobs" / "item3" / f"{label}.json")
    report["runs"] = runs

    checks = []

    def check(name, ok, detail=""):
        checks.append({"check": name, "pass": bool(ok), "detail": str(detail)[:300]})
        c.say(f"{'PASS' if ok else 'FAIL'} {name} {detail}")

    base = runs["uniform10"]
    check("uniform finished", base["exit"] == 0, base["exit"])
    check("a hand-back was built at the reservoir", base["basin_event"].get("handbacks") == [jobs.RESERVOIR], base["basin_event"].get("handbacks"))
    for label in ("mesh10_40", "mesh10_40_lts"):
        r = runs[label]
        check(f"{label} finished", r["exit"] == 0, r["exit"])
        check(f"{label} fewer cells than uniform", (r["cells"] or 0) < (base["cells"] or 0), (base["cells"], r["cells"]))
        check(f"{label} mass closes", abs(r["balance"].get("relative_error", 1.0)) < 1e-5, r["balance"].get("relative_error"))
        check(f"{label} whole closes to the routing defect", abs(r["balance"].get("whole_relative_error", 1.0)) < 1e-2, r["balance"].get("whole_relative_error"))
        for line in ("above", "Bidah_03"):
            pb, pm = base["lines"].get(line, (0, 0))[0], r["lines"].get(line, (0, 0))[0]
            if pb > 1.0:
                check(f"{label}: line {line} within {RULE:.1%} of uniform", abs(pm / pb - 1.0) < RULE, f"{pb:.1f} -> {pm:.1f}, {pm / pb - 1.0:+.2%}")
        hb, hm = base["handbacks"].get(jobs.RESERVOIR, {}), r["handbacks"].get(jobs.RESERVOIR, {})
        if hb and hm:
            check(f"{label}: hand-back crossing peak within {RULE:.1%}", abs(hm["crossed"][0] / hb["crossed"][0] - 1.0) < RULE, f"{hb['crossed'][0]:.1f} -> {hm['crossed'][0]:.1f}, {hm['crossed'][0] / hb['crossed'][0] - 1.0:+.2%}")
            check(f"{label}: hand-back volume within 1 %", abs(hm["crossed_m3"] / hb["crossed_m3"] - 1.0) < 0.01, f"{hb['crossed_m3']:.0f} -> {hm['crossed_m3']:.0f}")
        nb, nm = base["network"].get(jobs.RESERVOIR, {}), r["network"].get(jobs.RESERVOIR, {})
        if nb and nm:
            check(f"{label}: reservoir outflow peak within {RULE:.1%}", abs(nm["outflow"][0] / max(nb["outflow"][0], 1e-9) - 1.0) < RULE, (nb["outflow"], nm["outflow"]))
    report["checks"] = checks
    report["passed"] = sum(k["pass"] for k in checks)
    report["failed"] = sum(not k["pass"] for k in checks)
    c.dump(report, RESULTS / "item3_mesh.json")
    c.say(f"item 3: {report['passed']} passed, {report['failed']} failed")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
