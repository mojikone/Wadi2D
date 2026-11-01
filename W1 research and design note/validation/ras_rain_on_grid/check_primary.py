"""Is the 10 m match real? Raw series round the peak, RAS's own boundary output against the faces read here, and
Wadi2D with the thin-sheet option off against RAS. Writes check_primary.json.
"""

from __future__ import annotations

import json

import h5py
import numpy as np

import case
from compare import BASE, TS

out: dict = {}
for name in ("20m_n050_em", "10m_n050_em"):
    z = np.load(case.HERE / f"series_{name}.npz")
    tr, qr, tw, qw = z["axis_tr"], z["axis_qr"], z["axis_tw"], z["axis_qw"]
    i = int(np.argmax(qr))
    print(name, "RAS round its peak:")
    for k in range(i - 3, i + 4):
        print(f"  t {tr[k] / 3600:7.3f} h  RAS {qr[k]:8.2f}  Wadi2D {np.interp(tr[k], tw, qw):8.2f}")
    with h5py.File(case.HERE / f"ras_{name}" / "Bidah.p01.hdf", "r") as f:
        bc = f[TS]["Boundary Conditions"]
        east, north = bc["OutEast"][:, 1], bc["OutNorth"][:, 1]
        t = f[TS]["Time"][:] * 86400.0
        total = np.abs(east) + np.abs(north)
        # a third independent read: the outlet faces of Wadi2D's own balance
        va = f["Results/Unsteady/Summary/Volume Accounting"].attrs
        ras_out = float(va["Total Boundary Flux of Water Out"]) * 1000.0
        print(f"  RAS outlet peak {total.max():.1f} at {t[int(np.argmax(total))] / 3600:.2f} h; volume by series "
              f"{np.trapezoid(total, t):.0f}, by RAS's accounting {ras_out:.0f}")
        out[name] = {"ras_outlet_peak": float(total.max()), "ras_outlet_t_h": float(t[int(np.argmax(total))] / 3600.0),
                     "ras_outlet_volume_series": float(np.trapezoid(total, t)), "ras_outlet_volume_accounting": ras_out}  # fmt: skip
        s = dict(f[BASE + "/Summary Output/2D Flow Areas/Bidah"].attrs) if False else {}
        del s
    # the peak of the HMS-equivalent basis, read through the same function
    wall = json.loads((case.HERE / "wadi_runs" / name / "progress.jsonl").read_text(encoding="utf-8").strip().split("\n")[-1])
    out[name]["wadi_outflow_m3"] = wall["balance"]["outflow_m3"]
    print(f"  Wadi2D outflow {wall['balance']['outflow_m3']:.0f}")

for name, ref in (("w20m_no_sheet", "20m_n050_em"), ("w10m_no_sheet", "10m_n050_em")):
    z = np.load(case.HERE / f"series_{ref}.npz")
    tr, qr = z["axis_tr"], z["axis_qr"]
    a = np.loadtxt(case.HERE / "wadi_runs" / name / "series" / "line_axis.csv", delimiter=",", skiprows=1)
    q = np.interp(tr, a[:, 0], a[:, 1])
    nse = 1.0 - ((q - qr) ** 2).sum() / ((qr - qr.mean()) ** 2).sum()
    k = int(np.argmax(a[:, 1]))
    out[name] = {"peak": float(a[k, 1]), "t_h": float(a[k, 0] / 3600.0), "ratio_to_ras": float(a[k, 1] / qr.max()), "nse": float(nse)}
    print(name, out[name])
(case.HERE / "check_primary.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
