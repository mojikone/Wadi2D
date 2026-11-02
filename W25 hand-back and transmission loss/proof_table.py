"""The books of every proof case of tests/engine/test_handback.py, in one table (CPU; the mesh and the GPU too).

python proof_table.py <work folder>     # writes proof_table.json here
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from tests.engine import test_handback as t  # noqa: E402
from wadi2d.hydrology.from_hms import PairedColumns, ProjectTables  # noqa: E402
from wadi2d.run import run_job  # noqa: E402

MESH = {
    "enabled": True, "coarse_dx": 8.0, "min_dx": 1.0, "analysis_pixel": t.PIXEL, "stream_area_fine_km2": 100.0,
    "stream_area_mid_km2": 100.0,
    "zones": [{"coordinates": [(t.X0, t.Y0), (t.X0 + 256.0, t.Y0), (t.X0 + 256.0, t.SOUTH), (t.X0, t.SOUTH)],
               "dx": t.DX}],
}  # fmt: skip
POOL_TABLES = ProjectTables(
    {},
    {},
    {
        "EA": PairedColumns(np.array([100.0, 101.0, 110.0]), np.array([1.0e3, 1.0e3, 1.0e3])),
        "EQ": PairedColumns(np.array([100.0, 101.0, 110.0]), np.array([0.0, 0.0, 90.0])),
    },
)


def cases(work: Path):
    def folder(name):
        f = work / name
        f.mkdir(parents=True, exist_ok=True)
        return f

    f = folder("lag")
    yield "Lag 10 min, re-entry", t.box(f, t.write_basin(f, t.lag_reach(), t.SINK))
    f = folder("lag_held")
    yield (
        "Lag 30 min, stopped at 25 min with the flood inside",
        t.box(f, t.write_basin(f, t.lag_reach(30.0), t.SINK), duration=1500.0),
    )
    f = folder("mc")
    yield "Muskingum-Cunge 3 km, re-entry", t.box(f, t.write_basin(f, t.MC_REACH, t.SINK), duration=7200.0)
    f = folder("pool")
    yield "Reservoir, dead storage below a sill", t.box(f, t.write_basin(f, t.POOL, t.SINK), duration=9000.0)
    f = folder("end")
    yield (
        "Lag 10 min, no re-entry: leaves at the end",
        t.box(f, t.write_basin(f, t.lag_reach(), t.SINK), inflows=[t.flood()]),
    )
    f = folder("mesh")
    yield (
        "Lag 10 min on a mesh (4 m and 8 m cells)",
        t.box(f, t.write_basin(f, t.lag_reach(), t.SINK), mesh=MESH),
    )
    f = folder("gpu")
    yield "Lag 10 min, GPU", t.box(f, t.write_basin(f, t.lag_reach(), t.SINK), backend="gpu")


def main(work: Path) -> None:
    import wadi2d.run

    rows = []
    for name, cfg in cases(work):
        tables = POOL_TABLES if name.startswith("Reservoir") else None
        keep = wadi2d.run._project_tables
        if tables is not None:
            wadi2d.run._project_tables = lambda _h, _b, fixed=tables: fixed
        try:
            run = run_job(cfg, work / name.split(",")[0].replace(" ", "_") / "run")
        finally:
            wadi2d.run._project_tables = keep
        b = run.balance
        rows.append({
            "case": name, "exit": run.exit_code,
            "entered_m3": b.inflow - b.reentry + b.lateral,
            "crossed_m3": b.handback, "came_back_m3": b.reentry, "left_at_end_m3": b.network_out,
            "in_network_m3": b.network_storage, "on_grid_m3": b.storage,
            "routing_defect_m3": b.routing_defect, "grid_relative": b.relative, "whole_relative": b.whole_relative,
        })  # fmt: skip
        print(rows[-1], flush=True)
    (HERE / "proof_table.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
