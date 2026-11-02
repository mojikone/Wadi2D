"""The reader itself against the independent evidence: nothing here touches the raw array order by hand."""
import sys, re, pathlib, numpy as np, pyproj, rasterio
sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D")
from wadi2d.io.rain import read_rain, rain_choices
from wadi2d.io.rain.dss_grid import dss_choices, read_dss_grid
from wadi2d.storm.rain_frames import RainSpec
from hecdss import HecDss
import shutil, tempfile
W = pathlib.Path(sys.argv[1]); cellsf = sys.argv[2]
np.set_printoptions(linewidth=120, precision=2, suppress=True)
print("--- 1. Vortex, GeoTIFF sampled by coordinate")
f = read_dss_grid(W/"v1/vortex.dss", RainSpec())
print(f.depths[0]); print("west", f.west, "north", f.north, "dx", f.dx, "crs", pyproj.CRS.from_user_input(f.crs).to_epsg(), "origin", f.origin, "starts", f.starts_min, "ends", f.ends_min)
with rasterio.open(W/"v1/PRISM_ppt_stable_4kmD2_20000101_bil.tif") as t:
    xs, ys = np.meshgrid(440500.0 + 1000*np.arange(5), 2728500.0 - 1000*np.arange(4))
    want = np.array([v[0] for v in t.sample(zip(xs.ravel(), ys.ravel()))])
    got = f.depths[0].ravel()[f.pixel_of(xs.ravel(), ys.ravel())]
    print("every cell equal by coordinate, GeoTIFF vs reader:", bool(np.array_equal(want, got)))
print("--- 2. Asc2DssGrid, first ASCII line north, a hole, 2400")
f = read_dss_grid(W/"asc/asc.dss", RainSpec()); print(f.depths[0]); print("west", f.west, "north", f.north, "origin", f.origin, "ends", f.ends_min, "choices", dss_choices(W/"asc/asc.dss"))
print("--- 3. SHG from Vortex reprojection: north row sits where the UTM raster's north row sits")
f = read_dss_grid(W/"shg/shg.dss", RainSpec()); print(f.depths[0])
tr = pyproj.Transformer.from_crs(f.crs, 32615, always_xy=True)
print("centre of row 0, col 0 in UTM15:", tr.transform(f.west + f.dx/2, f.north - f.dy/2), " raster north row spans y 3948000-3950000, x from 300000")
print("--- 4. HRAP real: choices, rain of each subbasin vs HMS's own, through RainFrames.pixel_of")
f = read_rain(W/"hrap/hrap.dss", RainSpec()); print(dss_choices(W/"hrap/hrap.dss"), rain_choices(W/"hrap/hrap.dss"), f.depths.shape, "origin", f.origin, "west", f.west, "north", f.north, "missing share %.4f" % f.missing_share())
print("gaps in time:", int((f.starts_min[1:] != f.ends_min[:-1]).sum()), " first/last", f.starts_min[0], f.ends_min[-1])
cells = {}; cur = None
for line in open(cellsf):
    m = re.match(r"SUBBASIN:\s*(\S+)", line)
    if m: cur = m.group(1); cells[cur] = []
    m = re.match(r"\s*GRIDCELL:\s*(\d+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)", line)
    if m: cells[cur].append((int(m[1]), int(m[2]), float(m[4])))
d = pathlib.Path(tempfile.mkdtemp()); shutil.copy2(W/"hrap/jan96.dss", d/"r.dss"); r = HecDss(str(d/"r.dss"))
names = [str(p) for p in r.get_catalog().items]
lonlat = pyproj.Transformer.from_crs(f.crs, 4326, always_xy=True)
for sub, cl in cells.items():
    area = np.array([c[2] for c in cl]); x = (np.array([c[0] for c in cl]) + 0.5)*4762.5; y = (np.array([c[1] for c in cl]) + 0.5)*4762.5
    px = f.pixel_of(x, y); assert (px >= 0).all()
    ts = r.get(next(n for n in names if f"/{sub}/PRECIP-INC/" in n))
    t = np.array(ts.times, "datetime64[s]"); hms = np.asarray(ts.values, float)*25.4
    ends = f.origin + (f.ends_min*60).astype("timedelta64[s]")
    pick = np.isin(t, ends); idx = np.searchsorted(ends, t[pick])
    est = (np.nan_to_num(f.depths.reshape(f.count, -1)[idx][:, px])*area).sum(1)/area.sum()
    print(f"  {sub:4} {len(cl):3} cells, {pick.sum()} hours: max |reader-HMS| {np.abs(est-hms[pick]).max():.6f} mm, totals {est.sum():.3f} / {hms[pick].sum():.3f} mm;  basin centre lon,lat {tuple(round(v,2) for v in lonlat.transform(x.mean(), y.mean()))}")
r.close()
print("--- 5. Whole real frame vs Vortex's north-up GeoTIFF")
k = int(np.searchsorted(f.ends_min, ((np.datetime64("1996-01-17T20:00") - f.origin)/np.timedelta64(1,"m"))))
with rasterio.open(W/"exp/hrap_1900.tif") as t:
    v = t.read(1, masked=True).filled(np.nan).astype(float); print("tif bounds", tuple(t.bounds))
a = f.depths[k]; print("reader west,north", f.west, f.north, "south", f.north-f.rows*f.dy, "cells equal", float((np.isclose(a, v, atol=1e-4) | (np.isnan(a) & np.isnan(v))).mean()))
print("--- 6. His real files")
for name, spec in (("r8.dss", None), ("r8.dss", RainSpec(interval_min=60.0)), ("r13.dss", None), ("r13.dss", RainSpec(interval_min=30.0)), ("r10.dss", RainSpec()), ("r1.dss", RainSpec(interval_min=60.0, stamp="start")), ("r0.dss", RainSpec(interval_min=60.0))):
    try:
        f = read_dss_grid(W/"real"/name, spec or RainSpec())
        print(f"  {name} {f.depths.shape} first {f.origin} span {f.starts_min[0]}..{f.ends_min[-1]} min, west {f.west}, north {f.north}, max {np.nanmax(f.depths):.2f}, choices {dss_choices(W/'real'/name)}, looks cumulative {f.looks_cumulative()}")
    except ValueError as e:
        print(f"  {name} refused: {e}")
for name in ("r12.dss", "hrap/hrap6.dss"):
    try:
        read_dss_grid((W/"real"/name) if name.startswith("r1") else W/name, RainSpec())
    except ValueError as e:
        print("  ", e)
