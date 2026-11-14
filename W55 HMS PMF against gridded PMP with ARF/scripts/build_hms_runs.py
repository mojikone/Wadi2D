"""Test 2, the HMS side: five simulation runs on a copy of his project, one per dam, Basin 3 with its reservoirs.

Each run is set up as his depth-area runs set up a point: a Hypothetical Storm met, Point Depth = the dam
catchment's mean depth of the DSS PMP grid, Specified Pattern = that catchment's own cumulative pattern from the same
grid (a Percent Graph of 145 ordinates, as his FM PMP pattern has), Storm Duration 24 h, Storm Area = the dam's
drainage area, Depth-Area Reduction User-Specified with his ARF FM table, Uniform Depth Yes. A simulation run with
the storm area set to the point's drainage area is what HMS's depth-area analysis computes at that point (his own
log: "Storm area is 74.30 sq.km. for analysis point Faydh 01").

Writes into ``_work/hms_project`` only (a copy): the met files, the percent graphs (pdata and its DSS), the run
file, a project file listing them, and the Jython script HMS runs. Inputs from ``results/pmf_inputs.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

import hecdss
import numpy as np

HERE = Path(__file__).resolve().parents[1]
PROJECT = HERE / "_work" / "hms_project"
NAME = "HEC_HMS_Block_02"
STAMP = ("     Last Modified Date: 13 November 2026\n", "     Last Modified Time: 12:00:00\n")


def met_name(dam: str) -> str:
    return f"W55 PMP {dam}"


def file_stem(dam: str) -> str:
    return "W55_PMP_" + dam.replace(" ", "_")


def met_text(dam: str, row: dict, template: str) -> str:
    """His FM PMP met with the storm block replaced: point depth, this dam's pattern and storm area."""
    head, _, rest = template.partition("Precip Method Parameters: Hypothetical Storm")
    _, _, subbasins = rest.partition("End:\n")
    head = head.replace("Meteorology: FM PMP", f"Meteorology: {met_name(dam)}", 1)
    for other in ("Basin 1", "Basin 2"):  # the copy holds Basin 3 alone
        head = head.replace(f"     Use Basin Model: {other}\n", "")
    storm = (
        "Precip Method Parameters: Hypothetical Storm\n" + "".join(STAMP)
        + "     Precipitation Method: Point Depth\n"
        + f"     Storm Depth: {row['grid_depth_mm']:.6f}\n"
        + "     Storm Type: Specified Pattern\n"
        + "     Storm Duration: 24\n"
        + f"     Pattern Name: {met_name(dam)}\n"
        + f"     Storm Area: {row['drainage_area_km2']:.6f}\n"
        + "     Depth-Area Reduction Method: User-Specified\n"
        + "     Reduction Table Name: ARF FM\n"
        + "     Uniform Depth: Yes\n"
        + "End:\n"
    )
    return head + storm + subbasins


def pdata_block(dam: str) -> str:
    return (
        f"Table: {met_name(dam)}\n     Table Type: Percent Graph\n" + "".join(STAMP)
        + "     X-Units: %\n     Y-Units: %\n     Use External DSS File: NO\n"
        + f"     DSS File: {NAME}.dss\n     Pathname: //{met_name(dam)}/PERCENT GRAPH///TABLE/\n"
        + "     Interpolation: Linear Interpolation\nEnd:\n\n"
    )


def run_block(dam: str) -> str:
    return (
        f"Run: {met_name(dam)}\n     Default Description: Yes\n     Log File: {file_stem(dam)}.log\n"
        f"     DSS File: {file_stem(dam)}.dss\n     Is Save Spatial Results: No\n" + "".join(STAMP)
        + f"     Basin: Basin 3\n     Precip: {met_name(dam)}\n     Control: Control 1\n"
        "     Time-Series Output: Save All\n     Time Series Results Manager Start:\n"
        "     Time Series Results Manager End:\nEnd:\n\n"
    )


def project_text(dams: list[str]) -> str:
    parts = [
        "Project: HEC HMS Block 02\n     Description: W55 copy, test 2\n     Version: 4.12\n"
        f"     Filepath Separator: \\\n     DSS File Name: {NAME}.dss\n     Time Zone ID: America/Los_Angeles\nEnd:\n\n"
    ]
    for dam in dams:
        parts.append(f"Precipitation: {met_name(dam)}\n     Filename: {file_stem(dam)}.met\n     Description: \nEnd:\n\n")
    parts.append("Basin: Basin 3\n     Filename: Basin_3.basin\n     Description: \nEnd:\n\n")
    parts.append("Control: Control 1\n     FileName: Control_1.control\n     Description: \nEnd:\n\n")
    return "".join(parts)


def write_pattern(dss: hecdss.HecDss, dam: str, row: dict) -> None:
    pattern = hecdss.PairedData.create(
        np.asarray(row["pattern_time_percent"]),
        np.asarray(row["pattern_depth_percent"]).reshape(-1, 1),
        labels=[""],
        x_units="%",
        x_type="Linear",
        y_units="%",
        y_type="Linear",
        path=f"//{met_name(dam)}/PERCENT GRAPH///TABLE/",
    )
    dss.put(pattern)


def main() -> None:
    inputs = json.loads((HERE / "results" / "pmf_inputs.json").read_text(encoding="utf-8"))
    dams = list(inputs)
    template = (PROJECT / "FM_PMP.met").read_text(encoding="utf-8")
    pdata = (PROJECT / f"{NAME}.pdata").read_text(encoding="utf-8")
    pdata = pdata.rstrip("\n") + "\n\n" + "".join(pdata_block(dam) for dam in dams if f"Table: {met_name(dam)}\n" not in pdata)
    (PROJECT / f"{NAME}.pdata").write_text(pdata, encoding="utf-8")
    dss = hecdss.HecDss(str(PROJECT / f"{NAME}.dss"))
    try:
        for dam in dams:
            write_pattern(dss, dam, inputs[dam])
    finally:
        dss.close()
    for dam in dams:
        (PROJECT / f"{file_stem(dam)}.met").write_text(met_text(dam, inputs[dam], template), encoding="utf-8")
    (PROJECT / f"{NAME}.run").write_text("".join(run_block(dam) for dam in dams), encoding="utf-8")
    (PROJECT / f"{NAME}.hms").write_text(project_text(dams), encoding="utf-8")
    script = ["from hms.model.JythonHms import *", f'OpenProject("HEC HMS Block 02", r"{PROJECT}")']
    script += [f'ComputeRun("{met_name(dam)}")' for dam in dams]
    script += ["Exit(1)"]
    (PROJECT / "w55_runs.py").write_text("\n".join(script) + "\n", encoding="utf-8")
    print("written", PROJECT)


if __name__ == "__main__":
    main()
