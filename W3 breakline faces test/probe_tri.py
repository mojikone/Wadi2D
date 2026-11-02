import sys
sys.path.insert(0, ".")
from concurrent.futures import ProcessPoolExecutor
from options import run
CASES = [(45.,3,0.,0.),(45.,3,0.,5.),(45.,3,2.,5.),(30.,3,0.,0.),(30.,3,2.,0.),(22.5,3,0.,0.),(15.,3,0.,0.),(0.,3,0.,0.),(30.,12,0.,0.)]
def job(a):
    h, c = a
    return h, c, run("tri", *c, sheet=3, h=h)
if __name__ == "__main__":
    jobs=[(h,c) for h in (20.,26.3) for c in CASES]
    with ProcessPoolExecutor(11) as ex:
        for h,c,r in ex.map(job,jobs):
            print(h,c,{k:(round(r[k],3) if isinstance(r.get(k),float) else r.get(k)) for k in ("err_strip","err","qerr","dt","nelem","nfaces","clipped_dn","neg_dn","area_min","dn_min","skew_max","blew")},flush=True)
