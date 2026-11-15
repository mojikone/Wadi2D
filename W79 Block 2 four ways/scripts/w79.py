"""Shared paths and numbers of W79: Block 2 four ways. His Block 2 files are read only; everything written is under W79."""

from __future__ import annotations

import json
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

RUN_NAMES = {
    1: "run1_full_2d_aligned",
    2: "run2_hms_lumped",
    3: "run3_hybrid_aligned",
    4: "run4_hybrid_2d_routing_aligned",
}
"""Runs 1, 3 and 4 on the aligned centre mesh at 20 m (his decision of 2026-11-14). The first run 1 on plain 20 m squares
stays in runs/run1_full_2d as the superseded record."""
RUN_TITLES = {
    1: "Full 2D, rain on the grid, dams as 2D pools",
    2: "Full HMS way, all lumped, Basin 3 reservoirs",
    3: "Hybrid, lumped reaches and reservoirs, 2D below the dams",
    4: "Hybrid, lumped subbasins, all routing and the dams on the grid",
}


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
