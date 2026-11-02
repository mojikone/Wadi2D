import h5py, numpy as np, rasterio, json
for n in ('t0_base','t4_dx15','t3_ggc'):
    f=h5py.File(f'wadi_runs/{n}/results.h5','r')
    keys=sorted(f['maps'],key=lambda k:float(f['maps'][k].attrs['t_s']))
    g=f['maps'][keys[-1]]; m=g['mean_depth'][:]; dx=float(f.attrs['dx']); x0=float(f.attrs['x0']); y0=float(f.attrs['y0'])
    jj,ii=np.nonzero(m>0.5)
    print(n,'t_end',g.attrs['t_s']/3600,'volume in cells >0.5 m at end Mm3',round(m[m>0.5].sum()*dx*dx/1e6,1),'total',round(np.nansum(m)*dx*dx/1e6,1))
    x=x0+(ii+.5)*dx; y=y0-(jj+.5)*dx; v=m[jj,ii]*dx*dx/1e6
    for a,b in ((413000,440000),(440000,446000),(446000,450000),(450000,458000)):
        k=(x>=a)&(x<b); print('   x',a,b,'Mm3',round(v[k].sum(),1))
