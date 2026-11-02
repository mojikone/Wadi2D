import sys
from hec.heclib.grid import Asc2DssGrid
from java.lang import String
args = ["INPUT="+sys.argv[1], "DSSFILE="+sys.argv[2], "PATHNAME=/SHG/ASCTEST/PRECIP/01JAN2000:2300/01JAN2000:2400/HECASC/", "GRIDTYPE=SHG", "DTYPE=PER-CUM", "DUNITS=mm"]
a = Asc2DssGrid(args)
print("load status", a.load())
