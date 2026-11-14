"""What the aligned pair's tables say in a bend (W52, diagnosis): no solver, the tables alone.

For the centre mesh of a gorge case, at a water depth of 5.3 m over the bed: the conveyance and the area the two
station faces at each station carry together (the faces across the channel, the flow's own), the same for the face
on the thalweg (the face along the channel between the pair), and the water the two pair cells hold. Each is set
against the straight gorge's value on the same mesh size, where the pair reads the tables' own normal depth. A
table that read the bend differently would show here as a ratio off 1.

    .venv\\Scripts\\python "W52 gorge rows in the aligned mesh\\pair_tables.py" [20 10] [strips]
"""

from __future__ import annotations

import json
import sys

import numpy as np

import gorges as g
from wadi2d.config import RunConfig
from wadi2d.run import prepare_grid
from wadi2d.solver.cpu.kernels import cell_level, face_lookup

DEPTH = 5.3
F = np.float32


def reading(case: str, mesh: str, law: str, strips: dict | None = None) -> dict:
    _name, data = g.job(case, mesh, strips=strips, tables={"face_conveyance": law})
    cfg = RunConfig.model_validate(data)
    tables, _crs = prepare_grid(cfg, g.HERE / "cache" / "pair_tables" / f"{case}_{law}")
    st = tables.strip
    geo, mesh_, strip = st.strip.geometry, st.mesh, st.strip
    n = mesh_.real
    pair = (strip.row == 0) & (strip.corridor >= 0)
    line_edges = set().union(*strip.breakline_edges.values()) if strip.breakline_edges else set()
    rows = mesh_.rows
    x_mid = 0.5 * (geo.x.min() + geo.x.max())
    keep_x = (mesh_.xf > g.wp.X0 + 1200.0) & (mesh_.xf < g.wp.X0 + 7400.0)  # clear of the strip's ends
    k_station, a_station, k_line, a_line, x_station = [], [], [], [], []
    by_vertex: dict[tuple[int, int], list[int]] = {}
    for f in range(mesh_.nfaces):
        a, b = int(mesh_.left[f]), int(mesh_.right[f])
        if a >= n or b >= n or not (pair[a] and pair[b]) or not keep_x[f]:
            continue
        na, nb = (int(v) for v in geo.face_node[st.kept[f]])
        tab = np.ascontiguousarray(mesh_.ftab[f].ravel(), dtype=np.float32)
        area, t, _w = face_lookup(F(DEPTH), F(mesh_.ef[f]), tab, rows)
        conv = float(t) ** (5.0 / 3.0)
        if (min(na, nb), max(na, nb)) in line_edges:
            k_line.append(conv / mesh_.length[f])
            a_line.append(float(area) / mesh_.length[f])
        else:  # a station face: the two at one vertex of the line share the node on it
            for node in (na, nb):
                by_vertex.setdefault(node, []).append((f, conv, float(area)))
    on_line = {v for e in line_edges for v in e}
    for node, items in by_vertex.items():
        if node in on_line and len(items) == 2:
            k_station.append(items[0][1] + items[1][1])
            a_station.append(items[0][2] + items[1][2])
            x_station.append(float(geo.x[node]))
    # the pair cells' water at DEPTH over their lowest pixel plus half the cell's own bed drop (the mid-cell bed)
    vol = []
    hs = np.linspace(0.0, 12.0, 2401).astype(np.float32)
    cells = np.nonzero(pair[:n] & (mesh_.cx[:n] > g.wp.X0 + 1200.0) & (mesh_.cx[:n] < g.wp.X0 + 7400.0))[0]
    for c in cells:
        tab = np.ascontiguousarray(mesh_.dtab[c], dtype=np.float32)
        d = np.array([cell_level(h, F(mesh_.hc[c]), tab, rows) for h in hs])
        want = DEPTH + 0.5 * g.wp.S_BED * cfg.grid.dx
        vol.append(float(np.interp(want, d, hs)) * mesh_.area[c])
    del x_mid
    return {
        "station_faces": len(k_station), "K_station_mean": float(np.mean(k_station)), "K_station_min": float(np.min(k_station)),
        "K_station_max": float(np.max(k_station)), "A_station_mean": float(np.mean(a_station)),
        "K_line_per_m": float(np.mean(k_line)), "A_line_per_m": float(np.mean(a_line)), "pair_cells": int(cells.size),
        "pair_volume_per_m": float(np.sum(vol) / (0.5 * cells.size * cfg.grid.dx)),
        "k_station": k_station, "x_station": x_station,
    }  # fmt: skip


if __name__ == "__main__":
    sizes = [a for a in sys.argv[1:] if a in ("20", "10")] or ["20", "10"]
    laws = ["strips", "local_radius"] if "strips" in sys.argv else ["local_radius"]
    out = {}
    for law in laws:
        for size in sizes:
            ref = reading("narrow", f"ce{size}", law)
            for case in ("narrow_gentle", "narrow_sine"):
                r = reading(case, f"ce{size}", law)
                key = f"{case}_ce{size}_{law}"
                k = np.asarray(r.pop("k_station")) / ref["K_station_mean"]
                r.pop("x_station")
                out[key] = r | {
                    "K_station_vs_straight": r["K_station_mean"] / ref["K_station_mean"], "K_station_p05_p95": [float(np.percentile(k, 5)), float(np.percentile(k, 95))],
                    "A_station_vs_straight": r["A_station_mean"] / ref["A_station_mean"], "K_line_vs_straight": r["K_line_per_m"] / ref["K_line_per_m"],
                    "pair_volume_vs_straight": r["pair_volume_per_m"] / ref["pair_volume_per_m"],
                }  # fmt: skip
                o = out[key]
                print(f"{key}: station faces K {o['K_station_vs_straight']:.4f} of the straight gorge's (5 to 95 %: {o['K_station_p05_p95'][0]:.3f} to {o['K_station_p05_p95'][1]:.3f}),"
                      f" area {o['A_station_vs_straight']:.4f}; thalweg face K per m {o['K_line_vs_straight']:.4f}; pair cells' water per m {o['pair_volume_vs_straight']:.4f}", flush=True)
            ref.pop("k_station"), ref.pop("x_station")
            out[f"narrow_ce{size}_{law}"] = ref
    (g.HERE / "pair_tables.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
