"""W1 channel_scan.run verbatim on the production CPU twin (float32), then the same cases on the port.

channel_scan is imported read-only and its module global `backend` is set to "cpu": select_backend then never imports CuPy.
Run with PYTHONDONTWRITEBYTECODE=1 and NUMBA_CACHE_DIR outside the repository, so nothing is written under wadi2d/.
"""
import importlib.util, io, contextlib, sys, time
sys.path.insert(0, ".")
import cases as C
from lattice import Lattice

path = r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\prototypes\channel_scan.py"
spec = importlib.util.spec_from_file_location("channel_scan", path)
cs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cs)
cs.backend = "cpu"
assert "cupy" not in sys.modules


def port(theta, b, bank, Q):
    z = C.bed(theta, b, bank)
    yn = C.normal_depth(b, bank, Q)
    m = Lattice(z, C.K, C.DX, C.N, C.SIDE, C.SIDE)
    sc, tc = C.setup(m, theta, b, bank, Q, yn)
    t0 = time.time()
    m.advance(C.T_END)
    dep, qs = C.measure(m, sc, tc, yn, Q)
    return dep, yn, m.nsteps, time.time() - t0, qs


print("theta b bank Q | twin err% sec | port err% steps sec | Qsec err%", flush=True)
for theta, b, bank, Q in ((45, 60, 0, 60), (45, 60, 2, 60), (45, 120, 0, 150), (45, 120, 2, 150), (45, 30, 2, 20), (30, 60, 0, 60), (30, 60, 2, 60), (0, 60, 0, 60)):
    t0 = time.time()
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            r = cs.run(theta, float(b), float(bank), float(Q))
        twin = f"{r*100:+7.2f} {time.time()-t0:6.1f}"
    except Exception as e:
        twin = f"failed: {type(e).__name__}: {e}"
    dq, yn, sq, tq, qs = port(theta, float(b), float(bank), float(Q))
    print(f"{theta:3d} {b:4d} {bank} {Q:4d} | {twin} | {(dq/yn-1)*100:+7.2f} {sq:5d} {tq:6.1f} | {(qs/Q-1)*100:+6.2f}", flush=True)
assert "cupy" not in sys.modules
print("cupy never imported", flush=True)
