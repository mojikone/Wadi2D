"""The last SUMMARY line of every scenario log found in the first batch folder, beside the same scenario's in the
others, as a Markdown table. A batch folder holds ``<scenario>/log.txt`` or ``log_<scenario>.txt``."""

import re
import sys
from pathlib import Path

WORK = {
    "dock_cell_grid": "W17", "dock_boundary_table": "W18", "dock_profile_editor": "W22", "dock_mesh_controls": "W23",
    "dock_suggest": "W26", "dock_dam_start": "W34", "dock_flow_line": "W61", "dock_breach": "W68",
    "dock_basin_points": "W73", "dock_gauges": "W77",
}  # fmt: skip


def log_of(root: Path, name: str) -> Path:
    inside = root / name / "log.txt"
    return inside if inside.is_file() else root / f"log_{name}.txt"


def summary(root: Path, name: str) -> str:
    log = log_of(root, name)
    if not log.is_file():
        return "not run"
    lines = [line for line in log.read_text(encoding="utf-8", errors="replace").splitlines() if re.search(r"^\s*[\d.]+ SUMMARY", line)]
    if not lines:
        return "no summary"
    found = re.search(r"SUMMARY (\d+) passed, (\d+) failed\s*(.*)", lines[-1])
    passed, failed, how = found.group(1), found.group(2), found.group(3).strip()
    return f"{passed} passed, {failed} failed" + (f", stopped by an {how}" if how else "")


roots = [Path(arg) for arg in sys.argv[1:]]
for name in sorted(WORK, key=WORK.get):
    cells = [summary(root, name) for root in roots]
    print(f"| `{name}.py` ({WORK[name]}) | " + " | ".join(cells) + " |")
