import numpy as np, rasterio
GGC5=r"D:/Mojtaba/Renardet/2224 WS11/Batinah/Block 2/Hydrology/Terrain/GGC_2_MERGE_HDSM_5.tif"
b=np.load('block02_c100.npz'); cc,wse,zmin,his,area=b['cc'],b['wse'],b['zmin'],b['his'],b['area']
with rasterio.open(GGC5) as s:
    g=np.array([v[0] for v in s.sample(cc.tolist())],float); nd=s.nodata
ok=(g!=nd)&(g>1)
for name,m in (('plain x>440k, small cells',(cc[:,0]>440000)&ok),('all',ok)):
    h=np.nan_to_num(his,nan=0.0)
    dm=wse-g
    for th in (0.1,0.3,1.0):
        a=(h>=th)&m; c=(dm>=th)&m
        print(name,th,'F',round((a&c).sum()/max((a|c).sum(),1),3),'layer',a.sum(),'model',c.sum())
    sel=m&(h>0.5)&(dm>0.5)
    d=(h-dm)[sel]; print(' depth diff layer-model at cells wet>0.5: median',np.median(d),'p5,95',np.percentile(d,[5,95]),'n',sel.sum())
