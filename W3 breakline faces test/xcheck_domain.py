"""Port against the twin on the identical padded domain; then steadiness and lattice phase on the port."""
import sys, time
sys.path.insert(0, ".")
import numpy as np
import cases as C
from lattice import Lattice

def recorded_domain(theta, b, bank, Q):
    # as channel_scan: 160 x 160 grid, centred bed, cells 1..128 active
    nx = 160
    z = C.bed(theta, b, bank, side=nx)
    yn = C.normal_depth(b, bank, Q)
    mask = np.zeros((nx, nx), bool); mask[1:129, 1:129] = True
    sc, tc = C.centres(theta, 0.0, side=nx)
    band = np.abs(tc) < b/2 + bank*C.WALL + 6*C.DX
    m = Lattice(z, C.K, C.DX, C.N, nx, nx, mask=mask, band=band)
    level = -sc*C.S + yn
    hb = m.hbar_at_level(level)
    hb = np.where(np.abs(tc) < b/2 + bank*yn + 2*C.DX, hb, 0.0)
    m.set_depth(hb)
    lim = 0.45*128*C.DX
    up = (sc > -lim) & (sc < -lim+120) & (np.abs(tc) < b/2 + C.DX)
    rate = np.zeros((nx, nx)); rate[up] = Q/(up.sum()*C.DX*C.DX)
    m.set_source(rate)
    down = (sc > lim-120) & (sc < lim) & (np.abs(tc) < b + 3*C.DX)
    jj, ii = np.nonzero(down)
    m.set_boundary(jj, ii, np.maximum((level-m.zmin)[down], 0.0), hb[down])
    m.advance(C.T_END)
    mid = (np.abs(sc) < 0.15*128*C.DX) & (np.abs(tc) < 0.71*C.DX)
    dep = (m.zmin + m.field(m.d) + sc*C.S)[mid]
    return (np.mean(dep)/yn-1)*100, m.nsteps

print("port on the recorded domain (twin: v3 +2.01, b3 +1.94, v6 +0.99, b6 +0.85, 30 v3 +4.54, 30 b3 +4.15)")
for theta,b,bank,Q in ((45,60,0,60),(45,60,2,60),(45,120,0,150),(45,120,2,150),(30,60,0,60),(30,60,2,60)):
    t0=time.time(); r,ns=recorded_domain(theta,float(b),float(bank),float(Q)); print(f"{theta} b{b} bank{bank}: {r:+.2f}  steps {ns}  {time.time()-t0:.1f}s", flush=True)
