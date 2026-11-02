import sys, shutil, tempfile, pathlib, pyproj
from hecdss import HecDss
for f in sys.argv[1:]:
    d = pathlib.Path(tempfile.mkdtemp()); shutil.copy2(f, d/"x.dss")
    h = HecDss(str(d/"x.dss")); g = h.get(h.get_catalog().uncondensed_paths[0]); h.close()
    try:
        c = pyproj.CRS.from_user_input(g.srsDefinition)
        print(f[-20:], "OK", c.name, "| to_string", c.to_string()[:60], "| type", g.type)
        t = pyproj.Transformer.from_crs(c, 4326, always_xy=True)
        x, y = (g.lowerLeftCellX+g.numberOfCellsX/2)*g.cellSize, (g.lowerLeftCellY+g.numberOfCellsY/2)*g.cellSize
        print("   grid centre lon, lat", t.transform(x, y))
    except Exception as e:
        print(f[-20:], "FAILED", repr(e)[:200], g.srsDefinition[:200])
