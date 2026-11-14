"""W60 check, input side: Block 2's W1 dam workbook rebuilt by Wadi2D from the same HMS depth-area DSS files.

Usage: python rebuild_w1.py OUT_DIR

Writes OUT_DIR/w1_rebuild.xlsx through ``wadi2d.workbook.make`` (what ``wadi2d workbook`` runs), and
OUT_DIR/w1_rebuild_round4.xlsx with every series first rounded to 4 decimals, as W1's step 01 wrote its CSV before
step 05 rounded it again to 3: the second file isolates the double rounding. The workbooks hold project data and
stay out of git; the comparison is compare_w1.py.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import numpy as np

from wadi2d.workbook import layout, make, sources
from wadi2d.workbook.model import WorkbookInput, rp_sort_key

HMS = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\HEC_HMS_Block_02")
RPS = sorted(
    [
        "2yr",
        "5yr",
        "10yr",
        "25yr",
        "50yr",
        "100yr",
        "200yr",
        "500yr",
        "1000yr",
        "2000yr",
        "5000yr",
        "10000yr",
        "PMP",
    ],
    key=rp_sort_key,
)
ELEMENTS = [("Faydh 01", "Faydh 01"), ("Bidah 03", "Bidah 03"), ("R5A", "R5"), ("R2A", "R2A"), ("Z4C", "Z4C")]


def main(out: str) -> int:
    folder = Path(out)
    dss = {rp: HMS / f"DA_{rp}_B1.dss" for rp in RPS}
    kw = dict(project="Block 02", method="depth-area analyses")
    print(make(folder / "w1_rebuild.xlsx", ELEMENTS, dss=dss, basin_file=HMS / "Basin_1.basin", **kw))
    dams, dt = sources.from_hms_dss(dss, ELEMENTS, HMS / "Basin_1.basin")
    for dam in dams:
        for rp, h in dam.series.items():
            dam.series[rp] = dataclasses.replace(h, t_h=np.round(h.t_h, 4), inflow=np.round(h.inflow, 4))
    wi = WorkbookInput(dams, RPS, "200yr", dt, "W1 double rounding", "HMS", **kw)
    print(layout.write(wi, folder / "w1_rebuild_round4.xlsx"))
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
