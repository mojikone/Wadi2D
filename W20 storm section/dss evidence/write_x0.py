import sys, numpy as np
from hecdss import HecDss
from hecdss.gridded_data import GriddedData
wkt = 'PROJCS["WGS 84 / UTM zone 40N",GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],PARAMETER["latitude_of_origin",0],PARAMETER["central_meridian",57],PARAMETER["scale_factor",0.9996],PARAMETER["false_easting",500000],PARAMETER["false_northing",0],UNIT["metre",1],AUTHORITY["EPSG","32640"]]'
a = np.array([[0,0,0,0,0],[5,6,7,8,9],[30,31,32,33,34],[50,51,52,53,54]], float)
g = GriddedData.create(path="/UTM/X0/PRECIP/01JAN2000:0000/01JAN2000:0100/T/", type=430, dataType=1, lowerLeftCellX=3, lowerLeftCellY=4, numberOfCellsX=5, numberOfCellsY=4,
    dataUnits="MM", srsName="UTM40", srsDefinition=wkt, srsDefinitionType=1, cellSize=100.0, xCoordOfGridCellZero=1000.0, yCoordOfGridCellZero=2000.0, nullValue=-3.4028234663852886e+38, data=a)
h = HecDss(sys.argv[1]); print("put", h.put(g)); h.close()
