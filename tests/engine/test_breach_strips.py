"""A dam breach on the aligned mesh (W69): the dam's faces on a corridor rebuilt from their pixels, mixed with the
squares, the same trapezoid, the books, the peak against the squares; and an embankment's breach keeps the job's other
edits."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from tests.engine.conftest import X0, Y0, job
from tests.engine.test_breach import (
    BED_AT_DAM,
    CREST_X,
    CREST_Z,
    DX,
    MID,
    NX,
    NY,
    PIXEL,
    POOL_Z,
    breach,
    dem,  # noqa: F401
    ground,
    series,
)
from wadi2d.breach.control import build_breaches
from wadi2d.breach.faces import read_back
from wadi2d.breach.shape import opened_area, opening
from wadi2d.breach.strip import read_back as strip_read_back
from wadi2d.run import prepare_grid, run_job
from wadi2d.solver.model import Model
from wadi2d.strips.hybrid import make_hybrid

BELOW = [(X0 + 300.0, Y0), (X0 + 300.0, Y0 - NY * DX)]


def corridor(half_rows: int) -> dict:
    """A corridor along the valley axis (y = 100 m, mid-row), its rows on lattice lines, a station face on the dam."""
    offsets = [4.0 + 8.0 * k for k in range(half_rows)]
    return {
        "enabled": True,
        "corridors": [{
            "name": "valley", "centre": [(X0 + 56.0, Y0 - MID), (X0 + 344.0, Y0 - MID)],
            "offsets": sorted([-o for o in offsets] + offsets),
        }],
    }  # fmt: skip


def pool_job(dem: Path, breaches=(), duration=900.0, strips=None, objects=None, **parts):  # noqa: F811
    across = [(X0 + CREST_X, Y0), (X0 + CREST_X, Y0 - NY * DX)]
    pool = [(X0, Y0), (X0 + CREST_X, Y0), (X0 + CREST_X, Y0 - NY * DX), (X0, Y0 - NY * DX)]
    extra = {} if strips is None else {"strips": strips}
    return job(
        dem, NX, NY, DX,
        terrain={"objects": objects or [{"kind": "crest_line", "name": "Dam", "coordinates": across, "z_constant": CREST_Z}]},
        boundaries=[{"kind": "free", "coordinates": [(X0 + NX * DX - 4.0, Y0), (X0 + NX * DX - 4.0, Y0 - NY * DX)]}],
        initial_levels=[{"coordinates": pool, "level": POOL_Z}],
        breaches=list(breaches),
        outputs={"lines": [{"name": "Below", "coordinates": BELOW}]},
        run={"duration_s": duration, "backend": "cpu"},
        **extra, **parts,
    )  # fmt: skip


def _model(cfg, tmp_path):
    tables, crs = prepare_grid(cfg, tmp_path / "cache")
    model = Model(tables, cfg.numerics, "cpu")
    hybrid = make_hybrid(model, tables.strip.mesh, cfg.strips.substeps) if getattr(tables, "strip", None) is not None else None
    return tables, crs, model, hybrid


def _opened(tab, ef, e, rows) -> float:
    r = np.sqrt(np.clip(e / ef, 0.0, 1.0)) * (rows - 1)
    return float(np.interp(r, np.arange(rows), tab[:, 0]))


@pytest.mark.parametrize(("half_rows", "width"), [(3, 16.0), (1, 32.0)])
def test_the_final_faces_on_the_corridor_and_the_squares_hold_the_trapezoid(dem, tmp_path, half_rows, width) -> None:  # noqa: F811
    """Five rows (40 m, 56 m with the gap triangles) and a 16 m breach: the whole trapezoid on strip faces; one row
    (24 m with the triangles) and a 32 m breach: a mixed dam, the middle on the strip, the rest on the squares."""
    cfg = pool_job(dem, [breach(station_m=MID, bottom_width_m=width)], strips=corridor(half_rows))
    tables, _crs, model, hybrid = _model(cfg, tmp_path)
    run = build_breaches(cfg, tables, model, None, _crs).runs[0]
    assert run.strip is not None and run.faces is not None, "the dam lies on both meshes"
    assert run.on_strip == (True, True), "the centre face is a strip face between two strip cells"
    rows = cfg.tables.rows
    before_s, before_q = strip_read_back(hybrid, run.strip, rows), read_back(model.backend, run.faces, rows)
    run.started = 0.0
    run.update(run.geo.time)
    after_s, after_q = strip_read_back(hybrid, run.strip, rows), read_back(model.backend, run.faces, rows)
    cut_s = np.nonzero(after_s.cw != before_s.cw)[0]
    cut_q = np.nonzero(after_q.cw != before_q.cw)[0]
    assert cut_s.size > 0 and np.all(after_s.cw[cut_s] == pytest.approx(1.44))
    assert (cut_q.size > 0) == (half_rows == 1), "the squares open only where the trapezoid reaches past the strip"
    zf_s = after_s.fr + run.strip.zmin_r
    zf_q = after_q.fr + run.faces.zmin_r
    area = sum(_opened(after_s.ftab[m], after_s.ef[m], CREST_Z - zf_s[m], rows) for m in cut_s)
    area += sum(_opened(after_q.ftab[m], after_q.ef[m], CREST_Z - zf_q[m], rows) for m in cut_q)
    s = np.linspace(0.0, NY * DX, 20001)
    exact = opened_area(run.geo, opening(run.geo, 1.0, "overtopping", None, False), CREST_Z, ground(CREST_X, s), s)
    assert area == pytest.approx(exact, rel=0.03)
    assert zf_s[cut_s].min() == pytest.approx(BED_AT_DAM, abs=PIXEL * 0.2 + 1e-6)
    keep = after_s.cw == before_s.cw
    np.testing.assert_array_equal(after_s.ftab[keep], before_s.ftab[keep])


def test_a_breach_on_the_corridor_closes_the_books_and_peaks_as_on_the_squares(dem, tmp_path) -> None:  # noqa: F811
    b = [breach(station_m=MID, bottom_width_m=32.0)]
    square = run_job(pool_job(dem, b), tmp_path / "square")
    aligned = run_job(pool_job(dem, b, strips=corridor(3)), tmp_path / "aligned")
    mixed = run_job(pool_job(dem, b, strips=corridor(1)), tmp_path / "mixed")
    # the centre generator with the dam as its one hard line: 4-sided cells either side of the crest (W46)
    centres = run_job(pool_job(dem, b, strips={"enabled": True, "generator": "centres"}), tmp_path / "centres")
    peaks = {}
    for name, s in (("square", square), ("aligned", aligned), ("mixed", mixed), ("centres", centres)):
        assert s.exit_code == 0, s.message
        assert abs(s.balance.relative) < 1e-6, (name, s.balance)
        rows = series(tmp_path / name, "breach_Dam.csv")
        assert rows[0, 0] == pytest.approx(60.0, abs=1e-9)
        assert rows[rows[:, 1] >= 1.0 - 1e-12][0, 0] == pytest.approx(360.0, abs=1e-9)
        line = series(tmp_path / name, "line_Below.csv")
        peaks[name] = float(np.abs(line[:, 1]).max())
    print("W69 peaks", peaks, "storage0", square.balance.storage0, aligned.balance.storage0)
    assert peaks["aligned"] == pytest.approx(peaks["square"], rel=0.05)
    assert peaks["mixed"] == pytest.approx(peaks["square"], rel=0.05)
    assert peaks["centres"] == pytest.approx(peaks["square"], rel=0.05)


@pytest.mark.gpu
def test_the_breach_on_the_corridor_on_the_gpu_reads_the_cpu_peak(dem, tmp_path) -> None:  # noqa: F811
    b = [breach(station_m=MID, bottom_width_m=32.0)]
    cpu = run_job(pool_job(dem, b, strips=corridor(3)), tmp_path / "cpu")
    cfg = pool_job(dem, b, strips=corridor(3))
    gpu = run_job(cfg.model_copy(update={"run": cfg.run.model_copy(update={"backend": "gpu"})}), tmp_path / "gpu")
    assert gpu.exit_code == 0 and gpu.backend == "gpu", gpu.message
    assert abs(gpu.balance.relative) < 1e-6
    peak = {k: float(np.abs(series(tmp_path / k, "line_Below.csv")[:, 1]).max()) for k in ("cpu", "gpu")}
    assert peak["gpu"] == pytest.approx(peak["cpu"], rel=1e-3)


def test_a_breach_never_triggered_on_the_corridor_changes_nothing(dem, tmp_path) -> None:  # noqa: F811
    a = run_job(pool_job(dem, duration=300.0, strips=corridor(3)), tmp_path / "a")
    b = run_job(
        pool_job(dem, [breach(trigger="level", trigger_level=CREST_Z + 5.0)], duration=300.0, strips=corridor(3)),
        tmp_path / "b",
    )
    assert a.exit_code == b.exit_code == 0
    assert a.balance.storage == b.balance.storage
    np.testing.assert_array_equal(series(tmp_path / "a", "line_Below.csv"), series(tmp_path / "b", "line_Below.csv"))


def test_a_pipe_between_strip_cells_flows_then_collapses_and_closes_the_books(dem, tmp_path) -> None:  # noqa: F811
    out = tmp_path / "pipe"
    b = breach(mode="piping", piping_z=100.0, formation_time_s=600.0, trigger="level", trigger_level=102.0, station_m=MID)
    s = run_job(pool_job(dem, [b], duration=1200.0, strips=corridor(3)), out)
    assert s.exit_code == 0, s.message
    rows = series(out, "breach_Dam.csv")
    piping = rows[np.isfinite(rows[:, 4])]
    assert piping[1:, 7].max() > 0.0 and (~np.isfinite(rows[:, 4])).any()
    assert abs(s.balance.relative) < 1e-6


def test_an_embankment_breach_keeps_a_burn_beside_it(dem, tmp_path) -> None:  # noqa: F811
    """W63 cut an embankment's breach down to the raw DEM, undoing a channel burnt under it; the ground without the dam
    now keeps the job's other edits."""
    across = [(X0 + CREST_X, Y0), (X0 + CREST_X, Y0 - NY * DX)]
    burn = [(X0 + 150.0, Y0 - MID), (X0 + 260.0, Y0 - MID)]
    objects = [
        {"kind": "embankment", "name": "Dam", "coordinates": across, "z_constant": CREST_Z, "section": {"width": 4.0}},
        {"kind": "burn_line", "name": "cut", "coordinates": burn, "width": 8.0, "depth": 1.0},
    ]
    cfg = pool_job(dem, [breach(station_m=MID)], objects=objects)
    tables, crs, model, _h = _model(cfg, tmp_path)
    run = build_breaches(cfg, tables, model, None, crs).runs[0]
    # the lowest pixels stand 1 m off the axis, 0.2 m up the side; the burn takes 1 m off them (W63 read 98.2 m here)
    assert run.faces.free.min() == pytest.approx(BED_AT_DAM + 0.2 - 1.0, abs=0.05), "the burn stands under the breach"
