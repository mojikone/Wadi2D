"""W62's test cases on W59's metric HEC-HMS 4.12 project: gated spillways, pumps and culverts.

Same project, inflow (400 m3/s at 6 h), pool (100 to 125 m) and 48 h window as W59 (``W59 .../scripts/hms_project.py``),
which this module extends with new cases and tables; nothing of W59's is changed. Each block below is a guess at the
format, built from the string constants of ``hms.jar`` (``jar_strings.py``) and HMS's own ``river_bend`` sample
(``sample_blocks.py``); HMS re-saving the basin is what proves it (a key HMS does not read is dropped on re-save).

Usage: ``python hms_cases.py <folder> <case> [<case> ...]`` or ``every``; writes the project to ``_work/<folder>`` and
prints the Jython script for ``run_hms.ps1``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE.parent / "W59 HMS reservoir structures" / "scripts"))
import hms_project as w59  # noqa: E402

PUMP_HEAD = np.array([0.0, 5.0, 10.0, 15.0, 20.0])
PUMP_Q = np.array([8.0, 7.0, 6.0, 3.0, 0.0])
w59.TABLES["W62 Pump"] = ("Stage-Flow", "M", "M3/S", "STAGE-FLOW", PUMP_HEAD, PUMP_Q)



def broad_open(length: float) -> str:
    """A broad-crested spillway to carry gates: HMS requires the gates' widths to add up to its crest length."""
    return (
        "\n     Spillway: Broad-Crested Spillway\n     Spillway Outlet: Main\n"
        f"     Spillway Crest Length: {length:g}\n     Spillway Crest Elevation: 108\n     Spillway Coefficient: 1.6\n"
    )


SLUICE = (
    "\n     Spillway Gate: Sluice\n     Number Gates: 2\n     Gate Width: 10\n     Gate Coefficient: 0.6\n"
    "     Orifice Coefficient: 0.8\n     Gate Control: Fixed Opening\n     Gate Opening: 1.5\n"
    "     End Gate Control:\n     End Gate:\n"
)
RADIAL = (
    "\n     Spillway Gate: Radial\n     Number Gates: 2\n     Gate Width: 10\n     Gate Coefficient: 0.7\n"
    "     Orifice Coefficient: 0.8\n     Trunnion Height: 3\n     Trunnion Exponent: 0.16\n     Opening Exponent: 0.72\n"
    "     Head Exponent: 0.62\n     Gate Control: Fixed Opening\n     Gate Opening: 1.5\n"
    "     End Gate Control:\n     End Gate:\n"
)
END_SPILLWAY = "     End Spillway:\n"


def pump(units: int, on: float, off: float, intake: float, run: str = "", rest: str = "") -> str:
    return (
        f"\n     Pump: Head-Discharge Pump\n     Pump Outlet: Main\n     Number Of Pumps: {units}\n"
        f"     Intake Elevation: {intake}\n     Discharge Elevation: 112\n     Switch-On Elevation: {on}\n"
        f"     Switch-Off Elevation: {off}\n     Minimum Run Time: {run}\n     Minimum Rest Time: {rest}\n"
        "     Head-Discharge Table Name: W62 Pump\n     Equipment Head Loss: 0.5\n     End Pump:\n"
    )


NEW_CASES = {
    "gate_sluice": (w59.NO_TAILWATER, broad_open(20) + SLUICE + END_SPILLWAY, w59.ZERO_EVAPORATION),
    "gate_radial": (w59.NO_TAILWATER, broad_open(20) + RADIAL + END_SPILLWAY, w59.ZERO_EVAPORATION),
    "gate_two": (w59.NO_TAILWATER, broad_open(40) + SLUICE + RADIAL + END_SPILLWAY, w59.ZERO_EVAPORATION),
    "pump": (w59.NO_TAILWATER, w59.RATING + pump(2, 106.5, 104.5, 103.5), w59.ZERO_EVAPORATION),
    # Ten units drain the pool below the off level in the recession, and the inflow refills it: the pump cycles.
    "pump_cycle": (w59.NO_TAILWATER, w59.RATING + pump(10, 105.2, 105.0, 104.0), w59.ZERO_EVAPORATION),
    # Run 40 and rest 15 changed nothing against pump_cycle (on 31 h, off 13.4 h), so the unit is not hours. Run 2000
    # and rest 900 bind if it is minutes: the pump stays on past the off level until the pool falls under the intake,
    # then stays off to the end.
    "pump_times": (w59.NO_TAILWATER, w59.RATING + pump(10, 105.2, 105.0, 104.0, "2000", "900"), w59.ZERO_EVAPORATION),
    "pump_rest": (w59.NO_TAILWATER, w59.RATING + pump(10, 105.2, 105.0, 104.0, "", "900"), w59.ZERO_EVAPORATION),
    # The intake at the switch-on level: the pool never stands above the intake with the pump off, where HMS's books
    # lose a sixtieth of each step's net inflow (found on pump_cycle), so this one routes against HMS step by step.
    # HMS refuses a switch-off level under the intake (error 42585), so all three meet.
    "pump_closed": (w59.NO_TAILWATER, w59.RATING + pump(2, 106.5, 106.5, 106.5), w59.ZERO_EVAPORATION),
    # The switch tolerance: pump_cycle's pool starts steps 1.3 and 0.36 mm under 105.2 m, and 0.86 mm over 105.0 m.
    "pump_on_band": (w59.NO_TAILWATER, w59.RATING + pump(10, 105.1993, 105.0, 104.0), w59.ZERO_EVAPORATION),
    "pump_off_band": (w59.NO_TAILWATER, w59.RATING + pump(10, 105.2, 105.0234, 104.0), w59.ZERO_EVAPORATION),
    "pump_intake": (w59.NO_TAILWATER, w59.RATING + pump(10, 105.2, 105.0, 104.9, "1", ""), w59.ZERO_EVAPORATION),
    "pump_tw": (w59.FIXED_TAILWATER, w59.RATING + pump(2, 106.5, 104.5, 103.5), w59.ZERO_EVAPORATION),
}
w59.CASES.update(NEW_CASES)


def main() -> None:
    folder = HERE / "_work" / sys.argv[1]
    cases = list(NEW_CASES) if sys.argv[2:] == ["every"] else sys.argv[2:]
    w59.write_project(folder, cases)
    print(jython(folder, cases))


def jython(folder: Path, cases: list[str]) -> Path:
    """W59's script, with each case on its own: one case HMS refuses does not stop the others."""
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
    script = folder / "w62_run.py"
    script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return script


if __name__ == "__main__":
    main()
