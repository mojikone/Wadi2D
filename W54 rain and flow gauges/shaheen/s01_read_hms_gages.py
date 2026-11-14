"""What the project's HMS calibration holds for Shaheen at Lihban: its gages, and their records read through wadi2d.

Read only: the DSS file is opened through a scratch copy by wadi2d.hms.dss.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from wadi2d.hms import gage
from wadi2d.io.series import FLOW, PRECIPITATION, read_record

HERE = Path(__file__).resolve().parent
PROJECT = Path(
    r"W:\2224 Flood Protection Scheme in North & South Batinah_MAFWWR\06-WORKING\03-Hydrology\calibration"
    r"\HMS_Albatinah_Calibration\Albatinah_Calibration"
)
W11 = HERE.parents[1] / "W11 validation round two" / "t3_envelope" / "shaheen_5min.csv"

found = {}
for g in gage.load(PROJECT / "Albatinah_Calibration.gage"):
    found[g.name] = {"kind": g.kind, "units": g.units, "type": g.data_type, "pathname": g.pathname, "lat": g.latitude}
    want = PRECIPITATION if g.is_rain else FLOW
    if "Shahin" not in g.name:
        continue
    r = read_record(g.dss_file, g.pathname, want=want)
    v = r.values
    found[g.name].update(
        first=str(r.dates[0]), last=str(r.dates[-1]), values=int(v.size), missing=int(np.isnan(v).sum()),
        total_or_peak=float(np.nansum(v) if g.is_rain else np.nanmax(v)), interval_min=r.interval_min, kind_read=r.kind,
    )
w11 = np.loadtxt(W11, delimiter=",", skiprows=1)
found["W11 shaheen_5min.csv"] = {"rain_mm": float(w11[:, 1].sum()), "peak_m3s": float(w11[:, 2].max())}
(HERE / "hms_gages.json").write_text(json.dumps(found, indent=1), encoding="utf-8")
print(json.dumps(found, indent=1))
