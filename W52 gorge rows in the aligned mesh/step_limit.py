"""Which faces set the time step on the centre mesh, with and without gorge rows (W52): the kernel's wave frequency
(|u| + sqrt(g A dn / wet plan)) / dn read on each strip face at the run's final state, the faces ranked.

    .venv\Scripts\python "W52 gorge rows in the aligned mesh\step_limit.py" <case> <mesh> <rows>
"""

from __future__ import annotations

import sys

import fiona
import numpy as np

import gorges as g
from wadi2d.config import RunConfig
from wadi2d.run import prepare_grid
from wadi2d.solver.cpu.kernels import cell_level, cell_plan, face_lookup

F = np.float32
G = 9.81


def main(case: str, mesh: str, rows: int) -> None:
    name, data = g.job(case, mesh, tag=f"rows{rows}", strips={"gorge_rows": rows})
    cfg = RunConfig.model_validate(data)
    tables, _ = prepare_grid(cfg, g.HERE / "cache" / case)
    st = tables.strip
    m, strip = st.mesh, st.strip
    n = m.real
    run = g.RUNS / case / name
    level, qmax = np.zeros(n), np.zeros(m.nfaces)
    with fiona.open(run / "maps" / "strip_mesh.gpkg", layer="strip_cells") as src:
        for f in src:
            level[f["properties"]["cell"]] = f["properties"]["level_end_m"]
    with fiona.open(run / "maps" / "strip_mesh.gpkg", layer="strip_faces") as src:
        for k, f in enumerate(src):
            qmax[k] = f["properties"]["max_discharge_m3s"]
    d = np.maximum(level - m.zmin[:n], 0.0)
    hs = np.linspace(0.0, 15.0, 1501).astype(F)
    om = np.ones(n)
    for c in range(n):
        tab = np.ascontiguousarray(m.dtab[c], dtype=F)
        dd = np.array([cell_level(h, F(m.hc[c]), tab, m.rows) for h in hs])
        hb = F(np.interp(d[c], dd, hs))
        om[c] = float(cell_plan(hb, F(m.hc[c]), tab, m.rows))
    gorge = strip.gorge if strip.gorge is not None else np.zeros(n, int)
    out = []
    for f in range(m.nfaces):
        a, b = int(m.left[f]), int(m.right[f])
        if a >= n or b >= n:
            continue
        e_l, e_r = d[a] - m.fl[f], d[b] - m.fr[f]
        eup, up, down = (e_l, a, b) if e_l >= e_r else (e_r, b, a)
        if eup <= 0.05 or d[up] <= cfg.numerics.h_cfl:
            continue
        tab = np.ascontiguousarray(m.ftab[f].ravel(), dtype=F)
        A = float(face_lookup(F(eup), F(m.ef[f]), tab, m.rows)[0])
        wet = om[up] * m.area[up]
        if d[down] > cfg.numerics.h_cfl:
            wet = min(wet, om[down] * m.area[down])
        wave = np.sqrt(G * A * m.dn[f] / max(wet, cfg.numerics.plan_min * m.dx * m.dx))
        u = qmax[f] / max(A, 1e-6)
        out.append((f, (u + wave) / m.dn[f], m.dn[f], m.length[f], A, wet, u, wave, gorge[a], gorge[b], m.xf[f] - g.wp.X0))
    o = np.array(out)
    k = np.argsort(o[:, 1])[::-1]
    print(f"{name}: {len(o)} wet faces; step 0.45 / freq: smallest {0.45 / o[k[0], 1]:.3f} s, 1 % {0.45 / np.percentile(o[:, 1], 99):.3f} s, median {0.45 / np.median(o[:, 1]):.3f} s")
    print("   freq     dn   length     A    wet plan    u    wave  gorge(a,b)  x")
    for r in o[k[:12]]:
        print(f"  {r[1]:6.2f} {r[2]:6.2f} {r[3]:7.2f} {r[4]:7.1f} {r[5]:8.1f} {r[6]:6.2f} {r[7]:6.2f}   {int(r[8]):+d},{int(r[9]):+d}   {r[10]:7.1f}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]))
