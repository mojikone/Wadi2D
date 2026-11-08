"""The final steady water surface of the Faydh reach runs, read cleanly (W47, 2026-11-08): the lattice's level per
cell from the last saved frame (the maxima rasters hold the arrival transient, not the steady surface), the strip's
from its cells' final level; both laid pixel by pixel over the 0.5 m DEM inside the 20 m strip's footprint and read
against the 2 m squares: the mean surface difference and the water held.

    .venv\\Scripts\\python "W47 face level carried to the face\\steady_surfaces.py" [folder under W46/race_faydh] [runs ...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import fiona
import h5py
import numpy as np
import rasterio
import shapely
from rasterio import features
from rasterio.windows import from_bounds

ROOT = Path(__file__).resolve().parents[1]
DEM = ROOT / "W11 validation round two" / "t2_faydh" / "terrain" / "faydh_0p5m.tif"


def final_lattice_level(run: Path) -> tuple[np.ndarray, rasterio.Affine]:
    """zmin + the last frame's depth, per lattice cell, NaN where inactive or dry."""
    with rasterio.open(run / "maps" / "max_level.tif") as a, rasterio.open(run / "maps" / "max_depth.tif") as b:
        zmin = a.read(1).astype(np.float64) - b.read(1).astype(np.float64)
        zmin[a.read(1) == a.nodata] = np.nan
        tr = a.transform
    with h5py.File(run / "results.h5", "r") as f:
        names = sorted(f["maps"].keys())
        d = f["maps"][names[-1]]["depth"][...].astype(np.float64)
        t_last = float(f["maps"][names[-1]].attrs["t_s"])
    level = zmin + d
    level[d <= 1e-3] = np.nan
    return level, tr, t_last


def main() -> None:
    folder = ROOT / "W46 centre-based mesh generator" / "race_faydh" / (sys.argv[1] if len(sys.argv) > 1 else "reach_long_steady_ramp")
    runs = sys.argv[2:] or ["sq2", "sq5", "sq10", "sq20", "ce10", "ce20"]
    geoms = []
    with fiona.open(folder / "ce20" / "maps" / "strip_mesh.gpkg", layer="strip_cells") as src:
        for feat in src:
            geoms.append(shapely.geometry.shape(feat["geometry"]))
    xmin, ymin, xmax, ymax = shapely.total_bounds(np.array(geoms, dtype=object))
    with rasterio.open(DEM) as src:
        win = from_bounds(xmin - 2, ymin - 2, xmax + 2, ymax + 2, src.transform).round_offsets().round_lengths()
        z = src.read(1, window=win).astype(np.float64)
        tr = src.window_transform(win)
        p = src.res[0]
        z[z > 1e30] = np.nan
    inside = features.rasterize(((g, 1) for g in geoms), out_shape=z.shape, transform=tr, fill=0, dtype="uint8") == 1
    xs = tr.c + (np.arange(z.shape[1]) + 0.5) * tr.a
    ys = tr.f + (np.arange(z.shape[0]) + 0.5) * tr.e

    def on_pixels(level: np.ndarray, ltr) -> np.ndarray:
        cols = np.clip(((xs - ltr.c) / ltr.a).astype(int), 0, level.shape[1] - 1)
        rows = np.clip(((ys - ltr.f) / ltr.e).astype(int), 0, level.shape[0] - 1)
        return level[rows[:, None], cols[None, :]]

    surfaces: dict[str, np.ndarray] = {}
    for run in runs:
        path = folder / run
        if not (path / "results.h5").is_file():
            print(f"{run}: no run")
            continue
        level, ltr, t_last = final_lattice_level(path)
        surface = on_pixels(level, ltr)
        strip = path / "maps" / "strip_mesh.gpkg"
        if strip.is_file():
            g, lev = [], []
            with fiona.open(strip, layer="strip_cells") as src:
                for feat in src:
                    g.append(shapely.geometry.shape(feat["geometry"]))
                    lev.append(feat["properties"]["level_end_m"])
            owner = features.rasterize(((gg, k) for k, gg in enumerate(g)), out_shape=z.shape, transform=tr, fill=-1, dtype="int32")
            surface = np.where(owner >= 0, np.asarray(lev)[np.clip(owner, 0, None)], surface)
        surfaces[run] = surface
        print(f"{run}: last frame at {t_last / 3600:.1f} h")
    ref = surfaces.get("sq2")
    out = {}
    if ref is None:
        return
    vr = np.nansum(np.clip(ref - z, 0, None)[inside]) * p * p
    print(f"\n{folder.name}: final steady surfaces against the 2 m squares inside the 20 m strip's footprint ({vr / 1e3:.1f} e3 m3 of water)")
    for run, s in surfaces.items():
        if run == "sq2":
            continue
        wet = inside & ((s > z + 0.01) | (ref > z + 0.01))
        d = (s - ref)[wet]
        v = np.nansum(np.clip(s - z, 0, None)[inside]) * p * p
        out[run] = {"surface_mean_m": float(np.nanmean(d)), "surface_median_m": float(np.nanmedian(d)), "water_ratio": float(v / vr)}
        print(f"  {run:5s} surface mean {np.nanmean(d):+.3f} m, median {np.nanmedian(d):+.3f}; water {100 * (v / vr - 1):+.1f} %")
    (folder / "steady_surfaces.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
