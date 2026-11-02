import sys, tempfile, pathlib, numpy as np, pyproj
from hecdss import HecDss
from hecdss.gridded_data import GriddedData
d = pathlib.Path(tempfile.mkdtemp())
wkt2 = pyproj.CRS.from_epsg(32640).to_wkt()
for n, text in (("wkt2", wkt2), ("wkt1", pyproj.CRS.from_epsg(32640).to_wkt("WKT1_GDAL")), ("x5000", "x"*5000), ("x700", "x"*700)):
    f = d/f"{n}.dss"; h = HecDss(str(f))
    g = GriddedData.create(path="/A/B/PRECIP/01JAN2000:0000/01JAN2000:0100/F/", type=430, dataType=1, dataUnits="MM", cellSize=100.0, srsDefinition=text, data=np.ones((2,2)), numberOfCellsX=2, numberOfCellsY=2)
    h.put(g); h.close(); h = HecDss(str(f)); r = h.get(h.get_catalog().uncondensed_paths[0]); h.close()
    print("RESULT", n, "written", len(text), "read", len(r.srsDefinition), "same", r.srsDefinition == text)
