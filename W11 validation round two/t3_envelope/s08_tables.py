"""Tables 26, 27, 33 and 20 of the 2331 report joined: Q by return period, area, governorate, Tp, Tc. Read only."""
import json
import re
import sys
from pathlib import Path

import docx
import numpy as np

R = Path(r"W:\2331 Flood Hazard Maps for Muscat-Dhofar-Musandam_MWR\06-WORKING\03-Hydrology\0.13 REPORTS\Hydrology Final Report- Flood Data Analysis")
HERE = Path(__file__).resolve().parent
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
d = docx.Document(R / "Report" / "Final Report" / "Hydrology Final Report- Flood Data Analysis.docx")


def rows(i):
    out = []
    for r in d.tables[i].rows:
        cells, prev = [], None
        for c in r.cells:
            if c._tc is prev:
                continue
            prev = c._tc
            cells.append(c.text.strip().replace("\n", " "))
        out.append(cells)
    return out


def num(s):
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


for i in (33, 34, 35, 36, 43, 28, 29, 21, 45, 54):
    r = rows(i)
    print("TABLE", i)
    for x in r[:4]:
        print("  ", [c[:18] for c in x][:12])

# Table 26: index 35
t26 = {}
for r in rows(35)[2:]:
    if len(r) >= 10 and re.match(r"^[A-Z]{2}\d{6}[A-Z]{2}$", r[2]):
        t26[r[2]] = {"wadi": r[1], "q": {str(a): num(b) for a, b in zip((2, 5, 10, 25, 50, 100, 200, 500), r[3:11], strict=False)}}
print(len(t26))
t33 = {}
for r in rows(43):
    if r and re.match(r"^[A-Z]{2}\d{6}[A-Z]{2}$", r[0]):
        t33[r[0]] = {"area": num(r[1]), "mss": num(r[2])}
print(len(t33))
t21 = {}
for r in rows(21):
    if len(r) > 3 and re.match(r"^[A-Z]{2}\d{6}[A-Z]{2}$", r[1]):
        t21[r[1]] = {"area": num(r[2])}
print(len(t21))
t27 = {}
for r in rows(36):
    if len(r) > 5 and re.match(r"^[A-Z]{2}\d{6}[A-Z]{2}$", r[2]):
        t27[r[2]] = {"max": num(r[3]), "year": r[4], "rp": r[5], "cyclone": r[6] if len(r) > 6 else ""}
print(len(t27))
t25 = {}
for r in rows(34):
    if len(r) > 3 and re.match(r"^[A-Z]{2}\d{6}[A-Z]{2}$", r[2]):
        t25[r[2]] = {"gov": r[1]}
print(len(t25))
t20 = {}
for r in rows(28):
    if len(r) > 5 and re.match(r"^[A-Z]{2}\d{6}[A-Z]{2}$", r[2]):
        t20[r[2]] = {"wadi": r[1], "area": num(r[3]), "tp": num(r[4]), "tc": num(r[5])}
print(len(t20))
kir = {}
h = rows(29)
print(h[0])
for r in h[1:]:
    if re.match(r"^[A-Z]{2}\d{6}[A-Z]{2}$", r[0]):
        kir[r[0]] = [num(x) for x in r[1:]]
all_ = {}
for k, v in t26.items():
    all_[k] = {**v, **t33.get(k, {}), **{"area21": t21.get(k, {}).get("area")}, **t27.get(k, {}), **t25.get(k, {}),
               "tp": t20.get(k, {}).get("tp"), "tc": t20.get(k, {}).get("tc"), "kirpich_etc": kir.get(k)}  # fmt: skip
(HERE / "stations_2331.json").write_text(json.dumps(all_, indent=1), encoding="utf-8")
(HERE / "tc_2331.json").write_text(json.dumps({"header": h[0], "t20": t20, "emp": kir}, indent=1), encoding="utf-8")
print(json.dumps(list(all_.items())[0], indent=0)[:600])
