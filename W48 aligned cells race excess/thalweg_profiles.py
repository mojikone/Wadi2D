"""Every mesh's steady water surface along Faydh's true thalweg against the 2 m squares (W48): squares at 20, 10 and
5 m and the centre mesh at 20 and 10 m, sampled at the stations of reach_character.py (the lowest pixel every 20 m),
the strips at their cells' final level, the squares at their cells' final level from the last frame; per 2 km bin.

    .venv\\Scripts\\python "W48 aligned cells race excess\\thalweg_profiles.py" [steady run folder]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import fiona
import numpy as np
import shapely

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "W47 face level carried to the face"))
import steady_surfaces as ss  # noqa: E402

OUT = Path(__file__).resolve().parent / "where_the_water_is"


def surface_at(run: Path, pts: np.ndarray) -> np.ndarray:
    level, ltr, _t = ss.final_lattice_level(run)
    col = np.clip(((pts[:, 0] - ltr.c) / ltr.a).astype(int), 0, level.shape[1] - 1)
    row = np.clip(((pts[:, 1] - ltr.f) / ltr.e).astype(int), 0, level.shape[0] - 1)
    out = level[row, col]
    strip = run / "maps" / "strip_mesh.gpkg"
    if strip.is_file():
        g, lev = [], []
        with fiona.open(strip, layer="strip_cells") as src:
            for feat in src:
                g.append(shapely.geometry.shape(feat["geometry"]))
                lev.append(feat["properties"]["level_end_m"])
        tree = shapely.STRtree(g)
        hits = tree.query(shapely.points(pts), predicate="within")
        out = out.copy()
        out[hits[0]] = np.asarray(lev)[hits[1]]
    return out


def main(folder: Path) -> dict:
    st = json.loads((OUT / "reach_character.json").read_text())["stations"]
    from wadi2d.strips.banks import read_thalwegs
    from wadi2d.strips.centres import chain_streams

    sys.path.insert(0, str(ROOT))
    main_line = chain_streams(read_thalwegs(ROOT / "W26 suggested breaklines" / "suggested" / "faydh" / "suggested_breaklines.gpkg"))[0]["line"]
    pts = []
    for r in st:
        p = np.asarray(main_line.interpolate(r["s"]).coords)[0]
        a = np.asarray(main_line.interpolate(r["s"] - 10.0).coords)[0]
        b = np.asarray(main_line.interpolate(r["s"] + 10.0).coords)[0]
        t = (b - a) / max(np.hypot(*(b - a)), 1e-9)
        pts.append(p + r["offset_m"] * np.array([-t[1], t[0]]))
    pts = np.array(pts)
    s = np.array([r["s"] for r in st])
    ref = surface_at(folder / "sq2", pts)
    runs = [n for n in ("sq20", "sq10", "sq5", "ce20", "ce10") if (folder / n / "results.h5").is_file()]
    surf = {n: surface_at(folder / n, pts) for n in runs}
    print(f"{folder.name}: the steady surface on the true thalweg against the 2 m squares, m, median per 2 km bin")
    print("bin km  " + "".join(f"{n:>9s}" for n in runs) + "   depth m")
    out = {"bins": []}
    depth = np.array([r["depth_m"] for r in st])
    for a0 in range(4000, 20000, 2000):
        m = (s >= a0) & (s < a0 + 2000)
        row = {n: float(np.nanmedian((surf[n] - ref)[m])) for n in runs}
        out["bins"].append({"from_m": a0, **row, "depth_m": float(np.median(depth[m]))})
        print(f"{a0 / 1000:3.0f}-{(a0 + 2000) / 1000:<3.0f} " + "".join(f"{row[n]:+9.3f}" for n in runs) + f"   {np.median(depth[m]):5.2f}")
    allrow = {n: float(np.nanmedian(surf[n] - ref)) for n in runs}
    print("all     " + "".join(f"{allrow[n]:+9.3f}" for n in runs))
    out["all"] = allrow
    (OUT / f"thalweg_profiles_{folder.name}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "W47 face level carried to the face" / "depth_carry" / "steady"
    main(folder)
