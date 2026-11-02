import sys
sys.path.insert(0,'.')
from options import run
import time
for a in (("lattice",45,3,0.,0.),("P",45,3,0.,0.),("P",45,3,0.,5.),("P",30,3,0.,0.),("b",45,3,0.,0.),("b",45,3,0.,5.),("b",30,3,0.,0.),("c",45,3,0.,0.),("c",45,3,0.,5.),("c",30,3,0.,0.)):
    t=time.time()
    r=run(*a)
    print(a,{k:(round(v,3) if isinstance(v,float) else v) for k,v in r.items() if k not in('option','theta','cells','bank','offset')},round(time.time()-t,1),flush=True)
