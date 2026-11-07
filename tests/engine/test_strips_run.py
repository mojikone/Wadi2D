"""A job with strips through ``run_job`` (W45, stage 7): a corridor along a rained plane, the books close, the line
across it reads what the same job reads without strips, and a job without strips keeps its hash."""

from __future__ import annotations

import json

import numpy as np
import pytest

from tests.engine.conftest import X0, Y0, job, tilted_dem  # noqa: F401
from wadi2d.run import job_hash, run_job

MID_Y = Y0 - 48.0
LINE = [(X0 + 100.0, Y0 - 16.0), (X0 + 100.0, Y0 - 80.0)]
"""Across the plane at x = 100 m, through the corridor and the tiles either side."""


def plane_job(dem, strips: dict | None):
    parts = dict(
        storm={"kind": "uniform", "depth_mm": 60.0, "duration_min": 20.0},
        boundaries=[{"kind": "free", "coordinates": [(X0 + 201.0, Y0 + 2.0), (X0 + 201.0, Y0 - 98.0)]}],
        outputs={"lines": [{"name": "across", "coordinates": LINE}], "series_every_s": 10.0},
        run={"duration_s": 1800.0, "backend": "cpu", "source_every_s": 10.0},
    )
    if strips is not None:
        parts["strips"] = strips
    return job(dem, 50, 24, 4.0, **parts)


def corridor(x_end: float = 160.0) -> dict:
    return {
        "enabled": True,
        "corridors": [
            {
                "name": "mid",
                "centre": [(X0 + 40.0, MID_Y), (X0 + x_end, MID_Y)],
                "offsets": [-12.0, -8.0, -4.0, 0.0, 4.0, 8.0, 12.0],
                # row 2 lies 4 m to the right of travel (eastward: south), so its line is at MID_Y - 4
                "snap": [{"row": 2, "coordinates": [(X0, MID_Y - 4.0), (X0 + 200.0, MID_Y - 4.0)]}],
            }
        ],
    }


def peak_and_volume(out) -> tuple[float, float]:
    rows = (out / "series" / "line_across.csv").read_text(encoding="utf-8").splitlines()[1:]
    t = np.array([float(r.split(",")[0]) for r in rows])
    q = np.array([float(r.split(",")[1]) for r in rows])
    return float(np.abs(q).max()), float(abs(np.trapezoid(q, t)))


def test_a_job_with_a_corridor_runs_on_the_cpu_and_its_books_close(tilted_dem, tmp_path) -> None:  # noqa: F811
    cfg = plane_job(tilted_dem, corridor())
    out = tmp_path / "strips"
    run = run_job(cfg, out)
    assert run.exit_code == 0, run.message
    assert run.backend == "cpu"
    events = [json.loads(s) for s in (out / "progress.jsonl").read_text(encoding="utf-8").splitlines()]
    (strips,) = [e for e in events if e.get("ev") == "strips"]
    assert strips["corridors"] == 1 and strips["cells"] == 6 * 30 and strips["triangles"] > 0 and strips["replaced"] > 0
    assert abs(run.balance.relative) < 1e-6
    assert run.balance.rain > 0.0


def test_a_corridor_ending_on_the_outflow_boundary_closes_the_books(tilted_dem, tmp_path) -> None:  # noqa: F811
    """The free boundary opens the cells at x = 200 to 204 m; a corridor to x = 196 m has them as its ghosts, and
    what it passes into them has left the model."""
    cfg = plane_job(tilted_dem, corridor(196.0))
    out = tmp_path / "outlet"
    run = run_job(cfg, out)
    assert run.exit_code == 0, run.message
    assert abs(run.balance.relative) < 1e-6, run.balance
    plain = run_job(plane_job(tilted_dem, None), tmp_path / "plain")
    assert run.balance.outflow == pytest.approx(plain.balance.outflow, rel=0.05)
    assert run.balance.outflow > 0.5 * run.balance.rain


def test_the_line_across_the_corridor_reads_what_the_tiles_alone_read(tilted_dem, tmp_path) -> None:  # noqa: F811
    with_strips = run_job(plane_job(tilted_dem, corridor()), tmp_path / "strips")
    without = run_job(plane_job(tilted_dem, None), tmp_path / "plain")
    assert with_strips.exit_code == 0 and without.exit_code == 0
    peak_s, volume_s = peak_and_volume(tmp_path / "strips")
    peak_p, volume_p = peak_and_volume(tmp_path / "plain")
    assert volume_s == pytest.approx(volume_p, rel=0.05)
    assert peak_s == pytest.approx(peak_p, rel=0.1)


def test_a_job_without_strips_keeps_the_hash_it_had(tilted_dem) -> None:  # noqa: F811
    cfg = plane_job(tilted_dem, None)
    data = cfg.model_dump(mode="json")
    assert "strips" in data and not data["strips"]["enabled"]
    assert job_hash(cfg) == job_hash(cfg.model_copy(update={"strips": cfg.strips.model_copy(update={"smooth": 9})}))


@pytest.mark.gpu
def test_the_same_job_on_the_gpu_closes_its_books_and_reads_the_cpu_line(tilted_dem, tmp_path) -> None:  # noqa: F811
    cfg = plane_job(tilted_dem, corridor())
    on_gpu = cfg.model_copy(update={"run": cfg.run.model_copy(update={"backend": "gpu"})})
    gpu = run_job(on_gpu, tmp_path / "gpu")
    assert gpu.exit_code == 0, gpu.message
    assert gpu.backend == "gpu"
    assert abs(gpu.balance.relative) < 1e-6
    cpu = run_job(cfg, tmp_path / "cpu")
    peak_g, volume_g = peak_and_volume(tmp_path / "gpu")
    peak_c, volume_c = peak_and_volume(tmp_path / "cpu")
    assert cpu.exit_code == 0
    assert volume_g == pytest.approx(volume_c, rel=1e-3)
    assert peak_g == pytest.approx(peak_c, rel=1e-2)
