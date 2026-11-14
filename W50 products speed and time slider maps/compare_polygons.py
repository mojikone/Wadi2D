"""The hazard polygons of two remakes, band by band (W50, 2026-11-13): how far the boxed contouring moved them.

    python compare_polygons.py TAG_A TAG_B

Reads `remake/runs/<tag>/pixels/map_layers.gpkg`; every (class, block) band must exist in both. Prints and writes
`remake/compare_polygons_<a>_<b>.json`: bands identical to the byte, the largest Hausdorff distance and area change of
the rest, and the drawn areas per class of both.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import shapely

HERE = Path(__file__).resolve().parent / "remake"
QUERY = 'SELECT "class", block, geom FROM hazard_classes ORDER BY block, "class"'
HEADER = 40
"""Bytes of a GeoPackage geometry header with an xy envelope, before the WKB."""


def bands(tag: str) -> dict:
    with sqlite3.connect(HERE / "runs" / tag / "pixels" / "map_layers.gpkg") as db:
        return {(k, b): g for k, b, g in db.execute(QUERY)}


def main() -> int:
    a_tag, b_tag = sys.argv[1], sys.argv[2]
    a, b = bands(a_tag), bands(b_tag)
    assert a.keys() == b.keys(), sorted(set(a) ^ set(b))
    same, moved, worst_h, worst_area = 0, 0, 0.0, 0.0
    for key in a:
        if a[key] == b[key]:
            same += 1
            continue
        moved += 1
        ga, gb = shapely.from_wkb(a[key][HEADER:]), shapely.from_wkb(b[key][HEADER:])
        worst_h = max(worst_h, float(shapely.hausdorff_distance(ga, gb)))
        worst_area = max(worst_area, abs(float(ga.area - gb.area)))
    stats = {tag: json.loads((HERE / "runs" / tag / "pixels" / "pixels.json").read_text("utf-8"))["smooth"] for tag in (a_tag, b_tag)}
    out = {"bands": len(a), "identical": same, "moved": moved, "worst_hausdorff_m": worst_h, "worst_area_m2": worst_area,
           "drawn_km2": {tag: s["drawn_km2"] for tag, s in stats.items()}}  # fmt: skip
    (HERE / f"compare_polygons_{a_tag}_{b_tag}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
