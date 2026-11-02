import numpy as np, rasterio, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
z=np.load('layers_5m.npz'); his,w2,w7,mask=z['his'],z['w2'],z['w7'],z['mask']; t=rasterio.Affine(*z['t'])
print('W7 finite in mask km2',(np.isfinite(w7)&mask).sum()*25e-6)
k=8; ny,nx=his.shape[0]//k,his.shape[1]//k
def block(x): return x[:ny*k,:nx*k].reshape(ny,k,nx,k).any(axis=(1,3))
a=block(np.nan_to_num(his,nan=-1)>=.3); b=block(np.nan_to_num(w7,nan=-1)>=.3)
img=np.ones((ny,nx,3)); img[a&~b]=(.1,.3,.9); img[b&~a]=(.9,.2,.1); img[a&b]=(.1,.1,.1)
plt.figure(figsize=(11,10)); plt.imshow(img,extent=(t.c,t.c+nx*k*5,t.f-ny*k*5,t.f),interpolation='nearest'); plt.title('Black both, blue his only, red W7 hybrid only, 0.3 m'); plt.tight_layout(); plt.savefig('fig_extent_w7.png',dpi=65)
for s,lab in ((np.nan_to_num(w7,nan=-1),'w7'),(np.nan_to_num(w2,nan=-1),'w2'),(np.nan_to_num(his,nan=-1),'his')):
    print(lab,[round(float((s>=d).sum()*25e-6),1) for d in (0.05,0.1,0.3,0.5,1,2,5)])
