import csv, collections, math
rows=list(csv.DictReader(open('results/matrix.csv')))
num=lambda r,k: float(r[k]) if r.get(k) not in ('',None) else math.nan
names=["a","m","ms3","dir","P","b","c","t20","t26"]
fails=[r for r in rows if r['blew'] or not r['err'] or math.isnan(num(r,'err'))]
print("runs",len(rows),"failed",len(fails),collections.Counter(r['name'] for r in fails))
for r in fails[:6]: print({k:r[k] for k in ('name','theta','cells','bank','offset','blew')})
def sel(n,**kw):
    out=[r for r in rows if r['name']==n and r['err']!='' and not math.isnan(num(r,'err'))]
    for k,v in kw.items(): out=[r for r in out if float(r[k])==v]
    return out
print("\nPASS CASE: vertical walls, 3 cells, 45 deg. err vs Manning: phase 0 | all 8 phases min..max | strip min..max | dt ratio to a (worst, by phase)")
base={float(r['offset']):num(r,'dt') for r in sel('a',theta=45,cells=3,bank=0)}
for n in names:
    q=sel(n,theta=45,cells=3,bank=0)
    e=[num(r,'err') for r in q]; st=[num(r,'err_strip') for r in q]
    p0=[num(r,'err') for r in q if float(r['offset'])==0]
    ratio=[num(r,'dt')/base[float(r['offset'])] for r in q]
    print(f"{n:4s} {p0[0]:+6.2f} | {min(e):+6.2f} .. {max(e):+6.2f} | {min(st):+6.2f} .. {max(st):+6.2f} | dt/a {min(ratio):.2f}..{max(ratio):.2f} n={len(q)}")
print("\nWORST ABS STRIP ERROR over phases, by angle (3 cells vertical / 3 cells 2:1 / 6 vertical / 6 2:1 / 12 vertical / 12 2:1)")
for th in (0,15,22.5,30,45):
    print(f"theta {th}")
    for n in names:
        cells=[]
        for c in (3,6,12):
            for b in (0,2):
                q=sel(n,theta=th,cells=c,bank=b)
                v=[num(r,'err_strip') for r in q]
                cells.append(max(v,key=abs) if v else math.nan)
        print(f"  {n:4s} "+" ".join(f"{x:+7.2f}" for x in cells))
print("\nALL 30 x 3 cases: max |err vs Manning|, max |strip|, max |Q err|, dt/a median, dt/a worst")
b_dt={(r['theta'],r['cells'],r['bank'],r['offset']):num(r,'dt') for r in sel('a')}
for n in names:
    q=[r for r in sel(n) if float(r['offset']) in (0,5,10)]
    rs=sorted(num(r,'dt')/b_dt[(r['theta'],r['cells'],r['bank'],r['offset'])] for r in q)
    print(f"{n:4s} n={len(q):3d} {max(abs(num(r,'err')) for r in q):6.2f} {max(abs(num(r,'err_strip')) for r in q):6.2f} {max(abs(num(r,'qerr')) for r in q):6.2f}  dt/a median {rs[len(rs)//2]:.2f} worst {rs[0]:.2f}; vertical-only worst {min(num(r,'dt')/b_dt[(r['theta'],r['cells'],r['bank'],r['offset'])] for r in q if float(r['bank'])==0):.2f}")
print("\nCell and face counts, band, 45 deg 3 cells vertical")
for n in names:
    q=sel(n,theta=45,cells=3,bank=0,offset=0)[0]
    print(n,q['nelem'],q['nfaces'],q['dn_min'],q['area_min'],q['skew_max'],q['split_cells'],q['clipped_dn'])
print("\nPhase table 45 deg vertical, err vs Manning")
offs=[0,2.5,5,7.5,10,12.5,15,17.5]
for n in names:
    d={float(r['offset']):num(r,'err') for r in sel(n,theta=45,cells=3,bank=0)}
    print(f"{n:4s} "+" ".join(f"{d.get(o,math.nan):+6.2f}" for o in offs))
