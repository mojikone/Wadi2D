"""HMS's series of W62's cases to ``tests/data/hms_structures`` with W59's exporter, and the new tables added.

The basin file kept is the one HMS itself re-saved (``<stem>_saved.basin``), so every key in it is one HMS reads.
Usage: ``python export_cases.py <folder under _work> [<case> ...]``; with no case, every W62 case.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "W59 HMS reservoir structures" / "scripts"))
import export_hms
import hms_cases
import hms_project as w59

export_hms.SERIES["pump_1"] = ("Reservoir-PUMP-1", "FLOW", 1.0)
export_hms.SERIES["pump_2"] = ("Reservoir-PUMP-2", "FLOW", 1.0)
export_hms.SERIES["outlet_2"] = ("Reservoir-OUTLET-2", "FLOW", 1.0)


def main() -> None:
    folder = hms_cases.HERE / "_work" / sys.argv[1]
    cases = sys.argv[2:] or list(hms_cases.NEW_CASES)
    for case in cases:
        export_hms.export(case, folder)
        shutil.copy2(folder / f"{w59.file_stem(case)}_saved.basin", export_hms.TARGET / f"{case}.basin")
    path = export_hms.TARGET / "tables.json"
    tables = json.loads(path.read_text(encoding="utf-8"))
    for name, (kind, xu, yu, _c, x, y) in w59.TABLES.items():
        tables[name] = {"type": kind, "x": list(map(float, x)), "y": list(map(float, y)), "x_units": xu, "y_units": yu}
    path.write_text(json.dumps(tables, indent=1), encoding="utf-8")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
