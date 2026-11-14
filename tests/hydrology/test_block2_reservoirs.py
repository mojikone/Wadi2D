"""Basin 3's five dam reservoirs against HEC-HMS: Modified Puls on elevation-area-outflow tables. Reads only.

Each reservoir routes HMS's own inflow of the depth-area analysis at that reservoir (FLOW-COMBINE), and the outflow,
storage and pool level are compared with HMS's FLOW, STORAGE (1000 m3) and ELEVATION. HMS starts every pool at the
bottom of its table, empty, which is also Wadi2D's default since W34; the comparison reads HMS's own setting.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from wadi2d.hms import daa_fpart, load_basin, load_pdata, open_dss
from wadi2d.hydrology.from_hms import basin_from_hms, load_project_tables
from wadi2d.hydrology.reservoir import ReservoirOutflowCurve

pytestmark = pytest.mark.data

DAMS = ["Bidah 03", "Faydh 01", "R2A", "R5A", "Z4C"]
ANALYSES = {"DA PMP B3": "DA_PMP_B3.dss", "DA 100yr B3": "DA_100yr_B3.dss"}
STEP_MINUTES = 5.0
THOUSAND = 1000.0
FLOW_TOLERANCE = 1.0e-6
LEVEL_TOLERANCE_M = 1.0e-6
STORAGE_TOLERANCE = 1.0e-6
# HMS's maximum pool level of record, m, and its peak outflow, m3/s (DA_*_B3.dss).
HMS_PEAKS = {
    ("DA PMP B3", "Bidah 03"): (104.570, 1477.2),
    ("DA PMP B3", "Faydh 01"): (234.902, 4830.4),
    ("DA PMP B3", "R2A"): (166.277, 9091.1),
    ("DA PMP B3", "R5A"): (146.784, 6558.8),
    ("DA PMP B3", "Z4C"): (172.256, 9490.6),
    ("DA 100yr B3", "Bidah 03"): (97.038, 0.0),
    ("DA 100yr B3", "Faydh 01"): (224.632, 0.0),
    ("DA 100yr B3", "R2A"): (163.193, 433.8),
    ("DA 100yr B3", "R5A"): (143.874, 428.9),
    ("DA 100yr B3", "Z4C"): (169.303, 1583.2),
}


@pytest.fixture(scope="module")
def reservoirs(hms_project_dir: Path) -> dict[str, ReservoirOutflowCurve]:
    tables = load_project_tables(
        load_pdata(hms_project_dir / "HEC_HMS_Block_02.pdata"), hms_project_dir / "HEC_HMS_Block_02.dss"
    )
    basin = basin_from_hms(load_basin(hms_project_dir / "Basin_3.basin"), tables)
    return {dam: basin.elements[f"{dam} Reservoir"].routing for dam in DAMS}  # type: ignore[attr-defined]


@pytest.mark.parametrize("dam", DAMS)
def test_every_pool_starts_empty_at_the_bottom_of_its_table(
    reservoirs: dict[str, ReservoirOutflowCurve], dam: str
) -> None:
    routing = reservoirs[dam]
    assert isinstance(routing, ReservoirOutflowCurve)
    assert routing.initial_elevation_m == routing.elevations_m[0]
    assert routing.outflow_m3s[0] == 0.0


@pytest.mark.parametrize(("analysis", "dam"), list(HMS_PEAKS))
def test_routing_hms_inflow_gives_hms_outflow_storage_and_level(
    hms_project_dir: Path, reservoirs: dict[str, ReservoirOutflowCurve], analysis: str, dam: str
) -> None:
    reservoir = f"{dam} Reservoir"
    fpart = daa_fpart(analysis, reservoir)
    with open_dss(hms_project_dir / ANALYSES[analysis]) as dss:
        inflow, outflow, storage, level = (
            dss.read_timeseries(reservoir, part, fpart).values
            for part in ("FLOW-COMBINE", "FLOW", "STORAGE", "ELEVATION")
        )
    routing = reservoirs[dam]
    routed = routing.route(inflow, STEP_MINUTES)
    held, pool = routing.pool(inflow, routed, STEP_MINUTES)
    hms_level, hms_peak = HMS_PEAKS[(analysis, dam)]
    assert level.max() == pytest.approx(hms_level, abs=0.0005)
    assert outflow.max() == pytest.approx(hms_peak, abs=0.05)
    assert np.abs(routed - outflow).max() <= FLOW_TOLERANCE * max(1.0, outflow.max())
    assert np.abs(pool - level).max() <= LEVEL_TOLERANCE_M
    assert np.abs(held - storage * THOUSAND).max() <= STORAGE_TOLERANCE * storage.max() * THOUSAND
