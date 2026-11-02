import csv, numpy as np, rasterio, h5py
r=list(csv.reader(open("wadi_runs/fizh_gauge/series/line_z4c.csv")))[1:]
q=np.abs([float(x[1]) for x in r]); t=[float(x[0]) for x in r]
print('z4c peak',q.max(),'t',t[int(np.argmax(q))]/3600)
GX,GY=447523.0,2713540.0
with rasterio.open('wadi_runs/fizh_gauge/maps/max_mean_depth.tif') as s:
    d=s.read(1,masked=True).filled(0.0); tt=s.transform
with rasterio.open('wadi_runs/fizh_gauge/maps/max_speed.tif') as s:
    v=s.read(1,masked=True).filled(0.0)
c=int((GX-tt.c)/tt.a); r0=int((tt.f-(GY+2500))/-tt.e); r1=int((tt.f-(GY-2500))/-tt.e)
dd=d[r0:r1,c]; vv=v[r0:r1,c]
y=GY+2500-20*np.arange(len(dd))
wet=dd>0.2
print('wet width m at the section',wet.sum()*20,'of',len(dd)*20)
# threads
i=0
while i<len(dd):
    if wet[i]:
        j=i
        while j<len(dd) and wet[j]: j+=1
        q_est=(dd[i:j]*vv[i:j]*20).sum()
        print(f' thread y {y[j-1]:.0f}..{y[i]:.0f} width {20*(j-i)} m, max mean depth {dd[i:j].max():.2f}, q est (max d x max v) {q_est:.0f}')
        i=j
    else: i+=1
