"""Option (a) and the lattice options (d): the production kernels on plain padded arrays, float64.

Port of wadi2d/solver/cpu/kernels.py (read, not imported), same statement order, same section numbers [1]..[6]. Differences:
one (ny+4, nx+4) array instead of tiles, float64 instead of float32, no active-tile list (a dry cell returns at once), no
residual compensation (float64 does not need it). `Fix` flags switch the candidate kernel changes of option (d); with all flags 0 the
kernel is the baseline.

Index: k = (j + HALO) * STRIDE + (i + HALO). u[k] is the west face of cell k, v[k] its north face (rows grow south, as in production).
"""
from __future__ import annotations

import numpy as np
from numba import njit

G = 9.80665
ROWS = 16
HALO = 2
CLOSED = 1.0e9
CW = 1.7046
EPS_RELIEF = 1e-9


@njit
def cell_table(z, rows, tab):
    p = np.sort(z.ravel())
    n = p.size
    zmin = p[0]
    rel = p - zmin
    relmean = float(rel.mean())
    hc = float(rel[-1]) - relmean
    if hc <= EPS_RELIEF:
        tab[:] = 0.0
        return float(zmin), relmean, 0.0
    cum = 0.0
    hbar_at = np.empty(n)
    for m in range(n):
        cum += rel[m]
        hbar_at[m] = (rel[m] * (m + 1) - cum) / n
    last = rows - 1
    m = 0
    for r in range(rows):
        hb = hc * (r / last) ** 2
        while m + 1 < n and hbar_at[m + 1] <= hb:
            m += 1
        tab[r] = rel[m] + (hb - hbar_at[m]) * n / (m + 1)
    tab[last] = rel[-1]
    return float(zmin), relmean, hc


@njit
def face_table(prof, crest, pixel, n_inv, length, e_lo, e_hi, tab):
    """tab is (rows, 2): area, K^(3/5). Returns invert and table top. `pixel` is the length of one sample."""
    m = prof.size
    if not np.isnan(crest):
        prof = np.maximum(prof, crest)
    zf = prof.min()
    rel = prof - zf
    top = max(min(float(rel.max()), e_hi), e_lo)
    rows = tab.shape[0]
    last = rows - 1
    for r in range(rows):
        e = top * (r / last) ** 2
        area = 0.0
        conv = 0.0
        for q in range(m):
            dep = e - rel[q]
            if dep > 0.0:
                area += dep
                conv += dep * np.cbrt(dep) ** 2
        tab[r, 0] = pixel * area * length
        tab[r, 1] = (pixel * n_inv * conv * length) ** 0.6
    return float(zf), top


@njit
def build_all(z, k, ny, nx, pixel, n_inv, xcrest, xlen, ycrest, ylen, e_lo, e_hi, rows):
    """z is (ny*k+1+?, nx*k+1+?) with one extra pixel row and column before cell 0, as production reads it."""
    zmin = np.zeros((ny, nx))
    rel = np.zeros((ny, nx))
    hc = np.zeros((ny, nx))
    dtab = np.zeros((ny, nx, rows))
    zfx = np.zeros((ny, nx + 1))
    zfy = np.zeros((ny + 1, nx))
    efx = np.ones((ny, nx + 1))
    efy = np.ones((ny + 1, nx))
    ftx = np.zeros((ny, nx + 1, rows, 2))
    fty = np.zeros((ny + 1, nx, rows, 2))
    prof = np.empty(k)
    for j in range(ny):
        for i in range(nx):
            r0, c0 = 1 + j * k, 1 + i * k
            zmin[j, i], rel[j, i], hc[j, i] = cell_table(z[r0 : r0 + k, c0 : c0 + k].copy(), rows, dtab[j, i])
            for q in range(k):
                prof[q] = max(z[r0 + q, c0 - 1], z[r0 + q, c0])
            zfx[j, i], efx[j, i] = face_table(prof, xcrest[j, i], pixel, n_inv, xlen[j, i], e_lo, e_hi, ftx[j, i])
            for q in range(k):
                prof[q] = max(z[r0 - 1, c0 + q], z[r0, c0 + q])
            zfy[j, i], efy[j, i] = face_table(prof, ycrest[j, i], pixel, n_inv, ylen[j, i], e_lo, e_hi, fty[j, i])
    return zmin, rel, hc, dtab, zfx, efx, ftx, zfy, efy, fty


@njit(inline="always")
def minmod(a, b):
    if a * b <= 0.0:
        return 0.0
    return a if abs(a) < abs(b) else b


@njit(inline="always")
def ustar(uc, uup, udown, second):
    if not second:
        return uc
    return uc + 0.5 * minmod(uc - uup, udown - uc)


@njit(inline="always")
def cell_level(hb, hc, tab, rows):
    if hc <= 0.0:
        return hb
    last = rows - 1
    if hb >= hc:
        return tab[last] + (hb - hc)
    s = np.sqrt(hb / hc) * last
    r = min(int(s), last - 1)
    return tab[r] + (s - r) * (tab[r + 1] - tab[r])


@njit(inline="always")
def cell_plan(hb, hc, tab, rows):
    if hc <= 0.0 or hb >= hc:
        return 1.0
    last = rows - 1
    s = np.sqrt(hb / hc) * last
    r = min(int(s), last - 1)
    m = float(last)
    return hc * (2 * r + 1) / (m * m) / max(tab[r + 1] - tab[r], 1e-12)


@njit(inline="always")
def face_lookup(e, top, tab, rows):
    last = rows - 1
    m = float(last)
    if e >= top:
        a1 = tab[2 * last]
        a0 = tab[2 * last - 2]
        c = (m - 1.0) / m
        w = (a1 - a0) / (top * (1.0 - c * c))
        area = a1 + w * (e - top)
        return area, tab[2 * last + 1] * (area / max(a1, 1e-12)), w
    s = np.sqrt(e / top) * m
    r = min(int(s), last - 1)
    c0 = r / m
    c1 = (r + 1) / m
    e0 = c0 * c0 * top
    de = (c1 * c1 - c0 * c0) * top
    f = (e - e0) / de
    a0 = tab[2 * r]
    a1 = tab[2 * r + 2]
    t0 = tab[2 * r + 1]
    return a0 + f * (a1 - a0), t0 + f * (tab[2 * r + 3] - t0), (a1 - a0) / de


@njit(inline="always")
def gate(u_nb, uf, mirror):
    """A neighbour face that carries nothing (dry or closed, u exactly 0) has no velocity to give: fix m reads this face instead."""
    if mirror and u_nb == 0.0:
        return uf
    return u_nb


@njit
def face_step(
    k, dt, want_wave, om, s, p, h, d, u, m, q, qp, vp, fl, fr, gl, gr, ef, cw, ftab, fstart, fscale, u1, m1, q1,
    rows, g, dx, e_wet, h_cfl, u_max, lead, a_min, second, sheet, adv, mirror, vbopen,
):  # fmt: skip
    """One face: s is the array step along the normal, p across it. Returns the wave speed."""
    e_l = d[k - s] - fl[k]
    e_r = d[k] - fr[k]
    uf = u[k]
    e_lp = max(e_l, 0.0)
    e_rp = max(e_r, 0.0)
    from_left = uf > 0.0 or (uf == 0.0 and e_l >= e_r)
    eup = e_lp if from_left else e_rp
    if eup <= e_wet:
        u1[k] = 0.0
        m1[k] = 0.0
        q1[k] = 0.0
        return 0.0
    start = 2 * rows * fstart[k]
    area, t, w = face_lookup(eup, ef[k], ftab[start : start + 2 * rows], rows)
    h_l = h[k - s]
    h_r = h[k]
    hup = h_l if from_left else h_r

    # [1] section
    rho = 1.0
    d_eta = e_rp - e_lp
    if sheet:
        if sheet == 2:
            avol = max(h_l, h_r) * dx
        elif sheet == 3:
            avol = hup / max(om[k - s] if from_left else om[k], a_min) * dx
        else:
            avol = hup * dx
        edown = e_rp if from_left else e_lp
        if avol < area:
            sub = min(e_lp, e_rp) / max(e_lp, e_rp)
            sub2 = sub * sub
            alpha = sub2 * sub2
            rho = alpha + (1.0 - alpha) * avol / area
        if edown <= 0.0:
            # [2] disconnected
            g_u = gl[k] if from_left else gr[k]
            g_d = gr[k] if from_left else gl[k]
            h_d = h_r if from_left else h_l
            drop = (hup - g_u) - max(h_d - g_d, 0.5 * (g_u - g_d))
            level_drop = abs(e_l - e_r)
            drive = max(eup, min(drop, level_drop))
            d_eta = -drive if from_left else drive

    # [3] momentum fluxes
    um = gate(u[k - s], uf, mirror)
    up = gate(u[k + s], uf, mirror)
    qc_l = 0.5 * (q[k - s] + q[k])
    qc_r = 0.5 * (q[k] + q[k + s])
    umm = gate(u[k - 2 * s], um, mirror)
    upp = gate(u[k + 2 * s], up, mirror)
    s_l = ustar(um, umm, uf, second) if qc_l > 0.0 else ustar(uf, up, um, second)
    s_r = ustar(uf, um, up, second) if qc_r > 0.0 else ustar(up, upp, uf, second)
    flux = qc_r * s_r - qc_l * s_l
    qy_s = 0.5 * (qp[k - s] + qp[k])
    qy_n = 0.5 * (qp[k - s + p] + qp[k + p])
    u_s = gate(u[k - p], uf, mirror)
    u_n = gate(u[k + p], uf, mirror)
    uss = gate(u[k - 2 * p], u_s, mirror)
    unn = gate(u[k + 2 * p], u_n, mirror)
    us_s = ustar(u_s, uss, uf, second) if qy_s > 0.0 else ustar(uf, u_n, u_s, second)
    us_n = ustar(uf, u_s, u_n, second) if qy_n > 0.0 else ustar(u_n, unn, uf, second)
    flux += qy_n * us_n - qy_s * us_s

    # [4] momentum and pressure
    abar = 0.5 * (h_l + h_r) * dx
    press = dt * g * d_eta / dx
    if adv and abar > 1e-6 * dx:
        us = (m[k] - dt * flux / dx) / abar - press
    else:
        us = uf - press

    # [5] friction
    va = vp[k - s]
    vb_ = vp[k]
    vc = vp[k - s + p]
    vd = vp[k + p]
    if vbopen == 0:
        vb = 0.25 * (va + vb_ + vc + vd)
    else:
        # fix m2: closed or dry transverse faces do not count in the mean
        cnt = 0.0
        tot = 0.0
        if va != 0.0:
            cnt += 1.0
            tot += va
        if vb_ != 0.0:
            cnt += 1.0
            tot += vb_
        if vc != 0.0:
            cnt += 1.0
            tot += vc
        if vd != 0.0:
            cnt += 1.0
            tot += vd
        vb = tot / cnt if cnt > 0.0 else 0.0
    t3 = t * t * t * np.cbrt(t)
    fric = area * area / max(t3, 1e-30) * fscale[k]
    if rho < 1.0:
        fric = fric / max(rho * np.cbrt(rho), 1e-12)
    a = dt * g * fric
    sp = np.sqrt(us * us + vb * vb)
    un = 2.0 * us / (1.0 + np.sqrt(1.0 + 4.0 * a * sp))
    if abs(un) > u_max:
        un = u_max if un > 0.0 else -u_max

    # [6] crest face
    qn = area * rho * un
    c = cw[k]
    if c > 0.0:
        qc = c * area * np.sqrt(area / max(w, 1e-9))
        if abs(qn) > qc:
            qn = qc if qn > 0.0 else -qc
            un = qn / max(area * rho, 1e-12)
    u1[k] = un
    m1[k] = abar * un
    q1[k] = qn
    if not want_wave:
        return 0.0
    if not np.isfinite(un):
        return 1e30
    d_left = d[k - s]
    d_right = d[k]
    dup = d_left if from_left else d_right
    if dup <= h_cfl:
        return 0.0
    plan = om[k - s] if from_left else om[k]
    dother = d_right if from_left else d_left
    if dother > h_cfl:
        plan = min(plan, om[k] if from_left else om[k - s])
    wave = np.sqrt(max(g * area * rho / (max(plan, a_min) * dx), 0.0))
    return abs(un) + min(lead * abs(un - uf), 2.0 * wave) + wave


@njit
def step(
    dt, want_wave, st, alist, om, h, d, u, v, mx, my, qx, qy, flx, frx, glx, grx, efx, cwx, ftx, fsx, fly, fry, gly, gry,
    efy, cwy, fty, fsy, fscx, fscy, u1, v1, mx1, my1, qx1, qy1, r, src, hc, dtab, bcell, bkind, bd0, bh0, bref,
    rows, g, dx, e_wet, h_cfl, u_max, lead, a_min, second, sheet, adv, mirror, vbopen,
):  # fmt: skip
    w = 0.0
    for a_ in range(alist.size):
        k = alist[a_]
        wx = face_step(
            k, dt, want_wave, om, 1, st, h, d, u, mx, qx, qy, v, flx, frx, glx, grx, efx, cwx, ftx, fsx, fscx,
            u1, mx1, qx1, rows, g, dx, e_wet, h_cfl, u_max, lead, a_min, second, sheet, adv, mirror, vbopen,
        )  # fmt: skip
        wy = face_step(
            k, dt, want_wave, om, st, 1, h, d, v, my, qy, qx, u, fly, fry, gly, gry, efy, cwy, fty, fsy, fscy,
            v1, my1, qy1, rows, g, dx, e_wet, h_cfl, u_max, lead, a_min, second, sheet, adv, mirror, vbopen,
        )  # fmt: skip
        w = max(w, max(wx, wy))
    area = dx * dx
    for a_ in range(alist.size):
        k = alist[a_]
        out = max(qx1[k + 1], 0.0) + max(-qx1[k], 0.0) + max(qy1[k + st], 0.0) + max(-qy1[k], 0.0)
        have = max(h[k], 0.0) * area
        r[k] = have / (out * dt) if out * dt > have else 1.0
    for a_ in range(alist.size):
        k = alist[a_]
        cidx = fsx[k]
        rc = r[k]
        qw = qx1[k] * (r[k - 1] if qx1[k] > 0.0 else rc)
        qe = qx1[k + 1] * (rc if qx1[k + 1] > 0.0 else r[k + 1])
        qn = qy1[k] * (r[k - st] if qy1[k] > 0.0 else rc)
        qs = qy1[k + st] * (rc if qy1[k + st] > 0.0 else r[k + st])
        qx[k] = qw
        qy[k] = qn
        hn = max(h[k] + dt * src[k] - dt * (qe - qw + qs - qn) / area, 0.0)
        h[k] = hn
        tab = dtab[rows * cidx : rows * (cidx + 1)]
        d[k] = cell_level(hn, hc[k], tab, rows)
        if want_wave:
            om[k] = cell_plan(hn, hc[k], tab, rows)
    for n in range(bcell.size):
        k = bcell[n]
        if bkind[n] == 0:
            h[k] = bh0[n]
            d[k] = bd0[n]
        elif bkind[n] == 1:
            h[k] = 0.0
            d[k] = 0.0
        else:
            h[k] = h[bref[n]]
            d[k] = max(d[bref[n]] + bd0[n], 0.0)
    return w


class Lattice:
    """Grid, tables and state of the baseline; same defaults as production Numerics()."""

    def __init__(
        self, z, k, dx, n, ny, nx, xcrest=None, xlen=None, ycrest=None, ylen=None, xwall=None, ywall=None, xc=None, yc=None,
        cfl=0.45, e_wet=1e-4, h_cfl=0.01, u_max=25.0, dt_max=5.0, dt_every=8, wave_floor=3.0, a_min=0.02, lead=None,
        second=True, sheet=1, adv=True, mirror=False, vbopen=False, fscx=None, fscy=None, e_lo=8.0, e_hi=16.0, tol=0.05,
        mask=None, band=None,
    ):  # fmt: skip
        self.dx, self.k, self.ny, self.nx = dx, k, ny, nx
        self.cfl, self.e_wet, self.h_cfl, self.u_max, self.dt_max, self.dt_every = cfl, e_wet, h_cfl, u_max, dt_max, dt_every
        self.wave_floor, self.a_min, self.second, self.sheet = wave_floor, a_min, second, int(sheet)
        self.lead = float(dt_every) if lead is None else lead  # production: NumericsRecord.lead = dt_every
        self.adv, self.mirror, self.vbopen = adv, mirror, vbopen
        rows = ROWS
        self.rows = rows
        nan = np.full((ny, nx), np.nan)
        one = np.ones((ny, nx))
        xcrest = nan if xcrest is None else xcrest
        ycrest = nan if ycrest is None else ycrest
        xlen = one if xlen is None else xlen
        ylen = one if ylen is None else ylen
        self.st = st = nx + 2 * HALO
        self.N = N = (ny + 2 * HALO) * st
        self.mask = np.ones((ny, nx), bool) if mask is None else mask
        run_cells = self.mask if band is None else (self.mask & band)
        self.alist = self._own()[run_cells.ravel()].astype(np.int64)
        zmin, rel, hc, dtab, zfx, efx, ftx, zfy, efy, fty = build_all(
            z, k, ny, nx, dx / k, 1.0 / n, xcrest, xlen, ycrest, ylen, e_lo, e_hi, rows
        )
        self.zmin, self.relmean, self.hc2, self.dtab2 = zmin, rel, hc, dtab
        zbar = zmin + rel
        self.zbar = zbar
        pad = lambda a: self._pad(a)  # noqa: E731
        fx = self._faces(zfx[:, :-1], zmin, zbar, 1, np.zeros((ny, nx)) if xc is None else xc, tol, xwall)
        fy = self._faces(zfy[:-1, :], zmin, zbar, 0, np.zeros((ny, nx)) if yc is None else yc, tol, ywall)
        self.flx, self.frx, self.glx, self.grx, self.cwx = (pad(a) for a in fx)
        self.fly, self.fry, self.gly, self.gry, self.cwy = (pad(a) for a in fy)
        for name in ("flx", "frx", "fly", "fry"):
            a = getattr(self, name)
            mask = np.zeros(N, bool)
            mask[self._own()] = True
            a[~mask] = CLOSED
        self.efx, self.efy = pad(efx[:, :-1]), pad(efy[:-1, :])
        self.ftx = ftx[:, :-1].reshape(-1)
        self.fty = fty[:-1, :].reshape(-1)
        fid = np.zeros(N, np.int64)
        fid[self._own()] = np.arange(ny * nx)
        self.fid = fid
        self.hc = pad(hc)
        self.dtab = dtab.reshape(-1)
        self.fscx = np.ones(N) if fscx is None else pad(fscx)
        self.fscy = np.ones(N) if fscy is None else pad(fscy)
        for a in ("h", "d", "u", "v", "mx", "my", "qx", "qy", "u1", "v1", "mx1", "my1", "qx1", "qy1", "src"):
            setattr(self, a, np.zeros(N))
        self.r = np.ones(N)
        self.om = np.ones(N)
        self.bcell = np.zeros(0, np.int64)
        self.bkind = np.zeros(0, np.int64)
        self.bd0 = np.zeros(0)
        self.bh0 = np.zeros(0)
        self.bref = np.zeros(0, np.int64)
        self.t = 0.0
        self.nsteps = 0
        self.dt = self.cfl * dx / wave_floor
        self.refresh_due = True

    def _own(self):
        st, ny, nx = self.st, self.ny, self.nx
        jj, ii = np.meshgrid(np.arange(ny), np.arange(nx), indexing="ij")
        return ((jj + HALO) * st + ii + HALO).ravel()

    def _pad(self, a):
        out = np.zeros(self.N)
        out[self._own()] = np.asarray(a, dtype=np.float64).ravel()
        return out

    def field(self, a):
        return a[self._own()].reshape(self.ny, self.nx)

    def _faces(self, zf, zmin, zbar, axis, crest_c, tol, wall):
        ny, nx = self.ny, self.nx
        active = self.mask
        act_n = np.zeros((ny, nx), bool)
        zmin_n = np.zeros_like(zmin)
        zbar_n = np.zeros_like(zbar)
        if axis == 1:
            act_n[:, 1:] = active[:, :-1]
            zmin_n[:, 1:] = zmin[:, :-1]
            zbar_n[:, 1:] = zbar[:, :-1]
        else:
            act_n[1:, :] = active[:-1, :]
            zmin_n[1:, :] = zmin[:-1, :]
            zbar_n[1:, :] = zbar[:-1, :]
        open_face = active & act_n
        if wall is not None:
            open_face = open_face & ~wall
        fl = np.where(open_face, zf - zmin_n, CLOSED)
        fr = np.where(open_face, zf - zmin, CLOSED)
        gl = np.where(open_face, zf - zbar_n, 0.0)
        gr = np.where(open_face, zf - zbar, 0.0)
        natural = open_face & (gl > tol) & (gr > tol)
        cw = np.where(crest_c > 0.0, crest_c, np.where(natural, CW, 0.0))
        cw = np.where(open_face, cw, 0.0)
        return fl, fr, gl, gr, cw

    def hbar_at_level(self, level):
        rows = self.rows
        last = rows - 1
        zmin, hc, dtab = self.zmin, self.hc2, self.dtab2
        d = np.maximum(np.asarray(level, dtype=np.float64) - zmin, 0.0)
        out = np.where(hc <= 0.0, d, 0.0)
        top = dtab[..., last]
        above = (hc > 0.0) & (d >= top)
        out = np.where(above, hc + (d - top), out)
        inside = (hc > 0.0) & (d < top) & (d > 0.0)
        if inside.any():
            di = d[inside]
            tab = dtab[inside]
            r = np.clip(np.sum(tab <= di[:, None], axis=1) - 1, 0, last - 1)
            idx = np.arange(tab.shape[0])
            lo, hi = tab[idx, r], tab[idx, r + 1]
            s = r + (di - lo) / np.maximum(hi - lo, 1e-30)
            out[inside] = hc[inside] * (s / last) ** 2
        return out

    def set_depth(self, hb):
        st, rows = self.st, self.rows
        self.h[:] = 0.0
        self.h[self._own()] = (hb * self.mask).ravel()
        k_ = self._own()
        for n, k in enumerate(k_):
            tab = self.dtab[rows * n : rows * (n + 1)]
            self.d[k] = cell_level(self.h[k], self.hc[k], tab, rows)
            self.om[k] = cell_plan(self.h[k], self.hc[k], tab, rows)

    def set_source(self, rate):
        self.src[self._own()] = rate.ravel()

    def set_boundary(self, jj, ii, d0, h0, kind=None, ref=None):
        self.bcell = ((jj + HALO) * self.st + ii + HALO).astype(np.int64)
        self.bref = self.bcell.copy() if ref is None else ((ref[0] + HALO) * self.st + ref[1] + HALO).astype(np.int64)
        self.bkind = np.zeros(self.bcell.size, np.int64) if kind is None else kind
        self.bd0 = np.asarray(d0, dtype=np.float64)
        self.bh0 = np.asarray(h0, dtype=np.float64)

    def advance(self, t_end):
        g = G
        while self.t < t_end - 1e-9:
            refresh = self.refresh_due or self.nsteps % self.dt_every == 0
            self.refresh_due = False
            dt = min(self.dt, t_end - self.t, self.dt_max)
            w = step(
                dt, refresh, self.st, self.alist, self.om, self.h, self.d, self.u, self.v, self.mx, self.my, self.qx, self.qy,
                self.flx, self.frx, self.glx, self.grx, self.efx, self.cwx, self.ftx, self.fid,
                self.fly, self.fry, self.gly, self.gry, self.efy, self.cwy, self.fty, self.fid, self.fscx, self.fscy,
                self.u1, self.v1, self.mx1, self.my1, self.qx1, self.qy1, self.r, self.src, self.hc, self.dtab,
                self.bcell, self.bkind, self.bd0, self.bh0, self.bref,
                self.rows, g, self.dx, self.e_wet, self.h_cfl, self.u_max, self.lead, self.a_min, self.second, self.sheet,
                self.adv, self.mirror, self.vbopen,
            )  # fmt: skip
            self.t += dt
            self.nsteps += 1
            self.u, self.u1 = self.u1, self.u
            self.v, self.v1 = self.v1, self.v
            self.mx, self.mx1 = self.mx1, self.mx
            self.my, self.my1 = self.my1, self.my
            if refresh:
                if not np.isfinite(w):
                    raise FloatingPointError(f"non-finite wave at t={self.t}")
                self.dt = min(self.cfl * self.dx / max(w, self.wave_floor), self.dt_max)
        return self.t
