"""The rain-on-grid head-to-head, one source of truth for both models. Coordinates are in the DEM CRS (EPSG:32640).

The lattice is anchored at DEM pixel corners. The 20 m staircase perimeter serves both cell sizes, because a 20 m cell
is four 10 m cells on this lattice. RAS's outlet is the perimeter; Wadi2D's boundary cells are one extra row outside
it, so the two models hold the same rained cells and the open faces are the same faces.
"""

from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent
BLOCK = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology")
HMS = BLOCK / "HEC_HMS_Block_02"
DEM_SOURCE = BLOCK / "Terrain" / "GGC_2_MERGE_HDSM.tif"
DEM = HERE / "terrain" / "bidah_0p5m.tif"
ENGINE = HERE / "engine_609462d"
BLOCK2_SCRIPTS = HERE.parent / "block2_full" / "scripts"
RASPROCESS = r"C:\Program Files (x86)\HEC\HEC-RAS\6.6\RasProcess.exe"

ACC = HMS / "terrain" / "GGC_2_MERGE_HDSM_5m" / "00" / "flowaccum.tif"
ACC_CELL_KM2 = 25e-6
WADI_KM2 = 1.0  # a cell draining this much, and its neighbours within 40 m, is wadi; the rest is hillslope

FAN_WEST = 437300.0  # m E; the fan east of this, the gorge and hills west of it
COARSE = 20.0
X0 = 430585.98973783385  # west edge of the lattice, a DEM pixel corner
Y0 = 2727980.393463373  # north edge, a DEM pixel corner, and the north outlet of RAS

# The fan box below S13: its east and north edges are the open outlet, its other edges are walls.
BOX_WEST = X0 + 361 * COARSE
BOX_EAST = X0 + 423 * COARSE  # 439,045.99 E
BOX_SOUTH = Y0 - 69 * COARSE  # 2,726,600.39 N

PERIMETER_INSET = 0.02  # m; see s01_domain.pull_in
SLOPE_OUT = 0.01  # energy slope at the outlet; bed 0.7 to 1.0 % along the thalweg below the axis (outlet_probe)
DURATION_H = 30
SERIES_S = 60.0
SUBBASIN = "S13"
AREA_KM2 = 20.971
LAG_MIN = 53.3

# Positive downstream: heading south-east to north-west, the right is north-east.
AXIS = [(438870.0, 2726640.0), (438807.68, 2726752.81), (438259.32, 2727264.77), (438100.0, 2727420.0)]
S13_EDGE = [(438870.0, 2726820.0), (437835.0, 2727805.0)]
SECTIONS = {"axis": AXIS, "s13_edge": S13_EDGE}

CONFIGS = {
    "20m_n050_em": dict(dx=20.0, n=0.05, equation=2),
    "10m_n050_em": dict(dx=10.0, n=0.05, equation=2),
    "20m_n100_em": dict(dx=20.0, n=0.1, equation=2),
    "20m_n050_elm": dict(dx=20.0, n=0.05, equation=1),
}

# Wadi2D alone, to read what the thin-flow treatment does; settings of the frozen engine, set in the job.
WADI_VARIANTS = {
    "w20m_no_sheet": dict(dx=20.0, n=0.05, numerics={"sheet_flow": False}),
    "w10m_no_sheet": dict(dx=10.0, n=0.05, numerics={"sheet_flow": False}),
}
