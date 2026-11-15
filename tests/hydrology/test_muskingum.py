"""Muskingum reach routing: a textbook example by hand, HEC-HMS 4.12 run headless, and the rules of the range.

The textbook is Chow, Maidment and Mays (1988), Applied Hydrology, Example 8.4.1 (Table 8.4.1): K = 2.3 h, X = 0.15,
a 1 h step, C1 = 0.0631, C2 = 0.3442, C3 = 0.5927, the outflow starting at 85 cfs. The oracle is W89's cases in
``tests/data/hms_muskingum``: W59's metric test project with a Source, a Reach and a Sink per basin, each basin re-saved
by HMS itself (so every key is one HMS reads), and HMS's series and messages of each run.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from wadi2d.config.schema import REACH_CONSERVING, REACH_MUSKINGUM, Hydrology
from wadi2d.hms import load_basin
from wadi2d.hms.methods import MuskingumRoute
from wadi2d.hydrology import ROUTING_METHODS
from wadi2d.hydrology.from_hms import basin_from_hms, reach_from_hms
from wadi2d.hydrology.model import Basin, Junction, Reach
from wadi2d.hydrology.muskingum import MUSKINGUM, Muskingum, reach_notes, stable_subreaches
from wadi2d.hydrology.network import LumpedEngine
from wadi2d.hydrology.routing import MuskingumCunge

DATA = Path(__file__).resolve().parents[1] / "data" / "hms_muskingum"
STEP_MINUTES = 5.0
EXACT_OF_PEAK = 1.0e-12
"""A closed form: HMS's arithmetic to round-off, far inside W59's 3e-4 of peak for its solved structures."""
HMS_UNSTABLE = "WARNING 41169"
CASES = json.loads((DATA / "cases.json").read_text(encoding="utf-8"))

CHOW_INFLOW = [93, 137, 208, 320, 442, 546, 630, 678, 691, 675, 634, 571, 477, 390, 329, 247, 184, 134, 108, 90]
CHOW_OUTFLOW = [85, 91, 114, 159, 233, 324, 420, 509, 578, 623, 642, 635, 603, 546, 479, 413, 341, 274, 215, 170]
CHOW_K_HOURS, CHOW_X, CHOW_STEP_MINUTES, CHOW_START = 2.3, 0.15, 60.0, 85.0


def load_case(case: str) -> dict[str, np.ndarray]:
    with (DATA / f"{case}.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return {key: np.array([float(row[key]) for row in rows]) for key in rows[0]}


def reach_of(case: str) -> Reach:
    hms_reach = next(e for e in load_basin(DATA / f"{case}.basin").elements if e.name == "Reach")
    return reach_from_hms(hms_reach)


def test_the_textbook_coefficients() -> None:
    c1, c2, c3 = Muskingum(CHOW_K_HOURS, CHOW_X).coefficients(CHOW_STEP_MINUTES)
    assert (round(c1, 4), round(c2, 4), round(c3, 4)) == (0.0631, 0.3442, 0.5927)
    assert c1 + c2 + c3 == pytest.approx(1.0, abs=1e-15)


def test_the_textbook_outflow_by_hand() -> None:
    """The book starts at 85 cfs under an inflow of 93; a reach here starts at its inflow, and the routing is linear,
    so the two series differ by the 8 cfs of the start decaying as C3 to the step: the book's column to its unit."""
    method = Muskingum(CHOW_K_HOURS, CHOW_X)
    inflow = np.array(CHOW_INFLOW, dtype=np.float64)
    c1, c2, c3 = method.coefficients(CHOW_STEP_MINUTES)
    by_hand = [CHOW_START]
    for t in range(1, len(inflow)):
        by_hand.append(c1 * inflow[t] + c2 * inflow[t - 1] + c3 * by_hand[-1])
    assert np.abs(np.array(by_hand) - CHOW_OUTFLOW).max() <= 1.0  # the book rounds every line
    routed = method.route(inflow, CHOW_STEP_MINUTES)
    decay = (inflow[0] - CHOW_START) * c3 ** np.arange(len(inflow))
    assert routed - decay == pytest.approx(np.array(by_hand), abs=1e-10)
    assert routed.max() == pytest.approx(642.0 + decay[10], abs=1.0)
    assert int(np.argmax(routed)) == int(np.argmax(CHOW_OUTFLOW)) == 10


@pytest.mark.parametrize("case", sorted(CASES))
def test_the_hms_file_is_read_whole(case: str) -> None:
    """Every key HEC-HMS 4.12 wrote back for a Muskingum reach is one the reader maps."""
    hms_reach = next(e for e in load_basin(DATA / f"{case}.basin").elements if e.name == "Reach")
    assert isinstance(hms_reach.route, MuskingumRoute)
    assert not hms_reach.unknown
    routing = reach_of(case).routing
    expected = CASES[case]
    assert isinstance(routing, Muskingum)
    assert (routing.k_hours, routing.x, routing.subreaches) == (expected["k_hours"], expected["x"], expected["subreaches"])


@pytest.mark.parametrize("case", sorted(CASES))
def test_the_outflow_is_hms_to_round_off(case: str) -> None:
    series = load_case(case)
    routed = reach_of(case).routing.route(series["inflow"], STEP_MINUTES)
    assert np.abs(routed - series["outflow"]).max() <= EXACT_OF_PEAK * series["inflow"].max()
    assert routed.max() == pytest.approx(series["outflow"].max(), rel=1e-13)
    assert int(np.argmax(routed)) == int(np.argmax(series["outflow"]))


@pytest.mark.parametrize("case", sorted(CASES))
def test_a_note_where_hms_warns_and_nowhere_else(case: str) -> None:
    warned = any(HMS_UNSTABLE in message for message in CASES[case]["hms_messages"])
    reach = reach_of(case)
    note = reach.routing.note("Reach", STEP_MINUTES)
    assert (note is not None) == warned
    assert reach.routing.is_stable(STEP_MINUTES) != warned
    basin = Basin("b", [reach, Junction(name="Outlet", downstream=None)])
    assert len(reach_notes(basin, STEP_MINUTES)) == int(warned)
    if warned:
        assert "Reach" in note and "41169" in note


def test_outside_the_range_the_outflow_goes_where_hms_goes() -> None:
    """Nothing is clipped: under 2KX a dry bed reads below zero, as HMS's reach does before its sink zeroes it."""
    low = load_case("musk_dry_low")
    routed = reach_of("musk_dry_low").routing.route(low["inflow"], STEP_MINUTES)
    assert low["outflow"].min() < -2.0
    assert routed.min() == pytest.approx(low["outflow"].min(), abs=1e-10)
    inside = reach_of("musk_dry_in").routing.route(load_case("musk_dry_in")["inflow"], STEP_MINUTES)
    assert inside.min() >= 0.0


@pytest.mark.parametrize("case", ["musk_in_range", "musk_long", "musk_x0", "musk_dry_in", "musk_dry_low"])
def test_the_books_close(case: str) -> None:
    """Inflow less outflow over the run is what the reach holds more at the end, K [X I + (1 - X) O] per subreach."""
    series = load_case(case)
    method = reach_of(case).routing
    routed = method.route(series["inflow"], STEP_MINUTES)
    held = method.storage_m3(series["inflow"], STEP_MINUTES)
    seconds = STEP_MINUTES * 60.0
    passed = (0.5 * (series["inflow"][1:] + series["inflow"][:-1]) - 0.5 * (routed[1:] + routed[:-1])).sum() * seconds
    assert passed == pytest.approx(held[-1] - held[0], abs=1e-6 * np.abs(held).max())


def test_half_and_a_step_per_subreach_only_moves_the_wave() -> None:
    """X = 0.5 with K / n equal to the step: C1 = 0, C2 = 1, C3 = 0, each subreach a delay of one step."""
    method = Muskingum(k_hours=1.0, x=0.5, subreaches=12)
    assert method.coefficients(STEP_MINUTES) == pytest.approx((0.0, 1.0, 0.0), abs=1e-15)
    inflow = 300.0 * np.exp(-(((np.arange(200) - 60) / 12.0) ** 2))
    routed = method.route(inflow, STEP_MINUTES)
    assert routed[12:] == pytest.approx(inflow[:-12], abs=1e-12)
    assert method.is_stable(STEP_MINUTES)


def test_more_subreaches_attenuate_less() -> None:
    inflow = 300.0 * np.exp(-(((np.arange(400) - 60) / 12.0) ** 2))
    peaks = [Muskingum(2.0, 0.2, n).route(inflow, STEP_MINUTES).max() for n in (5, 10, 20, 38)]
    assert peaks == sorted(peaks)
    assert all(Muskingum(2.0, 0.2, n).is_stable(STEP_MINUTES) for n in (10, 20, 38))


@pytest.mark.parametrize(
    ("k_hours", "x", "expected"),
    [(1.0, 0.2, (5, 19)), (3.0, 0.3, (22, 50)), (1.0, 0.5, (12, 12)), (0.05, 0.2, (1, 0)), (1.5, 0.0, (1, 36))],
)
def test_the_stable_subreaches(k_hours: float, x: float, expected: tuple[int, int]) -> None:
    fewest, most = stable_subreaches(k_hours, x, STEP_MINUTES)
    assert (fewest, most) == expected
    for count in (fewest, most):
        if fewest <= most:
            assert Muskingum(k_hours, x, count).is_stable(STEP_MINUTES)
    if fewest > 1:
        assert not Muskingum(k_hours, x, fewest - 1).is_stable(STEP_MINUTES)
    if most >= 1:
        assert not Muskingum(k_hours, x, most + 1).is_stable(STEP_MINUTES)


def test_a_note_names_the_cure() -> None:
    assert "5 to 19 subreaches are stable" in Muskingum(1.0, 0.2, 1).note("R1", STEP_MINUTES)
    assert "under 2KX" in Muskingum(1.0, 0.2, 1).note("R1", STEP_MINUTES)
    assert "over 2K(1-X)" in Muskingum(1.0, 0.2, 40).note("R1", STEP_MINUTES)
    assert "no number of subreaches is stable" in Muskingum(0.05, 0.2, 1).note("R1", STEP_MINUTES)
    assert Muskingum(1.0, 0.2, 12).note("R1", STEP_MINUTES) is None


@pytest.mark.parametrize(
    "bad", [{"k_hours": 0.0, "x": 0.2}, {"k_hours": 1.0, "x": 0.6}, {"k_hours": 1.0, "x": -0.1},
            {"k_hours": 1.0, "x": 0.2, "subreaches": 0}, {"k_hours": 1.0, "x": 0.2, "subreaches": 2.5},
            {"k_hours": None, "x": 0.2}],
)
def test_numbers_outside_what_hms_takes_are_refused(bad: dict) -> None:
    with pytest.raises(ValueError, match="Muskingum"):
        ROUTING_METHODS.build(MUSKINGUM, **bad)


def test_it_runs_in_the_network() -> None:
    reach = Reach(name="R", downstream="Out", routing=ROUTING_METHODS.build(MUSKINGUM, k_hours=1.0, x=0.2, subreaches=12))
    basin = Basin("b", [reach, Junction(name="Out", downstream=None)])
    series = load_case("musk_in_range")
    from wadi2d.hydrology.model import TimeGrid

    run = LumpedEngine(basin).run(None, TimeGrid(STEP_MINUTES, len(series["inflow"]) - 1), external={"R": series["inflow"]})
    assert np.abs(run.outflow["Out"] - series["outflow"]).max() <= EXACT_OF_PEAK * 400.0


# The job's choice on an HMS basin: tests/data/hms holds Block 2-like Muskingum-Cunge reaches when present; a basin
# written here keeps the test free of project data.
MC_BASIN = """Basin: T
     Version: 4.12
     Unit System: Metric
End:

Reach: R1
     Downstream: J

     Route: Muskingum Cunge
     Channel: Trapezoid
     Length: 9000
     Energy Slope: 0.012
     Mannings n: 0.1
     Bottom Width: 60
     Side Slope: 1.5
     Initial Variable: Combined Inflow
     Space-Time Method: Automatic DX and DT
     Index Parameter Type: Index Celerity
     Index Celerity: 1.524
     Number Subreaches: 1
     Maximum Depth Iterations: 20
     Maximum Route Step Iterations: 30
     Channel Loss: None
End:

Reach: R2
     Downstream: J

     Route: Muskingum
     Initial Variable: Combined Inflow
     Muskingum K: 0.5
     Muskingum x: 0.25
     Muskingum Steps: 6
     Channel Loss: None
End:

Reach: R3
     Downstream: J

     Route: Lag
     Lag: 30
     Channel Loss: None
End:

Junction: J
End:
"""


@pytest.fixture
def mc_basin(tmp_path: Path):
    path = tmp_path / "t.basin"
    path.write_text(MC_BASIN, encoding="utf-8")
    return load_basin(path)


def entry(k: float, x: float, n: int = 1) -> SimpleNamespace:
    return SimpleNamespace(k_hours=k, x=x, subreaches=n)


def test_a_file_reach_keeps_its_own_method_under_every_choice(mc_basin) -> None:
    for choice in ("hms", REACH_CONSERVING):
        basin = basin_from_hms(mc_basin, reach_routing=choice)
        assert isinstance(basin.elements["R1"].routing, MuskingumCunge)
        assert basin.elements["R1"].routing.scheme == choice
        own = basin.elements["R2"].routing
        assert isinstance(own, Muskingum) and (own.k_hours, own.x, own.subreaches) == (0.5, 0.25, 6)


def test_muskingum_without_k_and_x_stops_and_names_the_reach(mc_basin) -> None:
    with pytest.raises(ValueError, match=r"no K and X for \['R1'\]"):
        basin_from_hms(mc_basin, reach_routing=REACH_MUSKINGUM)


def test_muskingum_takes_the_jobs_numbers_and_leaves_the_rest(mc_basin) -> None:
    basin = basin_from_hms(mc_basin, reach_routing=REACH_MUSKINGUM, muskingum={"R1": entry(1.2, 0.3, 14)})
    first = basin.elements["R1"].routing
    assert isinstance(first, Muskingum) and (first.k_hours, first.x, first.subreaches) == (1.2, 0.3, 14)
    assert basin.elements["R2"].routing.k_hours == 0.5  # the file's own Muskingum reach, not listed
    assert type(basin.elements["R3"].routing).__name__ == "LagRouting"
    listed = basin_from_hms(
        mc_basin, reach_routing=REACH_MUSKINGUM, muskingum={"R1": entry(1.2, 0.3), "R2": entry(0.7, 0.1, 8)}
    )
    assert listed.elements["R2"].routing.k_hours == 0.7


def test_a_name_that_is_no_reach_is_refused(mc_basin) -> None:
    with pytest.raises(ValueError, match="names \\['R9'\\]"):
        basin_from_hms(mc_basin, reach_routing=REACH_MUSKINGUM, muskingum={"R1": entry(1.0, 0.2), "R9": entry(1.0, 0.2)})


def test_a_specified_start_or_a_channel_loss_is_refused(tmp_path: Path) -> None:
    for old, new in (("Initial Variable: Combined Inflow\n     Muskingum K", "Initial Variable: Outflow\n     Muskingum K"),
                     ("Muskingum Steps: 6\n     Channel Loss: None", "Muskingum Steps: 6\n     Channel Loss: Constant")):
        assert old in MC_BASIN
        path = tmp_path / "bad.basin"
        path.write_text(MC_BASIN.replace(old, new), encoding="utf-8")
        with pytest.raises(ValueError, match="unsupported Muskingum options"):
            basin_from_hms(load_basin(path))


def test_the_job_refuses_numbers_it_would_ignore() -> None:
    rows = [{"reach": "R1", "k_hours": 1.0, "x": 0.2}]
    assert Hydrology(reach_routing="muskingum", muskingum=rows).muskingum[0].subreaches == 1
    with pytest.raises(ValueError, match="would be ignored"):
        Hydrology(muskingum=rows)
    with pytest.raises(ValueError, match="twice"):
        Hydrology(reach_routing="muskingum", muskingum=rows + rows)
    with pytest.raises(ValueError):
        Hydrology(reach_routing="muskingum", muskingum=[{"reach": "R1", "k_hours": 1.0, "x": 0.7}])
