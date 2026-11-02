import h5py, numpy as np, csv, sys
n=sys.argv[1]
f=h5py.File(f'ras_{n}/Bidah.p01.hdf','r')
print({k:(float(v) if not isinstance(v,(bytes,str)) else v) for k,v in f['Results/Unsteady/Summary/Volume Accounting'].attrs.items() if k not in('Precipitation Excess (mm)',)})
B='Results/Unsteady/Output/Output Blocks/Base Output/Unsteady Time Series/'
C=B+'2D Flow Areas/Bidah/2D Hyd Conn/Embankment/'
sv=f[C+'Structure Variables'][:].astype(float); t=f[B+'Time'][:]*24
m=f['Geometry/2D Flow Areas/Bidah']; nc=int(f['Geometry/2D Flow Areas/Attributes']['Cell Count'][0])
cc=m['Cells Center Coordinate'][:nc]
P=(438470.59,2726862.31)
j=int(np.argmin((cc[:,0]-P[0])**2+(cc[:,1]-P[1])**2))
wse=f[B+'2D Flow Areas/Bidah/Water Surface'][:,j].astype(float)
area=m['Cells Surface Area'][:nc]; info=m['Cells Volume Elevation Info'][:nc]; val=m['Cells Volume Elevation Values'][:]
wf=h5py.File(f'wadi_runs/{n}/results.h5','r')
keys=sorted(wf['maps'],key=lambda k:float(wf['maps'][k].attrs['t_s']))
print(list(wf['maps'][keys[0]].keys()))
x0,y0,dx=float(wf.attrs['x0']),float(wf.attrs['y0']),float(wf.attrs['dx'])
jj=int((y0-cc[j,1])/dx); ii=int((cc[j,0]-x0)/dx)
tw=np.array([float(wf['maps'][k].attrs['t_s'])/3600 for k in keys])
d=None
g0=wf['maps'][keys[0]]
name='level' if 'level' in g0 else 'depth'
lev=np.array([float(wf['maps'][k][name][jj,ii]) for k in keys])
print(name, wf['maps'][keys[0]][name].shape)
tq,qw=np.array(list(csv.reader(open(f'wadi_runs/{n}/series/line_crest.csv')))[1:],float).T
for h in (4,6,8,9,10,10.5,11,11.25,11.5,11.75,12,12.25,12.5,13,14,16,20,24,29.9):
    i=int(np.argmin(np.abs(t-h))); k=int(np.argmin(np.abs(tw-h))); q=int(np.argmin(np.abs(tq/3600-h)))
    print(h,'RAS z',round(wse[i],2),'Q',round(sv[i,0],1),'| Wadi lev',round(lev[k],2),'Q',round(qw[q],1))
