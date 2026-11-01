"""Throwaway prototype: explicit staggered (C-grid) shallow-water scheme with sub-grid tables.

Purpose: decide the discrete scheme by measurement before writing the tiled GPU kernels. Plain (ny, nx)
arrays, Numba, float64 for clarity. Cell state: mean depth hbar = V / dx^2. Face state: momentum M and
velocity u. Tables: cell level above zmin as a function of hbar; face area A and conveyance K as functions
of the depth e above the face invert. Levels never enter as absolute numbers: faces carry invert heights
over each neighbour's zmin, so e_L, e_R and their difference are local.

Momentum is updated in conservative form (M = Abar u), because the velocity form converges to the wrong
shock speed (measured: Stoker plateau 5.009 m against 5.079 m at every dx).
"""
from __future__ import annotations

import numpy as np
from numba import njit

G = 9.80665
ROWS = 16


# ---------------------------------------------------------------- tables
def quad_grid(top: float, rows: int = ROWS) -> np.ndarray:
    """Quadratic spacing 0..top: fine rows near the bottom, where the geometry bites."""
    return top * (np.arange(rows) / (rows - 1)) ** 2


def build_cell_tables(zs: np.ndarray, k: int, rows: int = ROWS):
    """zs: sub-grid bed (ny*k, nx*k). Returns zmin, zmean, H (top of the hbar axis), dtab[ny, nx, rows]."""
    ny, nx = zs.shape[0] // k, zs.shape[1] // k
    zmin = np.zeros((ny, nx))
    zmean = np.zeros((ny, nx))
    H = np.zeros((ny, nx))
    dtab = np.zeros((ny, nx, rows))
    for j in range(ny):
        for i in range(nx):
            p = np.sort(zs[j * k : (j + 1) * k, i * k : (i + 1) * k].ravel())
            zmin[j, i] = p[0]
            zmean[j, i] = p.mean()
            rel = p - p[0]
            top = rel[-1]
            H[j, i] = rel[-1] - rel.mean()  # hbar when the level reaches the highest sample
            if H[j, i] <= 1e-9:
                H[j, i] = 0.0
                dtab[j, i] = 0.0
                continue
            hb = quad_grid(H[j, i], rows)
            cum = np.cumsum(rel)
            n = rel.size
            ks = np.arange(1, n + 1)
            hbar_at = (rel * ks - cum) / n  # hbar when level = rel[m]
            idx = np.clip(np.searchsorted(hbar_at, hb, side="right") - 1, 0, n - 1)
            frac_area = (idx + 1) / n
            dtab[j, i] = rel[idx] + (hb - hbar_at[idx]) / frac_area
            dtab[j, i, -1] = top
    return zmin, zmean, H, dtab


def build_face_tables(zprof: np.ndarray, p: float, n: float, emax: float, emin: float = 8.0, rows: int = ROWS):
    """zprof: (nfaces, m) along-face ground. Returns zf, E, Atab, Ktab."""
    nf, m = zprof.shape
    zf = zprof.min(axis=1)
    rel = zprof - zf[:, None]
    E = np.maximum(np.minimum(rel.max(axis=1), emax), emin)
    Atab = np.zeros((nf, rows))
    Ktab = np.zeros((nf, rows))
    for f in range(nf):
        e = quad_grid(E[f], rows)
        dep = np.maximum(e[:, None] - rel[f][None, :], 0.0)
        Atab[f] = p * dep.sum(axis=1)
        Ktab[f] = ((p / n) * (dep ** (5.0 / 3.0)).sum(axis=1)) ** 0.6
    return zf, E, Atab, Ktab


@njit(cache=False)
def level_from_hbar(hb: float, H: float, tab: np.ndarray) -> float:
    if H <= 0.0:
        return hb
    if hb >= H:
        return tab[-1] + (hb - H)
    s = np.sqrt(hb / H) * (tab.size - 1)
    k = int(s)
    f = s - k
    return tab[k] + f * (tab[k + 1] - tab[k])


@njit(cache=False)
def face_lookup(e: float, E: float, A: np.ndarray, K: np.ndarray):
    """Area and conveyance at depth e over the face invert; linear in e inside, prismatic growth above."""
    rows = A.size
    m = rows - 1
    if e >= E:
        Wtop = (A[m] - A[m - 1]) / (E * (1.0 - ((m - 1.0) / m) ** 2))
        At = A[m] + Wtop * (e - E)
        return At, (K[m] * (At / max(A[m], 1e-12))) ** (5.0 / 3.0)
    s = np.sqrt(e / E) * m
    k = int(s)
    ek = (k / m) ** 2 * E
    ek1 = ((k + 1.0) / m) ** 2 * E
    f = (e - ek) / (ek1 - ek)
    return A[k] + f * (A[k + 1] - A[k]), (K[k] + f * (K[k + 1] - K[k])) ** (5.0 / 3.0)


@njit(cache=False)
def face_width(e: float, E: float, A: np.ndarray) -> float:
    """Wet width: slope of the area table at depth e."""
    m = A.size - 1
    if e >= E:
        return (A[m] - A[m - 1]) / (E * (1.0 - ((m - 1.0) / m) ** 2))
    k = int(np.sqrt(e / E) * m)
    return (A[k + 1] - A[k]) / (E * (((k + 1.0) / m) ** 2 - (k / m) ** 2))


@njit(cache=False)
def minmod(a: float, b: float) -> float:
    if a * b <= 0.0:
        return 0.0
    return a if abs(a) < abs(b) else b


@njit(cache=False)
def ustar(uc: float, uup: float, udown: float, second: bool) -> float:
    """Velocity at a cell centre from the upwind face uc, with a limited second-order correction."""
    if not second:
        return uc
    return uc + 0.5 * minmod(uc - uup, udown - uc)


@njit(cache=False)
def sweep(
    h, d, u, M, Q, Qp, vp,
    zmin, zmean, fL, fR, E, Atab, Ktab, cw, gL, gR,
    u_new, M_new, Q_new,
    dt, dx, second, sheet, eps_e, h_cfl, u_cap, use_energy, adv_on, fr_lim, phi_mode, phi0,
):
    """Momentum update of the faces normal to axis 1. u, M, Q have shape (n0, n1 + 1); Qp is the
    transverse face discharge, shape (n0 + 1, n1)."""
    n0, n1 = h.shape
    wave = 0.0
    for j in range(n0):
        for i in range(1, n1):
            eL = d[j, i - 1] - fL[j, i]
            eR = d[j, i] - fR[j, i]
            uf = u[j, i]
            eLp, eRp = max(eL, 0.0), max(eR, 0.0)
            if uf > 0.0 or (uf == 0.0 and eL >= eR):
                eup, edown, hup, up, dn = eLp, eRp, h[j, i - 1], i - 1, i
            else:
                eup, edown, hup, up, dn = eRp, eLp, h[j, i], i, i - 1
            if eup <= eps_e:
                u_new[j, i] = 0.0
                M_new[j, i] = 0.0
                Q_new[j, i] = 0.0
                continue
            A, K = face_lookup(eup, E[j, i], Atab[j, i], Ktab[j, i])
            rho = 1.0
            if sheet:
                Avol = hup * dx
                if Avol < A:
                    rho = Avol / A
            F = (A / max(K, 1e-30)) ** 2 * rho ** (-4.0 / 3.0)
            dEta = eRp - eLp
            if sheet and edown <= 0.0:
                etaU = zmean[j, up] + h[j, up]
                etaD = zmean[j, dn] + h[j, dn]
                zinv = zmin[j, i - 1] + fL[j, i]
                clip = max(etaD, zinv - 0.5 * (zmean[j, up] - zmean[j, dn]))
                drive = max(eup, etaU - clip)
                dEta = -drive if up == i - 1 else drive
            Abar = 0.5 * (h[j, i - 1] + h[j, i]) * dx
            phi = min(A / (dx * max(eup, 1e-9)), 1.0)
            closed_along = False
            closed_trans = False
            if phi_mode == 3:
                # a wet neighbour cell whose far face stands above its level: flow must turn there
                if i < n1 - 1 and h[j, i] > 0.0 and d[j, i] - fL[j, i + 1] <= 0.0:
                    closed_along = True
                if i > 1 and h[j, i - 1] > 0.0 and d[j, i - 1] - fR[j, i - 1] <= 0.0:
                    closed_along = True
                for c in (i - 1, i):
                    if d[j, c] - gR[j, c] <= 0.0 and h[j, c] > 0.0:
                        closed_trans = True
                    if d[j, c] - gL[j + 1, c] <= 0.0 and h[j, c] > 0.0:
                        closed_trans = True
            flux = 0.0
            energy = False
            adv_e = 0.0
            adv_t = 0.0
            if 1 < i < n1 - 1:
                QcL = 0.5 * (Q[j, i - 1] + Q[j, i])
                QcR = 0.5 * (Q[j, i] + Q[j, i + 1])
                if QcL > 0.0:
                    sL = ustar(u[j, i - 1], u[j, i - 2], uf, second)
                else:
                    sL = ustar(uf, u[j, i + 1], u[j, i - 1], second)
                if QcR > 0.0:
                    sR = ustar(uf, u[j, i - 1], u[j, i + 1], second)
                else:
                    sR = ustar(u[j, i + 1], u[j, i + 2], uf, second)
                flux = (QcR * sR - QcL * sL) / dx
                if use_energy:
                    # upstream face along the flow
                    uu = u[j, i - 1] if uf >= 0.0 else u[j, i + 1]
                    same = uu * uf >= 0.0
                    grow = abs(uf) > abs(uu)
                    fr2 = uf * uf / max(G * max(d[j, up], 1e-6), 1e-9)
                    if same and (grow or fr2 < fr_lim * fr_lim):
                        energy = True
                        adv_e = (uf * uf - uu * uu) / (2.0 * dx) * (1.0 if uf >= 0.0 else -1.0)
            if 0 < j < n0 - 1:
                QyS = 0.5 * (Qp[j, i - 1] + Qp[j, i])
                QyN = 0.5 * (Qp[j + 1, i - 1] + Qp[j + 1, i])
                if 1 < j < n0 - 2:
                    usS = ustar(u[j - 1, i], u[j - 2, i], uf, second) if QyS > 0.0 else ustar(uf, u[j + 1, i], u[j - 1, i], second)
                    usN = ustar(uf, u[j - 1, i], u[j + 1, i], second) if QyN > 0.0 else ustar(u[j + 1, i], u[j + 2, i], uf, second)
                else:
                    usS = u[j - 1, i] if QyS > 0.0 else uf
                    usN = uf if QyN > 0.0 else u[j + 1, i]
                if phi_mode == 1:
                    QyN *= phi
                    QyS *= phi
                if not closed_trans:
                    flux += (QyN * usN - QyS * usS) / dx
                if Abar > 1e-6 * dx and not closed_trans:
                    adv_t = (QyN * (usN - uf) - QyS * (usS - uf)) / (Abar * dx)
            if not adv_on or (phi_mode == 2 and phi < 0.999):
                us = uf - dt * G * dEta / dx
            elif closed_along:
                us = uf - dt * (adv_t + G * dEta / dx)
            elif energy:
                us = uf - dt * (adv_e + adv_t + G * dEta / dx)
            elif Abar > 1e-6 * dx:
                us = (M[j, i] - dt * flux) / Abar - dt * G * dEta / dx
            else:
                us = uf - dt * G * dEta / dx
            vb = 0.25 * (vp[j, i - 1] + vp[j, i] + vp[j + 1, i - 1] + vp[j + 1, i])
            if phi_mode == 4:
                psi = min(max((phi - phi0) / (1.0 - phi0 - 0.05), 0.0), 1.0)
                us = psi * us + (1.0 - psi) * (uf - dt * G * dEta / dx)
            a = dt * G * F
            sp = np.sqrt(us * us + vb * vb)
            un = 2.0 * us / (1.0 + np.sqrt(1.0 + 4.0 * a * sp)) if a > 0.0 else us
            if abs(un) > u_cap:
                un = u_cap if un > 0.0 else -u_cap
            q = A * rho * un
            if cw[j, i] > 0.0:
                # crest face: discharge cannot exceed the critical flow over the crest for this head
                w_top = face_width(eup, E[j, i], Atab[j, i])
                dh = A / max(w_top, 1e-9)
                qc = cw[j, i] * A * np.sqrt(dh)
                if abs(q) > qc:
                    q = qc if q > 0.0 else -qc
                    un = q / max(A * rho, 1e-12)
            u_new[j, i] = un
            M_new[j, i] = Abar * un
            Q_new[j, i] = q
            if d[j, up] > h_cfl:
                wave = max(wave, abs(un) + np.sqrt(G * d[j, up]))
    return wave


@njit(cache=False)
def cells(h, d, Qx, Qy, H, dtab, src, dt, dx):
    ny, nx = h.shape
    area = dx * dx
    r = np.ones((ny, nx))
    for j in range(ny):
        for i in range(nx):
            out = (
                max(Qx[j, i + 1], 0.0)
                + max(-Qx[j, i], 0.0)
                + max(Qy[j + 1, i], 0.0)
                + max(-Qy[j, i], 0.0)
            )
            have = max(h[j, i], 0.0) * area
            if out * dt > have:
                r[j, i] = have / (out * dt)
    for j in range(ny):
        for i in range(1, nx):
            q = Qx[j, i]
            f = r[j, i - 1] if q > 0.0 else r[j, i]
            if f < 1.0:
                Qx[j, i] = q * f
    for j in range(1, ny):
        for i in range(nx):
            q = Qy[j, i]
            f = r[j - 1, i] if q > 0.0 else r[j, i]
            if f < 1.0:
                Qy[j, i] = q * f
    for j in range(ny):
        for i in range(nx):
            div = Qx[j, i + 1] - Qx[j, i] + Qy[j + 1, i] - Qy[j, i]
            h[j, i] = max(h[j, i] - dt * div / area + dt * src[j, i], 0.0)
            d[j, i] = level_from_hbar(h[j, i], H[j, i], dtab[j, i])


class Model:
    """Bed given as sub-grid samples (ny*k, nx*k); n Manning; dx cell size."""

    def __init__(
        self, zs, k, dx, n, emax=16.0, second=True, sheet=True, eps_e=1e-4, cfl=0.45, h_cfl=1e-2,
        u_cap=30.0, use_energy=True, crest_tol=0.05, adv_on=True, fr_lim=0.0, phi_mode=0, phi0=0.6,
    ):
        self.dx, self.k, self.second, self.sheet, self.eps_e, self.cfl = dx, k, second, sheet, eps_e, cfl
        self.h_cfl, self.u_cap, self.use_energy = h_cfl, u_cap, use_energy
        self.adv_on = adv_on
        self.fr_lim = fr_lim
        self.phi_mode = phi_mode
        self.phi0 = phi0
        ny, nx = zs.shape[0] // k, zs.shape[1] // k
        self.ny, self.nx = ny, nx
        self.zmin, self.zmean, self.H, self.dtab = build_cell_tables(zs, k)
        p = dx / k
        prof_x = np.zeros((ny * (nx + 1), k))
        for j in range(ny):
            for i in range(nx + 1):
                a = zs[j * k : (j + 1) * k, max(i * k - 1, 0)]
                b = zs[j * k : (j + 1) * k, min(i * k, zs.shape[1] - 1)]
                prof_x[j * (nx + 1) + i] = np.maximum(a, b)
        zf, E, A, K = build_face_tables(prof_x, p, n, emax)
        self.Ax, self.Kx, self.Ex = A.reshape(ny, nx + 1, ROWS), K.reshape(ny, nx + 1, ROWS), E.reshape(ny, nx + 1)
        zf = zf.reshape(ny, nx + 1)
        self.zfx = zf
        self.fxL = np.zeros_like(zf)
        self.fxR = np.zeros_like(zf)
        self.fxL[:, 1:] = zf[:, 1:] - self.zmin
        self.fxR[:, :-1] = zf[:, :-1] - self.zmin
        prof_y = np.zeros(((ny + 1) * nx, k))
        for j in range(ny + 1):
            for i in range(nx):
                a = zs[max(j * k - 1, 0), i * k : (i + 1) * k]
                b = zs[min(j * k, zs.shape[0] - 1), i * k : (i + 1) * k]
                prof_y[j * nx + i] = np.maximum(a, b)
        zf, E, A, K = build_face_tables(prof_y, p, n, emax)
        self.Ay, self.Ky, self.Ey = A.reshape(ny + 1, nx, ROWS), K.reshape(ny + 1, nx, ROWS), E.reshape(ny + 1, nx)
        zf = zf.reshape(ny + 1, nx)
        self.zfy = zf
        self.fyL = np.zeros_like(zf)
        self.fyR = np.zeros_like(zf)
        self.fyL[1:, :] = zf[1:, :] - self.zmin
        self.fyR[:-1, :] = zf[:-1, :] - self.zmin
        # crest faces: the lowest point of the face stands above the mean bed of both neighbours
        cw0 = (2.0 / 3.0) * np.sqrt(2.0 * G / 3.0)
        self.Cx = np.zeros_like(self.zfx)
        self.Cy = np.zeros_like(self.zfy)
        zm = self.zmean
        self.Cx[:, 1:-1] = cw0 * ((self.zfx[:, 1:-1] > zm[:, :-1] + crest_tol) & (self.zfx[:, 1:-1] > zm[:, 1:] + crest_tol))
        self.Cy[1:-1, :] = cw0 * ((self.zfy[1:-1, :] > zm[:-1, :] + crest_tol) & (self.zfy[1:-1, :] > zm[1:, :] + crest_tol))
        self.h = np.zeros((ny, nx))
        self.d = np.zeros((ny, nx))
        self.u = np.zeros((ny, nx + 1))
        self.v = np.zeros((ny + 1, nx))
        self.Qx = np.zeros((ny, nx + 1))
        self.Qy = np.zeros((ny + 1, nx))
        self.Mx = np.zeros((ny, nx + 1))
        self.My = np.zeros((ny + 1, nx))
        self.src = np.zeros((ny, nx))
        self.t = 0.0
        self.dt = 0.01
        self.nsteps = 0

    def set_hbar(self, hb):
        self.h[:] = hb
        for j in range(self.ny):
            for i in range(self.nx):
                self.d[j, i] = level_from_hbar(self.h[j, i], self.H[j, i], self.dtab[j, i])

    def run(self, t_end, dtmax=5.0, on_step=None):
        ux, vy, mx, my, qx, qy = (np.zeros_like(a) for a in (self.u, self.v, self.Mx, self.My, self.Qx, self.Qy))
        args = (self.second, self.sheet, self.eps_e, self.h_cfl, self.u_cap, self.use_energy, self.adv_on, self.fr_lim, self.phi_mode, self.phi0)
        while self.t < t_end - 1e-9:
            dt = min(self.dt, t_end - self.t, dtmax)
            w1 = sweep(
                self.h, self.d, self.u, self.Mx, self.Qx, self.Qy, self.v,
                self.zmin, self.zmean, self.fxL, self.fxR, self.Ex, self.Ax, self.Kx, self.Cx, self.fyL, self.fyR,
                ux, mx, qx, dt, self.dx, *args,
            )
            w2 = sweep(
                self.h.T, self.d.T, self.v.T, self.My.T, self.Qy.T, self.Qx.T, self.u.T,
                self.zmin.T, self.zmean.T, self.fyL.T, self.fyR.T, self.Ey.T,
                self.Ay.transpose(1, 0, 2), self.Ky.transpose(1, 0, 2), self.Cy.T, self.fxL.T, self.fxR.T,
                vy.T, my.T, qy.T, dt, self.dx, *args,
            )
            self.u[:], self.v[:], self.Mx[:], self.My[:], self.Qx[:], self.Qy[:] = ux, vy, mx, my, qx, qy
            cells(self.h, self.d, self.Qx, self.Qy, self.H, self.dtab, self.src, dt, self.dx)
            self.t += dt
            self.nsteps += 1
            self.dt = self.cfl * self.dx / max(max(w1, w2), 1e-3)
            if on_step is not None:
                on_step(self)
