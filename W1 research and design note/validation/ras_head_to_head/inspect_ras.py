"""Sanity report on a RAS project folder: mesh, tables, boundaries, volume accounting, solver summary."""

from __future__ import annotations

import sys
from pathlib import Path

import h5py
import numpy as np

import case

d = Path(sys.argv[1])
gname = d / "Fan.g01.hdf"
pname = d / "Fan.p01.hdf"
with h5py.File(gname, "r") as f:
    g = f["Geometry"]
    print("geom attrs", {k: g.attrs[k] for k in g.attrs if "Terrain" in k or k in ("Version", "Complete Geometry")})
    print("geom groups", list(g.keys()))
    fa = g["2D Flow Areas"]
    print("attrs", fa["Attributes"][()])
    print("info", fa["Cell Info"][()])
    m = fa["Fan"]
    print("mesh datasets", list(m.keys()))
    print("mesh attrs", dict(m.attrs))
    n = int(fa["Attributes"]["Cell Count"][0])
    c = m["Cells Center Coordinate"][:]
    print("cells", c.shape, "physical", n)
    if "Cells Surface Area" in m:
        a = m["Cells Surface Area"][:n]
        print("area min/med/max", a.min(), np.median(a), a.max(), "unique", np.unique(np.round(a, 3))[:8])
        print("square cells", (np.abs(a - np.median(a)) < 1e-3).mean())
    if "Cells Minimum Elevation" in m:
        z = m["Cells Minimum Elevation"][:n]
        print("zmin", np.nanmin(z), np.nanmax(z), "nan", np.isnan(z).sum())
    nl = m["Faces NormalUnitVector and Length"][:]
    print("face lengths", np.unique(np.round(nl[:, 2], 3))[:8], "n", len(nl))
    if "Boundary Condition Lines" in g:
        b = g["Boundary Condition Lines"]
        print("BC", list(b.keys()))
        print(b["Attributes"][()])
if pname.exists():
    with h5py.File(pname, "r") as f:
        print("plan root", dict(f.attrs))
        p = f["Plan Data"]
        print(dict(p["Plan Information"].attrs))
        pp = p["Plan Parameters"]
        print({k: pp.attrs[k] for k in pp.attrs if "2D" in k and any(s in k for s in ("Equation", "Cores"))})
        r = f["Results"]["Unsteady"]
        print("unsteady attrs", dict(r.attrs))
        s = r["Summary"]
        print("summary", dict(s.attrs))
        if "Volume Accounting" in s:
            va = s["Volume Accounting"]
            print("VA", dict(va.attrs), list(va.keys()))
        base = r["Output"]["Output Blocks"]["Base Output"]
        ts = base["Unsteady Time Series"]
        print("ts", list(ts.keys()))
        print("2d vars", list(ts["2D Flow Areas"]["Fan"].keys()))
        print("summary vars", list(base["Summary Output"]["2D Flow Areas"]["Fan"].keys()))
        if "Boundary Conditions" in ts:
            for k in ts["Boundary Conditions"]:
                ds = ts["Boundary Conditions"][k]
                print("  bc", k, ds.shape, dict(ds.attrs) if ds.shape and ds.shape[0] < 3 else "")
print("hydrograph volume in, m3", np.trapezoid(case.hydrograph()[1], case.hydrograph()[0]))
