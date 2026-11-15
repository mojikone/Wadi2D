"""Shared paths and numbers of W79: Block 2 four ways. His Block 2 files are read only; everything written is under W79."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
REPO = HERE.parent
INPUTS = HERE / "inputs"
JOBS = HERE / "jobs"
RUNS = HERE / "runs"
CACHE = RUNS / "cache"

BLOCK = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2")
HYD = BLOCK / "Hydrology"
HMS_DIR = HYD / "HEC_HMS_Block_02"
BASIN = "Basin_3.basin"
MET = "FM_200yr.met"
CONTROL = "Control_1.control"
DEM = HYD / "Terrain" / "GGC_2_MERGE_HDSM.tif"
DEM5 = HYD / "Terrain" / "GGC_2_MERGE_HDSM_5.tif"
CN = HMS_DIR / "Hydrology Data" / "CN_Include_Hill_Area.tif"
ACC = HMS_DIR / "terrain" / "GGC_2_MERGE_HDSM_5m" / "00" / "flowaccum.tif"
AXES_SHP = BLOCK / "Claude Block 02" / "W2 reservoirs and routing" / "dam_data" / "gis" / "Block2_dam_axes.shp"
COAST_JOB = REPO / "W12 full extent rerun" / "jobs" / "full_30m_200yr.json"
W1_SCRIPTS = REPO / "W1 research and design note" / "validation" / "block2_full" / "scripts"

DX = 20.0
GGC_MINUS_NSA = 2.39
"""GGC_2_MERGE_HDSM over NSA_Batinah in both reservoirs of the dam team, m (W1 dem_difference.json)."""

DAMS = ["Bidah 03", "Faydh 01", "R5A", "R2A", "Z4C"]
RESERVOIR = {d: f"{d} Reservoir" for d in DAMS}

SET = os.environ.get("W79_SET", "rerun")
"""Which set of jobs and runs the scripts work on. ``rerun``: the rerun of 2026-11-15, on the domain with the 40 m rim
(inputs/domain.geojson). ``rerun2``: the same jobs on the domain without the rim (inputs/domain_no_rim.geojson), made
after his finding of 2026-11-15 that the rim was rained on in runs 3 and 4; not run yet."""
RUN_NAMES = {
    1: f"{SET}_run1_full_2d_aligned",
    2: f"{SET}_run2_hms_lumped",
    3: f"{SET}_run3_hybrid_aligned",
    4: f"{SET}_run4_hybrid_2d_routing_aligned",
}
DOMAIN_NO_RIM = INPUTS / "domain_no_rim.geojson"
"""The rerun of 2026-11-15 (the first attempt's jobs, without the ``rerun_`` prefix, stay in jobs/ and runs/ as the
superseded record). Runs 1, 3 and 4 on the aligned centre mesh at 20 m (his decision of 2026-11-14) at the 0.5 m pixel.
The first run 1 on plain 20 m squares stays in runs/run1_full_2d."""

STORM_AREA_KM2 = 100.0
"""His choice of 2026-11-15: one fixed storm area of 100 km2 for the 2D rain and everything not above a dam (the ARF FM
table at 100 km2, 0.913). The first attempt read the table at Basin 3's 1,370.77 km2 (0.661)."""
DAM_AREA_KM2 = {"Bidah 03": 20.97, "Faydh 01": 74.30, "R5A": 117.10, "R2A": 175.87, "Z4C": 211.09}
"""His dam drainage areas from Basin 3 (each reservoir's total upstream area; the engine's sums 20.971, 74.304,
117.105, 175.867, 211.085). Runs 2 to 4 read the ARF of a dam's catchment at the dam's area, HMS's depth-area way."""
RUN_TITLES = {
    1: "Full 2D, rain on the grid, dams as 2D pools",
    2: "Full HMS way, all lumped, Basin 3 reservoirs",
    3: "Hybrid, lumped reaches and reservoirs, 2D below the dams",
    4: "Hybrid, lumped subbasins, all routing and the dams on the grid",
}
if SET != "rerun":  # his definition of run 3, 2026-11-15
    RUN_TITLES[3] = "HMS in the mountains (above the dams and HAT-J4, left out of the mesh), rain on the grid below"


def load_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return path


def safe_csv_uri(path: Path) -> str:
    """A delimited-text URI QGIS reads for a CSV table without geometry; spaces in the path are escaped by as_uri."""
    return Path(path).resolve().as_uri() + "?type=csv&delimiter=,&detectTypes=yes&geomType=none"


def w1_path() -> None:
    """W1's dam definitions (Bidah 03 and Faydh 01 from the dam team's shapefiles, gaps joined) are imported, not copied."""
    if str(W1_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(W1_SCRIPTS))
