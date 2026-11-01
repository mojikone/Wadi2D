"""Hillshade panels around the five dam sites with polygons, axes, HMS junctions, streams. Reads only."""
import warnings
from pathlib import Path
import numpy as np, rasterio, shapefile
from rasterio.windows import from_bounds
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource
from wadi2d.hms import sqlite as S, load_basin
warnings.simplefilter("ignore")
B = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology")
H = B/"HEC_HMS_Block_02"
OUT = Path(r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\block2_full\scripts")
polys = {r.name:r.shape() for r in S.subbasin_polygons(H/"Basin_1.sqlite")}
bas = load_basin(H/"Basin_1.basin")
def lines(path):
    r = shapefile.Reader(str(path)); out=[]
    for sr in r.shapeRecords():
        pts = np.array(sr.shape.points); parts = list(sr.shape.parts)+[len(pts)]
        for a0,b0 in zip(parts[:-1],parts[1:]): out.append((list(sr.record), pts[a0:b0]))
    return out
axes_ = lines(B/"SHP/Block 2 Dams/SHP/Dams.shp")+lines(B/"SHP/already designed dams/Det_Design_DAMS.shp")+lines(B/"SHP/Block 2 Dams/SHP/Dikes.shp")
res = lines(B/"SHP/Block 2 Dams/SHP/Reservoirs.shp")
sites = {"Faydh 01":(431033,2733411),"Bidah 03":(438602,2727064),"R5A":(439053,2721052),"R2A":(439959,2715889),"Z4C":(440980,2710482)}
fig, axs = plt.subplots(2,3,figsize=(19,13)); axs=axs.ravel()
for k,(n,(x,y)) in enumerate(sites.items()):
    ax=axs[k]; r=3000
    b=(x-r,y-r,x+r,y+r)
    with rasterio.open(B/"Terrain/GGC_2_MERGE_HDSM_5.tif") as s:
        w=from_bounds(*b,s.transform); z=s.read(1,window=w,masked=True).astype(float).filled(np.nan)
    with rasterio.open(H/"terrain/GGC_2_MERGE_HDSM_5m/00/flowaccum.tif") as s:
        w=from_bounds(*b,s.transform); fa=s.read(1,window=w,masked=True).astype(float).filled(0)
    ls=LightSource(315,45); hs=ls.hillshade(np.nan_to_num(z,nan=np.nanmean(z)),vert_exag=3,dx=5,dy=5)
    ext=(x-r,x+r,y-r,y+r)
    ax.imshow(hs,extent=ext,cmap="gray",vmin=0,vmax=1)
    im=ax.imshow(z,extent=ext,cmap="terrain",alpha=.45)
    plt.colorbar(im,ax=ax,fraction=.04)
    fa_km2=fa*25e-6
    ax.imshow(np.ma.masked_less(fa_km2,0.5),extent=ext,cmap="winter",vmin=0,vmax=100,interpolation="nearest")
    for nm,p in polys.items():
        for g in getattr(p,'geoms',[p]):
            xx,yy=g.exterior.xy; ax.plot(xx,yy,'k',lw=.8)
    for rec,pts in axes_:
        ax.plot(pts[:,0],pts[:,1],'r-',lw=1.5)
    for rec,pts in res: ax.plot(pts[:,0],pts[:,1],'c-',lw=.7)
    for jn,j in bas.junctions.items():
        ax.plot(j.canvas_x,j.canvas_y,'y^',ms=7); ax.text(j.canvas_x,j.canvas_y,jn,color='y',fontsize=8)
    ax.set_xlim(x-r,x+r); ax.set_ylim(y-r,y+r); ax.set_title(n); ax.grid(alpha=.3)
axs[5].axis("off")
fig.tight_layout(); fig.savefig(OUT/"sites.png",dpi=80)
