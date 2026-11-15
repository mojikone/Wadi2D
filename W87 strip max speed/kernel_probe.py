"""W87, diagnosis only: do the unbounded velocities the step itself reads move the water?

The record is fixed (the strip's speed is read from its faces' velocities). The step still reads two velocities that
divide a discharge by a vanishing volume, and this script bounds each of them in memory, never in the source, and reruns
the test's gully job on the CPU to see what moves:

* ``cell``: the Perot cell vector ``U`` of the strip (``kernel.perot_velocity``) and of a ghost's lattice neighbour
  (``hybrid.ghost_rates``), which the strip's advection, friction speed and crest head read; bounded at ``u_max``.
* ``join``: the velocity the strip writes into the squares' closed face on the join (``HybridCpu.after_update``,
  ``q / (max(h, 1e-6) dx)``), which the squares' advection stencil and their speed of record read; bounded at ``u_max``.

    .venv\\Scripts\\python "W87 strip max speed\\kernel_probe.py" <work folder>

It belongs to the code as it stood at commit ``88b2d8c``, before the step was bounded in the source: on later code
there is nothing left to bound and it stops with a line saying so.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import h5py
import numpy as np
from numba import njit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.engine.test_strips_run import corridor, peak_and_volume  # noqa: E402
from tests.strips.test_speed_record import front_job, gully_dem  # noqa: E402
from wadi2d.run import run_job  # noqa: E402
from wadi2d.solver.layout import STRIDE  # noqa: E402
from wadi2d.solver.poly import kernel  # noqa: E402
from wadi2d.strips import hybrid  # noqa: E402

if hasattr(kernel, "bounded"):
    raise SystemExit(
        "the step is bounded in the source now: run this diagnosis on the code at commit 88b2d8c"
    )

F = np.float32
ZERO, HALF = F(0.0), F(0.5)
U_MAX = F(25.0)

perot_as_is, rates_as_is, after_as_is = (
    kernel.perot_velocity,
    hybrid.ghost_rates,
    hybrid.HybridCpu.after_update,
)


@njit(cache=False)
def perot_bounded(nf, nc, L, R, xf, yf, cx, cy, q, h, area, Ux, Uy) -> None:
    perot_as_is(nf, nc, L, R, xf, yf, cx, cy, q, h, area, Ux, Uy)
    for c in range(nc):
        s = np.sqrt(Ux[c] * Ux[c] + Uy[c] * Uy[c])
        if s > U_MAX:
            Ux[c] *= U_MAX / s
            Uy[c] *= U_MAX / s


@njit(cache=False)
def rates_bounded(ng, nreal, ghost, dx, open_w, open_e, open_n, open_s, h, qx, qy, Ux, Uy, Rx, Ry) -> None:
    for g in range(ng):
        c = nreal + g
        k = ghost[g]
        for side in range(4):
            if side == 0:
                opened, q_out, n = open_w[g], -qx[k], k - 1
            elif side == 1:
                opened, q_out, n = open_e[g], qx[k + 1], k + 1
            elif side == 2:
                opened, q_out, n = open_n[g], -qy[k], k - STRIDE
            else:
                opened, q_out, n = open_s[g], qy[k + STRIDE], k + STRIDE
            if not opened or q_out == ZERO:
                continue
            if q_out > ZERO:
                ux, uy = Ux[c], Uy[c]
            else:
                vol = h[n] * dx * dx
                if vol > F(1e-9):
                    ux = HALF * dx * (qx[n] + qx[n + 1]) / vol
                    uy = -HALF * dx * (qy[n] + qy[n + STRIDE]) / vol
                    s = np.sqrt(ux * ux + uy * uy)
                    if s > U_MAX:
                        ux *= U_MAX / s
                        uy *= U_MAX / s
                else:
                    ux, uy = ZERO, ZERO
            Rx[c] += q_out * ux
            Ry[c] += q_out * uy


def after_bounded(self, dt: float, want_wave: bool) -> None:
    b, s, n = self.model.backend, self.state, self.nreal
    b.src[self.ghost] = self.saved
    dx = float(self.dx)
    for axis, (faces, group, signs, unique, all_copies, owner, ghost_of) in self.edge.items():
        if faces.size == 0:
            continue
        q_edge = np.zeros(unique.size, np.float64)
        np.add.at(q_edge, group, self.q_mean[faces] * signs)
        depth = np.maximum(s.h[n + ghost_of].astype(np.float64), 1e-6)
        speed = np.clip(q_edge / (depth * dx), -float(U_MAX), float(U_MAX))
        discharge, velocity = (b.qx, b.u1) if axis == "x" else (b.qy, b.v1)
        discharge[unique] = q_edge.astype(F)
        velocity[all_copies] = speed[owner].astype(F)


book_as_is = hybrid.HybridCpu._book
OLD: dict[str, np.ndarray] = {}


def book_and_old_record(self, dt: float) -> None:
    """The step's bookkeeping, and beside it the record as it was before W87: the Perot vector's length where the
    cell is deeper than the speed depth."""
    book_as_is(self, dt)
    s, n = self.state, self.nreal
    old = np.hypot(s.Ux[:n], s.Uy[:n]) * (s.d[:n] > self.speed_depth)
    OLD["max"] = np.maximum(OLD.get("max", np.zeros(n, F)), old)


def one(work: Path, name: str, dem, bound_cell: bool, bound_join: bool) -> dict:
    kernel.perot_velocity = perot_bounded if bound_cell else perot_as_is
    hybrid.ghost_rates = rates_bounded if bound_cell else rates_as_is
    hybrid.HybridCpu.after_update = after_bounded if bound_join else after_as_is
    hybrid.HybridCpu._book = book_and_old_record
    OLD.clear()
    out = work / name
    run = run_job(front_job(dem, corridor()), out)
    peak, volume = peak_and_volume(out)
    with h5py.File(out / "results.h5", "r") as f:
        mx = f["maxima"]
        s, d = mx["strip_speed"][0], mx["strip_depth"][0]
        sq, sd = mx["speed"][()], mx["depth"][()]
    wet, sq_wet = d > 0.05, sd > 0.05
    return {
        "exit": run.exit_code, "steps": run.steps, "mass_error": run.balance.relative,
        "storage_m3": run.balance.storage, "outflow_m3": run.balance.outflow, "line_peak_m3s": peak, "line_volume_m3": volume,
        "strip_wet": int(wet.sum()), "strip_speed_max": float(s.max()), "strip_speed_median": float(np.median(s[wet])),
        "strip_speed_q99": float(np.quantile(s[wet], 0.99)), "strip_over_10": int((s > 10).sum()), "strip_over_5": int((s > 5).sum()),
        "strip_depth_max": float(d.max()),
        "old_record_max": float(OLD["max"].max()), "old_record_over_10": int((OLD["max"] > 10).sum()), "old_record_over_25": int((OLD["max"] > 25).sum()),
        "squares_speed_max": float(sq.max()), "squares_speed_q99": float(np.quantile(sq[sq_wet], 0.99)),
        "squares_over_10": int((sq > 10).sum()), "squares_over_5": int((sq > 5).sum()), "squares_depth_max": float(sd.max()),
    }  # fmt: skip


if __name__ == "__main__":
    work = Path(sys.argv[1])
    work.mkdir(parents=True, exist_ok=True)
    dem = gully_dem(work)
    found = {}
    for name, cell, join in (
        ("as_is", False, False),
        ("cell", True, False),
        ("join", False, True),
        ("both", True, True),
    ):
        found[name] = one(work, name, dem, cell, join)
        print(name, json.dumps(found[name]))
    plain = run_job(front_job(dem, None), work / "plain")
    with h5py.File(work / "plain" / "results.h5", "r") as f:
        sq = f["maxima"]["speed"][()]
    peak, volume = peak_and_volume(work / "plain")
    found["plain"] = {
        "steps": plain.steps,
        "line_peak_m3s": peak,
        "line_volume_m3": volume,
        "squares_speed_max": float(sq.max()),
        "outflow_m3": plain.balance.outflow,
    }
    print("plain", json.dumps(found["plain"]))
    (work / "kernel_probe.json").write_text(json.dumps(found, indent=1), encoding="utf-8")
