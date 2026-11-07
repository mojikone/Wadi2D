# Wadi2D. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The polygon step on the CPU: decision 19's scheme on any cells and faces, in the lattice kernel's order (W45).

Ported from the W3 prototype (`W3 breakline faces test/graph.py`, `gstep`), which proved it on 1,035 channel runs and
reduces to the production rule on a square lattice. The same unknowns as the lattice: mean depth per cell, normal
velocity, momentum and discharge per face, implicit friction, sub-grid tables on cells and faces, the same [1] to [6]
order. What a general polygon adds:

* the level gradient: ``dEta = eR - eL - s . G``, with ``G`` the Green-Gauss cell gradient of the face level differences,
  so still water has ``G = 0`` exactly and no absolute level enters;
* advection: a cell momentum vector from its faces (Perot), ``V U = sum (xf - c) Q_out``; a rate per cell
  ``R = sum Q_out U_upwind``; a face reads ``flux = n . (R_L + R_R) / 2``; uniform flow has ``R = 0`` on any polygon;
* the friction speed takes the transverse velocity from the cell vectors;
* the crest cap on the energy head takes the upstream cell's velocity with this face's own flow left out (W43);
* the time step per face: ``(|u| + min(lead |du|, 2c) + c) / dn``, ``c^2 = g A rho dn / max(plan Ac, a_min dx^2)``.

The cell list may end in ghost entries: tile cells a strip touches, whose state the hybrid stepper mirrors each step
and whose lattice faces it adds to the sums before the face loops run (:mod:`wadi2d.strips.hybrid`). The sums here
never zero their arrays, so a prefill survives; ``nreal`` cells are updated, the ghosts are not.

Loops over face and cell lists, each statement as the CUDA kernels will carry it: the twin of the strip path.
"""

from __future__ import annotations

import numpy as np
from numba import njit

from wadi2d.solver.cpu.kernels import cell_level, cell_plan, face_lookup

F = np.float32
ZERO, ONE, HALF, TWO = F(0.0), F(1.0), F(0.5), F(2.0)


@njit(cache=True)
def perot_velocity(nf, nc, L, R, xf, yf, cx, cy, q, h, area, Ux, Uy) -> None:
    """[3a] Perot cell momentum vectors from the face discharges, added to what the arrays hold (zero, or a
    ghost's lattice sums), then divided by the cell volume."""
    for f in range(nf):
        qf = q[f]
        if qf != ZERO:
            a, b = L[f], R[f]
            Ux[a] += (xf[f] - cx[a]) * qf
            Uy[a] += (yf[f] - cy[a]) * qf
            Ux[b] -= (xf[f] - cx[b]) * qf
            Uy[b] -= (yf[f] - cy[b]) * qf
    for c in range(nc):
        vol = h[c] * area[c]
        if vol > F(1e-9):
            Ux[c] /= vol
            Uy[c] /= vol
        else:
            Ux[c] = ZERO
            Uy[c] = ZERO


@njit(cache=True)
def advection_rate(nf, L, R, q, Ux, Uy, Rx, Ry) -> None:
    """[3a] The advection rate per cell, sum of outflow times the upwind cell's velocity, added to what the arrays
    hold (zero, or a ghost's lattice part)."""
    for f in range(nf):
        qf = q[f]
        if qf != ZERO:
            a, b = L[f], R[f]
            up = a if qf > ZERO else b
            Rx[a] += qf * Ux[up]
            Ry[a] += qf * Uy[up]
            Rx[b] -= qf * Ux[up]
            Ry[b] -= qf * Uy[up]


@njit(cache=True)
def level_gradients(nf, nc, L, R, ln, nfx, nfy, fl, fr, h, d, area, e_wet, Gx, Gy, Dl) -> None:
    """[3b] Green-Gauss cell gradient of the face level differences, added to what the arrays hold and then divided by
    the cell area; closed and dry faces contribute nothing."""
    for f in range(nf):
        a, b = L[f], R[f]
        e_l = d[a] - fl[f]
        e_r = d[b] - fr[f]
        if e_l > e_wet and e_r > e_wet and h[a] > ZERO and h[b] > ZERO:
            de = e_r - e_l
            Dl[f] = de
            w = HALF * de * ln[f]
            Gx[a] += w * nfx[f]
            Gy[a] += w * nfy[f]
            Gx[b] += w * nfx[f]
            Gy[b] += w * nfy[f]
        else:
            Dl[f] = ZERO
    for c in range(nc):
        Gx[c] /= area[c]
        Gy[c] /= area[c]


@njit(cache=True)
def faces(
    nf, dt, want_wave, L, R, ln, nfx, nfy, xf, yf, dn, sx, sy, fl, fr, gl, gr, ef, cw, ftab, area, cx, cy,
    h, d, om, u, m, q, Ux, Uy, Rx, Ry, Gx, Gy, Dl, u1, m1, q1,
    rows, g, dx, e_wet, h_cfl, u_max, lead, a_min, sheet, skew,
):  # fmt: skip
    """[1] to [6] on every face; returns the largest wave frequency when asked, else 0."""
    freq = ZERO
    for f in range(nf):
        a, b = L[f], R[f]
        e_l = d[a] - fl[f]
        e_r = d[b] - fr[f]
        uf = u[f]
        e_lp = max(e_l, ZERO)
        e_rp = max(e_r, ZERO)
        from_left = uf > ZERO or (uf == ZERO and e_l >= e_r)
        eup = e_lp if from_left else e_rp
        if eup <= e_wet:
            u1[f] = ZERO
            m1[f] = ZERO
            q1[f] = ZERO
            continue
        start = 2 * rows * f
        A, T, W = face_lookup(eup, ef[f], ftab[start : start + 2 * rows], rows)
        dnf = dn[f]
        v_l = h[a] * area[a]
        v_r = h[b] * area[b]
        hup = h[a] if from_left else h[b]
        # [1] section: thin flow on a slope spreads over the cell; the limit fades as the downstream side fills
        rho = ONE
        d_eta = e_rp - e_lp
        if skew and Dl[f] != ZERO:
            d_eta -= HALF * ((Gx[a] + Gx[b]) * sx[f] + (Gy[a] + Gy[b]) * sy[f])
        if sheet:
            avol = hup * ln[f]
            edown = e_rp if from_left else e_lp
            if avol < A:
                s = min(e_lp, e_rp) / max(e_lp, e_rp)
                s2 = s * s
                alpha = s2 * s2
                rho = alpha + (ONE - alpha) * avol / A
            if edown <= ZERO:
                # [2] disconnected: the driver is the mean-surface drop, clipped at the crest
                g_u = gl[f] if from_left else gr[f]
                g_d = gr[f] if from_left else gl[f]
                h_d = h[b] if from_left else h[a]
                drop = (hup - g_u) - max(h_d - g_d, HALF * (g_u - g_d))
                level_drop = e_l - e_r if e_l > e_r else e_r - e_l
                drive = max(eup, min(drop, level_drop))
                d_eta = -drive if from_left else drive
        # [3] advection from the cell vectors, [4] momentum and pressure
        abar = HALF * (v_l + v_r) / dnf
        press = dt * g * d_eta / dnf
        if abar > F(1e-6) * dx:
            flux = HALF * (nfx[f] * (Rx[a] + Rx[b]) + nfy[f] * (Ry[a] + Ry[b]))
            us = (m[f] - dt * flux / dnf) / abar - press
        else:
            us = uf - press
        # [5] friction, implicit in the speed, with the transverse velocity from the cell vectors
        tx, ty = -nfy[f], nfx[f]
        wa = ONE if v_l > F(1e-9) else ZERO
        wb = ONE if v_r > F(1e-9) else ZERO
        vb = ZERO
        if wa + wb > ZERO:
            vb = (wa * (Ux[a] * tx + Uy[a] * ty) + wb * (Ux[b] * tx + Uy[b] * ty)) / (wa + wb)
        T3 = T * T * T * F(np.cbrt(T))
        fric = A * A / max(T3, F(1e-30))
        if rho < ONE:
            fric = fric / max(rho * F(np.cbrt(rho)), F(1e-12))
        aa = dt * g * fric
        sp = F(np.sqrt(us * us + vb * vb))
        un = TWO * us / (ONE + F(np.sqrt(ONE + F(4.0) * aa * sp)))
        if abs(un) > u_max:
            un = u_max if un > ZERO else -u_max
        # [6] crest face: at most critical flow over the crest for this head
        qn = A * rho * un
        c = cw[f]
        if c != ZERO:
            Ac, Wc = A, W
            if c < ZERO:
                # the energy head of the upstream cell, this face's own flow left out of its velocity (W43)
                c = -c
                up = a if from_left else b
                vup = v_l if from_left else v_r
                sign = ONE if from_left else -ONE
                ux, uy = Ux[up], Uy[up]
                if vup > F(1e-9):
                    ux -= sign * (xf[f] - cx[up]) * q[f] / vup
                    uy -= sign * (yf[f] - cy[up]) * q[f] / vup
                Ac, _tc, Wc = face_lookup(eup + HALF * (ux * ux + uy * uy) / g, ef[f], ftab[start : start + 2 * rows], rows)
            qc = c * Ac * F(np.sqrt(Ac / max(Wc, F(1e-9))))
            if abs(qn) > qc:
                qn = qc if qn > ZERO else -qc
                un = qn / max(A * rho, F(1e-12))
        u1[f] = un
        m1[f] = abar * un
        q1[f] = qn
        if want_wave:
            if not np.isfinite(un):
                return F(1e30)
            dup = d[a] if from_left else d[b]
            if dup > h_cfl:
                up_c = a if from_left else b
                dn_c = b if from_left else a
                wet_plan = om[up_c] * area[up_c]
                if d[dn_c] > h_cfl:
                    wet_plan = min(wet_plan, om[dn_c] * area[dn_c])
                wave = F(np.sqrt(max(g * A * rho * dnf / max(wet_plan, a_min * dx * dx), ZERO)))
                fr_ = (abs(un) + min(lead * abs(un - uf), TWO * wave) + wave) / dnf
                freq = max(freq, fr_)
    return freq


@njit(cache=True)
def outflows(nf, nc, L, R, q1, out) -> None:
    """What each cell would give out through its faces this step, before positivity."""
    for c in range(nc):
        out[c] = ZERO
    for f in range(nf):
        qf = q1[f]
        if qf > ZERO:
            out[L[f]] += qf
        elif qf < ZERO:
            out[R[f]] -= qf


@njit(cache=True)
def positivity(nreal, dt, h, area, out, r) -> None:
    """A real cell gives at most what it holds; a ghost's ratio is the hybrid stepper's and stays."""
    for c in range(nreal):
        have = max(h[c], ZERO) * area[c]
        o = out[c]
        r[c] = have / (o * dt) if o * dt > have else ONE


@njit(cache=True)
def update(nf, nc, nreal, dt, want_wave, L, R, area, hc, dtab, q1, r, src, div, h, d, om, q, rows) -> None:
    """The scaled discharges, the divergence of every cell, the new depth, level and wet share of the real ones."""
    for c in range(nc):
        div[c] = ZERO
    for f in range(nf):
        qf = q1[f]
        a, b = L[f], R[f]
        qf = qf * (r[a] if qf > ZERO else r[b])
        q[f] = qf
        div[a] += qf
        div[b] -= qf
    for c in range(nreal):
        hn = max(h[c] + dt * src[c] - dt * div[c] / area[c], ZERO)
        h[c] = hn
        tab = dtab[rows * c : rows * (c + 1)]
        d[c] = cell_level(hn, hc[c], tab, rows)
        if want_wave:
            om[c] = cell_plan(hn, hc[c], tab, rows)


@njit(cache=True)
def boundary(bcell, bd0, bh0, h, d) -> None:
    for n in range(bcell.size):
        k = bcell[n]
        h[k] = bh0[n]
        d[k] = bd0[n]
