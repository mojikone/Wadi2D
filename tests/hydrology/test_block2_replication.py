"""The lumped engine against the HEC-HMS results of Block 2. Reads the project; writes only the report.

Since 2026-11-11 the project holds three basin models, each with its own 13 depth-area analyses (`DA <storm> B<n>`,
the FM storms of `FM_<storm>.met` through the ARF FM table at every point's own drainage area): Basin 1, the 18
subbasins and eight reaches of the dam catchments (40 points); Basin 2, Basin 1 plus the Block 2 channel network
below the dams (91 points); Basin 3, Basin 2 plus the five dam reservoirs, empty at the start, routed by Modified Puls on
their elevation-area-outflow tables (97 points, the five reservoirs among them). All 39 are rerun here.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from wadi2d.hms import (
    AnalysisResults,
    Basin,
    DssFile,
    daa_fpart,
    load_basin,
    load_met,
    load_nals,
    load_pdata,
    load_results,
    met_fpart,
    open_dss,
)
from wadi2d.hms.sqlite import subbasin_polygons
from wadi2d.hydrology import LumpedEngine, TimeGrid, analyse_point, point_storm
from wadi2d.hydrology.constants import SECONDS_PER_MINUTE
from wadi2d.hydrology.from_hms import (
    basin_from_hms,
    find_grid_file,
    grid_from_hms,
    load_project_tables,
    storm_from_hms,
)
from wadi2d.hydrology.model import Basin as EngineBasin
from wadi2d.hydrology.replication import Replication, render, replicate
from wadi2d.storm import HypotheticalStorm
from wadi2d.storm.grid_depth import DepthGrid

pytestmark = pytest.mark.data

ANALYSIS = "DA 100yr B1"
MET = "FM 100yr"
DAMS = ["Faydh 01", "Bidah 03", "R5A", "R2A", "Z4C"]
DAM_PEAKS_100YR = {"Faydh 01": 993.0, "Bidah 03": 362.0, "R5A": 887.0, "R2A": 1356.0, "Z4C": 1666.0}
# The reservoirs' outflow of record in DAA_DA_*_B3.results; Bidah 03 and Faydh 01 do not spill at 100 yr.
RESERVOIR_PEAKS = {
    ("DA 100yr B3", "Bidah 03 Reservoir"): 0.0,
    ("DA 100yr B3", "Faydh 01 Reservoir"): 0.0,
    ("DA 100yr B3", "R2A Reservoir"): 433.8,
    ("DA 100yr B3", "R5A Reservoir"): 428.9,
    ("DA 100yr B3", "Z4C Reservoir"): 1583.2,
    ("DA PMP B3", "Bidah 03 Reservoir"): 1477.2,
    ("DA PMP B3", "Faydh 01 Reservoir"): 4830.4,
    ("DA PMP B3", "R2A Reservoir"): 9091.1,
    ("DA PMP B3", "R5A Reservoir"): 6558.8,
    ("DA PMP B3", "Z4C Reservoir"): 9490.6,
}
POINTS_PER_BASIN = {"1": 40, "2": 91, "3": 97}
STORMS_PER_BASIN = 13
REACHES = [f"R{number}" for number in range(1, 9)]
STEP_MINUTES = 5.0
PEAK_TOLERANCE = 0.01
VOLUME_TOLERANCE = 0.01
WHOLE_BASIN_PEAK_PERCENT = 2.0
DAM_PEAK_PERCENT = 1.0
REPORT = Path(__file__).parents[2] / "W1 research and design note" / "validation" / "hms_replication.md"
PREAMBLE = """# HEC-HMS replication, Block 2

Written by `tests/hydrology/test_block2_replication.py`; do not edit by hand. The Wadi2D lumped engine reruns all
39 depth-area analyses of `HEC_HMS_Block_02` (HMS 4.12) from the HMS files alone: `B1` runs Basin 1 (the dam
catchments, 40 analysis points), `B2` Basin 2 (with the Block 2 channel network, 91 points), `B3` Basin 3 (Basin 2
with the five dam reservoirs, empty at the start, 97 points). Each peak is compared with `results\\DAA_*.results`.
Error = (Wadi2D / HMS - 1) x 100; an empty cell is a point the analysis does not have. PMP is included: its depth
is the PMP grid read through rasterio and averaged over the cells centred in the polygons above each point, or,
where those polygons hold no cell centre (three Basin 3 points), the cell nearest their centroid.

The few hundredths of a per cent on `RIJ-J17`, `RIJ-J20` and `RIJ-J21` are two short reaches, `RIJ-R11` and
`RIJ-R17`, on which HMS logged two cells and twice the sub-steps where its rule on the other 69 reaches of Basin 3
gives one; routed on HMS's logged grid they match to 1e-5 (W55). What makes HMS double them is not identified.

## What it took: HMS behaviour that its documents do not state

All measured on the Block 2 output; the routing constants are frozen in `wadi2d/hydrology/routing.py`.

- **SCS unit hydrograph**: table 16-1 is read through a natural cubic spline, not linearly, sampled at i dt / Tp
  and renormalised. Deconvolving HMS's flows from its excess gives these ordinates to 2e-14 of the peak. The linear
  table misses every peak by 0.3 %.
- **Cells**: N = ceil(L / (c_index dt)), confirmed by every dx in the HMS log.
- **Stencil**: 3-point start, iterated on the 4-point mean, stopping on a relative change of 1e-3.
- **Low flow**: below a 3-point mean of 0.01 m3/s the outflow is that mean.
- **Negative new-inflow weight**: below C + D = 1 it is zeroed and split evenly between the other two weights.
  This form was fitted to the lag of the falling limb, then confirmed by the peaks; it is not a documented rule.
  Without it the 5 yr peaks miss by 7.5 %.
"""


@dataclass(frozen=True)
class Block2:
    """The Block 2 project as this file needs it."""

    folder: Path
    hms_basin: Basin
    basin: EngineBasin
    grid: TimeGrid
    storm: HypotheticalStorm
    results: AnalysisResults


@pytest.fixture(scope="module")
def block2(hms_project_dir: Path) -> Block2:
    hms_basin = load_basin(hms_project_dir / "Basin_1.basin")
    tables = load_project_tables(
        load_pdata(hms_project_dir / "HEC_HMS_Block_02.pdata"), hms_project_dir / "HEC_HMS_Block_02.dss"
    )
    met = load_met(hms_project_dir / "FM_100yr.met")
    assert met.storm is not None
    results = load_results(hms_project_dir / "results" / "DAA_DA_100yr_B1.results")
    analysis = load_nals(hms_project_dir / "HEC_HMS_Block_02.nals").analysis(ANALYSIS)
    return Block2(
        folder=hms_project_dir,
        hms_basin=hms_basin,
        basin=basin_from_hms(hms_basin),
        grid=grid_from_hms(analysis),
        storm=storm_from_hms(met.storm, tables),
        results=results,
    )


@pytest.fixture(scope="module")
def engine(block2: Block2) -> LumpedEngine:
    return LumpedEngine(block2.basin)


@pytest.fixture(scope="module")
def analysis_dss(block2: Block2) -> Iterator[DssFile]:
    with open_dss(block2.folder / "DA_100yr_B1.dss") as dss:
        yield dss


def peak_clock(start: datetime | None, stamp: datetime | None) -> float:
    assert start is not None and stamp is not None
    return (stamp - start).total_seconds() / SECONDS_PER_MINUTE


def test_rain_at_s18_equals_the_hms_series(block2: Block2) -> None:
    with open_dss(block2.folder / "FM_100yr.dss") as dss:
        hms_rain = dss.read_timeseries("S18", "PRECIP-INC", met_fpart(MET, "S18")).values
    storm = block2.storm.at_area(block2.basin.drainage_area("S18"))
    assert np.abs(storm.increments(STEP_MINUTES, len(hms_rain)) - hms_rain).max() < 1e-4


def test_total_depth_at_every_point_is_the_area_reduced_depth(block2: Block2) -> None:
    checked = 0
    for point, elements in block2.results.points.items():
        storm = block2.storm.at_area(block2.basin.drainage_area(point))
        for statistics in elements.values():
            if statistics.precipitation is not None:
                assert storm.total_depth == pytest.approx(statistics.precipitation, abs=0.06)
                checked += 1
    assert checked >= 40


def test_s3_excess_and_loss_equal_the_hms_series(
    block2: Block2, engine: LumpedEngine, analysis_dss: DssFile
) -> None:
    water = analyse_point(engine, point_storm(block2.storm), block2.grid, "S3").run.water["S3"]
    fpart = daa_fpart(ANALYSIS, "S3")
    assert water.excess.sum() == pytest.approx(159.21, abs=0.005)
    assert water.loss.sum() == pytest.approx(30.10, abs=0.005)
    hms_excess = analysis_dss.read_timeseries("S3", "PRECIP-EXCESS", fpart).values
    hms_loss = analysis_dss.read_timeseries("S3", "INFILTRATION", fpart).values
    assert np.abs(water.excess[-len(hms_excess) :] - hms_excess).max() < 1e-3
    assert np.abs(water.loss[-len(hms_loss) :] - hms_loss).max() < 1e-3


@pytest.mark.parametrize(
    ("name", "peak", "clock"),
    [("S1", 628.6, "13:45"), ("S3", 708.3, "14:30"), ("S13", 362.4, "12:45")],
)
def test_named_subbasin_peaks(
    block2: Block2, engine: LumpedEngine, name: str, peak: float, clock: str
) -> None:
    result = analyse_point(engine, point_storm(block2.storm), block2.grid, name)
    hours, minutes = clock.split(":")
    assert result.peak == pytest.approx(peak, rel=PEAK_TOLERANCE)
    assert result.peak_minutes == pytest.approx(60.0 * int(hours) + int(minutes), abs=STEP_MINUTES)


def test_every_subbasin_at_its_own_point(block2: Block2, engine: LumpedEngine) -> None:
    for name in block2.basin.subbasins:
        reference = block2.results.element(name)
        assert reference.outflow_max is not None
        result = analyse_point(engine, point_storm(block2.storm), block2.grid, name)
        assert result.peak == pytest.approx(reference.outflow_max, rel=PEAK_TOLERANCE), name
        hms_minutes = peak_clock(block2.results.start, reference.outflow_max_time)
        assert result.peak_minutes == pytest.approx(hms_minutes, abs=STEP_MINUTES), name


@pytest.mark.parametrize("name", REACHES)
def test_reach_with_the_hms_inflow(block2: Block2, analysis_dss: DssFile, name: str) -> None:
    fpart = daa_fpart(ANALYSIS, name)
    inflow = analysis_dss.read_timeseries(name, "FLOW-COMBINE", fpart).values
    hms_outflow = analysis_dss.read_timeseries(name, "FLOW", fpart).values
    routing = block2.basin.elements[name].routing  # type: ignore[attr-defined]
    outflow = routing.route(inflow, STEP_MINUTES)
    assert outflow.max() == pytest.approx(hms_outflow.max(), rel=PEAK_TOLERANCE)
    assert outflow.sum() == pytest.approx(hms_outflow.sum(), rel=VOLUME_TOLERANCE)
    assert abs(int(np.argmax(outflow)) - int(np.argmax(hms_outflow))) <= 1


def test_the_series_of_every_reach_stays_close_to_hms(block2: Block2, analysis_dss: DssFile) -> None:
    for name in REACHES:
        fpart = daa_fpart(ANALYSIS, name)
        inflow = analysis_dss.read_timeseries(name, "FLOW-COMBINE", fpart).values
        hms_outflow = analysis_dss.read_timeseries(name, "FLOW", fpart).values
        routing = block2.basin.elements[name].routing  # type: ignore[attr-defined]
        assert np.abs(routing.route(inflow, STEP_MINUTES) - hms_outflow).max() < 0.02, name


@pytest.mark.parametrize("model", list(POINTS_PER_BASIN))
def test_grid_depth_equals_every_depth_hms_logged(block2: Block2, model: str) -> None:
    """The PMP depth is read off the log of each basin model's PMP analysis: 40, 91 and 97 points.

    Basin 2 and 3 have ten subbasins too small to hold a cell centre; three points of Basin 3 have nothing else above
    them (BID-J17, BID-J19, BID-J45) and read the cell nearest the centroid of their polygons.
    """
    folder = block2.folder
    raster = find_grid_file(folder / "HEC_HMS_Block_02.grid", "PMP", (folder, folder.parent))
    depths = DepthGrid.load(raster)
    basin = basin_from_hms(load_basin(folder / f"Basin_{model}.basin"), load_project_tables(
        load_pdata(folder / "HEC_HMS_Block_02.pdata"), folder / "HEC_HMS_Block_02.dss"
    ))
    shapes = {polygon.name: polygon.shape() for polygon in subbasin_polygons(folder / f"Basin_{model}.sqlite")}
    log = (folder / f"DA_PMP_B{model}_daa.log").read_text(encoding="utf-8", errors="replace")
    logged: dict[str, float] = {}
    point = ""
    for line in log.splitlines():
        started = re.search(r'Computing analysis point "(.+)"', line)
        depth = re.search(r"Hypothetical storm depth for subbasin \S+: ([\d,.]+) MM", line)
        if started:
            point = started.group(1)
        elif depth and point not in logged:
            logged[point] = float(depth.group(1).replace(",", ""))
    assert len(logged) == POINTS_PER_BASIN[model]
    for name, value in logged.items():
        upstream = basin.upstream_of(name)
        mean = depths.mean_over(shape for key, shape in shapes.items() if key in upstream)
        assert mean == pytest.approx(value, abs=0.001), name


@pytest.fixture(scope="module")
def replication(block2: Block2) -> Replication:
    return replicate(block2.folder / "HEC_HMS_Block_02.hms")


def test_whole_basin_replicates_and_the_report_is_written(replication: Replication) -> None:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(render(replication, DAMS, ANALYSIS, PREAMBLE), encoding="utf-8", newline="\n")
    assert len(replication.analyses) == STORMS_PER_BASIN * len(POINTS_PER_BASIN)
    assert len(replication.comparisons) == STORMS_PER_BASIN * sum(POINTS_PER_BASIN.values())
    assert not replication.left_out
    assert not replication.points_without_results
    assert abs(replication.worst().error_percent) < WHOLE_BASIN_PEAK_PERCENT
    assert abs(replication.worst(DAMS).error_percent) < DAM_PEAK_PERCENT


def test_every_peak_falls_within_one_step(replication: Replication) -> None:
    assert max(abs(comparison.time_steps) for comparison in replication.comparisons) <= 1


@pytest.mark.parametrize(("dam", "peak"), DAM_PEAKS_100YR.items())
def test_dam_sites_at_100yr(replication: Replication, dam: str, peak: float) -> None:
    assert replication.of(ANALYSIS, [dam])[0].peak == pytest.approx(peak, abs=0.5)


@pytest.mark.parametrize(("key", "peak"), RESERVOIR_PEAKS.items(), ids=lambda key: str(key))
def test_reservoir_outflow_of_basin_3(replication: Replication, key: tuple[str, str], peak: float) -> None:
    analysis, reservoir = key
    row = replication.of(analysis, [reservoir])[0]
    assert row.hms_peak == pytest.approx(peak, abs=0.05)
    assert row.peak == pytest.approx(row.hms_peak, abs=0.01)
    assert row.time_steps == 0
