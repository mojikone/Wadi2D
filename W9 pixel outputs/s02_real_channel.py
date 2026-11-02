"""The sloped surface on the solver's own water: a straight channel at 1, 5 and 10 %, 30 m cells on 5 m pixels, steady.

The freeboard cases of s01 are built by hand; here the levels come from a real run. The true surface is the bed plus
the steady depth, read as the median depth of the channel's mid reach, so this checks the shape, not the solver's
depth. Writes real_channel.json. Run from the repository root with PYTHONPATH on it.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import Affine

from wadi2d.config.schema import RunConfig
from wadi2d.products.step import PIXEL_DIR
from wadi2d.run import run_job

HERE = Path(__file__).resolve().parent
PIXEL, CELL = 5.0, 30.0
NX, NY = 720, 120  # pixels: 3.6 km by 600 m
WIDTH = 45.0
BANK = 6.0
X0, Y0 = 400000.0, 2700000.0
FLOW = 80.0


def dem(path: Path, slope: float) -> np.ndarray:
    x = (np.arange(NX) + 0.5) * PIXEL
    y = (np.arange(NY) + 0.5) * PIXEL
    gx, gy = np.meshgrid(x, y)
    off = np.abs(gy - NY * PIXEL / 2.0 - 7.5)
    z = 500.0 - slope * gx + np.where(off <= WIDTH / 2.0, 0.0, BANK)
    with rasterio.open(
        path, "w", driver="GTiff", height=NY, width=NX, count=1, dtype="float32", crs="EPSG:32640",
        transform=Affine(PIXEL, 0.0, X0, 0.0, -PIXEL, Y0),
    ) as out:  # fmt: skip
        out.write(z.astype(np.float32), 1)
    return z


def case(slope: float) -> dict:
    tmp = Path(tempfile.mkdtemp())
    z = dem(tmp / "dem.tif", slope)
    middle = Y0 - NY * PIXEL / 2.0 - 7.5
    cfg = RunConfig.model_validate(
        {
            "grid": {"dx": CELL, "extent": (X0, Y0 - NY * PIXEL, X0 + NX * PIXEL, Y0)},
            "terrain": {"dem": str(tmp / "dem.tif"), "manning": 0.03},
            "hydrology": {
                "inflows": [
                    {"name": "in", "x": X0 + 45.0, "y": middle, "times_s": [0.0, 1e6], "flows": [FLOW, FLOW]}
                ],
                "inject_radius": 40.0,
            },
            "boundaries": [
                {"kind": "free", "coordinates": [(X0 + NX * PIXEL - 15.0, Y0), (X0 + NX * PIXEL - 15.0, Y0 - NY * PIXEL)]}
            ],
            "run": {"duration_s": 2400.0},
            "outputs": {"map_every_s": 600.0, "live_every_s": 0.0},
        }
    )
    summary = run_job(cfg, tmp / "run")
    assert summary.exit_code == 0, summary.message
    with rasterio.open(tmp / "run" / PIXEL_DIR / "pixel_depth.tif") as src:
        depth = src.read(1, masked=True).filled(0.0)
        t = src.transform
    top = round((Y0 - t.f) / PIXEL)
    left = round((t.c - X0) / PIXEL)
    ground = z[top : top + depth.shape[0], left : left + depth.shape[1]]
    x = (np.arange(depth.shape[1]) + 0.5) * PIXEL + (t.c - X0)
    reach = (x > 1000.0) & (x < 2800.0)
    channel = ground < (500.0 - slope * ((np.arange(ground.shape[1]) + 0.5) * PIXEL + (t.c - X0)))[None, :] + BANK / 2
    in_reach = depth[:, reach][channel[:, reach]]
    steady = float(np.median(in_reach))
    bank = ~channel[:, reach]
    flat_error = 12.5 * slope
    return {
        "slope": slope,
        "steady_depth_m": round(steady, 3),
        "surface_spread_m": round(float(np.quantile(np.abs(in_reach - steady), 0.99)), 3),
        "flat_error_m": round(flat_error, 3),
        "bank_pixels_wet_pct": round(float((depth[:, reach][bank] >= 0.05).mean() * 100.0), 3),
    }


rows = [case(slope) for slope in (0.01, 0.05, 0.10)]
print(json.dumps(rows, indent=1))
(HERE / "real_channel.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
