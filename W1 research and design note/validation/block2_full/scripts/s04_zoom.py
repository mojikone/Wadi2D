"""Zoomed panels: Faydh and Bidah axes, dikes, reservoirs; R5A, R2A, Z4C mouths."""
import warnings, sys
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
dams = lines(B/"SHP/Block 2 Dams/SHP/Dams.shp")
dikes = lines(B/"SHP/Block 2 Dams/SHP/Dikes.shp")
det = lines(B/"SHP/already designed dams/Det_Design_DAMS.shp")
res = lines(B/"SHP/Block 2 Dams/SHP/Reservoirs.shp")
views = {"Faydh":(431100,2733700,1000),"Bidah":(438300,2726900,1000),"R5A":(439000,2720600,1500),"R2A":(439400,2716300,1500),"Z4C":(440600,2710600,1200)}
for n,(x,y,r) in views.items():
    b=(x-r,y-r,x+r,y+r)
    with rasterio.open(B/"Terrain/GGC_2_MERGE_HDSM_5.tif") as s:
        w=from_bounds(*b,s.transform); z=s.read(1,window=w,masked=True).astype(float).filled(np.nan)
    with rasterio.open(H/"terrain/GGC_2_MERGE_HDSM_5m/00/flowaccum.tif") as s:
        w=from_bounds(*b,s.transform); fa=s.read(1,window=w,masked=True).astype(float).filled(0)
    fig,ax=plt.subplots(figsize=(11,10))
    ls=LightSource(315,45); hs=ls.hillshade(np.nan_to_num(z,nan=np.nanmean(z)),vert_exag=2,dx=5,dy=5)
    ext=(x-r,x+r,y-r,y+r)
    ax.imshow(hs,extent=ext,cmap="gray",vmin=0,vmax=1)
    im=ax.imshow(z,extent=ext,cmap="terrain",alpha=.5)
    cs=ax.contour(z[::-1],levels=np.arange(np.nanmin(z)//5*5,np.nanmax(z),5),extent=ext,colors="k",linewidths=.25)
    ax.clabel(cs,fontsize=6,inline=True)
    plt.colorbar(im,ax=ax,fraction=.04)
    fa_km2=fa*25e-6
    ax.imshow(np.ma.masked_less(fa_km2,1.0),extent=ext,cmap="autumn",vmin=0,vmax=200,interpolation="nearest")
    for nm,p in polys.items():
        for g in getattr(p,'geoms',[p]):
            xx,yy=g.exterior.xy; ax.plot(xx,yy,'k',lw=1.2)
        ax.text(p.representative_point().x,p.representative_point().y,nm,color='k',fontsize=8,clip_on=True)
    for rec,pts in dams+det:
        ax.plot(pts[:,0],pts[:,1],'r-o',lw=1.5,ms=3)
    for rec,pts in dikes:
        ax.plot(pts[:,0],pts[:,1],'m-o',lw=1.2,ms=2)
        for i,p in enumerate(pts): ax.text(p[0],p[1],str(i),color='m',fontsize=6,clip_on=True)
    for rec,pts in res: ax.plot(pts[:,0],pts[:,1],'c-',lw=.7)
    for rec,pts in dams:
        for i,p in enumerate(pts): ax.text(p[0],p[1],str(i),color='r',fontsize=9,clip_on=True)
    for jn,j in bas.junctions.items():
        ax.plot(j.canvas_x,j.canvas_y,'y^',ms=8,mec='k'); ax.text(j.canvas_x,j.canvas_y,jn,color='k',fontsize=8,clip_on=True)
    ax.set_xlim(x-r,x+r); ax.set_ylim(y-r,y+r); ax.set_title(n); ax.grid(alpha=.3)
    fig.tight_layout(); fig.savefig(OUT/f"zoom_{n}.png",dpi=75); plt.close(fig)
