"""Overview of DEM coverage, polygons, dams and dam-axis layers. Reads only."""
import warnings, zipfile, io, json
from pathlib import Path
import numpy as np, rasterio, shapefile, shapely
from rasterio.enums import Resampling
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from wadi2d.hms import sqlite as S
warnings.simplefilter("ignore")
B = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology")
H = B/"HEC_HMS_Block_02"
OUT = Path(r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\block2_full")
for name in ("GGC_2_MERGE_HDSM.tif","GGC_2_MERGE_HDSM_5.tif","NSA_Batinah_2m.tif","NSA_Batinah_5m.tif"):
    with rasterio.open(B/"Terrain"/name) as s:
        print(name, s.bounds, s.res, s.crs.to_epsg() if s.crs else None, s.nodata, s.dtypes, s.overviews(1)[:4], s.block_shapes[:1])
with rasterio.open(H/"Hydrology Data"/"CN_Include_Hill_Area.tif") as s:
    print("CN", s.bounds, s.res, s.crs.to_epsg() if s.crs else None, s.nodata, s.dtypes)
    a = s.read(1, masked=True)
    print(" CN min max mean", a.min(), a.max(), a.mean(), np.unique(a.compressed())[:30], len(np.unique(a.compressed())))
with rasterio.open(H/"terrain/GGC_2_MERGE_HDSM_5m/00/flowaccum.tif") as s:
    print("flowaccum", s.bounds, s.res, s.nodata, s.dtypes)
ds = 25
with rasterio.open(B/"Terrain"/"GGC_2_MERGE_HDSM_5.tif") as s:
    h = s.height//ds; w = s.width//ds
    a = s.read(1, out_shape=(h,w), masked=True, resampling=Resampling.nearest)
    ext = (s.bounds.left, s.bounds.right, s.bounds.bottom, s.bounds.top)
    print("nodata frac", a.mask.mean(), a.min(), a.max())
fig, ax = plt.subplots(figsize=(13,14))
ax.imshow(np.clip(a.filled(np.nan),0,900), extent=ext, cmap="terrain")
polys = {r.name:r.shape() for r in S.subbasin_polygons(H/"Basin_1.sqlite")}
for n,p in polys.items():
    for g in getattr(p,'geoms',[p]):
        x,y = g.exterior.xy; ax.plot(x,y,'k',lw=.6)
    ax.text(p.centroid.x,p.centroid.y,n,fontsize=7)
def shp(path, color, label):
    r = shapefile.Reader(str(path))
    print(path.name, r.fields[1:], r.bbox)
    for sr in r.shapeRecords():
        pts = np.array(sr.shape.points); parts = list(sr.shape.parts)+[len(pts)]
        for a0,b0 in zip(parts[:-1],parts[1:]):
            ax.plot(pts[a0:b0,0],pts[a0:b0,1],color=color,lw=1.5)
        print("  ", sr.record.as_dict() if hasattr(sr.record,'as_dict') else list(sr.record), len(pts), np.round(pts[:8],1).tolist())
D = B/"SHP"/"Block 2 Dams"/"SHP"
shp(D/"Dams.shp","r","dams"); shp(D/"Dikes.shp","m","dikes"); shp(D/"Reservoirs.shp","c","res")
for p in sorted((B/"SHP"/"already designed dams").glob("*.shp")):
    shp(p,"orange",p.stem)
ax.set_xlim(405000,460000); ax.set_ylim(2695000,2750000)
fig.savefig(OUT/"scripts"/"overview.png",dpi=90)
