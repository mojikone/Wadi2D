import sys, numpy as np, rasterio
from rasterio.transform import from_origin
from rasterio.crs import CRS
out, west, north, cell, epsg = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), int(sys.argv[5])
data = np.array([[50,51,52,53,54],[30,31,32,33,34],[5,6,7,8,9],[0,0,0,0,0]], dtype="float32")
with rasterio.open(out, "w", driver="GTiff", width=5, height=4, count=1, dtype="float32", crs=CRS.from_epsg(epsg),
                   transform=from_origin(west, north, cell, cell), nodata=-9999.0) as d:
    d.write(data, 1)
