"""Steady flows with friction: subcritical, supercritical and with a hydraulic jump (MacDonald profiles)."""

from __future__ import annotations

import numpy as np
import pytest

from tests.solver import harness
from wadi2d.config.schema import Numerics
from wadi2d.solver.backend import BoundaryCells
from wadi2d.validation import UniformGrid
from wadi2d.validation.case import State
from wadi2d.validation.cases import macdonald


def _steady(variant, t_end=2500.0):
    """Hold the upstream cell and its face at the exact state; downstream hold the depth or let it run out."""
    case = macdonald.build_macdonald(UniformGrid(0.0, 0.0, 5.0, 200, 4), variant)
    g = case.grid
    m = harness.build(case, num=Numerics(dt_every=1, e_wet=1e-5), backend="cpu")
    harness.set_initial(case, m, 1)
    exact = case.exact(case.t_end)
    q = float(case.solution.q)
    h_in = float(exact.h[0, 0])
    h_out = float(exact.h[0, -1])
    jr = range(g.ny)
    inlet = [m.cell_state_index(j + harness.PAD, harness.PAD) for j in jr]
    face = [m.cell_state_index(j + harness.PAD, harness.PAD + 1) for j in jr]
    last = [m.cell_state_index(j + harness.PAD, g.nx - 1 + harness.PAD) for j in jr]
    inner = [m.cell_state_index(j + harness.PAD, g.nx - 2 + harness.PAD) for j in jr]
    n = g.ny
    subcritical_in = variant is macdonald.Variant.SUBCRITICAL
    subcritical_out = variant is not macdonald.Variant.SUPERCRITICAL
    cells = ([] if subcritical_in else inlet) + last
    refs = ([] if subcritical_in else inlet) + inner
    d_out = h_out if subcritical_out else 0.0
    head = [] if subcritical_in else [h_in] * n
    m.set_boundary(
        BoundaryCells(
            np.array(cells, np.int32),
            np.array(refs, np.int32),
            np.array(([0] * len(head)) + ([0 if subcritical_out else 2] * n), np.int32),
            np.array(head + [d_out] * n, np.float32),
            np.array(head + [d_out] * n, np.float32),
        )
    )
    b = m.backend
    if subcritical_in:
        # a subcritical inlet fixes the discharge only: the depth has to answer to the downstream
        rate = np.zeros(m.grid.shape)
        rate[harness.PAD : harness.PAD + g.ny, harness.PAD] = q / g.dx
        m.set_source(rate)
        m.advance(t_end)
        return case, harness.result(case, m)
    u_in = q / h_in
    idx = np.array(face + inlet)  # the inlet cell's west face too: the first face needs momentum coming in

    def hold(_):
        b.u[idx] = u_in
        b.mx[idx] = h_in * g.dx * u_in
        b.qx[idx] = q * g.dx

    m.advance(t_end, hold)
    return case, harness.result(case, m)


@pytest.mark.parametrize(
    "variant, limit",
    [
        (macdonald.Variant.SUBCRITICAL, 0.015),
        (macdonald.Variant.SUPERCRITICAL, 0.012),
        (macdonald.Variant.JUMP, 0.05),
    ],
)
def test_macdonald(variant, limit):
    case, s = _steady(variant)
    exact: State = case.exact(case.t_end)
    err = np.sqrt(np.mean((s.h[1, 2:-2] - exact.h[1, 2:-2]) ** 2))
    assert err < limit
    assert s.qx[1, 2:-2] == pytest.approx(case.solution.q, rel=0.02)


