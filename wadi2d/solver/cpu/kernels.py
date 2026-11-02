"""Numba twin of solver/gpu/kernels. Same statement order, same helper names, same float32 arithmetic.

The sections numbered [1] to [6] match faces.cu; parity tests hold the two together.
"""

from __future__ import annotations

import numpy as np
from numba import njit, prange

from wadi2d.solver.layout import HALO, STRIDE, STRIDE2, TILE, TILE2

F = np.float32
ZERO = F(0.0)
HALF = F(0.5)
ONE = F(1.0)


@njit(inline="always")
def minmod(a, b):
    if a * b <= ZERO:
        return ZERO
    return a if abs(a) < abs(b) else b


@njit(inline="always")
def ustar(uc, uup, udown, second):
    if not second:
        return uc
    return uc + HALF * minmod(uc - uup, udown - uc)


@njit(inline="always")
def gated(neighbour, own, mirror):
    """A neighbour face that carries nothing (dry or closed, u exactly 0) has no velocity to give: read this one instead."""
    return own if mirror and neighbour == ZERO else neighbour


@njit(inline="always")
def cell_level(hb, hc, tab, rows):
    if hc <= ZERO:
        return hb
    last = rows - 1
    if hb >= hc:
        return tab[last] + (hb - hc)
    s = F(np.sqrt(hb / hc)) * F(last)
    r = min(int(s), last - 1)
    return tab[r] + (s - F(r)) * (tab[r + 1] - tab[r])


@njit(inline="always")
def cell_plan(hb, hc, tab, rows):
    if hc <= ZERO or hb >= hc:
        return ONE
    last = rows - 1
    s = F(np.sqrt(hb / hc)) * F(last)
    r = min(int(s), last - 1)
    m = F(last)
    return hc * F(2 * r + 1) / (m * m) / max(tab[r + 1] - tab[r], F(1e-12))


@njit(inline="always")
def face_lookup(e, top, tab, rows):
    last = rows - 1
    m = F(last)
    if e >= top:
        a1 = tab[2 * last]
        a0 = tab[2 * last - 2]
        c = (m - ONE) / m
        w = (a1 - a0) / (top * (ONE - c * c))
        area = a1 + w * (e - top)
        return area, tab[2 * last + 1] * (area / max(a1, F(1e-12))), w
    s = F(np.sqrt(e / top)) * m
    r = min(int(s), last - 1)
    c0 = F(r) / m
    c1 = F(r + 1) / m
    e0 = c0 * c0 * top
    de = (c1 * c1 - c0 * c0) * top
    f = (e - e0) / de
    a0 = tab[2 * r]
    a1 = tab[2 * r + 2]
    t0 = tab[2 * r + 1]
    return a0 + f * (a1 - a0), t0 + f * (tab[2 * r + 3] - t0), (a1 - a0) / de


@njit
def face_step(
    k, fid, dt, want_wave, om, s, p, h, d, u, m, q, qp, vp, fl, fr, gl, gr, ef, cw, ftab, u1, m1, q1, rows, g, dx, e_wet,
    h_cfl, u_max, lead, a_min, second, sheet, mirror, dist=None, far=2,
):  # fmt: skip
    """One face: s is the array step along the normal, p across it. Returns the wave speed.

    ``dist`` is the distance between the two cell centres, ``dx`` unless given; ``far`` how far ahead second-order terms
    read, 1 on a face held in a halo entry.
    """
    span = dx if dist is None else dist
    e_l = d[k - s] - fl[fid]
    e_r = d[k] - fr[fid]
    uf = u[k]
    e_lp = max(e_l, ZERO)
    e_rp = max(e_r, ZERO)
    from_left = uf > ZERO or (uf == ZERO and e_l >= e_r)
    eup = e_lp if from_left else e_rp
    if eup <= e_wet:
        u1[k] = ZERO
        m1[k] = ZERO
        q1[k] = ZERO
        return ZERO
    start = 2 * rows * fid
    area, t, w = face_lookup(eup, ef[fid], ftab[start : start + 2 * rows], rows)
    h_l = h[k - s]
    h_r = h[k]
    hup = h_l if from_left else h_r

    # [1] section
    rho = ONE
    d_eta = e_rp - e_lp
    if sheet:
        avol = hup * dx
        edown = e_rp if from_left else e_lp
        if avol < area:
            sub = min(e_lp, e_rp) / max(e_lp, e_rp)
            sub2 = sub * sub
            alpha = sub2 * sub2
            rho = alpha + (ONE - alpha) * avol / area
        if edown <= ZERO:
            # [2] disconnected
            g_u = gl[fid] if from_left else gr[fid]
            g_d = gr[fid] if from_left else gl[fid]
            h_d = h_r if from_left else h_l
            drop = (hup - g_u) - max(h_d - g_d, HALF * (g_u - g_d))
            level_drop = abs(e_l - e_r)
            drive = max(eup, min(drop, level_drop))
            d_eta = -drive if from_left else drive

    # [3] momentum fluxes
    um = gated(u[k - s], uf, mirror)
    up = gated(u[k + s], uf, mirror)
    umm = gated(u[k - 2 * s], um, mirror)
    upp = gated(u[k + far * s], up, mirror)
    qc_l = HALF * (q[k - s] + q[k])
    qc_r = HALF * (q[k] + q[k + s])
    s_l = ustar(um, umm, uf, second) if qc_l > ZERO else ustar(uf, up, um, second)
    s_r = ustar(uf, um, up, second) if qc_r > ZERO else ustar(up, upp, uf, second)
    flux = qc_r * s_r - qc_l * s_l
    qy_s = HALF * (qp[k - s] + qp[k])
    qy_n = HALF * (qp[k - s + p] + qp[k + p])
    u_s = gated(u[k - p], uf, mirror)
    u_n = gated(u[k + p], uf, mirror)
    uss = gated(u[k - 2 * p], u_s, mirror)
    unn = gated(u[k + 2 * p], u_n, mirror)
    us_s = ustar(u_s, uss, uf, second) if qy_s > ZERO else ustar(uf, u_n, u_s, second)
    us_n = ustar(uf, u_s, u_n, second) if qy_n > ZERO else ustar(u_n, unn, uf, second)
    flux += qy_n * us_n - qy_s * us_s

    # [4] momentum and pressure
    abar = HALF * (h_l + h_r) * dx
    press = dt * g * d_eta / span
    if abar > F(1e-6) * dx:
        us = (m[k] - dt * flux / span) / abar - press
    else:
        us = uf - press

    # [5] friction
    vb = F(0.25) * (vp[k - s] + vp[k] + vp[k - s + p] + vp[k + p])
    t3 = t * t * t * F(np.cbrt(t))
    fric = area * area / max(t3, F(1e-30))
    if rho < ONE:
        fric = fric / max(rho * F(np.cbrt(rho)), F(1e-12))
    a = dt * g * fric
    sp = F(np.sqrt(us * us + vb * vb))
    un = F(2.0) * us / (ONE + F(np.sqrt(ONE + F(4.0) * a * sp)))
    if abs(un) > u_max:
        un = u_max if un > ZERO else -u_max

    # [6] crest face
    qn = area * rho * un
    c = cw[fid]
    if c != ZERO:
        area_c, w_c = area, w
        if c < ZERO:
            # a shaped object's crest may be resolved: the cell before the face has already spent its velocity head
            c = -c
            ua = um if from_left else up
            area_c, _t, w_c = face_lookup(eup + HALF * ua * ua / g, ef[fid], ftab[start : start + 2 * rows], rows)
        qc = c * area_c * F(np.sqrt(area_c / max(w_c, F(1e-9))))
        if abs(qn) > qc:
            qn = qc if qn > ZERO else -qc
            un = qn / max(area * rho, F(1e-12))
    u1[k] = un
    m1[k] = abar * un
    q1[k] = qn
    if not want_wave:
        return ZERO
    if not np.isfinite(un):
        return F(1e30)
    d_left = d[k - s]
    d_right = d[k]
    dup = d_left if from_left else d_right
    if dup <= h_cfl:
        return ZERO
    plan = om[k - s] if from_left else om[k]
    dother = d_right if from_left else d_left
    if dother > h_cfl:
        plan = min(plan, om[k] if from_left else om[k - s])
    wave = F(np.sqrt(max(g * area * rho / (max(plan, a_min) * dx), ZERO)))
    return abs(un) + min(lead * abs(un - uf), F(2.0) * wave) + wave


@njit(parallel=True)
def faces(
    active, dt, want_wave, om, h, d, u, v, mx, my, qx, qy, flx, frx, glx, grx, efx, cwx, ftabx, fly, fry, gly, gry, efy,
    cwy, ftaby, u1, v1, mx1, my1, qx1, qy1, wave, rows, g, dx, e_wet, h_cfl, u_max, lead, a_min, second, sheet, mirror,
):  # fmt: skip
    for a in prange(active.size):
        t = active[a]
        w = ZERO
        for j in range(TILE):
            for i in range(TILE):
                k = t * STRIDE2 + (j + HALO) * STRIDE + i + HALO
                fid = t * TILE2 + j * TILE + i
                wx = face_step(
                    k, fid, dt, want_wave, om, 1, STRIDE, h, d, u, mx, qx, qy, v, flx, frx, glx, grx, efx, cwx, ftabx,
                    u1, mx1, qx1, rows, g, dx, e_wet, h_cfl, u_max, lead, a_min, second, sheet, mirror,
                )  # fmt: skip
                wy = face_step(
                    k, fid, dt, want_wave, om, STRIDE, 1, h, d, v, my, qy, qx, u, fly, fry, gly, gry, efy, cwy, ftaby,
                    v1, my1, qy1, rows, g, dx, e_wet, h_cfl, u_max, lead, a_min, second, sheet, mirror,
                )  # fmt: skip
                w = max(w, max(wx, wy))
        if want_wave:
            wave[t] = w


@njit(parallel=True)
def limit(active, dt, h, qx1, qy1, r, dx):
    area = dx * dx
    for a in prange(active.size):
        t = active[a]
        for j in range(TILE):
            for i in range(TILE):
                k = t * STRIDE2 + (j + HALO) * STRIDE + i + HALO
                out = (
                    max(qx1[k + 1], ZERO)
                    + max(-qx1[k], ZERO)
                    + max(qy1[k + STRIDE], ZERO)
                    + max(-qy1[k], ZERO)
                )
                have = max(h[k], ZERO) * area
                r[k] = have / (out * dt) if out * dt > have else ONE


@njit(inline="always")
def scaled(q, rl, rr):
    return q * (rl if q > ZERO else rr)


@njit(parallel=True)
def update(active, dt, want_plan, debt, res, om, qx1, qy1, r, src, hc, dtab, h, d, qx, qy, wet, rows, dx):
    area = dx * dx
    for a in prange(active.size):
        t = active[a]
        any_wet = 0
        for j in range(TILE):
            for i in range(TILE):
                k = t * STRIDE2 + (j + HALO) * STRIDE + i + HALO
                fid = t * TILE2 + j * TILE + i
                rc = r[k]
                qw = scaled(qx1[k], r[k - 1], rc)
                qe = scaled(qx1[k + 1], rc, r[k + 1])
                qn = scaled(qy1[k], r[k - STRIDE], rc)
                qs = scaled(qy1[k + STRIDE], rc, r[k + STRIDE])
                qx[k] = qw
                qy[k] = qn
                h0 = h[k]
                inc = res[k] + dt * src[k] - dt * (qe - qw + qs - qn) / area
                total = h0 + inc
                hn = max(total, ZERO)
                res[k] = inc - (total - h0) if total > ZERO else (total if debt else ZERO)
                h[k] = hn
                tab = dtab[rows * fid : rows * (fid + 1)]
                d[k] = cell_level(hn, hc[fid], tab, rows)
                if want_plan:
                    om[k] = cell_plan(hn, hc[fid], tab, rows)
                if hn > ZERO:
                    any_wet = 1
        wet[t] = any_wet


@njit
def exchange(active, slot, src, nhalo, a):
    for n in range(active.size):
        t = active[n]
        for m in range(nhalo):
            a[t * STRIDE2 + slot[m]] = a[src[(t - 1) * nhalo + m]]


@njit
def boundary(cell, ref, kind, d0, h0, h, d):
    for m in range(cell.size):
        k = cell[m]
        if kind[m] == 0:
            h[k] = h0[m]
            d[k] = d0[m]
        elif kind[m] == 1:
            h[k] = ZERO
            d[k] = ZERO
        else:
            h[k] = h[ref[m]]
            d[k] = max(d[ref[m]] + d0[m], ZERO)
