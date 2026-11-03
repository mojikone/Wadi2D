"""Item 4: a generated basin with a resume. The item-3 job at 20 m (2D above the dam, the hand-back live at the
reservoir, reaches routing): one straight run; one run stopped through ``out/stop`` once it is well inside the flood,
with a checkpoint every 15 wall seconds; then ``--resume``. Every series CSV of the resumed run against the straight one,
digit by digit, and the balance as W25 checked it.

    python item4_resume.py <scratch folder>   (after item2_gridded.py)
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402
import jobs  # noqa: E402

RESULTS = Path(__file__).resolve().parents[1] / "results"
HOURS = 30.0
STOP_AT_H = 12.0
"""Simulated hour at which the stop file is dropped: inside the rising flood of the 24 h storm."""


def stopped_run(job: Path, out: Path) -> tuple[int, float, float]:
    """Starts the engine, drops ``out/stop`` once progress passes STOP_AT_H, returns exit code, wall, hour reached."""
    code = (
        f"import sys; sys.path.insert(0, r'{c.REPO}'); from wadi2d.engine.cli import main; "
        f"sys.argv = ['wadi2d', 'run', r'{job}', '--out', r'{out}']; raise SystemExit(main())"
    )
    start = time.monotonic()
    process = subprocess.Popen([str(c.VENV), "-c", code], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    progress = out / "progress.jsonl"
    hour = 0.0
    while process.poll() is None:
        time.sleep(1.0)
        if progress.exists():
            for line in progress.read_text(encoding="utf-8").splitlines()[-5:]:
                if '"step"' in line[:30]:
                    try:
                        hour = json.loads(line).get("t", 0.0) / 3600.0
                    except ValueError:
                        pass
            if hour >= STOP_AT_H:
                (out / "stop").touch()
                break
    process.wait()
    return process.returncode, time.monotonic() - start, hour


def compare_series(a: Path, b: Path) -> dict:
    out = {}
    for f in sorted((a / "series").glob("*.csv")):
        g = b / "series" / f.name
        if not g.exists():
            out[f.stem] = {"missing_in_resumed": True}
            continue
        with f.open(newline="") as ha, g.open(newline="") as hb:
            ra, rb = list(csv.reader(ha)), list(csv.reader(hb))
        same_text = ra == rb
        worst, where, n = 0.0, None, 0
        if ra[0] == rb[0] and len(ra) == len(rb):
            for x, y in zip(ra[1:], rb[1:], strict=False):
                for k, (u, v) in enumerate(zip(x, y, strict=False)):
                    d = abs(float(u) - float(v))
                    n += 1
                    if d > worst:
                        worst, where = d, (ra[0][k], x[0])
        out[f.stem] = {"identical_text": same_text, "rows": (len(ra) - 1, len(rb) - 1), "max_abs_diff": worst, "at": where, "values": n}
    return out


def main(scratch: Path) -> None:
    basin = scratch / "basin2" / "basin" / "basin.json"
    cache = scratch / "cache"
    job = jobs.two_d_above_dam("resume_case", basin, cache, dx=20.0, hours=HOURS, run={"checkpoint_every_s": 15.0})
    path = c.write(job, scratch / "item4" / "job.json")
    c.write(job, RESULTS.parent / "jobs" / "item4" / "job.json")
    report: dict = {"job": str(path), "stop_at_h": STOP_AT_H}

    code, wall = c.run(path, scratch / "item4" / "whole")
    whole = jobs.read_run(scratch / "item4" / "whole")
    report["whole"] = {**whole, "wall_s": round(wall, 1)}
    c.say(f"whole: exit {code}, {whole['balance']}")

    out = scratch / "item4" / "resumed"
    code, wall, hour = stopped_run(path, out)
    stopped = jobs.read_run(out)
    report["stopped"] = {**stopped, "wall_s": round(wall, 1), "stopped_near_h": hour, "checkpoint": (out / "checkpoint.h5").exists()}
    c.say(f"stopped: exit {code} near {hour:.2f} h, checkpoint {(out / 'checkpoint.h5').exists()}, {stopped['balance']}")
    t_stop = c.done_event(out).get("t")

    code, wall = c.run(path, out, resume=True)
    resumed = jobs.read_run(out)
    report["resumed"] = {**resumed, "wall_s": round(wall, 1)}
    c.say(f"resumed: exit {code}, {resumed['balance']}")
    diff = compare_series(scratch / "item4" / "whole", out)
    report["series"] = diff

    checks = []

    def check(name, ok, detail=""):
        checks.append({"check": name, "pass": bool(ok), "detail": str(detail)[:300]})
        c.say(f"{'PASS' if ok else 'FAIL'} {name} {detail}")

    check("the straight run finished", whole["exit"] == 0, whole["exit"])
    check("the run stopped on the stop file with a checkpoint", stopped["exit"] == 6 and (out / "checkpoint.h5").exists(), (stopped["exit"], t_stop))
    check("stopped inside the flood", t_stop is not None and 0.0 < t_stop < HOURS * 3600.0, t_stop)
    check("the resumed run finished", resumed["exit"] == 0, resumed["exit"])
    done = c.done_event(out)
    check("resumed to the end", abs(done.get("t", 0) - HOURS * 3600.0) < 1.0, done.get("t"))
    bw, br = whole["balance"], resumed["balance"]
    check("whole error of the resumed run small", abs(br.get("whole_relative_error", 1.0)) < 1e-2, br.get("whole_relative_error"))
    check("grid error of the resumed run small", abs(br.get("relative_error", 1.0)) < 1e-5, br.get("relative_error"))
    for key in ("storage_end_m3", "handback_m3", "network_storage_m3", "outflow_m3", "reentry_m3", "inflow_m3", "rain_m3"):
        if key in bw:
            check(f"{key} as the straight run within 1e-3", abs(br.get(key, 0) - bw[key]) <= 1e-3 * max(abs(bw[key]), 1.0), (bw[key], br.get(key)))
    identical = [k for k, v in diff.items() if v.get("identical_text")]
    check("every series file is present after the resume", not [k for k, v in diff.items() if v.get("missing_in_resumed")], [k for k, v in diff.items() if v.get("missing_in_resumed")])
    check("every series equal to the last digit", len(identical) == len(diff), f"{len(identical)} of {len(diff)} identical; worst {max((v.get('max_abs_diff', 0.0), k) for k, v in diff.items())}")
    for k, v in diff.items():
        if not v.get("identical_text"):
            c.say(f"  differs: {k}: rows {v.get('rows')}, max |diff| {v.get('max_abs_diff')} at {v.get('at')}")
    lw, lr = whole["lines"], resumed["lines"]
    for line in lw:
        if lw[line][0] > 1.0:
            check(f"line {line} peak within 1e-3", abs(lr.get(line, (0, 0))[0] / lw[line][0] - 1.0) < 1e-3, (lw[line], lr.get(line)))
    report["checks"] = checks
    report["passed"] = sum(k["pass"] for k in checks)
    report["failed"] = sum(not k["pass"] for k in checks)
    c.dump(report, RESULTS / "item4_resume.json")
    c.say(f"item 4: {report['passed']} passed, {report['failed']} failed")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
