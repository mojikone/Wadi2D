"""NSA 5 m with Copernicus 30 m in its gaps, on the NSA pixel lattice, over the actual project boundary.

NSA stays exact away from a gap. Inside a gap the ground is Copernicus plus a correction that equals the local NSA
difference at the edge of the gap and relaxes to the median difference further in. Over a band on the NSA side the two
surfaces are feathered, so no step is left at the border. Writes terrain/NSA5_COP30_blend.tif and terrain/blend_qa.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pyogrio
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject
from rasterio.windows import Window
from scipy import ndimage
from shapely import contains_xy

HERE = Path(__file__).resolve().parent
NSA = r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\Terrain\NSA_Batinah_5m.tif"
COP = r"D:\Mojtaba\Renardet\2224 WS11\Oman Streams\Terrain\Oman Copernicus 30 m.tif"
BOUNDARY = (
    r"W:\2224 Flood Protection Scheme in North & South Batinah_MAFWWR\06-WORKING\04-Hydraulic\00 Data\SHP"
    r"\Project Boundary\Project Boundary Actual extent.shp"
)
OUT = HERE / "terrain" / "NSA5_COP30_blend.tif"

PIX = 5.0  # m, the NSA pixel
SCALE = 6  # NSA pixels in one coarse cell
COARSE = PIX * SCALE
LEFT, TOP = 398650.0, 2773900.0  # on the NSA lattice, outside the boundary
EDGE_M = 300.0  # NSA cells this close to a gap set the local correction
SMOOTH_M = 150.0  # gaussian sigma of that correction
TAPER_M = 1500.0  # into a gap, the distance over which it relaxes to the median
FEATHER_M = 300.0  # width of the blend on the NSA side
BLOCK = 4096


def coarse_layers(poly) -> dict:
    x0, y0, x1, _ = poly.bounds
    nx = int(np.ceil((x1 + 50.0 - LEFT) / COARSE))
    ny = int(np.ceil((TOP - (y0 - 50.0)) / COARSE))
    tr = from_origin(LEFT, TOP, COARSE, COARSE)
    cop = np.full((ny, nx), np.nan, "float32")
    nsa = np.full((ny, nx), np.nan, "float32")
    with rasterio.open(COP) as s:
        reproject(rasterio.band(s, 1), cop, dst_transform=tr, dst_crs="EPSG:32640", dst_nodata=np.nan, resampling=Resampling.bilinear)
    with rasterio.open(NSA) as s:
        reproject(rasterio.band(s, 1), nsa, dst_transform=tr, dst_crs="EPSG:32640", dst_nodata=np.nan, resampling=Resampling.average)
    cop = np.nan_to_num(cop, nan=0.0)
    valid = np.isfinite(nsa)
    from_gap = ndimage.distance_transform_edt(valid) * COARSE  # on NSA, how far to the nearest gap
    edge = valid & (from_gap <= EDGE_M)
    diff = np.where(edge, nsa - cop, 0.0)
    xs = LEFT + (np.arange(nx) + 0.5) * COARSE
    ys = TOP - (np.arange(ny) + 0.5) * COARSE
    gx, gy = np.meshgrid(xs, ys)
    inside = contains_xy(poly, gx, gy)
    base = float(np.median(diff[edge & inside]))
    sigma = SMOOTH_M / COARSE
    weight = ndimage.gaussian_filter(edge.astype("float32"), sigma)
    near = ndimage.gaussian_filter(diff.astype("float32"), sigma) / np.maximum(weight, 1e-3)
    near = np.clip(near, base - 15.0, base + 15.0)
    distance, index = ndimage.distance_transform_edt(~edge, return_indices=True)
    held = near[index[0], index[1]]
    relax = np.clip(1.0 - distance * COARSE / TAPER_M, 0.0, 1.0)
    correction = (base + (held - base) * relax).astype("float32")
    weight_nsa = np.clip(from_gap / FEATHER_M, 0.0, 1.0).astype("float32")
    return {"cop": cop, "nsa": nsa, "correction": correction, "weight": weight_nsa, "base": base, "valid": valid,
            "inside": inside, "shape": (ny, nx), "transform": tr}  # fmt: skip


def upsample(a: np.ndarray, row: int, col: int, rows: int, cols: int) -> np.ndarray:
    """Bilinear from the coarse grid to the block of NSA pixels starting at (row, col)."""
    r = (np.arange(row, row + rows) + 0.5) / SCALE - 0.5
    c = (np.arange(col, col + cols) + 0.5) / SCALE - 0.5
    r0 = np.clip(np.floor(r).astype(int), 0, a.shape[0] - 2)
    c0 = np.clip(np.floor(c).astype(int), 0, a.shape[1] - 2)
    fr = (r - r0).clip(0.0, 1.0)[:, None]
    fc = (c - c0).clip(0.0, 1.0)[None, :]
    near = a[np.ix_(r0, c0)] * (1 - fc) + a[np.ix_(r0, c0 + 1)] * fc
    far = a[np.ix_(r0 + 1, c0)] * (1 - fc) + a[np.ix_(r0 + 1, c0 + 1)] * fc
    return near * (1 - fr) + far * fr


def main() -> None:
    OUT.parent.mkdir(exist_ok=True)
    poly = pyogrio.read_dataframe(BOUNDARY).geometry.iloc[0]
    layers = coarse_layers(poly)
    ny, nx = layers["shape"]
    print(f"coarse grid {nx} x {ny}; median NSA minus Copernicus at the gap edge {layers['base']:.2f} m", flush=True)
    height, width = ny * SCALE, nx * SCALE
    profile = {"driver": "GTiff", "height": height, "width": width, "count": 1, "dtype": "float32", "crs": "EPSG:32640",
               "transform": from_origin(LEFT, TOP, PIX, PIX), "nodata": -9999.0, "tiled": True, "blockxsize": 512,
               "blockysize": 512, "compress": "deflate", "predictor": 3, "zlevel": 1, "BIGTIFF": "YES"}  # fmt: skip
    copied = blended = 0
    with rasterio.open(NSA) as src, rasterio.open(OUT, "w", **profile) as dst:
        col_off = round((LEFT - src.transform.c) / PIX)
        row_off = round((src.transform.f - TOP) / PIX)
        for row in range(0, height, BLOCK):
            rows = min(BLOCK, height - row)
            for col in range(0, width, BLOCK):
                cols = min(BLOCK, width - col)
                a = np.full((rows, cols), np.nan, "float32")
                r0, c0 = row + row_off, col + col_off
                r1, c1 = max(r0, 0), max(c0, 0)
                r2, c2 = min(r0 + rows, src.height), min(c0 + cols, src.width)
                if r2 > r1 and c2 > c1:
                    part = src.read(1, window=Window(c1, r1, c2 - c1, r2 - r1), masked=True)
                    a[r1 - r0 : r2 - r0, c1 - c0 : c2 - c0] = part.filled(np.nan)
                w = upsample(layers["weight"], row, col, rows, cols)
                if w.min() >= 1.0 and np.isfinite(a).all():
                    copied += 1
                else:
                    fill = upsample(layers["cop"], row, col, rows, cols) + upsample(layers["correction"], row, col, rows, cols)
                    keep = np.isfinite(a)
                    z = fill.copy()
                    z[keep] = (w * np.nan_to_num(a) + (1.0 - w) * fill)[keep]
                    a = z.astype("float32")
                    blended += 1
                dst.write(a, 1, window=Window(col, row, cols, rows))
            print(f"row {row + rows} of {height}; copied {copied}, blended {blended}", flush=True)

    # step across the border, before and after, on the coarse grid
    mean = np.full((ny, nx), np.nan, "float32")
    with rasterio.open(OUT) as s:
        reproject(rasterio.band(s, 1), mean, dst_transform=layers["transform"], dst_crs="EPSG:32640", dst_nodata=np.nan, resampling=Resampling.average)
    valid, inside, nsa, cop = layers["valid"], layers["inside"], layers["nsa"], layers["cop"]
    plain = valid & (ndimage.distance_transform_edt(valid) * COARSE > FEATHER_M + COARSE) & inside
    jump_after, jump_before = [], []
    for axis in (0, 1):
        a, b = valid, np.roll(valid, -1, axis)
        pairs = (a != b) & inside & np.roll(inside, -1, axis)
        jump_after.append(np.abs(mean - np.roll(mean, -1, axis))[pairs])
        raw = np.where(valid, nsa, cop)
        jump_before.append(np.abs(raw - np.roll(raw, -1, axis))[pairs])
    after = np.concatenate(jump_after)
    before = np.concatenate(jump_before)
    typical = np.abs(np.diff(mean, axis=1))[plain[:, :-1] & plain[:, 1:]]
    qa = {
        "median_nsa_minus_cop_m": layers["base"],
        "gap_km2_inside_boundary": float((~valid & inside).sum() * COARSE**2 * 1e-6),
        "nsa_changed_beyond_feather_max_m": float(np.nanmax(np.abs(mean - nsa)[plain])),
        "step_at_border_raw_median_p95_m": [float(np.median(before)), float(np.percentile(before, 95))],
        "step_at_border_blended_median_p95_m": [float(np.median(after)), float(np.percentile(after, 95))],
        "step_30m_on_plain_nsa_median_p95_m": [float(np.median(typical)), float(np.percentile(typical, 95))],
        "constants": {"EDGE_M": EDGE_M, "SMOOTH_M": SMOOTH_M, "TAPER_M": TAPER_M, "FEATHER_M": FEATHER_M},
    }
    (HERE / "terrain" / "blend_qa.json").write_text(json.dumps(qa, indent=1), encoding="utf-8")
    print(json.dumps(qa, indent=1), flush=True)


if __name__ == "__main__":
    main()
