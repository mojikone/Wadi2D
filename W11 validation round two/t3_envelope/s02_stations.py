"""Where the gauges are: KMZ placemarks joined to the gauge table, distance to Block 2. Read only."""
import json
import re
import zipfile
from pathlib import Path

import numpy as np
from pyproj import Transformer

B = Path(r"W:\2224 Flood Protection Scheme in North & South Batinah_MAFWWR\06-WORKING\03-Hydrology")
W = B / "WadiGaugeDataAnalyses_MT"
HERE = Path(__file__).resolve().parent
table = json.loads((HERE / "gauges_table.json").read_text(encoding="utf-8"))

z = zipfile.ZipFile(W / "GIS_USR1.Monitoring_Stations.kmz")
kml = z.read("doc.kml").decode("utf-8", "replace")
marks = re.findall(r"<Placemark.*?</Placemark>", kml, flags=re.S)
print(len(marks))
print(marks[0][:1800])
out = {}
tr = Transformer.from_crs(4326, 32640, always_xy=True)
for m in marks:
    name = re.search(r"<name>(.*?)</name>", m, re.S)
    co = re.search(r"<coordinates>\s*([-\d.]+),([-\d.]+)", m)
    fields = dict(re.findall(r'<td>([^<]+)</td>\s*<td>([^<]*)</td>', m))
    if not co:
        continue
    lon, lat = float(co.group(1)), float(co.group(2))
    x, y = tr.transform(lon, lat)
    key = (name.group(1).strip() if name else "")
    out[key] = {"lon": lon, "lat": lat, "x": x, "y": y, **fields}
(HERE / "stations_all.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print(list(out.items())[:2])
