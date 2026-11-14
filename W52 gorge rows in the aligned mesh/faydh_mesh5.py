"""The centre mesh at 5 m on Faydh's main-stem reach (W48 found the tiling guard refusing it, 233 m2 in 0.66 km2):
does it build now, mesh only. W47's steady reach job at 10 m set to 5 m cells and 5 m along.

    .venv\Scripts\python "W52 gorge rows in the aligned mesh\faydh_mesh5.py" [dx]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from wadi2d.config import RunConfig
from wadi2d.run import RasterBed, _domain_polygon, _wkt, domain_mask, grid_window, with_tables
from wadi2d.strips.build import mask_for_strips

JOB = Path(r"D:\Mojtaba\Renardet\Wadi2D\W47 face level carried to the face\depth_carry\steady\ce10.json")

if __name__ == "__main__":
    dx = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
    data = json.loads(JOB.read_text(encoding="utf-8"))
    data["grid"]["dx"] = dx
    data["strips"]["along"] = dx
    data["grid"]["cache_dir"] = str(Path(__file__).resolve().parent / "cache" / "faydh_mesh5")
    cfg = with_tables(RunConfig.model_validate(data))
    with RasterBed(cfg.terrain.dem, cfg.terrain.pixel_stride) as bed:
        window = grid_window(cfg, bed)
        mask = domain_mask(cfg, bed, window)
        crs = _wkt(bed)
    try:
        _m, strip = mask_for_strips(cfg, mask, window.x0, window.y0, _domain_polygon(cfg.grid.domain, crs))
    except ValueError as error:
        print(f"{dx:g} m: refused: {error}")
        raise SystemExit(1) from None
    area = strip.geometry.areas_centroids()[0]
    print(f"{dx:g} m: {strip.geometry.ncells} cells, {area.sum():.1f} m2 against {strip.masked[0].size * dx * dx:.1f} m2 of squares; ring sizes {np.diff(strip.geometry.ring_start).min()} to {np.diff(strip.geometry.ring_start).max()}")
    print("  notes:", strip.notes[:5])
