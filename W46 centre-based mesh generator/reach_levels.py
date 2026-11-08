"""The steady water level along the main stem's thalweg in the reach runs (W46, 2026-11-08): each run's final level
at thalweg stations every 200 m, lattice cells from maps/max_level.tif, strip cells from maps/strip_mesh.gpkg, and
the difference of every run against the 2 m squares. Under a steady inflow the maximum level is the final level.

    .venv\\Scripts\\python "W46 centre-based mesh generator\\reach_levels.py" [reach_long_steady] [sq2 sq5 sq10 ce10 sq20 ce20 ...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import shapely

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from wadi2d.strips.banks import read_thalwegs  # noqa: E402
from wadi2d.strips.centres import chain_streams  # noqa: E402

W26 = ROOT / "W26 suggested breaklines" / "suggested" / "faydh" / "suggested_breaklines.gpkg"
FROM_M, TO_M, STEP_M = 4_500.0, 19_500.0, 200.0


def stations() -> np.ndarray:
    main = chain_streams(read_thalwegs(W26))[0]["line"]
    s = np.arange(FROM_M, TO_M + 1.0, STEP_M)
    return np.asarray([main.interpolate(v).coords[0] for v in s])[:, :2], s


def levels(folder: Path, pts: np.ndarray) -> np.ndarray:
    """The final level at each point: the strip cell holding it, else the lattice cell."""
    import fiona
    import rasterio

    out = np.full(pts.shape[0], np.nan)
    strip = folder / "maps" / "strip_mesh.gpkg"
    if strip.is_file():
        with fiona.open(strip, layer="strip_cells") as src:
            geoms, vals = [], []
            for f in src:
                geoms.append(shapely.geometry.shape(f["geometry"]))
                vals.append(f["properties"]["max_level_m"])
        tree = shapely.STRtree(geoms)
        for k, (x, y) in enumerate(pts):
            hit = tree.query(shapely.Point(x, y), predicate="within")
            if hit.size:
                out[k] = vals[int(hit[0])]
    with rasterio.open(folder / "maps" / "max_level.tif") as src:
        sampled = np.array([v[0] for v in src.sample(pts.tolist())], np.float64)
        sampled[sampled == src.nodata] = np.nan
    missing = np.isnan(out)
    out[missing] = sampled[missing]
    return out


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent / "race_faydh" / (sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith(("sq", "ce")) else "reach_long_steady")
    names = [a for a in sys.argv[1:] if a.startswith(("sq", "ce"))] or ["sq2", "sq5", "sq10", "ce10", "sq20", "ce20"]
    pts, s = stations()
    table = {n: levels(folder / n, pts) for n in names if (folder / n / "maps" / "max_level.tif").is_file()}
    ref = table.get("sq2")
    print(f"steady level along the thalweg, {folder.name}: mean and spread of the difference against the 2 m squares, m, over {pts.shape[0]} stations")
    out = {}
    for n, z in table.items():
        if ref is None or n == "sq2":
            print(f"  {n:5s} level {np.nanmean(z):8.3f} m mean")
            continue
        d = z - ref
        ok = np.isfinite(d)
        out[n] = {"mean_m": float(np.nanmean(d)), "median_m": float(np.nanmedian(d)), "p10_m": float(np.nanpercentile(d, 10)), "p90_m": float(np.nanpercentile(d, 90)), "stations": int(ok.sum())}
        print(f"  {n:5s} against sq2: mean {out[n]['mean_m']:+.3f} m, median {out[n]['median_m']:+.3f}, 10th to 90th {out[n]['p10_m']:+.3f} to {out[n]['p90_m']:+.3f}, on {ok.sum()} stations")
    if ref is not None:
        print("\n  km   " + "".join(f"{n:>9s}" for n in table))
        for k in range(0, pts.shape[0], 5):
            print(f"  {s[k] / 1000:4.1f} " + "".join(f"{table[n][k]:9.2f}" for n in table))
    (folder / "levels.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
