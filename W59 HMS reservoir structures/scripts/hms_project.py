"""A small metric HEC-HMS 4.12 project written from scratch: one basin per reservoir case, Source -> Reservoir -> Sink.

Nothing here touches his projects. The project goes to ``_work/<folder>``; HMS is run on it by ``run_hms.ps1`` with a
Jython script. Every case shares one inflow hydrograph (a discharge gage in the project DSS) and one control window
that crosses a month boundary, so monthly evaporation changes rate inside the run.

Usage: ``python hms_project.py <folder> <case> [<case> ...]`` with cases from :data:`CASES`, or ``probe``.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import hecdss
import numpy as np

HERE = Path(__file__).resolve().parents[1]
NAME = "W59 structures"
STEM = "W59_structures"
STAMP = "     Last Modified Date: 14 November 2026\n     Last Modified Time: 12:00:00\n"
STEP_MINUTES = 5
START = ("31 January 2000", "12:00")
END = ("2 February 2000", "12:00")
INFLOW_PATH = "//INFLOW/FLOW//5MIN/W59/"
BASE_M3S = 2.0
PEAK_M3S = 400.0
PEAK_H = 6.0
RECESSION_H = 30.0

# The pool: 100 to 125 m, area rising from 0.2 to 2.7 km2.
POOL_Z = np.arange(100.0, 126.0, 1.0)
POOL_A = 2.0e5 + 1.0e5 * (POOL_Z - POOL_Z[0])
POOL_S = np.concatenate(([0.0], np.cumsum(np.diff(POOL_Z) / 3.0 * (POOL_A[:-1] + POOL_A[1:] + np.sqrt(POOL_A[:-1] * POOL_A[1:])))))
RATING_Z = np.array([100.0, 106.0, 107.0, 108.0, 110.0, 112.0, 115.0, 120.0, 125.0])
RATING_Q = np.array([0.0, 0.0, 5.0, 20.0, 80.0, 180.0, 380.0, 800.0, 1300.0])
SEEP_OUT_X = np.array([0.0, 5.0, 10.0, 25.0])
SEEP_OUT_Q = np.array([0.0, 0.5, 1.5, 6.0])
SEEP_IN_X = np.array([0.0, 5.0, 25.0])
SEEP_IN_Q = np.array([0.0, 0.2, 1.0])
EVAPORATION_MM = [300.0, 450.0, 200.0, 180.0, 160.0, 150.0, 140.0, 130.0, 120.0, 110.0, 100.0, 90.0]


def inflow() -> np.ndarray:
    """The test hydrograph at 5 min over the whole window: a sine rise to the peak, an exponential fall."""
    hours = np.arange(0, 48 * 60 + STEP_MINUTES, STEP_MINUTES) / 60.0
    rise = BASE_M3S + (PEAK_M3S - BASE_M3S) * np.sin(0.5 * np.pi * np.clip(hours / PEAK_H, 0.0, 1.0)) ** 2
    fall = BASE_M3S + (PEAK_M3S - BASE_M3S) * np.exp(-(hours - PEAK_H) / (RECESSION_H / 5.0))
    return np.where(hours <= PEAK_H, rise, fall)


TABLES = {
    # name: (table type, x units, y units, DSS C part, x, y)
    "W59 EA": ("Elevation-Area", "M", "M2", "ELEVATION-AREA", POOL_Z, POOL_A),
    "W59 Rating": ("Stage-Flow", "M", "M3/S", "STAGE-FLOW", RATING_Z, RATING_Q),
    "W59 Seep Out": ("Stage-Flow", "M", "M3/S", "STAGE-FLOW", SEEP_OUT_X, SEEP_OUT_Q),
    "W59 Seep In": ("Stage-Flow", "M", "M3/S", "STAGE-FLOW", SEEP_IN_X, SEEP_IN_Q),
    "W59 ES": ("Elevation-Storage", "M", "THOU M3", "ELEVATION-STORAGE", POOL_Z, POOL_S / 1000.0),
}

HEADER_ROUTE = (
    "     Route: Controlled Outflow\n     Routing Curve: Elevation-Area\n     Initial Elevation: 103\n"
    "     Elevation-Area Table: W59 EA\n     Adaptive Control: On\n"
)
NO_TAILWATER = "     Main Tailwater Condition: None\n     Auxiliary Tailwater Condition: None\n"
FIXED_TAILWATER = (
    "     Main Tailwater Condition: Fixed Stage\n     Main Fixed Tailwater Stage: 103\n"
    "     Auxiliary Tailwater Condition: None\n"
)
# Above the dam top's crest (109.5 m), so the drowned rule of the dam top is exercised.
HIGH_TAILWATER = (
    "     Main Tailwater Condition: Fixed Stage\n     Main Fixed Tailwater Stage: 110.2\n"
    "     Auxiliary Tailwater Condition: None\n"
)
SEEP_IN_TAILWATER = (
    "     Main Tailwater Condition: Fixed Stage\n     Main Fixed Tailwater Stage: 105\n"
    "     Auxiliary Tailwater Condition: None\n"
)
STORAGE_ROUTE = (
    "     Route: Controlled Outflow\n     Routing Curve: Elevation-Storage\n     Initial Elevation: 103\n"
    "     Elevation-Storage Table: W59 ES\n     Adaptive Control: On\n"
)
ZERO_EVAPORATION = "\n     Evaporation Method: Zero Evaporation\n     End Evaporation:\n"
MONTHLY_EVAPORATION = (
    "\n     Evaporation Method: Monthly Evaporation\n"
    + "".join(f"     Evaporation Rate: {depth}\n" for depth in EVAPORATION_MM)
    + "     End Evaporation:\n"
)
BROAD = (
    "\n     Spillway: Broad-Crested Spillway\n     Spillway Outlet: Main\n     Spillway Crest Length: 60\n"
    "     Spillway Crest Elevation: 108\n     Spillway Coefficient: 1.6\n     End Spillway:\n"
)
RATING = (
    "\n     Spillway: Rating Curve Spillway\n     Spillway Outlet: Main\n"
    "     Spillway Rating Curve Name: W59 Rating\n     End Spillway:\n"
)
ORIFICE = (
    "\n     Conduit: Orifice\n     Conduit Outlet: Main\n     Number Barrels: 2\n     Centerline Elevation: 101\n"
    "     Orifice Area: 1.5\n     Orifice Coefficient: 0.6\n     End Conduit:\n"
)
LEVEL_DAM = (
    "\n     Dam Top: Level Dam\n     Dam Top Outlet: Main\n     Top Elevation: 109.5\n     Top Length: 150\n"
    "     Overflow Coefficient: 1.7\n     End Dam Top:\n"
)
SEEPAGE = (
    "\n     Dam Seepage: Tabular Dam Seepage\n     Dam Seepage Outlet: Main\n"
    "     Pool-To-Tailwater Table Name: W59 Seep Out\n     Tailwater-To-Pool Table Name: W59 Seep In\n"
    "     End Dam Seepage:\n"
)

# case: (tailwater block, structure blocks, evaporation block)
CASES: dict[str, tuple[str, str, str]] = {
    "broad": (NO_TAILWATER, BROAD, ZERO_EVAPORATION),
    "rating": (NO_TAILWATER, RATING, ZERO_EVAPORATION),
    "orifice": (NO_TAILWATER, ORIFICE + BROAD, ZERO_EVAPORATION),
    "orifice_tw": (FIXED_TAILWATER, ORIFICE + BROAD, ZERO_EVAPORATION),
    "level_dam": (NO_TAILWATER, RATING + LEVEL_DAM, ZERO_EVAPORATION),
    "level_dam_tw": (HIGH_TAILWATER, RATING + LEVEL_DAM, ZERO_EVAPORATION),
    "seepage": (NO_TAILWATER, RATING + SEEPAGE, ZERO_EVAPORATION),
    "seepage_tw": (FIXED_TAILWATER, RATING + SEEPAGE, ZERO_EVAPORATION),
    "seepage_in": (SEEP_IN_TAILWATER, RATING + SEEPAGE, ZERO_EVAPORATION),
    "evaporation": (NO_TAILWATER, RATING, MONTHLY_EVAPORATION),
    "storage": (NO_TAILWATER, RATING, ZERO_EVAPORATION),
    "all": (FIXED_TAILWATER, ORIFICE + RATING + LEVEL_DAM + SEEPAGE, MONTHLY_EVAPORATION),
}
STORAGE_CASES = {"storage"}
SOURCE_BLOCK = "     Flow Method: GAGE_FLOW\n     Flow Gage: W59 Inflow\n     End Flow Method:\n"


def basin_name(case: str) -> str:
    return f"W59 {case}"


def basin_text(case: str) -> str:
    tailwater, structures, evaporation = CASES[case]
    return (
        f"Basin: {basin_name(case)}\n{STAMP}     Version: 4.12\n     Filepath Separator: \\\n     Unit System: Metric\n"
        "     Missing Flow To Zero: No\n     Enable Flow Ratio: No\n     Compute Local Flow At Junctions: No\n"
        "     Unregulated Output Required: No\n\n     Enable Sediment Routing: No\nEnd:\n\n"
        f"Source: Inflow\n{STAMP}     Canvas X: 0\n     Canvas Y: 1000\n     Downstream: Reservoir\n\n{SOURCE_BLOCK}End:\n\n"
        f"Reservoir: Reservoir\n{STAMP}     Canvas X: 0\n     Canvas Y: 500\n     Downstream: Outlet\n\n"
        + (STORAGE_ROUTE if case in STORAGE_CASES else HEADER_ROUTE) + tailwater + structures + evaporation + "End:\n\n"
        f"Sink: Outlet\n{STAMP}     Canvas X: 0\n     Canvas Y: 0\nEnd:\n\n"
        "Basin Schematic Properties:\n     Last View N: 2000\n     Last View S: -500\n     Last View W: -1000\n"
        "     Last View E: 1000\n     Maximum View N: 2000\n     Maximum View S: -500\n     Maximum View W: -1000\n"
        "     Maximum View E: 1000\n     Extent Method: Elements Maximum\n     Buffer: 0\n     Draw Icons: Yes\n"
        "     Draw Icons By Default: Yes\n     Draw Gridlines: No\n     Draw Flow Direction: No\n     Fix Element Locations: No\n"
        "     Fix Hydrologic Order: No\n     Map: \nEnd:\n"
    )


def file_stem(case: str) -> str:
    return f"W59_{case}"


def write_project(folder: Path, cases: list[str]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    project = [
        f"Project: {NAME}\n     Description: W59 test project, written from scratch\n     Version: 4.12\n"
        f"     Filepath Separator: \\\n     DSS File Name: {STEM}.dss\n     Time Zone ID: Asia/Dubai\nEnd:\n\n"
    ]
    for case in cases:
        project.append(f"Basin: {basin_name(case)}\n     Filename: {file_stem(case)}.basin\n     Description: \nEnd:\n\n")
        (folder / f"{file_stem(case)}.basin").write_text(basin_text(case), encoding="utf-8")
    project.append("Precipitation: W59 none\n     Filename: W59_none.met\n     Description: \nEnd:\n\n")
    project.append("Control: W59 window\n     FileName: W59_window.control\n     Description: \nEnd:\n\n")
    (folder / f"{STEM}.hms").write_text("".join(project), encoding="utf-8")
    (folder / "W59_window.control").write_text(
        f"Control: W59 window\n{STAMP}     Version: 4.12\n     Time Zone ID: Asia/Dubai\n     Time Zone GMT Offset: 14400000\n"
        f"     Start Date: {START[0]}\n     Start Time: {START[1]}\n     End Date: {END[0]}\n     End Time: {END[1]}\n"
        f"     Time Interval: {STEP_MINUTES}\nEnd:\n",
        encoding="utf-8",
    )
    (folder / "W59_none.met").write_text(
        f"Meteorology: W59 none\n{STAMP}     Version: 4.12\n     Unit System: Metric\n     Set Missing Data to Default: Yes\n"
        "     Precipitation Method: None\n     Air Temperature Method: None\n     Atmospheric Pressure Method: None\n"
        "     Dew Point Method: None\n     Wind Speed Method: None\n     Shortwave Radiation Method: None\n"
        "     Longwave Radiation Method: None\n     Snowmelt Method: None\n     Evapotranspiration Method: No Evapotranspiration\n"
        + "".join(f"     Use Basin Model: {basin_name(case)}\n" for case in cases)
        + "End:\n",
        encoding="utf-8",
    )
    (folder / f"{STEM}.gage").write_text(
        f"Gage Manager: {NAME}\n     Version: 4.12\n     Filepath Separator: \\\nEnd:\n\n"
        f"Gage: W59 Inflow\n{STAMP}     Reference Height Units: Meters\n     Reference Height: 10.0\n     Gage Type: Flow\n"
        "     Units: M3/S\n     Data Type: INST-VAL\n     Data Source Type: External DSS\n     Variant: Variant-1\n"
        "       Last Variant Modified Date: 14 November 2026\n       Last Variant Modified Time: 12:00:00\n"
        f"       Default Variant: Yes\n       DSS File Name: {STEM}.dss\n       DSS Pathname: {INFLOW_PATH}\n"
        f"       Start Time: {START[0]}, {START[1]}\n       End Time: {END[0]}, {END[1]}\n     End Variant: Variant-1\nEnd:\n",
        encoding="utf-8",
    )
    pdata = [f"Paired Data Manager: {NAME}\n     Version: 4.12\n     Filepath Separator: \\\nEnd:\n\n"]
    for name, (kind, xu, yu, cpart, _x, _y) in TABLES.items():
        pdata.append(
            f"Table: {name}\n     Table Type: {kind}\n{STAMP}     X-Units: {xu}\n     Y-Units: {yu}\n"
            f"     Use External DSS File: NO\n     DSS File: {STEM}.dss\n     Pathname: //{name}/{cpart}///TABLE/\n"
            "     Interpolation: Linear Interpolation\nEnd:\n\n"
        )
    (folder / f"{STEM}.pdata").write_text("".join(pdata), encoding="utf-8")
    runs = []
    for case in cases:
        runs.append(
            f"Run: {basin_name(case)}\n     Default Description: Yes\n     Log File: {file_stem(case)}.log\n"
            f"     DSS File: {file_stem(case)}.dss\n     Is Save Spatial Results: No\n{STAMP}"
            f"     Basin: {basin_name(case)}\n     Precip: W59 none\n     Control: W59 window\n"
            "     Time-Series Output: Save All\n     Time Series Results Manager Start:\n"
            "     Time Series Results Manager End:\nEnd:\n\n"
        )
    (folder / f"{STEM}.run").write_text("".join(runs), encoding="utf-8")
    dss = hecdss.HecDss(str(folder / f"{STEM}.dss"))
    try:
        values = inflow()
        first = datetime(2000, 1, 31, 12, 0)
        times = [first + timedelta(minutes=STEP_MINUTES * k) for k in range(len(values))]
        series = hecdss.RegularTimeSeries.create(
            values=values, times=times, units="M3/S", data_type="INST-VAL", interval="5MIN", path=INFLOW_PATH,
        )
        dss.put(series)
        for name, (_kind, xu, yu, cpart, x, y) in TABLES.items():
            table = hecdss.PairedData.create(
                np.asarray(x, dtype=float), np.asarray(y, dtype=float).reshape(-1, 1), labels=[""],
                x_units=xu, x_type="Linear", y_units=yu, y_type="Linear", path=f"//{name}/{cpart}///TABLE/",
            )
            dss.put(table)
    finally:
        dss.close()


def jython(folder: Path, cases: list[str], resave: bool) -> Path:
    """The script HMS runs: open, optionally re-save every basin under a new name (key check), compute every run."""
    lines = ["from hms.model.JythonHms import *", f'OpenProject("{NAME}", r"{folder}")']
    for case in cases:
        if resave:
            lines += [f'OpenBasinModel("{basin_name(case)}")', f'SaveBasinModelAs("{basin_name(case)} saved")']
        lines.append(f'ComputeRun("{basin_name(case)}")')
    lines.append("Exit(1)")
    script = folder / "w59_run.py"
    script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return script


def main() -> None:
    folder = HERE / "_work" / sys.argv[1]
    cases = list(CASES) if sys.argv[2:] == ["every"] else sys.argv[2:]
    write_project(folder, cases)
    print(jython(folder, cases, resave=True))


if __name__ == "__main__":
    main()
