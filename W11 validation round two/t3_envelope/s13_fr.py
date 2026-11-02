import json, numpy as np
a=json.load(open('stations_2331.json'))
near=json.load(open('stations_all.json'))
def K(q,A): return 10*(1-(np.log10(q)-6)/(np.log10(A)-8))
def QK(k,A): return 1e6*(A/1e8)**(1-k/10)
print('K check station with report Table 54? Bidah HMS',K(362.4,20.97),'Bidah 2D',K(622,20.97))
for n,A,h,w in (('Faydh',74.3,993,1803),('R5A',117.1,887,1736),('R2A',175.9,1356,2820),('Z4C',211.1,1666,2316)):
    print(n,A,'HMS K',round(K(h,A),2),'u',round(h/A,1),'2D K',round(K(w,A),2),'u',round(w/A,1))
for k in ('DC417300AD','DC434816AD','DC237976AD','DN241238AD','DB496929AD','DN257177AD','DB388507AD','CC907987AD','DB839224AD','DM938388AD','FL295527AD','FM305151AD','FA395799AD','EA350697AD','EL887952AD'):
    v=a.get(k)
    if not v: print(k,'none');continue
    A=v.get('area') or v['area21']; q=v['q']['100']
    print(k,v['wadi'],'A',A,'Q100',q,'Q200',v['q']['200'],'K100',round(K(q,A),2),'read at 21 km2 ->',round(QK(K(q,A),21)/21,1),'max',v.get('max'),v.get('year'),'T',v.get('rp'),v.get('cyclone'))
north=[(v.get('area') or v.get('area21'),v['q']['100'],k,v.get('gov')) for k,v in a.items() if v.get('gov') and any(s in v['gov'] for s in ('Batinah','Buraymi','Dhahirah','Dakhliyah','Muscat'))]
A=np.array([x[0] for x in north],float);Q=np.array([x[1] for x in north],float)
m=A>0
b=np.polyfit(np.log(A),np.log(Q/A),1)
print('all north fit u=',np.exp(b[1]),'A^',b[0],'at 21:',np.exp(b[1])*21**b[0],'n',len(A),'resid sd log',np.std(np.log(Q/A)-np.polyval(b,np.log(A))))
sm=A<=300
b2=np.polyfit(np.log(A[sm]),np.log((Q/A)[sm]),1)
print('A<=300 fit',np.exp(b2[1]),b2[0],'at 21:',np.exp(b2[1])*21**b2[0],'n',sm.sum(),'sd',np.std(np.log((Q/A)[sm])-np.polyval(b2,np.log(A[sm]))))
ks=np.array([K(q,x) for x,q in zip(A,Q)])
print('K100 north: median',np.median(ks),'p10',np.percentile(ks,10),'p90',np.percentile(ks,90),'max',ks.max())
print('read at 21: median K ->',QK(np.median(ks),21)/21,'p10',QK(np.percentile(ks,10),21)/21,'p90',QK(np.percentile(ks,90),21)/21)
B=[k for k in ('DC417300AD','DC434816AD','DC237976AD','DN241238AD','DB496929AD','DN257177AD')]
kk=[K(a[k]['q']['100'],a[k].get('area') or a[k]['area21']) for k in B]
print('six nearest',np.round(kk,2),'mean',np.mean(kk),'read',QK(np.mean(kk),21)/21, 'min',QK(min(kk),21)/21,'max',QK(max(kk),21)/21)
