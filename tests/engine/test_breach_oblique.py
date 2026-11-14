"""A dam breach where the valley, its corridor and the dam run at an angle to the grid (W71): the squares carry the dam
as a staircase of faces, the corridor and the centre mesh on faces along the dam's own line; the peak below the dam
and the books on all three."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
import shapely

from tests.engine.conftest import X0, Y0, job, write_dem
from tests.engine.test_breach import breach, series
from wadi2d.run import run_job

PIXEL, DX = 2.0, 8.0
W = H = 480.0
FALL, SIDE = 0.03, 0.2
BED, CREST_Z, POOL_Z = 98.0, 103.0, 102.5
POOL_M3 = (POOL_Z - BED) ** 3 / (3.0 * FALL * SIDE)
"""The pool by hand: 150 m long, wholly inside the box at every angle, so the runs differ only by the angle."""
DAM = (240.0, 240.0)
"""The dam's centre on the valley floor, (east, south) of the north-west corner, m."""
HALF = 100.0


def frame(angle: float):
    a = math.radians(angle)
    d, n = np.array([math.cos(a), math.sin(a)]), np.array([-math.sin(a), math.cos(a)])
    return d, n


def ground(angle: float, u, v):
    d, n = frame(angle)
    s = (u - DAM[0]) * d[0] + (v - DAM[1]) * d[1]
    across = (u - DAM[0]) * n[0] + (v - DAM[1]) * n[1]
    return BED - FALL * s + SIDE * np.abs(across)


def xy(u: float, v: float) -> tuple[float, float]:
    return (X0 + float(u), Y0 - float(v))


def across_at(angle: float, s: float) -> list[tuple[float, float]]:
    d, n = frame(angle)
    c = np.array(DAM) + s * d
    return [xy(*(c - HALF * n)), xy(*(c + HALF * n))]


def oblique_job(dem: Path, angle: float, strips=None, breaches=(), duration=900.0):
    d, _n = frame(angle)
    box = shapely.box(0.0, 0.0, W, H)
    big = 1e4
    upstream = shapely.Polygon(
        [DAM + big * np.array(frame(angle)[1]), DAM + big * np.array(frame(angle)[1]) - big * d,
         DAM - big * np.array(frame(angle)[1]) - big * d, DAM - big * np.array(frame(angle)[1])]
    )  # fmt: skip
    pool = [xy(u, v) for u, v in box.intersection(upstream).exterior.coords[:-1]]
    edge = [xy(W - 4.0, 4.0), xy(W - 4.0, H - 4.0), xy(4.0, H - 4.0)]
    extra = {} if strips is None else {"strips": strips}
    return job(
        dem, int(W / DX), int(H / DX), DX,
        terrain={"objects": [{"kind": "crest_line", "name": "Dam", "coordinates": across_at(angle, 0.0), "z_constant": CREST_Z}]},
        boundaries=[{"kind": "free", "coordinates": edge}],
        initial_levels=[{"coordinates": pool, "level": POOL_Z}],
        breaches=list(breaches),
        outputs={"lines": [{"name": "Below", "coordinates": across_at(angle, 100.0)}]},
        run={"duration_s": duration, "backend": "cpu"},
        **extra,
    )  # fmt: skip


def corridor(angle: float) -> dict:
    """Five rows of 8 m along the valley's axis, a station face on the dam (stations every 8 m from 200 m above it)."""
    d, _n = frame(angle)
    start, end = np.array(DAM) - 200.0 * d, np.array(DAM) + 200.0 * d
    return {
        "enabled": True,
        "corridors": [{"name": "valley", "centre": [xy(*start), xy(*end)], "offsets": [-20.0, -12.0, -4.0, 4.0, 12.0, 20.0]}],
    }


def _run(tmp_path: Path, angle: float, name: str, strips) -> tuple[float, float]:
    u = (np.arange(W / PIXEL) + 0.5) * PIXEL
    v = (np.arange(H / PIXEL) + 0.5) * PIXEL
    dem = write_dem(tmp_path / f"valley{angle:g}.tif", ground(angle, u[None, :], v[:, None]), PIXEL)
    b = [breach(station_m=HALF, bottom_z=BED, bottom_width_m=32.0)]
    out = tmp_path / f"{name}{angle:g}"
    s = run_job(oblique_job(dem, angle, strips, b), out)
    assert s.exit_code == 0, (name, s.message)
    assert abs(s.balance.relative) < 1e-6, (name, s.balance)
    rows = series(out, "breach_Dam.csv")
    assert rows[0, 0] == pytest.approx(60.0, abs=1e-9)
    assert rows[rows[:, 1] >= 1.0 - 1e-12][0, 0] == pytest.approx(360.0, abs=1e-9)
    return float(np.abs(series(out, "line_Below.csv")[:, 1]).max()), s.balance.storage0


@pytest.mark.parametrize("angle", [30.0, 45.0])
def test_a_breach_on_oblique_aligned_faces_peaks_as_on_the_squares_along_the_grid(tmp_path, angle) -> None:
    """The yardstick is the same valley along the grid on the squares (W69: the aligned cells read it within 1 %);
    the squares at the angle carry the dam and the valley as staircases."""
    peaks, stored = {}, {}
    peaks["square0"], stored["square0"] = _run(tmp_path, 0.0, "square", None)
    meshes = {"square": None, "corridor": corridor(angle), "centres": {"enabled": True, "generator": "centres"}}
    for name, strips in meshes.items():
        peaks[name], stored[name] = _run(tmp_path, angle, name, strips)
    print("W71 oblique", angle, "peaks", peaks, "storage0", stored, "by hand", POOL_M3)
    assert stored["square0"] == pytest.approx(POOL_M3, rel=0.02)
    assert peaks["corridor"] == pytest.approx(peaks["square0"], rel=0.05)
    assert peaks["centres"] == pytest.approx(peaks["square0"], rel=0.05)
