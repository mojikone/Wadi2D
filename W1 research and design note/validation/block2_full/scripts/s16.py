"""Escape level: the lowest level at which the pool reaches a cell downstream of the dam, and the face that lets it."""
import sys
from collections import deque
from pathlib import Path

import numpy as np

sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\block2_full\scripts")
from common import CACHE
from dams import DAM_LIST, NSA2, tied
from dams import job as dam_job
from s10_eav import RES, lowest_cell

from wadi2d.config.schema import RunConfig
from wadi2d.run import prepare_grid
from wadi2d.solver.layout import CLOSED
from wadi2d.terrain import apply_objects
import heapq

for dam in DAM_LIST.values():
    print(dam.name, [len(a) - len(b) for a, b in zip(tied(dam), dam.crest_lines)], [ (t[0], t[-1]) for t in tied(dam)])
    for dx in (20.0, 10.0):
        cfg = RunConfig.model_validate(dam_job(dam, "leak", dx, np.array([0.0, 3600.0]), np.array([0.0, 0.0]), 3600.0, dem=NSA2))
        tables, _ = prepare_grid(cfg, Path(CACHE))
        g = tables.grid
        crest = apply_objects(g, cfg.terrain.objects, 2.0).crest
        xc, yc = np.isfinite(crest.xz), np.isfinite(crest.yz)
        fx, fy = g.from_tiles(tables.flx), g.from_tiles(tables.fly)
        z = tables.zmin
        ny, nx = z.shape
        seed = lowest_cell(tables, RES[dam.name])
        target = g.cell_of(*dam.tailwater_point)
        # minimax path by Dijkstra on the level needed
        best = {seed: float(z[seed])}
        parent = {}
        pq = [(float(z[seed]), seed)]
        done = set()
        while pq:
            lv, c = heapq.heappop(pq)
            if c in done:
                continue
            done.add(c)
            if c == target:
                break
            j, i = c
            for a, b, fj, fi, f, cl, nl in ((j, i + 1, j, i + 1, fx, xc, (j, i)), (j, i - 1, j, i, fx, xc, (j, i - 1)), (j + 1, i, j + 1, i, fy, yc, (j, i)), (j - 1, i, j, i, fy, yc, (j - 1, i))):
                if not (0 <= a < ny and 0 <= b < nx) or not g.mask[a, b] or cl[fj, fi] or f[fj, fi] >= CLOSED * 0.5:
                    continue
                need = max(lv, float(z[nl] + f[fj, fi]))
                if need < best.get((a, b), 1e9):
                    best[(a, b)] = need
                    parent[(a, b)] = (j, i, float(z[nl] + f[fj, fi]))
                    heapq.heappush(pq, (need, (a, b)))
        lv = best.get(target)
        path = []
        c = target
        while c in parent:
            j, i, inv = parent[c]
            path.append((inv, c))
            c = (j, i)
        top = max(path)
        x, y = g.xy_of(np.array(top[1][0]), np.array(top[1][1]))
        px, py = g.xy_of(*np.array([c for _, c in path]).T)
        sj, si = seed
        print("   seed", g.xy_of(np.array(sj), np.array(si)), "zmin", z[seed], "path cells", len(path), "first", [(round(float(a)), round(float(b))) for a, b in zip(px[-6:], py[-6:])])
        print(f"  dx {dx}: escape level around the dam {lv:.2f} (crest {dam.crest}), at cell ({float(x):.0f}, {float(y):.0f})")
