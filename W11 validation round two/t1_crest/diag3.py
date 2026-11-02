import h5py, numpy as np, sys
n=sys.argv[1]; dt=int(sys.argv[2]) if len(sys.argv)>2 else 30
f=h5py.File(f'ras_{n}/Bidah.p01.hdf','r')
B='Results/Unsteady/Output/Output Blocks/Base Output/Unsteady Time Series/'
m=f['Geometry/2D Flow Areas/Bidah']; nc=int(f['Geometry/2D Flow Areas/Attributes']['Cell Count'][0])
area=m['Cells Surface Area'][:nc]; info=m['Cells Volume Elevation Info'][:nc]; val=m['Cells Volume Elevation Values'][:].astype(float)
t=f[B+'Time'][:]*24
W=f[B+'2D Flow Areas/Bidah/Water Surface']
bc={k:f[B+'Boundary Conditions'][k][:,1].astype(float) for k in ('OutEast','OutNorth')}
qout=bc['OutEast']+bc['OutNorth']
print('outflow sign peak',qout.max(),qout.min())
vout=np.concatenate(([0],np.cumsum(0.5*(np.abs(qout[1:])+np.abs(qout[:-1]))*np.diff(t)*3600)))
a=np.loadtxt('../../W1 research and design note/validation/ras_rain_on_grid/excess_5min.csv',delimiter=',',skiprows=1)
cum=np.interp(t*60,np.concatenate(([0],a[:,0])),np.concatenate(([0],np.cumsum(a[:,1]))))/1000*area.sum()
def vol(w):
    v=np.zeros(nc)
    for c in range(nc):
        s,k=info[c]; z=val[s:s+k,0]; y=val[s:s+k,1]
        v[c]=np.interp(w[c],z,y)+max(w[c]-z[-1],0)*area[c]
    return v
SV=f[B+'2D Flow Areas/Bidah/2D Hyd Conn/Embankment/Structure Variables'][:,0].astype(float)
vs=np.concatenate(([0],np.cumsum(0.5*(SV[1:]+SV[:-1])*np.diff(t)*3600)))
for i in range(0,len(t),dt*4 if len(t)>1000 else dt):
    v=vol(W[i,:nc].astype(float)).sum()
    print(round(t[i],1),'rain',round(cum[i]/1e6,3),'out',round(vout[i]/1e6,3),'stored',round(v/1e6,3),'error (stored+out-rain)',round((v+vout[i]-cum[i])/1e6,3),'crest vol',round(vs[i]/1e6,3))
