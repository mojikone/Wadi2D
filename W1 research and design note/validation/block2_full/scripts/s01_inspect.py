"""Inspect the HMS model: network, polygons, dam sites, DA 100yr reference numbers. Reads only."""
import json, sys, warnings
from pathlib import Path
import numpy as np, shapely
warnings.simplefilter("ignore")
from wadi2d.hms import load_basin, load_results, load_met, load_pdata
from wadi2d.hms import sqlite as S
from wadi2d.hydrology.from_hms import load_project_tables

H = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\HEC_HMS_Block_02")
b = load_basin(H/"Basin_1.basin")
print("subbasins", len(b.subbasins), "reaches", len(b.reaches) if hasattr(b,'reaches') else '?', "junctions", len(b.junctions))
polys = {r.name: r.shape() for r in S.subbasin_polygons(H/"Basin_1.sqlite")}
for n, e in b.subbasins.items():
    p = polys[n]
    c = p.centroid
    print(n, "A_hms", e.area_km2 if hasattr(e,'area_km2') else getattr(e,'area',None), "A_poly %.3f"%(p.area/1e6), "ds", e.downstream, "CN", getattr(e.loss,'curve_number',None), "Ia", getattr(e.loss,'initial_abstraction',None), "lag", getattr(e.transform,'lag',None), "centroid %.0f %.0f"%(c.x,c.y), "bounds", [round(v) for v in p.bounds], p.is_valid)
print("junctions")
for n, e in b.junctions.items():
    print(n, e.canvas_x, e.canvas_y, "ds", e.downstream)
for attr in ("reaches",):
    d = getattr(b, attr, {})
    for n, e in d.items():
        print("reach", n, "ds", e.downstream, {k:v for k,v in vars(e).items() if k not in ('name','downstream')} if hasattr(e,'__dict__') else e)
u = shapely.union_all([p.buffer(0) for p in polys.values()])
print("union bounds", u.bounds, "area", u.area/1e6, u.geom_type)
r = load_results(H/"results"/"DAA_DA_100yr_B1.results")
print("start", r.start, r.end)
for p in ("Faydh 01","Bidah 03","R5A","R2A","Z4C"):
    e = r.element(p)
    print(p, "area", e.drainage_area, "peak", e.outflow_max, "t", (e.outflow_max_time-r.start).total_seconds()/3600, "vol", e.outflow_volume, e.measures.get('Outflow Volume'), "depth", e.outflow_depth, e.measures.get('Outflow Depth'))
    print("   upstream elems", sorted(r.points[p].keys()))
stem = H/"HEC_HMS_Block_02"
t = load_project_tables(load_pdata(stem.with_suffix(".pdata")), stem.with_suffix(".dss"))
m = load_met(H/"FM_100yr.met").storm
print(m)
pat = t.patterns[m.pattern_name]
print("pattern n", len(pat.time_percent), list(zip(pat.time_percent[:5], pat.depth_percent[:5])), list(zip(pat.time_percent[-3:], pat.depth_percent[-3:])))
arf = t.area_reductions[m.reduction_table_name]
print("ARF", [(float(a), float(f)) for a,f in zip(arf.areas_km2, arf.factors)])
