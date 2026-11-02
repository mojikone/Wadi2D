import json, numpy as np, re
from pathlib import Path
s=json.load(open('stations_all.json')); t=json.load(open('gauges_table.json'))
print(list(list(s.values())[0].keys()))
c=(432000,2722000)
rows=[]
for k,v in t.items():
    st=s.get(k)
    if not st: rows.append((1e9,k,'?',v)); continue
    d=np.hypot(st['x']-c[0],st['y']-c[1])/1e3
    rows.append((d,k,st,v))
rows.sort(key=lambda r:r[0])
for d,k,st,v in rows:
    nm=st if st=='?' else (st.get('LOCAL_ID') or st.get('SITE_NAME') or '')
    x=None if st=='?' else (round(st['x']),round(st['y']))
    print(f"{d:7.1f} km {k} {nm!s:34.34} {x} A={v.get('area_km2')} n={v.get('n')} {v.get('first')}-{v.get('last')} max={v.get('max')} in {v.get('year_max')} unit={None if v.get('unit_max') is None else round(v['unit_max'],2)}")
