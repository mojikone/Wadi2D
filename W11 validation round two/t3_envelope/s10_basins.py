import json, sys
from pathlib import Path
import shapefile, shapely, numpy as np
from shapely.geometry import shape
from pyproj import Transformer
sys.path.insert(0,r"D:/Mojtaba/Renardet/Wadi2D/W1 research and design note/validation/block2_full/scripts")
from common import polygons, AXES, UPSTREAM
L=Path(r"W:/2331 Flood Hazard Maps for Muscat-Dhofar-Musandam_MWR/06-WORKING/03-Hydrology/0.13 REPORTS/Hydrology Final Report- Flood Data Analysis/Layers/Wadi Gauges Basin")
print(len(list(L.glob('*.shp'))))
P=polygons()
T=None
res={}
for st in ('DC417300AD','DC434816AD','DC237976AD','DN241238AD','DB496929AD','DC514700AD'):
    f=L/f'{st}.shp'
    if not f.exists():
        print(st,'no shp'); continue
    r=shapefile.Reader(str(f))
    g=shape(r.shape(0).__geo_interface__)
    prj=(f.with_suffix('.prj').read_text() if f.with_suffix('.prj').exists() else '')
    if abs(g.bounds[0])<180:
        tr=Transformer.from_crs(4326,32640,always_xy=True)
        g=shapely.ops.transform(tr.transform,g) if False else shapely.transform(g,lambda c:np.column_stack(tr.transform(c[:,0],c[:,1])))
    g=shapely.make_valid(g)
    area=g.area/1e6
    print(st,'area',round(area,1),'bounds',[round(b) for b in g.bounds],'prj',prj[:40])
    ov={k:round(g.intersection(v).area/1e6,2) for k,v in P.items() if g.intersects(v)}
    print('   overlap with Block 2 subbasins km2',ov,'sum',round(sum(ov.values()),1))
    res[st]=dict(area=area,overlap=ov)
json.dump(res,open('gauge_basin_overlap.json','w'),indent=1)
