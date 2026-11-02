import h5py, numpy as np, sys
n=sys.argv[1]
f=h5py.File(f'ras_{n}/Bidah.p01.hdf','r')
B='Results/Unsteady/Output/Output Blocks/Base Output/Unsteady Time Series/'
C=B+'2D Flow Areas/Bidah/2D Hyd Conn/Embankment/'
print(dict((k,(float(v) if not isinstance(v,(bytes,str)) else v)) for k,v in f['Results/Unsteady/Summary/Volume Accounting'].attrs.items()))
pd=f['Geometry/Structures/Profile Data'][:]
print('profile',pd.shape,pd[:3],pd[-3:],'min z',pd[:,1].min(),'max',pd[:,1].max())
print('stations where z>94.01', pd[pd[:,1]>94.01,0].min(), pd[pd[:,1]>94.01,0].max())
q=f[C+'HW TW Segments/Flow'][:]; hw=f[C+'HW TW Segments/Water Surface HW'][:]; tw=f[C+'HW TW Segments/Water Surface TW'][:]; st=f[C+'HW TW Segments/HW TW Station'][:]
sv=f[C+'Structure Variables'][:]
ip=int(np.argmax(sv[:,0]))
print('peak idx',ip,'shape',q.shape, 'total',sv[ip,:])
print('segments flow sum at peak',np.nansum(q[ip]))
for k in range(0,q.shape[1],6):
    print(round(float(st[k]),1),'q',round(float(q[ip,k]),2),'hw',round(float(hw[ip,k]),2),'tw',round(float(tw[ip,k]),2))
wv=f[C+'Weir Variables'][:]
print([x[0].decode() for x in f[C+'Weir Variables'].attrs['Variable_Unit']])
print(wv[ip])
# time of first flow
t=f[B+'Time'][:]*24
k=np.nonzero(sv[:,0]>1)[0]; print('first >1 m3/s',t[k[0]], 'value',sv[k[0],0])
for i in range(k[0],k[0]+60,8): print(round(t[i],2),np.round(sv[i],2), 'segs flowing',int((np.abs(q[i])>0.01).sum()),'q by seg top',np.round(np.sort(q[i])[-3:],1))
