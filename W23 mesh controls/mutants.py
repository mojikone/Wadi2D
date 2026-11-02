"""Faults put into the new code one at a time, in a scratch copy: which do the tests catch?

usage: python mutants.py TREE_COPY     TREE_COPY holds wadi2d, plugin, tests and pyproject.toml, and is edited freely.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TESTS = [
    "tests/plugin/test_mesh_rows.py", "tests/plugin/test_job_builder.py", "tests/plugin/test_contract.py",
    "tests/plugin/test_protocol.py", "tests/engine/test_mesh_lines.py",
]  # fmt: skip
REFINE = "wadi2d/mesh/refine.py"
BUILD = "wadi2d/mesh/build.py"
ROWS = "plugin/wadi2d_qgis/mesh_rows.py"
JOBS = "plugin/wadi2d_qgis/job_builder.py"
MUTANTS = [
    ("rungs not cumulative", REFINE, "reach += item.rows", "reach = item.rows"),
    ("a rung takes no doubling", REFINE, "reach += item.rows * lat.dx * (1 << level)", "reach += item.rows * lat.dx"),
    ("far rung left out", REFINE, "rung(item.far_dx, lat.dx, top) + 1)", "rung(item.far_dx, lat.dx, top))"),
    ("band only where its centre falls", REFINE, 'transform=lat.transform(), all_touched=True, dtype="uint8"\n            ).astype(bool)\n            out[hit] = np.minimum(out[hit], level)\n    return out\n\n\n__all__', 'transform=lat.transform(), all_touched=False, dtype="uint8"\n            ).astype(bool)\n            out[hit] = np.minimum(out[hit], level)\n    return out\n\n\n__all__'),
    ("later line coarsens an earlier", REFINE, "out[hit] = np.minimum(out[hit], level)\n    return out\n\n\n__all__", "out[hit] = level\n    return out\n\n\n__all__"),
    ("rung rounds to nearest", REFINE, "np.floor(np.log2(size / dx) + 1e-9)", "np.round(np.log2(size / dx))"),
    ("rung has no noise guard", REFINE, "np.floor(np.log2(size / dx) + 1e-9)", "np.floor(np.log2(size / dx) - 1e-9)"),
    ("rung not held at the top", REFINE, "np.clip(np.floor(np.log2(size / dx) + 1e-9), 0, top)", "np.maximum(np.floor(np.log2(size / dx) + 1e-9), 0)"),
    ("lines left out of the mesh", BUILD, "level = np.minimum(level, band_levels(m.lines, lat, top))\n", "pass\n"),
    ("far change not reported", BUILD, '"rounded": near != item.near_dx or far != item.far_dx', '"rounded": near != item.near_dx'),
    ("reach wrong", BUILD, '"reach": item.rows * (2.0 * far - near)', '"reach": item.rows * (2.0 * far + near)'),
    ("a missed line passes", BUILD, "    if missed:\n        raise ValueError", "    if False:\n        raise ValueError"),
    ("the report drops the lines", BUILD, "int(grid.interfaces.shape[0]), lines or [],", "int(grid.interfaces.shape[0]), [],"),
    ("no number for an unnamed line", BUILD, 'item.name or f"Line {number}"', "item.name"),
    ("a run keeps quiet", "wadi2d/run.py", "for note in rounding_notes(cfg):\n            progress.emit", "for note in []:\n            progress.emit"),
    ("the preview gets no lines", "wadi2d/engine/cli.py", "cfg.grid.dx, line_sizes(cfg))", "cfg.grid.dx)"),
    ("table rounds to nearest", ROWS, "level = min(max(math.floor(math.log2(asked / finest) + LADDER_NOISE), 0), top)", "level = min(max(round(math.log2(asked / finest)), 0), top)"),
    ("table not held at the top", ROWS, "0), top)\n    return finest", "0), 99)\n    return finest"),
    ("table not held at the bottom", ROWS, "level = min(max(math.floor(math.log2(asked / finest) + LADDER_NOISE), 0), top)", "level = min(math.floor(math.log2(asked / finest) + LADDER_NOISE), top)"),
    ("a set near still follows", ROWS, "if not row.near_pinned:", "if True:"),
    ("a set far still follows", ROWS, "if not row.far_pinned:", "if True:"),
    ("merged rows forget", ROWS, "known = {row.fid: row for row in old}", "known = {}"),
    ("near above far passes", ROWS, 'if near > far else ""', 'if False else ""'),
    ("the note is only the near", ROWS, 'for word, asked in (("near", near), ("far", far))', 'for word, asked in (("near", near),)'),
    ("the job gets the rounded size", ROWS, '"near_dx": row.near,', '"near_dx": 10.0,'),
    ("no note before a run", JOBS, "return found + _line_notes(values)", "return found"),
    ("job always has lines", JOBS, '    if mesh.get("lines"):\n        out["lines"] =', '    if True:\n        out["lines"] ='),
    ("lines not on file", JOBS, 'if values["mesh"].get("lines"):\n            write_geojson', 'if False:\n            write_geojson'),
    ("note ladder ignores the snap", JOBS, 'finest = snap_dx(values.get("dx", 0.0), values.get("pixel", 0.0))\n    found = []\n    for line in mesh["lines"]', 'finest = values.get("dx", 0.0)\n    found = []\n    for line in mesh["lines"]'),
    ("preview text drops the lines", "plugin/wadi2d_qgis/protocol.py", 'return " ".join([text, *lines])', "return text"),
]  # fmt: skip


def main() -> None:
    root = Path(sys.argv[1])
    survived = []
    for name, file, old, new in MUTANTS:
        path = root / file
        source = path.read_text(encoding="utf-8")
        if old not in source:
            print(f"NOT APPLIED  {name}", flush=True)
            survived.append(f"{name} (not applied)")
            continue
        path.write_text(source.replace(old, new, 1), encoding="utf-8")
        run = subprocess.run(
            [sys.executable, "-m", "pytest", *TESTS, "-x", "-q", "--no-header", "-p", "no:cacheprovider", "-W", "ignore"],
            cwd=root, capture_output=True, text=True,
        )  # fmt: skip
        path.write_text(source, encoding="utf-8")
        caught = run.returncode != 0
        print(f"{'caught  ' if caught else 'SURVIVED'}  {name}", flush=True)
        if not caught:
            survived.append(name)
    print(f"{len(MUTANTS) - len(survived)} of {len(MUTANTS)} caught; survived: {survived}")


if __name__ == "__main__":
    main()
