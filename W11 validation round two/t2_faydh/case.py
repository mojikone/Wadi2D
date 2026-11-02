"""Test 2: Faydh 01 rain-on-grid against HEC-RAS, the method of validation/ras_rain_on_grid on another catchment.

S11 + S12 as the polygons stand, plus a box on the wadi below the dam axis. The lattice is anchored at DEM pixel
corners, 20 m ring, serving 20 m and 10 m. The east edge of the box is the only outlet: RAS's boundary line on the
perimeter, Wadi2D's boundary cells one column outside it, so both hold the same rained cells.
"""

from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent
W1 = Path(r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\ras_rain_on_grid")
BLOCK = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology")
HMS = BLOCK / "HEC_HMS_Block_02"
DEM_SOURCE = BLOCK / "Terrain" / "GGC_2_MERGE_HDSM.tif"
DEM = HERE / "terrain" / "faydh_0p5m.tif"
ENGINE = HERE.parent / "engine_f976c23"
BLOCK2_SCRIPTS = W1.parent / "block2_full" / "scripts"
RASPROCESS = r"C:\Program Files (x86)\HEC\HEC-RAS\6.6\RasProcess.exe"

ACC = HMS / "terrain" / "GGC_2_MERGE_HDSM_5m" / "00" / "flowaccum.tif"
ACC_CELL_KM2 = 25e-6
WADI_KM2 = 1.0

COARSE = 20.0
X0 = 430585.98973783385 - 592 * COARSE  # 418,745.99 E, a DEM pixel corner, as the Bidah lattice
Y0 = 2727980.393463373 + 392 * COARSE  # 2,735,820.39 N

BOX_WEST = X0 + 612 * COARSE  # 430,985.99 E
BOX_EAST = X0 + 678 * COARSE  # 432,305.99 E, the outlet
BOX_NORTH = Y0 - 98 * COARSE  # 2,733,860.39 N
BOX_SOUTH = Y0 - 144 * COARSE  # 2,732,940.39 N
FAN_WEST = 431000.0  # m E; "fan" here is the box, the wadi below the mountain front

PERIMETER_INSET = 0.02
SLOPE_OUT = 0.015  # placeholder until the thalweg is read, then fixed in the README before any RAS run
DURATION_H = 30
SERIES_S = 120.0
SITE = "Faydh 01"
SUBBASINS = ("S11", "S12")
AREA_KM2 = 74.304

# Positive downstream: heading north, the right is east.
AXIS = [(431065.0, 2732960.0), (431054.16, 2733225.76), (431019.77, 2733523.58), (431019.77, 2733840.0)]
BOX_MID = [(431605.0, 2732960.0), (431605.0, 2733840.0)]
SECTIONS = {"axis": AXIS, "box_mid": BOX_MID}

CONFIGS = {
    "20m_n050_em": dict(dx=20.0, n=0.05, equation=2),
    "10m_n050_em": dict(dx=10.0, n=0.05, equation=2, ras_hours=16),  # the peak falls at 12.2 h; see the README
}
