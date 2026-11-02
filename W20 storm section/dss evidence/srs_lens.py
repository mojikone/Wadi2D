import pyproj, re, sys, json, collections
for code, label in ((32640,"WGS84 UTM40N"),(32639,"WGS84 UTM39N"),(3440,"PSD93 UTM40N"),(3439,"PSD93 UTM39N"),(23240,"Fahud UTM40N"),(27040,"Nahrwan67 UTM40N"),(5070,"NAD83 Conus Albers"),(26915,"NAD83 UTM15N"),(4326,"WGS84 geographic"),(32615,"WGS84 UTM15N")):
    try:
        c = pyproj.CRS.from_epsg(code)
        print(f"{label:22} GDAL-WKT1 {len(c.to_wkt('WKT1_GDAL')):5}  ESRI-WKT1 {len(c.to_wkt('WKT1_ESRI')):5}  over 599: {len(c.to_wkt('WKT1_GDAL')) > 599}")
    except Exception as e:
        print(label, "n/a", str(e)[:60])
