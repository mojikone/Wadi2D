"""W85 step 4: the window runs side by side: steps, the pit's water through time and how quiet its level is.

    python s07_window_table.py <window folder> [variant ...]

For each variant: steps, smallest step, the step at hours 12, 18, 24 and 30 (from the progress file), the pit's level at
those hours in both of its cells, the largest jump of the level between two samples 10 s apart after hour 26 (rain
over, water at rest: a level that is not quiet shows here), the water left in the window and the balance error.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np

HOURS = (12.0, 18.0, 24.0, 30.0)
REST_H = 26.0


def series(path: Path) -> dict[str, np.ndarray]:
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return {k: np.array([float(r[k]) for r in rows]) for k in rows[0]}


def main() -> None:
    root = Path(sys.argv[1])
    names = sys.argv[2:] or [p.name for p in sorted(root.iterdir()) if (p / "progress.jsonl").is_file()]
    out = {}
    for name in names:
        folder = root / name
        events = [
            json.loads(line) for line in (folder / "progress.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        steps = [e for e in events if e["ev"] == "step"]
        done = next(e for e in events if e["ev"] == "done")
        t = np.array([e["t"] for e in steps])
        dt = np.array([e["dt"] for e in steps])
        row = {
            "steps": done["steps"],
            "dt_min": round(done["dt_min"], 4),
            "dt_at_h": {f"{h:g}": round(float(np.interp(h * 3600.0, t, dt)), 4) for h in HOURS},
            "storage_end_m3": round(done["balance"]["storage_end_m3"], 1),
            "outflow_m3": round(done["balance"]["outflow_m3"], 1),
            "relative_error": done["balance"]["relative_error"],
        }
        for point in ("pit_east", "pit_west"):
            s = series(folder / "series" / f"point_{point}.csv")
            rest = s["t_s"] >= REST_H * 3600.0
            row[point] = {
                "level_at_h": {
                    f"{h:g}": round(float(np.interp(h * 3600.0, s["t_s"], s["level_m"])), 3) for h in HOURS
                },
                "depth_end_m": round(float(s["depth_m"][-1]), 3),
                "largest_jump_at_rest_m": round(float(np.abs(np.diff(s["level_m"][rest])).max()), 4),
                "range_at_rest_m": round(float(np.ptp(s["level_m"][rest])), 4),
            }
        out[name] = row
        print(
            f"{name:8s} steps {row['steps']:>7,} dt_min {row['dt_min']:.3f} dt at 12/18/24/30 h "
            + "/".join(f"{v:.3f}" for v in row["dt_at_h"].values())
            + f" | pit east level at 24 h {row['pit_east']['level_at_h']['24']:.2f} end depth {row['pit_east']['depth_end_m']:.2f}"
            f" jump at rest {row['pit_east']['largest_jump_at_rest_m']:.4f} / west {row['pit_west']['largest_jump_at_rest_m']:.4f}"
            f" | stored {row['storage_end_m3']:.0f} m3 out {row['outflow_m3']:.0f} m3 err {row['relative_error']:.1e}"
        )
    (root / "window_table.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
