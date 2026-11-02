import sys, shutil, tempfile, pathlib, numpy as np
from hecdss import HecDss
from hecdss.gridded_data import GriddedData
d = pathlib.Path(tempfile.mkdtemp()); shutil.copy2(sys.argv[1], d/"g.dss")
h = HecDss(str(d/"g.dss")); o = HecDss(sys.argv[2])
for p in h.get_catalog().uncondensed_paths:
    r = h.get(p); arr = np.asarray(r.data, float).copy(); arr[arr < -1e30] = np.nan
    s = o.put(GriddedData.create(path=p, type=r.type, dataType=r.data_type, lowerLeftCellX=r.lowerLeftCellX, lowerLeftCellY=r.lowerLeftCellY, numberOfCellsX=arr.shape[1], numberOfCellsY=arr.shape[0],
        dataUnits=r.dataUnits, dataSource=r.dataSource, srsName=r.srsName, srsDefinition=r.srsDefinition, timeZoneID=r.timeZoneID, cellSize=r.cellSize, nullValue=r.nullValue, data=arr))
o.close(); h.close()
