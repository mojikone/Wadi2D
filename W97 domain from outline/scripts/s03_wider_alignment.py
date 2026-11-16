"""W97: the completed Block 2 domain (s01, sea kept) aligned to Basin 3 at wider tolerances, through ``wadi2d domain``.

    python s03_wider_alignment.py

What is left outside every Basin 3 polygon after a 100 m alignment is mostly two plain strips on the north edge where
the D8 lines and HMS's delineation part (s01). This runs the command line with ``--align job`` at 100, 200 and 300 m
and counts W79's way. Writes ``runs/aligned_<tol>m/`` and ``wider_alignment.json``.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import shapely

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "scripts"))
from s01_block2_check import JOB, NO_RIM_DOMAIN, REPO, RIM_DOMAIN, RUNS, _geojson, strip_of, w79_count  # noqa: E402

sys.path.insert(0, str(REPO))
from wadi2d.engine.cli import main as cli  # noqa: E402
from wadi2d.forcing import load_polygons  # noqa: E402
from wadi2d.run import load_job  # noqa: E402


def main() -> None:
    cfg = load_job(JOB)
    polys = [shapely.make_valid(p).buffer(0) for p in load_polygons(cfg.hydrology).values()]
    joined = shapely.union_all([p.buffer(1.0) for p in polys]).buffer(-1.0)
    land = shapely.Polygon(max(getattr(joined, "geoms", [joined]), key=lambda g: g.area).exterior)
    old, no_rim = _geojson(RIM_DOMAIN), _geojson(NO_RIM_DOMAIN)
    strip = strip_of(old, land)
    completed = RUNS / "completed_10m" / "domain.geojson"
    out = {"completed_cells_outside": w79_count(_geojson(completed), polys, strip, old)}
    for tol in (100.0, 200.0, 300.0):
        folder = RUNS / f"aligned_{tol:g}m"
        started = time.perf_counter()
        code = cli(["domain", str(JOB), "--out", str(folder), "--outline", str(completed), "--align", "job",
                    "--tolerance-m", str(tol)])  # fmt: skip
        seconds = time.perf_counter() - started
        dom = _geojson(folder / "domain.geojson")
        out[f"{tol:g}m"] = {
            "exit": code,
            "seconds": round(seconds, 1),
            "domain_km2": round(dom.area / 1e6, 3),
            "cells_outside_every_polygon": w79_count(dom, polys, strip, old),
            "basin3_outside_domain_km2": round(land.difference(dom).area / 1e6, 3),
            "against_w79_no_rim_symdiff_km2": round(dom.symmetric_difference(no_rim).area / 1e6, 3),
        }
    (HERE / "wider_alignment.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
