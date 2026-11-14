"""W67's test cases on W59's metric HEC-HMS 4.12 project: culverts and drowned weirs.

Same project, inflow (400 m3/s at 6 h), pool (100 to 125 m) and 48 h window as W59 (``W59 .../scripts/hms_project.py``),
which this module extends with new cases; nothing of W59's or W62's is changed. The culvert block follows HMS's own
``river_bend`` sample; the circular keys are guesses from ``hms.jar`` (``Diameter``). HMS re-saving the basin is what
proves a key (a key HMS does not read is dropped on re-save).

Usage: ``python hms_cases.py <folder> <case> [<case> ...]`` or ``every``; writes the project to ``_work/<folder>`` and
prints the Jython script for ``run_hms.ps1`` (W62's).
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE.parent / "W59 HMS reservoir structures" / "scripts"))
sys.path.insert(0, str(HERE.parent / "W62 HMS culverts gates pumps" / "scripts"))
import hms_cases as w62  # noqa: E402
import hms_project as w59  # noqa: E402


def tailwater(stage: float) -> str:
    return (
        f"     Main Tailwater Condition: Fixed Stage\n     Main Fixed Tailwater Stage: {stage:g}\n"
        "     Auxiliary Tailwater Condition: None\n"
    )


def culvert(
    shape: str, chart: int, scale: int, control: str, size: str, barrels: int, length: float, n: float,
    inlet: float = 100.5, outlet: float = 100.0, entrance: float = 0.5, exit_: float = 1.0,
) -> str:
    return (
        "\n     Conduit: Culvert\n     Conduit Outlet: Main\n"
        f"     Culvert Shape: {shape}\n     Chart Number: {chart}\n     Scale Number: {scale}\n"
        f"     Solution Control: {control}\n{size}     Number Barrels: {barrels}\n     Culvert Length: {length:g}\n"
        f"     Entrance Loss Coefficient: {entrance:g}\n     Exit Loss Coefficient: {exit_:g}\n"
        f"     Top Manning's n: {n:g}\n     Inlet Invert Elevation: {inlet:g}\n"
        f"     Outlet Invert Elevation: {outlet:g}\n     End Conduit:\n"
    )


BOX = "     Rise: 3\n     Span: 3\n"
PIPE = "     Diameter: 2.5\n"
SHORT_BOX_IC = culvert("Box", 8, 1, "Inlet Control", BOX, 2, 40, 0.013)
LONG_BOX = {c: culvert("Box", 8, 1, c, BOX, 2, 300, 0.02, inlet=100.3) for c in
            ("Automatic", "Outlet Control", "Inlet Control")}
BOX_FORM2 = culvert("Box", 10, 2, "Inlet Control", BOX, 2, 40, 0.013)
PIPE_IC = culvert("Circular", 1, 1, "Inlet Control", PIPE, 2, 40, 0.013)
PIPE_AUTO = culvert("Circular", 2, 3, "Automatic", PIPE, 2, 250, 0.024, inlet=100.3)
LEVEL_DAM = w59.LEVEL_DAM

NEW_CASES = {
    # Drowned weirs: a tailwater over the crest, low enough that the pool passes through every submergence.
    "damtop_drowned": (tailwater(109.7), w59.RATING + LEVEL_DAM, w59.ZERO_EVAPORATION),
    "broad_drowned": (tailwater(108.3), w59.BROAD, w59.ZERO_EVAPORATION),
    "broad_drowned_high": (tailwater(109.5), w59.BROAD, w59.ZERO_EVAPORATION),
    # Culverts, with the rating spillway as relief: the pool sweeps the inlet from unsubmerged to submerged.
    "culvert_box_ic": (w59.NO_TAILWATER, w59.RATING + SHORT_BOX_IC, w59.ZERO_EVAPORATION),
    "culvert_box_form2": (w59.NO_TAILWATER, w59.RATING + BOX_FORM2, w59.ZERO_EVAPORATION),
    "culvert_box_auto": (w59.NO_TAILWATER, w59.RATING + LONG_BOX["Automatic"], w59.ZERO_EVAPORATION),
    "culvert_box_oc": (w59.NO_TAILWATER, w59.RATING + LONG_BOX["Outlet Control"], w59.ZERO_EVAPORATION),
    "culvert_box_tw_full": (tailwater(104.0), w59.RATING + LONG_BOX["Automatic"], w59.ZERO_EVAPORATION),
    "culvert_box_tw_part": (tailwater(101.5), w59.RATING + LONG_BOX["Automatic"], w59.ZERO_EVAPORATION),
    "culvert_pipe_ic": (w59.NO_TAILWATER, w59.RATING + PIPE_IC, w59.ZERO_EVAPORATION),
    "culvert_pipe_auto": (tailwater(101.5), w59.RATING + PIPE_AUTO, w59.ZERO_EVAPORATION),
}
# Every other chart and scale of the table, inlet control, on the short barrels: each coefficient set measured.
CHART_CASES = {
    f"culvert_chart_{chart}_{scale}": (
        w59.NO_TAILWATER,
        w59.RATING + culvert(shape, chart, scale, "Inlet Control", size, 2, 40, 0.013),
        w59.ZERO_EVAPORATION,
    )
    for shape, size, charts in (("Circular", PIPE, ((1, 2), (1, 3), (2, 1), (2, 2), (3, 1), (3, 2))),
                                ("Box", BOX, ((8, 2), (8, 3), (9, 1), (9, 2), (10, 1), (10, 3))))
    for chart, scale in charts
}
NEW_CASES.update(CHART_CASES)
w59.CASES.update(NEW_CASES)


def main() -> None:
    folder = HERE / "_work" / sys.argv[1]
    cases = list(NEW_CASES) if sys.argv[2:] == ["every"] else sys.argv[2:]
    w59.write_project(folder, cases)
    script = w62.jython(folder, cases)
    print(script)


if __name__ == "__main__":
    main()
