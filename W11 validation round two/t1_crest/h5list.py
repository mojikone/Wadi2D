import h5py,sys
f=h5py.File(sys.argv[1],'r')
g=f['Geometry']
print(list(g.keys()))
s=g['Structures']; print(list(s.keys()))
for k in s:
    if hasattr(s[k],'shape'): print(k,s[k].shape, s[k].dtype.names)
A=g['2D Flow Areas/Bidah']; print(A['Cells Center Coordinate'].shape, g['2D Flow Areas/Attributes'][()])
def walk(n,o):
    if ('Embank' in n or 'SA 2D' in n): print(n, getattr(o,'shape',None))
f.visititems(walk)
