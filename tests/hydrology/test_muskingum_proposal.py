"""The K, X and subreaches proposed for a Muskingum reach: hand numbers, the rules of the count and of X, and the
command. No project data."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from tests.hydrology.test_muskingum import MC_BASIN
from wadi2d.basin.parameters import kirpich_travel_minutes
from wadi2d.engine.cli import main
from wadi2d.engine.muskingum_proposals import BASIS_KIRPICH, proposal_table, propose_reaches
from wadi2d.hydrology.muskingum import Muskingum
from wadi2d.hydrology.muskingum_proposal import (
    BASIS_FLOW,
    BASIS_INDEX,
    BASIS_VELOCITY,
    DEFAULT_X,
    at_index_celerity,
    at_reference_flow,
    at_travel_time,
    at_velocity,
    flow_at_celerity,
    section_state,
)
from wadi2d.hydrology.routing import MuskingumCunge

# A wide rectangle by hand: 100 m, n 0.03, S 0.001, 2 m deep. A 200, P 104, R 1.9231, V = R^(2/3) sqrt(S) / n
# = 1.5464 x 0.031623 / 0.03 = 1.6300 m/s, Q = 326.0 m3/s; c = V (5/3 - 2/3 R 2 / B) = 1.6300 x 1.6410 = 2.6749 m/s.
WIDTH, SIDE, SLOPE, MANNING = 100.0, 0.0, 0.001, 0.03
FLOW, DEPTH, VELOCITY, CELERITY = 326.0, 2.0, 1.6300, 2.6749
SECTION = (SLOPE, MANNING, WIDTH, SIDE)


def test_the_section_by_hand() -> None:
    state = section_state(FLOW, WIDTH, SIDE, SLOPE, MANNING)
    assert state.depth_m == pytest.approx(DEPTH, abs=2e-4)
    assert state.velocity_ms == pytest.approx(VELOCITY, rel=2e-4)
    assert state.celerity_ms == pytest.approx(CELERITY, rel=2e-4)
    assert state.top_width_m == WIDTH


def test_the_wave_speed_is_the_slope_of_the_rating_over_the_width() -> None:
    """Seddon's law on a trapezoid, against a difference of the rating itself."""
    low, high = (section_state(q, 60.0, 1.5, 0.012, 0.1) for q in (999.0, 1001.0))
    middle = section_state(1000.0, 60.0, 1.5, 0.012, 0.1)
    assert middle.celerity_ms == pytest.approx(2.0 / (high.area_m2 - low.area_m2), rel=1e-5)


def test_cunge_by_hand() -> None:
    """10 km at the hand section, a 10 min step: K = 10,000 / 2.6749 = 3,738 s = 1.0384 h; 6 subreaches of 1,667 m;
    X = 1/2 (1 - 326 / (100 x 0.001 x 2.6749 x 1,666.7)) = 1/2 (1 - 0.7312) = 0.134."""
    found = at_reference_flow(10_000.0, *SECTION, FLOW, 10.0)
    assert found.k_hours == pytest.approx(1.0384, abs=2e-4)
    assert found.subreaches == 6
    assert found.x == pytest.approx(0.134, abs=1e-3)
    assert found.x_cunge == pytest.approx(found.x, abs=5e-4)
    assert found.basis == BASIS_FLOW and found.stable
    assert found.reference_flow_m3s == FLOW and found.celerity_ms == pytest.approx(CELERITY, rel=2e-4)
    assert "Cunge (1969) at 326 m3/s" in found.words and "6 subreaches of 1,667 m" in found.words
    assert Muskingum(found.k_hours, found.x, found.subreaches).is_stable(10.0)


def test_what_is_shown_is_what_is_used() -> None:
    found = at_reference_flow(26_008.98, 0.01241, 0.1, 60.0, 0.7, 1200.0, 5.0)
    assert found.k_hours == round(found.k_hours, 4) and found.x == round(found.x, 3)
    assert f"K = L / c = {found.k_hours:g} h" in found.words


def test_a_proposal_at_the_flood_routes_like_muskingum_cunge() -> None:
    """Constant K and X taken at a flood's own size give the variable-parameter scheme's peak and timing closely."""
    reach = MuskingumCunge(26_008.98, 0.01241, 0.1, 60.0, 0.7, 1.524)
    step = 5.0
    inflow = 1100.0 * np.exp(-(((np.arange(600) - 160) / 36.0) ** 2))
    reference = reach.route(inflow, step)
    found = at_reference_flow(26_008.98, 0.01241, 0.1, 60.0, 0.7, 1100.0, step)
    routed = Muskingum(found.k_hours, found.x, found.subreaches).route(inflow, step)
    assert found.stable and 0.3 < found.x <= 0.5
    assert routed.max() == pytest.approx(reference.max(), rel=0.02)
    assert abs(int(np.argmax(routed)) - int(np.argmax(reference))) <= 3
    small = at_reference_flow(26_008.98, 0.01241, 0.1, 60.0, 0.7, 20.0, step)
    assert small.k_hours > 2.0 * found.k_hours  # a small flood travels far slower: why fixed numbers drift


def test_the_index_celerity_stands_in_for_a_reference_flow() -> None:
    flow = flow_at_celerity(1.524, 60.0, 1.5, 0.012, 0.1)
    assert section_state(flow, 60.0, 1.5, 0.012, 0.1).celerity_ms == pytest.approx(1.524, rel=1e-9)
    found = at_index_celerity(9000.0, 0.012, 0.1, 60.0, 1.5, 1.524, 5.0)
    assert found.basis == BASIS_INDEX
    assert found.k_hours == pytest.approx(9000.0 / 1.524 / 3600.0, abs=1e-4)
    assert found.reference_flow_m3s == pytest.approx(flow)
    assert "give a reference flow" in found.words
    assert at_index_celerity(9000.0, 0.012, 0.1, 60.0, 1.5, 500.0, 5.0) is None  # no flow travels that fast


def test_a_negative_x_becomes_zero_on_one_subreach() -> None:
    """A wide, flat, short reach diffuses more than Muskingum can: X = 0 and one subreach, the most it has."""
    found = at_reference_flow(600.0, 0.0002, 0.03, 300.0, 0.0, 900.0, 1.0)
    assert found.x_cunge < 0.0 and found.x == 0.0 and found.subreaches == 1
    assert "below what HMS takes" in found.words
    assert found.stable


def test_x_is_lowered_where_no_count_is_stable_with_cunges() -> None:
    """K near 7.3 min at a 5 min step: one subreach asks 2KX <= 5, two ask 5 <= 2K(1-X); neither holds with Cunge's
    X of about 0.42, so one subreach keeps and X comes down to step / 2K."""
    found = at_reference_flow(660.0, 0.003, 0.038, 60.0, 0.0, 26.7, 5.0)
    assert 7.0 < found.k_hours * 60.0 < 7.6 and found.x_cunge > 0.40
    assert found.subreaches == 1 and found.stable
    assert found.x < found.x_cunge - 0.05
    assert found.x == pytest.approx(5.0 / (2.0 * found.k_hours * 60.0), abs=1e-3)
    assert "lowered" in found.words
    assert Muskingum(found.k_hours, found.x, 1).is_stable(5.0)


def test_rounding_x_to_what_is_shown_never_leaves_the_stable_range() -> None:
    for flow in np.geomspace(5.0, 3000.0, 60):
        for length in (700.0, 2500.0, 9000.0, 26_000.0):
            found = at_reference_flow(length, 0.012, 0.1, 60.0, 1.5, float(flow), 5.0)
            assert Muskingum(found.k_hours, found.x, found.subreaches).is_stable(5.0) == found.stable
            assert found.stable or found.k_hours * 60.0 < 2.5


def test_a_reach_crossed_in_under_half_a_step_is_said_to_be_unroutable() -> None:
    found = at_reference_flow(180.0, 0.003, 0.038, 60.0, 0.0, 26.7, 5.0)
    assert not found.stable and found.subreaches == 1
    assert "under half a step" in found.words and "NOT stable" in found.words


def test_a_velocity_gives_k_and_a_default_x() -> None:
    """9 km at 2 m/s: wave speed 1.5 x 2 = 3 m/s, K = 3,000 s = 0.8333 h, 10 subreaches at 5 min, X the default."""
    found = at_velocity(9000.0, 2.0, 5.0)
    assert (found.k_hours, found.x, found.subreaches) == (0.8333, DEFAULT_X, 10)
    assert found.basis == BASIS_VELOCITY and found.stable and found.celerity_ms == 3.0
    assert "a default and not a property of this reach" in found.words and "EM 1110-2-1417" in found.words
    assert found.x_cunge is None


def test_a_travel_time_gives_k() -> None:
    found = at_travel_time(47.0, 5.0, "Measured between two gauges:")
    assert (found.k_hours, found.subreaches) == (0.7833, 9)
    assert found.words.startswith("Measured between two gauges: K = 0.7833 h. 9 subreaches")
    short = at_travel_time(3.0, 5.0, "Short:")
    assert short.subreaches == 1 and short.stable and short.x == pytest.approx(0.166, abs=1e-3)  # 1 - 5 / 6, cut
    assert "lowered" in short.words


def test_kirpich_on_a_reach_by_hand() -> None:
    # 9,000 m at 0.012: 9000^0.77 = 1108.5, 0.012^0.385 = 0.18220, / 52 = 117.0 min
    assert kirpich_travel_minutes(9000.0, 0.012) == pytest.approx(117.0, rel=2e-3)
    assert kirpich_travel_minutes(9000.0, 0.012) == pytest.approx(9000.0**0.77 / (52.0 * 0.012**0.385))


@pytest.mark.parametrize("bad", [0.0, -5.0])
def test_numbers_that_mean_nothing_are_refused(bad: float) -> None:
    with pytest.raises(ValueError):
        at_reference_flow(9000.0, 0.012, 0.1, 60.0, 1.5, bad, 5.0)
    with pytest.raises(ValueError):
        at_velocity(9000.0, bad, 5.0)
    with pytest.raises(ValueError):
        at_travel_time(bad, 5.0, "")


@pytest.fixture
def hms_file(tmp_path: Path) -> Path:
    path = tmp_path / "t.basin"
    path.write_text(MC_BASIN, encoding="utf-8")
    return path


def test_every_reach_of_an_hms_basin_gets_the_best_basis_its_data_allow(hms_file: Path) -> None:
    found = propose_reaches(hms_file, 5.0)
    rows = {row["name"]: row for row in found["reaches"]}
    assert found["kind"] == "hms" and list(rows) == ["R1", "R2", "R3"]
    assert rows["R1"]["method"] == "Muskingum Cunge" and rows["R1"]["proposal"]["basis"] == BASIS_INDEX
    assert rows["R2"]["own"] == {"k_hours": 0.5, "x": 0.25, "subreaches": 6} and rows["R2"]["proposal"] is None
    assert "its own K and X" in rows["R2"]["words"]
    assert rows["R3"]["proposal"] is None and rows["R3"]["words"].startswith("No proposal")
    at_flow = propose_reaches(hms_file, 5.0, {"R1": 800.0})["reaches"][0]["proposal"]
    assert at_flow["basis"] == BASIS_FLOW and at_flow["reference_flow_m3s"] == 800.0
    assert at_flow["k_hours"] < rows["R1"]["proposal"]["k_hours"]
    assert json.loads(json.dumps(found)) == found


def test_a_reference_flow_for_no_reach_is_refused(hms_file: Path) -> None:
    with pytest.raises(ValueError, match=r"reference flows for \['R9'\]"):
        propose_reaches(hms_file, 5.0, {"R9": 100.0})


def test_the_command_prints_or_writes_and_changes_nothing(hms_file: Path, tmp_path: Path, capsys) -> None:
    before = hms_file.read_bytes()
    assert main(["muskingum", str(hms_file), "--flow", "R1=800"]) == 0
    printed = capsys.readouterr().out
    assert "R1 (Muskingum Cunge): K " in printed and "Cunge (1969) at 800 m3/s" in printed
    assert "nothing is used until it is written into hydrology.muskingum" in printed
    out = tmp_path / "found.json"
    assert main(["muskingum", str(hms_file), "--dt", "10", "--out", str(out)]) == 0
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["step_minutes"] == 10.0 and len(written["reaches"]) == 3
    assert proposal_table(written).count("\n") == 7
    assert main(["muskingum", str(hms_file), "--flow", "R9=1"]) != 0
    assert main(["muskingum", str(hms_file), "--flow", "R1"]) != 0
    assert hms_file.read_bytes() == before


def test_a_reach_with_a_length_and_a_slope_only_gets_kirpich(tmp_path: Path) -> None:
    from wadi2d.engine.muskingum_proposals import _propose

    known = {"length_m": 9000.0, "slope": 0.012}
    proposal, words = _propose("R", known, 5.0, {}, None)
    assert proposal.basis == BASIS_KIRPICH
    assert proposal.k_hours == pytest.approx(kirpich_travel_minutes(9000.0, 0.012) / 60.0, abs=1e-4)
    assert proposal.x == DEFAULT_X and "a rough start only" in words
    faster, _words = _propose("R", known, 5.0, {}, 2.0)
    assert faster.basis == BASIS_VELOCITY and math.isclose(faster.k_hours, 0.8333)
    assert _propose("R", {}, 5.0, {}, None)[0] is None
