from java.lang import System
System.loadLibrary("gdalalljni")
from mil.army.usace.hec.vortex import GdalRegister
GdalRegister.getInstance()
import sys
from java.util import ArrayList, HashMap
from mil.army.usace.hec.vortex.io import BatchImporter, DataReader
src, dst = sys.argv[1], sys.argv[2]
vs = DataReader.getVariables(src)
print("variables", list(vs))
ins = ArrayList(); ins.add(src)
vl = ArrayList(); vl.addAll(vs)
wo = HashMap(); wo.put("partA", "UTM40N"); wo.put("partB", "VORTEX"); wo.put("partF", "NORTHWET")
b = BatchImporter.builder().inFiles(ins).variables(vl).destination(dst).writeOptions(wo).build()
b.process()
print("done")
