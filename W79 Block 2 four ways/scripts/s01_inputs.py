"""Inputs shared by the four runs: the domain to the sea, the sea boundary, the Manning raster, the five dams.

- Domain: the 104 subbasin polygons of his Basin 3 (the HMS Block 2 model, 1,370.8 km2), joined, +40 m, holes filled,
  plus the strip between their seaward edge and W12's coastline (the polygons stop 0.1 to 2.6 km short of it). The
  existing Block 2 jobs (W1, W41, W49) stop at a box 5 to 13 km short of the coast, so this domain is new.
- Sea boundary: W12's coastline where the domain meets it, `normal` at 0.003 as in W12.
- Manning: W1's rule (s07_manning_rasters.py, the hills_100 raster of its full-2D jobs) on the new domain: 0.1 on the
  18 hill subbasins off the wadis, 0.04 on wadis of 1 km2 and more and on the whole plain.
- Dams, levels on the GGC terrain of the runs:
  - Bidah 03 and Faydh 01: W1's crest lines, dikes and spillway (dams.py, from the dam team's Dams.shp and Dikes.shp), the
    dam team's levels on NSA moved up by 2.39 m (W1's measured GGC-NSA offset in both reservoirs).
  - R5A, R2A, Z4C: the axes of Det_Design_DAMS.shp as W1 extended them to high ground, levels of Basin 3 (spillway crest
    where the HMS outflow table leaves zero, dam crest where it jumps), not moved: their HMS tables were cut from the
    HDSM itself (W14 of the Block 02 session), and the table bottoms lie 0.1 to 0.5 m above the GGC bed on the axis.
  - Spillways centred on the thalweg of each branch; R2A and R5A have two chutes on two wadi branches (80 + 90 m and
    150 + 115 m in the 2014 reports), scaled to the net length the tables use (160 and 250 m) [Guessing: which chute
    is on which branch is not on disk; the longer is put on the deeper bed].
  - Each crest line is carried on along its end segment until the ground stands 0.5 m above the crest (W1's tie).
- Per dam: the pool at crest + 0.3 m (under the 0.5 m tie) on the 5 m DEM behind the crest lines, and a line round its upstream edge (60 m
  out) that reads what flows into the pool on the grid; the point 200 m below the main thalweg where run 3 puts the
  reservoir's outflow on the grid; the DEM pool volume at the spillway crest against Basin 3's elevation-area table.

Writes inputs/domain.geojson, inputs/inputs.json, inputs/dams.geojson, inputs/dam_check.json and
runs/inputs/manning_hills_100.tif (a raster, not in git).
"""

from __future__ import annotations

import sys

import numpy as np
import rasterio
import rasterio.features
import shapely
import shapely.ops
from rasterio.transform import from_origin
from rasterio.windows import from_bounds
from scipy import ndimage
from shapely.geometry import LineString, Point, mapping, shape
from shapely.geometry.polygon import orient

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from w79 import (  # noqa: E402
    ACC,
    AXES_SHP,
    BASIN,
    COAST_JOB,
    DAMS,
    DEM,
    DEM5,
    GGC_MINUS_NSA,
    HMS_DIR,
    INPUTS,
    RUNS,
    load_json,
    w1_path,
    write_json,
)

from wadi2d.config.schema import Hydrology  # noqa: E402
from wadi2d.forcing import load_polygons  # noqa: E402
from wadi2d.hms import load_basin, load_pdata  # noqa: E402
from wadi2d.hydrology.from_hms import load_project_tables  # noqa: E402

w1_path()
from common import AXES as W1_AXES  # noqa: E402  (W1's common, imported through its folder)
from dams import BIDAH, FAYDH  # noqa: E402

SEA_REACH_M = 50.0
SEA_GAP_M = 3000.0
SEA_SLOPE = 0.003
POOL_ABOVE_CREST = 0.3
RING_OUT_M = 60.0
RING_CUT_M = 100.0
ENTRY_BELOW_M = 200.0
TIE_ABOVE = 0.5
HILLS = [f"S{i}" for i in range(1, 19)]
N_HILL, N_WADI, WADI_KM2, MANNING_PIX = 0.1, 0.04, 1.0, 10.0


def _sqlite():
    return HMS_DIR / BASIN.replace(".basin", ".sqlite")


def basin_polygons() -> dict[str, shapely.Geometry]:
    h = Hydrology(hms_basin=str(HMS_DIR / BASIN), hms_sqlite=str(_sqlite()))
    return {k: shapely.make_valid(v).buffer(0) for k, v in load_polygons(h).items()}


def _coast() -> LineString:
    return LineString(load_json(COAST_JOB)["boundaries"][0]["coordinates"])


def _single(geom) -> shapely.Polygon:
    if geom.geom_type != "Polygon":
        parts = sorted(geom.geoms, key=lambda g: g.area, reverse=True)
        print("domain pieces dropped, km2:", [round(g.area / 1e6, 3) for g in parts[1:]])
        geom = parts[0]
    return shapely.Polygon(geom.exterior)


def make_domain(polys) -> tuple[shapely.Polygon, LineString]:
    """Basin 3's polygons + 40 m, and the strip between their seaward edge and W12's coastline: the polygons stop
    0.1 to 2.6 km short of the coast, so without the strip there is no sea to drain to."""
    land = _single(shapely.union_all([p.buffer(1.0) for p in polys.values()]).buffer(-1.0).buffer(40.0))
    coast = _coast()
    edge = land.exterior.intersection(coast.buffer(SEA_GAP_M))
    edge = shapely.line_merge(edge) if edge.geom_type == "MultiLineString" else edge
    edge = max(edge.geoms, key=lambda g: g.length) if hasattr(edge, "geoms") else edge
    a, b = edge.coords[0], edge.coords[-1]
    sa, sb = coast.project(Point(a)), coast.project(Point(b))
    sub = shapely.ops.substring(coast, min(sa, sb), max(sa, sb))
    back = list(sub.coords)[::-1] if sa < sb else list(sub.coords)
    strip = shapely.make_valid(shapely.Polygon(list(edge.coords) + back)).buffer(0)
    dom = _single(shapely.union_all([land, strip]).buffer(1.0).buffer(-1.0)).simplify(5.0)
    print("coast strip km2", round(dom.area / 1e6 - land.area / 1e6, 1), "coast km", round(sub.length / 1000, 1))
    return dom, sub


def sea_boundary(dom: shapely.Polygon, sub: LineString) -> list[list[tuple[float, float]]]:
    """The coast where the domain meets it, as W12's `normal` line."""
    line = sub.intersection(dom.buffer(SEA_REACH_M))
    pieces = list(line.geoms) if hasattr(line, "geoms") else [line]
    pieces = [p for p in pieces if p.length > 100.0]
    print("sea boundary km:", [round(p.length / 1000, 2) for p in pieces])
    return [[(float(x), float(y)) for x, y in p.coords] for p in pieces]


def manning_raster(dom, polys) -> str:
    with rasterio.open(DEM) as s:
        left, top, crs = s.transform.c, s.transform.f, s.crs
    b = dom.bounds
    col, row = int((b[0] - left) // MANNING_PIX), int((top - b[3]) // MANNING_PIX)
    x0, y0 = left + col * MANNING_PIX, top - row * MANNING_PIX
    nx, ny = int(np.ceil((b[2] - x0) / MANNING_PIX)) + 1, int(np.ceil((y0 - b[1]) / MANNING_PIX)) + 1
    t = from_origin(x0, y0, MANNING_PIX, MANNING_PIX)
    hills = rasterio.features.rasterize(
        [polys[n] for n in HILLS], out_shape=(ny, nx), transform=t, fill=0, default_value=1, dtype="uint8"
    ).astype(bool)
    wadi = np.zeros((ny, nx), bool)
    with rasterio.open(ACC) as src:
        w = from_bounds(x0, y0 - ny * MANNING_PIX, x0 + nx * MANNING_PIX, y0, src.transform).round_offsets().round_lengths()
        a = src.read(1, window=w, masked=True).filled(0.0) * src.res[0] ** 2 * 1e-6
        tt = src.window_transform(w)
    r, c = np.nonzero(a >= WADI_KM2)
    xs, ys = tt.c + (c + 0.5) * tt.a, tt.f + (r + 0.5) * tt.e
    jj, ii = ((y0 - ys) // MANNING_PIX).astype(int), ((xs - x0) // MANNING_PIX).astype(int)
    ok = (jj >= 0) & (jj < ny) & (ii >= 0) & (ii < nx)
    wadi[jj[ok], ii[ok]] = True
    wadi = ndimage.binary_dilation(wadi, iterations=2)
    n = np.where(hills & ~wadi, N_HILL, N_WADI).astype(np.float32)
    out = RUNS / "inputs" / "manning_hills_100.tif"
    out.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out, "w", driver="GTiff", height=ny, width=nx, count=1, dtype="float32", crs=crs, transform=t,
                       compress="deflate") as d:
        d.write(n, 1)
    print("manning: hills off wadis km2", round((hills & ~wadi).sum() * MANNING_PIX**2 / 1e6, 1))
    return str(out)


# ---------------------------------------------------------------- dams

def _levels_from_table(name: str, tables) -> tuple[float, float]:
    """Spillway crest: the last level of zero outflow; dam crest: the level after which the table's step jumps."""
    q = tables.paired[f"Elev-Dis {name}"]
    x, y = np.asarray(q.x, float), np.asarray(q.y, float)
    fsl = float(x[np.nonzero(y > 0.0)[0][0] - 1])
    jump = np.diff(y) / np.diff(x)
    above = np.nonzero(x[:-1] >= fsl)[0]
    k = above[np.argmax(np.diff(jump[above])) + 1]
    return fsl, float(x[k])


def _axes_shp() -> dict:
    import fiona

    out = {}
    with fiona.open(AXES_SHP) as src:
        for f in src:
            p = dict(f["properties"])
            out[{"R5": "R5A"}.get(p["DAM"], p["DAM"])] = p
    return out


def _sample(src, pts) -> np.ndarray:
    z = np.array([v[0] for v in src.sample([(float(x), float(y)) for x, y in pts])], float)
    z[(z > 1e30) | (z < -1000.0)] = np.nan
    return z


def tie(lines, crest: float, step: float = 5.0, reach: float = 400.0):
    """W1's tie on the GGC terrain: each open end carried on along its last segment until the ground passes crest + 0.5."""
    out = []
    with rasterio.open(DEM) as src:
        for line in lines:
            pts = [tuple(map(float, p)) for p in line]
            for end in (0, -1):
                a, b = (pts[1], pts[0]) if end == 0 else (pts[-2], pts[-1])
                v = np.array(b) - np.array(a)
                v = v / np.hypot(*v)
                if _sample(src, [b])[0] >= crest + TIE_ABOVE:
                    continue
                for s in np.arange(step, reach, step):
                    q = np.array(b) + s * v
                    if _sample(src, [q])[0] >= crest + TIE_ABOVE:
                        pts = [tuple(map(float, q))] + pts if end == 0 else pts + [tuple(map(float, q))]
                        break
            out.append(pts)
    return out


def _thalwegs(axis: LineString, count: int) -> list[float]:
    """Stations of the ``count`` deepest valleys along the axis on the 5 m DEM, deepest first."""
    from scipy.signal import find_peaks

    ss = np.arange(0.0, axis.length, 5.0)
    with rasterio.open(DEM5) as src:
        z = _sample(src, [axis.interpolate(s).coords[0] for s in ss])
    pk, _ = find_peaks(-np.nan_to_num(z, nan=1e4), prominence=10.0, distance=40)
    pk = sorted(pk, key=lambda i: z[i])[:count]
    return [float(ss[i]) for i in pk]


def _segment(axis: LineString, s: float, length: float) -> list[tuple[float, float]]:
    a, b = max(s - length / 2.0, 0.0), min(s + length / 2.0, axis.length)
    return [axis.interpolate(a).coords[0], axis.interpolate(b).coords[0]]


def dam_defs(tables) -> dict:
    axes = _axes_shp()
    defs = {}
    for dam in (BIDAH, FAYDH):
        crest = dam.crest + GGC_MINUS_NSA
        defs[dam.name] = {
            "fsl": dam.fsl + GGC_MINUS_NSA, "crest": crest, "shift": GGC_MINUS_NSA, "c": dam.c,
            "crest_lines": tie(dam.crest_lines, crest),
            "spillways": [{"coordinates": [tuple(map(float, p)) for p in dam.spillway], "length": dam.spill_len}],
            "axis": [tuple(map(float, p)) for p in dam.axis_line],
            "source": "W1 dams.py from the dam team's Dams.shp and Dikes.shp; levels NSA + 2.39 m",
        }
    chutes = {"R2A": (90.0, 80.0), "R5A": (150.0, 115.0), "Z4C": (220.0,)}
    for name in ("R5A", "R2A", "Z4C"):
        fsl, crest = _levels_from_table(name, tables)
        p = axes[name]
        if abs(fsl - p["FSL_M"]) > 0.01 or abs(crest - p["CREST_M"]) > 0.01:
            raise SystemExit(f"{name}: Basin 3 table gives {fsl}/{crest}, the dam sheet {p['FSL_M']}/{p['CREST_M']}")
        axis = LineString(W1_AXES[name])
        net = float(p["SP_L_M"])
        parts = chutes[name]
        stations = _thalwegs(axis, len(parts))
        spill = [
            {"coordinates": _segment(axis, s, net * part / sum(parts)), "length": net * part / sum(parts)}
            for s, part in zip(stations, parts, strict=True)
        ]
        defs[name] = {
            "fsl": fsl, "crest": crest, "shift": 0.0, "c": float(p["SP_C"]),
            "crest_lines": tie([W1_AXES[name]], crest),
            "spillways": spill,
            "axis": [tuple(map(float, q)) for q in W1_AXES[name]],
            "source": "Det_Design_DAMS.shp axis as W1 extended it; levels of Basin 3's tables (GGC)",
        }
    return defs


def _window(geom, pad=5000.0):
    with rasterio.open(DEM5) as src:
        b = geom.bounds
        w = from_bounds(b[0] - pad, b[1] - pad, b[2] + pad, b[3] + pad, src.transform).round_offsets().round_lengths()
        w = w.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
        z = src.read(1, window=w, masked=True).astype(float).filled(np.nan)
        return z, src.window_transform(w)


def pool(defn: dict, level: float, z, t):
    """The pool behind the crest lines at ``level``: label of the side that does not reach the window's edge."""
    wall = rasterio.features.rasterize(
        [LineString(c).buffer(6.0) for c in defn["crest_lines"]], out_shape=z.shape, transform=t, fill=0,
        default_value=1, dtype="uint8", all_touched=True,
    ).astype(bool)
    wet = (z < level) & ~wall & np.isfinite(z)
    lab, _ = ndimage.label(wet)
    edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])))
    sp = LineString(defn["spillways"][0]["coordinates"])
    mid = sp.interpolate(0.5, normalized=True)
    (x0, y0), (x1, y1) = sp.coords[0], sp.coords[-1]
    nrm = np.array([-(y1 - y0), x1 - x0]) / sp.length
    found = {}
    for sign in (1.0, -1.0):
        for d in (30.0, 45.0, 60.0, 80.0):
            px, py = mid.x + sign * d * nrm[0], mid.y + sign * d * nrm[1]
            r, c = rasterio.transform.rowcol(t, px, py)
            if 0 <= r < z.shape[0] and 0 <= c < z.shape[1] and lab[r, c] > 0:
                found[sign] = int(lab[r, c])
                break
    inside = [s for s, k in found.items() if k not in edge]
    if len(inside) != 1:
        raise SystemExit(f"{defn['name']}: pool at {level:.2f} m not closed on exactly one side ({found}, edge {len(edge)})")
    up = inside[0]
    return lab == found[up], up, nrm, mid


def table_volume(name: str, tables, level: float) -> float:
    a = tables.paired[f"Elev-Area {name}"]
    x, y = np.asarray(a.x, float), np.asarray(a.y, float)
    keep = x <= level
    xs, ys = np.append(x[keep], level), np.append(y[keep], np.interp(level, x, y))
    return float(np.trapezoid(ys, xs))


def entry_point(mid: Point, nrm, up: float, z, t, axis: LineString) -> tuple[float, float]:
    """200 m below the main thalweg, then down the steepest 5 m pixel for at most 60 m."""
    px, py = mid.x - up * ENTRY_BELOW_M * nrm[0], mid.y - up * ENTRY_BELOW_M * nrm[1]
    r, c = rasterio.transform.rowcol(t, px, py)
    for _ in range(12):
        win = z[r - 1:r + 2, c - 1:c + 2]
        k = np.nanargmin(win)
        dr, dc = divmod(int(k), 3)
        if dr == 1 and dc == 1:
            break
        r, c = r + dr - 1, c + dc - 1
    x, y = rasterio.transform.xy(t, r, c)
    if axis.distance(Point(x, y)) < 150.0:
        raise SystemExit(f"entry point {x:.0f}, {y:.0f} lies {axis.distance(Point(x, y)):.0f} m from the dam line")
    return float(x), float(y)


def ring(mask, t, crest_lines) -> list[tuple[float, float]]:
    shapes = [shape(g) for g, v in rasterio.features.shapes(mask.astype("uint8"), mask=mask, transform=t) if v == 1]
    poly = shapely.union_all(shapes).buffer(RING_OUT_M)
    if poly.geom_type != "Polygon":
        poly = max(poly.geoms, key=lambda g: g.area)
    ext = orient(shapely.Polygon(poly.exterior), sign=-1.0).simplify(10.0)  # clockwise: the pool on the right
    coords = list(ext.exterior.coords)[:-1]
    cut = shapely.union_all([LineString(c).buffer(RING_CUT_M) for c in crest_lines])
    start = next(i for i, p in enumerate(coords) if cut.contains(Point(p)))
    coords = coords[start:] + coords[:start + 1]
    kept = LineString(coords).difference(cut)
    parts = list(kept.geoms) if hasattr(kept, "geoms") else [kept]
    best = max(parts, key=lambda g: g.length)
    return [(float(x), float(y)) for x, y in best.coords]


def main() -> None:
    INPUTS.mkdir(parents=True, exist_ok=True)
    polys = basin_polygons()
    model = load_basin(HMS_DIR / BASIN)
    area_hms = float(sum(e.area for e in model.subbasins.values()))
    dom, coast = make_domain(polys)
    write_json(INPUTS / "domain.geojson", {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": "Block 2 to the sea (Basin 3)"}, "geometry": mapping(dom)}]})
    print("domain km2", round(dom.area / 1e6, 1), "HMS area km2", round(area_hms, 2))
    sea = sea_boundary(dom, coast)
    manning = manning_raster(dom, polys)
    stem = HMS_DIR / "HEC_HMS_Block_02"
    tables = load_project_tables(load_pdata(stem.with_suffix(".pdata")), stem.with_suffix(".dss"))
    defs = dam_defs(tables)
    feats, check = [], {}
    for name in DAMS:
        d = defs[name]
        d["name"] = name
        z, t = _window(LineString(d["axis"]))
        top, up, nrm, mid = pool(d, d["crest"] + POOL_ABOVE_CREST, z, t)
        at_fsl, _, _, _ = pool(d, d["fsl"], z, t)
        cell = abs(t.a * t.e)
        vol_dem = float(np.nansum(np.where(at_fsl, d["fsl"] - z, 0.0)) * cell)
        vol_tab = table_volume(name, tables, d["fsl"] - d["shift"])
        d["ring"] = ring(top, t, d["crest_lines"])
        d["entry"] = entry_point(mid, nrm, up, z, t, LineString(d["axis"]))
        check[name] = {
            "fsl_ggc": d["fsl"], "crest_ggc": d["crest"], "shift_m": d["shift"],
            "pool_volume_at_fsl_dem_Mm3": vol_dem / 1e6, "pool_volume_at_fsl_table_Mm3": vol_tab / 1e6,
            "dem_over_table": vol_dem / vol_tab, "pool_area_crest_plus_3_km2": float(top.sum() * cell / 1e6),
            "ring_m": LineString(d["ring"]).length, "entry": d["entry"],
            "spillways": [{"length": s["length"], "centre": LineString(s["coordinates"]).interpolate(0.5, True).coords[0]}
                          for s in d["spillways"]],
            "source": d["source"],
        }
        print(name, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in check[name].items() if k != "spillways"})
        for i, c in enumerate(d["crest_lines"]):
            feats.append({"type": "Feature", "properties": {"dam": name, "kind": "crest_line", "z": d["crest"], "part": i},
                          "geometry": mapping(LineString(c))})
        for i, s in enumerate(d["spillways"]):
            feats.append({"type": "Feature", "properties": {"dam": name, "kind": "spillway", "z": d["fsl"], "part": i,
                                                            "length": s["length"], "c": d["c"]},
                          "geometry": mapping(LineString(s["coordinates"]))})
        feats.append({"type": "Feature", "properties": {"dam": name, "kind": "dam_line"}, "geometry": mapping(LineString(d["axis"]))})
        feats.append({"type": "Feature", "properties": {"dam": name, "kind": "inflow_ring"}, "geometry": mapping(LineString(d["ring"]))})
        feats.append({"type": "Feature", "properties": {"dam": name, "kind": "outflow_entry_run3"}, "geometry": mapping(Point(d["entry"]))})
        shapes = [shape(g) for g, v in rasterio.features.shapes(top.astype("uint8"), mask=top, transform=t) if v == 1]
        feats.append({"type": "Feature", "properties": {"dam": name, "kind": f"pool_crest_plus_{POOL_ABOVE_CREST:g}m"},
                      "geometry": mapping(shapely.union_all(shapes).simplify(5.0))})
    write_json(INPUTS / "dams.geojson", {"type": "FeatureCollection", "features": feats})
    write_json(INPUTS / "dam_check.json", check)
    write_json(INPUTS / "inputs.json", {
        "domain": str(INPUTS / "domain.geojson"), "domain_km2": dom.area / 1e6, "hms_area_km2": area_hms,
        "sea": sea, "sea_slope": SEA_SLOPE, "manning_raster": manning,
        "dams": {n: {k: defs[n][k] for k in ("fsl", "crest", "shift", "c", "crest_lines", "spillways", "axis", "ring", "entry")}
                 for n in DAMS},
    })


if __name__ == "__main__":
    main()
