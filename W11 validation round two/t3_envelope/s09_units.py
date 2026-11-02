import json, numpy as np
a=json.load(open('stations_2331.json'))
tc=json.load(open('tc_2331.json'))
near=json.load(open('stations_all.json'))
c=(432000,2722000)
rows=[]
for k,v in a.items():
    A=v.get('area') or v.get('area21')
    q=v['q'].get('100')
    if not A or not q: continue
    st=near.get(k)
    d=None if st is None else np.hypot(st['x']-c[0],st['y']-c[1])/1e3
    rows.append((A,k,v['wadi'],v.get('gov'),q,q/A,v.get('max'),v.get('year'),v.get('rp'),v.get('cyclone'),d))
rows.sort()
print(len(rows))
print('area km2, station, wadi, gov, Q100, unit100, max, yr, rp, cyc, dist km')
for r in rows:
    if r[0]<=150:
        print(f"{r[0]:7.1f} {r[1]} {r[2]:14.14} {str(r[3]):22.22} Q100={r[4]:7.0f} u100={r[5]:6.2f} max={r[6]} {r[7]} T={r[8]} {r[9]} d={None if r[10] is None else round(r[10])}")
print('Near Block 2 within 60 km, any size')
for r in sorted(rows,key=lambda x:(x[10] is None, x[10])):
    if r[10] is not None and r[10]<=60:
        print(f"d={r[10]:5.1f} A={r[0]:7.1f} {r[1]} {r[2]:14.14} {str(r[3]):20.20} Q100={r[4]:7.0f} u100={r[5]:6.2f} max={r[6]} {r[7]} T={r[8]} {r[9]}")
north=[r for r in rows if r[3] and any(s in r[3] for s in ('Batinah','Buraymi','Dhahirah','Dakhliyah','Muscat'))]
print('n north',len(north))
A=np.array([r[0] for r in north]);U=np.array([r[5] for r in north])
for lo,hi in ((1,60),(60,150),(150,300),(300,600),(600,2000),(2000,1e5)):
    m=(A>=lo)&(A<hi)
    if m.sum(): print(lo,hi,m.sum(),'u100 median',round(np.median(U[m]),2),'p90',round(np.percentile(U[m],90),2),'max',round(U[m].max(),2))
print('Tc: station area tp tc kirpich ratio')
h=tc['header']; ki=h.index('Kirpich')-1
R=[]
for k,v in tc['t20'].items():
    e=tc['emp'].get(k)
    if e and e[ki]:
        R.append((v['area'],k,v['wadi'],v['tp'],v['tc'],e[ki],v['tc']/e[ki]))
R.sort()
for r in R: print(r[0],r[1],r[2],r[3],r[4],r[5],round(r[6],2))
print('median ratio',np.median([r[6] for r in R]))
