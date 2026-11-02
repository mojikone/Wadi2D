"""Cheap kernel fixes at generic lattice phases."""
import sys
sys.path.insert(0, ".")
import numpy as np
from concurrent.futures import ProcessPoolExecutor
import cases as C
from lattice import Lattice

def one(args):
    theta, cells, bank, offset, name, kw = args
    b, Q = C.WIDTHS[cells]
    z = C.bed(theta, b, bank, offset)
    yn = C.normal_depth(b, bank, Q); yw = C.normal_depth_wide(b, bank, Q)
    sc, tc = C.centres(theta, offset)
    band = np.abs(tc) < b/2 + bank*C.WALL + 6*C.DX
    m = Lattice(z, C.K, C.DX, C.N, C.SIDE, C.SIDE, band=band, **kw)
    sc, tc = C.setup(m, theta, b, bank, Q, yn, offset)
    deps=[]; qs=[]
    for t in np.arange(3600., 4001., 100.):
        m.advance(t); d_,q_=C.measure(m, sc, tc, yn, Q); deps.append(d_); qs.append(q_)
    d_=float(np.mean(deps))
    return (theta,cells,bank,offset,name,(d_/yn-1)*100,(d_/yw-1)*100,(np.mean(qs)/Q-1)*100,4000./m.nsteps)

if __name__ == "__main__":
    variants = [("base",{}),("m",dict(mirror=True)),("s2",dict(sheet=2)),("s3",dict(sheet=3)),("m+s2",dict(mirror=True,sheet=2)),("m+s3",dict(mirror=True,sheet=3)),("sheet0",dict(sheet=0))]
    jobs=[]
    for th,offs in ((45.,(0.,5.,10.)),(30.,(0.,)),(22.5,(0.,)),(15.,(0.,))):
        for off in offs:
            for cells in (3,6):
                for bank in (0.,2.):
                    for name,kw in variants:
                        jobs.append((th,cells,bank,off,name,kw))
    with ProcessPoolExecutor(11) as ex:
        res=list(ex.map(one,jobs))
    import collections
    tab=collections.OrderedDict()
    for r in res:
        tab.setdefault(r[:4],{})[r[4]]=r
    names=[n for n,_ in variants]
    print("err vs Manning %, then strip-reference % in the second block")
    print("theta cells bank off | "+" ".join(f"{n:>7s}" for n in names))
    for key,d in tab.items():
        print(f"{key[0]:5} {key[1]:2d} {key[2]} {key[3]:4} | "+" ".join(f"{d[n][5]:+7.2f}" for n in names))
    print("\nstrip reference")
    for key,d in tab.items():
        print(f"{key[0]:5} {key[1]:2d} {key[2]} {key[3]:4} | "+" ".join(f"{d[n][6]:+7.2f}" for n in names))
    print("\ndt mean, s")
    for key,d in tab.items():
        print(f"{key[0]:5} {key[1]:2d} {key[2]} {key[3]:4} | "+" ".join(f"{d[n][8]:7.3f}" for n in names))
