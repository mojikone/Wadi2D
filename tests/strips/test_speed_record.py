"""The strip's speed of record (W87): read from the faces' velocities as the squares read theirs, never the cell's
momentum over its volume. On a strip of squares it is the lattice's mean of opposite faces; a uniform velocity is read
exactly on any polygon, at map coordinates; nothing passes what a square can read; and a flood front over a dry gully
that weaves through a corridor's gap triangles records speeds of the same order as the squares alone, where the run
before recorded 1.6e7 m/s (Block 2, W79: 1e7 to 7e8 m/s on the aligned cells)."""

from __future__ import annotations

import h5py
import numpy as np
import pytest

from tests.engine.conftest import X0, Y0, write_dem
from tests.engine.test_strips_run import MID_Y, corridor, plane_job
from tests.strips.test_hybrid import hybrid_case
from wadi2d.config.schema import Inflow, Numerics
from wadi2d.run import run_job
from wadi2d.solver.poly import kernel
from wadi2d.solver.poly.mesh import PolyMesh
from wadi2d.strips.geometry import MeshGeometry

F = np.float32
U_MAX = Numerics().u_max
CAP = kernel.SPEED_CAP * U_MAX


def lattice_speed(mesh: PolyMesh, u: np.ndarray) -> np.ndarray:
    """The lattice's rule on a mesh of squares: at each real cell, half the sum of its two x-faces' velocities and half
    of its two y-faces', as ``wadi2d.engine.maxima`` reads a square."""
    vx, vy = np.zeros(mesh.ncells), np.zeros(mesh.ncells)
    for side in (mesh.left, mesh.right):
        np.add.at(vx, side, 0.5 * u * np.round(mesh.nx))
        np.add.at(vy, side, 0.5 * u * np.round(mesh.ny))
    return np.hypot(vx, vy)[: mesh.real]


def one_cell(ring: np.ndarray) -> PolyMesh:
    """One polygon whose every face opens onto a ghost: only what the speed of record reads is filled."""
    geo = MeshGeometry.from_rings(ring[:, 0], ring[:, 1], [np.arange(len(ring))])
    area, cx, cy = geo.areas_centroids()
    length, nfx, nfy, xf, yf = geo.faces(cx, cy)
    nf = geo.nfaces
    none = np.zeros(0)
    return PolyMesh(
        area=np.append(area, 1.0), cx=np.append(cx, 0.0), cy=np.append(cy, 0.0), zmin=none, zbar=none, hc=none,
        dtab=np.zeros((2, 2)), left=np.zeros(nf, np.int64), right=np.ones(nf, np.int64), length=length, nx=nfx, ny=nfy,
        xf=xf, yf=yf, zf=none, ef=none, ftab=none, cw=none, dx=20.0, nreal=1,
    )  # fmt: skip


def speed_of(mesh: PolyMesh, u: np.ndarray, cap: float = CAP) -> np.ndarray:
    n = mesh.real
    vx, vy, speed = (np.zeros(n, F) for _ in range(3))
    weights = tuple(w.astype(F) for w in mesh.speed_weights())
    kernel.cell_speed(
        mesh.nfaces,
        n,
        mesh.left.astype(np.int64),
        mesh.right.astype(np.int64),
        *weights,
        u.astype(F),
        F(cap),
        vx,
        vy,
        speed,
    )
    return speed


def test_on_a_strip_of_squares_the_speed_of_record_is_the_lattices_mean_of_opposite_faces() -> None:
    _tg, _tables, _sc, _tc, _model, hybrid, _cells = hybrid_case(0.0)
    s, mesh = hybrid.state, hybrid.mesh
    rng = np.random.default_rng(3)
    s.u[:] = rng.uniform(-3.0, 3.0, mesh.nfaces).astype(F)
    s.u[rng.random(mesh.nfaces) < 0.2] = 0.0  # dry faces carry nothing, as on the lattice
    before = {name: getattr(s, name).copy() for name in ("h", "d", "om", "u", "m", "q", "res", "Ux", "Uy")}
    speed = hybrid.strip_cell_speed()
    assert speed.shape == (mesh.real,)
    assert np.allclose(speed, lattice_speed(mesh, s.u.astype(np.float64)), atol=2e-5)
    for name, a in before.items():  # the record reads the state and writes none of it
        assert np.array_equal(getattr(s, name), a), name


@pytest.mark.parametrize("ring", [
    [[0.0, 0.0], [20.0, 0.0], [20.0, 20.0], [0.0, 20.0]],
    [[0.0, 0.0], [14.0, -3.0], [22.0, 9.0], [11.0, 21.0], [-4.0, 12.0]],
    [[0.0, 0.0], [20.0, 0.0], [10.0, 0.4]],  # a sliver gap triangle, 50 to 1
])  # fmt: skip
def test_a_uniform_velocity_is_read_exactly_on_any_polygon_at_map_coordinates(ring) -> None:
    """Float32 holds a northing of 2.7e6 to 0.25 m: the lever arms are differenced in double precision first."""
    mesh = one_cell(np.array(ring) + [X0 + 31_234.56, Y0 + 33_456.78])
    velocity = np.array([1.3, -0.7])
    u = velocity[0] * mesh.nx + velocity[1] * mesh.ny  # each face's normal component of the same velocity
    assert speed_of(mesh, u)[0] == pytest.approx(np.hypot(*velocity), rel=2e-5)


def test_the_speed_of_record_never_passes_what_a_square_can_read() -> None:
    """Face velocities no uniform flow could give, on a sliver, would read 50 times the cap: the record stops at the
    most a square's centre reads with its four faces at ``u_max``."""
    mesh = one_cell(np.array([[0.0, 0.0], [20.0, 0.0], [10.0, 0.4]]))
    u = U_MAX * np.sign(
        np.round(mesh.xf - mesh.cx[0], 6)
    )  # out of one long side at the cap, in through the other
    assert speed_of(mesh, u, cap=1e9)[0] > 10.0 * CAP
    assert speed_of(mesh, u)[0] == pytest.approx(CAP, rel=1e-6)
    square = one_cell(np.array([[0.0, 0.0], [20.0, 0.0], [20.0, 20.0], [0.0, 20.0]]))
    flat_out = U_MAX * (square.nx + square.ny)  # every face at the cap, along +x and +y
    assert speed_of(square, flat_out, cap=1e9)[0] == pytest.approx(CAP, rel=1e-6)


def gully_dem(folder):
    """200 x 96 m at 0.5 m pixels falling 10 % east, rough to 0.3 m, with a gully 1 m deep that weaves 16 m either
    side of the corridor's axis: in and out through the gap triangles of a corridor 12 m either side of it."""
    pixel = 0.5
    x, y = np.meshgrid((np.arange(400) + 0.5) * pixel, (np.arange(192) + 0.5) * pixel)
    gully = -1.0 * np.clip(1.0 - np.abs(y - (48.0 + 16.0 * np.sin(x / 17.0))) / 1.5, 0.0, 1.0)
    z = 100.0 - 0.1 * x + gully + np.random.default_rng(7).uniform(0.0, 0.3, x.shape)
    return write_dem(folder / "gully.tif", z, pixel)


def front_job(dem, strips: dict | None, backend: str = "cpu"):
    """Two floods of 3 m3/s down the dry gully, the bed draining between them; a map every minute."""
    cfg = plane_job(dem, strips)
    point = Inflow(
        name="in",
        x=X0 + 60.0,
        y=MID_Y,
        times_s=[0.0, 300.0, 301.0, 600.0, 900.0, 901.0, 1800.0],
        flows=[3.0, 3.0, 0.0, 0.0, 3.0, 0.0, 0.0],
    )
    return cfg.model_copy(update={
        "storm": cfg.storm.model_copy(update={"depth_mm": 0.01}),
        "hydrology": cfg.hydrology.model_copy(update={"inflows": [point], "inject_radius": 6.0}),
        "outputs": cfg.outputs.model_copy(update={"maxima_every": 1, "map_every_s": 60.0}),
        "run": cfg.run.model_copy(update={"backend": backend}),
    })  # fmt: skip


def record_of(out) -> dict[str, np.ndarray]:
    """The run's maxima and the largest strip speed of its saved maps."""
    with h5py.File(out / "results.h5", "r") as f:
        found = {name: f["maxima"][name][()] for name in f["maxima"]}
        maps = [g["strip_speed"][()] for g in f["maps"].values() if "strip_speed" in g]
    if maps:
        found["map_strip_speed"] = np.max(maps, axis=0)
    return found


def run_front(tmp_path, backend: str):
    dem = gully_dem(tmp_path)
    with_strips = run_job(front_job(dem, corridor(), backend), tmp_path / "strips")
    plain = run_job(front_job(dem, None, backend), tmp_path / "plain")
    assert with_strips.exit_code == 0 and plain.exit_code == 0, (with_strips.message, plain.message)
    assert abs(with_strips.balance.relative) < 1e-6
    return record_of(tmp_path / "strips"), record_of(tmp_path / "plain")


def check_record(tmp_path, backend: str) -> None:
    """What the record holds whatever the step does: nothing above what a square can read, in the maxima and in the
    saved maps (no depth threshold there, as the squares' maps have none); the hazard is depth times that speed.
    """
    strip, squares = run_front(tmp_path, backend)
    wet = strip["strip_depth"][0] > 0.05
    assert wet.sum() > 150  # the front crossed the corridor and its triangles
    assert 2.0 < float(squares["speed"].max()) < 6.0  # the squares alone on this job: 3.4 m/s
    top = float(strip["strip_speed"].max())
    assert 1.0 < top <= CAP * (1.0 + 1e-6), top  # before W87: 1.6e7 m/s
    assert float(strip["map_strip_speed"].max()) <= CAP * (1.0 + 1e-6)
    assert float(strip["strip_hazard"].max()) <= float(strip["strip_depth"].max()) * top * (
        1.0 + 1e-6
    )  # before: 9.2e6 m2/s
    assert float(np.median(strip["strip_speed"][0][wet])) < float(squares["speed"].max())


def test_a_flood_front_over_dry_transition_cells_records_no_speed_above_what_a_square_can_read(
    tmp_path,
) -> None:
    check_record(tmp_path, "cpu")


@pytest.mark.gpu
def test_the_same_front_on_the_gpu_records_no_speed_above_what_a_square_can_read(tmp_path) -> None:
    check_record(tmp_path, "gpu")


@pytest.mark.xfail(reason="W87, a fault in the step, not in the record, and his decision: the velocity written into the squares' face on the join divides the discharge by the ghost's depth floored at 1e-6 m, and the Perot cell vector by a volume floored at 1e-9 m3; on a front over a dry join each feeds the other, faces are kicked to u_max, and the line across the corridor peaks 22 % over the inflow", strict=False)  # fmt: skip
def test_a_flood_front_over_a_dry_join_carries_the_inflow_and_runs_at_the_squares_speed(tmp_path) -> None:
    """With either velocity bounded at ``u_max`` (``W87 strip max speed/kernel_probe.py``, in memory) the line reads
    3.000 m3/s, the squares alone 3.000, and the strip's fastest cell 3.0 m/s against the squares' 3.4; as the step
    stands, 3.655 m3/s and 39 cells over 10 m/s."""
    strip, squares = run_front(tmp_path, "cpu")
    rows = (tmp_path / "strips" / "series" / "line_across.csv").read_text(encoding="utf-8").splitlines()[1:]
    peak = max(abs(float(r.split(",")[1])) for r in rows)
    assert peak == pytest.approx(3.0, rel=0.02), peak
    assert float(strip["strip_speed"].max()) < 2.0 * float(squares["speed"].max())


@pytest.mark.gpu
def test_the_gpu_reads_the_cpus_speed_of_record_and_holds_its_maxima() -> None:
    _tg, _tables, _sc, _tc, _model, hybrid, _cells = hybrid_case(0.0, backend="gpu")
    s, mesh = hybrid.state, hybrid.mesh
    cp = s.cp
    rng = np.random.default_rng(5)
    u = rng.uniform(-3.0, 3.0, mesh.nfaces).astype(F)
    u[rng.random(mesh.nfaces) < 0.2] = 0.0
    s.u[:] = cp.asarray(u)
    want = speed_of(mesh, u)
    assert np.allclose(hybrid.strip_cell_speed(), want, atol=2e-5)
    deep = rng.random(mesh.real) < 0.5  # half the cells deeper than the speed depth, half not
    s.d[: mesh.real] = cp.asarray(np.where(deep, 0.5, 0.01).astype(F))
    s.maxima(0.05, hybrid.max_d, hybrid.max_h, hybrid.max_s, hybrid.max_dv, hybrid.max_q)
    max_s, max_dv = hybrid.strip_speed_maxima()
    assert np.allclose(max_s, np.where(deep, want, 0.0), atol=2e-5)
    assert np.allclose(max_dv, np.where(deep, 0.5 * want, 0.0), atol=2e-5)
