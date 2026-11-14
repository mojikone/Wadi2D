"""Synthetic grounds of W57 that W46 and W48 did not make: a tributary junction and a gorge opening into a plain.

Both use W48's narrow gorge section (12 m bed, walls 7 m over 1.5 m, a 10 m ledge at 5 %, hills at 50 %) on a 0.5 m
DEM, n 0.05, written with the thalweg file (layer `thalwegs`, an empty `breaklines`) and the domain polygon the
engine reads.

* junction: a straight main gorge 5 km long at 1 %, turned 30 degrees off the lattice, and a tributary gorge 1.5 km
  long at 2 % joining it half-way at 45 or 90 degrees to the main's flow; the ground is the lower of the two valleys.
  The main is written as two segments split at the junction (44 and 74 km2) and the tributary as one (30 km2), as a
  D8 stream file has them, so the generator's chaining and tributary rule do the work.
* plain: the gentle sine of W48 (amplitude 50 m, radius 729 m), the bed widening from 12 to 300 m over 300 m from
  3 km down, 300 m wide for 1.4 km with a 0.5 % fall to its middle, and narrowing back over 300 m.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "W46 centre-based mesh generator"))
import wave_probe as wp  # noqa: E402

NARROW = dict(bed_half=6.0, bank_run=1.5, depth=7.0, plain_w=10.0, plain_slope=0.05, hill=0.5)
PIXEL = 0.5
CRS = wp.CRS


def section(t: np.ndarray, bed_half: np.ndarray | float, floor_fall: float = 0.0) -> np.ndarray:
    """Height above the thalweg bed across a narrow-gorge section of a given bed half-width; a wide bed falls
    `floor_fall` per m towards its middle (zero on the narrow bed)."""
    c = NARROW
    a = np.abs(t)
    bank_top = bed_half + c["bank_run"]
    plain_edge = bank_top + c["plain_w"]
    h = np.where(a < bed_half, floor_fall * a, floor_fall * bed_half + (a - bed_half) / c["bank_run"] * c["depth"])
    top = floor_fall * bed_half + c["depth"]
    h = np.where(a >= bank_top, top + (a - bank_top) * c["plain_slope"], h)
    h = np.where(a >= plain_edge, top + c["plain_w"] * c["plain_slope"] + (a - plain_edge) * c["hill"], h)
    return h


def write_dem(path: Path, x0: float, y0: float, ncols: int, nrows: int, zfun) -> None:
    import rasterio
    from rasterio.transform import from_origin
    from rasterio.windows import Window

    top = y0 + nrows * PIXEL
    x = x0 + (np.arange(ncols) + 0.5) * PIXEL
    profile = dict(driver="GTiff", height=nrows, width=ncols, count=1, dtype="float32", crs=CRS, nodata=-9999.0,
                   transform=from_origin(x0, top, PIXEL, PIXEL), compress="deflate", tiled=True, blockxsize=512, blockysize=512)
    path.unlink(missing_ok=True)
    with rasterio.open(path, "w", **profile) as dst:
        for r0 in range(0, nrows, 100):
            r1 = min(nrows, r0 + 100)
            y = top - (np.arange(r0, r1) + 0.5) * PIXEL
            px, py = np.meshgrid(x, y)
            dst.write(zfun(px, py).astype(np.float32), 1, window=Window(0, r0, ncols, r1 - r0))


def write_lines(path: Path, lines: list[tuple[list, float]]) -> None:
    import fiona
    from shapely.geometry import LineString, mapping

    path.unlink(missing_ok=True)
    with fiona.open(path, "w", driver="GPKG", layer="thalwegs", crs=CRS,
                    schema={"geometry": "LineString", "properties": {"area_km2": "float", "incised_m": "float"}}) as dst:
        for coords, area in lines:
            dst.write({"geometry": mapping(LineString(coords)), "properties": {"area_km2": area, "incised_m": NARROW["depth"]}})
    with fiona.open(path, "w", driver="GPKG", layer="breaklines", crs=CRS,
                    schema={"geometry": "LineString", "properties": {"kind": "str", "side": "str", "area_km2": "float"}}):
        pass


def write_domain(path: Path, geom) -> None:
    from shapely.geometry import mapping

    path.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": path.parent.name}, "geometry": mapping(geom)}]}), encoding="utf-8")


# ---------------------------------------------------------------- the junction

JX0, JY0 = 500_000.0, 2_700_000.0
MAIN_L, TRIB_L, JUNCTION_S = 5_000.0, 1_500.0, 2_500.0
TURN = np.radians(30.0)
HALF = 250.0
"""Half-width of the domain about each thalweg."""


def junction_geometry(angle_deg: float) -> dict:
    d = np.array([np.cos(TURN), np.sin(TURN)])
    n = np.array([-d[1], d[0]])
    a = np.radians(angle_deg)
    head = np.array([JX0 + 400.0, JY0 + 400.0]) + 0.0 * d
    j = head + JUNCTION_S * d
    end = head + MAIN_L * d
    # the tributary flows toward the junction at `angle` to the main's flow, from the +normal side
    td = np.cos(a) * d - np.sin(a) * n
    thead = j - TRIB_L * td
    return dict(d=d, n=n, head=head, j=j, end=end, td=td, thead=thead)


def junction_ground(case: str, angle_deg: float) -> Path:
    from shapely.geometry import LineString

    work = HERE / "ground" / case
    work.mkdir(parents=True, exist_ok=True)
    g = junction_geometry(angle_deg)
    main = LineString([g["head"], g["end"]])
    trib = LineString([g["thead"], g["j"]])
    domain = main.buffer(HALF, cap_style=2).union(trib.buffer(HALF, cap_style=2)).simplify(0.5)
    minx, miny, maxx, maxy = domain.bounds
    x0, y0 = np.floor(minx / 10) * 10 - 20, np.floor(miny / 10) * 10 - 20
    ncols, nrows = int((np.ceil(maxx / 10) * 10 + 20 - x0) / PIXEL), int((np.ceil(maxy / 10) * 10 + 20 - y0) / PIXEL)
    bed_j = 200.0 - JUNCTION_S * wp.S_BED

    def z(px, py):
        rx, ry = px - g["head"][0], py - g["head"][1]
        s = rx * g["d"][0] + ry * g["d"][1]
        t = rx * g["n"][0] + ry * g["n"][1]
        zm = 200.0 - s * wp.S_BED + section(t, NARROW["bed_half"])
        qx, qy = px - g["j"][0], py - g["j"][1]
        st = -(qx * g["td"][0] + qy * g["td"][1])  # distance upstream of the junction along the tributary
        tt = -qx * g["td"][1] + qy * g["td"][0]
        zt = bed_j + 0.02 * np.clip(st, 0.0, None) + section(tt, NARROW["bed_half"])
        zt = np.where(st >= -20.0, zt, np.inf)
        return np.minimum(zm, zt)

    t0 = time.perf_counter()
    write_dem(work / "dem.tif", x0, y0, ncols, nrows, z)
    print(f"{case}: DEM {ncols} x {nrows} in {time.perf_counter() - t0:.0f} s")
    write_lines(work / "thalweg.gpkg", [
        ([tuple(g["head"]), tuple(g["j"])], 44.0),
        ([tuple(g["j"]), tuple(g["end"] - 20.0 * g["d"])], 74.0),
        ([tuple(g["thead"] + 150.0 * g["td"]), tuple(g["j"])], 30.0),
    ])
    write_domain(work / "domain.geojson", domain)
    return work


def junction_lines(angle_deg: float) -> dict:
    """Result lines 500 m long across each reach: main above the junction, the tributary, main 500 m and 2,000 m
    below, and the outlet boundary 5 m inside the main's end."""
    g = junction_geometry(angle_deg)

    def across(p, d):
        nn = np.array([-d[1], d[0]])
        return [list(p - 240.0 * nn), list(p + 240.0 * nn)]

    return {
        "lines": {
            "main_up": across(g["j"] - 700.0 * g["d"], g["d"]),
            "trib": across(g["j"] - 700.0 * g["td"], g["td"]),
            "main_dn": across(g["j"] + 700.0 * g["d"], g["d"]),
            "outlet": across(g["end"] - 300.0 * g["d"], g["d"]),
        },
        "boundary": across(g["end"] - 5.0 * g["d"], g["d"]),
        "main_in": list(g["head"] + 300.0 * g["d"]),
        "trib_in": list(g["thead"] + 300.0 * g["td"]),
    }


# ---------------------------------------------------------------- the straight valley turned off the lattice


def rotated_frame(angle_deg: float) -> dict:
    """W48's straight narrow valley (8.4 by 1 km, the axis down its middle) turned about the axis's upstream end."""
    a = np.radians(angle_deg)
    d = np.array([np.cos(a), np.sin(a)])
    n = np.array([-d[1], d[0]])
    origin = np.array([wp.X0, wp.Y0 + wp.WIDTH / 2])
    return dict(d=d, n=n, o=origin)


def rotated_ground(case: str, angle_deg: float) -> Path:
    from shapely.geometry import Polygon

    work = HERE / "ground" / case
    work.mkdir(parents=True, exist_ok=True)
    f = rotated_frame(angle_deg)
    half = wp.WIDTH / 2
    corners = [f["o"] + s * f["d"] + t * f["n"] for s, t in ((0, -half), (wp.LENGTH, -half), (wp.LENGTH, half), (0, half))]
    poly = Polygon(corners)
    minx, miny, maxx, maxy = poly.bounds
    x0, y0 = np.floor(minx / 10) * 10 - 20, np.floor(miny / 10) * 10 - 20
    ncols, nrows = int((np.ceil(maxx / 10) * 10 + 20 - x0) / PIXEL), int((np.ceil(maxy / 10) * 10 + 20 - y0) / PIXEL)

    def z(px, py):
        rx, ry = px - f["o"][0], py - f["o"][1]
        s = rx * f["d"][0] + ry * f["d"][1]
        t = rx * f["n"][0] + ry * f["n"][1]
        return 200.0 - s * wp.S_BED + section(t, NARROW["bed_half"])

    t0 = time.perf_counter()
    write_dem(work / "dem.tif", x0, y0, ncols, nrows, z)
    print(f"{case}: DEM {ncols} x {nrows} in {time.perf_counter() - t0:.0f} s")
    line = [tuple(f["o"] + s * f["d"]) for s in np.arange(wp.THALWEG_FROM, wp.THALWEG_TO + 1.0, 10.0)]
    write_lines(work / "thalweg.gpkg", [(line, 74.0)])
    write_domain(work / "domain.geojson", poly)
    return work


def rotated_lines(angle_deg: float, sections: dict) -> dict:
    f = rotated_frame(angle_deg)
    half = wp.WIDTH / 2 + 10.0

    def across(s):
        p = f["o"] + s * f["d"]
        return [list(p - half * f["n"]), list(p + half * f["n"])]

    return {"lines": {n: across(s) for n, s in sections.items()}, "boundary": across(wp.LENGTH - 5.0)}


def split_grid(work: Path, dem: Path, angle_deg: float, where: str, near_m: float = 30.0) -> Path:
    """A storm depth grid at 10 m over a straight valley's DEM (on the lattice at angle 0, turned otherwise): 70 mm
    within `near_m` of the axis ('near', the bed, walls and ledge) or beyond it ('hills'), nothing elsewhere."""
    import rasterio
    from rasterio.transform import from_origin

    path = work / f"split_{where}_{int(angle_deg)}.tif"
    if path.is_file():
        return path
    with rasterio.open(dem) as src:
        b = src.bounds
    f = rotated_frame(angle_deg)
    step = 10.0
    ncols, nrows = int(np.ceil((b.right - b.left) / step)), int(np.ceil((b.top - b.bottom) / step))
    x = b.left + (np.arange(ncols) + 0.5) * step
    y = b.top - (np.arange(nrows) + 0.5) * step
    px, py = np.meshgrid(x, y)
    t = (px - f["o"][0]) * f["n"][0] + (py - f["o"][1]) * f["n"][1]
    near = np.abs(t) <= near_m
    z = np.where(near if where == "near" else ~near, 70.0, 0.0).astype(np.float32)
    work.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", height=nrows, width=ncols, count=1, dtype="float32", crs=CRS, nodata=-9999.0,
                       transform=from_origin(b.left, b.top, step, step)) as dst:
        dst.write(z, 1)
    return path


# ---------------------------------------------------------------- the plain

PLAIN_AMP = 50.0
PLAIN_FROM, PLAIN_RAMP, PLAIN_LEN, PLAIN_HALF = 3_000.0, 300.0, 1_400.0, 150.0
FLOOR_FALL = 0.005


def plain_half(s: np.ndarray) -> np.ndarray:
    a = np.clip((s - PLAIN_FROM) / PLAIN_RAMP, 0.0, 1.0)
    b = np.clip((PLAIN_FROM + 2 * PLAIN_RAMP + PLAIN_LEN - s) / PLAIN_RAMP, 0.0, 1.0)
    w = np.minimum(a, b)
    w = 0.5 - 0.5 * np.cos(np.pi * w)
    return NARROW["bed_half"] + (PLAIN_HALF - NARROW["bed_half"]) * w


def plain_ground(case: str) -> Path:
    from scipy.spatial import cKDTree
    from shapely.geometry import Polygon

    work = HERE / "ground" / case
    work.mkdir(parents=True, exist_ok=True)
    pts, arc = wp.curve(PLAIN_AMP)
    tree = cKDTree(pts)

    def z(px, py):
        s, t = wp.frame(px, py, pts, arc, tree)
        bh = plain_half(s)
        fall = np.where(bh > NARROW["bed_half"] + 1.0, FLOOR_FALL, 0.0)
        return 200.0 - s * wp.S_BED + section(t, bh, fall)

    t0 = time.perf_counter()
    write_dem(work / "dem.tif", wp.X0, wp.Y0, int(wp.LENGTH / PIXEL), int(wp.WIDTH / PIXEL), z)
    print(f"{case}: DEM in {time.perf_counter() - t0:.0f} s")
    keep = (pts[:, 0] >= wp.X0 + wp.THALWEG_FROM) & (pts[:, 0] <= wp.X0 + wp.THALWEG_TO)
    write_lines(work / "thalweg.gpkg", [([tuple(p) for p in pts[keep][::10]], 74.0)])
    ring = [(wp.X0, wp.Y0), (wp.X0 + wp.LENGTH, wp.Y0), (wp.X0 + wp.LENGTH, wp.Y0 + wp.WIDTH), (wp.X0, wp.Y0 + wp.WIDTH)]
    write_domain(work / "domain.geojson", Polygon(ring))
    return work
