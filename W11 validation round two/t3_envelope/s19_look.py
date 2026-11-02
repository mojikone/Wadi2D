import json, numpy as np, rasterio, shapely, shapefile, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from shapely.geometry import shape
B=r"W:/2224 Flood Protection Scheme in North & South Batinah_MAFWWR/06-WORKING/03-Hydrology/calibration/HMS_Albatinah_Calibration/Basin_DB839224AD.shp"
r=shapefile.Reader(B); gs=[shape(r.shape(i).__geo_interface__) for i in range(len(r))]
print([ (r.record(i)[0], round(gs[i].area/1e6,1)) for i in range(len(r))])
DEM=r"D:/Mojtaba/Renardet/Wadi2D/W2 full extent run/terrain/NSA5_COP30_blend.tif"
GX,GY=488963.0,2632307.0
b=(GX-2500,GY-2500,GX+2500,GY+2500)
with rasterio.open(DEM) as s:
    w=rasterio.windows.from_bounds(*b,s.transform); a=s.read(1,window=w,masked=True).filled(np.nan)
fig,ax=plt.subplots(figsize=(8,8))
ax.imshow(a,extent=(b[0],b[2],b[1],b[3]),cmap='terrain',vmin=np.nanpercentile(a,1),vmax=np.nanpercentile(a,90))
ax.contour(np.linspace(b[0],b[2],a.shape[1]),np.linspace(b[3],b[1],a.shape[0]),a,levels=np.arange(200,500,5),colors='k',linewidths=.3)
for g in gs:
    for p in (g.geoms if g.geom_type!='Polygon' else [g]):
        x,y=p.exterior.xy; ax.plot(x,y,'r')
ax.plot(GX,GY,'m*',ms=14); ax.set_xlim(b[0],b[2]); ax.set_ylim(b[1],b[3]); ax.grid(True)
plt.savefig('look_lihban.png',dpi=70)
