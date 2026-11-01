"""The rules found on Block 2 against three HMS projects that had no part in finding them.

Reads the projects; writes nothing. The limits are the measured results of ``hms_heldout.md`` with a small margin,
so a regression fails here. The full run, 26,369 point-peaks, is ``heldout_replication.py``; this is a sample of
the analyses that were worst when the rules were wrong.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from wadi2d.hms import DssFile, daa_fpart, load_basin, load_pdata, load_project, open_dss
from wadi2d.hms.sqlite import subbasin_polygons
from wadi2d.hydrology.from_hms import ProjectTables, basin_from_hms, find_grid_file, load_project_tables
from wadi2d.hydrology.model import Basin, Branching, Reach
from wadi2d.hydrology.replication import replicate, results_file_name
from wadi2d.storm.grid_depth import DepthGrid

pytestmark = pytest.mark.data

ROOT = Path(r"D:\Mojtaba\Renardet\2224 WS11")
BLOCK_4 = ROOT / r"Batinah\Block 4\Hydrology\HEC_HMS_Block_04\HEC_HMS_Block_04.hms"
BLOCK_6 = ROOT / r"HMS\B6\60 HMS_Block_6_Mod1\HMS_Block_6_Mod1.hms"
MAJLAS = ROOT / r"Majlas\Hydrology\HEC_HMS_Majlas\HEC_HMS_Majlas.hms"
STEP_MINUTES = 5.0
LOG_DEPTH_ROUNDING_MM = 0.00051
ROUTING_LINE = re.compile(
    r'Routing parameters based on index celerity [\d.,]+ m/s for reach "(.+?)": '
    r"Delta t \(sec\) ([\d.,]+)\s+Delta x \(m\) ([\d.,]+)"
)
UNEXPLAINED_REACH = "R20"


def number(text: str) -> float:
    """HMS prints thousands with a comma."""
    return float(text.replace(",", ""))


@dataclass(frozen=True)
class Project:
    """A project as these tests need it."""

    source: Path
    tables: ProjectTables

    def basin(self, name: str) -> Basin:
        return basin_from_hms(load_basin(self.basin_path(name)), self.tables)

    def basin_path(self, name: str) -> Path:
        project = load_project(self.source)
        return project.path_of(project.basins[name])

    def dss(self, run: str) -> DssFile:
        return open_dss(self.source.parent / f"{run}.dss")


def project_at(source: Path) -> Project:
    if not source.is_file():
        pytest.skip(f"{source} not available")
    tables = load_project_tables(load_pdata(source.with_suffix(".pdata")), source.with_suffix(".dss"))
    return Project(source, tables)


@pytest.fixture(scope="module")
def block4() -> Project:
    return project_at(BLOCK_4)


@pytest.fixture(scope="module")
def block6() -> Project:
    return project_at(BLOCK_6)


@pytest.fixture(scope="module")
def majlas() -> Project:
    return project_at(MAJLAS)


@pytest.mark.parametrize(
    ("source", "analysis", "points", "limit_percent"),
    [
        (BLOCK_4, "DA 2yr B3", 362, 0.010),  # 6.6 % before the sub-step rule
        (BLOCK_4, "DA 100yr B4", 93, 0.010),  # Modified Puls
        (BLOCK_4, "DA PMP B6", 362, 0.010),  # grid depth, uniform, Modified Puls
        (BLOCK_6, "DA 5yr 1D DAM - All", 405, 0.11),  # 3.9 % before; hyphen in the results name
        (BLOCK_6, "DA 1000yr 1D DAM - All", 405, 0.14),  # worst of the project
        (BLOCK_6, "DA PMP 1D DAM - All", 405, 0.09),  # depth by subbasin, spillways, three diversions
        (BLOCK_6, "DA 1000yr 1D noDAM", 405, 0.09),
        (MAJLAS, "DA PMP Res2", 49, 0.005),  # geographic grid, depth by subbasin, spillway
        (MAJLAS, "DA 10yr Dams", 46, 0.005),  # the results lack one point of the .nals
    ],
)
def test_peaks_stay_within_what_was_measured(
    source: Path, analysis: str, points: int, limit_percent: float
) -> None:
    if not source.is_file():
        pytest.skip(f"{source} not available")
    replication = replicate(source, [analysis])
    assert not replication.left_out
    assert len(replication.comparisons) == points
    assert abs(replication.worst().error_percent) < limit_percent
    assert max(abs(comparison.time_steps) for comparison in replication.comparisons) <= 1


def test_an_analysis_with_no_results_is_left_out_with_its_reason() -> None:
    if not BLOCK_6.is_file():
        pytest.skip(f"{BLOCK_6} not available")
    replication = replicate(BLOCK_6, ["DA PMP Basin DAMs"])
    assert not replication.comparisons
    assert "DAA_DA_PMP_Basin_DAMs.results" in replication.left_out["DA PMP Basin DAMs"]


def test_a_point_the_results_lack_is_reported() -> None:
    if not MAJLAS.is_file():
        pytest.skip(f"{MAJLAS} not available")
    replication = replicate(MAJLAS, ["DA 10yr Dams"])
    assert len(replication.points_without_results["DA 10yr Dams"]) == 1


def test_hyphenated_analysis_names_find_their_results(block6: Project) -> None:
    name = results_file_name("DA 10yr 1D DAM - All")
    assert (block6.source.parent / "results" / name).is_file()


def test_modified_puls_is_the_hms_series(block4: Project) -> None:
    """Hawasinah 02 at 100 yr with HMS's own inflow: exact to the printed digits."""
    basin = block4.basin("Basin 4")
    point = "Hawasinah 02 Reservoir"
    fpart = daa_fpart("DA 100yr B4", point)
    with block4.dss("DA_100yr_B4") as dss:
        inflow = dss.read_timeseries(point, "FLOW-COMBINE", fpart).values
        outflow = dss.read_timeseries(point, "FLOW", fpart).values
    element = basin.elements[point]
    assert isinstance(element, Branching)
    assert np.abs(element.routing.branches(inflow, STEP_MINUTES)[0] - outflow).max() < 1e-9


def test_a_slow_pool_is_one_implicit_trapezoid_per_step(majlas: Project) -> None:
    """Majlas never reaches the crest at 100 yr, so a reservoir that only fills must match to the step."""
    basin = majlas.basin("Basin 1 Res")
    point = "Majlas Dam Reservoir"
    fpart = daa_fpart("DA 100yr Res", point)
    with majlas.dss("DA_100yr_Res") as dss:
        inflow = dss.read_timeseries(point, "FLOW-COMBINE", fpart).values
        outflow = dss.read_timeseries(point, "FLOW", fpart).values
    element = basin.elements[point]
    assert isinstance(element, Branching)
    assert outflow.max() == 0.0
    assert element.routing.branches(inflow, STEP_MINUTES)[0].max() == 0.0


@pytest.fixture(scope="module")
def al_ais(block6: Project) -> Iterator[DssFile]:
    with block6.dss("DA_PMP_1D_DAM___All") as dss:
        yield dss


def test_a_diversion_is_its_table_read_at_the_inflow(block6: Project, al_ais: DssFile) -> None:
    basin = block6.basin("Basin 1 - 1D - DAM")
    name = "S94 Diversion"
    fpart = daa_fpart("DA PMP 1D DAM - All", "Bani Kharous Existing")
    inflow = al_ais.read_timeseries(name, "FLOW-COMBINE", fpart).values
    diverted = al_ais.read_timeseries(name, "FLOW-DIVERSION", fpart).values
    element = basin.elements[name]
    assert isinstance(element, Branching)
    assert np.abs(element.routing.branches(inflow, STEP_MINUTES)[1] - diverted).max() < 1e-6


def test_the_auxiliary_outlet_spills_on_the_same_pool_as_the_main_one(
    block6: Project, al_ais: DssFile
) -> None:
    basin = block6.basin("Basin 1 - 1D - DAM")
    name = "Al Ais 10 Reservoir"
    fpart = daa_fpart("DA PMP 1D DAM - All", "Al Ais 10 Culvert outlet")
    inflow = al_ais.read_timeseries(name, "FLOW-COMBINE", fpart).values
    auxiliary = al_ais.read_timeseries(name, "FLOW-AUX", fpart).values
    element = basin.elements[name]
    assert isinstance(element, Branching)
    computed = element.routing.branches(inflow, STEP_MINUTES)[1]
    assert computed.max() == pytest.approx(auxiliary.max(), rel=2e-4)


def test_storm_area_follows_downstream_links_while_the_network_follows_the_water(block6: Project) -> None:
    basin = block6.basin("Basin 1 - 1D - noDAM")
    assert basin.drainage_area("J93") == pytest.approx(2.753, abs=0.001)
    assert len(basin.upstream_of("J93")) == 27


def test_cells_and_substeps_of_every_block_6_reach_are_the_logged_ones(block6: Project) -> None:
    basin = block6.basin("Basin 1 - 1D - DAM")
    log = (block6.source.parent / "DA_100yr_1D_DAM___All_daa.log").read_text(
        encoding="utf-8", errors="replace"
    )
    logged = {name: (number(dt), number(dx)) for name, dt, dx in ROUTING_LINE.findall(log)}
    assert len(logged) > 100
    for name, (dt, dx) in logged.items():
        element = basin.elements[name]
        assert isinstance(element, Reach)
        cells, length, substeps = element.routing.grid(300.0)  # type: ignore[attr-defined]
        if name == UNEXPLAINED_REACH:
            assert (cells, substeps) == (1, 1) and dx == pytest.approx(length / 2.0)
            continue
        assert length == pytest.approx(dx, abs=0.01), name
        assert 300.0 / substeps == pytest.approx(dt, abs=0.051), name


@pytest.mark.parametrize(
    ("source", "basin_name", "log_name"),
    [
        (MAJLAS, "Basin 1", "DA_PMP_Dams_daa.log"),  # raster in EPSG:4326, polygons in UTM
        (BLOCK_6, "Basin 1 - 1D - noDAM", "DA_PMP_1D_noDAM_daa.log"),  # subbasins of one cell
    ],
)
def test_depth_by_subbasin_is_every_depth_hms_logged(source: Path, basin_name: str, log_name: str) -> None:
    project = project_at(source)
    log = (source.parent / log_name).read_text(encoding="utf-8", errors="replace")
    logged = {
        name: number(depth)
        for name, depth in re.findall(r"Hypothetical storm depth for subbasin (.+?): ([\d,.]+) MM", log)
    }
    hms_basin = load_basin(project.basin_path(basin_name))
    assert hms_basin.spatial is not None
    raster = find_grid_file(source.with_suffix(".grid"), "PMP", (source.parent, source.parent.parent))
    depths = DepthGrid.load(raster, hms_basin.spatial.coordinate_system)
    shapes = {
        polygon.name: polygon.shape()
        for polygon in subbasin_polygons(project.basin_path(basin_name).with_suffix(".sqlite"))
    }
    assert len(logged) >= 20
    for name, depth in logged.items():
        assert depths.mean_over([shapes[name]]) == pytest.approx(depth, abs=LOG_DEPTH_ROUNDING_MM), name
