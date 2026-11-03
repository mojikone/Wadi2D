"""Item 5: a generated basin on the full extent, W12's domain, 15,398 km2 at 30 m.

``wadi2d basin`` on W12's job with the HMS network taken out (the generator wants the terrain and the settings only),
first at the default analysis pixel to see what the size guard says, then at the pixel it asks for. Then the run on the
generated basin, all lumped by default, W12's storm and outlets, on W12's grid cache. The run is stopped through the stop
file after ``--minutes`` of wall time unless ``--full`` is given: a full run is about 68 min on an idle card.

    python item5_full_extent.py <scratch folder> [--minutes 10] [--full] [--pixel 10]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402

RESULTS = Path(__file__).resolve().parents[1] / "results"
W12_JOB = Path(r"D:\Mojtaba\Renardet\Wadi2D\W12 full extent rerun\jobs\full_30m_200yr.json")
W12_CACHE = Path(r"D:\Mojtaba\Renardet\Wadi2D\W12 full extent rerun\cache")


def generation_job(scratch: Path) -> dict:
    job = json.loads(W12_JOB.read_text(encoding="utf-8"))
    job["project"] = {"name": "full_extent_basin", "description": "W32 item 5: a generated basin on the full extent"}
    job["grid"]["cache_dir"] = str(W12_CACHE)
    job["hydrology"] = {"curve_number": 88.0}
    job["basin"] = {"stream_threshold_km2": 10.0}
    return job


def timed_run(job: Path, out: Path, minutes: float | None) -> dict:
    """The run, stopped through out/stop after ``minutes`` of wall time (None runs it out)."""
    code = (
        f"import sys; sys.path.insert(0, r'{c.REPO}'); from wadi2d.engine.cli import main; "
        f"sys.argv = ['wadi2d', 'run', r'{job}', '--out', r'{out}']; raise SystemExit(main())"
    )
    start = time.monotonic()
    log = (out.parent / f"{out.name}_engine.log").open("w", encoding="utf-8")
    process = subprocess.Popen([str(c.VENV), "-c", code], stdout=log, stderr=subprocess.STDOUT)
    started_at = None
    while process.poll() is None:
        time.sleep(5.0)
        if started_at is None and c.events(out, "start"):
            started_at = time.monotonic() - start
        if minutes is not None and started_at is not None and time.monotonic() - start - started_at > minutes * 60.0:
            (out / "stop").touch()
            break
    process.wait()
    log.close()
    done = c.done_event(out)
    progress = [json.loads(s) for s in (out / "progress.jsonl").read_text(encoding="utf-8").splitlines() if '"progress"' in s[:30]] if (out / "progress.jsonl").exists() else []
    return {
        "exit": process.returncode, "wall_s": round(time.monotonic() - start, 1), "started_after_s": started_at,
        "start": c.start_event(out), "done": {k: v for k, v in done.items() if k != "balance"}, "balance": done.get("balance", {}),
        "warnings": c.warnings(out), "last_progress": progress[-1] if progress else None, "progress_count": len(progress),
        "basin_event": (c.events(out, "basin") or [{}])[0],
    }  # fmt: skip


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("scratch")
    ap.add_argument("--minutes", type=float, default=10.0)
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--pixel", type=float, default=10.0)
    args = ap.parse_args()
    scratch = Path(args.scratch) / "item5"
    scratch.mkdir(parents=True, exist_ok=True)
    report: dict = {}
    job = c.write(generation_job(scratch), scratch / "gen.json")

    c.say("generation at the default analysis pixel")
    code, wall, text = c.engine("basin", str(job), "--out", str(scratch / "basin_default"), log=scratch / "basin_default.log")
    report["generation_default_pixel"] = {"exit": code, "wall_s": round(wall, 1), "said": c.last_json(text) or text[-600:]}
    c.say(f"default pixel: exit {code} in {wall:.0f} s: {report['generation_default_pixel']['said']}")

    event = c.last_json(text) if code == 0 else {}
    if code != 0:
        c.say(f"generation at {args.pixel} m")
        code, wall, text = c.engine("basin", str(job), "--out", str(scratch / "basin"), "--pixel", str(args.pixel), log=scratch / "basin.log")
        event = c.last_json(text)
        report["generation"] = {"exit": code, "wall_s": round(wall, 1), "pixel": args.pixel, "said": event or text[-600:]}
        c.say(f"pixel {args.pixel}: exit {code} in {wall:.0f} s: {event or text[-600:]}")
    else:
        report["generation"] = report["generation_default_pixel"]
    if not event.get("basin"):
        c.dump(report, RESULTS / "item5_full_extent.json")
        c.say("no basin: stop here")
        return
    basin = Path(event["basin"])
    model = json.loads(basin.read_text(encoding="utf-8"))
    kinds = {}
    for e in model["elements"]:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    incomplete = [e["name"] for e in model["elements"] if e.get("missing")]
    report["elements"] = {"counts": kinds, "incomplete": len(incomplete), "incomplete_names": incomplete[:20], "notes": event.get("notes")}
    c.say(f"elements {kinds}, incomplete {len(incomplete)}")

    run_job = generation_job(scratch)
    run_job["hydrology"] = {"basin_json": str(basin), "time_step_min": 5.0, "curve_number": 88.0}
    run_job["outputs"]["pixels"] = {"enabled": False}
    run_job["outputs"]["smooth"] = {"enabled": False}
    path = c.write(run_job, scratch / "run.json")
    c.write(run_job, RESULTS.parent / "jobs" / "item5" / "run.json")
    minutes = None if args.full else args.minutes
    c.say(f"the run, {'to the end' if minutes is None else f'{minutes:g} min of wall time after it starts'}")
    report["run"] = timed_run(path, scratch / "run", minutes)
    c.say(json.dumps({k: v for k, v in report["run"].items() if k not in ("warnings",)}, default=str)[:1500])
    c.say(f"warnings: {report['run']['warnings'][:10]}")
    c.dump(report, RESULTS / "item5_full_extent.json")


if __name__ == "__main__":
    main()
