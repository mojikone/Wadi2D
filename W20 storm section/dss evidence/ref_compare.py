import sys, shutil, tempfile, pathlib, numpy as np, rasterio
from hecdss import HecDss
dss, path, tif = sys.argv[1:4]
d = pathlib.Path(tempfile.mkdtemp()); shutil.copy2(dss, d/"x.dss")
h = HecDss(str(d/"x.dss")); g = h.get(path); raw = np.asarray(g.data, float); h.close()
with rasterio.open(tif) as t:
    v = t.read(1, masked=True).filled(np.nan).astype(float); print("tif bounds", t.bounds, "shape", v.shape, "res", t.res)
    print("crs", (t.crs.to_wkt() or "")[:160])
raw[raw < -1e30] = np.nan
for name, a in (("raw", raw), ("raw flipped", raw[::-1])):
    same = (np.isclose(a, v, atol=1e-4) | (np.isnan(a) & np.isnan(v))).mean()
    print(f"{name:12} agrees on {same*100:.3f} % of cells; wet cells raw {np.nansum(a>0)}, max abs diff {np.nanmax(np.abs(a-v)):.3f}")
print("west", g.lowerLeftCellX*g.cellSize, "south", g.lowerLeftCellY*g.cellSize, "north", (g.lowerLeftCellY+g.numberOfCellsY)*g.cellSize)
print("HRAP wkt:", g.srsDefinition)
