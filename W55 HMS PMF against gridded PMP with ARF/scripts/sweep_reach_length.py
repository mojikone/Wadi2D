"""Sweep one reach's length in HEC-HMS (BID-R24 of Basin 3 on the project copy) and read the cells and sub-steps it
logs, to find HMS's rule for Automatic DX and DT. All variants go in one basin each and one HMS session.
Usage: python sweep_reach_length.py build | read
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
PROJECT = HERE / "_work" / "hms_project"
MET = "W55 PMP Bidah 03"
REACH = "BID-R24"
LENGTHS = [round(float(v), 1) for v in np.arange(60.0, 560.0, 20.0)] + [
    227.9, 237.4, 400.1, 448.3, 399.9, 400.2, 400.5, 400.9, 300.1, 300.5, 240.1, 239.9, 228.0, 227.8, 460.1, 1000.1,
]
CELERITY, DT = 1.524, 300.0


def key(length: float) -> str:
    return f"L{length:07.1f}".replace(".", "_")


def build() -> None:
    base = (PROJECT / "Basin_3.basin").read_text(encoding="utf-8")
    hms = (PROJECT / "HEC_HMS_Block_02.hms").read_text(encoding="utf-8")
    runs = (PROJECT / "HEC_HMS_Block_02.run").read_text(encoding="utf-8")
    met = (PROJECT / "W55_PMP_Bidah_03.met").read_text(encoding="utf-8")
    script = ["from hms.model.JythonHms import *", f'OpenProject("HEC HMS Block 02", r"{PROJECT}")']
    start = base.index(f"Reach: {REACH}\n")
    end = base.index("End:", start)
    for length in LENGTHS:
        name = f"Sweep {key(length)}"
        block = re.sub(r"(     Length: ).*", rf"\g<1>{length:.2f}", base[start:end], count=1)
        text = (base[:start] + block + base[end:]).replace("Basin: Basin 3\n", f"Basin: {name}\n", 1)
        (PROJECT / f"W55_sweep_{key(length)}.basin").write_text(text, encoding="utf-8")
        if f"Basin: {name}\n" not in hms:
            hms += f"Basin: {name}\n     Filename: W55_sweep_{key(length)}.basin\n     Description: \nEnd:\n\n"
        if f"Run: {name}\n" not in runs:
            runs += (f"Run: {name}\n     Default Description: Yes\n     Log File: W55_sweep_{key(length)}.log\n"
                     f"     DSS File: W55_sweep.dss\n     Is Save Spatial Results: No\n     Basin: {name}\n"
                     f"     Precip: {MET}\n     Control: Control 1\n     Time-Series Output: Save All\nEnd:\n\n")
        line = f"     Use Basin Model: {name}\n"
        if line not in met:
            met = met.replace("     Use Basin Model: Basin 3\n", "     Use Basin Model: Basin 3\n" + line, 1)
        if not (PROJECT / f"W55_sweep_{key(length)}.log").is_file():
            script.append(f'ComputeRun("{name}")')
    (PROJECT / "HEC_HMS_Block_02.hms").write_text(hms, encoding="utf-8")
    (PROJECT / "HEC_HMS_Block_02.run").write_text(runs, encoding="utf-8")
    (PROJECT / "W55_PMP_Bidah_03.met").write_text(met, encoding="utf-8")
    (PROJECT / "w55_sweep.py").write_text("\n".join(script + ["Exit(1)"]) + "\n", encoding="utf-8")


def read() -> None:
    pattern = re.compile(rf'reach "{REACH}": Delta t \(sec\) ([\d.]+)\s+Delta x \(m\) ([\d.]+)')
    rows = []
    for length in sorted(set(LENGTHS)):
        found = pattern.search((PROJECT / f"W55_sweep_{key(length)}.log").read_text(errors="replace"))
        dt, dx = float(found.group(1)), float(found.group(2))
        rows.append({"length": length, "ratio": length / (CELERITY * DT), "cells": round(length / dx),
                     "substeps": round(DT / dt), "dt": dt, "dx": dx})
    for row in rows:
        print(f"L {row['length']:7.1f} L/(c dt) {row['ratio']:6.3f} N {row['cells']:2d} k {row['substeps']:2d}")
    (HERE / "results" / "sweep_reach_length.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")


if __name__ == "__main__":
    {"build": build, "read": read}[sys.argv[1]]()
