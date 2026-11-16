"""W95 through the engine: each rain source puts the intended depth on every 2D cell and every lumped subbasin, and the
area reduction split by part puts each part's factor on that part alone (his requirements of 2026-11-15)."""

from __future__ import annotations

import json

import h5py
import numpy as np
import pytest
from pydantic import ValidationError

from tests.engine.conftest import X0, Y0, job, write_dem
from tests.engine.test_handback import CHAIN, DX, MIDDLE, NX, NY, SINK, SUB, plane, write_basin
from tests.engine.test_lumped_network import TABLE as SMALL_TABLE
from tests.engine.test_lumped_network import net_job
from tests.engine.test_network_series import _polygons
from tests.engine.test_rain_run import DX as BOX_DX
from tests.engine.test_rain_run import SIDE, box, gridded, stack
from wadi2d.arf import check_storm
from wadi2d.forcing import Forcing, boundary_set, build_storm
from wadi2d.run import InvalidJob, _lumped_basin, _lumped_rain, arf_tags, run_job
from wadi2d.solver.model import Model
from wadi2d.storm.split_arf import at_study_area

MM_PER_M = 1000.0
CURVE = {"areas_km2": [10.0, 1000.0], "factors": [1.0, 0.5], "table_type": "test table"}
AT_505 = 0.75
SMALL = {"areas_km2": [0.01, 1.0], "factors": [1.0, 0.5], "table_type": "small"}
"""A curve that reduces the 0.1 km2 subbasins of the hybrid case."""
LUMPED_C, GRID_C = 0.6, 0.8
END_MIN = 60.0
FRONT = {"kind": "table", "values": {"time": [0.0, 25.0, 100.0], "depth": [0.0, 60.0, 100.0]}}
SPLIT = {"lumped": {"form": "coefficient", "coefficient": LUMPED_C},
         "grid": {"form": "area", "table": CURVE, "area_km2": 505.0}}  # fmt: skip


def _depth_raster(path, nx: int, ny: int, dx: float) -> tuple[str, np.ndarray]:
    """Depths in mm that differ cell to cell and are exact in float32: 50 + row + column / 4."""
    rows, columns = np.mgrid[0:ny, 0:nx]
    depths = 50.0 + rows + 0.25 * columns
    return str(write_dem(path, depths, dx)), depths


def _cells(cfg, tmp_path):
    """Each interior cell's rain over the storm, mm, float64, and the window's volume as the solver gets it, m3."""
    from wadi2d.run import prepare_grid

    tables, crs = prepare_grid(cfg, tmp_path / "cache")
    model = Model(tables, cfg.numerics, "cpu")
    model.set_depth(np.zeros(tables.grid.shape))
    forcing = Forcing(cfg, tables, model, boundary_set([], tables), build_storm(cfg), {}, [], crs)
    end = END_MIN * 60.0
    excess = forcing._excess_mm(end) - forcing._excess_mm(0.0)
    per_cell = excess if forcing.depths is not None else excess[forcing.class_of]
    return forcing, per_cell, forcing.rate(0.0, end)[1]


def _box_job(tmp_path, storm):
    return job(box(tmp_path), SIDE, SIDE, BOX_DX, storm=storm, run={"duration_s": END_MIN * 60.0})


@pytest.mark.parametrize(
    ("name", "storm", "factor"),
    [
        ("depth", {"kind": "depth", "depth_mm": 80.0, "duration_min": 30.0}, 1.0),
        ("depth, pattern, coefficient", {"kind": "depth", "depth_mm": 80.0, "duration_min": 30.0, "pattern": FRONT,
                                         "area_reduction": {"grid": {"form": "coefficient", "coefficient": GRID_C}}},
         GRID_C),
        ("depth, scs, area", {"kind": "depth", "depth_mm": 80.0, "duration_min": 1440.0,
                              "pattern": {"kind": "scs", "scs_type": "II"}, "area_reduction": SPLIT}, AT_505),
    ],
)  # fmt: skip
def test_a_depth_falls_whole_on_every_cell(tmp_path, name, storm, factor) -> None:
    _forcing, per_cell, volume = _cells(_box_job(tmp_path, storm), tmp_path)
    share = 1.0 if storm["duration_min"] <= END_MIN else float(build_storm(_box_job(tmp_path, storm)).cumulative_depth(
        np.array([END_MIN]))[0]) / (80.0 * factor)  # fmt: skip
    intended = 80.0 * factor * share
    assert per_cell.size == SIDE * SIDE
    assert np.allclose(per_cell, intended, rtol=1e-12, atol=0.0), name
    cell_area = BOX_DX**2
    exact = per_cell.sum() * cell_area / MM_PER_M
    assert exact == pytest.approx(SIDE * SIDE * cell_area * intended / MM_PER_M, rel=1e-9)
    assert volume == pytest.approx(exact, rel=1e-6), "the solver's source is float32"


def test_a_depth_grid_falls_on_each_cell_as_its_own_pixel_says(tmp_path) -> None:
    path, depths = _depth_raster(tmp_path / "depths.tif", SIDE, SIDE, BOX_DX)
    storm = {"kind": "depth_grid", "depth_grid": path, "duration_min": 30.0, "pattern": FRONT,
             "area_reduction": {"grid": {"form": "coefficient", "coefficient": GRID_C}}}  # fmt: skip
    forcing, per_cell, volume = _cells(_box_job(tmp_path, storm), tmp_path)
    rows = np.floor((Y0 - forcing.y) / BOX_DX).astype(int)  # the pixel under each cell's centre
    columns = np.floor((forcing.x - X0) / BOX_DX).astype(int)
    expected = depths[rows, columns] * GRID_C
    assert np.allclose(per_cell, expected, rtol=1e-12, atol=0.0)
    exact = per_cell.sum() * BOX_DX**2 / MM_PER_M
    assert exact == pytest.approx(depths.sum() * GRID_C * BOX_DX**2 / MM_PER_M, rel=1e-9)
    assert volume == pytest.approx(exact, rel=1e-6)
    early = forcing._excess_mm(7.5 * 60.0)  # a quarter of the duration: 60 % of each cell's depth by the pattern
    assert np.allclose(early, 0.6 * expected, rtol=1e-12, atol=0.0)


def test_a_gridded_series_takes_the_2d_part_s_factor_on_every_cell(tmp_path) -> None:
    folder = stack(tmp_path, 40.0, 10.0)
    whole = _cells(_box_job(tmp_path, gridded(folder)), tmp_path / "a")[1]
    split = {"grid": {"form": "coefficient", "coefficient": GRID_C}, "lumped": {"form": "coefficient", "coefficient": 0.5}}
    reduced = _cells(_box_job(tmp_path, gridded(folder, area_reduction=split)), tmp_path / "b")[1]
    assert np.allclose(reduced, GRID_C * whole, rtol=1e-12, atol=0.0)
    assert set(np.round(whole, 4)) == {40.0, 10.0}, "the west and the east halves keep their own rain (float32 frames)"


def _hybrid(tmp_path, storm: dict, own: float | None = None):
    wide = SUB.replace("Subbasin: Side", "Subbasin: Wide").format(down="J")
    basin = write_basin(tmp_path, SUB.format(down="J"), wide, CHAIN, SINK)
    side = {"name": "Side", "mode": "lumped", "outlet": (X0 + 300.0, MIDDLE), "storm_area_km2": own}
    return job(
        plane(tmp_path), NX, NY, DX, storm=storm,
        hydrology={
            "hms_basin": str(basin), "time_step_min": 5.0, "inject_radius": 6.0, "polygons": str(_polygons(tmp_path)),
            "subbasins": [side, {"name": "Wide", "mode": "2d"}],
        },
        run={"duration_s": 7200.0, "backend": "cpu"},
    )  # fmt: skip


def _network_rain(cfg, name: str = "Side") -> float:
    basin, hms, _cut = _lumped_basin(cfg, "")
    storm = _lumped_rain(cfg, build_storm(cfg), basin, hms, "").over(name)
    return float(storm.increments(5.0, 24).sum())


def test_every_source_puts_its_depth_on_a_lumped_subbasin(tmp_path) -> None:
    depth = {"kind": "depth", "depth_mm": 50.0, "duration_min": 60.0, "pattern": FRONT}
    assert _network_rain(_hybrid(tmp_path, depth)) == pytest.approx(50.0, rel=1e-12)
    assert _network_rain(_hybrid(tmp_path, {**depth, "area_reduction": SPLIT})) == pytest.approx(50.0 * LUMPED_C, rel=1e-12)
    path, depths = _depth_raster(tmp_path / "depths.tif", NX, NY, DX)
    grid = {"kind": "depth_grid", "depth_grid": path, "duration_min": 60.0, "area_reduction": SPLIT}
    cfg = _hybrid(tmp_path, grid)
    side = depths[:10, :10].mean()  # Side is the 40 m square at the north-west corner: ten by ten cells of 4 m
    assert _network_rain(cfg) == pytest.approx(side * LUMPED_C, rel=1e-12)
    assert _network_rain(cfg, "Wide") == pytest.approx(depths[:10, 15:25].mean() * LUMPED_C, rel=1e-12)


def test_a_lumped_curve_reads_each_subbasin_at_its_own_area_in_a_hybrid_run(tmp_path) -> None:
    curve = {"lumped": {"form": "curve", "table": SMALL}, "grid": {"form": "coefficient", "coefficient": GRID_C}}
    storm = {"kind": "depth", "depth_mm": 50.0, "duration_min": 60.0, "area_reduction": curve}
    at = float(np.interp(0.1, SMALL["areas_km2"], SMALL["factors"]))
    assert _network_rain(_hybrid(tmp_path, storm)) == pytest.approx(50.0 * at, rel=1e-12), "Side's own 0.1 km2"
    own = float(np.interp(0.5, SMALL["areas_km2"], SMALL["factors"]))
    assert _network_rain(_hybrid(tmp_path, storm, own=0.5)) == pytest.approx(50.0 * own, rel=1e-12)
    assert build_storm(_hybrid(tmp_path, storm)).total_depth == pytest.approx(50.0 * GRID_C, rel=1e-12)


def test_the_hybrid_run_puts_each_part_s_factor_on_that_part_alone(tmp_path) -> None:
    depth = {"kind": "depth", "depth_mm": 50.0, "duration_min": 60.0, "pattern": FRONT}
    plain = run_job(_hybrid(tmp_path, depth), tmp_path / "plain")
    cfg = _hybrid(tmp_path, {**depth, "area_reduction": SPLIT})
    split = run_job(cfg, tmp_path / "split")
    assert plain.exit_code == split.exit_code == 0, split.message
    assert split.balance.rain == pytest.approx(AT_505 * plain.balance.rain, rel=1e-6), "the 2D cells: 0.75"
    assert split.balance.inflow == pytest.approx(LUMPED_C * plain.balance.inflow, rel=1e-6), "Side, CN 100: 0.6"
    lines = (tmp_path / "split" / "progress.jsonl").read_text(encoding="utf-8").splitlines()
    said = [e for e in map(json.loads, lines) if e.get("kind") == "area_reduction"]
    assert [(e["part"], e["form"], e["factor"]) for e in said] == [("lumped", "coefficient", LUMPED_C),
                                                                   ("grid", "area", AT_505)]  # fmt: skip
    words = [e["message"] for e in map(json.loads, lines) if e.get("ev") == "warn"]
    assert "rain on the 2D part: every depth is multiplied by 0.7500, the curve at 505 km2" in words
    assert arf_tags(cfg) == {"arf_lumped": "every depth is multiplied by 0.6000, the given coefficient",
                             "arf_grid": "every depth is multiplied by 0.7500, the curve at 505 km2"}  # fmt: skip


def test_a_lumped_curve_in_a_lumped_only_run_reads_every_element_as_arf_by_element(tmp_path) -> None:
    lumped = {"lumped_only": True, "duration_s": 3600.0}
    old = {"kind": "uniform", "depth_mm": 20.0, "duration_min": 20.0, "arf": SMALL_TABLE, "storm_area_km2": 50.0}
    new = {"kind": "depth", "depth_mm": 20.0, "duration_min": 20.0,
           "area_reduction": {"lumped": {"form": "curve", "table": SMALL_TABLE}}}  # fmt: skip

    def series(name, storm, **hydro):
        cfg = net_job(tmp_path, low="lumped", entry="outlet", storm=storm, run=lumped, hydrology=hydro)
        run = run_job(cfg, tmp_path / name)
        assert run.exit_code == 0, run.message
        with h5py.File(tmp_path / name / "results.h5", "r") as f:
            return {g.attrs["name"]: g["outflow_m3s"][:] for g in f["series/network"].values()}

    each_old = series("old", old, arf_by_element=True)
    each_new = series("new", new)
    assert set(each_old) == set(each_new)
    for element, flow in each_old.items():
        assert np.allclose(each_new[element], flow, rtol=1e-12, atol=0.0), element


def test_what_cannot_apply_is_refused_in_words(tmp_path) -> None:
    depth = {"kind": "depth", "depth_mm": 50.0, "duration_min": 60.0}
    on_grid = {**depth, "area_reduction": {"grid": {"form": "curve", "table": CURVE}}}
    run = run_job(_hybrid(tmp_path, on_grid), tmp_path / "curve")
    assert run.exit_code == 2 and "a fixed area or a coefficient, or run the study" in run.message
    with pytest.raises(InvalidJob, match="every run would be the same run"):
        check_storm(_hybrid(tmp_path, {**depth, "area_reduction": SPLIT}))
    check_storm(_hybrid(tmp_path, on_grid))
    one = at_study_area(_hybrid(tmp_path, on_grid).storm, 505.0)
    assert one.area_reduction.grid.form == "area" and one.area_reduction.grid.area_km2 == 505.0
    with pytest.raises(ValidationError, match=r"a lumped curve in storm\.area_reduction"):
        _hybrid(tmp_path, {**depth, "area_reduction": SPLIT}, own=74.3)
    with pytest.raises(ValidationError, match="not both"):
        _hybrid(tmp_path, {"kind": "uniform", "depth_mm": 50.0, "arf": CURVE, "area_reduction": SPLIT})
    with pytest.raises(ValidationError, match="takes no area reduction"):
        _hybrid(tmp_path, {"kind": "hyetograph", "hyetograph_min": [30.0], "hyetograph_mm": [10.0],
                           "area_reduction": SPLIT})  # fmt: skip
    for bad, words in (
        ({"form": "coefficient", "coefficient": 0.7, "area_km2": 5.0}, "coefficient alone"),
        ({"form": "area", "table": CURVE}, "needs area_km2"),
        ({"form": "curve", "table": CURVE, "area_km2": 5.0}, "takes none"),
        ({"form": "area", "area_km2": 5.0}, "needs a curve"),
        ({"form": "coefficient", "coefficient": 1.2}, "less than or equal to 1"),
    ):
        with pytest.raises(ValidationError, match=words):
            _hybrid(tmp_path, {**depth, "area_reduction": {"grid": bad}})
    with pytest.raises(ValidationError, match="sets neither part"):
        _hybrid(tmp_path, {**depth, "area_reduction": {}})
    assert Y0 > 0.0
