"""HMS's series of every W89 case to ``tests/data/hms_muskingum``: the oracle of ``tests/hydrology/test_hms_muskingum.py``.

Columns: inflow (the reach's FLOW-COMBINE) and outflow (its FLOW). The basin file kept is the one HMS re-saved, so
every key in it is one HMS reads; ``cases.json`` holds each case's K, X, subreaches and HMS's own warnings.
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
from musk_cases import CASES, HERE, w59

from wadi2d.hms import open_dss

TARGET = HERE.parent / "tests" / "data" / "hms_muskingum"
SERIES = {"inflow": ("Reach", "FLOW-COMBINE"), "outflow": ("Reach", "FLOW")}


def export(case: str, folder: Path) -> dict:
    columns: dict[str, np.ndarray] = {}
    with open_dss(folder / f"{w59.file_stem(case)}.dss") as dss:
        for column, (b, c) in SERIES.items():
            columns[column] = dss.read_timeseries(b, c, f"RUN:{w59.basin_name(case)}").values
    with (TARGET / f"{case}.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for row in zip(*columns.values(), strict=True):
            writer.writerow([repr(float(value)) for value in row])
    shutil.copy2(folder / f"{w59.file_stem(case)}_saved.basin", TARGET / f"{case}.basin")
    log = (folder / f"{w59.file_stem(case)}.log").read_text(encoding="utf-8", errors="replace")
    warnings = [line.strip() for line in log.splitlines() if line.startswith(("WARNING", "ERROR"))]
    k, x, steps = CASES[case]
    print(case, {name: round(float(values.max()), 4) for name, values in columns.items()}, warnings)
    return {"k_hours": k, "x": x, "subreaches": steps, "hms_messages": warnings}


def main() -> None:
    folder = HERE / "_work" / sys.argv[1]
    TARGET.mkdir(parents=True, exist_ok=True)
    cases = {case: export(case, folder) for case in CASES}
    (TARGET / "cases.json").write_text(json.dumps(cases, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
