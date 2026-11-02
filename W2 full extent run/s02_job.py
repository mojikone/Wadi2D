"""The job of the full-extent run: Block 2's 200-yr storm over the actual project boundary, open along the coast.

Storm and design outputs come from the Block 2 10 m job, so the pattern, the ARF table and the five dam lines are the
ones already validated; only the depth and the storm area change, to those of FM_200yr.met. Writes domain.geojson,
jobs/full_30m_200yr.json and boundaries.geojson.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pyogrio
import rasterio
from shapely.ops import substring

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TEMPLATE = ROOT / "W1 research and design note" / "validation" / "block2_full" / "jobs" / "c10_A74_h100.json"
BOUNDARY = (
    r"W:\2224 Flood Protection Scheme in North & South Batinah_MAFWWR\06-WORKING\04-Hydraulic\00 Data\SHP"
    r"\Project Boundary\Project Boundary Actual extent.shp"
)
DEM = HERE / "terrain" / "NSA5_COP30_blend.tif"
CN = r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\HEC_HMS_Block_02\Hydrology Data\CN_Include_Hill_Area.tif"

DX = 30.0  # 6 NSA pixels; the finest that fits the 16 GB card
MANNING = 0.05  # one value: the n of the HEC-RAS head-to-head; the hill and wadi rasters exist for Block 2 only
CN_DEFAULT = 88.0  # the 24 km2 the CN grid misses
STORM_DEPTH_MM = 251.0  # FM_200yr.met
STORM_AREA_KM2 = 300.0  # FM_200yr.met
DURATION_S = 36 * 3600.0  # as the Block 2 10 m run
COAST_Z = 5.0  # m; a stretch of the edge on ground this low is an outlet
COAST_MIN_M = 1000.0
COAST_GAP_M = 1000.0  # a higher stretch shorter than this stays open
EDGE_SLOPE = 0.003  # energy slope at the outlets; fan toe on the coastal plain
SAMPLE_M = 100.0


def coast_lines(poly) -> list[list[tuple[float, float]]]:
    """Stretches of the edge on low ground, half a cell inside it, so they lie on the last row of cells."""
    inner = poly.buffer(-0.6 * DX)
    if inner.geom_type != "Polygon":
        inner = max(inner.geoms, key=lambda g: g.area)
    ring = inner.exterior
    along = np.arange(0.0, ring.length, SAMPLE_M)
    points = [ring.interpolate(s).coords[0][:2] for s in along]
    with rasterio.open(DEM) as d:
        z = np.array([v[0] for v in d.sample(points)], dtype=float)
    low = z <= COAST_Z
    edges = np.flatnonzero(np.diff(np.r_[0, low.astype(int), 0]))
    runs = [[int(a), int(b)] for a, b in zip(edges[::2], edges[1::2])]
    merged: list[list[int]] = []
    for a, b in runs:
        if merged and (a - merged[-1][1]) * SAMPLE_M < COAST_GAP_M:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    lines = []
    for a, b in merged:
        if (b - a) * SAMPLE_M < COAST_MIN_M:
            continue
        part = substring(ring, along[a], min(along[b - 1] + SAMPLE_M, ring.length)).simplify(5.0)
        lines.append([(round(x, 2), round(y, 2)) for x, y in part.coords])
    return lines


def main() -> None:
    poly = pyogrio.read_dataframe(BOUNDARY).geometry.iloc[0]
    crs = {"type": "name", "properties": {"name": "EPSG:32640"}}
    ring = [[round(x, 3), round(y, 3)] for x, y in poly.exterior.coords]
    domain = HERE / "domain.geojson"
    domain.write_text(
        json.dumps({"type": "FeatureCollection", "crs": crs, "features": [
            {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [ring]}}]}),
        encoding="utf-8",
    )  # fmt: skip
    lines = coast_lines(poly)
    length = sum(np.hypot(*np.diff(np.array(k), axis=0).T).sum() for k in lines) / 1000.0
    print(f"{len(lines)} outlets, {length:,.0f} km of the {poly.exterior.length / 1000:,.0f} km edge")
    (HERE / "boundaries.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "crs": crs, "features": [
            {"type": "Feature", "properties": {"n": n}, "geometry": {"type": "LineString", "coordinates": k}}
            for n, k in enumerate(lines)]}),
        encoding="utf-8",
    )  # fmt: skip

    job = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    job["project"] = {"name": "full_30m_200yr", "description": "Block 2 200-yr storm over the actual project boundary"}
    job["grid"].update({"dx": DX, "domain": str(domain), "cache_dir": str(HERE / "cache")})
    job["terrain"].update({"dem": str(DEM), "pixel_stride": 1, "manning": MANNING, "manning_raster": None, "cn_raster": CN})
    job["storm"].update({"depth_mm": STORM_DEPTH_MM, "storm_area_km2": STORM_AREA_KM2})
    job["hydrology"]["curve_number"] = CN_DEFAULT
    job["boundaries"] = [{"kind": "normal", "slope": EDGE_SLOPE, "coordinates": k} for k in lines]
    job["run"]["duration_s"] = DURATION_S
    (HERE / "jobs").mkdir(exist_ok=True)
    out = HERE / "jobs" / "full_30m_200yr.json"
    out.write_text(json.dumps(job, indent=1), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
