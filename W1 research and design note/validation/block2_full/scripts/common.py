"""Shared inputs of the Block 2 full validation: paths, lines, domain, job builder, reference numbers.

Block 2 data are read only. Everything written goes under validation/block2_full.
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import rasterio
import rasterio.features
import shapefile  # noqa: F401
import shapely
from rasterio.windows import from_bounds
from shapely.geometry import mapping
from shapely.geometry.polygon import orient

warnings.simplefilter("ignore")

from wadi2d.engine.hms_import import _storm  # noqa: E402
from wadi2d.hms import load_results  # noqa: E402
from wadi2d.hms import sqlite as hms_sqlite  # noqa: E402

BLOCK = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology")
HMS = BLOCK / "HEC_HMS_Block_02"
DEM = BLOCK / "Terrain" / "GGC_2_MERGE_HDSM.tif"
CN = HMS / "Hydrology Data" / "CN_Include_Hill_Area.tif"
ACC = HMS / "terrain" / "GGC_2_MERGE_HDSM_5m" / "00" / "flowaccum.tif"
DAMS = BLOCK / "SHP" / "Block 2 Dams" / "SHP"
OUT = Path(r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\block2_full")
JOBS = OUT / "jobs"
RUNS = OUT / "runs"
CACHE = OUT / "cache_3f32ca6"

SITES = {"Bidah 03": 20.971, "Faydh 01": 74.304, "R5A": 117.1046, "R2A": 175.8665, "Z4C": 211.085}
UPSTREAM = {
    "Bidah 03": ["S13"],
    "Faydh 01": ["S11", "S12"],
    "R5A": ["S14", "S15", "S16", "S17", "S18"],
    "R2A": ["S5", "S6", "S7", "S8", "S9", "S10"],
    "Z4C": ["S1", "S2", "S3", "S4"],
}
HEADWATERS = ["S1", "S2", "S5", "S6", "S11", "S14"]
ARF_NOTE = "ARF FM: storm-centred ratio of one cyclone, not a fixed-area curve (design note section 7)"
OUTLET_ERODE = 80.0

# dam axes: Dams.shp and Det_Design_DAMS.shp, ends extended to high ground on the 5 m contours.
# Faydh: vertices 2-6 of Dams.shp; the leg 1-2 of the file doubles back and is left out.
AXES = {
    "Bidah 03": [(438100.0, 2727420.0), (438259.32, 2727264.77), (438807.68, 2726752.81), (438870.0, 2726640.0)],
    "Faydh 01": [
        (431000.0, 2734340.0), (431003.28, 2734233.93), (431235.24, 2733997.1), (431244.34, 2733873.98),
        (431019.77, 2733523.58), (431054.16, 2733225.76), (431065.0, 2733130.0),
    ],
    "R5A": [(438960.0, 2721850.0), (438975.1, 2721721.4), (439107.5, 2720389.9), (439154.4, 2719918.2),
            (439118.8, 2719462.1), (439110.0, 2719330.0)],
    "R2A": [(438485.6, 2716855.1), (439178.8, 2716807.2), (440331.5, 2715435.3), (440420.0, 2715330.0)],
    "Z4C": [(440030.0, 2711065.0), (440139.9, 2711053.6), (440335.3, 2711037.5), (440485.5, 2711023.1),
            (440996.7, 2710733.6), (440967.1, 2710405.7), (440773.7, 2710135.6), (440700.0, 2710030.0)],
}


def polygons() -> dict[str, shapely.Geometry]:
    return {r.name: shapely.make_valid(r.shape()) for r in hms_sqlite.subbasin_polygons(HMS / "Basin_1.sqlite")}


def ring_of(names: list[str], polys: dict[str, shapely.Geometry]) -> list[tuple[float, float]]:
    """Exterior of the union, counter-clockwise, so the right of the walk is outside: outflow positive."""
    u = shapely.union_all([polys[n].buffer(1.0) for n in names]).buffer(-1.0)
    if u.geom_type != "Polygon":
        u = max(u.geoms, key=lambda g: g.area)
    u = orient(shapely.Polygon(u.exterior), sign=1.0).simplify(15.0)
    return [(float(x), float(y)) for x, y in u.exterior.coords]


def domain() -> shapely.Geometry:
    """Polygons + 40 m, plus the plain box out to the free edges."""
    polys = polygons()
    u = shapely.union_all([p.buffer(40.0) for p in polys.values()])
    box = shapely.box(430700.0, 2709000.0, 443500.0, 2736200.0)
    return shapely.union_all([u, box]).buffer(0.0)


BOUNDARIES = [
    {"kind": "normal", "slope": 0.008, "coordinates": [(443490.0, 2709000.0), (443490.0, 2736200.0)]},
    {"kind": "normal", "slope": 0.008, "coordinates": [(430700.0, 2736190.0), (443500.0, 2736190.0)]},
    {"kind": "normal", "slope": 0.008, "coordinates": [(441000.0, 2709010.0), (443500.0, 2709010.0)]},
]


def write_domain() -> Path:
    path = OUT / "domain.geojson"
    d = domain()
    path.write_text(
        json.dumps({"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"name": "block2"}, "geometry": mapping(d)}]}),
        encoding="utf-8",
    )
    return path


def design_lines(rings: bool = True) -> list[dict]:
    polys = polygons()
    out = [{"name": n, "coordinates": c, "drainage_area_km2": SITES[n]} for n, c in AXES.items()]
    if rings:
        for n, names in UPSTREAM.items():
            out.append({"name": f"{n} ring", "coordinates": ring_of(names, polys)})
        for n in HEADWATERS:
            out.append({"name": f"{n} ring", "coordinates": ring_of([n], polys)})
    return out


def storm(area: float | None = None, met: str = "FM_100yr.met") -> dict:
    s = _storm(HMS / met, HMS).model_dump()
    s["arf"]["table_type"] = ARF_NOTE
    if area is not None:
        s["storm_area_km2"] = area
    return s


def lumped_outlets() -> dict[str, tuple[float, float]]:
    """Each subbasin's outlet: the largest accumulation inside its polygon, 80 m in from the edge,
    so the point lies upstream of a dam line drawn on the polygon's edge, on the wadi."""
    polys = polygons()
    out = {}
    with rasterio.open(ACC) as src:
        for name, poly in polys.items():
            inner = poly.buffer(-OUTLET_ERODE)
            if inner.is_empty:
                inner = poly
            b = inner.bounds
            w = from_bounds(*b, src.transform).round_offsets().round_lengths()
            a = src.read(1, window=w, masked=True).filled(0.0)
            t = src.window_transform(w)
            mask = rasterio.features.geometry_mask([inner], a.shape, t, invert=True)
            a = np.where(mask, a, 0.0)
            j, i = np.unravel_index(int(np.argmax(a)), a.shape)
            x, y = t * (i + 0.5, j + 0.5)
            out[name] = (float(x), float(y))
    return out


def job(name: str, dx: float, *, area: float | None, mode: str = "c", duration_s: float = 172800.0,
        stride: int = 1, manning: float = 0.04, manning_raster: str | None = None, lines=None,
        points=None, extra: dict | None = None) -> dict:
    """A job dict; mode 'c' rain on every cell, 'b' all 18 subbasins lumped, reaches and plain in 2D."""
    hyd: dict = {"curve_number": 88.0, "hms_basin": str(HMS / "Basin_1.basin"),
                 "hms_sqlite": str(HMS / "Basin_1.sqlite")}
    if mode == "b":
        hyd["subbasins"] = [{"name": n, "mode": "lumped", "outlet": list(p)} for n, p in lumped_outlets().items()]
    j = {
        "project": {"name": name, "description": "Block 2 full validation"},
        "grid": {"dx": dx, "domain": str(OUT / "domain.geojson"), "cache_dir": str(CACHE)},
        "terrain": {"dem": str(DEM), "pixel_stride": stride, "manning": manning,
                    "manning_raster": manning_raster, "cn_raster": str(CN)},
        "storm": storm(area),
        "hydrology": hyd,
        "boundaries": BOUNDARIES,
        "outputs": {"map_every_s": 21600.0, "series_every_s": 60.0, "live_every_s": 0.0,
                    "lines": design_lines() if lines is None else lines, "points": points or []},
        "run": {"duration_s": duration_s, "backend": "gpu", "source_every_s": 30.0, "checkpoint_every_s": 0.0},
    }
    if extra:
        for k, v in extra.items():
            if isinstance(v, dict):
                j.setdefault(k, {}).update(v)
            else:
                j[k] = v
    return j


def write_job(j: dict, name: str) -> Path:
    JOBS.mkdir(parents=True, exist_ok=True)
    path = JOBS / f"{name}.json"
    path.write_text(json.dumps(j, indent=1), encoding="utf-8")
    return path


def hms_reference() -> dict[str, dict[str, float]]:
    r = load_results(HMS / "results" / "DAA_DA_100yr_B1.results")
    out = {}
    for p in SITES:
        e = r.element(p)
        out[p] = {"area": e.drainage_area, "peak": e.outflow_max,
                  "t_h": (e.outflow_max_time - r.start).total_seconds() / 3600.0,
                  "vol_m3": e.outflow_volume, "depth_mm": e.outflow_depth}
    return out
