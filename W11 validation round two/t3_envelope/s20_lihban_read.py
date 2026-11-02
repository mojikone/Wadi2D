import csv, json, numpy as np
a=np.loadtxt('shaheen_5min.csv',delimiter=',',skiprows=1); tq,p,obs=a.T
out={}
for name,start in (('phi',-45.0),('fraction',-660.0)):
    r=np.array(list(csv.reader(open(f'wadi_runs/lihban_{name}/series/line_gauge.csv')))[1:],float)
    t=r[:,0]/60+start; q=np.abs(r[:,1])
    i=int(np.argmax(q))
    vol=np.trapezoid(q,r[:,0])/1e6
    k=(tq>=-100)&(tq<=800)
    sim=np.interp(tq[k],t,q,left=0,right=0)
    nse=1-((sim-obs[k])**2).sum()/((obs[k]-obs[k].mean())**2).sum()
    # lag of the two peaks: first peak of the simulated curve before minute 300
    m=(t<=300)
    print(name,'peak',round(q[i],0),'at min from 00:00',round(t[i],0),'vol',round(vol,1),'NSE',round(nse,3),'peak before 300 min',round(q[m].max(),0),'at',round(t[m][q[m].argmax()],0))
    out[name]=dict(peak=float(q[i]),t_min=float(t[i]),vol=float(vol),nse=float(nse),first_peak=float(q[m].max()),t_first=float(t[m][q[m].argmax()]))
json.dump(out,open('lihban_results.json','w'),indent=1)
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
plt.figure(figsize=(10,5)); plt.plot(tq/60,obs,'k',lw=2,label='Gauge DB839224AD')
for name,start,c in (('phi',-45.0,'#c8501e'),('fraction',-660.0,'#1f4e79')):
    r=np.array(list(csv.reader(open(f'wadi_runs/lihban_{name}/series/line_gauge.csv')))[1:],float)
    plt.plot(r[:,0]/3600+start/60,np.abs(r[:,1]),c,label=f'Wadi2D, {name} loss')
plt.xlim(-1,14); plt.grid(alpha=.3); plt.legend(); plt.xlabel('hours from 00:00 4 Oct 2021'); plt.ylabel('m3/s'); plt.title('Shaheen at Lihban, excess volume set to the observed volume'); plt.tight_layout(); plt.savefig('fig_lihban.png',dpi=80)
