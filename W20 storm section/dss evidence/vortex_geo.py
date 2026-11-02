import sys
from java.lang import System
System.loadLibrary("gdalalljni")
from java.util import ArrayList, HashMap
from mil.army.usace.hec.vortex.io import BatchImporter, DataReader
from mil.army.usace.hec.vortex.geo import WktFactory
src, dst, shg = sys.argv[1], sys.argv[2], sys.argv[3] == "shg"
ins = ArrayList(); ins.add(src); vl = ArrayList(); vl.addAll(DataReader.getVariables(src))
wo = HashMap(); wo.put("partA", "SHG" if shg else "UTM40N"); wo.put("partB", "VORTEX"); wo.put("partF", "T")
geo = HashMap()
if shg:
    geo.put("targetWkt", WktFactory.shg()); geo.put("targetCellSize", "2000"); geo.put("resamplingMethod", "Nearest Neighbor")
BatchImporter.builder().inFiles(ins).variables(vl).geoOptions(geo).destination(dst).writeOptions(wo).build().process()
print("done")
