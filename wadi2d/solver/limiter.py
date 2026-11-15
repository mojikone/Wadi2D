"""What sets the time step (W85): the face whose wave speed the step rule read, and what stands there.

Both backends keep the largest wave speed of every tile for the step rule. This takes the tile that leads, copies its
block to the host and asks the CPU twin's ``face_step`` for the wave speed of each of its faces: one source for the
CPU and the GPU, no kernel changed, and nothing is run unless a job asks (``outputs.step_limiter``).

The state it reads is the one after the step, the kernels read the one before: on a step that holds for minutes the
two name the same face. On a quadtree the faces inside a tile are read at the tile's own cell size and the faces of an
interface between sizes are not; a strip beside the tiles (W45) is named when its wave leads, not located.
"""

from __future__ import annotations

import numpy as np
from numba import njit

from wadi2d.solver.cpu.kernels import face_step
from wadi2d.solver.layout import HALO, STRIDE, STRIDE2, TILE, TILE2

STATE = ("om", "zcx", "zcy", "h", "d", "u", "v", "mx", "my", "qx", "qy")
"""The state arrays ``face_step`` reads, in the order ``_waves`` takes them."""

NEAR = 0.8
"""Tiles whose wave is within this share of the leading one are counted as limiting too."""


@njit
def _waves(
    dt, om, zcx, zcy, h, d, u, v, mx, my, qx, qy, flx, frx, glx, grx, efx, cwx, ftabx, fly, fry, gly, gry, efy, cwy,
    ftaby, rows, g, dx, e_wet, h_cfl, u_max, lead, a_min, second, sheet, mirror, carry,
):  # fmt: skip
    """The wave speed of every own face of one tile, and the velocity each would take: (wx, wy, un_x, un_y)."""
    wx = np.zeros((TILE, TILE), np.float32)
    wy = np.zeros((TILE, TILE), np.float32)
    u1 = np.zeros(STRIDE2, np.float32)
    v1 = np.zeros(STRIDE2, np.float32)
    m1 = np.zeros(STRIDE2, np.float32)
    q1 = np.zeros(STRIDE2, np.float32)
    for j in range(TILE):
        for i in range(TILE):
            k = (j + HALO) * STRIDE + i + HALO
            fid = j * TILE + i
            wx[j, i] = face_step(
                k, fid, dt, True, om, zcx, 1, STRIDE, h, d, u, mx, qx, qy, v, flx, frx, glx, grx, efx, cwx, ftabx,
                u1, m1, q1, rows, g, dx, e_wet, h_cfl, u_max, lead, a_min, second, sheet, mirror, carry,
            )  # fmt: skip
            wy[j, i] = face_step(
                k, fid, dt, True, om, zcy, STRIDE, 1, h, d, v, my, qy, qx, u, fly, fry, gly, gry, efy, cwy, ftaby,
                v1, m1, q1, rows, g, dx, e_wet, h_cfl, u_max, lead, a_min, second, sheet, mirror, carry,
            )  # fmt: skip
    return wx, wy, u1, v1


def _host(backend, a) -> np.ndarray:
    cp = getattr(backend, "cp", None)
    return np.ascontiguousarray(a) if cp is None else cp.asnumpy(a)


def tile_block(backend, t: int) -> dict[str, np.ndarray]:
    """Host copies of what the faces of tile ``t`` read: its state block with halos, its face tables."""
    lo, hi = t * STRIDE2, (t + 1) * STRIDE2
    flo, fhi = t * TILE2, (t + 1) * TILE2
    rows2 = 2 * backend.rows
    block = {name: _host(backend, getattr(backend, name)[lo:hi]) for name in STATE}
    block["sx"] = tuple(_host(backend, a[flo:fhi]) for a in backend.static_x)
    block["sy"] = tuple(_host(backend, a[flo:fhi]) for a in backend.static_y)
    block["ftabx"] = _host(backend, backend.ftabx[flo * rows2 : fhi * rows2])
    block["ftaby"] = _host(backend, backend.ftaby[flo * rows2 : fhi * rows2])
    return block


def tile_waves(backend, t: int, dt: float, dx: float | None = None, block: dict | None = None):
    """(wx, wy, un_x, un_y) of tile ``t``: the wave speed its west and north faces would report in a step ``dt``, m/s,
    as (TILE, TILE) grids, and the face velocities of that step in the tile's state layout."""
    num = backend.num
    f = np.float32
    b = block or tile_block(backend, t)
    return _waves(
        f(dt), *(b[name] for name in STATE), *b["sx"], b["ftabx"], *b["sy"], b["ftaby"], backend.rows, f(num.g),
        f(num.dx if dx is None else dx), f(num.e_wet), f(num.h_cfl), f(num.u_max), f(num.lead), f(num.a_min),
        num.second, num.sheet, num.mirror, num.carry,
    )  # fmt: skip


def face_report(
    backend, grid, zmin, t: int, axis: int, j: int, i: int, waves, block: dict, dx: float
) -> dict:
    """What stands at the west (axis 0) or north (axis 1) face of own cell (j, i) of tile ``t``."""
    num = backend.num
    wx, wy, ux, vy = waves
    s = 1 if axis == 0 else STRIDE
    k = (j + HALO) * STRIDE + i + HALO
    fid = j * TILE + i
    wave = float((wx if axis == 0 else wy)[j, i])
    un = float((ux if axis == 0 else vy)[k])
    uf = float(block["u" if axis == 0 else "v"][k])
    fl, fr, _gl, _gr, _ef, cw = (a[fid] for a in block["sx" if axis == 0 else "sy"])
    d, h, om = block["d"], block["h"], block["om"]
    e_l, e_r = float(d[k - s] - fl), float(d[k] - fr)
    from_left = uf > 0.0 or (uf == 0.0 and e_l >= e_r)
    up, other = (k - s, k) if from_left else (k, k - s)
    plan = float(om[up])
    both = bool(d[other] > num.h_cfl)
    if both:
        plan = min(plan, float(om[other]))
    # the three parts of the kernel's sum, |u| + min(lead |du|, 2c) + c, taken apart without a second copy of its rule
    jump = num.lead * abs(un - uf)
    rest = wave - abs(un)
    c = rest - jump if rest - jump >= 0.5 * jump else rest / 3.0
    used = max(plan, num.a_min)
    scale = round(dx / grid.dx)
    tj, ti = (int(a) for a in grid.tiles[t])
    step = (0, -1) if axis == 0 else (-1, 0)
    own = (tj * TILE + j * scale, ti * TILE + i * scale)
    left = (own[0] + step[0] * scale, own[1] + step[1] * scale)
    cells = {"up": left if from_left else own, "other": own if from_left else left}
    half = 0.5 * (scale - 1)
    xy = {key: grid.xy_of(jj + half, ii + half) for key, (jj, ii) in cells.items()}
    slim = "other" if both and float(om[other]) < float(om[up]) else "up"
    """The cell whose wet share the rule read: the smaller of the two when both are wet."""
    out = {
        "tile": int(t),
        "axis": "x" if axis == 0 else "y",
        "x": round(float(xy[slim][0]), 2),
        "y": round(float(xy[slim][1]), 2),
        "j": int(cells[slim][0]),
        "i": int(cells[slim][1]),
        "face_x": round(0.5 * float(xy["up"][0] + xy["other"][0]), 2),
        "face_y": round(0.5 * float(xy["up"][1] + xy["other"][1]), 2),
        "wave": round(wave, 3),
        "speed": round(abs(un), 3),
        "jump": round(max(rest - c, 0.0), 3),
        "celerity": round(c, 3),
        "depth": round(float(d[up if slim == "up" else other]), 3),
        "mean_depth": round(float(h[up if slim == "up" else other]), 4),
        "plan": round(float(om[up if slim == "up" else other]), 4),
        "plan_floor": bool(plan < num.a_min),
        "upwind_depth": round(float(d[up]), 3),
        "upwind_plan": round(float(om[up]), 4),
        "face_depth": round(max(e_l, e_r), 3),
        "face_area": round(c * c / num.g * used * dx, 3),
        "hydraulic_depth": round(c * c / num.g, 3),
        "crest": bool(cw != 0.0),
        "cell_dx": float(dx),
    }
    if zmin is not None:
        jj, ii = cells[slim]
        if 0 <= jj < zmin.shape[0] and 0 <= ii < zmin.shape[1]:
            out["bed"] = round(float(zmin[jj, ii]), 3)
            out["level"] = round(out["bed"] + out["depth"], 3)
    return out


def step_limiter(model, tables=None) -> dict | None:
    """The face that sets the step now: where, what stands there, and the step without its tile. None on a dry run.

    ``wave`` is the kernel's sum for that face, m/s; ``speed``, ``jump`` and ``celerity`` are its three parts.
    ``celerity`` is sqrt(g x face area / (wet share of the cell plan x dx)), so a face deep under water beside a cell
    that is wet over a sliver of its plan reads a ``hydraulic_depth`` far above any depth on the ground.
    ``dt_without_tile`` is the step the next tile would give, with nothing else changed.
    """
    backend, grid, st = model.backend, model.grid, model.stepper
    num = st.num
    wave = _host(backend, backend.wave).astype(np.float64)
    quad = getattr(grid, "quad", False)
    tile_dx = np.asarray(grid.tile_dx, np.float64) if quad else np.full(wave.size, grid.dx)
    freq = wave / tile_dx
    freq[0] = 0.0
    t = int(np.argmax(freq))
    if not np.isfinite(freq[t]) or freq[t] <= 0.0:
        return None
    order = np.sort(freq)[::-1]
    floor = num.wave_floor / grid.dx
    strip = float(getattr(backend, "extra_wave", 0.0)) / grid.dx
    lead = {
        "dt": round(float(st.dt), 5),
        "dt_tile": round(num.cfl / max(freq[t], floor), 5),
        "dt_without_tile": round(min(num.cfl / max(order[1], strip, floor), num.dt_max), 5),
        "tiles_near": int((freq >= NEAR * freq[t]).sum()),
        "tile_wave": round(float(wave[t]), 3),
    }
    if strip > freq[t]:
        return {"source": "strip", "wave": round(strip * grid.dx, 3), **lead}
    dx = float(tile_dx[t])
    block = tile_block(backend, t)
    waves = tile_waves(backend, t, st.dt, dx, block)
    axis = 0 if waves[0].max() >= waves[1].max() else 1
    j, i = (int(a) for a in np.unravel_index(int(np.argmax(waves[axis])), (TILE, TILE)))
    zmin = getattr(tables, "zmin", None) if tables is not None and not quad else None
    report = face_report(backend, grid, zmin, t, axis, j, i, waves, block, dx)
    return {"source": "tiles", **report, **lead}
