"""W78: the post-run check. Bidah: W61's job run on the CPU through ``run_job`` (both checks, as the dock runs them), and
the same job with outlet 2 free (the clean case). Faydh 01: the check on W11's 20 m squares run, read from its maps.

Run from the repository root: ``.venv\\Scripts\\python "W78 domain edge valley check\\probe_pools.py" <runs folder>``.
Writes ``logs/pools.json``.
"""

import json
import sys
from pathlib import Path

import numpy as np
import rasterio
import shapely
from rasterio import features

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

from probe_crossings import bidah  # noqa: E402

from wadi2d.config.schema import EdgeCheck, RunConfig  # noqa: E402
from wadi2d.edge_valleys import edge_pools, pool_notes  # noqa: E402
from wadi2d.run import EDGE_REACH, run_job  # noqa: E402

FAYDH_RUN = REPO.parents[2] / "W11 validation round two" / "t2_faydh" / "wadi_runs" / "20m_n050_em"
"""W11's Faydh 01 squares at 20 m; its maps sit in the main checkout, not in git."""


class MapGrid:
    """Just what the check reads of a grid, from a run's own map."""

    def __init__(self, path: Path):
        with rasterio.open(path) as src:
            self.depth = src.read(1).astype(np.float64)
            self.transform = src.transform
            self.mask = self.depth != src.nodata
        self.dx = self.transform.a

    def xy_of(self, j, i):
        return self.transform * (i + 0.5, j + 0.5)


def bidah_runs(runs: Path) -> dict:
    record = {}
    for name, flow_line in (("bidah_flow_line", True), ("bidah_clean", False)):
        job = bidah(flow_line).model_dump(mode="json")
        job["storm"].update(kind="uniform", depth_mm=5.0, duration_min=30.0)
        job["outputs"]["map_every_s"] = 0.0
        job["outputs"]["pixels"]["enabled"] = False
        job["run"]["backend"] = "cpu"
        job["grid"]["cache_dir"] = str(runs / "cache")
        cfg = RunConfig.model_validate(job)
        out = runs / name
        summary = run_job(cfg, out, "cpu")
        events = [
            json.loads(line) for line in (out / "progress.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        record[name] = {
            "status": summary.status,
            "edge_warnings": [e["message"] for e in events if e["ev"] == "warn" and "domain" in e["message"]],
            "outputs": [e for e in events if e["ev"] == "output" and e.get("kind") == "edge_checks"],
        }
        print(name, summary.status, json.dumps(record[name]["edge_warnings"], indent=1))
    return record


def faydh_maps() -> dict:
    grid = MapGrid(FAYDH_RUN / "maps" / "max_depth.tif")
    with rasterio.open(FAYDH_RUN / "maps" / "max_level.tif") as src:
        level = src.read(1).astype(np.float64)
    depth = np.where(grid.mask, grid.depth, 0.0)
    zmin = np.where(depth > 0.0, level - depth, 0.0)
    cfg = json.loads((FAYDH_RUN / "config.resolved.json").read_text(encoding="utf-8"))
    lines = [shapely.LineString(b["coordinates"]).buffer(grid.dx) for b in cfg["boundaries"]]
    open_cells = features.geometry_mask(lines, out_shape=depth.shape, transform=grid.transform, invert=True)
    check = EdgeCheck()
    pools = edge_pools(grid, depth, zmin, open_cells, EDGE_REACH, 3.0, check)
    notes = pool_notes(pools, check)
    print("faydh", json.dumps(notes, indent=1))
    return {"faydh_w11_20m": {"pools": [p.__dict__ for p in pools], "warnings": notes}}


def main():
    runs = Path(sys.argv[1])
    record = {**faydh_maps(), **bidah_runs(runs)}
    (HERE / "logs").mkdir(exist_ok=True)
    (HERE / "logs" / "pools.json").write_text(json.dumps(record, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
