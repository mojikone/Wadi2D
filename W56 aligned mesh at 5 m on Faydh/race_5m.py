"""Faydh 01 race: the centre mesh at 5 m against the 5 m squares, with 20 m and 10 m centres, on one engine (W56).

Jobs are W47's race jobs (`depth_carry/race`, read-only) copied with `tables.face_conveyance: local_radius`, as W49's
`race_local_radius.py` did, a cache of their own, and a 5 m centre job made from `ce10` (`grid.dx` 5, `strips.along` 5).
Runs one after the other through `python -m wadi2d.engine.cli` from this worktree; the peak is read from
`series/line_axis.csv` as W47's `race_after_fix.shape` reads it.

    python "W56 aligned mesh at 5 m on Faydh/race_5m.py" [build|run|report|all] [names ...]
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SOURCE = Path(r"D:\Mojtaba\Renardet\Wadi2D\W47 face level carried to the face\depth_carry\race")
WORK = HERE / "runs"
NAMES = ("ce5", "sq5", "ce10", "ce20")
FROM = {"ce5": "ce10", "sq5": "sq5", "ce10": "ce10", "ce20": "ce20"}
REFERENCE = 1796.2  # W49 race_faydh_top_fix/sq5


def build(names: list[str]) -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    for name in names:
        job = json.loads((SOURCE / f"{FROM[name]}.json").read_text(encoding="utf-8"))
        job["grid"]["cache_dir"] = str(WORK / "cache")
        job.setdefault("tables", {})["face_conveyance"] = "local_radius"
        if name == "ce5":
            job["grid"]["dx"] = 5.0
            job["strips"]["along"] = 5.0
        (WORK / f"{name}.json").write_text(json.dumps(job, indent=1), encoding="utf-8")
    print("jobs written:", ", ".join(names), flush=True)


def run(name: str) -> None:
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    t0 = time.perf_counter()
    done = subprocess.run([sys.executable, "-m", "wadi2d.engine.cli", "run", str(WORK / f"{name}.json"), "--out", str(WORK / name)],
                          capture_output=True, text=True, cwd=str(ROOT), env=env)
    wall = time.perf_counter() - t0
    (WORK / f"{name}.log").write_text(done.stdout + "\n" + done.stderr, encoding="utf-8")
    (WORK / f"{name}.wall").write_text(f"{wall:.1f}\n{done.returncode}\n", encoding="utf-8")
    print(f"{name}: exit {done.returncode} in {wall:.0f} s", flush=True)


def shape(folder: Path, line: str = "axis") -> dict:
    rows = (folder / "series" / f"line_{line}.csv").read_text(encoding="utf-8").splitlines()[1:]
    a = np.array([[float(v) for v in r.split(",")[:2]] for r in rows])
    t, q = a[:, 0], np.abs(a[:, 1])
    k = int(q.argmax())
    return {"peak": float(q[k]), "at_h": float(t[k] / 3600), "vol_Mm3": float(q.sum() * float(np.median(np.diff(t))) / 1e6)}


def report(names: list[str]) -> dict:
    out = {}
    for name in names:
        if not (WORK / name / "series" / "line_axis.csv").is_file():
            print(f"{name}: no series")
            continue
        r = shape(WORK / name)
        prog = (WORK / name / "progress.jsonl").read_text(encoding="utf-8").splitlines()
        done = [json.loads(s) for s in prog if '"done"' in s[:14]][-1]
        r["tables_s"], r["loop_s"] = done.get("tables_s"), done.get("loop_s")
        r["wall_s"] = float((WORK / f"{name}.wall").read_text().split()[0]) if (WORK / f"{name}.wall").is_file() else None
        out[name] = r
    ref = out.get("sq5", {}).get("peak")
    print(f"{'run':6s} {'peak':>9s} {'vs sq5':>8s} {'vs 1796.2':>10s} {'vol Mm3':>8s} {'tables s':>9s} {'loop s':>8s} {'wall s':>8s}")
    for name, r in out.items():
        vs = f"{100 * (r['peak'] / ref - 1):+.2f} %" if ref else ""
        print(f"{name:6s} {r['peak']:9.1f} {vs:>8s} {100 * (r['peak'] / REFERENCE - 1):+9.2f} % {r['vol_Mm3']:8.3f} "
              f"{r['tables_s'] or 0:9.1f} {r['loop_s'] or 0:8.1f} {r['wall_s'] or 0:8.0f}")
    (WORK / "race_5m.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    names = [a for a in sys.argv[2:] if a in NAMES] or list(NAMES)
    if what in ("build", "all"):
        build(names)
    if what in ("run", "all"):
        for name in names:
            run(name)
    if what in ("report", "all"):
        report(names)
