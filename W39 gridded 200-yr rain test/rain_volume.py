"""The rain on the Bidah 03 domain read from the files themselves, without Wadi2D's readers. Venv python only.

usage: rain_volume.py OUT.json [--cells results.h5] [--basin basin.gpkg]

- NetCDF through h5py, DSS through hecdss, the PMP GeoTIFF through rasterio; the HMS tables through hecdss.
- A polygon's depth is the mean of the pixels it covers, each weighted by the area it shares with the polygon, in the
  file's own coordinate system; the volume is that depth times the polygon's area in UTM 40N, where the cells are.
- ``--cells``: the same depth read as the 2D cells read it, the pixel under each active cell centre, as a second figure.
- ``--basin``: the same for every subbasin of a generated basin.
- The DSS row order is not assumed: both orders are sampled against the NetCDF at the same ground points and the one
  that agrees is used, and both correlations are written.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np
import pyogrio
import pyproj
import rasterio
import shapely
from hecdss import HecDss

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
GRID = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\Grid")
NC = GRID / "netCDF" / "Precipitation_RP200_10min.nc"
DSS = GRID / "DSS" / "Precipitation_RP200_10min.dss"
HMS = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\HEC_HMS_Block_02")
PMP = HMS / "Hydrology Data" / "Rainfall Grids" / "tiff" / "Clip_PMP_823mm_21c_27032024.tif"
SQLITE = HMS / "Basin_1.sqlite"
PROJECT_DSS = HMS / "HEC_HMS_Block_02.dss"
DOMAIN = REPO / "W1 research and design note" / "validation" / "block2_full" / "domain_Bidah03.geojson"
UTM = "EPSG:32640"
SEGMENT_M = 20.0
NULL_BELOW = -1.0e30
NC_FILL = -9999.0
STORM_AREA_KM2 = 300.0
ARF_PATH = "//ARF FM/AREA-REDUCTION FACTOR///TABLE/"
PMP_PATTERN = "//FM PMP/PERCENT GRAPH///TABLE/"
RP200_PATTERN = "//FM 10-1000yr/PERCENT GRAPH///TABLE/"
SAMPLE_STEP_M = 4000.0


@dataclass
class Grid:
    """Totals, north row first, with the outer north-west corner and the pixel size."""

    totals: np.ndarray
    west: float
    north: float
    dx: float
    dy: float
    crs: str
    frames: int

    def boxes(self, polygon):
        left, bottom, right, top = shapely.bounds(polygon)
        c0 = max(int(np.floor((left - self.west) / self.dx)), 0)
        c1 = min(int(np.ceil((right - self.west) / self.dx)), self.totals.shape[1])
        r0 = max(int(np.floor((self.north - top) / self.dy)), 0)
        r1 = min(int(np.ceil((self.north - bottom) / self.dy)), self.totals.shape[0])
        rows, cols = np.mgrid[r0:r1, c0:c1]
        x = self.west + cols.ravel() * self.dx
        y = self.north - rows.ravel() * self.dy
        return rows.ravel(), cols.ravel(), shapely.box(x, y - self.dy, x + self.dx, y)

    def at(self, x, y):
        """Total under each point (in this grid's system); NaN off the grid."""
        col = np.floor((np.asarray(x) - self.west) / self.dx).astype(np.int64)
        row = np.floor((self.north - np.asarray(y)) / self.dy).astype(np.int64)
        ok = (row >= 0) & (row < self.totals.shape[0]) & (col >= 0) & (col < self.totals.shape[1])
        out = np.full(row.shape, np.nan)
        out[ok] = self.totals[row[ok], col[ok]]
        return out


def to_grid(polygon_utm, crs):
    t = pyproj.Transformer.from_crs(UTM, crs, always_xy=True)
    dense = shapely.segmentize(polygon_utm, SEGMENT_M)
    return shapely.make_valid(
        shapely.transform(dense, lambda p: np.column_stack(t.transform(p[:, 0], p[:, 1])))
    )


def weighted(grid: Grid, polygon_utm) -> dict:
    """Area-weighted mean over a polygon, and the share of the polygon on pixels with data."""
    poly = to_grid(polygon_utm, grid.crs)
    rows, cols, boxes = grid.boxes(poly)
    areas = shapely.area(shapely.intersection(boxes, poly))
    depth = grid.totals[rows, cols]
    keep = (areas > 0) & np.isfinite(depth)
    mean = float((areas[keep] * depth[keep]).sum() / areas[keep].sum())
    area_utm = float(shapely.area(polygon_utm))
    return {
        "mean_mm": mean,
        "covered": float(areas[keep].sum() / shapely.area(poly)),
        "pixels": int(keep.sum()),
        "area_m2": area_utm,
        "volume_m3": mean / 1000.0 * area_utm,
    }


def centre_count(grid: Grid, polygon_utm) -> dict:
    """Unweighted mean of the pixels whose centre lies in the polygon: how HMS averages a depth grid."""
    t = pyproj.Transformer.from_crs(grid.crs, UTM, always_xy=True)
    poly_g = to_grid(polygon_utm, grid.crs)
    rows, cols, _ = grid.boxes(shapely.buffer(poly_g, 2 * grid.dx))
    x = grid.west + (cols + 0.5) * grid.dx
    y = grid.north - (rows + 0.5) * grid.dy
    ux, uy = t.transform(x, y)
    inside = shapely.contains_xy(polygon_utm, ux, uy)
    depth = grid.totals[rows, cols]
    keep = inside & np.isfinite(depth)
    return {"mean_mm": float(depth[keep].mean()) if keep.any() else None, "pixels": int(keep.sum())}


def read_nc() -> Grid:
    with h5py.File(NC, "r") as f:
        rain = f["precipitation"][:].astype(np.float64)
        x, y = f["x"][:], f["y"][:]
        crs = f["spatial_ref"].attrs["crs_wkt"].decode()
        ends = f["time"][:]
    rain[rain == NC_FILL] = np.nan
    dx, dy = float(np.diff(x).mean()), float(-np.diff(y).mean())
    assert np.allclose(np.diff(x), dx) and np.allclose(-np.diff(y), dy) and dy > 0, "regular, north row first"
    assert np.allclose(np.diff(ends), 10.0) and ends[0] == 10.0, ends[:3]
    totals = rain.sum(axis=0)
    return Grid(totals, float(x[0] - dx / 2), float(y[0] + dy / 2), dx, dy, crs, rain.shape[0])


def read_dss() -> tuple[np.ndarray, dict]:
    with HecDss(str(DSS)) as f:
        paths = sorted(str(p) for p in f.get_catalog().uncondensed_paths)
        total, meta = None, None
        for p in paths:
            g = f.get(p)
            data = np.array(g.data, dtype=np.float64)
            data[data < NULL_BELOW] = np.nan
            total = data if total is None else total + data
            if meta is None:
                meta = {
                    "llx": g.lowerLeftCellX, "lly": g.lowerLeftCellY, "cell": g.cellSize, "wkt": g.srsDefinition,
                    "x0": g.xCoordOfGridCellZero, "y0": g.yCoordOfGridCellZero, "type": g.type, "first": p,
                    "last": paths[-1], "units": g.dataUnits,
                }  # fmt: skip
    meta["frames"] = len(paths)
    return total, meta


def dss_grids(total: np.ndarray, meta: dict) -> dict[str, Grid]:
    cell = meta["cell"]
    west = meta["x0"] + meta["llx"] * cell
    north = meta["y0"] + (meta["lly"] + total.shape[0]) * cell
    return {
        order: Grid(t, west, north, cell, cell, meta["wkt"], meta["frames"])
        for order, t in (("south row first", total[::-1]), ("north row first", total))
    }


def orientation(nc: Grid, candidates: dict[str, Grid]) -> dict:
    """Both DSS row orders against the NetCDF at the same ground points, a 4 km lattice over the NetCDF grid."""
    xs = np.arange(nc.west + 1000.0, nc.west + nc.dx * nc.totals.shape[1], SAMPLE_STEP_M)
    ys = np.arange(nc.north - 1000.0, nc.north - nc.dy * nc.totals.shape[0], -SAMPLE_STEP_M)
    gx, gy = np.meshgrid(xs, ys)
    gx, gy = gx.ravel(), gy.ravel()
    ref = nc.at(gx, gy)
    t = pyproj.Transformer.from_crs(UTM, next(iter(candidates.values())).crs, always_xy=True)
    sx, sy = t.transform(gx, gy)
    out = {}
    for order, grid in candidates.items():
        v = grid.at(sx, sy)
        ok = np.isfinite(v) & np.isfinite(ref)
        out[order] = {
            "points": int(ok.sum()),
            "correlation": float(np.corrcoef(ref[ok], v[ok])[0, 1]),
            "median_abs_mm": float(np.median(np.abs(ref[ok] - v[ok]))),
        }
    return out


def read_pmp() -> Grid:
    with rasterio.open(PMP) as d:
        a = d.read(1, masked=True).astype(np.float64).filled(np.nan)
        tr = d.transform
        assert tr.b == 0 and tr.d == 0 and tr.e < 0
        return Grid(a, tr.c, tr.f, tr.a, -tr.e, d.crs.to_wkt(), 1)


def hms_tables() -> dict:
    with HecDss(str(PROJECT_DSS)) as f:
        arf = f.get(ARF_PATH)
        pmp = f.get(PMP_PATTERN)
        rp = f.get(RP200_PATTERN)
        areas, factors = np.ravel(arf.ordinates), np.ravel(arf.values)
        return {
            "arf_areas_km2": [float(v) for v in areas],
            "arf_factors": [float(v) for v in factors],
            "arf_at_300": float(np.interp(STORM_AREA_KM2, areas, factors)),
            "arf_at_20.971": float(np.interp(20.971, areas, factors)),
            "pmp_pattern_end_percent": float(np.ravel(pmp.values)[-1]),
            "pmp_pattern_time_end_percent": float(np.ravel(pmp.ordinates)[-1]),
            "rp200_pattern_end_percent": float(np.ravel(rp.values)[-1]),
        }


def cells_figure(grid: Grid, h5: Path) -> dict:
    """The pixel under each active cell centre, as the 2D cells read it."""
    with h5py.File(h5, "r") as f:
        mask = f["mask"][:].astype(bool)
        x0, y0, dx = float(f.attrs["x0"]), float(f.attrs["y0"]), float(f.attrs["dx"])
    rows, cols = np.nonzero(mask)
    x, y = x0 + (cols + 0.5) * dx, y0 - (rows + 0.5) * dx
    gx, gy = pyproj.Transformer.from_crs(UTM, grid.crs, always_xy=True).transform(x, y)
    depth = grid.at(gx, gy)
    return {
        "cells": int(rows.size), "dx": dx, "off_grid": int(np.count_nonzero(~np.isfinite(depth))),
        "mean_mm": float(np.nanmean(depth)), "volume_m3": float(np.nansum(depth) / 1000.0 * dx * dx),
    }  # fmt: skip


def polygons(path: Path, layer_hint: str) -> dict:
    layer = next(n for n, _k in pyogrio.list_layers(path) if layer_hint in n.lower())
    frame = pyogrio.read_dataframe(path, layer=layer)
    if frame.crs is not None and frame.crs.to_epsg() != 32640:
        frame = frame.to_crs(UTM)
    return {str(r["name"]): shapely.make_valid(r.geometry) for _i, r in frame.iterrows()}


def main(argv: list[str]) -> int:
    out = Path(argv[0])
    cells = Path(argv[argv.index("--cells") + 1]) if "--cells" in argv else None
    basin = Path(argv[argv.index("--basin") + 1]) if "--basin" in argv else None
    domain = shapely.make_valid(
        shapely.from_geojson(
            json.dumps(json.loads(DOMAIN.read_text(encoding="utf-8"))["features"][0]["geometry"])
        )
    )
    s13 = polygons(SQLITE, "subbasin2d")["S13"]
    nc = read_nc()
    total, meta = read_dss()
    candidates = dss_grids(total, meta)
    agree = orientation(nc, candidates)
    order = max(agree, key=lambda k: agree[k]["correlation"])
    dss = candidates[order]
    pmp = read_pmp()
    report: dict = {
        "domain_area_km2": shapely.area(domain) / 1e6,
        "s13_polygon_area_km2": shapely.area(s13) / 1e6,
        "tables": hms_tables(),
        "dss_meta": {k: v for k, v in meta.items() if k != "wkt"} | {"crs": pyproj.CRS(meta["wkt"]).name},
        "dss_orientation": agree,
        "dss_order_used": order,
        "nc": {
            "frames": nc.frames,
            "crs": pyproj.CRS(nc.crs).name,
            "domain": weighted(nc, domain),
            "S13": weighted(nc, s13),
        },
        "dss": {
            "frames": dss.frames,
            "crs": pyproj.CRS(dss.crs).name,
            "domain": weighted(dss, domain),
            "S13": weighted(dss, s13),
        },
        "pmp": {
            "file": PMP.name,
            "pixel_m": [pmp.dx, pmp.dy],
            "domain": weighted(pmp, domain),
            "domain_centres": centre_count(pmp, domain),
            "S13": weighted(pmp, s13),
            "S13_centres": centre_count(pmp, s13),
        },
    }
    if cells is not None:
        for key, grid in (("nc", nc), ("dss", dss), ("pmp", pmp)):
            report[key]["cells"] = cells_figure(grid, cells)
    if basin is not None:
        subs = polygons(basin, "subbasin")
        for key, grid in (("nc", nc), ("dss", dss)):
            report[key]["subbasins"] = {name: weighted(grid, poly) for name, poly in subs.items()}
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "out": str(out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
