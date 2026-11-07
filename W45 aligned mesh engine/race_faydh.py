"""The race on Faydh 01 at 20 m: the dam peak with no lines, with W26's banks as corridors of aligned cells, on the CPU.

W36's rule: the peak at the dam line within 3 % of the run with no lines. The staircase of W36 read -11.1 % here.
Jobs are W36's base (W11's rain-on-grid job at 20 m on the 20 m domain, 16 h), on the CPU backend with no maps.

    .venv\\Scripts\\python "W45 aligned mesh engine\\race_faydh.py" <work folder> [build|run|report]
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import shapely

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from wadi2d.strips.banks import corridor_specs, pair_banks, read_layers  # noqa: E402
from wadi2d.terrain.vector import read_features  # noqa: E402

W11 = ROOT / "W11 validation round two" / "t2_faydh"
W26 = ROOT / "W26 suggested breaklines" / "suggested" / "faydh" / "suggested_breaklines.gpkg"
DURATION_S = 16 * 3600.0
LAYER, ROWS_PER_SIDE = 10.0, 3
RULE = 0.03


def base(work: Path) -> dict:
    data = json.loads((W11 / "jobs" / "10m_n050_em.json").read_text(encoding="utf-8"))
    data["grid"]["dx"] = 20.0
    data["grid"]["domain"] = str(W11 / "domain_wadi_20m.geojson")
    data["grid"]["cache_dir"] = str(work / "cache")
    data["outputs"]["map_every_s"] = 0.0
    data["outputs"]["live_every_s"] = 0.0
    data["outputs"]["pixels"] = {"enabled": False}
    data["run"]["duration_s"] = DURATION_S
    data["run"]["backend"] = "cpu"
    data["run"]["checkpoint_every_s"] = 0.0
    return data


def build(work: Path) -> None:
    work.mkdir(parents=True, exist_ok=True)
    domain = shapely.union_all([shape for _props, shape in read_features(W11 / "domain_wadi_20m.geojson", "")])
    banks, thalwegs = read_layers(W26)
    pairs = pair_banks(banks, thalwegs)
    specs, rejected = corridor_specs(pairs, domain, LAYER, ROWS_PER_SIDE, 20.0)
    (work / "corridors.json").write_text(json.dumps({"accepted": len(specs), "rejected": rejected, "pairs": len(pairs)}, indent=1), encoding="utf-8")
    print(f"banks {len(banks)}, wadis {len(thalwegs)}, pairs {len(pairs)}, corridors {len(specs)}, rejected {len(rejected)}")
    none = base(work)
    (work / "faydh20_none.json").write_text(json.dumps(none, indent=1), encoding="utf-8")
    strips = base(work)
    strips["strips"] = {"enabled": True, "corridors": specs, "along": 20.0, "buffer_cells": 0.5, "smooth": 5}
    (work / "faydh20_strips.json").write_text(json.dumps(strips, indent=1), encoding="utf-8")


def run(work: Path, name: str) -> None:
    exe = ROOT / ".venv" / "Scripts" / "wadi2d.exe"
    t0 = time.perf_counter()
    done = subprocess.run([str(exe), "run", str(work / f"{name}.json"), "--out", str(work / name)], capture_output=True, text=True)
    (work / f"{name}.log").write_text(done.stdout + "\n" + done.stderr, encoding="utf-8")
    print(f"{name}: exit {done.returncode} in {time.perf_counter() - t0:.0f} s")


def peak(folder: Path, line: str) -> tuple[float, float]:
    rows = (folder / "series" / f"line_{line}.csv").read_text(encoding="utf-8").splitlines()[1:]
    t = np.array([float(r.split(",")[0]) for r in rows])
    q = np.abs(np.array([float(r.split(",")[1]) for r in rows]))
    return float(q.max()), float(t[q.argmax()] / 3600.0)


def report(work: Path) -> None:
    out = {}
    for name in ("faydh20_none", "faydh20_strips"):
        folder = work / name
        done = [json.loads(s) for s in (folder / "progress.jsonl").read_text(encoding="utf-8").splitlines() if '"done"' in s[:14]]
        p, at = peak(folder, "axis")
        out[name] = {"axis_peak_m3s": p, "at_h": at, "steps": done[-1]["steps"], "loop_s": done[-1]["loop_s"], "mass_error": done[-1]["balance"]["relative_error"]}
        print(f"{name}: axis peak {p:.1f} m3/s at {at:.2f} h, {done[-1]['steps']} steps, {done[-1]['loop_s']:.0f} s, mass error {done[-1]['balance']['relative_error']:.1e}")
    ratio = out["faydh20_strips"]["axis_peak_m3s"] / out["faydh20_none"]["axis_peak_m3s"]
    out["ratio"] = ratio
    print(f"corridors against no lines: {ratio:.4f} ({100 * (ratio - 1):+.1f} %); the rule is {100 * RULE:.0f} %: {'PASS' if abs(ratio - 1) <= RULE else 'FAIL'}; the staircase of W36 read -11.1 %")
    (work / "race.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    work = Path(sys.argv[1])
    what = sys.argv[2] if len(sys.argv) > 2 else "all"
    if what in ("build", "all"):
        build(work)
    if what in ("run", "all"):
        run(work, "faydh20_none")
        run(work, "faydh20_strips")
    if what in ("report", "all"):
        report(work)
