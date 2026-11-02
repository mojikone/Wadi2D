"""The ground the solver really used: the lowest ground in the cell at each point, from a run's own job, through the
grid cache it ran on. Started by the dock check on the engine's Python, so the check reads the tables and not only a
raster written beside them. Arguments: repo, job.json, cache folder, then x y pairs. Prints JSON.
"""

import json
import sys
from pathlib import Path

repo, job, cache, *numbers = sys.argv[1:]
sys.path.insert(0, repo)

import wadi2d  # noqa: E402
from wadi2d.run import load_job, prepare_grid  # noqa: E402

tables, _crs = prepare_grid(load_job(Path(job)), Path(cache))
grid = tables.grid
points = list(zip(numbers[0::2], numbers[1::2], strict=True))
cells = [grid.cell_of(float(x), float(y)) for x, y in points]
print(json.dumps({"engine": wadi2d.__file__, "zmin": [float(tables.zmin[j, i]) for j, i in cells]}))
