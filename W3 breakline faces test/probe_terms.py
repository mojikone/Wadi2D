"""Which term carries the rotated-channel error, and how much does the lattice phase move it?"""
import sys
sys.path.insert(0, ".")
import numpy as np
from concurrent.futures import ProcessPoolExecutor
import cases as C
from lattice import Lattice

def one(args):
    theta, cells, bank, offset, kw = args
    b, Q = C.WIDTHS[cells]
    z = C.bed(theta, b, bank, offset)
    yn = C.normal_depth(b, bank, Q)
    yw = C.normal_depth_wide(b, bank, Q)
    sc, tc = C.centres(theta, offset)
    band = np.abs(tc) < b/2 + bank*C.WALL + 6*C.DX
    m = Lattice(z, C.K, C.DX, C.N, C.SIDE, C.SIDE, band=band, **kw)
    sc, tc = C.setup(m, theta, b, bank, Q, yn, offset)
    deps=[]; qs=[]
    for t in np.arange(3600., 4001., 100.):
        m.advance(t); d_,q_=C.measure(m, sc, tc, yn, Q); deps.append(d_); qs.append(q_)
    d_=float(np.mean(deps))
    return (theta,cells,bank,offset,kw,(d_/yn-1)*100,(d_/yw-1)*100,(np.mean(qs)/Q-1)*100,4000./m.nsteps)

if __name__ == "__main__":
    variants = [("base",{}),("adv off",dict(adv=False)),("no 2nd order",dict(second=False)),("sheet off",dict(sheet=False)),("mirror",dict(mirror=True)),("vbopen",dict(vbopen=True)),("mirror+vbopen",dict(mirror=True,vbopen=True))]
    jobs=[]
    for th in (45.,30.,22.5,15.):
        for bank in (0.,2.):
            for name,kw in variants:
                jobs.append((th,3,bank,0.,kw))
    # phase scan of the baseline
    ph=[]
    for th in (45.,30.):
        for cells,bank in ((3,0.),(3,2.),(6,0.)):
            for off in (0.,2.5,5.,7.5,10.,12.5,15.,17.5):
                ph.append((th,cells,bank,off,{}))
    with ProcessPoolExecutor(11) as ex:
        res=list(ex.map(one,jobs+ph))
    lookup={str(kw):n for n,kw in variants}
    print("theta cells bank variant | err vs Manning % | err vs strip % | Q err % | dt mean")
    for r in res[:len(jobs)]:
        print(f"{r[0]:5} {r[1]} {r[2]} {lookup[str(r[4])]:14s} {r[5]:+7.2f} {r[6]:+7.2f} {r[7]:+6.2f} {r[8]:.3f}")
    print("\nphase scan, baseline: theta cells bank offset err-vs-Manning")
    for r in res[len(jobs):]:
        print(f"{r[0]:5} {r[1]} {r[2]} {r[3]:5} {r[5]:+7.2f}  strip {r[6]:+7.2f}")
