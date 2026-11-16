"""Two s01 runs compared: every field's digest, then the pickled meshes field by field, arrays by bytes.

    python s02_compare.py <label a> <label b>
"""

from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np

RUNS = Path(__file__).resolve().parents[1] / "runs"


def main() -> None:
    a, b = sys.argv[1], sys.argv[2]
    da = json.loads((RUNS / f"{a}.json").read_text(encoding="utf-8"))["digest"]
    db = json.loads((RUNS / f"{b}.json").read_text(encoding="utf-8"))["digest"]
    differ = [k for k in da if da[k] != db.get(k)]
    print(f"{len(da)} fields, {len(differ)} differ: {differ}")
    with open(RUNS / f"{a}.mesh.pkl", "rb") as f:
        ma, sa = pickle.load(f)
    with open(RUNS / f"{b}.mesh.pkl", "rb") as f:
        mb, sb = pickle.load(f)
    checks = {"mask": (ma, mb), "masked_j": (sa.masked[0], sb.masked[0]), "masked_i": (sa.masked[1], sb.masked[1]),
              "corridor": (sa.corridor, sb.corridor), "row": (sa.row, sb.row)}  # fmt: skip
    for name in ("x", "y", "ring_start", "ring_node", "face_node", "face_cell"):
        checks[f"geometry.{name}"] = (getattr(sa.geometry, name), getattr(sb.geometry, name))
    for name, (x, y) in checks.items():
        same = x.dtype == y.dtype and x.shape == y.shape and x.tobytes() == y.tobytes()
        print(f"  {name:20s} {x.shape!s:16s} {'identical' if same else 'DIFFERENT'}")
    print("  breakline_edges     ", "identical" if sa.breakline_edges == sb.breakline_edges else "DIFFERENT")
    print("  polygons            ", "identical" if all(p.equals_exact(q, 0.0) and p.wkb == q.wkb for p, q in zip(sa.polygons, sb.polygons, strict=True)) else "DIFFERENT")
    print("  notes, rules        ", "identical" if (sa.notes, sa.rules) == (sb.notes, sb.rules) else "DIFFERENT")
    print("  cells", sa.geometry.ncells, "faces", sa.geometry.nfaces, "nodes", sa.geometry.x.size, "max |dx|", float(np.max(np.abs(sa.geometry.x - sb.geometry.x))) if sa.geometry.x.shape == sb.geometry.x.shape else "-")


if __name__ == "__main__":
    main()
