"""The hybrid step on the GPU (W45, stage 5): the CUDA twin of the strip gives the CPU hybrid's answer on the
channel, through and across the join, keeps still water still and a closed box's water."""

from __future__ import annotations

import numpy as np
import pytest

from tests.strips.test_hybrid import composed_depth, hybrid_case, run_hybrid_channel
from wadi2d.config.schema import Numerics
from wadi2d.tables.builder import hbar_at_level

pytestmark = pytest.mark.gpu


@pytest.mark.parametrize("theta", [0.0, 45.0])
def test_the_gpu_hybrid_gives_the_cpu_hybrid_answer_on_the_channel(theta: float) -> None:
    cpu, cpu_steps = run_hybrid_channel(theta, "cpu")
    gpu, gpu_steps = run_hybrid_channel(theta, "gpu")
    assert gpu == pytest.approx(cpu, abs=2e-3), (gpu, cpu, gpu_steps, cpu_steps)
    assert abs(gpu_steps - cpu_steps) <= max(2, cpu_steps // 200)


def test_the_two_backends_agree_cell_by_cell_after_a_release_across_the_join() -> None:
    fields = {}
    for backend in ("cpu", "gpu"):
        tg, tables, sc, _tc, model, hybrid, cells = hybrid_case(0.0, Numerics(dt_every=1), backend)
        hc, dtab = tg.from_tiles(tables.hc), tg.from_tiles(tables.dtab)
        level = 101.0 + 0.3 * np.tanh(sc / 100.0)
        hb = hbar_at_level(level, tables.zmin, hc, dtab) * tg.mask
        model.set_depth(hb)
        jj, ii = cells
        hybrid.set_strip_depth(hybrid.strip_hbar_at_level(level[jj, ii]))
        v0 = hybrid.volume()
        hybrid.advance(120.0)
        assert hybrid.volume() == pytest.approx(v0, rel=1e-7)
        fields[backend] = composed_depth(tg, hybrid, cells)
    worst = float(np.abs(fields["gpu"] - fields["cpu"]).max())
    assert worst < 1e-4, worst  # the gate of stage 5: within 1e-4 m


def test_still_water_across_the_join_stays_still_on_the_gpu() -> None:
    tg, tables, _sc, _tc, model, hybrid, _cells = hybrid_case(30.0, Numerics(dt_every=1), "gpu")
    hc, dtab = tg.from_tiles(tables.hc), tg.from_tiles(tables.dtab)
    hb = hbar_at_level(101.0, tables.zmin, hc, dtab) * tg.mask
    model.set_depth(hb)
    hybrid.set_strip_depth(hybrid.strip_hbar_at_level(101.0))
    v0 = hybrid.volume()
    hybrid.advance(600.0)
    speed = max(float(np.abs(model.field("u")).max()), float(np.abs(model.field("v")).max()))
    assert speed < 2e-5
    assert float(np.abs(hybrid.strip_host("u")).max()) < 2e-5
    assert hybrid.volume() == pytest.approx(v0, rel=1e-7)
