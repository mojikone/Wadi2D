"""Refinement by change of slope against refinement by slope, on a synthetic valley.

Ground, across the valley: mountain plane 12 %, a slope break, plain 1 % down to a wadi with 1:1 banks 2.5 m high and a 60 m bed, plain 1 % back up. Along
the valley everything falls 0.5 % to the outlet. Rain 60 mm/h for 25 min, no losses, so the storm is shorter than the time of concentration and the peak depends on routing. Outlet: a dry row, so water leaves at the end of the valley.

Meshes are 2:1 balanced quadtrees of 40, 20 and 10 m cells on the polygon kernel, and uniform grids on the same kernel, so only the mesh differs.
Criterion by change of slope: split a block while its pixels leave a best-fit plane by more than eps. A tilted plane stays coarse however steep.
Criterion by slope: split where the mean slope of the block exceeds 3 %.
Reference: uniform 5 m. Cost is cell-steps, which is what a GPU run pays for.
"""
import csv
import sys
import time

sys.path.insert(0, ".")
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from graph import Graph, finish
from lattice import ROWS, cell_table
from meshes import FaceList, _empty_cells

W, H = 2200.0, 2000.0
PIX = 1.0
N_MAN = 0.04
RAIN = 60e-3 / 3600.0
T_RAIN = 1500.0
T_END = 7200.0
SECTIONS = (1000.0, 300.0)
WADI_X = 1832.0


def terrain():
    x = (np.arange(int(W)) + 0.5) * PIX
    y = (np.arange(int(H)) + 0.5) * PIX
    a = 1000.0
    bank_l, bed_l, bed_r, bank_r = 1800.0, 1802.5, 1862.5, 1865.0
    z = np.empty(x.size)
    plain_at_bank = 0.0
    z[:] = plain_at_bank
    m = x < a
    z[m] = plain_at_bank + 0.01 * (bank_l - a) + 0.12 * (a - x[m])
    m = (x >= a) & (x < bank_l)
    z[m] = plain_at_bank + 0.01 * (bank_l - x[m])
    m = (x >= bank_l) & (x < bed_l)
    z[m] = plain_at_bank - (x[m] - bank_l)
    m = (x >= bed_l) & (x < bed_r)
    z[m] = plain_at_bank - 2.5
    m = (x >= bed_r) & (x < bank_r)
    z[m] = plain_at_bank - 2.5 + (x[m] - bed_r)
    m = x >= bank_r
    z[m] = plain_at_bank + 0.01 * (x[m] - bank_r)
    return np.add.outer(0.005 * y, z)


def plane_residual(block):
    ny, nx = block.shape
    jj, ii = np.mgrid[0:ny, 0:nx]
    A = np.stack((jj.ravel().astype(float), ii.ravel().astype(float), np.ones(jj.size)), axis=1)
    c, *_ = np.linalg.lstsq(A, block.ravel(), rcond=None)
    return float(np.abs(block.ravel() - A @ c).max()), float(np.hypot(c[0], c[1]))


def quad_levels(z, rule, eps=0.2):
    """Cell size on a 10 m array: start at 40 m blocks, split by the rule, then 2:1 balance."""
    fine = 10
    ny, nx = int(H) // fine, int(W) // fine
    size = np.full((ny, nx), 40)
    for bj in range(0, ny, 4):
        for bi in range(0, nx, 4):
            blk = z[bj * fine : (bj + 4) * fine, bi * fine : (bi + 4) * fine]
            r, sl = plane_residual(blk)
            if rule == "change":
                split = r > eps
            else:
                split = sl > 0.03
            if not split:
                continue
            size[bj : bj + 4, bi : bi + 4] = 20
            for sj in (0, 2):
                for si in (0, 2):
                    b2 = blk[sj * fine : (sj + 2) * fine, si * fine : (si + 2) * fine]
                    if b2.size == 0:
                        continue
                    r2, sl2 = plane_residual(b2)
                    if (r2 > eps) if rule == "change" else (sl2 > 0.03):
                        size[bj + sj : bj + sj + 2, bi + si : bi + si + 2] = 10
    # 2:1 balance on the 10 m array
    for _ in range(4):
        changed = False
        for lv in (10, 20):
            m = size == lv
            near = m.copy()
            near[1:, :] |= m[:-1, :]
            near[:-1, :] |= m[1:, :]
            near[:, 1:] |= m[:, :-1]
            near[:, :-1] |= m[:, 1:]
            too = near & (size > 2 * lv)
            if too.any():
                for bj in range(0, ny, 4):
                    for bi in range(0, nx, 4):
                        if too[bj : bj + 4, bi : bi + 4].any():
                            size[bj : bj + 4, bi : bi + 4] = np.minimum(size[bj : bj + 4, bi : bi + 4], 2 * lv)
                changed = True
        if not changed:
            break
    return size


def cells_from(size, fine=10):
    ny, nx = size.shape
    ids = -np.ones((ny, nx), np.int64)
    blocks = []
    for j in range(ny):
        for i in range(nx):
            if ids[j, i] >= 0:
                continue
            s = size[j, i] // fine
            s = max(s, 1)
            # squares are aligned to their own size
            j0, i0 = j - j % s, i - i % s
            ids[j0 : j0 + s, i0 : i0 + s] = len(blocks)
            blocks.append((j0, i0, s))
    return ids, blocks


def build(z, ids, blocks, fine):
    nc = len(blocks)
    ce = _empty_cells(nc)
    tab = np.zeros(ROWS)
    f = int(fine / PIX)
    for c, (j, i, s) in enumerate(blocks):
        blk = z[j * f : (j + s) * f, i * f : (i + s) * f]
        zm, rel, hc = cell_table(blk.copy().ravel(), ROWS, tab)
        ce["Ac"][c] = (s * fine) ** 2
        ce["cx"][c] = (i + 0.5 * s) * fine
        ce["cy"][c] = (j + 0.5 * s) * fine
        ce["zmin"][c], ce["zbar"][c], ce["hc"][c] = zm, zm + rel, hc
        ce["dtab"][c] = tab
    ny, nx = ids.shape
    groups = {}
    # vertical fine edges
    jj, ii = np.nonzero(ids[:, :-1] != ids[:, 1:])
    for j, i in zip(jj, ii, strict=True):
        groups.setdefault((int(ids[j, i]), int(ids[j, i + 1]), 0), []).append((j, i + 1))
    jj, ii = np.nonzero(ids[:-1, :] != ids[1:, :])
    for j, i in zip(jj, ii, strict=True):
        groups.setdefault((int(ids[j, i]), int(ids[j + 1, i]), 1), []).append((j + 1, i))
    fl = FaceList()
    n_inv = 1.0 / N_MAN
    for (a, b, axis), edges in groups.items():
        prof = []
        for j, i in edges:
            if axis == 0:
                prof.append(np.maximum(z[j * f : (j + 1) * f, i * f - 1], z[j * f : (j + 1) * f, i * f]))
            else:
                prof.append(np.maximum(z[j * f - 1, i * f : (i + 1) * f], z[j * f, i * f : (i + 1) * f]))
        prof = np.concatenate(prof)
        ln = len(edges) * fine
        ej = np.mean([e[0] for e in edges])
        ei = np.mean([e[1] for e in edges])
        if axis == 0:
            fl.add(a, b, ln, 1.0, 0.0, ei * fine, (ej + 0.5) * fine, prof, PIX, n_inv)
        else:
            fl.add(a, b, ln, 0.0, 1.0, (ei + 0.5) * fine, ej * fine, prof, PIX, n_inv)
    return finish(ce, fl.done(), fine)


def run(name):
    z = terrain()
    t0 = time.time()
    if name.startswith("uniform"):
        fine = float(name.split()[1])
        ny, nx = int(H / fine), int(W / fine)
        size = np.full((ny, nx), int(fine))
        ids = np.arange(ny * nx).reshape(ny, nx)
        blocks = [(j, i, 1) for j in range(ny) for i in range(nx)]
    else:
        fine = 10.0
        size = quad_levels(z, "change" if "change" in name else "slope", eps=0.05 if "eps05" in name else 0.2)
        if "max20" in name:
            size = np.minimum(size, 20)
        ids, blocks = cells_from(size)
    me = build(z, ids, blocks, fine)
    m = Graph(me, fine, sheet=3)
    out_cells = np.nonzero(me.cy < 40.0)[0]  # the same outlet section on every mesh
    m.bcell = out_cells.astype(np.int64)
    m.bkind = np.zeros(out_cells.size, np.int64)
    m.bd0 = np.zeros(out_cells.size)
    m.bh0 = np.zeros(out_cells.size)
    is_out = np.zeros(me.Ac.size, bool)
    is_out[out_cells] = True
    into = is_out[me.L] != is_out[me.R]
    m.src[:] = RAIN
    m.src[out_cells] = 0.0
    wadi = (me.cx[me.R] > 1790.0) & (me.cx[me.R] < 1880.0) & into
    secs = [int(np.argmin(np.hypot(me.cx - WADI_X, me.cy - y))) for y in SECTIONS]
    zbed = [float(z[int(y), int(WADI_X)]) for y in SECTIONS]
    t_build = time.time() - t0
    t = 0.0
    qmax = 0.0
    qw_max = 0.0
    tpeak = 0.0
    dmax = [0.0, 0.0]
    vol_out = 0.0
    tm = time.time()
    last = 0.0
    while t < T_END - 1e-6:
        t = min(t + 30.0, T_END)
        if last < T_RAIN <= t:
            m.advance(T_RAIN)
            m.src[:] = 0.0
        m.advance(t)
        last = t
        sign = np.where(is_out[me.R], 1.0, -1.0)
        q = float((m.q[into] * sign[into]).sum())
        qw = float((m.q[wadi] * sign[wadi]).sum())
        vol_out += q * 30.0
        if q > qmax:
            qmax, tpeak = q, t
        qw_max = max(qw_max, qw)
        for n, c in enumerate(secs):
            dmax[n] = max(dmax[n], float(m.zmin[c] + m.d[c] - zbed[n]))
    return dict(
        name=name, cells=me.Ac.size, faces=me.L.size, steps=m.nsteps, cell_steps=me.Ac.size * m.nsteps, dt=m.t / m.nsteps, qpeak=qmax, qwadi=qw_max, tpeak=tpeak,
        d1000=dmax[0], d300=dmax[1], vol_out=vol_out, build_s=t_build, run_s=time.time() - tm,
        share10=float((size == 10).mean()) if not name.startswith("uniform") else 1.0, share40=float((size == 40).mean()) if not name.startswith("uniform") else 0.0,
    )  # fmt: skip


if __name__ == "__main__":
    names = ["uniform 5", "uniform 10", "uniform 20", "uniform 40", "quad by change of slope", "quad by slope"]
    with ProcessPoolExecutor(6) as ex:
        res = list(ex.map(run, names))
    ref = res[0]
    keys = list(res[0].keys())
    with open("results/valley.csv", "w", newline="") as f:
        w = csv.DictWriter(f, keys)
        w.writeheader()
        w.writerows(res)
    rain_vol = RAIN * T_RAIN * W * H
    print(f"rain volume {rain_vol:.0f} m3")
    print(f"{'mesh':26s} {'cells':>7s} {'steps':>7s} {'Gcs':>7s} {'x ref':>7s} {'Qpeak':>7s} {'%ref':>6s} {'Qwadi':>7s} {'%ref':>6s} {'tpk h':>6s} {'d1000':>6s} {'d300':>6s} {'vol %':>6s}")
    for r in res:
        print(f"{r['name']:26s} {r['cells']:7d} {r['steps']:7d} {r['cell_steps']/1e9:7.2f} {r['cell_steps']/ref['cell_steps']:7.3f} {r['qpeak']:7.1f} {(r['qpeak']/ref['qpeak']-1)*100:+6.1f} {r['qwadi']:7.1f} {(r['qwadi']/ref['qwadi']-1)*100:+6.1f} {r['tpeak']/3600:6.2f} {r['d1000']:6.3f} {r['d300']:6.3f} {r['vol_out']/rain_vol*100:6.1f}")
