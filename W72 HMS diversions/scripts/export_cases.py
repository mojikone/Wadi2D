"""HMS's series of every W72 case to ``tests/data/hms_diversions``: the oracle of ``tests/hydrology/test_hms_diversions.py``.

Columns: inflow (the diversion's FLOW-COMBINE), passed (its FLOW), diverted (its FLOW-DIVERSION) and received (the
FLOW of the Sink it diverts to; absent when Not Connected). The basin file kept is the one HMS re-saved, so every key
in it is one HMS reads; the tables go to ``tables.json``.
Usage: ``python export_cases.py <folder under _work>``.
"""

from __future__ import annotations

import csv
import json
import shutil
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import w72_cases  # noqa: E402
from w72_cases import CASES, HERE, w59  # noqa: E402

from wadi2d.hms import open_dss  # noqa: E402
from wadi2d.hms.dss import DssLookupError  # noqa: E402

TARGET = HERE.parent / "tests" / "data" / "hms_diversions"
SERIES = {
    "inflow": ("Diversion", "FLOW-COMBINE"),
    "passed": ("Diversion", "FLOW"),
    "diverted": ("Diversion", "FLOW-DIVERSION"),
    "received": ("Diverted", "FLOW"),
}


def export(case: str, folder: Path) -> None:
    columns: dict[str, np.ndarray] = {}
    with open_dss(folder / f"{w59.file_stem(case)}.dss") as dss:
        for column, (b, c) in SERIES.items():
            try:
                columns[column] = dss.read_timeseries(b, c, f"RUN:{w59.basin_name(case)}").values
            except DssLookupError:
                continue
    with (TARGET / f"{case}.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for row in zip(*columns.values(), strict=True):
            writer.writerow([repr(float(value)) for value in row])
    shutil.copy2(folder / f"{w59.file_stem(case)}_saved.basin", TARGET / f"{case}.basin")
    print(case, {name: round(float(values.max()), 4) for name, values in columns.items()})


def main() -> None:
    folder = HERE / "_work" / sys.argv[1]
    TARGET.mkdir(parents=True, exist_ok=True)
    for case in CASES:
        export(case, folder)
    tables = {
        name: {"type": kind, "x": list(map(float, x)), "y": list(map(float, y)), "x_units": xu, "y_units": yu}
        for name, (kind, xu, yu, _c, x, y) in w59.TABLES.items() if name.startswith("W72")
    }
    tables["specified_m3s"] = list(map(float, w72_cases.specified()))
    (TARGET / "tables.json").write_text(json.dumps(tables, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
