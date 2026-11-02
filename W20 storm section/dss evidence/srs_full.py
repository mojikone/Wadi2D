import sys, tempfile, pathlib, numpy as np, pyproj
sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D")
from hecdss import HecDss
from hecdss.gridded_data import GriddedData
from wadi2d.hms.dss import open_dss
d = pathlib.Path(tempfile.mkdtemp())
for n, text in (("psd93", pyproj.CRS.from_epsg(3440).to_wkt("WKT1_GDAL")), ("x5000", "x"*5000), ("short", "abc")):
    f = d/f"{n}.dss"; h = HecDss(str(f))
    h.put(GriddedData.create(path="/A/B/PRECIP/01JAN2000:0000/01JAN2000:0100/F/", type=430, dataType=1, dataUnits="MM", cellSize=100.0, srsDefinition=text, data=np.ones((2,2)), numberOfCellsX=2, numberOfCellsY=2)); h.close()
    with open_dss(f) as dss:
        r = dss.read_grid(dss.grid_pathnames()[0])
        again = dss.read_grid(dss.grid_pathnames()[0])
    print("RESULT", n, len(text), len(r.srs), r.srs == text, again.srs == text)
