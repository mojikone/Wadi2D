"""Why the Bidah dam's pool is refused at 100 m: the held components beside each crest piece, by side, with sizes.

usage: python s01_pool_sides.py <the dock's runs/spillway/job.json> [level]
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wadi2d.dam_levels import _beside, _components, _dam
from wadi2d.forcing import boundary_set
from wadi2d.run import load_job, prepare_grid
from wadi2d.terrain.sections import with_tables


def main(job_path: Path, level: float) -> None:
    cfg = with_tables(load_job(job_path))
    tables, _crs = prepare_grid(cfg, Path(cfg.grid.cache_dir))
    bset = boundary_set(cfg.boundaries, tables, cfg.grid.line_samples)
    component, _flat = _components(tables, level)
    leaking = set(np.unique(component[bset.mask & (component >= 0)]).tolist())
    sizes = np.bincount(component[component >= 0].ravel())
    name = cfg.dam_levels[0].name
    for n, piece in enumerate(_dam(cfg, name)):
        labels, sides = _beside(tables, component, piece)
        print(f"piece {n}: {len(piece.coordinates)} vertices, {labels.size} wet cells beside it")
        for label in sorted(set(labels.tolist())):
            on = sorted(set(sides[labels == label].tolist()))
            state = "reaches a boundary" if label in leaking else "held"
            print(f"   component {label}: {sizes[label]} cells, {state}, sides {on}")
    dx = tables.grid.dx
    print(f"boundary cells {int(bset.mask.sum())}, cell {dx} m")


if __name__ == "__main__":
    main(Path(sys.argv[1]), float(sys.argv[2]) if len(sys.argv) > 2 else 100.0)
