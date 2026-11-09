"""Recorded validation jobs rerun on this branch with the strips sum and with the local radius (W49, 2026-11-08).

- `bidah10`: W1's rain-on-grid job on Bidah at 10 m (`ras_rain_on_grid/jobs/10m_n050_em.json`), recorded at 622.0 m3/s
  against HEC-RAS's 621.9 at the Bidah section on the old kernels.
- `block2_b20`: W1's mode (b) hybrid on Block 2 at 20 m with HMS's reach n 0.1 (`block2_full/jobs/arf_b20_n100.json`),
  its design storm as one run (the ARF section dropped), the five dam lines.

Each job is copied with `tables.face_conveyance` set explicitly and its own cache here, so the recorded runs stay as
they were. Every line's peak is reported strips against local radius.

    .venv\Scripts\python "W49 local hydraulic radius face table\validation_reruns\reruns.py" [run|report|all] [names ...]
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
V = ROOT / "W1 research and design note" / "validation"
SOURCES = {"bidah10": V / "ras_rain_on_grid" / "jobs" / "10m_n050_em.json", "block2_b20": V / "block2_full" / "jobs" / "arf_b20_n100.json"}
MODES = ("strips", "local_radius")


def name(case: str, mode: str) -> str:
    return f"{case}_{mode}"


def build(case: str) -> None:
    for mode in MODES:
        job = json.loads(SOURCES[case].read_text(encoding="utf-8"))
        job.pop("arf", None)
        job["grid"]["cache_dir"] = str(HERE / "cache")
        job.setdefault("tables", {})["face_conveyance"] = mode
        job["project"]["name"] = name(case, mode)
        (HERE / f"{name(case, mode)}.json").write_text(json.dumps(job, indent=1), encoding="utf-8")


def run(case: str) -> None:
    exe = ROOT / ".venv" / "Scripts" / "wadi2d.exe"
    for mode in MODES:
        n = name(case, mode)
        if (HERE / n / "results.h5").is_file():
            continue
        t0 = time.perf_counter()
        done = subprocess.run([str(exe), "run", str(HERE / f"{n}.json"), "--out", str(HERE / n)], capture_output=True, text=True)
        (HERE / f"{n}.log").write_text(done.stdout + "\n" + done.stderr, encoding="utf-8")
        print(f"{n}: exit {done.returncode} in {time.perf_counter() - t0:.0f} s", flush=True)


def peaks(folder: Path) -> dict:
    out = {}
    for f in sorted((folder / "series").glob("line_*.csv")):
        rows = f.read_text(encoding="utf-8").splitlines()[1:]
        q = np.abs(np.array([float(r.split(",")[1]) for r in rows if r]))
        out[f.stem[5:]] = float(q.max())
    return out


def report(case: str) -> dict:
    a, b = (peaks(HERE / name(case, m)) for m in MODES)
    done = {}
    for m in MODES:
        prog = [json.loads(s) for s in (HERE / name(case, m) / "progress.jsonl").read_text(encoding="utf-8").splitlines() if '"done"' in s[:14]]
        done[m] = prog[-1] if prog else {}
    print(f"\n{case}: line peaks, m3/s, strips against local radius (tables {done['strips'].get('tables_s')} / {done['local_radius'].get('tables_s')} s, loop {done['strips'].get('loop_s')} / {done['local_radius'].get('loop_s')} s)")
    res = {}
    for line in a:
        if line in b:
            res[line] = {"strips": a[line], "local_radius": b[line], "change": b[line] / a[line] - 1 if a[line] else None}
            ch = f"{100 * res[line]['change']:+6.1f} %" if res[line]["change"] is not None else ""
            print(f"  {line:24s} {a[line]:10.1f} {b[line]:10.1f} {ch}")
    (HERE / f"{case}_peaks.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    return res


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    cases = [a for a in sys.argv[2:] if a in SOURCES] or list(SOURCES)
    for case in cases:
        if what in ("run", "all"):
            build(case)
            run(case)
        if what in ("report", "all"):
            report(case)
