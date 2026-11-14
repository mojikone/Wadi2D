"""How much of the aligned pair's bend rise its tables alone explain (W52, diagnosis; no solver).

For the centre mesh of each gorge case: at every vertex of the stream line, the two station faces (the faces across
the channel that leave the line there) give K_i(h) from their tables; the normal depth the tables imply for a reach
is the h at which the mean friction slope over the stations, mean(Q^2 / K_i(h)^2), equals the bed slope. The rise of
that depth from the straight gorge to a sine is the part of the pair's bend rise that its station faces carry; the
rest of the solver's bend rise is the kernel's (momentum on two curved cells). Also the spoke lengths (line to far
node) on the inner and outer side of the bends, and the guide line's offset from the true axis.

    .venv\Scripts\python "W52 gorge rows in the aligned mesh\pair_depth.py" [20 10] [strips] [rows=N]
"""

from __future__ import annotations

import json
import sys

import numpy as np

import gorges as g
from wadi2d.config import RunConfig
from wadi2d.run import prepare_grid
from wadi2d.solver.cpu.kernels import face_lookup

F = np.float32
Q, S = 300.0, 0.01
H = np.arange(3.0, 8.0, 0.005)


def stations(case: str, mesh: str, law: str, strips: dict | None = None) -> dict:
    _name, data = g.job(case, mesh, strips=strips, tables={"face_conveyance": law})
    cfg = RunConfig.model_validate(data)
    tag = f"{case}_{law}" + ("" if not strips else "_" + "_".join(f"{k}{v}" for k, v in sorted(strips.items())))
    tables, _crs = prepare_grid(cfg, g.HERE / "cache" / "pair_depth" / tag)
    st = tables.strip
    geo, m, strip = st.strip.geometry, st.mesh, st.strip
    n = m.real
    line_edges = set().union(*strip.breakline_edges.values())
    on_line = {v for e in line_edges for v in e}
    keep_x = (m.xf > g.wp.X0 + 1200.0) & (m.xf < g.wp.X0 + 7400.0)
    by_vertex: dict[int, list[int]] = {}
    for f in range(m.nfaces):
        a, b = int(m.left[f]), int(m.right[f])
        if a >= n or b >= n or not keep_x[f]:
            continue
        na, nb = (int(v) for v in geo.face_node[st.kept[f]])
        if (min(na, nb), max(na, nb)) in line_edges:
            continue
        # a face across the channel that touches the line at one node (a spoke) or one cut from a spoke (rows)
        for node in (na, nb):
            if node in on_line:
                by_vertex.setdefault(node, []).append(f)
    pts, _arc = g.wp.curve(g.wp.CASES[case]["amp"])
    from scipy.spatial import cKDTree

    tree = cKDTree(pts)
    K, lengths, offsets, skew = [], [], [], []
    tang_all = np.gradient(pts, axis=0)
    for node, faces in by_vertex.items():
        if len(faces) != 2:
            continue
        k = np.zeros(H.size)
        for f in faces:
            tab = np.ascontiguousarray(m.ftab[f].ravel(), dtype=np.float32)
            top = F(m.ef[f])
            k += np.array([float(face_lookup(F(h), top, tab, m.rows)[1]) ** (5.0 / 3.0) for h in H])
        K.append(k)
        lengths.append([float(m.length[f]) for f in faces])
        dist, j = tree.query([geo.x[node], geo.y[node]])
        offsets.append(float(dist))
        t = tang_all[j] / np.hypot(*tang_all[j])
        for f in faces:  # the spoke's angle off the true section (the normal to the axis), degrees
            na, nb = (int(v) for v in geo.face_node[st.kept[f]])
            d = np.array([geo.x[nb] - geo.x[na], geo.y[nb] - geo.y[na]])
            skew.append(float(np.degrees(np.arcsin(min(1.0, abs(d @ t) / np.hypot(*d))))))
    K = np.asarray(K)
    sf = np.mean(Q * Q / np.maximum(K, 1e-9) ** 2, axis=0)
    h_normal = float(np.interp(S, sf[::-1], H[::-1]))
    L = np.asarray(lengths)
    return {
        "stations": int(K.shape[0]), "h_normal_tables_m": h_normal,
        "spoke_m_min": float(L.min()), "spoke_m_median": float(np.median(L)), "spoke_m_max": float(L.max()),
        "line_offset_m_median": float(np.median(offsets)), "line_offset_m_max": float(np.max(offsets)),
        "cells": int(n), "spoke_skew_deg_median": float(np.median(skew)), "spoke_skew_deg_p95": float(np.percentile(skew, 95)),
        "short_spokes_under_7m_share": float(np.mean(L < 7.2)),
    }  # fmt: skip


if __name__ == "__main__":
    sizes = [a for a in sys.argv[1:] if a in ("20", "10")] or ["20", "10"]
    laws = ["strips", "local_radius"] if "strips" in sys.argv else ["local_radius"]
    rows = next((int(a.split("=")[1]) for a in sys.argv[1:] if a.startswith("rows=")), 0)
    strips = {"gorge_rows": rows} if rows else None
    out = {}
    for law in laws:
        for size in sizes:
            ref = stations("narrow", f"ce{size}", law, strips)
            out[f"narrow_ce{size}_{law}"] = ref
            print(f"narrow ce{size} {law}: tables' normal depth {ref['h_normal_tables_m']:.3f} m, spokes {ref['spoke_m_min']:.2f} to {ref['spoke_m_max']:.2f} m", flush=True)
            for case in ("narrow_gentle", "narrow_sine"):
                r = stations(case, f"ce{size}", law, strips)
                r["rise_vs_straight_m"] = r["h_normal_tables_m"] - ref["h_normal_tables_m"]
                out[f"{case}_ce{size}_{law}"] = r
                print(f"{case} ce{size} {law}: tables' normal depth {r['h_normal_tables_m']:.3f} m, rise {r['rise_vs_straight_m']:+.3f} m;"
                      f" spokes {r['spoke_m_min']:.2f} / {r['spoke_m_median']:.2f} / {r['spoke_m_max']:.2f} m; line off the axis median {r['line_offset_m_median']:.2f}, max {r['line_offset_m_max']:.2f} m;"
                      f" spoke skew median {r['spoke_skew_deg_median']:.1f}, 95 % {r['spoke_skew_deg_p95']:.1f} deg; spokes shorter than the water's half-width {100 * r['short_spokes_under_7m_share']:.0f} %", flush=True)
    name = f"pair_depth_{'_'.join(sizes)}{'_rows' + str(rows) if rows else ''}.json"
    (g.HERE / name).write_text(json.dumps(out, indent=1), encoding="utf-8")
