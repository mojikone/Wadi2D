"""Why a run's gross rain reads 0.62 % under the file's depth over the domain: the outlet cells take no rain.

usage (venv, PYTHONPATH = this checkout): boundary_cells.py RUN_DIR CACHE_DIR
Rebuilds the run's grid and boundary cells with the engine, then sums the NetCDF's own totals over the interior cells
alone, read straight from the file with h5py, the pixel under each cell centre.
"""

import json
import sys
from pathlib import Path

import h5py
import numpy as np

from wadi2d.config.schema import RunConfig
from wadi2d.forcing import boundary_set
from wadi2d.run import prepare_grid, with_tables

NC = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\Grid\netCDF\Precipitation_RP200_10min.nc")
HALF_PIXEL = 1000.0
PIXEL = 2000.0

run = Path(sys.argv[1])
cfg = with_tables(RunConfig.model_validate_json((run / "config.resolved.json").read_text(encoding="utf-8")))
tables, _crs = prepare_grid(cfg, Path(sys.argv[2]), None)
grid = tables.grid
bset = boundary_set(list(cfg.boundaries), tables, cfg.grid.line_samples)
inner = grid.mask & ~bset.mask
out = {
    "active": int(grid.mask.sum()),
    "boundary": int((grid.mask & bset.mask).sum()),
    "interior": int(inner.sum()),
}
with h5py.File(run / "results.h5", "r") as f:
    out["same_mask_as_results"] = bool(np.array_equal(f["mask"][:].astype(bool), grid.mask))
    out["run_rain_m3"] = float(f.attrs["rain_m3"])
jj, ii = np.nonzero(inner)
x, y = grid.xy_of(jj, ii)
with h5py.File(NC, "r") as f:
    total = f["precipitation"][:].astype(np.float64).sum(axis=0)
    xs, ys = f["x"][:], f["y"][:]
col = np.floor((x - (xs[0] - HALF_PIXEL)) / PIXEL).astype(int)
row = np.floor(((ys[0] + HALF_PIXEL) - y) / PIXEL).astype(int)
out["nc_on_interior_cells_m3"] = float(total[row, col].sum() / 1000.0 * grid.dx**2)
out["run_over_interior"] = out["run_rain_m3"] / out["nc_on_interior_cells_m3"] - 1.0
out["boundary_share"] = out["boundary"] / out["active"]
print(json.dumps(out))
