"""HMS's result series of every W59 case to one CSV per case, plus the basin files and the tables as JSON.

The CSVs are the oracle of ``tests/hydrology/test_hms_structures.py``: the test needs neither HMS nor DSS. Columns:
inflow (FLOW-COMBINE), outflow (FLOW), storage_m3 (STORAGE x 1000), elevation_m, area_m2, tailwater_m, evaporation
(m3 over each step, 0 at the first time), and the flow of each structure HMS reports (``-OUTLET-1``, ``-SPILL-1``, ``-DAMTOP-1``, ``-DAM SEEPAGE``).
"""

from __future__ import annotations

import csv
import json
import shutil
import sys
from pathlib import Path

import numpy as np

from wadi2d.hms import open_dss
from wadi2d.hms.dss import DssLookupError

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from hms_project import CASES, TABLES, basin_name, file_stem  # noqa: E402

TARGET = HERE.parents[0] / "tests" / "data" / "hms_structures"
THOUSAND = 1000.0
SERIES = {
    "inflow": ("Reservoir", "FLOW-COMBINE", 1.0),
    "outflow": ("Reservoir", "FLOW", 1.0),
    "storage_m3": ("Reservoir", "STORAGE", THOUSAND),
    "elevation_m": ("Reservoir", "ELEVATION", 1.0),
    "area_m2": ("Reservoir", "AREA", THOUSAND),
    "tailwater_m": ("Reservoir", "STAGE-TAILWATER", 1.0),
    "evaporation_m3": ("Reservoir", "EVAPORATION", THOUSAND),
    "outlet_1": ("Reservoir-OUTLET-1", "FLOW", 1.0),
    "spill_1": ("Reservoir-SPILL-1", "FLOW", 1.0),
    "spill_2": ("Reservoir-SPILL-2", "FLOW", 1.0),
    "damtop_1": ("Reservoir-DAMTOP-1", "FLOW", 1.0),
    "seepage": ("Reservoir-DAM SEEPAGE", "FLOW", 1.0),
}


def export(case: str, folder: Path) -> None:
    columns: dict[str, np.ndarray] = {}
    units: dict[str, str] = {}
    with open_dss(folder / f"{file_stem(case)}.dss") as dss:
        for column, (b, c, scale) in SERIES.items():
            try:
                series = dss.read_timeseries(b, c, f"RUN:{basin_name(case)}")
            except DssLookupError:
                continue
            values = series.values * scale
            # a per-period volume series starts one step late: its first period ends at the second time
            late = column != "inflow" and len(values) == len(columns["inflow"]) - 1
            columns[column] = np.concatenate(([0.0], values)) if late else values
            units[column] = f"{series.units} {len(series.values)} {series.times[0]}"
    print(case, units)
    with (TARGET / f"{case}.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for row in zip(*columns.values(), strict=True):
            writer.writerow([repr(float(value)) for value in row])
    shutil.copy2(folder / f"{file_stem(case)}.basin", TARGET / f"{case}.basin")
    print(case, len(next(iter(columns.values()))), "steps;", units)


def main() -> None:
    folder = HERE / "_work" / "hms"
    TARGET.mkdir(parents=True, exist_ok=True)
    for case in CASES:
        export(case, folder)
    tables = {name: {"type": kind, "x": list(map(float, x)), "y": list(map(float, y)), "x_units": xu, "y_units": yu}
              for name, (kind, xu, yu, _c, x, y) in TABLES.items()}
    (TARGET / "tables.json").write_text(json.dumps(tables, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
