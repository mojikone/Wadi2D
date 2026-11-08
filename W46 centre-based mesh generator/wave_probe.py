"""An unsteady flood wave down a long sinuous channel on synthetic ground, through the real engine (W46, 2026-11-08).

Every probe before this one measured steady flow, where mass conservation fixes the discharge and only the depth can
be wrong; the Faydh race measures a flood peak, a dynamic quantity. Here a triangular hydrograph enters at the head
of an 8.4 km valley whose centreline is a sine wave (amplitude 150 m, wavelength 1,200 m, radius 243 m at the bends)
and the peak is read at three sections across the whole valley, 1.5, 4.5 and 7.5 km down, with no rain, so the
routing alone is on trial. Two grounds, each from one section translated along the curve on a 0.5 m DEM:

* gorge: a channel 40 m wide and 3 m deep with 2:1 banks, a floodplain 80 m each side at 1.5 %, hills at 25 %; the
  floor rule puts the bank at the channel lip, so the aligned cells are the channel's own rows and the floodplain is
  squares, as on Faydh;
* plain: a shallow wadi 60 m wide and 0.8 m deep with 4:1 banks (under the 1 m scarp and the 2 m rise), a floodplain
  100 m each side at 0.8 %, hills at 25 %; the floor reaches the hill toe, so the aligned rows cover the floodplain.

Meshes: squares at 20, 10 and 5 m and the centre mesh at 20 and 10 m; the 5 m squares are the reference. Read: the
peak and its time at each section, the width of the hydrograph at half its peak at the last section, the wet area,
the steps and the wall time.

    .venv\\Scripts\\python "W46 centre-based mesh generator\\wave_probe.py" <gorge|plain|straight|skew|pools> [ground|build|run|report|all]
        [wave|sharp|rain|rain_all|rain_near|rain_hills] [sq20 ce20 sq10 ce10 sq5 ...]
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = Path(__file__).resolve().parent / "probe_wave"
CRS = "EPSG:32640"
X0, Y0 = 400_000.0, 2_700_000.0
LENGTH, WIDTH, PIXEL = 8_400.0, 1_000.0, 0.5
AMP, WAVE = 150.0, 1_200.0
S_BED = 0.01
MANNING = 0.05
INFLOW_S = 300.0
THALWEG_FROM, THALWEG_TO = 800.0, 7_800.0
SECTIONS = {"s1": 1_500.0, "s2": 4_500.0, "s3": 7_500.0}
DURATION_S = 21_600.0
WET_M = 0.1
FORCINGS = {
    # the first wave, a 1.5 h rise and a 2.5 h fall, hardly attenuates over 7 km (1.6 %), so no mesh could show on it
    "wave": dict(times_s=[0.0, 1_800.0, 7_200.0, 16_200.0, 21_600.0], flows=[50.0, 50.0, 1_500.0, 50.0, 50.0]),
    # a flash flood: 20 min up, 40 min down, about the half-peak width of Faydh's own hydrograph (50 min)
    "sharp": dict(times_s=[0.0, 1_800.0, 3_000.0, 5_400.0, 21_600.0], flows=[50.0, 50.0, 1_500.0, 50.0, 50.0]),
    # a steady 300 m3/s for 4 h: the level each construction holds at the same discharge, against the normal depth
    "steady": dict(times_s=[0.0, 3_600.0, 21_600.0], flows=[0.0, 300.0, 300.0]),
    # rain on the whole valley, hills included, a burst of 30 mm in 20 min inside 70 mm in 4 h, as Faydh's storm has
    "rain": dict(hyetograph_min=[60.0, 120.0, 125.0, 130.0, 135.0, 140.0, 200.0, 240.0], hyetograph_mm=[4.0, 8.0, 7.0, 8.0, 8.0, 7.0, 18.0, 10.0]),
    # the same rain as a hypothetical storm with a depth grid: everywhere, within NEAR_M of the thalweg only, or
    # beyond it only; the run hands the strip its cells' own rates by position, so both meshes get the same water
    "rain_all": dict(grid=None),
    "rain_near": dict(grid="near"),
    "rain_hills": dict(grid="hills"),
}

CASES = {
    "gorge": dict(bed_half=20.0, bank_run=6.0, depth=3.0, plain_w=80.0, plain_slope=0.015, hill=0.25, amp=AMP),
    "plain": dict(bed_half=30.0, bank_run=3.2, depth=0.8, plain_w=100.0, plain_slope=0.008, hill=0.25, amp=AMP),
    # the gorge section down a straight valley along the lattice: the squares have no staircase there
    "straight": dict(bed_half=20.0, bank_run=6.0, depth=3.0, plain_w=80.0, plain_slope=0.015, hill=0.25, amp=0.0),
    # the gorge again, but the guide line given to the mesher wobbles 30 m either side of the true centreline every
    # 400 m, so the strip's station faces stand up to 25 degrees off the flow, as a smoothed D8 thalweg does on a
    # real channel; the ground is the gorge's
    "skew": dict(bed_half=20.0, bank_run=6.0, depth=3.0, plain_w=80.0, plain_slope=0.015, hill=0.25, amp=AMP, wobble=(30.0, 400.0)),
    # the gorge with pools: the bed widens from 40 to 80 m and back every 300 m along the valley, so the flood meets
    # an expansion and a contraction every 300 m, where the momentum advection terms work and a prismatic channel
    # never exercises them
    "pools": dict(bed_half=20.0, bank_run=6.0, depth=3.0, plain_w=80.0, plain_slope=0.015, hill=0.25, amp=AMP, pools=(20.0, 300.0)),
}
NEAR_M = 200.0
"""Rain 'near' falls within this distance of the thalweg (the pair, the band and the nearest squares), 'hills' beyond."""
# the hyetograph as the hypothetical storm's cumulative pattern: 70 mm in 240 min, 30 mm of it in the 20 min after 2 h
PATTERN_T = [0.0, 25.0, 50.0, 52.0833, 54.1667, 56.25, 58.3333, 83.3333, 100.0]
PATTERN_D = [0.0, 5.7143, 17.1429, 27.1429, 38.5714, 50.0, 60.0, 85.7143, 100.0]
MESHES = {"sq20": (20.0, False), "ce20": (20.0, True), "sq10": (10.0, False), "ce10": (10.0, True), "sq5": (5.0, False)}


def section(t: np.ndarray, c: dict, s: np.ndarray | None = None) -> np.ndarray:
    """Height of the ground above the thalweg bed at signed across-distance t; with pools, the bed's half-width
    swings with the along-coordinate s."""
    a = np.abs(t)
    bed_half = c["bed_half"]
    if c.get("pools") and s is not None:
        extra, wave_p = c["pools"]
        bed_half = c["bed_half"] + 0.5 * extra * (1.0 + np.sin(2 * np.pi * s / wave_p))
    bank_top = bed_half + c["bank_run"]
    plain_edge = bank_top + c["plain_w"]
    h = np.where(a < bed_half, 0.0, (a - bed_half) / c["bank_run"] * c["depth"])
    h = np.where(a >= bank_top, c["depth"] + (a - bank_top) * c["plain_slope"], h)
    h = np.where(a >= plain_edge, c["depth"] + c["plain_w"] * c["plain_slope"] + (a - plain_edge) * c["hill"], h)
    return h


def centreline(x: np.ndarray, amp: float) -> np.ndarray:
    return Y0 + WIDTH / 2 + amp * np.sin(2 * np.pi * (x - X0) / WAVE)


def curve(amp: float) -> tuple[np.ndarray, np.ndarray]:
    """The centreline at 1 m, extended 500 m past both ends so the frame is sound at the domain edges; and its arc."""
    x = np.arange(X0 - 500.0, X0 + LENGTH + 500.0 + 0.5, 1.0)
    pts = np.column_stack((x, centreline(x, amp)))
    seg = np.diff(pts, axis=0)
    arc = np.concatenate(([0.0], np.cumsum(np.hypot(seg[:, 0], seg[:, 1]))))
    return pts, arc


def frame(px: np.ndarray, py: np.ndarray, pts: np.ndarray, arc: np.ndarray, tree) -> tuple[np.ndarray, np.ndarray]:
    """Arc length along and signed distance across the centreline of points, by the nearest curve vertex."""
    q = np.column_stack((np.ravel(px), np.ravel(py)))
    d, k = tree.query(q)
    k = np.clip(k, 1, pts.shape[0] - 2)
    tang = pts[k + 1] - pts[k - 1]
    tang /= np.maximum(np.hypot(tang[:, 0], tang[:, 1]), 1e-12)[:, None]
    rel = q - pts[k]
    side = np.sign(-rel[:, 0] * tang[:, 1] + rel[:, 1] * tang[:, 0])
    return arc[k].reshape(np.shape(px)), (side * d).reshape(np.shape(px))


def point_at(s: float, pts: np.ndarray, arc: np.ndarray) -> tuple[float, float]:
    """The centreline point at along-coordinate s, measured from the domain's upstream edge."""
    k = int(np.argmin(np.abs(pts[:, 0] - (X0 + s))))
    return float(pts[k, 0]), float(pts[k, 1])


def ground(case: str) -> Path:
    """Write the DEM, the thalweg file and the domain polygon of a case."""
    import fiona
    import rasterio
    from rasterio.transform import from_origin
    from rasterio.windows import Window
    from scipy.spatial import cKDTree
    from shapely.geometry import LineString, Polygon, mapping

    c = CASES[case]
    work = OUT / case
    work.mkdir(parents=True, exist_ok=True)
    pts, arc = curve(c["amp"])
    tree = cKDTree(pts)
    ncols, nrows = int(LENGTH / PIXEL), int(WIDTH / PIXEL)
    top = Y0 + WIDTH
    x = X0 + (np.arange(ncols) + 0.5) * PIXEL
    dem = work / "dem.tif"
    dem.unlink(missing_ok=True)
    t0 = time.perf_counter()
    profile = dict(driver="GTiff", height=nrows, width=ncols, count=1, dtype="float32", crs=CRS, nodata=-9999.0,
                   transform=from_origin(X0, top, PIXEL, PIXEL), compress="deflate", tiled=True, blockxsize=512, blockysize=512)
    with rasterio.open(dem, "w", **profile) as dst:
        chunk = 100
        for r0 in range(0, nrows, chunk):
            r1 = min(nrows, r0 + chunk)
            y = top - (np.arange(r0, r1) + 0.5) * PIXEL
            px, py = np.meshgrid(x, y)
            s, t = frame(px, py, pts, arc, tree)
            z = 200.0 - s * S_BED + section(t, c, s)
            dst.write(z.astype(np.float32), 1, window=Window(0, r0, ncols, r1 - r0))
    print(f"{case}: DEM {ncols} x {nrows} pixels at {PIXEL} m written in {time.perf_counter() - t0:.0f} s")
    keep = (pts[:, 0] >= X0 + THALWEG_FROM) & (pts[:, 0] <= X0 + THALWEG_TO)
    line = pts[keep][::10]
    if c.get("wobble"):
        amp_w, wave_w = c["wobble"]
        seg = np.gradient(line, axis=0)
        normal = np.column_stack((-seg[:, 1], seg[:, 0])) / np.maximum(np.hypot(seg[:, 0], seg[:, 1]), 1e-12)[:, None]
        arc_w = np.concatenate(([0.0], np.cumsum(np.hypot(*np.diff(line, axis=0).T))))
        line = line + normal * (amp_w * np.sin(2 * np.pi * arc_w / wave_w))[:, None]
    gpkg = work / "thalweg.gpkg"
    gpkg.unlink(missing_ok=True)
    with fiona.open(gpkg, "w", driver="GPKG", layer="thalwegs", crs=CRS,
                    schema={"geometry": "LineString", "properties": {"area_km2": "float", "incised_m": "float"}}) as dst:
        dst.write({"geometry": mapping(LineString(line)), "properties": {"area_km2": 74.0, "incised_m": c["depth"]}})
    with fiona.open(gpkg, "w", driver="GPKG", layer="breaklines", crs=CRS,
                    schema={"geometry": "LineString", "properties": {"kind": "str", "side": "str", "area_km2": "float"}}):
        pass
    ring = [(X0, Y0), (X0 + LENGTH, Y0), (X0 + LENGTH, top), (X0, top), (X0, Y0)]
    (work / "domain.geojson").write_text(json.dumps({
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {"name": case}, "geometry": mapping(Polygon(ring))}],
    }), encoding="utf-8")
    print(f"{case}: thalweg of {len(line)} points and domain written to {work}")
    return work


def depth_grid(case: str, where: str) -> Path:
    """A raster of storm depths in mm at 10 m: 70 within NEAR_M of the thalweg ('near') or beyond it ('hills')."""
    import rasterio
    from rasterio.transform import from_origin
    from scipy.spatial import cKDTree

    c = CASES[case]
    work = OUT / case
    path = work / f"depth_{where}.tif"
    if path.is_file():
        return path
    pts, arc = curve(c["amp"])
    step = 10.0
    ncols, nrows = int(LENGTH / step), int(WIDTH / step)
    x = X0 + (np.arange(ncols) + 0.5) * step
    y = Y0 + WIDTH - (np.arange(nrows) + 0.5) * step
    px, py = np.meshgrid(x, y)
    _s, t = frame(px, py, pts, arc, cKDTree(pts))
    near = np.abs(t) <= NEAR_M
    z = np.where(near if where == "near" else ~near, 70.0, 0.0).astype(np.float32)
    with rasterio.open(path, "w", driver="GTiff", height=nrows, width=ncols, count=1, dtype="float32", crs=CRS, nodata=-9999.0,
                       transform=from_origin(X0, Y0 + WIDTH, step, step)) as dst:
        dst.write(z, 1)
    return path


def name_of(case: str, forcing: str, mesh: str) -> str:
    return f"{case}_{mesh}" if forcing == "wave" else f"{case}_{forcing}_{mesh}"


def job(case: str, forcing: str, mesh: str) -> dict:
    dx, centres = MESHES[mesh]
    work = OUT / case
    pts, arc = curve(CASES[case]["amp"])
    xin, yin = point_at(INFLOW_S, pts, arc)
    f = FORCINGS[forcing]
    hydrology: dict = {}
    if "flows" in f:
        storm = {"kind": "none"}
        hydrology = {"inflows": [{"name": "head", "x": xin, "y": yin, "times_s": f["times_s"], "flows": f["flows"]}], "inject_radius": 60.0}
    elif "hyetograph_min" in f:
        storm = {"kind": "hyetograph", "hyetograph_min": f["hyetograph_min"], "hyetograph_mm": f["hyetograph_mm"]}
    else:
        storm = {"kind": "hypothetical", "depth_mm": 70.0, "duration_min": 240.0, "time_percent": PATTERN_T, "depth_percent": PATTERN_D}
        if f["grid"]:
            storm["depth_grid"] = str(depth_grid(case, f["grid"]))
    data = {
        "project": {"name": f"wave_{name_of(case, forcing, mesh)}", "description": "W46 unsteady wave probe: a flood down a sinuous synthetic valley"},
        "grid": {"dx": dx, "domain": str(work / "domain.geojson"), "cache_dir": str(work / "cache")},
        "terrain": {"dem": str(work / "dem.tif"), "pixel_stride": 1, "manning": MANNING},
        "storm": storm,
        "hydrology": hydrology,
        "boundaries": [{"kind": "normal", "slope": S_BED, "coordinates": [[X0 + LENGTH - 5.0, Y0], [X0 + LENGTH - 5.0, Y0 + WIDTH]]}],
        "outputs": {
            "map_every_s": 0.0, "series_every_s": 30.0, "live_every_s": 0.0,
            "lines": [{"name": n, "coordinates": [[X0 + s, Y0], [X0 + s, Y0 + WIDTH]]} for n, s in SECTIONS.items()],
            "pixels": {"enabled": False},
        },
        "run": {"duration_s": DURATION_S, "backend": "gpu", "source_every_s": 30.0, "checkpoint_every_s": 0.0},
    }
    if centres:
        data["strips"] = {"enabled": True, "generator": "centres", "banks": str(work / "thalweg.gpkg"), "along": dx}
    return data


def build(case: str, forcing: str, meshes: list[str]) -> None:
    work = OUT / case
    for mesh in meshes:
        (work / f"{name_of(case, forcing, mesh)}.json").write_text(json.dumps(job(case, forcing, mesh), indent=1), encoding="utf-8")
    print(f"{case} {forcing}: jobs written for {', '.join(meshes)}")


def run(case: str, forcing: str, mesh: str) -> None:
    work = OUT / case
    name = name_of(case, forcing, mesh)
    exe = ROOT / ".venv" / "Scripts" / "wadi2d.exe"
    t0 = time.perf_counter()
    done = subprocess.run([str(exe), "run", str(work / f"{name}.json"), "--out", str(work / name)], capture_output=True, text=True)
    (work / f"{name}.log").write_text(done.stdout + "\n" + done.stderr, encoding="utf-8")
    print(f"{name}: exit {done.returncode} in {time.perf_counter() - t0:.0f} s", flush=True)


def series(folder: Path, line: str) -> tuple[np.ndarray, np.ndarray]:
    rows = (folder / "series" / f"line_{line}.csv").read_text(encoding="utf-8").splitlines()[1:]
    t = np.array([float(r.split(",")[0]) for r in rows])
    q = np.abs(np.array([float(r.split(",")[1]) for r in rows]))
    return t, q


def half_width_min(t: np.ndarray, q: np.ndarray) -> float:
    """Minutes the hydrograph stands above half its peak."""
    above = q >= 0.5 * q.max()
    return float(above.sum() * np.median(np.diff(t)) / 60.0)


def wet_area_km2(folder: Path, dx: float) -> float:
    """Wet area over the valley between 1 and 8 km: lattice cells from the max mean depth raster, strip cells from
    the strip mesh file, both at the run's own wet threshold."""
    import rasterio

    with rasterio.open(folder / "maps" / "max_mean_depth.tif") as src:
        z = src.read(1)
        cols = np.arange(src.width)
        xs = src.transform.c + (cols + 0.5) * src.transform.a
    inside = (xs >= X0 + 1_000.0) & (xs <= X0 + 8_000.0)
    wet = (z > WET_M) & (z != src.nodata) & inside[None, :]
    area = float(wet.sum()) * dx * dx
    strip = folder / "maps" / "strip_mesh.gpkg"
    if strip.is_file():
        import fiona

        with fiona.open(strip, layer="strip_cells") as src:
            for f in src:
                p = f["properties"]
                xc = np.mean([c[0] for c in f["geometry"]["coordinates"][0][0]]) if f["geometry"]["type"] == "MultiPolygon" else np.mean([c[0] for c in f["geometry"]["coordinates"][0]])
                if (p["max_mean_depth_m"] or 0.0) > WET_M and X0 + 1_000.0 <= xc <= X0 + 8_000.0:
                    area += float(p["area_m2"])
    return area / 1e6


def report(case: str, forcing: str, meshes: list[str]) -> None:
    work = OUT / case
    out: dict = {}
    for mesh in meshes:
        folder = work / name_of(case, forcing, mesh)
        if not (folder / "progress.jsonl").is_file():
            print(f"{name_of(case, forcing, mesh)}: no run")
            continue
        lines = (folder / "progress.jsonl").read_text(encoding="utf-8").splitlines()
        done = [json.loads(s) for s in lines if '"done"' in s[:14]]
        built = [json.loads(s) for s in lines if '"ev": "strips"' in s]
        r: dict = {"dx": MESHES[mesh][0]}
        for name in SECTIONS:
            t, q = series(folder, name)
            r[name] = {"peak_m3s": float(q.max()), "at_h": float(t[q.argmax()] / 3600.0), "half_width_min": half_width_min(t, q)}
        r["attenuation_s3_s1"] = r["s3"]["peak_m3s"] / r["s1"]["peak_m3s"]
        if done:
            b = done[-1]["balance"]
            r |= {"steps": done[-1]["steps"], "loop_s": done[-1]["loop_s"], "mass_error": b["relative_error"],
                  "outflow_Mm3": b["outflow_m3"] / 1e6, "storage_end_Mm3": b["storage_end_m3"] / 1e6}
        if built:
            s = built[-1]
            r["strips"] = {k: s.get(k) for k in ("cells", "triangles", "replaced")}
        try:
            r["wet_km2"] = wet_area_km2(folder, MESHES[mesh][0])
        except Exception as error:  # noqa: BLE001  the area is a reading, not the result
            r["wet_km2"] = f"{type(error).__name__}: {error}"
        out[mesh] = r
    ref = out.get("sq5")
    print(f"\n{case} {forcing}: peak m3/s at s1 / s2 / s3 (hour), s3 against 5 m squares, half-peak width at s3, wet km2, stored at end Mm3, steps, GPU s")
    for mesh, r in out.items():
        against = f"{100 * (r['s3']['peak_m3s'] / ref['s3']['peak_m3s'] - 1):+.1f} %" if ref else "n/a"
        r["s3_against_sq5"] = r["s3"]["peak_m3s"] / ref["s3"]["peak_m3s"] if ref else None
        wet = r["wet_km2"] if isinstance(r["wet_km2"], str) else f"{r['wet_km2']:.3f}"
        print(f"  {mesh:5s} {r['s1']['peak_m3s']:7.1f} ({r['s1']['at_h']:.2f}) / {r['s2']['peak_m3s']:7.1f} ({r['s2']['at_h']:.2f}) / {r['s3']['peak_m3s']:7.1f} ({r['s3']['at_h']:.2f})"
              f"  {against:>8s}  {r['s3']['half_width_min']:5.1f} min  {wet}  {r.get('storage_end_Mm3', 0):.4f}  {r.get('steps', '?')}  {r.get('loop_s', 0):.0f}"
              + (f"  strip cells {r['strips']['cells']}" if "strips" in r else ""))
    (work / f"wave_probe_{forcing}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    case = sys.argv[1]
    what = sys.argv[2] if len(sys.argv) > 2 else "all"
    forcing = next((a for a in sys.argv[3:] if a in FORCINGS), "wave")
    meshes = [a for a in sys.argv[3:] if a in MESHES] or list(MESHES)
    if what in ("ground", "all"):
        ground(case)
    if what in ("build", "all"):
        build(case, forcing, meshes)
    if what in ("run", "all"):
        for mesh in meshes:
            run(case, forcing, mesh)
    if what in ("report", "all"):
        report(case, forcing, meshes)
