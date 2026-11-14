"""Dam breach on the 2D grid (W63): the trapezoid on the faces, the progression, the triggers, the pipe, the books."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from tests.engine.conftest import X0, Y0, job, write_dem
from wadi2d.breach.control import build_breaches
from wadi2d.breach.faces import read_back
from wadi2d.breach.shape import Geometry, estimate, final_geometry, opened_area, opening, progress
from wadi2d.config.schema import Breach, BreachEstimator
from wadi2d.run import job_hash, prepare_grid, run_job
from wadi2d.solver.model import Model

PIXEL, DX = 2.0, 8.0
NX, NY = 50, 25
FALL, SIDE = 0.01, 0.2
CREST_X, CREST_Z, POOL_Z = 200.0, 103.0, 102.5
BED_AT_DAM = 100.0 - FALL * CREST_X
MID = NY * DX / 2.0


def ground(x, y):
    return 100.0 - FALL * x + SIDE * np.abs(y - MID)


@pytest.fixture
def dem(tmp_path: Path) -> Path:
    x = (np.arange(NX * DX / PIXEL) + 0.5) * PIXEL
    y = (np.arange(NY * DX / PIXEL) + 0.5) * PIXEL
    return write_dem(tmp_path / "valley.tif", ground(x[None, :], y[:, None]), PIXEL)


def breach(**over) -> dict:
    data = {
        "dam": "Dam", "bottom_z": BED_AT_DAM, "bottom_width_m": 16.0, "left_slope": 1.0, "right_slope": 1.0,
        "formation_time_s": 300.0, "trigger": "time", "trigger_time_s": 60.0, "update_s": 2.0,
    }  # fmt: skip
    data.update(over)
    return data


def dam_job(dem: Path, breaches=(), duration=900.0, **parts):
    across = [(X0 + CREST_X, Y0), (X0 + CREST_X, Y0 - NY * DX)]
    return job(
        dem, NX, NY, DX,
        terrain={"objects": [{"kind": "crest_line", "name": "Dam", "coordinates": across, "z_constant": CREST_Z}]},
        boundaries=[{"kind": "free", "coordinates": [(X0 + NX * DX - 4.0, Y0), (X0 + NX * DX - 4.0, Y0 - NY * DX)]}],
        dam_levels=[{"name": "Dam", "start": POOL_Z}],
        breaches=list(breaches),
        run={"duration_s": duration},
        **parts,
    )  # fmt: skip


def series(out: Path, name: str) -> np.ndarray:
    return np.loadtxt(out / "series" / name, delimiter=",", skiprows=1, ndmin=2)


# --- the shape, without a grid


def test_a_breach_needs_its_geometry_or_an_estimator_and_its_trigger() -> None:
    with pytest.raises(ValidationError, match="bottom_width_m"):
        Breach(dam="Dam", bottom_z=98.0, trigger="time", trigger_time_s=0.0)
    with pytest.raises(ValidationError, match="trigger_level"):
        Breach(**breach(trigger="level"))
    with pytest.raises(ValidationError, match="piping_z"):
        Breach(**breach(mode="piping"))
    est = BreachEstimator(method="froehlich_2008", pool_volume_m3=1e6)
    assert (
        Breach(dam="Dam", bottom_z=98.0, trigger="time", trigger_time_s=0.0, estimator=est).estimator == est
    )


def test_froehlich_2008_by_hand() -> None:
    # B_ave = 0.27 x 1.3 x (2e6)^0.32 x 10^0.04, t_f = 63.2 (2e6 / (g 100))^0.5 s, slope 1 (TD-39, p. 17)
    e = estimate(BreachEstimator(method="froehlich_2008", pool_volume_m3=2e6), "overtopping", 10.0)
    bave = 0.27 * 1.3 * 2e6**0.32 * 10.0**0.04
    assert e.width == pytest.approx(bave - 10.0)
    assert e.time == pytest.approx(63.2 * math.sqrt(2e6 / (9.80665 * 100.0)), rel=1e-3)
    vt = estimate(BreachEstimator(method="von_thun_gillette", pool_volume_m3=2e6), "overtopping", 10.0)
    assert vt.width == pytest.approx(2.5 * 10.0 + 18.3 - 10.0) and vt.time == pytest.approx(0.15 * 3600.0)
    mac = estimate(
        BreachEstimator(method="macdonald_langridge_monopolis", pool_volume_m3=2e6), "overtopping", 10.0
    )
    assert mac.slope == 0.5 and mac.time == pytest.approx(0.0179 * (0.0261 * 2e7**0.769) ** 0.364 * 3600.0)


# West, Morris and Hassan (2018), A guide to breach prediction, HR Wallingford HRPP770, Tables 2 and 3: Xu and Zhang
# (2009) on three failures, B_ave and t_f between low and high erodibility, to the table's two decimals (W76).
GUIDE_CASES = [
    # name, V_w m3, h_w, h_b, h_d m, mode, (B_ave low, B_ave high) m, (t_f low, t_f high) h
    ("Testalinden", 0.02e6, 2.1, 2.1, 2.1, "overtopping", (6.49, 12.50), (1.37, 0.25)),
    ("Big Bay Lake", 17.5e6, 13.6, 14.0, 14.0, "piping", (33.65, 64.78), (7.73, 1.43)),
    ("Delhi", 12.2e6, 11.2, 11.0, 11.0, "overtopping", (47.92, 92.25), (7.24, 1.34)),
]
TABLE_HALF_DIGIT = 0.0051


@pytest.mark.parametrize(("name", "vw", "hw", "hb", "hd", "mode", "widths", "hours"), GUIDE_CASES)
def test_xu_zhang_2009_reproduces_the_guides_worked_examples(name, vw, hw, hb, hd, mode, widths, hours) -> None:
    for erodibility, width, time in zip(("low", "high"), widths, hours, strict=True):
        est = BreachEstimator(
            method="xu_zhang_2009", pool_volume_m3=vw, water_depth_m=hw, dam_height_m=hd, erodibility_class=erodibility
        )
        e = estimate(est, mode, hb, 0.0)  # a vertical side: the bottom width is B_ave
        assert e.width == pytest.approx(width, abs=TABLE_HALF_DIGIT), name
        assert e.time / 3600.0 == pytest.approx(time, abs=TABLE_HALF_DIGIT), name


def test_froehlich_2016_and_xu_zhang_by_hand_and_their_refusal() -> None:
    # Froehlich (2016a): B_ave = 0.23 x 1.5 x V^(1/3), slope 1, t_f = 60 (V / (g h^2))^0.5 s; piping 1.0 and 0.6
    e = estimate(BreachEstimator(method="froehlich_2016", pool_volume_m3=2e6), "overtopping", 10.0)
    bave = 0.23 * 1.5 * 2e6 ** (1.0 / 3.0)
    assert e.slope == 1.0 and e.width == pytest.approx(bave - 10.0)
    assert e.time == pytest.approx(60.0 * math.sqrt(2e6 / (9.80665 * 100.0)), rel=1e-3)
    p = estimate(BreachEstimator(method="froehlich_2016", pool_volume_m3=2e6), "piping", 10.0)
    assert p.slope == 0.6 and p.width == pytest.approx(0.23 * 2e6 ** (1.0 / 3.0) - 6.0)
    # Xu and Zhang, medium erodibility, piping: B_ave / h_b = 5.543 (V^(1/3) / h_w)^0.739 e^(-1.747 - 1.073)
    x = estimate(BreachEstimator(method="xu_zhang_2009", pool_volume_m3=2e6), "piping", 10.0, 0.5)
    shape = 2e6 ** (1.0 / 3.0) / 10.0
    assert x.width == pytest.approx(10.0 * 5.543 * shape**0.739 * math.exp(-2.820) - 5.0)
    assert x.time == pytest.approx(0.066 * (10.0 / 15.0) ** 0.654 * shape**1.246 * 3600.0)
    with pytest.raises(ValueError, match="no side slope"):
        estimate(BreachEstimator(method="xu_zhang_2009", pool_volume_m3=2e6), "piping", 10.0)
    xz = BreachEstimator(method="xu_zhang_2009", pool_volume_m3=2e6, erodibility_class="high")
    with pytest.raises(ValueError, match="no side slope"):
        final_geometry(Breach(dam="Dam", bottom_z=93.0, trigger="time", trigger_time_s=0.0, estimator=xz), 50.0, 103.0)
    geo, note = final_geometry(Breach(**breach(bottom_z=93.0, bottom_width_m=None, formation_time_s=None,
                                                left_slope=0.5, right_slope=1.5, estimator=xz)), 50.0, 103.0)
    high = estimate(xz, "overtopping", 10.0, 1.0)
    assert (geo.width, geo.left, geo.right, geo.time) == (high.width, 0.5, 1.5, high.time) and "Xu and Zhang" in note


def test_a_w63_estimator_keeps_its_hash(dem) -> None:
    est = {"method": "froehlich_2008", "pool_volume_m3": 1e6}
    old = dam_job(dem, [breach(estimator=est)])
    assert job_hash(old) == job_hash(dam_job(dem, [breach(estimator=est | {"erodibility_class": "medium"})]))
    assert job_hash(old) != job_hash(dam_job(dem, [breach(estimator=est | {"erodibility_class": "high"})]))


def test_progressions_and_the_pipe_grow_to_the_same_trapezoid() -> None:
    assert progress(0.5, "linear") == 0.5 and progress(0.5, "sine") == pytest.approx(0.5)
    assert progress(0.1, "sine") < 0.1 < progress(0.9, "sine") - 0.8
    geo = Geometry(100.0, 103.0, 98.0, 16.0, 1.0, 1.0, 300.0)
    top = opening(geo, 0.0, "overtopping", None, False)
    assert (top.bottom, top.width) == (103.0, 0.0)
    pipe = opening(geo, 0.25, "piping", 100.0, False)
    assert (pipe.bottom, pipe.roof, pipe.width) == (99.5, 100.5, 4.0)
    a, b = opening(geo, 1.0, "overtopping", None, False), opening(geo, 1.0, "piping", 100.0, True)
    assert (a.bottom, a.width, a.open) == (b.bottom, b.width, b.open) == (98.0, 16.0, True)


# --- on the grid


def test_an_old_job_keeps_its_hash(dem) -> None:
    plain = dam_job(dem)
    assert job_hash(plain) != job_hash(dam_job(dem, [breach()]))
    assert "breaches" not in job(dem, NX, NY, DX).model_fields_set


def test_the_final_faces_hold_the_trapezoid_cut_into_the_dam_and_not_the_valley(dem, tmp_path) -> None:
    cfg = dam_job(dem, [breach(station_m=MID)])
    tables, crs = prepare_grid(cfg, tmp_path / "cache")
    model = Model(tables, cfg.numerics, "cpu")
    runs = build_breaches(cfg, tables, model, None, crs)
    run = runs.runs[0]
    before = read_back(model.backend, run.faces, cfg.tables.rows)
    run.started = 0.0
    run.update(run.geo.time)
    assert run.formed == run.geo.time
    after = read_back(model.backend, run.faces, cfg.tables.rows)
    cut = np.nonzero(after.cw != before.cw)[0]
    assert cut.size > 0 and np.all(after.cw[cut] == pytest.approx(1.44))
    # the opened area under the crest, face by face, against the trapezoid on the ground sampled finely
    zf = after.fr + run.faces.zmin_r
    area = 0.0
    for m in cut:
        e = CREST_Z - zf[m]
        tab = after.ftab[m]
        top = after.ef[m]
        r = np.sqrt(np.clip(e / top, 0.0, 1.0)) * (cfg.tables.rows - 1)
        area += float(np.interp(r, np.arange(cfg.tables.rows), tab[:, 0]))
    s = np.linspace(0.0, NY * DX, 20001)
    exact = opened_area(
        run.geo, opening(run.geo, 1.0, "overtopping", None, False), CREST_Z, ground(CREST_X, s), s
    )
    assert area == pytest.approx(exact, rel=0.03)
    # the invert of the deepest face sits on the valley floor, the faces outside the trapezoid keep the crest
    assert zf[cut].min() == pytest.approx(BED_AT_DAM, abs=PIXEL * SIDE + 1e-6)
    np.testing.assert_array_equal(after.ftab[after.cw == before.cw], before.ftab[after.cw == before.cw])


def test_an_overtopping_breach_starts_on_time_closes_the_books_and_empties_the_pool(dem, tmp_path) -> None:
    out = tmp_path / "over"
    s = run_job(dam_job(dem, [breach(station_m=MID)]), out)
    assert s.exit_code == 0, s.message
    assert abs(s.balance.relative) < 1e-6
    rows = series(out, "breach_Dam.csv")
    assert rows[0, 0] == pytest.approx(60.0, abs=1e-9), "the breach starts on the trigger time"
    formed = rows[rows[:, 1] >= 1.0 - 1e-12]
    assert formed[0, 0] == pytest.approx(360.0, abs=1e-9), "and is formed one formation time later"
    assert formed[0, 2] == pytest.approx(BED_AT_DAM) and formed[0, 3] == pytest.approx(16.0)
    lost = s.balance.storage0 - s.balance.storage
    assert lost > 0.5 * s.balance.storage0, "most of the pool has left"
    assert s.balance.outflow == pytest.approx(lost, rel=1e-5)


def test_a_breach_never_triggered_changes_nothing(dem, tmp_path) -> None:
    point = {"lines": [{"name": "Below", "coordinates": [(X0 + 300.0, Y0), (X0 + 300.0, Y0 - NY * DX)]}]}
    a = run_job(dam_job(dem, duration=300.0, outputs=point), tmp_path / "a")
    b = run_job(
        dam_job(dem, [breach(trigger="level", trigger_level=CREST_Z + 5.0)], duration=300.0, outputs=point),
        tmp_path / "b",
    )
    assert a.exit_code == b.exit_code == 0
    assert a.balance.storage == b.balance.storage
    np.testing.assert_array_equal(
        series(tmp_path / "a", "line_Below.csv"), series(tmp_path / "b", "line_Below.csv")
    )


def test_a_level_held_for_a_duration_starts_the_breach_after_it(dem, tmp_path) -> None:
    out = tmp_path / "held"
    s = run_job(
        dam_job(
            dem,
            [breach(trigger="level_duration", trigger_level=102.0, trigger_duration_s=90.0)],
            duration=200.0,
        ),
        out,
    )
    assert s.exit_code == 0, s.message
    assert series(out, "breach_Dam.csv")[0, 0] == pytest.approx(90.0, abs=1e-9)


def test_a_pipe_flows_as_an_orifice_then_collapses_into_an_open_breach(dem, tmp_path) -> None:
    out = tmp_path / "pipe"
    b = breach(mode="piping", piping_z=100.0, formation_time_s=600.0, trigger="level", trigger_level=102.0)
    s = run_job(dam_job(dem, [b], duration=1500.0), out)
    assert s.exit_code == 0, s.message
    rows = series(out, "breach_Dam.csv")
    piping = rows[np.isfinite(rows[:, 4])]
    opened = rows[~np.isfinite(rows[:, 4])]
    assert piping.size and opened.size, "a pipe first, an open breach after"
    assert piping[:, 0].max() < opened[:, 0].min()
    assert piping[1:, 7].max() > 0.0, "the pipe carries water"
    flowing = piping[piping[:, 7] > 0.0]
    head = flowing[:, 5] - np.maximum(0.5 * (flowing[:, 2] + flowing[:, 4]), flowing[:, 6])
    q = 0.5 * flowing[:, 3] * (flowing[:, 4] - flowing[:, 2]) * np.sqrt(2.0 * 9.80665 * head)
    assert np.all(flowing[:, 7] <= q * (1 + 1e-5) + 2e-6), "never more than the orifice law (CSV to 1e-6)"
    collapse = opened[0]
    assert collapse[5] <= piping[-1, 4] + 0.05 or piping[-1, 4] >= CREST_Z - 1e-9, (
        "the roof falls with the pool at it"
    )
    assert abs(s.balance.relative) < 1e-6


def test_a_breach_on_an_unknown_dam_or_a_mesh_is_refused_in_words(dem, tmp_path) -> None:
    s = run_job(dam_job(dem, [breach(dam="Nowhere")]), tmp_path / "x")
    assert s.exit_code != 0 and "Nowhere" in s.message
    s = run_job(dam_job(dem, [breach()], numerics={"local_time_stepping": True}), tmp_path / "y")
    assert s.exit_code != 0 and "local time stepping" in s.message
