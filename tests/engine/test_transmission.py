"""Dry-bed transmission loss, through ``run_job``: volumes known by hand, its own line in the balance."""

from __future__ import annotations

import json
import threading
import time

import h5py
import numpy as np
import pytest

from tests.engine.conftest import X0, Y0, job, write_dem
from wadi2d.run import run_job

PIXEL, DX = 2.0, 4.0
NX, NY = 32, 16
AREA = NX * NY * DX * DX
RING = [(X0 - 1.0, Y0 + 1.0), (X0 + NX * DX + 1.0, Y0 + 1.0), (X0 + NX * DX + 1.0, Y0 - NY * DX - 1.0),
        (X0 - 1.0, Y0 - NY * DX - 1.0)]  # fmt: skip
MM_H = 1.0 / 1000.0 / 3600.0


def pond(tmp_path, level: float = 100.5, backend: str = "cpu", duration: float = 3600.0, **parts):
    """A flat closed box holding still water: nothing moves, so the loss is the only change."""
    dem = write_dem(tmp_path / "flat.tif", np.full((NY * 2, NX * 2), 100.0), PIXEL)
    return job(
        dem, NX, NY, DX,
        initial_levels=[{"coordinates": RING, "level": level}],
        run={"duration_s": duration, "backend": backend, "source_every_s": 30.0},
        **parts,
    )  # fmt: skip


def test_off_takes_nothing(tmp_path):
    run = run_job(pond(tmp_path, transmission={"rate_mm_h": 100.0}), tmp_path / "run")
    assert run.exit_code == 0, run.message
    assert run.balance.transmission == 0.0
    assert run.balance.storage == pytest.approx(0.5 * AREA, rel=1e-6)
    assert "transmission_m3" not in run.done["balance"]


def test_a_known_rate_over_a_wet_bed_takes_rate_times_time_times_area(tmp_path):
    rate = 36.0
    run = run_job(pond(tmp_path, transmission={"enabled": True, "rate_mm_h": rate}), tmp_path / "run")
    assert run.exit_code == 0, run.message
    by_hand = rate / 1000.0 * AREA  # 36 mm in the hour, everywhere
    b = run.balance
    assert b.transmission == pytest.approx(by_hand, rel=1e-5)
    assert b.storage == pytest.approx(0.5 * AREA - by_hand, rel=1e-5)
    assert abs(b.relative) < 1e-6
    assert run.done["balance"]["transmission_m3"] == b.transmission


def test_the_bed_takes_no_more_than_its_depth(tmp_path):
    run = run_job(
        pond(tmp_path, transmission={"enabled": True, "rate_mm_h": 36.0, "max_depth_mm": 10.0}),
        tmp_path / "run",
    )
    assert run.exit_code == 0, run.message
    assert run.balance.transmission == pytest.approx(0.010 * AREA, rel=1e-5)
    assert abs(run.balance.relative) < 1e-6


def test_it_never_takes_more_water_than_there_is(tmp_path):
    """2 m of loss an hour on 20 mm of water: a cell keeps losing half of what it holds, and the books still close."""
    cfg = pond(
        tmp_path, level=100.02, transmission={"enabled": True, "rate_mm_h": 2000.0, "min_depth_m": 0.0}
    )
    run = run_job(cfg, tmp_path / "run")
    assert run.exit_code == 0, run.message
    b = run.balance
    assert 0.0 < b.transmission < 0.02 * AREA
    assert b.storage > 0.0
    assert abs(b.relative) < 1e-6


def test_thin_water_below_the_channel_depth_keeps_its_water(tmp_path):
    cfg = pond(tmp_path, level=100.05, transmission={"enabled": True, "rate_mm_h": 36.0, "min_depth_m": 0.1})
    run = run_job(cfg, tmp_path / "run")
    assert run.exit_code == 0, run.message
    assert run.balance.transmission == 0.0


def test_only_the_area_given_loses_water(tmp_path):
    half = [(X0 - 1.0, Y0 + 1.0), (X0 + NX * DX / 2.0, Y0 + 1.0), (X0 + NX * DX / 2.0, Y0 - NY * DX - 1.0),
            (X0 - 1.0, Y0 - NY * DX - 1.0), (X0 - 1.0, Y0 + 1.0)]  # fmt: skip
    path = tmp_path / "bed.geojson"
    feature = {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [half]}}
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [feature]}), encoding="utf-8")
    cfg = pond(tmp_path, transmission={"enabled": True, "rate_mm_h": 36.0, "area": str(path)})
    run = run_job(cfg, tmp_path / "run")
    assert run.exit_code == 0, run.message
    assert run.balance.transmission == pytest.approx(0.036 * AREA / 2.0, rel=1e-5)


# a dry channel with water running down it


CH_NX, CH_NY, LENGTH = 128, 16, 512.0
BED_W = 8.0
"""Two cells of 4 m: the vertical walls lie on cell edges, so a channel cell is all bed and a bank cell none."""
Q_IN = 2.0


def channel(tmp_path) -> np.ndarray:
    """A plane falling east at 0.5 %, a rectangular cut 1 m deep and 8 m wide along its middle."""
    x = (np.arange(CH_NX * 2) + 0.5) * PIXEL
    z = np.tile(100.0 - 0.005 * x, (CH_NY * 2, 1))
    middle = CH_NY  # pixel rows
    z[middle - 2 : middle + 2, :] -= 1.0
    return write_dem(tmp_path / "channel.tif", z, PIXEL)


def channel_job(tmp_path, backend="cpu", **parts):
    mid = Y0 - CH_NY * DX / 2.0
    return job(
        channel(tmp_path), CH_NX, CH_NY, DX,
        terrain={"manning": 0.03},
        hydrology={
            "inflows": [{"name": "Head", "x": X0 + 6.0, "y": mid, "times_s": [0.0, 300.0, 1.0e5],
                         "flows": [0.0, Q_IN, Q_IN]}],
            "inject_radius": 3.0,
        },
        boundaries=[{"kind": "free", "coordinates": [(X0 + LENGTH - 2.0, Y0), (X0 + LENGTH - 2.0, Y0 - CH_NY * DX)]}],
        outputs={"lines": [{"name": "End", "coordinates": [(X0 + 480.0, Y0), (X0 + 480.0, Y0 - CH_NY * DX)]}],
                 "series_every_s": 30.0},
        run={"duration_s": 4800.0, "backend": backend, "source_every_s": 30.0},
        **parts,
    )  # fmt: skip


def steady_end(out) -> float:
    with h5py.File(out / "results.h5", "r") as f:
        q = np.abs(f["series/lines/End/discharge_m3s"][()])
        t = f["series/lines/End/t_s"][()]
    return float(q[t > 3600.0].mean())


def test_a_dry_channel_loses_rate_times_its_wetted_bed(tmp_path):
    """Steady flow: what reaches the end is what came in less the rate over the wetted bed above it, by hand."""
    rate = 720.0  # mm/h: 2e-4 m/s, so 0.77 m3/s over the 3,840 m2 of bed above the section
    plain = run_job(channel_job(tmp_path), tmp_path / "plain")
    assert plain.exit_code == 0, plain.message
    lost = run_job(
        channel_job(tmp_path, transmission={"enabled": True, "rate_mm_h": rate, "min_depth_m": 0.02}),
        tmp_path / "lost",
    )
    assert lost.exit_code == 0, lost.message
    bed_above = BED_W * (480.0 - 4.0)  # the head cell of the inflow loses too; the section sits on a face
    by_hand = rate * MM_H * bed_above
    taken = steady_end(tmp_path / "plain") - steady_end(tmp_path / "lost")
    assert steady_end(tmp_path / "plain") == pytest.approx(Q_IN, rel=0.01)
    assert taken == pytest.approx(by_hand, rel=0.03)
    assert abs(lost.balance.relative) < 1e-5


def test_a_stop_and_a_resume_keep_what_the_beds_took(tmp_path):
    cfg = pond(
        tmp_path, duration=3600.0, transmission={"enabled": True, "rate_mm_h": 36.0, "max_depth_mm": 20.0}
    )
    out = tmp_path / "run"

    def stop_soon() -> None:
        while not (out / "results.h5").exists():
            time.sleep(0.02)
        time.sleep(0.3)
        (out / "stop").touch()

    thread = threading.Thread(target=stop_soon, daemon=True)
    thread.start()
    assert run_job(cfg, out).exit_code == 6
    thread.join()
    done = run_job(cfg, out, resume=True)
    assert done.exit_code == 0, done.message
    # the cap holds across the stop: a bed that forgot would take the 20 mm again
    assert done.balance.transmission == pytest.approx(0.020 * AREA, rel=1e-4)
    assert abs(done.balance.relative) < 1e-5


@pytest.mark.gpu
def test_the_gpu_takes_the_same(tmp_path):
    run = run_job(
        pond(tmp_path, backend="gpu", transmission={"enabled": True, "rate_mm_h": 36.0}), tmp_path / "g"
    )
    assert run.exit_code == 0, run.message
    assert run.balance.transmission == pytest.approx(0.036 * AREA, rel=1e-5)
