"""Polygon kernel for options (b) and (c): decision 19's scheme on any cells and faces.

Same unknowns as the lattice: mean depth per cell, normal velocity, momentum and discharge per face, implicit friction, sub-grid tables on
cells and faces, the same [1]..[6] order. What changes is what a uniform lattice lets you leave out:

* geometry: cell area Ac, centroid c; face length, unit normal n (L to R), midpoint xf; dn = n.(cR - cL); skew s = (cR - cL) - dn n.
* level gradient: dEta = eR - eL - s.G, with G the Green-Gauss cell gradient built from face level differences only, so still water has
  G = 0 exactly and no absolute level enters the kernel. Closed and dry faces contribute nothing.
* advection: cell momentum vector from the faces (Perot): V U = sum (xf - c) Q_out. Rate per cell R = sum Q_out U_upwind. A face reads
  flux = n.(R_L + R_R)/2. A wall carries no Q, so it sinks no momentum, and uniform flow has R = 0 at any angle on any polygon.
* friction speed: transverse velocity from the cell vectors.
* time step: per face, freq = (|u| + min(lead |du|, 2c) + c) / dn, c^2 = g A rho dn / max(plan Ac, a_min dx^2). On the lattice this is exactly
  the production rule.

Written as loops over a face list because options (b) and (c) share it; the cost of that form is not the cost on a GPU (see README).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numba import njit

from lattice import CW, ROWS, cell_level, cell_plan, face_lookup

G = 9.80665


@dataclass
class Mesh:
    Ac: np.ndarray
    cx: np.ndarray
    cy: np.ndarray
    zmin: np.ndarray
    zbar: np.ndarray
    hc: np.ndarray
    dtab: np.ndarray  # (nc, rows)
    L: np.ndarray
    R: np.ndarray
    ln: np.ndarray
    nx: np.ndarray
    ny: np.ndarray
    xf: np.ndarray
    yf: np.ndarray
    dn: np.ndarray
    sx: np.ndarray
    sy: np.ndarray
    zf: np.ndarray
    ef: np.ndarray
    ftab: np.ndarray  # (nf, rows, 2)
    cw: np.ndarray


def finish(cells, faces, dx, tol=0.05, dn_min=0.15):
    """cells: dict of arrays Ac, cx, cy, zmin, zbar, hc, dtab; faces: dict L, R, ln, nx, ny, xf, yf, zf, ef, ftab. Adds dn, skew, crest flags."""
    Ac, cx, cy = cells["Ac"], cells["cx"], cells["cy"]
    L, R = faces["L"], faces["R"]
    # the lattice's max-of-two-pixels rule puts every invert at or above both cell minima; a sampled polygon face must keep that, or a dry cell shows a wet face
    faces["zf"] = np.maximum(np.maximum(faces["zf"], cells["zmin"][L]), cells["zmin"][R])
    dcx, dcy = cx[R] - cx[L], cy[R] - cy[L]
    dn = dcx * faces["nx"] + dcy * faces["ny"]
    dn = np.maximum(dn, dn_min * dx)
    sx = dcx - dn * faces["nx"]
    sy = dcy - dn * faces["ny"]
    gl = faces["zf"] - cells["zbar"][L]
    gr = faces["zf"] - cells["zbar"][R]
    cw = np.where((gl > tol) & (gr > tol), CW, 0.0)
    return Mesh(Ac, cx, cy, cells["zmin"], cells["zbar"], cells["hc"], cells["dtab"], L, R, faces["ln"], faces["nx"], faces["ny"],
                faces["xf"], faces["yf"], dn, sx, sy, faces["zf"], faces["ef"], faces["ftab"], cw)  # fmt: skip


@njit
def gstep(
    dt, want_wave, nc, nf, L, R, ln, nfx, nfy, xf, yf, dn, sx, sy, fl, fr, gl, gr, ef, cw, ftab, Ac, cx, cy, hc, dtab,
    h, d, om, u, m, q, u1, m1, q1, r, src, Ux, Uy, Rx, Ry, Gx, Gy, Dl, bcell, bkind, bd0, bh0,
    rows, g, dx, e_wet, h_cfl, u_max, lead, a_min, sheet, adv, skew,
):  # fmt: skip
    # cell vectors
    Ux[:] = 0.0
    Uy[:] = 0.0
    Rx[:] = 0.0
    Ry[:] = 0.0
    if adv:
        for f in range(nf):
            qf = q[f]
            if qf != 0.0:
                a, b = L[f], R[f]
                Ux[a] += (xf[f] - cx[a]) * qf
                Uy[a] += (yf[f] - cy[a]) * qf
                Ux[b] -= (xf[f] - cx[b]) * qf
                Uy[b] -= (yf[f] - cy[b]) * qf
        for c in range(nc):
            vol = h[c] * Ac[c]
            if vol > 1e-9:
                Ux[c] /= vol
                Uy[c] /= vol
            else:
                Ux[c] = 0.0
                Uy[c] = 0.0
        for f in range(nf):
            qf = q[f]
            if qf != 0.0:
                a, b = L[f], R[f]
                up = a if qf > 0.0 else b
                Rx[a] += qf * Ux[up]
                Ry[a] += qf * Uy[up]
                Rx[b] -= qf * Ux[up]
                Ry[b] -= qf * Uy[up]
    # level gradient from face differences
    if skew:
        Gx[:] = 0.0
        Gy[:] = 0.0
        for f in range(nf):
            a, b = L[f], R[f]
            e_l = d[a] - fl[f]
            e_r = d[b] - fr[f]
            if e_l > e_wet and e_r > e_wet and h[a] > 0.0 and h[b] > 0.0:
                de = e_r - e_l
                Dl[f] = de
                w = 0.5 * de * ln[f]
                Gx[a] += w * nfx[f]
                Gy[a] += w * nfy[f]
                Gx[b] += w * nfx[f]
                Gy[b] += w * nfy[f]
            else:
                Dl[f] = 0.0
        for c in range(nc):
            Gx[c] /= Ac[c]
            Gy[c] /= Ac[c]
    freq = 0.0
    for f in range(nf):
        a, b = L[f], R[f]
        e_l = d[a] - fl[f]
        e_r = d[b] - fr[f]
        uf = u[f]
        e_lp = max(e_l, 0.0)
        e_rp = max(e_r, 0.0)
        from_left = uf > 0.0 or (uf == 0.0 and e_l >= e_r)
        eup = e_lp if from_left else e_rp
        if eup <= e_wet:
            u1[f] = 0.0
            m1[f] = 0.0
            q1[f] = 0.0
            continue
        start = 2 * rows * f
        area, t, w = face_lookup(eup, ef[f], ftab[start : start + 2 * rows], rows)
        dnf = dn[f]
        v_l = h[a] * Ac[a]
        v_r = h[b] * Ac[b]
        vup = v_l if from_left else v_r
        rho = 1.0
        d_eta = e_rp - e_lp
        if skew and Dl[f] != 0.0:
            d_eta -= 0.5 * ((Gx[a] + Gx[b]) * sx[f] + (Gy[a] + Gy[b]) * sy[f])
        if sheet:
            if sheet == 2:
                avol = max(v_l, v_r) / dnf
            elif sheet == 3:
                # mean depth over the cell times the face length: production's hup dx on the lattice, right on any polygon
                avol = (h[a] if from_left else h[b]) * ln[f]
            else:
                avol = vup / dnf
            edown = e_rp if from_left else e_lp
            if avol < area:
                sub = min(e_lp, e_rp) / max(e_lp, e_rp)
                sub2 = sub * sub
                alpha = sub2 * sub2
                rho = alpha + (1.0 - alpha) * avol / area
            if edown <= 0.0:
                g_u = gl[f] if from_left else gr[f]
                g_d = gr[f] if from_left else gl[f]
                hup = h[a] if from_left else h[b]
                h_d = h[b] if from_left else h[a]
                drop = (hup - g_u) - max(h_d - g_d, 0.5 * (g_u - g_d))
                level_drop = abs(e_l - e_r)
                drive = max(eup, min(drop, level_drop))
                d_eta = -drive if from_left else drive
        abar = 0.5 * (v_l + v_r) / dnf
        press = dt * g * d_eta / dnf
        if adv and abar > 1e-6 * dx:
            flux = 0.5 * (nfx[f] * (Rx[a] + Rx[b]) + nfy[f] * (Ry[a] + Ry[b]))
            us = (m[f] - dt * flux / dnf) / abar - press
        else:
            us = uf - press
        tx, ty = -nfy[f], nfx[f]
        wa = 1.0 if v_l > 1e-9 else 0.0
        wb = 1.0 if v_r > 1e-9 else 0.0
        vb = 0.0
        if wa + wb > 0.0:
            vb = (wa * (Ux[a] * tx + Uy[a] * ty) + wb * (Ux[b] * tx + Uy[b] * ty)) / (wa + wb)
        t3 = t * t * t * np.cbrt(t)
        fric = area * area / max(t3, 1e-30)
        if rho < 1.0:
            fric = fric / max(rho * np.cbrt(rho), 1e-12)
        aa = dt * g * fric
        sp = np.sqrt(us * us + vb * vb)
        un = 2.0 * us / (1.0 + np.sqrt(1.0 + 4.0 * aa * sp))
        if abs(un) > u_max:
            un = u_max if un > 0.0 else -u_max
        qn = area * rho * un
        c = cw[f]
        if c > 0.0:
            qc = c * area * np.sqrt(area / max(w, 1e-9))
            if abs(qn) > qc:
                qn = qc if qn > 0.0 else -qc
                un = qn / max(area * rho, 1e-12)
        u1[f] = un
        m1[f] = abar * un
        q1[f] = qn
        if want_wave:
            if not np.isfinite(un):
                return 1e30
            dup = d[a] if from_left else d[b]
            if dup > h_cfl:
                up_c = a if from_left else b
                dn_c = b if from_left else a
                wet_plan = om[up_c] * Ac[up_c]
                if d[dn_c] > h_cfl:
                    wet_plan = min(wet_plan, om[dn_c] * Ac[dn_c])
                wave = np.sqrt(max(g * area * rho * dnf / max(wet_plan, a_min * dx * dx), 0.0))
                fr_ = (abs(un) + min(lead * abs(un - uf), 2.0 * wave) + wave) / dnf
                freq = max(freq, fr_)
    # positivity and cells
    Rx[:] = 0.0  # used as outflow accumulator
    for f in range(nf):
        qf = q1[f]
        if qf > 0.0:
            Rx[L[f]] += qf
        elif qf < 0.0:
            Rx[R[f]] -= qf
    for c in range(nc):
        have = max(h[c], 0.0) * Ac[c]
        out = Rx[c]
        r[c] = have / (out * dt) if out * dt > have else 1.0
    Ry[:] = 0.0  # divergence
    for f in range(nf):
        qf = q1[f]
        a, b = L[f], R[f]
        qf = qf * (r[a] if qf > 0.0 else r[b])
        q[f] = qf
        Ry[a] += qf
        Ry[b] -= qf
    for c in range(nc):
        hn = max(h[c] + dt * src[c] - dt * Ry[c] / Ac[c], 0.0)
        h[c] = hn
        tab = dtab[rows * c : rows * (c + 1)]
        d[c] = cell_level(hn, hc[c], tab, rows)
        if want_wave:
            om[c] = cell_plan(hn, hc[c], tab, rows)
    for n in range(bcell.size):
        k = bcell[n]
        h[k] = bh0[n]
        d[k] = bd0[n]
    return freq


class Graph:
    def __init__(
        self, mesh: Mesh, dx, cfl=0.45, e_wet=1e-4, h_cfl=0.01, u_max=25.0, dt_max=5.0, dt_every=8, wave_floor=3.0, a_min=0.02,
        sheet=1, adv=True, skew=True,
    ):  # fmt: skip
        self.me, self.dx = mesh, dx
        self.cfl, self.e_wet, self.h_cfl, self.u_max, self.dt_max, self.dt_every = cfl, e_wet, h_cfl, u_max, dt_max, dt_every
        self.wave_floor, self.a_min, self.sheet, self.adv, self.skew = wave_floor, a_min, int(sheet), adv, skew
        self.lead = float(dt_every)
        self.rows = ROWS
        me = mesh
        self.nc, self.nf = me.Ac.size, me.L.size
        self.zmin = me.zmin
        self.fl = me.zf - me.zmin[me.L]
        self.fr = me.zf - me.zmin[me.R]
        self.gl = me.zf - me.zbar[me.L]
        self.gr = me.zf - me.zbar[me.R]
        self.ftab = me.ftab.reshape(-1)
        self.dtab = me.dtab.reshape(-1)
        for a in ("h", "d", "src", "Ux", "Uy", "Rx", "Ry", "Gx", "Gy"):
            setattr(self, a, np.zeros(self.nc))
        self.om = np.ones(self.nc)
        self.r = np.ones(self.nc)
        for a in ("u", "m", "q", "u1", "m1", "q1", "Dl"):
            setattr(self, a, np.zeros(self.nf))
        self.bcell = np.zeros(0, np.int64)
        self.bkind = np.zeros(0, np.int64)
        self.bd0 = np.zeros(0)
        self.bh0 = np.zeros(0)
        self.t = 0.0
        self.nsteps = 0
        self.dt = cfl * dx / wave_floor
        self.refresh_due = True

    def hbar_at_level(self, level):
        last = self.rows - 1
        zmin, hc, dtab = self.zmin, self.me.hc, self.me.dtab
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
        rows = self.rows
        self.h[:] = hb
        for c in range(self.nc):
            tab = self.dtab[rows * c : rows * (c + 1)]
            self.d[c] = cell_level(self.h[c], self.me.hc[c], tab, rows)
            self.om[c] = cell_plan(self.h[c], self.me.hc[c], tab, rows)

    def advance(self, t_end):
        me = self.me
        while self.t < t_end - 1e-9:
            refresh = self.refresh_due or self.nsteps % self.dt_every == 0
            self.refresh_due = False
            dt = min(self.dt, t_end - self.t, self.dt_max)
            fq = gstep(
                dt, refresh, self.nc, self.nf, me.L, me.R, me.ln, me.nx, me.ny, me.xf, me.yf, me.dn, me.sx, me.sy, self.fl, self.fr,
                self.gl, self.gr, me.ef, me.cw, self.ftab, me.Ac, me.cx, me.cy, me.hc, self.dtab, self.h, self.d, self.om, self.u,
                self.m, self.q, self.u1, self.m1, self.q1, self.r, self.src, self.Ux, self.Uy, self.Rx, self.Ry, self.Gx, self.Gy,
                self.Dl, self.bcell, self.bkind, self.bd0, self.bh0, self.rows, G, self.dx, self.e_wet, self.h_cfl, self.u_max,
                self.lead, self.a_min, self.sheet, self.adv, self.skew,
            )  # fmt: skip
            self.t += dt
            self.nsteps += 1
            self.u, self.u1 = self.u1, self.u
            self.m, self.m1 = self.m1, self.m
            if refresh:
                if not np.isfinite(fq) or fq > 1e29:
                    raise FloatingPointError(f"non-finite at t={self.t}")
                self.dt = min(self.cfl / max(fq, self.wave_floor / self.dx), self.dt_max)
        return self.t
