"""W76's HEC-HMS 4.12 cases on W59's metric project: gate controls beyond Fixed Opening, and drowned gates.

Same project, inflow (400 m3/s at 6 h), pool (100 to 125 m) and 48 h window as W59 (``W59 .../scripts/hms_project.py``)
and W62's gates (2 x 10 m on a 20 m broad-crested crest at 108 m, coefficient 1.6). Nothing of W59's, W62's or W67's
is changed. The control names and keys are the string constants of ``hms.jar`` (``hms/model/basin/hydraulics``,
classes ``B``, ``ax``, ``az``, ``b``; the enum ``I``: Fixed Opening, Percent Annual Pattern, Percent Time Series,
Adjustable Gate Control); HMS re-saving the basin is what proves them.

Usage: ``python w76_cases.py <folder> <case> [<case> ...]`` or ``every``; writes the project to ``_work/<folder>`` and
prints the Jython script for W62's ``run_hms.ps1``.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import hecdss
import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE.parent / "W59 HMS reservoir structures" / "scripts"))
sys.path.insert(0, str(HERE.parent / "W62 HMS culverts gates pumps" / "scripts"))
import hms_cases as w62  # noqa: E402
import hms_project as w59  # noqa: E402

PERCENT_GAGE = "W76 Percent"
PERCENT_PATH = "//W76 PERCENT/PERCENT-GATE//1HOUR/W76/"
MAX_OPENING = 2.0
# Hourly percent open from the window's start (31 January 2000 12:00): fully open through the rise, closing to a
# quarter across the peak, a jump to three quarters at hour 20 (held), so the opening crosses every regime.
PERCENT_HOURS = np.arange(0, 49)
PERCENT = np.interp(PERCENT_HOURS, [0, 6, 14, 19, 20, 48], [100.0, 100.0, 25.0, 25.0, 75.0, 75.0])


def tailwater(stage: float) -> str:
    return (
        f"     Main Tailwater Condition: Fixed Stage\n     Main Fixed Tailwater Stage: {stage:g}\n"
        "     Auxiliary Tailwater Condition: None\n"
    )


def sluice(control: str) -> str:
    return (
        "\n     Spillway Gate: Sluice\n     Number Gates: 2\n     Gate Width: 10\n     Gate Coefficient: 0.6\n"
        f"     Orifice Coefficient: 0.8\n{control}     End Gate:\n"
    )


def radial(control: str) -> str:
    return (
        "\n     Spillway Gate: Radial\n     Number Gates: 2\n     Gate Width: 10\n     Gate Coefficient: 0.7\n"
        "     Orifice Coefficient: 0.8\n     Trunnion Height: 3\n     Trunnion Exponent: 0.16\n"
        f"     Opening Exponent: 0.72\n     Head Exponent: 0.62\n{control}     End Gate:\n"
    )


FIXED = "     Gate Control: Fixed Opening\n     Gate Opening: 1.5\n     End Gate Control:\n"
TIME_SERIES = (
    f"     Gate Control: Percent Time Series\n     Maximum Gate Opening: {MAX_OPENING:g}\n"
    f"     Percent Gage Name: {PERCENT_GAGE}\n     End Gate Control:\n"
)
SPILLWAY = w62.broad_open(20)
END = w62.END_SPILLWAY

NEW_CASES = {
    # Percent Time Series: the opening is the maximum times the gage's percent.
    "gate_percent_sluice": (w59.NO_TAILWATER, SPILLWAY + sluice(TIME_SERIES) + END, w59.ZERO_EVAPORATION),
    "gate_percent_radial": (w59.NO_TAILWATER, SPILLWAY + radial(TIME_SERIES) + END, w59.ZERO_EVAPORATION),
    # Drowned gates: W62's fixed 1.5 m opening (lip at 109.5 m) under a fixed tailwater over the crest.
    "gate_sluice_tw_low": (tailwater(108.6), SPILLWAY + sluice(FIXED) + END, w59.ZERO_EVAPORATION),
    "gate_sluice_tw_lip": (tailwater(109.6), SPILLWAY + sluice(FIXED) + END, w59.ZERO_EVAPORATION),
    "gate_sluice_tw_high": (tailwater(110.4), SPILLWAY + sluice(FIXED) + END, w59.ZERO_EVAPORATION),
    "gate_radial_tw_low": (tailwater(108.6), SPILLWAY + radial(FIXED) + END, w59.ZERO_EVAPORATION),
    "gate_radial_tw_lip": (tailwater(109.6), SPILLWAY + radial(FIXED) + END, w59.ZERO_EVAPORATION),
}

def sluice_as(gate_c: float, orifice_c: float, opening: float) -> str:
    """A sluice group with its own coefficients and a fixed opening: the drowned law's coefficient told apart."""
    return (
        "\n     Spillway Gate: Sluice\n     Number Gates: 2\n     Gate Width: 10\n"
        f"     Gate Coefficient: {gate_c:g}\n     Orifice Coefficient: {orifice_c:g}\n"
        f"     Gate Control: Fixed Opening\n     Gate Opening: {opening:g}\n     End Gate Control:\n     End Gate:\n"
    )


def radial_as(gate_c: float, orifice_c: float, opening: float) -> str:
    return (
        "\n     Spillway Gate: Radial\n     Number Gates: 2\n     Gate Width: 10\n"
        f"     Gate Coefficient: {gate_c:g}\n     Orifice Coefficient: {orifice_c:g}\n     Trunnion Height: 3\n"
        "     Trunnion Exponent: 0.16\n     Opening Exponent: 0.72\n     Head Exponent: 0.62\n"
        f"     Gate Control: Fixed Opening\n     Gate Opening: {opening:g}\n     End Gate Control:\n     End Gate:\n"
    )


ROUND_TWO = {
    # Small openings under a low tailwater, so pool over tailwater passes 1.25 openings for many steps.
    "gate_sluice_tw_a": (tailwater(108.6), SPILLWAY + sluice_as(0.6, 0.8, 0.8) + END, w59.ZERO_EVAPORATION),
    "gate_sluice_tw_b": (tailwater(108.6), SPILLWAY + sluice_as(0.5, 0.9, 0.8) + END, w59.ZERO_EVAPORATION),
    "gate_sluice_tw_c": (tailwater(109.2), SPILLWAY + sluice_as(0.5, 0.7, 1.0) + END, w59.ZERO_EVAPORATION),
    "gate_radial_tw_a": (tailwater(108.6), SPILLWAY + radial_as(0.7, 0.8, 0.8) + END, w59.ZERO_EVAPORATION),
    "gate_radial_tw_b": (tailwater(108.6), SPILLWAY + radial_as(0.6, 0.9, 0.8) + END, w59.ZERO_EVAPORATION),
}
NEW_CASES.update(ROUND_TWO)

ANNUAL = "W76 Annual"
ANNUAL_PATH = "//W76 ANNUAL/PERCENT//IR-YEAR/W76/"
# The same shape as the hourly gage, on dates of the year 2000 (an annual pattern's year in hms.jar, class O).
ANNUAL_TIMES = [datetime(2000, 1, 1), datetime(2000, 1, 31, 18), datetime(2000, 2, 1, 2), datetime(2000, 2, 1, 7),
                datetime(2000, 2, 1, 8), datetime(2000, 12, 31)]
ANNUAL_PERCENT = [100.0, 100.0, 25.0, 25.0, 75.0, 75.0]
PATTERN_CONTROL = (
    f"     Gate Control: Percent Annual Pattern\n     Maximum Gate Opening: {MAX_OPENING:g}\n"
    f"     Percent Pattern Name: {ANNUAL}\n     End Gate Control:\n"
)
ANNUAL_CASES = {
    "gate_annual_sluice": (w59.NO_TAILWATER, SPILLWAY + sluice(PATTERN_CONTROL) + END, w59.ZERO_EVAPORATION),
}
NEW_CASES.update(ANNUAL_CASES)
w59.CASES.update(NEW_CASES)


def add_annual_pattern(folder: Path, data_type: str) -> None:
    """A guess at a percent pattern in the paired-data file (``Pattern:``, keys of hms.jar's class O) and its record."""
    block = (
        f"Pattern: {ANNUAL}\n     Description: \n{w59.STAMP}     Data Type: {data_type}\n     Units: %\n"
        f"     Use External DSS File: NO\n     DSS File: {w59.STEM}.dss\n     Pathname: {ANNUAL_PATH}\nEnd:\n\n"
    )
    pdata = folder / f"{w59.STEM}.pdata"
    pdata.write_text(pdata.read_text(encoding="utf-8") + block, encoding="utf-8")
    dss = hecdss.HecDss(str(folder / f"{w59.STEM}.dss"))
    try:
        dss.put(hecdss.IrregularTimeSeries.create(
            values=ANNUAL_PERCENT, times=ANNUAL_TIMES, units="%", data_type="INST-VAL", path=ANNUAL_PATH,
        ))
    finally:
        dss.close()


def add_percent_gage(folder: Path) -> None:
    """The percent gage beside W59's inflow gage, its record in the project DSS."""
    start, end = w59.START, w59.END
    block = (
        f"\nGage: {PERCENT_GAGE}\n{w59.STAMP}     Gage Type: Percent\n     Units: %\n     Data Type: INST-VAL\n"
        "     Data Source Type: External DSS\n     Variant: Variant-1\n"
        "       Last Variant Modified Date: 14 November 2026\n       Last Variant Modified Time: 12:00:00\n"
        f"       Default Variant: Yes\n       DSS File Name: {w59.STEM}.dss\n       DSS Pathname: {PERCENT_PATH}\n"
        f"       Start Time: {start[0]}, {start[1]}\n       End Time: {end[0]}, {end[1]}\n     End Variant: Variant-1\nEnd:\n"
    )
    gage = folder / f"{w59.STEM}.gage"
    gage.write_text(gage.read_text(encoding="utf-8") + block, encoding="utf-8")
    dss = hecdss.HecDss(str(folder / f"{w59.STEM}.dss"))
    try:
        first = datetime(2000, 1, 31, 12, 0)
        times = [first + timedelta(hours=int(h)) for h in PERCENT_HOURS]
        dss.put(hecdss.RegularTimeSeries.create(
            values=PERCENT, times=times, units="%", data_type="INST-VAL", interval="1HOUR", path=PERCENT_PATH,
        ))
    finally:
        dss.close()


def main() -> None:
    folder = HERE / "_work" / sys.argv[1]
    cases = list(NEW_CASES) if sys.argv[2:] == ["every"] else sys.argv[2:]
    w59.write_project(folder, cases)
    add_percent_gage(folder)
    if any(case in ANNUAL_CASES for case in cases):
        # the pattern's Data Type is a guess; W76_PATTERN_TYPE tries another
        add_annual_pattern(folder, os.environ.get("W76_PATTERN_TYPE", "Percent Pattern"))
    print(w62.jython(folder, cases))


if __name__ == "__main__":
    main()
