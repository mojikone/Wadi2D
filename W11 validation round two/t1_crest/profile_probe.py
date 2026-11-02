"""Ground along the axis and pool volume against level, from the DEM."""
import json
import numpy as np, rasterio
from rasterio.windows import from_bounds
from shapely.geometry import LineString
import t1case as c
ds = rasterio.open(c.base.DEM)
L = LineString(c.AXIS)
S = np.arange(0, L.length, 1.0)
z = np.array([v[0] for v in ds.sample([(L.interpolate(s).x, L.interpolate(s).y) for s in S])], float)
for zc in (90, 91, 92, 93, 94, 95, 96, 97):
    on = np.nonzero(z < zc)[0]
    print(zc, 'overflow length', len(on), 'm, stations', on.min(), on.max())
print('max beyond 800:', z[800:].max(), 'min beyond 850:', z[850:].min(), 'z at end', z[-1])
