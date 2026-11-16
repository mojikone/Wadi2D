"""The last SUMMARY line of every scenario log in the batches given, side by side, as a Markdown table."""

import re
import sys
from pathlib import Path

ORDER = [
    ("W17", "dock_cell_grid"), ("W18", "dock_boundary_table"), ("W19", "dock_time_slider"), ("W21", "dock_result_lines"),
    ("W22", "dock_profile_editor"), ("W23", "dock_mesh_controls"), ("W26", "dock_suggest"), ("W27", "dock_basin_bidah"),
    ("W34", "dock_dam_start"), ("W37", "dock_backend_arf"), ("W61", "dock_flow_line"), ("W68", "dock_breach"),
    ("W73", "dock_basin_points"), ("W75", "dock_wiring_gaps"), ("W77", "dock_gauges"),
]  # fmt: skip


def summary(root: Path, name: str) -> str:
    log = root / name / "log.txt"
    if not log.is_file():
        return "not run"
    lines = [line for line in log.read_text(encoding="utf-8", errors="replace").splitlines() if re.search(r"^\s*[\d.]+ SUMMARY", line)]
    if not lines:
        return "no summary"
    found = re.search(r"SUMMARY (\d+) passed, (\d+) failed\s*(.*)", lines[-1])
    passed, failed, how = found.group(1), found.group(2), found.group(3).strip()
    return f"{passed} passed, {failed} failed" + (f", stopped by an {how}" if how else "")


roots = [Path(arg) for arg in sys.argv[1:]]
for work, name in ORDER:
    cells = [summary(root, name) for root in roots]
    print(f"| `{name}.py` ({work}) | " + " | ".join(cells) + " |")
