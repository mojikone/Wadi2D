"""lattice_fast must give the same numbers as lattice."""
import sys
sys.path.insert(0, ".")
import numpy as np
import cases as C
import lattice, lattice_fast
out = []
for mod, kw in ((lattice, {}), (lattice_fast, {}), (lattice, dict(mirror=True)), (lattice_fast, dict(mirror=True))):
    b, Q = C.WIDTHS[3]
    z = C.bed(30.0, b, 0.0, 5.0)
    yn = C.normal_depth(b, 0.0, Q)
    sc, tc = C.centres(30.0, 5.0)
    m = mod.Lattice(z, C.K, C.DX, C.N, C.SIDE, C.SIDE, band=np.abs(tc) < b / 2 + 6 * C.DX, **kw)
    C.setup(m, 30.0, b, 0.0, Q, yn, 5.0)
    m.advance(300.0)
    out.append(m.h.copy())
print("max depth difference, baseline", np.abs(out[0] - out[1]).max(), " mirror", np.abs(out[2] - out[3]).max())
