"""W78: the pre-run check on Faydh 01 (W56's job) and Bidah (W61's job), and what the ground shows at each place found.

Run from the repository root: ``.venv\\Scripts\\python "W78 domain edge valley check\\probe_crossings.py"``.
Writes ``logs/crossings.json``.
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
import rasterio

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))

from wadi2d.config.schema import RunConfig  # noqa: E402
from wadi2d.edge_valleys import crossing_notes, stream_crossings  # noqa: E402

VALIDATION = REPO / "W1 research and design note" / "validation" / "block2_full"
BLOCK_DEM = r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\Terrain\GGC_2_MERGE_HDSM_5.tif"
KNOWN = {"faydh": (424370.0, 2726845.0), "bidah": (439416.0, 2728690.0)}
"""Where the runs left deep water against the edge (W56, W75)."""


def faydh() -> RunConfig:
    job = json.loads(
        (REPO / "W56 aligned mesh at 5 m on Faydh" / "runs" / "sq5.json").read_text(encoding="utf-8")
    )
    job["grid"].pop("cache_dir", None)
    return RunConfig.model_validate(job)


def bidah(flow_line: bool) -> RunConfig:
    """W61's job: Bidah 03's domain, outlet 1 free, the middle half of outlet 2 a flow line (or free, for the clean case)."""
    dam = json.loads((VALIDATION / "jobs" / "dam_Bidah03_100yr_20.json").read_text(encoding="utf-8"))
    (a, b) = [o["coordinates"] for o in dam["boundaries"]]
    (x0, y0), (x1, y1) = b[0], b[-1]
    middle = [(x0 + 0.25 * (x1 - x0), y0 + 0.25 * (y1 - y0)), (x0 + 0.75 * (x1 - x0), y0 + 0.75 * (y1 - y0))]
    flow = {
        "kind": "flow",
        "coordinates": middle,
        "flow": {"times_s": [0, 600, 1800, 2400], "flows": [0, 20, 20, 0]},
    }
    lines = [{"kind": "free", "coordinates": a}, flow if flow_line else {"kind": "free", "coordinates": b}]
    return RunConfig.model_validate(
        {
            "terrain": {"dem": BLOCK_DEM},
            "grid": {"dx": 20.0, "domain": str(VALIDATION / "domain_Bidah03.geojson")},
            "boundaries": lines,
            "run": {"duration_s": 3600.0},
        }
    )


def ground_profile(
    dem: str, x: float, y: float, along: tuple[float, float], half: float = 300.0, step: float = 25.0
):
    """Ground along the edge through (x, y), every ``step`` m: the valley the outline cuts, seen as a section."""
    ux, uy = along
    d = np.arange(-half, half + step, step)
    with rasterio.open(dem) as src:
        z = [float(v[0]) for v in src.sample([(x + s * ux, y + s * uy) for s in d])]
    return [(float(s), round(v, 2)) for s, v in zip(d, z, strict=True)]


def main():
    with rasterio.open(BLOCK_DEM) as src:
        crs = src.crs.to_wkt()
    record = {}
    cases = {
        "faydh": (faydh(), (1.0, 0.0)),  # the south edge runs east-west at the known spot
        "bidah_flow_line": (bidah(True), (1.0, 0.0)),
        "bidah_clean": (bidah(False), (1.0, 0.0)),
    }
    for name, (cfg, along) in cases.items():
        t = time.monotonic()
        found = stream_crossings(cfg, crs)
        took = time.monotonic() - t
        known = KNOWN["faydh" if name == "faydh" else "bidah"]
        rows = []
        for c in found:
            rows.append(
                {
                    "kind": c.kind, "x": round(c.x), "y": round(c.y), "area_km2": round(c.area_km2, 3),
                    "no_ground": c.no_ground, "from_known_m": round(float(np.hypot(c.x - known[0], c.y - known[1]))),
                }
            )  # fmt: skip
        nearest = min(found, key=lambda c: np.hypot(c.x - known[0], c.y - known[1]), default=None)
        record[name] = {
            "seconds": round(took, 1),
            "found": rows,
            "warnings": crossing_notes(found, cfg.outputs.edge_check),
            "ground_at_nearest": None
            if nearest is None
            else ground_profile(cfg.terrain.dem, nearest.x, nearest.y, along),
        }
        print(name, f"{took:.1f} s", json.dumps(rows, indent=1))
    (HERE / "logs").mkdir(exist_ok=True)
    (HERE / "logs" / "crossings.json").write_text(json.dumps(record, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
