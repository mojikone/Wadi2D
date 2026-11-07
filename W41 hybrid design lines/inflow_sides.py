"""Where each dam's local lumped hydrograph enters, against its dam line, on Block 2.

Two placements: the dock's HMS route (`wadi2d/engine/hms_import.py`, `_outlet`: the icon of the element the subbasin
drains to) and W1's validated mode (b) (`validation/block2_full/scripts/common.py`, `lumped_outlets`: the largest
accumulation inside the polygon eroded 80 m). Signed distance to the dam line: negative is the side the subbasin lies on
(upstream), positive the other side (downstream).

Run with the project venv: ``.venv\\Scripts\\python "W41 hybrid design lines\\inflow_sides.py" OUT.json``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from wadi2d.hms import load_basin

REPO = Path(__file__).resolve().parents[1]
HMS = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\HEC_HMS_Block_02")
W1_JOB = REPO / "W1 research and design note" / "validation" / "block2_full" / "jobs" / "arf_b20_n100.json"
DAMS = ("Bidah 03", "Faydh 01", "R5A", "R2A", "Z4C")


def signed_distance(line: np.ndarray, point) -> float:
    """Distance to the nearest segment, signed by the side (cross product of the segment and the point)."""
    p = np.asarray(point, dtype=float)
    best = (np.inf, 0.0)
    for a, b in zip(line[:-1], line[1:], strict=True):
        d = b - a
        t = np.clip(np.dot(p - a, d) / np.dot(d, d), 0.0, 1.0)
        dist = float(np.linalg.norm(p - (a + t * d)))
        side = float(np.sign(d[0] * (p - a)[1] - d[1] * (p - a)[0]))
        if dist < best[0]:
            best = (dist, side)
    return best[0] * best[1]


def main(out: Path) -> None:
    model = load_basin(HMS / "Basin_1.basin")
    icon = {e.name: (e.canvas_x, e.canvas_y) for e in model.elements if getattr(e, "canvas_x", None) is not None}
    job = json.loads(W1_JOB.read_text(encoding="utf-8"))
    w1 = {s["name"]: s["outlet"] for s in job["hydrology"]["subbasins"]}
    lines = {k["name"]: np.asarray(k["coordinates"], dtype=float) for k in job["outputs"]["lines"]}
    rows = []
    for dam in DAMS:
        line = lines[dam]
        sign = np.sign(signed_distance(line, icon[next(e.name for e in model.elements if e.downstream == dam)]))
        for element in model.elements:
            if type(element).__name__ == "Subbasin" and element.downstream == dam:
                own = signed_distance(line, icon[element.name])
                flip = -1.0 if own > 0 else 1.0  # the subbasin's own icon lies upstream: make that side negative
                rows.append({
                    "dam": dam,
                    "subbasin": element.name,
                    "dock_entry_m": round(flip * signed_distance(line, icon[dam]), 1),
                    "w1_entry_m": round(flip * signed_distance(line, w1[element.name]), 1),
                    "subbasin_icon_m": round(flip * own, 1),
                })
        del sign
    for r in rows:
        print(f"{r['dam']:9s} {r['subbasin']:4s} dock {r['dock_entry_m']:+8.1f} m   W1 {r['w1_entry_m']:+8.1f} m")
    out.write_text(json.dumps(rows, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
