"""The race on Faydh 01 at 20 m: the dam peak with no lines, with suggested banks as corridors of aligned cells.

W36's rule: the peak at the dam line within 3 % of the run with no lines. The staircase of W36 read -11.1 % here.
Jobs are W36's base (W11's rain-on-grid job at 20 m on the 20 m domain, 16 h), with no maps. The corridors come from
a banks file through the engine's own rule (``strips.banks`` with the width rule's numbers), so what runs is what the
dock would build; a job may name another banks file and other cell bounds.

    .venv\\Scripts\\python "W45 aligned mesh engine\\race_faydh.py" <work folder> [build|run|report|all] [cpu|gpu]
        [--banks <gpkg>] [--cells <min> <max> <fraction> <rows_outside>] [--tag <name>]
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

W11 = ROOT / "W11 validation round two" / "t2_faydh"
W26 = ROOT / "W26 suggested breaklines" / "suggested" / "faydh" / "suggested_breaklines.gpkg"
DURATION_S = 16 * 3600.0
RULE = 0.03


def options(argv: list[str]) -> dict:
    out = {"backend": "cpu", "banks": W26, "cells": None, "tag": ""}
    if len(argv) > 3 and argv[3] in ("cpu", "gpu"):
        out["backend"] = argv[3]
    if "--banks" in argv:
        out["banks"] = Path(argv[argv.index("--banks") + 1])
    if "--cells" in argv:
        k = argv.index("--cells")
        out["cells"] = (float(argv[k + 1]), float(argv[k + 2]), float(argv[k + 3]), int(argv[k + 4]))
    if "--tag" in argv:
        out["tag"] = argv[argv.index("--tag") + 1]
    return out


def names(opts: dict) -> tuple[str, str]:
    suffix = ("_gpu" if opts["backend"] == "gpu" else "") + (f"_{opts['tag']}" if opts["tag"] else "")
    return "faydh20_none" + ("_gpu" if opts["backend"] == "gpu" else ""), "faydh20_strips" + suffix


def base(work: Path, backend: str) -> dict:
    data = json.loads((W11 / "jobs" / "10m_n050_em.json").read_text(encoding="utf-8"))
    data["grid"]["dx"] = 20.0
    data["grid"]["domain"] = str(W11 / "domain_wadi_20m.geojson")
    data["grid"]["cache_dir"] = str(work / "cache")
    data["outputs"]["map_every_s"] = 0.0
    data["outputs"]["live_every_s"] = 0.0
    data["outputs"]["pixels"] = {"enabled": False}
    data["run"]["duration_s"] = DURATION_S
    data["run"]["backend"] = backend
    data["run"]["checkpoint_every_s"] = 0.0
    return data


def build(work: Path, opts: dict) -> None:
    work.mkdir(parents=True, exist_ok=True)
    none_name, strips_name = names(opts)
    (work / f"{none_name}.json").write_text(json.dumps(base(work, opts["backend"]), indent=1), encoding="utf-8")
    strips = base(work, opts["backend"])
    strips["strips"] = {"enabled": True, "banks": str(opts["banks"]), "along": 20.0, "buffer_cells": 0.5, "smooth": 5}
    if opts["cells"]:
        lo, hi, share, outside = opts["cells"]
        strips["strips"].update({"cell_min_m": lo, "cell_max_m": hi, "width_fraction": share, "rows_outside": outside})
    (work / f"{strips_name}.json").write_text(json.dumps(strips, indent=1), encoding="utf-8")
    print(f"jobs written: {none_name}, {strips_name} (banks {opts['banks'].name}, cells {opts['cells'] or 'schema defaults'})")


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


def report(work: Path, opts: dict) -> None:
    out = {}
    none_name, strips_name = names(opts)
    for name in (none_name, strips_name):
        folder = work / name
        lines = (folder / "progress.jsonl").read_text(encoding="utf-8").splitlines()
        done = [json.loads(s) for s in lines if '"done"' in s[:14]]
        built = [json.loads(s) for s in lines if '"ev": "strips"' in s]
        p, at = peak(folder, "axis")
        out[name] = {"axis_peak_m3s": p, "at_h": at, "steps": done[-1]["steps"], "loop_s": done[-1]["loop_s"], "mass_error": done[-1]["balance"]["relative_error"]}
        print(f"{name}: axis peak {p:.1f} m3/s at {at:.2f} h, {done[-1]['steps']} steps, {done[-1]['loop_s']:.0f} s, mass error {done[-1]['balance']['relative_error']:.1e}")
        if built:
            s = built[-1]
            rules = s.get("rules", [])
            across = [r["across_m"] for r in rules]
            cells = [r["cells_across"] for r in rules]
            out[name]["strips"] = {k: s[k] for k in ("corridors", "cells", "triangles", "replaced")} | {"cut": len(s["cut"]), "rules": rules}
            print(f"  corridors {s['corridors']}, strip cells {s['cells']}, triangles {s['triangles']}, squares replaced {s['replaced']}, cut {len(s['cut'])}"
                  + (f"; cells across {min(cells)} to {max(cells)}, cell across {min(across):.0f} to {max(across):.0f} m" if rules else ""))
    ratio = out[strips_name]["axis_peak_m3s"] / out[none_name]["axis_peak_m3s"]
    out["ratio"] = ratio
    print(f"corridors against no lines: {ratio:.4f} ({100 * (ratio - 1):+.1f} %); the rule is {100 * RULE:.0f} %: {'PASS' if abs(ratio - 1) <= RULE else 'FAIL'}; the staircase of W36 read -11.1 %")
    (work / f"race{'_' + opts['tag'] if opts['tag'] else ''}{'_gpu' if opts['backend'] == 'gpu' else ''}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    work = Path(sys.argv[1])
    what = sys.argv[2] if len(sys.argv) > 2 else "all"
    opts = options(sys.argv)
    none_name, strips_name = names(opts)
    if what in ("build", "all"):
        build(work, opts)
    if what in ("run", "all"):
        if not (work / none_name / "progress.jsonl").is_file() or "--rerun-none" in sys.argv:
            run(work, none_name)
        run(work, strips_name)
    if what in ("report", "all"):
        report(work, opts)
