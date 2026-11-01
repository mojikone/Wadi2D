"""The lumped engine against the HEC-HMS results of Block 2. Reads the project; writes only the report."""

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
REACHES = [f"R{number}" for number in range(1, 9)]
STEP_MINUTES = 5.0
PEAK_TOLERANCE = 0.01
VOLUME_TOLERANCE = 0.01
WHOLE_BASIN_PEAK_PERCENT = 2.0
DAM_PEAK_PERCENT = 1.0
REPORT = Path(__file__).parents[2] / "W1 research and design note" / "validation" / "hms_replication.md"
PREAMBLE = """# HEC-HMS replication, Block 2

Written by `tests/hydrology/test_block2_replication.py`; do not edit by hand. The Wadi2D lumped engine reruns all
13 depth-area analyses of `HEC_HMS_Block_02` (HMS 4.12), 40 analysis points each, from the HMS files alone, and each
peak is compared with `results\\DAA_*.results`. Error = (Wadi2D / HMS - 1) x 100. PMP is included: its depth is the
PMP grid read through rasterio and averaged over the cells centred in the polygons above each point.

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


def test_grid_depth_equals_every_depth_hms_logged(block2: Block2) -> None:
    """The PMP depth is read off the log of the analysis; 40 points."""
    folder = block2.folder
    raster = find_grid_file(folder / "HEC_HMS_Block_02.grid", "PMP", (folder, folder.parent))
    depths = DepthGrid.load(raster)
    shapes = {polygon.name: polygon.shape() for polygon in subbasin_polygons(folder / "Basin_1.sqlite")}
    log = (folder / "DA_PMP_B1_daa.log").read_text(encoding="utf-8", errors="replace")
    logged: dict[str, float] = {}
    point = ""
    for line in log.splitlines():
        started = re.search(r'Computing analysis point "(.+)"', line)
        depth = re.search(r"Hypothetical storm depth for subbasin \S+: ([\d,.]+) MM", line)
        if started:
            point = started.group(1)
        elif depth and point not in logged:
            logged[point] = float(depth.group(1).replace(",", ""))
    assert len(logged) == len(block2.basin.elements)
    for name, value in logged.items():
        upstream = block2.basin.upstream_of(name)
        mean = depths.mean_over(shape for key, shape in shapes.items() if key in upstream)
        assert mean == pytest.approx(value, abs=0.001), name


@pytest.fixture(scope="module")
def replication(block2: Block2) -> Replication:
    return replicate(block2.folder / "HEC_HMS_Block_02.hms")


def test_whole_basin_replicates_and_the_report_is_written(replication: Replication) -> None:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(render(replication, DAMS, ANALYSIS, PREAMBLE), encoding="utf-8", newline="\n")
    assert len(replication.analyses) == 13
    assert len(replication.comparisons) == 13 * 40
    assert not replication.left_out
    assert abs(replication.worst().error_percent) < WHOLE_BASIN_PEAK_PERCENT
    assert abs(replication.worst(DAMS).error_percent) < DAM_PEAK_PERCENT


def test_every_peak_falls_within_one_step(replication: Replication) -> None:
    assert max(abs(comparison.time_steps) for comparison in replication.comparisons) <= 1


@pytest.mark.parametrize(("dam", "peak"), DAM_PEAKS_100YR.items())
def test_dam_sites_at_100yr(replication: Replication, dam: str, peak: float) -> None:
    assert replication.of(ANALYSIS, [dam])[0].peak == pytest.approx(peak, abs=0.5)
