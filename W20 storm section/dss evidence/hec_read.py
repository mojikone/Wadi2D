"""HEC's own view of a record: GridInfo fields, Dss2AscGrid's export, and Vortex's reader writing a north-up GeoTIFF."""
import sys
from java.lang import System
from java.util import ArrayList
System.loadLibrary("gdalalljni")
from hec.heclib.grid import GridUtilities, GriddedData, GridData, Dss2AscGrid
from hec.heclib.dss import HecDSSUtilities
dss, path, stem = sys.argv[1], sys.argv[2], sys.argv[3]
# 1. Vortex reader -> VortexGrid -> GeoTIFF
try:
    from mil.army.usace.hec.vortex.io import DataReader, DataWriter
    r = DataReader.builder().path(dss).variable(path).build()
    dtos = r.getDtos()
    print("vortex frames", len(dtos))
    g = dtos[0]
    print("vortex grid origin", g.originX(), g.originY(), "dx", g.dx(), "dy", g.dy(), "nx", g.nx(), "ny", g.ny(), "units", g.units(), "interval", g.interval())
    print("vortex data[0:5]", list(g.data())[:5])
    w = DataWriter.builder().data(dtos).destination(stem + ".tif").build()
    w.write()
    print("wrote tif")
except Exception as e:
    print("vortex failed:", e)
# 2. Dss2AscGrid
try:
    d = Dss2AscGrid(["INPUT=" + dss, "OUTPUT=" + stem + ".asc", "DSSFILE=" + dss, "PATHNAME=" + path])
    d.printArgs()
    d.dump()
    print("asc status", d.getStatus())
except Exception as e:
    print("dss2asc failed:", e)
