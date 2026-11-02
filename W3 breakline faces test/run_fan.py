"""Real terrain: the 3 x 3 km Block 2 fan of W1, against the HEC-RAS 6.6 SWE-EM runs, baseline and mirror on the same lattice port.

Inputs are read, not written: the DEM clip and job of W1/validation/ras_head_to_head. Same hydrograph, Manning 0.04, normal-depth edges. Inflows enter at the cell
under each point, which is simpler than production's injection; the check on that is the first line printed, the port against the frozen GPU run.
"""
import json, sys
sys.path.insert(0, ".")
import h5py
import numpy as np
import rasterio
from lattice import Lattice

V = r"D:/Mojtaba/Renardet/Wadi2D/W1 research and design note/validation/ras_head_to_head/"
X0, Y0, SIDE, S = 436999.98973783385, 2728999.893463373, 3000.0, 0.015
SHEET = 1
BASE = "Results/Unsteady/Output/Output Blocks/Base Output/Summary Output/2D Flow Areas/Fan"


def ras_lattice(dx):
    n = round(SIDE / dx)
    with h5py.File(V + f"ras_{int(dx)}m_swe_em/Fan.p01.hdf", "r") as f:
        m = f["Geometry/2D Flow Areas/Fan"]
        c = int(f["Geometry/2D Flow Areas/Attributes"]["Cell Count"][0])
        cc = m["Cells Center Coordinate"][:c]
        col = np.round((cc[:, 0] - X0) / dx - 0.5).astype(int)
        row = np.round((Y0 - cc[:, 1]) / dx - 0.5).astype(int)
        wse = f[BASE]["Maximum Water Surface"][0, :c]
        zmin = m["Cells Minimum Elevation"][:c]
    a = np.full((n, n), np.nan)
    b = np.full((n, n), np.nan)
    ok = (row >= 0) & (row < n) & (col >= 0) & (col < n)
    a[row[ok], col[ok]] = wse[ok]
    b[row[ok], col[ok]] = zmin[ok]
    return a, b


def run(dx, mirror):
    k = int(round(dx / 0.5))
    n = round(SIDE / dx)
    with rasterio.open(V + "terrain/fan_window_0p5m.tif") as d:
        c0 = round((X0 - d.transform.c) / d.transform.a)
        r0 = round((Y0 - d.transform.f) / d.transform.e)
        arr = d.read(1).astype(np.float64)
    arr = np.pad(arr, 2, mode="edge")
    z = arr[r0 + 2 - 1 : r0 + 2 + n * k + 1, c0 + 2 - 1 : c0 + 2 + n * k + 1]
    job = json.load(open(V + f"job_{int(dx)}m.json"))
    # cells near the frozen 20 m wet map only: nine tenths of the window never wets
    with rasterio.open(V + "wadi_runs/w20m/maps/max_level.tif") as d:
        fz = d.read(1, masked=True).filled(np.nan)[1:151, 1:151]
    w = np.isfinite(fz)
    for _ in range(8):
        g = w.copy()
        g[1:, :] |= w[:-1, :]; g[:-1, :] |= w[1:, :]; g[:, 1:] |= w[:, :-1]; g[:, :-1] |= w[:, 1:]
        w = g
    band = np.kron(w, np.ones((round(20 / dx), round(20 / dx)), bool)) if dx < 20 else w
    m = Lattice(z, k, dx, 0.04, n, n, mirror=mirror, mask=band, sheet=SHEET)
    # edges: east column and north row follow an inner cell lowered by S dx, as forcing._one_boundary
    east = [(j, n - 1) for j in range(n)]
    north = [(0, i) for i in range(n - 1)]
    cells = east + north
    taken = np.zeros((n, n), bool)
    for c in cells:
        taken[c] = True
    jj, ii, rj, ri, d0, kind = [], [], [], [], [], []
    for j, i in cells:
        opts = [(a, b) for a, b in ((j - 1, i), (j + 1, i), (j, i - 1), (j, i + 1)) if 0 <= a < n and 0 <= b < n and not taken[a, b]]
        jj.append(j); ii.append(i)
        if not opts:
            rj.append(j); ri.append(i); d0.append(0.0); kind.append(1)
            continue
        a, b = max(opts, key=lambda q: m.zbar[q])
        rj.append(a); ri.append(b); d0.append(min(m.zmin[a, b] - m.zmin[j, i] - S * dx, 0.0)); kind.append(2)
    m.set_boundary(np.array(jj), np.array(ii), np.array(d0), np.zeros(len(jj)), np.array(kind, np.int64), (np.array(rj), np.array(ri)))
    inf = job["hydrology"]["inflows"]
    pj = np.array([min(int((Y0 - q["y"]) / dx), n - 1) for q in inf])
    pi = np.array([min(int((q["x"] - X0) / dx), n - 1) for q in inf])
    times = np.array(inf[0]["times_s"])
    flows = np.array([q["flows"] for q in inf])
    own = m._own()
    idx = own[pj * n + pi]
    lvl = np.full((n, n), -1e9)
    T = job["run"]["duration_s"]
    t = 0.0
    while t < T - 1e-6:
        q = np.array([np.interp(t + 15.0, times, f) for f in flows])
        m.src[:] = 0.0
        np.add.at(m.src, idx, q / dx**2)
        t = min(t + 30.0, T)
        m.advance(t)
        h = m.field(m.h)
        e = m.zmin + m.field(m.d)
        lvl = np.where(h > 1e-3, np.maximum(lvl, e), lvl)
    return lvl, m.nsteps


def one(a):
    global SHEET
    SHEET = a[2]
    return run(a[0], a[1])


def score(lvl, ras, zr, name):
    wet = (ras - zr) > 0.5
    good = wet & (lvl > -1e8)
    d = (lvl - ras)[good]
    # extent, cells at 0.1 m
    a = (ras - zr) >= 0.1
    b = (lvl - zr) >= 0.1
    F = (a & b).sum() / max((a | b).sum(), 1)
    print(f"{name:18s} level mean {d.mean()*100:+6.2f} cm rms {np.sqrt((d**2).mean())*100:6.2f} cm  p5 {np.percentile(d,5)*100:+6.1f} p95 {np.percentile(d,95)*100:+6.1f}  F(0.1 m) {F:.3f}  n {good.sum()}", flush=True)


if __name__ == "__main__":
    dx = float(sys.argv[1])
    ras, zr = ras_lattice(dx)
    n = ras.shape[0]
    with rasterio.open(V + f"wadi_runs/w{int(dx)}m/maps/max_level.tif") as d:
        fz = d.read(1, masked=True).astype(np.float64).filled(-1e9)
    fz = fz[1:n + 1, 1:n + 1]
    score(fz, ras, zr, "frozen 3f32ca6 GPU")
    res = {}
    from concurrent.futures import ProcessPoolExecutor
    tags = (("port baseline", False, 1), ("port mirror", True, 1), ("port mirror s3", True, 3))
    with ProcessPoolExecutor(3) as ex:
        outs = list(ex.map(one, [(dx, a, b) for _, a, b in tags]))
    for (tag, _, _), (lvl, ns) in zip(tags, outs):
        res[tag] = lvl
        score(lvl, ras, zr, tag)
        print("  steps", ns, flush=True)
    a, b = res["port baseline"], res["port mirror"]
    wet = (ras - zr) > 0.5
    print(f"mirror minus baseline, wet cells: mean {(b-a)[wet].mean()*100:+.2f} cm, largest {np.abs((b-a)[wet]).max()*100:.1f} cm", flush=True)
