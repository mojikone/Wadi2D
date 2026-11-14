"""A copy of Block 2's HMS project whose Bidah 03 reservoir routes by W59's outflow structures, for the dock check.

His project is read-only: the copy goes to the folder given. In ``Basin_3.basin`` the reservoir's Modified Puls curve is
replaced by Controlled Outflow on its own elevation-area table, with an orifice, the project's own elevation-discharge
table as a rating-curve spillway, and a level dam top; every key as W59's HMS-saved test basins write it. Its outflow goes
to a sink of its own in place of BID-R1: with every subbasin on the grid, the reach below would carry rain-on-grid
subbasins and the engine refuses that route (their rain would fall twice).

    python hms_copy.py <out folder>
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

HMS = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\HEC_HMS_Block_02")
FILES = (
    "HEC_HMS_Block_02.hms", "HEC_HMS_Block_02.run", "HEC_HMS_Block_02.gage", "HEC_HMS_Block_02.pdata",
    "HEC_HMS_Block_02.dss", "Basin_3.basin", "FM_200yr.met", "Control_1.control",
)  # fmt: skip
RESERVOIR = "Bidah 03 Reservoir"
SINK = "W68 Outlet"
DOWNSTREAM = "     Downstream: BID-R1\n"
OLD = """     Route: Modified Puls
     Routing Curve: Elevation-Area-Outflow
     Initial Elevation: 84.70
     Elevation-Area Table: Elev-Area Bidah 03
     Elevation-Outflow Table: Elev-Dis Bidah 03
     Primary Table: Elevation-Area
"""
NEW = """     Route: Controlled Outflow
     Routing Curve: Elevation-Area
     Initial Elevation: 84.70
     Elevation-Area Table: Elev-Area Bidah 03
     Adaptive Control: On
     Main Tailwater Condition: None
     Auxiliary Tailwater Condition: None

     Conduit: Orifice
     Conduit Outlet: Main
     Orifice Coefficient: 0.6
     Orifice Area: 1.5
     Centerline Elevation: 86
     Number Barrels: 2
     End Conduit:

     Spillway: Rating Curve Spillway
     Spillway Outlet: Main
     Spillway Rating Curve Name: Elev-Dis Bidah 03
     End Spillway:

     Dam Top: Level Dam
     Dam Top Outlet: Main
     Overflow Coefficient: 1.7
     Top Length: 300
     Top Elevation: 104
     End Dam Top:
"""


def make(out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        shutil.copy2(HMS / name, out / name)
    basin = out / "Basin_3.basin"
    text = basin.read_text(encoding="utf-8")
    start = text.index(f"Reservoir: {RESERVOIR}\n")
    end = text.index("End:", start)
    block = text[start:end]
    assert block.count(OLD) == 1 and block.count(DOWNSTREAM) == 1, "the reservoir is no longer as W68 found it"
    block = block.replace(OLD, NEW).replace(DOWNSTREAM, f"     Downstream: {SINK}\n")
    sink = f"End:\n\nSink: {SINK}\n     Canvas X: 438900.0\n     Canvas Y: 2726600.0\n"
    basin.write_text(text[:start] + block + sink + text[end:], encoding="utf-8")
    return out


if __name__ == "__main__":
    print(make(Path(sys.argv[1])))
