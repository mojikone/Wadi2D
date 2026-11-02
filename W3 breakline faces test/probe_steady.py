"""Is 4000 s steady? And does the answer depend on where the wall falls on the lattice?"""
import sys, time
sys.path.insert(0, ".")
import numpy as np
from concurrent.futures import ProcessPoolExecutor
import cases as C
from lattice import Lattice

def one(args):
    theta, cells, bank, offset, times = args
    b, Q = C.WIDTHS[cells]
    z = C.bed(theta, b, bank, offset)
    yn = C.normal_depth(b, bank, Q)
    sc, tc = C.centres(theta, offset)
    band = np.abs(tc) < b/2 + bank*C.WALL + 6*C.DX
    m = Lattice(z, C.K, C.DX, C.N, C.SIDE, C.SIDE, band=band)
    sc, tc = C.setup(m, theta, b, bank, Q, yn, offset)
    out = []
    for t in times:
        m.advance(t)
        dep, qs = C.measure(m, sc, tc, yn, Q)
        out.append(((dep/yn-1)*100, (qs/Q-1)*100))
    return (theta, cells, bank, offset, out, m.nsteps)

if __name__ == "__main__":
    times = (2000., 3000., 4000., 6000., 8000., 12000., 16000.)
    jobs = [(45,3,0,0.,times),(45,3,2,0.,times),(30,3,0,0.,times),(22.5,3,0,0.,times),(15,3,0,0.,times),(0,3,0,0.,times),(45,6,0,0.,times),(45,12,0,0.,times)]
    with ProcessPoolExecutor(8) as ex:
        print("theta cells bank | depth err % at", times)
        for r in ex.map(one, jobs):
            print(r[0], r[1], r[2], " ".join(f"{a:+.2f}" for a,_ in r[4]), "| Q err at last", f"{r[4][-1][1]:+.2f}", flush=True)
