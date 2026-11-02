"""The project's gauge table: station, area, record, largest annual instantaneous peak, unit peak. Read only."""
import json
import re
import zipfile
from pathlib import Path

import numpy as np
import openpyxl

B = Path(r"W:\2224 Flood Protection Scheme in North & South Batinah_MAFWWR\06-WORKING\03-Hydrology")
W = B / "WadiGaugeDataAnalyses_MT"
HERE = Path(__file__).resolve().parent

wb = openpyxl.load_workbook(W / "Francou-Rodier.xlsx", read_only=True, data_only=True)
ws = wb["36stations"]
rows = [list(r) for r in ws.iter_rows(values_only=True)]
print(ws.max_row, ws.max_column)
ids = rows[1]
km2 = rows[2]
code = {}
for c in range(1, 80):
    if isinstance(ids[c], str) and re.match(r"^[A-Z]{2}\d{6}[A-Z]{2}$", ids[c]):
        code[c] = ids[c]
print(len(code), "stations in row 2")
years = [r[0] for r in rows[4:] if isinstance(r[0], (int, float))]
print("years", years[:3], years[-3:], len(years))
table = {}
for c, name in code.items():
    vals = [(int(r[0]), r[c]) for r in rows[4:] if isinstance(r[0], (int, float)) and isinstance(r[c], (int, float))]
    vals = [(y, float(v)) for y, v in vals if v > 0]
    if not vals:
        table[name] = {"area_km2": km2[c], "n": 0}
        continue
    q = np.array([v for _, v in vals])
    y = np.array([a for a, _ in vals])
    table[name] = {
        "area_km2": km2[c],
        "n": len(vals),
        "first": int(y.min()),
        "last": int(y.max()),
        "max": float(q.max()),
        "year_max": int(y[q.argmax()]),
        "unit_max": float(q.max() / km2[c]) if km2[c] else None,
    }

for name, t in sorted(table.items(), key=lambda kv: kv[1]["area_km2"] or 0):
    print(name, t)
(HERE / "gauges_table.json").write_text(json.dumps(table, indent=1), encoding="utf-8")

# station coordinates and names from the KMZ
z = zipfile.ZipFile(W / "GIS_USR1.Monitoring_Stations.kmz")
kml = z.read(z.namelist()[0]).decode("utf-8", "replace")
print(len(kml), z.namelist())
print(kml[:1500])
