"""W78: domain outlines that cut valleys. Streams across a closed edge before a run, pools held by one after it."""

from __future__ import annotations

import json
import sqlite3

import numpy as np
import pytest

from tests.engine.conftest import CRS, X0, Y0, job, tilted_dem, write_dem  # noqa: F401
from wadi2d.config.schema import EdgeCheck
from wadi2d.edge_valleys import (
    BOWL,
    DEEP,
    ENTERS,
    FILE,
    LEAVES,
    POOL,
    crossing_notes,
    edge_pools,
    pool_notes,
    stream_crossings,
)
from wadi2d.run import EDGE_REACH, run_job

PIXEL = 5.0
SIDE = 2000.0
"""A valley 2 km wide running south down the middle of a 2 km square of ground."""
THALWEG = SIDE / 2 + 3.0
"""Off the pixel lattice's symmetry, so one D8 line carries the valley, not two side by side."""
MID = X0 + THALWEG


def valley(tmp_path):
    """Ground falling 2 % south with sides rising 10 % from a thalweg on x = MID; rows south."""
    n = int(SIDE / PIXEL)
    x = (np.arange(n) + 0.5) * PIXEL
    y = (np.arange(n) + 0.5) * PIXEL
    z = 300.0 - 0.02 * y[:, None] + 0.1 * np.abs(x[None, :] - THALWEG)
    return write_dem(tmp_path / "valley.tif", z, PIXEL)


def valley_job(dem, top: float, bottom: float, lines=(), **parts):
    """The job's extent from ``top`` to ``bottom`` metres south of the DEM's north edge, full width."""
    cfg = job(dem, 1, 1, 20.0, **parts)
    data = cfg.model_dump(mode="json")
    data["grid"]["extent"] = (X0, Y0 - bottom, X0 + SIDE, Y0 - top)
    data["boundaries"] = [{"kind": "free", "coordinates": list(c)} for c in lines]
    return type(cfg).model_validate(data)


SOUTH_LINE = [(MID - 200.0, Y0 - 1500.0), (MID + 200.0, Y0 - 1500.0)]
DEM_END_LINE = [(MID - 200.0, Y0 - SIDE), (MID + 200.0, Y0 - SIDE)]


@pytest.fixture
def ground(tmp_path):
    return valley(tmp_path)


def test_a_valley_leaving_through_a_closed_edge_is_named(ground):
    found = stream_crossings(valley_job(ground, 0.0, 1500.0), CRS)
    assert [c.kind for c in found] == [LEAVES]
    c = found[0]
    assert abs(c.x - MID) <= 20.0 and c.y == pytest.approx(Y0 - 1500.0, abs=1.0)
    assert c.area_km2 == pytest.approx(3.0, rel=0.05)  # the whole valley above the edge
    assert not c.no_ground
    note = crossing_notes(found, EdgeCheck())[0]
    assert "leaves the domain at" in note and "3.0" in note


def test_an_outflow_line_there_makes_it_clean(ground):
    assert stream_crossings(valley_job(ground, 0.0, 1500.0, [SOUTH_LINE]), CRS) == []


def test_an_inflow_line_is_not_an_outlet(ground):
    cfg = valley_job(ground, 0.0, 1500.0)
    data = cfg.model_dump(mode="json")
    data["boundaries"] = [
        {"kind": "flow", "coordinates": SOUTH_LINE, "flow": {"times_s": [0, 60], "flows": [1, 1]}}
    ]
    found = stream_crossings(type(cfg).model_validate(data), CRS)
    assert [c.kind for c in found] == [LEAVES]


def test_a_valley_entering_from_beyond_the_edge_is_named(ground):
    found = stream_crossings(valley_job(ground, 500.0, SIDE, [DEM_END_LINE]), CRS)
    assert [c.kind for c in found] == [ENTERS]
    assert found[0].area_km2 == pytest.approx(1.0, rel=0.1)  # the 500 m of valley north of the domain
    assert "beyond the edge enters" in crossing_notes(found, EdgeCheck())[0]


def test_a_stream_leaving_where_the_dem_ends_says_so(ground):
    found = stream_crossings(valley_job(ground, 0.0, SIDE), CRS)
    assert [c.kind for c in found] == [LEAVES] and found[0].no_ground
    assert "where the DEM ends" in crossing_notes(found, EdgeCheck())[0]


def test_the_threshold_and_the_switch_hold(ground):
    cfg = valley_job(ground, 0.0, 1500.0, outputs={"edge_check": {"stream_km2": 5.0}})
    assert stream_crossings(cfg, CRS) == []
    cfg = valley_job(ground, 0.0, 1500.0, outputs={"edge_check": {"enabled": False}})
    assert stream_crossings(cfg, CRS) == []


def test_the_d8_part_is_cached(ground, tmp_path):
    cfg = valley_job(ground, 0.0, 1500.0)
    first = stream_crossings(cfg, CRS, tmp_path / "cache")
    assert len(list((tmp_path / "cache").glob("edge_streams_*.npz"))) == 1
    assert stream_crossings(cfg, CRS, tmp_path / "cache") == first


class Grid:
    """What the pool check reads of a grid: a square of cells, rows south."""

    def __init__(self, n: int = 20, dx: float = 20.0):
        self.mask = np.ones((n, n), bool)
        self.dx = dx
        self.shape = self.mask.shape

    def xy_of(self, j, i):
        return X0 + (i + 0.5) * self.dx, Y0 - (j + 0.5) * self.dx


def pools_of(grid, depth, zmin, open_cells=None, **check):
    open_cells = np.zeros(grid.shape, bool) if open_cells is None else open_cells
    return edge_pools(grid, depth, zmin, open_cells, EDGE_REACH, 3.0, EdgeCheck(**check))


def test_a_flat_pool_against_the_edge_is_a_pool_once():
    grid = Grid()
    zmin = np.tile(np.linspace(110.0, 100.0, 20)[:, None], (1, 20))  # falling south to the last row
    zmin += np.abs(np.arange(20) - 10)[None, :] * 0.5
    level = 106.0
    depth = np.maximum(level - zmin, 0.0)
    found = pools_of(grid, depth, zmin)
    assert [p.kind for p in found] == [POOL]
    p = found[0]
    assert (
        p.depth_m == pytest.approx(6.0)
        and p.level_m == pytest.approx(level)
        and p.spread_m == pytest.approx(0.0)
    )
    assert p.area_km2 > 5 * grid.dx**2 / 1e6
    assert "a pool the edge holds" in pool_notes(found, EdgeCheck())[0]


def test_one_wet_edge_cell_is_a_bowl():
    grid = Grid()
    zmin = np.full(grid.shape, 100.0)
    depth = np.zeros(grid.shape)
    depth[19, 5] = 9.0
    found = pools_of(grid, depth, zmin)
    assert [p.kind for p in found] == [BOWL]
    assert "past a divide" in pool_notes(found, EdgeCheck())[0]


def test_deep_water_running_along_the_edge_is_not_a_pool():
    grid = Grid()
    zmin = np.tile(np.linspace(100.0, 80.0, 20)[None, :], (20, 1))  # the edge row slopes east
    depth = np.zeros(grid.shape)
    depth[19, :] = 4.0
    found = pools_of(grid, depth, zmin)
    assert [p.kind for p in found] == [DEEP]
    assert pool_notes(found, EdgeCheck())[0].endswith("an edge is a wall, so check the domain polygon there")


def test_deep_water_at_an_open_boundary_is_not_listed():
    grid = Grid()
    zmin = np.full(grid.shape, 100.0)
    depth = np.zeros(grid.shape)
    depth[19, 5] = 9.0
    open_cells = np.zeros(grid.shape, bool)
    open_cells[19, 4:7] = True
    assert pools_of(grid, depth, zmin, open_cells) == []


def test_squares_beside_a_strip_are_joins_not_edges():
    """W80: the squares an aligned corridor replaced leave the mask; deep water beside them is no pool of the edge."""
    grid = Grid()
    zmin = np.full(grid.shape, 100.0)
    depth = np.zeros(grid.shape)
    domain = grid.mask.copy()
    grid.mask[8:12, 4:16] = False  # the corridor's squares
    depth[7, 4:16] = depth[12, 4:16] = 5.0  # the squares either side of it, deep
    assert [p.kind for p in pools_of(grid, depth, zmin)]  # read on the mask alone: false pools
    assert edge_pools(grid, depth, zmin, np.zeros(grid.shape, bool), EDGE_REACH, 3.0, EdgeCheck(), domain) == []
    depth[19, 5] = 9.0  # the outline is still checked
    found = edge_pools(grid, depth, zmin, np.zeros(grid.shape, bool), EDGE_REACH, 3.0, EdgeCheck(), domain)
    assert [p.kind for p in found] == [BOWL] and found[0].depth_m == 9.0


def test_a_strip_run_names_no_pool_at_its_joins(tilted_dem, tmp_path):  # noqa: F811
    """A corridor across the middle of a rained plane: water against the outline may be named, never at the squares
    beside the corridor, however shallow the depth that counts."""
    import re

    from tests.engine.test_strips_run import MID_Y, corridor, plane_job

    cfg = plane_job(tilted_dem, corridor())
    data = cfg.model_dump(mode="json")
    data["outputs"]["edge_depth"] = 0.001  # any water at a join would be listed
    data["outputs"]["edge_check"] = {"max_listed": 1000}
    cfg = type(cfg).model_validate(data)
    out = tmp_path / "run"
    run = run_job(cfg, out, "cpu")
    assert run.exit_code == 0, run.message
    events = [json.loads(line) for line in (out / "progress.jsonl").read_text().splitlines()]
    (built,) = [e for e in events if e.get("ev") == "strips"]
    assert built["replaced"] > 0
    named = [
        (float(x), float(y))
        for e in events
        if e["ev"] == "warn"
        for x, y in re.findall(r"against the domain edge at \((-?[\d.]+), (-?[\d.]+)\)", e["message"])
    ]
    at_joins = [(x, y) for x, y in named if X0 + 30.0 < x < X0 + 170.0 and abs(y - MID_Y) < 24.0]
    assert at_joins == [], at_joins


def test_a_run_against_a_closed_valley_names_both(ground, tmp_path):
    """The whole of it through the engine: the stream before, the pool after, both in the run's file."""
    cfg = valley_job(
        ground, 0.0, 1500.0,
        storm={"kind": "uniform", "depth_mm": 50.0, "duration_min": 30.0},
        run={"duration_s": 5400.0, "backend": "cpu"},
    )  # fmt: skip
    out = tmp_path / "run"
    assert run_job(cfg, out, "cpu").exit_code == 0
    events = [json.loads(line) for line in (out / "progress.jsonl").read_text().splitlines()]
    warned = [e["message"] for e in events if e["ev"] == "warn"]
    assert any("leaves the domain at" in w for w in warned), warned
    assert any("a pool the edge holds" in w for w in warned), warned
    db = sqlite3.connect(out / FILE)
    try:
        assert db.execute("SELECT count(*) FROM edge_streams").fetchone()[0] == 1
        kinds = [k for (k,) in db.execute("SELECT kind FROM edge_pools ORDER BY depth_m DESC")]
    finally:
        db.close()
    assert kinds[0] == POOL


def test_a_run_with_its_outlet_open_names_nothing(ground, tmp_path):
    cfg = valley_job(
        ground, 0.0, 1500.0, [SOUTH_LINE],
        storm={"kind": "uniform", "depth_mm": 50.0, "duration_min": 30.0},
        run={"duration_s": 5400.0, "backend": "cpu"},
    )  # fmt: skip
    out = tmp_path / "run"
    assert run_job(cfg, out, "cpu").exit_code == 0
    events = [json.loads(line) for line in (out / "progress.jsonl").read_text().splitlines()]
    assert not [e for e in events if e["ev"] == "warn" and "domain" in e["message"]]
    assert not (out / FILE).exists()


def test_an_outflow_line_lies_along_the_edge_at_a_leaving_stream() -> None:
    """W106 gap 9: a line on the outline, centred on the crossing, as long as the wadi may be wide; across the seam of
    the ring too; none for a stream that enters."""
    import shapely

    from wadi2d.edge_valleys import ENTERS, LEAVES, OUTFLOW_PER_ROOT_KM2, Crossing, outflow_lines

    square = shapely.box(0.0, 0.0, 10000.0, 10000.0)
    found = [Crossing(10000.0, 5000.0, LEAVES, 400.0), Crossing(0.0, 0.0, LEAVES, 4.0), Crossing(5000.0, 0.0, ENTERS, 50.0)]
    lines = outflow_lines(found, square, 20.0)
    assert len(lines) == 2
    first = shapely.LineString(lines[0]["coordinates"])
    assert first.length == pytest.approx(2.0 * OUTFLOW_PER_ROOT_KM2 * 20.0, rel=1e-6)  # 15 m a root km2, both sides
    assert square.exterior.distance(first) < 1e-6 and first.distance(shapely.Point(10000.0, 5000.0)) < 1e-6
    corner = shapely.LineString(lines[1]["coordinates"])  # on the ring's start: the two pieces joined
    assert corner.length == pytest.approx(400.0, rel=1e-6) and corner.distance(shapely.Point(0.0, 0.0)) < 1e-6
    assert lines[0]["area_km2"] == 400.0
