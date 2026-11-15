"""W89's Muskingum cases on W59's metric HEC-HMS 4.12 test project: Source -> Reach -> Sink.

W59's inflow (400 m3/s at 6 h over a 2 m3/s base), 5 min step and 48 h window, written by W59's own
``hms_project.write_project``; only the basin text is W89's. The ``Route: Muskingum`` keys are the ones of
``wadi2d.hms.methods.MuskingumRoute`` (research note H04); HMS re-saving the basin is what proves them, since a key
HMS does not read is dropped on re-save.

Usage: ``python musk_cases.py <folder> <case> [<case> ...]`` or ``every``; writes ``_work/<folder>`` and prints the
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

# case: (K in hours, X, subreaches). With the 5-minute step, a subreach is inside 2KX <= dt <= 2K(1-X) when
# its K/n lies between dt / (2 (1 - X)) and dt / (2 X).
CASES: dict[str, tuple[float, float, int]] = {
    "musk_in_range": (1.0, 0.2, 12),  # K/n = 5 min: 2 <= 5 <= 8
    "musk_long": (3.0, 0.3, 36),  # K/n = 5 min: 3 <= 5 <= 7
    "musk_x0": (1.5, 0.0, 6),  # X = 0, a linear reservoir per subreach: 0 <= 5 <= 30
    "musk_x05": (1.0, 0.5, 12),  # X = 0.5, K/n = dt: pure translation, 5 <= 5 <= 5
    "musk_one": (0.1, 0.25, 1),  # one subreach in range: 3 <= 5 <= 9
    "musk_low": (1.0, 0.2, 1),  # dt below 2KX (24 min): the new inflow's weight negative
    "musk_low_mild": (0.5, 0.1, 1),  # dt below 2KX (6 min), barely
    "musk_high": (0.05, 0.2, 1),  # dt above 2K(1-X) (4.8 min): the old outflow's weight negative
    "musk_high_n": (1.0, 0.2, 40),  # the same through too many subreaches: K/n = 1.5 min, 2K(1-X)/n = 2.4 min
    "musk_x05_low": (1.0, 0.5, 4),  # X = 0.5 with K/n = 15 min: dt below 2KX
    # The same on a flood from a dry bed and back to it (the gage W89 Dry): what HMS does with an ordinate below zero.
    "musk_dry_in": (1.0, 0.2, 12),
    "musk_dry_low": (1.0, 0.2, 1),
    "musk_dry_high": (0.05, 0.2, 1),
    "musk_dry_x05_low": (1.0, 0.5, 4),
}
DRY_GAGE = "W89 Dry"
DRY_PATH = "//DRY/FLOW//5MIN/W89/"


def dry_inflow() -> np.ndarray:
    """A flood on a dry bed: nothing for 1 h, a sine rise to 400 m3/s at 3 h, a straight fall to nothing at 9 h."""
    hours = np.arange(0, 48 * 60 + w59.STEP_MINUTES, w59.STEP_MINUTES) / 60.0
    rise = 400.0 * np.sin(0.5 * np.pi * np.clip((hours - 1.0) / 2.0, 0.0, 1.0)) ** 2
    fall = 400.0 * np.clip((9.0 - hours) / 6.0, 0.0, 1.0)
    return np.where(hours <= 3.0, rise, fall)


def source_block(case: str) -> str:
    return w59.SOURCE_BLOCK.replace("W59 Inflow", DRY_GAGE) if "_dry_" in case else w59.SOURCE_BLOCK


EXTRA_KEYS = "     Draw Icons By Default: Yes\n"  # the control: a key HMS does not read, dropped on re-save


def basin_text(case: str) -> str:
    k, x, steps = CASES[case]
    stamp = w59.STAMP
    return (
        f"Basin: {w59.basin_name(case)}\n{stamp}     Version: 4.12\n     Filepath Separator: \\\n     Unit System: Metric\n"
        "     Missing Flow To Zero: No\n     Enable Flow Ratio: No\n     Compute Local Flow At Junctions: No\n"
        "     Unregulated Output Required: No\n\n     Enable Sediment Routing: No\nEnd:\n\n"
        f"Source: Inflow\n{stamp}     Canvas X: 0\n     Canvas Y: 1000\n     Downstream: Reach\n\n"
        f"{source_block(case)}End:\n\n"
        f"Reach: Reach\n{stamp}     Canvas X: 0\n     Canvas Y: 500\n     From Canvas X: 0\n     From Canvas Y: 1000\n"
        "     Downstream: Outlet\n\n"
        f"     Route: Muskingum\n     Muskingum K: {k}\n     Muskingum x: {x}\n     Muskingum Steps: {steps}\n"
        "     Initial Variable: Combined Inflow\n     Channel Loss: None\nEnd:\n\n"
        f"Sink: Outlet\n{stamp}     Canvas X: 0\n     Canvas Y: 0\nEnd:\n\n"
        "Basin Schematic Properties:\n     Last View N: 2000\n     Last View S: -500\n     Last View W: -1000\n"
        "     Last View E: 1000\n     Maximum View N: 2000\n     Maximum View S: -500\n     Maximum View W: -1000\n"
        "     Maximum View E: 1000\n     Extent Method: Elements Maximum\n     Buffer: 0\n     Draw Icons: Yes\n"
        f"{EXTRA_KEYS}     Draw Gridlines: No\n     Draw Flow Direction: No\n     Fix Element Locations: No\n"
        "     Fix Hydrologic Order: No\n     Map: \nEnd:\n"
    )


w59.CASES = CASES  # write_project reads only the names
w59.basin_text = basin_text


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
    script = folder / "w89_run.py"
    script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return script

def write(folder: Path, cases: list[str]) -> None:
    w59.write_project(folder, cases)
    gage = folder / f"{w59.STEM}.gage"
    gage.write_text(
        gage.read_text(encoding="utf-8")
        + f"\nGage: {DRY_GAGE}\n{w59.STAMP}     Reference Height Units: Meters\n     Reference Height: 10.0\n"
        "     Gage Type: Flow\n     Units: M3/S\n     Data Type: INST-VAL\n     Data Source Type: External DSS\n"
        "     Variant: Variant-1\n       Last Variant Modified Date: 14 November 2026\n"
        "       Last Variant Modified Time: 12:00:00\n       Default Variant: Yes\n"
        f"       DSS File Name: {w59.STEM}.dss\n       DSS Pathname: {DRY_PATH}\n"
        f"       Start Time: {w59.START[0]}, {w59.START[1]}\n       End Time: {w59.END[0]}, {w59.END[1]}\n"
        "     End Variant: Variant-1\nEnd:\n",
        encoding="utf-8",
    )
    dss = hecdss.HecDss(str(folder / f"{w59.STEM}.dss"))
    try:
        values = dry_inflow()
        first = datetime(2000, 1, 31, 12, 0)
        times = [first + timedelta(minutes=w59.STEP_MINUTES * k) for k in range(len(values))]
        dss.put(hecdss.RegularTimeSeries.create(
            values=values, times=times, units="M3/S", data_type="INST-VAL", interval="5MIN", path=DRY_PATH,
        ))
    finally:
        dss.close()


def main() -> None:
    folder = HERE / "_work" / sys.argv[1]
    cases = list(CASES) if sys.argv[2:] == ["every"] else sys.argv[2:]
    write(folder, cases)
    print(jython(folder, cases))


if __name__ == "__main__":
    main()
