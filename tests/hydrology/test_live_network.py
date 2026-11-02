"""The network below a hand-back, without a grid: causality, the routes, the books."""

from __future__ import annotations

import numpy as np
import pytest

from wadi2d.hydrology import Basin, Junction, LumpedEngine, Reach, Subbasin, TimeGrid
from wadi2d.hydrology.live_network import LiveNetwork, plan_routes
from wadi2d.hydrology.losses import NoLoss
from wadi2d.hydrology.model import Reservoir
from wadi2d.hydrology.reservoir import ReservoirOutflowCurve
from wadi2d.hydrology.routing import LagRouting, MuskingumCunge, NoRouting
from wadi2d.hydrology.transforms import ScsUnitHydrograph
from wadi2d.storm import UniformStorm

DT_MIN = 5.0
DT = DT_MIN * 60.0
N = 120


def pulse(peak: float = 100.0, at: int = 20, width: float = 6.0) -> np.ndarray:
    """A smooth flood from zero to zero; the first ordinate is exactly zero, as a period-ending series always is."""
    q = peak * np.exp(-0.5 * ((np.arange(N + 1) - at) / width) ** 2)
    q[0] = 0.0
    return q


MC = MuskingumCunge(6000.0, 0.01, 0.04, 30.0, 2.0, 3.0)
POOL = ReservoirOutflowCurve(
    np.array([100.0, 104.0, 110.0, 120.0]),
    np.array([1.0e5, 1.4e5, 2.0e5, 4.0e5]),
    np.array([100.0, 104.0, 120.0]),
    np.array([0.0, 0.0, 800.0]),
    100.0,
)


def line_of(routing, name="R1") -> Basin:
    return Basin("b", [Junction("J0", name), Reach(name, "OUT", routing), Junction("OUT", None)])


def network(basin: Basin, entries, exits, storm=None) -> LiveNetwork:
    routes = plan_routes(basin, entries, exits)
    base = LumpedEngine(basin).run(storm, TimeGrid(DT_MIN, N), None, None, routes.cut) if storm else None
    if base is None:
        base = LumpedEngine(basin).run(None, TimeGrid(DT_MIN, N), routes.live, None, routes.cut)
    return LiveNetwork(basin, routes, base)


@pytest.mark.parametrize("routing", [LagRouting(17.0), NoRouting(), MC], ids=["lag", "none", "mc"])
def test_the_routing_is_causal_so_a_rerun_on_the_series_so_far_is_the_true_series(routing):
    q = pulse()
    whole = routing.route(q, DT_MIN)
    for k in (1, 7, 20, 21, 55, N):
        assert routing.route(q[: k + 1], DT_MIN)[k] == whole[k]


def test_the_reservoir_is_causal_too():
    q = pulse(300.0)
    whole = POOL.route(q, DT_MIN)
    for k in (1, 7, 20, 21, 55, N):
        assert POOL.route(q[: k + 1], DT_MIN)[k] == whole[k]


def test_a_route_stops_at_the_reentry_and_cuts_the_link_below_it():
    basin = Basin(
        "b", [Reach("R0", "R1", LagRouting(5.0)), Reach("R1", "R2", LagRouting(5.0)), Reach("R2", None, NoRouting())]
    )
    routes = plan_routes(basin, ["R1"], ["R1"])
    assert routes.live == ("R1",)
    assert routes.cut == {("R0", "R1"), ("R1", "R2")}
    assert routes.ends == ()


def test_a_route_with_no_reentry_runs_to_the_end_of_the_network():
    basin = line_of(LagRouting(5.0))
    routes = plan_routes(basin, ["R1"], [])
    assert routes.live == ("R1", "OUT")
    assert routes.ends == (("OUT", False),)


def test_a_second_handback_on_the_route_is_refused_it_would_swallow_the_water():
    basin = Basin("b", [Reach("R1", "R2", NoRouting()), Reach("R2", None, NoRouting())])
    with pytest.raises(ValueError, match="would be lost"):
        plan_routes(basin, ["R1", "R2"], [])


def test_two_handbacks_in_series_are_fine_when_the_first_reenters_above_the_second():
    basin = Basin("b", [Reach("R1", "R2", NoRouting()), Reach("R2", None, NoRouting())])
    routes = plan_routes(basin, ["R1", "R2"], ["R1", "R2"])
    assert set(routes.live) == {"R1", "R2"}


def test_a_route_through_a_subbasin_is_refused():
    area = Subbasin("S", None, 1.0, NoLoss(), ScsUnitHydrograph(30.0))
    basin = Basin("b", [Reach("R1", "S", NoRouting()), area])
    with pytest.raises(ValueError, match="subbasin S"):
        plan_routes(basin, ["R1"], [])


def test_an_unknown_element_is_refused():
    with pytest.raises(ValueError, match="unknown element"):
        plan_routes(line_of(NoRouting()), ["nope"], [])


def test_a_plain_lag_holds_exactly_what_the_lag_says_and_has_no_defect():
    live = network(line_of(LagRouting(25.0)), ["R1"], ["R1"])
    q = pulse()
    k = 22
    series = {"R1": q[: k + 1]}
    # water that left: every held ordinate up to k - 1
    run = live.route(series)
    left = float(run.outflow["R1"][:k].sum()) * DT
    line = float(series["R1"].sum()) * DT
    books = live.settle(series, line, k, left, ["R1"])
    # a lag of 5 steps holds the 5 last inflow ordinates and the one the hold has not passed on yet
    assert books.storage == pytest.approx(float(q[k - 5 : k + 1].sum()) * DT, rel=1e-12)
    assert books.defect == pytest.approx(0.0, abs=1e-6)
    assert books.drained


def test_muskingum_cunge_shows_its_own_mass_error_as_a_defect_not_as_storage():
    live = network(line_of(MC), ["R1"], ["R1"])
    q = pulse(400.0)
    series = {"R1": q}
    run = live.route(series)
    line = float(q.sum()) * DT
    books = live.settle(series, line, N, float(run.outflow["R1"][:N].sum()) * DT, ["R1"])
    assert books.drained
    # the flood has gone by the end of the series: nothing is left in the reach, whatever the routing did to the volume
    assert abs(books.storage) < 1e-4 * line
    assert books.defect == pytest.approx(line - float(run.outflow["R1"].sum()) * DT - books.storage, abs=1e-6)


def test_a_reservoir_keeps_what_its_pool_says():
    basin = Basin("b", [Reservoir("D", "OUT", POOL), Junction("OUT", None)])
    live = network(basin, ["D"], ["D"])
    q = pulse(200.0)
    series = {"D": q}
    run = live.route(series)
    line = float(q.sum()) * DT
    books = live.settle(series, line, N, float(run.outflow["D"][:N].sum()) * DT, ["D"])
    # the pool ends on its dead storage, below the 104 m sill: conic from the table, not from the flows
    assert books.drained
    assert line > POOL.storage_m3[1] > 0.0
    assert books.storage == pytest.approx(POOL.storage_m3[1], rel=1e-3)
    assert abs(books.defect) < 1e-6 * line


def test_a_subbasin_joining_below_the_handback_comes_in_as_a_frozen_lateral():
    basin = Basin(
        "b",
        [
            Reach("R1", "J", LagRouting(10.0)),
            Subbasin("S", "J", 5.0, NoLoss(), ScsUnitHydrograph(30.0)),
            Junction("J", "R2"),
            Reach("R2", None, LagRouting(10.0)),
        ],
    )
    storm = UniformStorm(depth_mm=20.0, duration_minutes=60.0)
    live = network(basin, ["R1"], ["R2"], storm)
    assert set(live.lateral) == {"J"}
    q = np.zeros(N + 1)
    run = live.route({"R1": q})
    assert run.outflow["R2"].max() > 1.0  # the subbasin alone
    plain = LumpedEngine(basin).run(storm, TimeGrid(DT_MIN, N))
    np.testing.assert_allclose(run.outflow["R2"], plain.outflow["R2"], atol=1e-12)
