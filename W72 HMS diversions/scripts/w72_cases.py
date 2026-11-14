"""W72's diversion cases on W59's metric HEC-HMS 4.12 test project: Source -> Diversion -> Sink, diverted to a Sink.

W59's inflow (400 m3/s at 6 h over a 2 m3/s base), 5 min step and 48 h window, written by W59's own
``hms_project.write_project``; only the basin text, two tables and a second gage are W72's. Each ``Diverter`` block
is a guess built from the string constants of ``hms.jar`` (``hms/model/basin/e/*.class``); HMS re-saving the basin is
what proves it, since a key HMS does not read is dropped on re-save.

Usage: ``python w72_cases.py <folder> <case> [<case> ...]`` or ``every``; writes ``_work/<folder>`` and prints the
Jython script for W59's ``run_hms.ps1``.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import hecdss
import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE.parent / "W59 HMS reservoir structures" / "scripts"))
import hms_project as w59  # noqa: E402

DIVERT_PATH = "//DIVERT/FLOW//5MIN/W72/"
# HMS 4.12 refuses an inflow above the last row (ERROR 42824, measured on a table ending at 300 m3/s).
IDT_IN = np.array([0.0, 50.0, 200.0, 300.0, 500.0])
IDT_OUT = np.array([0.0, 0.0, 100.0, 150.0, 150.0])
# The channel at the diversion: stage 100 m at no flow, 1,000 m3/s at 110 m.
CHANNEL_Z = np.array([100.0, 101.0, 102.0, 103.0, 104.0, 106.0, 108.0, 110.0])
CHANNEL_Q = np.array([0.0, 10.0, 40.0, 90.0, 160.0, 350.0, 620.0, 1000.0])
# The diversion channel's tailwater against the diverted flow.
TAIL_Z = np.array([100.0, 102.0, 103.0, 104.0, 105.0, 107.0])
TAIL_Q = np.array([0.0, 20.0, 60.0, 120.0, 250.0, 1000.0])
PUMP_HEAD = np.array([0.0, 5.0, 10.0, 15.0, 20.0])
PUMP_Q = np.array([30.0, 25.0, 20.0, 10.0, 0.0])
w59.TABLES.update({
    "W72 IDT": ("Inflow-Diversion", "M3/S", "M3/S", "INFLOW-DIVERSION", IDT_IN, IDT_OUT),
    "W72 Channel": ("Stage-Flow", "M", "M3/S", "STAGE-FLOW", CHANNEL_Z, CHANNEL_Q),
    "W72 Tail": ("Stage-Flow", "M", "M3/S", "STAGE-FLOW", TAIL_Z, TAIL_Q),
    "W72 Pump": ("Stage-Flow", "M", "M3/S", "STAGE-FLOW", PUMP_HEAD, PUMP_Q),
})


def specified() -> np.ndarray:
    """The diversion gage: 150 m3/s in a sine over the first day, above the inflow in the first hour."""
    hours = np.arange(0, 48 * 60 + w59.STEP_MINUTES, w59.STEP_MINUTES) / 60.0
    return np.where(hours < 24.0, 20.0 + 130.0 * np.sin(np.pi * hours / 24.0), 5.0)


def diverter(method: str, limits: str = "") -> str:
    return f"\n     Diverter: {method}\n{limits}{BODIES[method]}     End Diverter:\n"


PUMP_BLOCK = (
    "     Pump: Head-Discharge Pump\n     Number Of Pumps: 2\n     Intake Elevation: 101\n"
    "     Discharge Elevation: 112\n     Switch-On Elevation: 103\n     Switch-Off Elevation: 102\n"
    "     Minimum Run Time: \n     Minimum Rest Time: \n     Head-Discharge Table Name: W72 Pump\n"
    "     Equipment Head Loss: 0.5\n     End Pump:\n"
)
WEIR = (
    "     Diverter Rating Table Name: W72 Channel\n     Weir Elevation: 103\n     Weir Length: 20\n"
    "     Weir Coefficient: 1.6\n"
)
BODIES = {
    "Inflow-Diversion Table": "     Inflow Diversion Table Name: W72 IDT\n",
    "Constant": "     Constant Flow: 50\n",
    "Specified": "     Flow Gage: W72 Divert\n",
    "Lateral Weir": WEIR,
    "Pump": "     Diverter Rating Table Name: W72 Channel\n" + PUMP_BLOCK,
}
WEIR_TW = WEIR.replace("Weir Elevation", "Tailwater Rating Table Name: W72 Tail\n     Weir Elevation")
MAX_FLOW = "     Maximum Diversion Flow: 60\n"
MAX_VOLUME = "     Maximum Diversion Volume: 2000\n"

# case: (Divert To, Diverter block)
CASES: dict[str, tuple[str | None, str]] = {
    "div_table": ("Diverted", diverter("Inflow-Diversion Table")),
    "div_constant": ("Diverted", diverter("Constant")),
    "div_specified": ("Diverted", diverter("Specified")),
    "div_weir": ("Diverted", diverter("Lateral Weir")),
    "div_weir_tw": ("Diverted", diverter("Lateral Weir").replace(WEIR, WEIR_TW)),
    "div_pump": ("Diverted", diverter("Pump")),
    "div_max_flow": ("Diverted", diverter("Inflow-Diversion Table", MAX_FLOW)),
    "div_max_volume": ("Diverted", diverter("Constant", MAX_VOLUME)),
    "div_not_connected": (None, diverter("Inflow-Diversion Table")),
    # A tailwater rating high enough to drown the weir (submergence past 0.76) near the peak.
    "div_weir_drowned": ("Diverted", diverter("Lateral Weir").replace(WEIR, WEIR_TW.replace("W72 Tail", "W72 Tail High"))),
    # On at 104 m, off at 103.6 m: the pump's draw pulls the stage under the off level, so it cycles.
    "div_pump_cycle": ("Diverted", diverter("Pump").replace("Switch-On Elevation: 103", "Switch-On Elevation: 104")
                       .replace("Switch-Off Elevation: 102", "Switch-Off Elevation: 103.6")),
}
w59.TABLES["W72 Tail High"] = (
    "Stage-Flow", "M", "M3/S", "STAGE-FLOW", np.array([100.0, 103.5, 104.0, 105.0, 106.0, 108.0]),
    np.array([0.0, 1.0, 20.0, 60.0, 150.0, 1000.0]),
)


def basin_text(case: str) -> str:
    target, block = CASES[case]
    divert = f"     Divert To: {target}\n" if target else ""
    stamp = w59.STAMP
    return (
        f"Basin: {w59.basin_name(case)}\n{stamp}     Version: 4.12\n     Filepath Separator: \\\n     Unit System: Metric\n"
        "     Missing Flow To Zero: No\n     Enable Flow Ratio: No\n     Compute Local Flow At Junctions: No\n"
        "     Unregulated Output Required: No\n\n     Enable Sediment Routing: No\nEnd:\n\n"
        f"Source: Inflow\n{stamp}     Canvas X: 0\n     Canvas Y: 1000\n     Downstream: Diversion\n\n"
        f"{w59.SOURCE_BLOCK}End:\n\n"
        f"Diversion: Diversion\n{stamp}     Canvas X: 0\n     Canvas Y: 500\n     Downstream: Outlet\n{divert}"
        f"{block}End:\n\n"
        f"Sink: Outlet\n{stamp}     Canvas X: 0\n     Canvas Y: 0\nEnd:\n\n"
        f"Sink: Diverted\n{stamp}     Canvas X: 500\n     Canvas Y: 0\nEnd:\n\n"
        "Basin Schematic Properties:\n     Last View N: 2000\n     Last View S: -500\n     Last View W: -1000\n"
        "     Last View E: 1000\n     Maximum View N: 2000\n     Maximum View S: -500\n     Maximum View W: -1000\n"
        "     Maximum View E: 1000\n     Extent Method: Elements Maximum\n     Buffer: 0\n     Draw Icons: Yes\n"
        "     Draw Gridlines: No\n     Draw Flow Direction: No\n     Fix Element Locations: No\n"
        "     Fix Hydrologic Order: No\n     Map: \nEnd:\n"
    )


w59.CASES = CASES  # write_project reads only the names
w59.basin_text = basin_text


def write(folder: Path, cases: list[str]) -> None:
    w59.write_project(folder, cases)
    gage = folder / f"{w59.STEM}.gage"
    gage.write_text(
        gage.read_text(encoding="utf-8")
        + f"\nGage: W72 Divert\n{w59.STAMP}     Reference Height Units: Meters\n     Reference Height: 10.0\n"
        "     Gage Type: Flow\n     Units: M3/S\n     Data Type: INST-VAL\n     Data Source Type: External DSS\n"
        "     Variant: Variant-1\n       Last Variant Modified Date: 14 November 2026\n"
        "       Last Variant Modified Time: 12:00:00\n       Default Variant: Yes\n"
        f"       DSS File Name: {w59.STEM}.dss\n       DSS Pathname: {DIVERT_PATH}\n"
        f"       Start Time: {w59.START[0]}, {w59.START[1]}\n       End Time: {w59.END[0]}, {w59.END[1]}\n"
        "     End Variant: Variant-1\nEnd:\n",
        encoding="utf-8",
    )
    dss = hecdss.HecDss(str(folder / f"{w59.STEM}.dss"))
    try:
        values = specified()
        first = datetime(2000, 1, 31, 12, 0)
        times = [first + timedelta(minutes=w59.STEP_MINUTES * k) for k in range(len(values))]
        dss.put(hecdss.RegularTimeSeries.create(
            values=values, times=times, units="M3/S", data_type="INST-VAL", interval="5MIN", path=DIVERT_PATH,
        ))
    finally:
        dss.close()


def jython(folder: Path, cases: list[str]) -> Path:
    """Each case on its own, re-saved then computed: one case HMS refuses does not stop the others."""
    lines = ["from hms.model.JythonHms import *", f'OpenProject("{w59.NAME}", r"{folder}")']
    for case in cases:
        name = w59.basin_name(case)
        lines += [
            "try:",
            f'    OpenBasinModel("{name}")',
            f'    SaveBasinModelAs("{name} saved")',
            f'    ComputeRun("{name}")',
            "except Exception as error:",
            f'    print("CASE FAILED {case}: %s" % error)',
        ]
    lines.append("Exit(1)")
    script = folder / "w72_run.py"
    script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return script


def main() -> None:
    folder = HERE / "_work" / sys.argv[1]
    cases = list(CASES) if sys.argv[2:] == ["every"] else sys.argv[2:]
    write(folder, cases)
    print(jython(folder, cases))


if __name__ == "__main__":
    main()
