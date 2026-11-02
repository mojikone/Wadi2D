"""F of each Wadi2D variant against his layer: 30 m mean depth, inside his perimeter, 0.3 m and 0.1 m, by zone."""
import json, sys
from pathlib import Path
import numpy as np, rasterio, rasterio.features, shapely
from rasterio.enums import Resampling
from rasterio.warp import reproject
sys.path.insert(0, r"D:/Mojtaba/Renardet/Wadi2D/W1 research and design note/validation/block2_full/scripts")
from common import polygons
HERE=Path(__file__).resolve().parent
HIS=Path(r"D:/Mojtaba/Renardet/2224 WS11/Batinah/Block 2/Hydrology/Raster/Block2_Depth_200Year.tif")
per=np.array(json.loads((HERE/'his_perimeter.json').read_text()))
poly=shapely.Polygon(per)
b=poly.bounds
d=30.0
x0=np.floor(b[0]/d)*d; y1=np.ceil(b[3]/d)*d
nx=int(np.ceil((b[2]-x0)/d)); ny=int(np.ceil((y1-b[1])/d))
t=rasterio.transform.from_origin(x0,y1,d,d)
ins=rasterio.features.geometry_mask([poly],out_shape=(ny,nx),transform=t,invert=True)
hills_poly=shapely.union_all([p.buffer(5.0) for p in polygons().values()])
hills=rasterio.features.geometry_mask([hills_poly],out_shape=(ny,nx),transform=t,invert=True)
tag=HERE/'his30.npy'
if tag.exists():
    his=np.load(tag)
else:
    with rasterio.open(HIS) as s:
        a=s.read(1); a=np.where(a==s.nodata,0.0,a).astype(np.float32); ts=s.transform
    his=np.zeros((ny,nx),np.float32)
    reproject(a,his,src_transform=ts,src_crs='EPSG:32640',dst_transform=t,dst_crs='EPSG:32640',resampling=Resampling.average)
    np.save(tag,his)
def load(p):
    o=np.zeros((ny,nx),np.float32)
    with rasterio.open(p) as s:
        a=s.read(1,masked=True).filled(0.0).astype(np.float32); ts=s.transform
    reproject(a,o,src_transform=ts,src_crs='EPSG:32640',dst_transform=t,dst_crs='EPSG:32640',resampling=Resampling.average)
    return o
def F(a,b,m):
    both=(a&b&m).sum(); o1=(a&~b&m).sum(); o2=(~a&b&m).sum()
    return dict(F=round(float(both/max(both+o1+o2,1)),3),both=round(both*9e-4,1),his=round(o1*9e-4,1),wadi=round(o2*9e-4,1))
out={}
names=sys.argv[1:] or ['t0_base','t1_rain228','t2_n060','t3_ggc','t4_dx15','t5_all']
W2=HERE.parent.parent/'W2 full extent run'/'runs'/'full_30m_200yr'/'maps'/'max_mean_depth.tif'
for n,p in [('W2 run',W2)]+[(n,HERE/'wadi_runs'/n/'maps'/'max_mean_depth.tif') for n in names]:
    if not Path(p).exists():
        print(n,'missing'); continue
    w=load(p)
    r={'all':F(his>=.3,w>=.3,ins),'hills':F(his>=.3,w>=.3,ins&hills),'plain':F(his>=.3,w>=.3,ins&~hills),'all_0.1':F(his>=.1,w>=.1,ins),'wet03_km2':round(float(((w>=.3)&ins).sum()*9e-4),1),'his03_km2':round(float(((his>=.3)&ins).sum()*9e-4),1)}
    out[n]=r; print(n,r)
    if Path(HERE/'wadi_runs'/n/'results.h5').exists():
        import h5py
        f=h5py.File(HERE/'wadi_runs'/n/'results.h5','r'); print('   rain Mm3',round(float(f.attrs['rain_m3'])/1e6,1),'out',round(float(f.attrs['outflow_m3'])/1e6,1),'end',round(float(f.attrs['storage_end_m3'])/1e6,1))
(HERE/'score.json').write_text(json.dumps(out,indent=1))
