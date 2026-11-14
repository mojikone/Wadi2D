"""Probe, in HEC-HMS itself, what makes it give RIJ-R11 and RIJ-R17 two cells where its rule gives one.

Variants of Basin 3 on the project copy, each with one reach parameter changed, run under the W55 Bidah 03 storm;
each log's "Routing parameters" line is read for the reaches named. Writes into ``_work/hms_project`` only.
Usage: python probe_reach_grid.py build | read
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
PROJECT = HERE / "_work" / "hms_project"
MET = "W55 PMP Bidah 03"
WATCH = ["RIJ-R11", "RIJ-R17", "BID-R24", "BID-R21", "RIJ-R19"]
VARIANTS = {
    "P0 none": {},
    "P1 R17 slope 0.0100": {"RIJ-R17": {"Energy Slope": "0.01000"}},
    "P2 R17 width 20": {"RIJ-R17": {"Bottom Width": "20.0"}},
    "P3 R17 n 0.04": {"RIJ-R17": {"Mannings n": "0.04"}},
    "P4 R17 length 300": {"RIJ-R17": {"Length": "300.00"}},
    "P5 R11 width 50": {"RIJ-R11": {"Bottom Width": "50.0"}},
    "P6 R11 slope 0.0050": {"RIJ-R11": {"Energy Slope": "0.00500"}},
    "P7 R24 length 400.1": {"BID-R24": {"Length": "400.10"}},
    "P8 R18 length 1000": {"RIJ-R18": {"Length": "1000.00"}},
}


def changed(text: str, edits: dict[str, dict[str, str]]) -> str:
    for reach, keys in edits.items():
        start = text.index(f"Reach: {reach}\n")
        end = text.index("End:", start)
        block = text[start:end]
        for key, value in keys.items():
            block = re.sub(rf"(     {re.escape(key)}: ).*", rf"\g<1>{value}", block, count=1)
        text = text[:start] + block + text[end:]
    return text


def stem(name: str) -> str:
    return "W55_probe_" + name.split()[0]


def build() -> None:
    base = (PROJECT / "Basin_3.basin").read_text(encoding="utf-8")
    hms = (PROJECT / "HEC_HMS_Block_02.hms").read_text(encoding="utf-8")
    runs = (PROJECT / "HEC_HMS_Block_02.run").read_text(encoding="utf-8")
    script = ["from hms.model.JythonHms import *", f'OpenProject("HEC HMS Block 02", r"{PROJECT}")']
    for name, edits in VARIANTS.items():
        basin_name = f"Probe {name.split()[0]}"
        text = changed(base, edits).replace("Basin: Basin 3\n", f"Basin: {basin_name}\n", 1)
        (PROJECT / f"{stem(name)}.basin").write_text(text, encoding="utf-8")
        if f"Basin: {basin_name}\n" not in hms:
            hms += f"Basin: {basin_name}\n     Filename: {stem(name)}.basin\n     Description: \nEnd:\n\n"
        run = f"Probe run {name.split()[0]}"
        if f"Run: {run}\n" not in runs:
            runs += (f"Run: {run}\n     Default Description: Yes\n     Log File: {stem(name)}.log\n"
                     f"     DSS File: {stem(name)}.dss\n     Is Save Spatial Results: No\n     Basin: {basin_name}\n"
                     f"     Precip: {MET}\n     Control: Control 1\n     Time-Series Output: Save All\nEnd:\n\n")
        script.append(f'ComputeRun("{run}")')
    met = (PROJECT / "W55_PMP_Bidah_03.met").read_text(encoding="utf-8")
    for name in VARIANTS:
        line = f"     Use Basin Model: Probe {name.split()[0]}\n"
        if line not in met:
            met = met.replace("     Use Basin Model: Basin 3\n", "     Use Basin Model: Basin 3\n" + line, 1)
    (PROJECT / "W55_PMP_Bidah_03.met").write_text(met, encoding="utf-8")
    (PROJECT / "HEC_HMS_Block_02.hms").write_text(hms, encoding="utf-8")
    (PROJECT / "HEC_HMS_Block_02.run").write_text(runs, encoding="utf-8")
    (PROJECT / "w55_probe.py").write_text("\n".join(script + ["Exit(1)"]) + "\n", encoding="utf-8")


def read() -> None:
    line = re.compile(r'reach "(.+)": Delta t \(sec\) ([\d.]+)\s+Delta x \(m\) ([\d.]+)')
    out = {}
    for name in VARIANTS:
        log = PROJECT / f"{stem(name)}.log"
        found = {m.group(1): (float(m.group(2)), float(m.group(3))) for m in line.finditer(log.read_text(errors="replace"))}
        out[name] = {reach: found.get(reach) for reach in WATCH}
        print(f"{name:32s} " + "  ".join(f"{r} dt {v[0]:g} dx {v[1]:g}" if v else f"{r} -" for r, v in out[name].items()))
    (HERE / "results" / "probe_reach_grid.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    {"build": build, "read": read}[sys.argv[1]]()
