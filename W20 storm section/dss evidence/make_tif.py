import sys, numpy as np, rasterio
from rasterio.transform import from_origin
from rasterio.crs import CRS
out = sys.argv[1]
# 4 rows, 5 columns, north wet, south dry, every wet cell unique, west to east rising.
data = np.array([[50,51,52,53,54],[30,31,32,33,34],[5,6,7,8,9],[0,0,0,0,0]], dtype="float32")
west, north, cell = 440000.0, 2729000.0, 1000.0
with rasterio.open(out, "w", driver="GTiff", width=5, height=4, count=1, dtype="float32",
                   crs=CRS.from_epsg(32640), transform=from_origin(west, north, cell, cell), nodata=-9999.0) as d:
    d.write(data, 1)
    d.update_tags(1, units="mm")
with rasterio.open(out) as d:
    print("transform", d.transform, "bounds", d.bounds)
    # Independent statement of where the wet row is: sample by coordinate, not by index.
    print("value at y=2728500 (north row):", list(d.sample([(440500.0, 2728500.0)]))[0])
    print("value at y=2725500 (south row):", list(d.sample([(440500.0, 2725500.0)]))[0])
