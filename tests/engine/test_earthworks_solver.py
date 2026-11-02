"""Shaped terrain objects in the running solver, through the whole pipeline on the CPU."""

from __future__ import annotations

import math

import h5py
import numpy as np
import pytest
from scipy.optimize import brentq

from tests.engine.conftest import X0, Y0, job, write_dem
from wadi2d.config.constants import CRITICAL_WEIR_COEFF
from wadi2d.run import prepare_grid, run_job

PIXEL, DX = 1.5, 6.0
N, S = 0.03, 0.002
BOTTOM, SIDE = 18.0, 2.0
"""Bottom 3 cells wide, the narrowest the normal-depth requirement covers."""
FLOW = 40.0
DEPTH_BELOW_GROUND = 3.0
TOP = 100.0
DYKE_TOP = 3.0
"""Top of the dykes above the bed."""


def normal_depth(q: float, b: float, side: float, n: float, slope: float) -> float:
    def excess(y: float) -> float:
        area = (b + side * y) * y
        wetted = b + 2.0 * y * math.sqrt(1.0 + side * side)
        return area * (area / wetted) ** (2.0 / 3.0) * math.sqrt(slope) / n - q

    return float(brentq(excess, 1e-3, 20.0))


def channel_case(
    tmp_path,
    angle: float,
    manning: float = N,
    lining: float | None = None,
    depth=DEPTH_BELOW_GROUND,
    dyke=False,
):
    """A straight trapezoid in a plane falling along it, ``angle`` degrees south of east; held to steady flow."""
    size = 864.0 if angle else 1080.0
    height = 864.0 if angle else 96.0
    ux, uy = math.cos(math.radians(angle)), -math.sin(math.radians(angle))
    nx, ny = round(size / PIXEL), round(height / PIXEL)
    px = (np.arange(nx) + 0.5) * PIXEL
    py = -(np.arange(ny) + 0.5) * PIXEL
    start = np.array([0.0, -height / 2.0 if not angle else 0.0])
    along = (px[None, :] - start[0]) * ux + (py[:, None] - start[1]) * uy
    ground = TOP - S * along
    dem = write_dem(tmp_path / f"plane{angle:.0f}.tif", ground, PIXEL)
    length = size / max(ux, 1e-9)
    bed0 = TOP - depth

    def point(s: float, offset: float = 0.0) -> tuple[float, float]:
        return (X0 + start[0] + s * ux - offset * uy, Y0 + start[1] + s * uy + offset * ux)

    obj = {
        "kind": "channel",
        "coordinates": [point(0.0), point(length)],
        "z": [bed0, bed0 - S * length],
        "section": {"width": BOTTOM, "left_slope": SIDE, "right_slope": SIDE},
    }
    if lining is not None:
        obj["lining_n"] = lining
    if dyke:
        top = [bed0 + DYKE_TOP, bed0 - S * length + DYKE_TOP]
        rows = [
            {"station": 0.0, "bed_z": bed0, "crest_z": top[0]},
            {"station": length, "bed_z": bed0 - S * length, "crest_z": top[1]},
        ]
        obj = {
            "kind": "channel_dyke",
            "coordinates": obj["coordinates"],
            "section": {**obj["section"], "rows": rows},
        }
    stop = length - 60.0
    stations = (0.40 * length, 0.55 * length, 0.70 * length)
    # the level the solver is held to is the answer only at the end: upstream it must find its own depth
    held = bed0 - S * stop + normal_depth(FLOW, BOTTOM, SIDE, N, S)
    cfg = job(
        dem,
        nx // 4,
        ny // 4,
        DX,
        terrain={"objects": [obj], "manning": manning},
        hydrology={
            "inflows": [
                {
                    "name": "in",
                    "x": point(60.0)[0],
                    "y": point(60.0)[1],
                    "times_s": [0.0, 1e6],
                    "flows": [FLOW, FLOW],
                }
            ],
            "inject_radius": 10.0,
        },
        boundaries=[{"kind": "stage", "coordinates": [point(stop, -40.0), point(stop, 40.0)], "stage": held}],
        run={"duration_s": 2400.0, "source_every_s": 30.0},
        outputs={
            "points": [{"name": f"p{i}", "x": point(s)[0], "y": point(s)[1]} for i, s in enumerate(stations)],
            "lines": [{"name": "q", "coordinates": [point(stations[1], -40.0), point(stations[1], 40.0)]}],
            "series_every_s": 20.0,
        },
    )
    out = tmp_path / f"run{angle:.0f}"
    run = run_job(cfg, out)
    assert run.exit_code == 0, run.message
    depths = []
    with h5py.File(out / "results.h5", "r") as f:
        for i, s in enumerate(stations):
            level = f[f"series/points/p{i}/level_m"][()]
            depths.append(float(level[-30:].mean()) - (bed0 - S * s))
        flow = float(np.abs(f["series/lines/q/discharge_m3s"][()])[-30:].mean())
    return depths, flow


@pytest.mark.parametrize("angle", [0.0, 45.0])
def test_a_straight_trapezoid_runs_at_manning_normal_depth(tmp_path, angle):
    depths, flow = channel_case(tmp_path, angle)
    expected = normal_depth(FLOW, BOTTOM, SIDE, N, S)
    assert flow == pytest.approx(FLOW, rel=0.02)
    for depth in depths:
        assert depth == pytest.approx(expected, rel=0.05)


def test_a_lined_channel_runs_at_the_depth_of_its_lining(tmp_path):
    depths, _flow = channel_case(tmp_path, 0.0, manning=0.12, lining=N)
    expected = normal_depth(FLOW, BOTTOM, SIDE, N, S)
    for depth in depths:
        assert depth == pytest.approx(expected, rel=0.05)


@pytest.mark.parametrize("angle", [0.0, 45.0])
def test_a_channel_between_dykes_runs_at_manning_normal_depth(tmp_path, angle):
    # the ground is only 0.5 m above the bed, so the water stands against the dykes and between their crest lines
    depths, flow = channel_case(tmp_path, angle, depth=0.5, dyke=True)
    expected = normal_depth(FLOW, BOTTOM, SIDE, N, S)
    assert expected > 0.5
    assert flow == pytest.approx(FLOW, rel=0.02)
    for depth in depths:
        assert depth == pytest.approx(expected, rel=0.05)


CREST, HEAD = 102.0, 0.6


def step_dem(tmp_path, nx: int, ny: int, pixel: float, drop_at) -> object:
    """Ground at 100 upstream and at 95 past ``drop_at(x, y)``, so the crest is the only control."""
    x = (np.arange(nx) + 0.5) * pixel
    y = (np.arange(ny) + 0.5) * pixel
    z = np.where(drop_at(x[None, :], y[:, None]), 95.0, 100.0)
    return write_dem(tmp_path / "step.tif", z, pixel)


def barrier(kind: str, a, b) -> dict:
    """A dyke from ``a`` to ``b``: an embankment on the line, or the right bank of a channel beside it."""
    if kind == "embankment":
        section = {"width": 4.0, "left_slope": 2.0, "right_slope": 2.0}
        return {"kind": kind, "coordinates": [a, b], "z_constant": CREST, "section": section}
    section = {
        "width": 8.0, "left_slope": 2.0, "right_slope": 2.0, "left_top_z": 99.5, "right_top_z": CREST,
        "right_crest_width": 4.0, "right_outer_slope": 2.0,
    }  # fmt: skip
    return {"kind": kind, "coordinates": [a, b], "z_constant": 99.0, "section": section}


def weir_case(tmp_path, kind: str, stage: float, duration: float, diagonal: bool = False):
    """A reservoir already full at ``stage``, so no surge runs up the bank; a free fall behind the crest."""
    nx, ny, pixel, dx = 160, 40, 2.0, 8.0
    width = ny * pixel
    far = X0 - 100.0
    probe = [(X0 + 230.0, Y0), (X0 + 230.0, Y0 - width)]
    if diagonal:
        drop = lambda x, y: x - y > 160.0  # noqa: E731
        a, b = (X0 + 160.0, Y0), (X0 + 160.0 + width, Y0 - width)
        reach = width * math.sqrt(2.0)
        # back off the line by more than a cell: the faces are a staircase round it, water must start on one side
        back = 2.0 * dx
        ring = [
            (far, Y0 + 10.0), (a[0] - back, a[1] + 10.0), (b[0] - back, b[1] - 10.0), (far, Y0 - width - 10.0),
        ]  # fmt: skip
    else:
        crest = 164.0 if kind == "embankment" else 172.0
        drop = lambda x, y: x + 0.0 * y > crest + 8.0  # noqa: E731
        start = 164.0 if kind == "embankment" else 160.0
        a, b = (X0 + start, Y0 - width), (X0 + start, Y0)
        reach = width
        ring = [
            (far, Y0 + 10.0), (X0 + crest, Y0 + 10.0), (X0 + crest, Y0 - width - 10.0), (far, Y0 - width - 10.0),
        ]  # fmt: skip
    dem = step_dem(tmp_path, nx, ny, pixel, drop)
    cfg = job(
        dem,
        nx // 4,
        ny // 4,
        dx,
        terrain={"objects": [barrier(kind, a, b)]},
        initial_levels=[{"coordinates": ring, "level": stage}],
        boundaries=[
            {"kind": "stage", "coordinates": [(X0 + 4.0, Y0), (X0 + 4.0, Y0 - width)], "stage": stage},
            {"kind": "free", "coordinates": [(X0 + 316.0, Y0), (X0 + 316.0, Y0 - width)]},
        ],
        run={"duration_s": duration, "source_every_s": 30.0},
        outputs={"lines": [{"name": "over", "coordinates": probe}], "series_every_s": 5.0},
    )
    out = tmp_path / "weir"
    run = run_job(cfg, out)
    assert run.exit_code == 0, run.message
    with h5py.File(out / "results.h5", "r") as f:
        return np.abs(f["series/lines/over/discharge_m3s"][()]), reach


@pytest.mark.parametrize("kind", ["embankment", "channel_dyke"])
def test_a_dyke_holds_water_below_its_crest(tmp_path, kind):
    q, _reach = weir_case(tmp_path, kind, CREST - 0.3, 900.0)
    assert q.max() == 0.0


@pytest.mark.parametrize("kind", ["embankment", "channel_dyke"])
def test_a_dyke_overtopped_passes_critical_flow(tmp_path, kind):
    q, reach = weir_case(tmp_path, kind, CREST + HEAD, 900.0)
    assert q[-40:].mean() == pytest.approx(CRITICAL_WEIR_COEFF * reach * HEAD**1.5, rel=0.05)


def test_a_diagonal_dyke_holds_on_coarse_cells(tmp_path):
    # filled slowly to 0.3 m under the crest: a ridge in the pixels alone would pass this at every face it crosses
    nx, ny, pixel, dx = 160, 40, 2.0, 8.0
    width = ny * pixel
    dem = step_dem(tmp_path, nx, ny, pixel, lambda x, y: x - y > 160.0)
    a, b = (X0 + 160.0, Y0), (X0 + 160.0 + width, Y0 - width)
    area = 160.0 * width + 0.5 * width * width
    flow = 12.0
    fill = (CREST - 0.3 - 100.0) * area / flow
    cfg = job(
        dem,
        nx // 4,
        ny // 4,
        dx,
        terrain={"objects": [barrier("embankment", a, b)]},
        hydrology={
            "inflows": [
                {
                    "name": "in",
                    "x": X0 + 40.0,
                    "y": Y0 - 40.0,
                    "times_s": [0.0, fill, fill + 1.0, 1e6],
                    "flows": [flow, flow, 0.0, 0.0],
                }
            ],
            "inject_radius": 12.0,
        },
        run={"duration_s": fill + 200.0, "source_every_s": 10.0},
        outputs={
            "lines": [{"name": "over", "coordinates": [(X0 + 230.0, Y0), (X0 + 230.0, Y0 - width)]}],
            "series_every_s": 5.0,
        },
    )
    out = tmp_path / "hold"
    run = run_job(cfg, out)
    assert run.exit_code == 0, run.message
    with h5py.File(out / "results.h5", "r") as f:
        q = f["series/lines/over/discharge_m3s"][()]
        depth = f["maxima"]["depth"][()]
    assert np.abs(q).max() == 0.0
    assert depth.max() > 1.5


def test_a_diagonal_dyke_overtopped_passes_critical_flow_along_its_true_length(tmp_path):
    q, reach = weir_case(tmp_path, "embankment", CREST + HEAD, 900.0, diagonal=True)
    assert q[-40:].mean() == pytest.approx(CRITICAL_WEIR_COEFF * reach * HEAD**1.5, rel=0.05)


PARTLY_WET_SPEED = 2e-6
"""Water below the crests touches wet and dry cells; an old burn line on this ground gives 1.2e-6 m/s."""


def bumpy(nx: int, ny: int, pixel: float) -> np.ndarray:
    x = (np.arange(nx) + 0.5) * pixel
    y = (np.arange(ny) + 0.5) * pixel
    return 100.0 + 0.8 * np.sin(x[None, :] / 37.0) * np.cos(y[:, None] / 23.0) - 0.004 * x[None, :]


EVERY_OBJECT = [
    {
        "kind": "embankment", "name": "bank", "z_constant": 103.0,
        "coordinates": [(X0 + 30.0, Y0 - 20.0), (X0 + 120.0, Y0 - 90.0), (X0 + 250.0, Y0 - 100.0)],
        "section": {"width": 4.0}, "openings": [{"start": 60.0, "end": 90.0}],
    },
    {
        "kind": "channel", "name": "cut", "coordinates": [(X0 + 40.0, Y0 - 150.0), (X0 + 270.0, Y0 - 170.0)],
        "z": [98.5, 97.5], "section": {"width": 12.0}, "lining_n": 0.018, "start_end": "taper", "end_end": "closed",
    },
    {
        "kind": "channel_dyke", "name": "mixed", "coordinates": [(X0 + 20.0, Y0 - 215.0), (X0 + 280.0, Y0 - 225.0)],
        "z": [98.0, 97.0],
        "section": {"width": 14.0, "left_top_z": 100.3, "right_top_z": 99.0, "right_crest_width": 2.0},
        "openings": [{"start": 100.0, "end": 130.0, "side": "left"}],
    },
]  # fmt: skip


@pytest.mark.parametrize("level", [104.0, 99.5])
def test_still_water_stays_still_over_every_object(tmp_path, level):
    nx, ny, pixel, dx = 240, 200, 1.25, 5.0
    dem = write_dem(tmp_path / "bumpy.tif", bumpy(nx, ny, pixel), pixel)
    ring = [
        (X0 - 10.0, Y0 + 10.0),
        (X0 + 310.0, Y0 + 10.0),
        (X0 + 310.0, Y0 - 260.0),
        (X0 - 10.0, Y0 - 260.0),
    ]
    cfg = job(
        dem,
        nx // 4,
        ny // 4,
        dx,
        terrain={"objects": EVERY_OBJECT},
        initial_levels=[{"coordinates": ring, "level": level}],
        run={"duration_s": 120.0, "source_every_s": 30.0},
    )
    out = tmp_path / "still"
    run = run_job(cfg, out)
    assert run.exit_code == 0, run.message
    with h5py.File(out / "results.h5", "r") as f:
        speed = f["maxima"]["speed"][()]
    assert speed.max() == 0.0 if level > 103.0 else speed.max() < PARTLY_WET_SPEED
    assert abs(run.balance.storage - run.balance.storage0) <= 1e-12 * run.balance.storage0


def test_a_spillway_on_a_real_embankment_passes_its_rating(tmp_path):
    # the raised pixels must be notched, or the faces meet the embankment instead of the spillway crest
    nx, ny, pixel, dx = 120, 32, 2.0, 4.0
    z = np.full((ny, nx), 90.0)
    z[:, 62:] = 80.0
    dem = write_dem(tmp_path / "s.tif", z, pixel)
    crest_z, head, c, length = 100.0, 0.8, 2.1, 40.0
    line = [(X0 + 120.0, Y0), (X0 + 120.0, Y0 - 64.0)]
    spill = [(X0 + 120.0, Y0 - 12.0), (X0 + 120.0, Y0 - 52.0)]
    objects = [
        {"kind": "embankment", "coordinates": line, "z_constant": 110.0, "section": {"width": 6.0}},
        {"kind": "spillway", "coordinates": spill, "z_constant": crest_z, "coefficient": c, "length": length},
    ]
    cfg = job(
        dem,
        60,
        16,
        dx,
        terrain={"objects": objects},
        boundaries=[
            {
                "kind": "stage",
                "coordinates": [(X0 + 2.0, Y0), (X0 + 2.0, Y0 - 64.0)],
                "stage": crest_z + head,
            },
            {"kind": "free", "coordinates": [(X0 + 238.0, Y0), (X0 + 238.0, Y0 - 64.0)]},
        ],
        run={"duration_s": 900.0, "source_every_s": 30.0},
        outputs={"lines": [{"name": "sp", "coordinates": line}], "series_every_s": 5.0},
    )
    run = run_job(cfg, tmp_path / "s")
    assert run.exit_code == 0, run.message
    with h5py.File(tmp_path / "s" / "results.h5", "r") as f:
        q = f["series/lines/sp/discharge_m3s"][()]
    assert abs(q[-40:].mean()) == pytest.approx(c * length * head**1.5, rel=0.05)


def test_old_crests_keep_their_law_and_new_ones_read_the_energy_head(tmp_path):
    dem = write_dem(tmp_path / "f.tif", np.full((64, 64), 100.0), 2.0)
    line = [(X0 + 60.0, Y0), (X0 + 60.0, Y0 - 128.0)]
    old = job(
        dem,
        16,
        16,
        8.0,
        terrain={"objects": [{"kind": "crest_line", "coordinates": line, "z_constant": 102.0}]},
    )
    thin = {**barrier("embankment", *line), "section": {"width": 3.0}}
    new = job(dem, 16, 16, 8.0, terrain={"objects": [thin]})
    wide = job(
        dem, 16, 16, 8.0, terrain={"objects": [{**barrier("embankment", *line), "section": {"width": 20.0}}]}
    )
    assert prepare_grid(old, tmp_path / "c")[0].cwx.max() == pytest.approx(CRITICAL_WEIR_COEFF)
    assert prepare_grid(new, tmp_path / "c")[0].cwx.min() == pytest.approx(-CRITICAL_WEIR_COEFF)
    assert np.abs(prepare_grid(wide, tmp_path / "c")[0].cwx).max() == 0.0
