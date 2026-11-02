"""Yardstick: how far apart are his own 100-yr and 200-yr layers on the same metric?"""
import json, numpy as np, rasterio, rasterio.features, shapely
from rasterio.enums import Resampling
from rasterio.warp import reproject
R=r"W:/2224 Flood Protection Scheme in North & South Batinah_MAFWWR/06-WORKING/04-Hydraulic/00 Data/Layers/Flood Maps/Depth/Rasters OK/B2 Depth Rasters/"
per=np.array(json.load(open('his_perimeter.json'))); poly=shapely.Polygon(per); b=poly.bounds
d=30.0; x0=np.floor(b[0]/d)*d; y1=np.ceil(b[3]/d)*d; nx=int(np.ceil((b[2]-x0)/d)); ny=int(np.ceil((y1-b[1])/d))
t=rasterio.transform.from_origin(x0,y1,d,d)
ins=rasterio.features.geometry_mask([poly],out_shape=(ny,nx),transform=t,invert=True)
def load(p):
    o=np.zeros((ny,nx),np.float32)
    with rasterio.open(p) as s:
        a=s.read(1); a=np.where(a==s.nodata,0,a).astype(np.float32); ts=s.transform
    reproject(a,o,src_transform=ts,src_crs='EPSG:32640',dst_transform=t,dst_crs='EPSG:32640',resampling=Resampling.average); return o
L={k:load(R+f'Block2_Depth_{k}Year.tif') for k in (100,200,1000)}
def F(a,b): 
    a=a&ins;b=b&ins; return round(float((a&b).sum()/(a|b).sum()),3),round(float(a.sum()*9e-4),1),round(float(b.sum()*9e-4),1)
print('his 200 vs his 100',F(L[200]>=.3,L[100]>=.3))
print('his 200 vs his 1000',F(L[200]>=.3,L[1000]>=.3))
