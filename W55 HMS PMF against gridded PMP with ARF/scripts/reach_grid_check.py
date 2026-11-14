"""The Muskingum-Cunge cells and sub-steps HMS logged for every reach of Basin 2 and 3, against routing.grid()."""

from __future__ import annotations

import re
from pathlib import Path

from wadi2d.hydrology.replication import _Project

HMS = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\HEC_HMS_Block_02\HEC_HMS_Block_02.hms")
LINE = re.compile(r'reach "(.+)": Delta t \(sec\) ([\d.]+)\s+Delta x \(m\) ([\d.]+)')
DT = 300.0

project = _Project(HMS)
seen: dict[str, tuple[float, float]] = {}
for log in sorted(HMS.parent.glob("DA_*_B[23]_daa.log")):
    for match in LINE.finditer(log.read_text(errors="replace")):
        seen[match.group(1)] = (float(match.group(2)), float(match.group(3)))
_, engine = project.model("Basin 3")
rows = []
for name, (dt_logged, dx_logged) in sorted(seen.items()):
    routing = engine.basin.elements[name].routing
    cells, dx, substeps = routing.grid(DT)
    logged_cells = round(routing.length_m / dx_logged)
    logged_sub = round(DT / dt_logged)
    ratio = routing.length_m / (routing.index_celerity * DT)
    rows.append((ratio, name, routing.length_m, cells, substeps, logged_cells, logged_sub))
rows.sort()
bad = [r for r in rows if (r[3], r[4]) != (r[5], r[6])]
print(f"{len(rows)} reaches, {len(bad)} differ")
for ratio, name, length, cells, sub, lc, ls in rows:
    flag = "  <-- differs" if (cells, sub) != (lc, ls) else ""
    if ratio < 1.2 or flag:
        print(f"{name:10s} L={length:8.1f} L/(c dt)={ratio:6.3f} grid N={cells} k={sub}  logged N={lc} k={ls}{flag}")
