"""The small and near gauges of the 2331 report in one table, K at each, for the README."""
import json, numpy as np
a=json.load(open('stations_2331.json'))
near=json.load(open('stations_all.json'))
def K(q,A): return 10*(1-(np.log10(q)-6)/(np.log10(A)-8))
for k in ['DC417300AD','DC434816AD','DC237976AD','DN241238AD','DB496929AD','DN257177AD','DB839224AD','EL887952AD','FL295527AD','FM305151AD','FA395799AD','EA350697AD']:
    v=a[k];A=v.get('area') or v['area21'];q=v['q']
    print(f"| {k} | {v['wadi']} | {A:.0f} | {v.get('max'):.0f} ({v.get('year')}) | {v.get('rp')} | {q['100']:.0f} | {q['100']/A:.1f} | {K(q['100'],A):.2f} |")
print(sorted((round(K(v['q']['100'],v.get('area') or v['area21']),2),k) for k,v in a.items() if v.get('gov') and any(s in v['gov'] for s in ('Batinah','Buraymi','Dhahirah','Dakhliyah','Muscat')))[-5:])
