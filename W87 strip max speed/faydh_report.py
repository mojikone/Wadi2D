"""W87 on real ground: Faydh 01 at 20 m with the aligned centre mesh (W46's job, ``faydh20_centres_wide.json``, the
CPU, a map every hour), run three times: on the code before W87, on the code after, and after with the step's two
unbounded velocities bounded at ``u_max`` in memory (``run_bounded.py``).

Before against after: the water to the digit and the record (``compare_runs.py``). After against bounded: what the
fault in the step moves, at the dam axis and across the model.

    .venv\\Scripts\\python "W87 strip max speed\\faydh_report.py" <before> <after> <bounded> [<out.json>]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import h5py
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from compare_runs import compare, counts


def line(folder: Path, name: str) -> dict:
    rows = (folder / "series" / f"line_{name}.csv").read_text(encoding="utf-8").splitlines()[1:]
    t = np.array([float(r.split(",")[0]) for r in rows])
    q = np.abs(np.array([float(r.split(",")[1]) for r in rows]))
    return {
        "peak_m3s": float(q.max()),
        "at_h": float(t[q.argmax()] / 3600.0),
        "volume_m3": float(np.trapezoid(q, t)),
    }


def run_of(folder: Path) -> dict:
    events = [json.loads(s) for s in (folder / "progress.jsonl").read_text(encoding="utf-8").splitlines()]
    done = [e for e in events if e.get("ev") == "done"][-1]
    found = {
        "steps": done["steps"],
        "loop_s": done.get("loop_s"),
        "mass_error": done["balance"]["relative_error"],
    }
    found["lines"] = {
        p.stem[5:]: line(folder, p.stem[5:]) for p in sorted((folder / "series").glob("line_*.csv"))
    }
    with h5py.File(folder / "results.h5", "r") as f:
        mx = f["maxima"]
        d = mx["strip_depth"][0]
        found["strip_cells"] = int(d.size)
        found["strip_cells_wet"] = int((d > 0.05).sum())
        found["strip_speed"] = counts(mx["strip_speed"][0])
        found["strip_speed_median_wet"] = float(np.median(mx["strip_speed"][0][d > 0.05]))
        found["strip_hazard"] = counts(mx["strip_hazard"][0])
        found["strip_depth_max"] = float(d.max())
        found["squares_speed"] = counts(mx["speed"][()])
        found["squares_depth_max"] = float(mx["depth"][()].max())
    return found


if __name__ == "__main__":
    before, after, bounded = (Path(a) for a in sys.argv[1:4])
    result = {
        "before_against_after": compare(before, after),
        "after": run_of(after),
        "bounded": run_of(bounded),
    }
    a, b = result["after"], result["bounded"]
    result["bounded_over_after"] = {
        "steps": b["steps"] / a["steps"],
        "lines": {
            n: {"peak": b["lines"][n]["peak_m3s"] / a["lines"][n]["peak_m3s"], "volume": b["lines"][n]["volume_m3"] / a["lines"][n]["volume_m3"]}
            for n in a["lines"]
        },
    }  # fmt: skip
    with h5py.File(after / "results.h5", "r") as fa, h5py.File(bounded / "results.h5", "r") as fb:
        da, db = fa["maxima"]["strip_depth"][0], fb["maxima"]["strip_depth"][0]
        wet = (da > 0.3) | (db > 0.3)
        diff = (db - da)[wet]
        result["strip_max_depth_bounded_minus_after_m"] = {
            "cells_over_0.3_m": int(wet.sum()), "mean": float(diff.mean()), "median": float(np.median(diff)),
            "q05": float(np.quantile(diff, 0.05)), "q95": float(np.quantile(diff, 0.95)), "min": float(diff.min()), "max": float(diff.max()),
        }  # fmt: skip
        over = da - db
        result["strip_max_level_after_over_bounded"] = {
            f"by_over_{lim:g}_m": [int((over > lim).sum()), int((over < -lim).sum())]
            for lim in (0.05, 0.1, 0.5, 1.0, 5.0)
        }
        worst = int(np.argmax(over))
        ha, hb = fa["maxima"]["strip_mean_depth"][0], fb["maxima"]["strip_mean_depth"][0]
        result["strip_worst_cell"] = {
            "cell": worst, "max_level_after_m": float(da[worst]), "max_level_bounded_m": float(db[worst]),
            "max_mean_depth_after_m": float(ha[worst]), "max_mean_depth_bounded_m": float(hb[worst]),
        }  # fmt: skip
        result["strip_max_mean_depth_after_over_bounded_by_over_0.05_m"] = int(((ha - hb) > 0.05).sum())
        qa, qb = fa["maxima"]["depth"][()], fb["maxima"]["depth"][()]
        result["squares_max_depth_after_minus_bounded_m"] = [float((qa - qb).min()), float((qa - qb).max())]
        # the squares: how many move, and how many of those sit on a join (an active square beside a replaced one)
        mask = fa["mask"][()].astype(bool)
        pad = np.pad(mask, 1, constant_values=True)
        join = mask & (~pad[:-2, 1:-1] | ~pad[2:, 1:-1] | ~pad[1:-1, :-2] | ~pad[1:-1, 2:])
        moved = np.abs(np.where(mask, qa - qb, 0.0))
        sa, sb = fa["maxima"]["speed"][()], fb["maxima"]["speed"][()]
        faster = np.abs(np.where(mask, sa - sb, 0.0))
        result["squares"] = {
            "active": int(mask.sum()), "on_a_join": int(join.sum()),
            "max_depth_moved_by_over_m": {f"{lim:g}": [int((moved > lim).sum()), int(((moved > lim) & join).sum())] for lim in (0.001, 0.01, 0.05)},
            "max_depth_moved_most_m": float(moved.max()), "max_depth_moved_mean_on_join_m": float(moved[join].mean()),
            "max_speed_moved_by_over_ms": {f"{lim:g}": [int((faster > lim).sum()), int(((faster > lim) & join).sum())] for lim in (0.1, 1.0, 5.0)},
            "max_speed_moved_most_ms": float(faster.max()),
        }  # fmt: skip
        ea, eb = (
            m - np.max([g["strip_depth"][0] for g in f["maps"].values()], axis=0)
            for m, f in ((da, fa), (db, fb))
        )
        result["strip_max_level_over_highest_hourly_map"] = {
            "after": {f"{lim:g}": int((ea > lim).sum()) for lim in (1.0, 2.0, 5.0)} | {"max_m": float(ea.max())},
            "bounded": {f"{lim:g}": int((eb > lim).sum()) for lim in (1.0, 2.0, 5.0)} | {"max_m": float(eb.max())},
        }
    text = json.dumps(result, indent=1)
    print(text)
    if len(sys.argv) > 4:
        Path(sys.argv[4]).write_text(text, encoding="utf-8")
