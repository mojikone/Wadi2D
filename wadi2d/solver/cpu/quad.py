"""Numba twin of solver/gpu/kernels/quad.cu: same statement order, same float32 arithmetic."""

from __future__ import annotations

from numba import njit

from wadi2d.solver.cpu.kernels import ZERO, F, face_step, scaled
from wadi2d.solver.cpu.levels import edge_cell, edge_face
from wadi2d.solver.layout import STRIDE, STRIDE2, TILE

HALF_TILE = TILE // 2


@njit
def quad_halo(active, slot, cell, fu, fv, qu, qv, nhalo, level, n, h, h0, d, d0, u, v, qx, qy):
    for x in range(active.size):
        t = active[x]
        for m in range(nhalo):
            dst = t * STRIDE2 + slot[m]
            at = (t - 1) * nhalo + m
            s = cell[at]
            span = 1 << level[s // STRIDE2]
            part = n & (span - 1)
            if part == 0:
                h[dst] = h[s]
                d[dst] = d[s]
            else:
                w = F(part) / F(span)
                h[dst] = h0[s] + w * (h[s] - h0[s])
                d[dst] = d0[s] + w * (d[s] - d0[s])
            u[dst] = u[fu[at]]
            v[dst] = v[fv[at]]
            qx[dst] = qu[at] * qx[fu[at]]
            qy[dst] = qv[at] * qy[fv[at]]


@njit
def quad_faces_done(active, slot, fu, fv, nhalo, u1, v1, qx1, qy1):
    for x in range(active.size):
        t = active[x]
        for m in range(nhalo):
            dst = t * STRIDE2 + slot[m]
            at = (t - 1) * nhalo + m
            u1[dst] = u1[fu[at]]
            qx1[dst] = qx1[fu[at]]
            v1[dst] = v1[fv[at]]
            qy1[dst] = qy1[fv[at]]


@njit
def iface_faces(
    rows_, dt, want_wave, om, h, d, u, v, mx, my, qx, qy, flx, frx, glx, grx, efx, cwx, ftabx, fly, fry, gly, gry, efy,
    cwy, ftaby, u1, v1, mx1, my1, qx1, qy1, wave, rows, g, dx, e_wet, h_cfl, u_max, lead, a_min, second, sheet, mirror,
):  # fmt: skip
    dist = F(1.5) * dx
    for n in range(rows_.shape[0]):
        t, side, coarse, base, step = rows_[n, 0], rows_[n, 1], rows_[n, 2], rows_[n, 5], rows_[n, 6]
        far = 1 if side >= 2 else 2
        for q in range(TILE):
            k = edge_face(t, side, q)
            fid = base + q * step
            if side % 2 == 0:
                w = face_step(
                    k, fid, dt, want_wave, om, 1, STRIDE, h, d, u, mx, qx, qy, v, flx, frx, glx, grx, efx, cwx, ftabx,
                    u1, mx1, qx1, rows, g, dx, e_wet, h_cfl, u_max, lead, a_min, second, sheet, mirror, dist, far,
                )  # fmt: skip
            else:
                w = face_step(
                    k, fid, dt, want_wave, om, STRIDE, 1, h, d, v, my, qy, qx, u, fly, fry, gly, gry, efy, cwy, ftaby,
                    v1, my1, qy1, rows, g, dx, e_wet, h_cfl, u_max, lead, a_min, second, sheet, mirror, dist, far,
                )  # fmt: skip
            if want_wave:
                wave[t] = max(wave[t], w)
                wave[coarse] = max(wave[coarse], w)


@njit
def iface_load(rows_, u1, v1, qx1, qy1):
    for n in range(rows_.shape[0]):
        side = rows_[n, 1]
        for c in range(HALF_TILE):
            f1 = edge_face(rows_[n, 0], side, 2 * c)
            f2 = edge_face(rows_[n, 0], side, 2 * c + 1)
            kc = edge_face(rows_[n, 2], side ^ 2, rows_[n, 4] + c)
            if side & 1:
                qy1[kc] = qy1[f1] + qy1[f2]
                v1[kc] = F(0.5) * (v1[f1] + v1[f2])
            else:
                qx1[kc] = qx1[f1] + qx1[f2]
                u1[kc] = F(0.5) * (u1[f1] + u1[f2])


@njit(inline="always")
def iface_sum(t, side, c, qx1, qy1, rr):
    s = STRIDE if side & 1 else 1
    q1 = qy1 if side & 1 else qx1
    f1 = edge_face(t, side, 2 * c)
    f2 = edge_face(t, side, 2 * c + 1)
    return scaled(q1[f1], rr[f1 - s], rr[f1]) + scaled(q1[f2], rr[f2 - s], rr[f2])


@njit
def iface_estimate(rows_, dt, qx1, qy1, rr, est, res, dx):
    for n in range(rows_.shape[0]):
        side = rows_[n, 1]
        for c in range(HALF_TILE):
            total = iface_sum(rows_[n, 0], side, c, qx1, qy1, rr)
            est[rows_[n, 3] * HALF_TILE + c] = total
            sign = F(-1.0) if side < 2 else F(1.0)
            res[edge_cell(rows_[n, 2], side, rows_[n, 4] + c)] += sign * dt * total / (F(4.0) * dx * dx)
            kc = edge_face(rows_[n, 2], side ^ 2, rows_[n, 4] + c)
            if side & 1:
                qy1[kc] = ZERO
            else:
                qx1[kc] = ZERO


@njit
def iface_flux(rows_, dt, qx1, qy1, rr, est, res, dx):
    for n in range(rows_.shape[0]):
        side = rows_[n, 1]
        for c in range(HALF_TILE):
            total = iface_sum(rows_[n, 0], side, c, qx1, qy1, rr)
            sign = F(-1.0) if side < 2 else F(1.0)
            owed = total - est[rows_[n, 3] * HALF_TILE + c]
            res[edge_cell(rows_[n, 2], side, rows_[n, 4] + c)] += sign * dt * owed / (F(4.0) * dx * dx)


@njit
def iface_store(rows_, qx1, qy1, rr, u1, v1, mx1, my1, u, v, mx, my, qx, qy):
    for n in range(rows_.shape[0]):
        side = rows_[n, 1]
        s = STRIDE if side & 1 else 1
        for q in range(TILE):
            k = edge_face(rows_[n, 0], side, q)
            qf = qy1[k] if side & 1 else qx1[k]
            qs = scaled(qf, rr[k - s], rr[k])
            if side == 2:
                u[k] = u1[k]
                mx[k] = mx1[k]
                qx[k] = qs
            if side == 3:
                v[k] = v1[k]
                my[k] = my1[k]
                qy[k] = qs
            if q & 1:
                continue
            f2 = edge_face(rows_[n, 0], side, q + 1)
            qf2 = qy1[f2] if side & 1 else qx1[f2]
            qs2 = scaled(qf2, rr[f2 - s], rr[f2])
            kc = edge_face(rows_[n, 2], side ^ 2, rows_[n, 4] + q // 2)
            if side & 1:
                qy[kc] = qs + qs2
                v[kc] = F(0.5) * (v1[k] + v1[f2])
            else:
                qx[kc] = qs + qs2
                u[kc] = F(0.5) * (u1[k] + u1[f2])
