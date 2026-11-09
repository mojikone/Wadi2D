"""Numba kernels of the table builder: one tile of pixels in, its cell and face tables out.

Rows are spaced quadratically. A cell table gives the level above zmin at hbar_r = Hc (r / m)^2, exact on a plane
when read linearly in r. A face table gives area and conveyance^(3/5) at depth e_r = E (r / m)^2 over the face
invert, read linearly in e; conveyance^(3/5) is linear in depth for a wide section, so no error enters there.
"""

from __future__ import annotations

import numpy as np
from numba import njit, prange

EPS_RELIEF = 1e-9


@njit(cache=True)
def _cell_table(z: np.ndarray, rows: int, tab: np.ndarray) -> tuple[float, float, float]:
    """Fill ``tab`` for one cell. Returns zmin, mean bed over zmin, and Hc."""
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


@njit(cache=True)
def _face_table(
    prof: np.ndarray,
    crest: float,
    pixel: float,
    n_inv: float,
    weight: np.ndarray,
    length: float,
    e_lo: float,
    e_hi: float,
    tab: np.ndarray,
) -> tuple[float, float]:
    """Fill ``tab`` (rows, 2) for one face from its along-face ground. Returns invert and table top.

    ``weight`` is the conveyance of each pixel over what the face's own n gives: 1 unless the pixel is lined.
    """
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
                conv += weight[q] * dep * np.cbrt(dep) ** 2
        tab[r, 0] = pixel * area * length
        tab[r, 1] = (pixel * n_inv * conv * length) ** 0.6
    return float(zf), top


@njit(cache=True)
def _local_radius_conveyance(
    ext: np.ndarray,
    i0: int,
    i1: int,
    zf: float,
    top: float,
    pixel: float,
    n_inv: float,
    weight: np.ndarray,
    length: float,
    beta: float,
    tab: np.ndarray,
) -> None:
    """Overwrite the conveyance column of a face table with Spada et al.'s local hydraulic radius (W49).

    ``ext`` is the ground along the face's line at the pixel spacing, reaching past the face's own pixels
    ``[i0, i1)`` on both sides; the table's levels are the ones ``_face_table`` used, ``zf + top (r / m)^2``. At each
    level a pixel i of the face conveys (1/n) d_i R_i^(2/3) per unit width, R_i the wetted area over the wetted
    perimeter (ground slope included) over the pixels within beta d_i of it on the same wet run, each weighted
    1 - |s - s_i| / (beta d_i) (Spada et al. 2015, eqs. 14 to 17). Window sums by prefix sums: linear in the line's
    length, whatever the window. On a flat bed R_i = d_i, the strips sum exactly."""
    n = ext.size
    rows = tab.shape[0]
    last = rows - 1
    d = np.zeros(n)
    per = np.zeros(n)
    run_lo = np.zeros(n, np.int64)
    run_hi = np.zeros(n, np.int64)
    s0 = np.zeros(n + 1)
    s1 = np.zeros(n + 1)
    p0 = np.zeros(n + 1)
    p1 = np.zeros(n + 1)
    pix2 = pixel * pixel
    for r in range(rows):
        level = zf + top * (r / last) ** 2
        for t in range(n):
            dep = level - ext[t]
            d[t] = dep if dep > 0.0 else 0.0
        # the wetted perimeter: the ground between pixel centres taken as straight, each segment counted only where it
        # lies under the water, so a pixel just wet adds a sliver, not its whole slope (continuous in the level)
        for t in range(n):
            per[t] = 0.0
        if d[0] > 0.0:
            per[0] += 0.5 * pixel
        if d[n - 1] > 0.0:
            per[n - 1] += 0.5 * pixel
        for t in range(n - 1):
            wa, wb = d[t] > 0.0, d[t + 1] > 0.0
            if not (wa or wb):
                continue
            rise = ext[t + 1] - ext[t]
            seg = np.sqrt(pix2 + rise * rise)
            if wa and wb:
                per[t] += 0.5 * seg
                per[t + 1] += 0.5 * seg
            elif wa:
                per[t] += min(d[t] / rise, 1.0) * seg if rise > 0.0 else 0.5 * pixel
            elif -rise > 0.0:
                per[t + 1] += min(d[t + 1] / -rise, 1.0) * seg
            else:
                per[t + 1] += 0.5 * pixel
        start = -1
        for t in range(n):
            if d[t] > 0.0:
                if start < 0:
                    start = t
                run_lo[t] = start
            else:
                start = -1
        end = -1
        for t in range(n - 1, -1, -1):
            if d[t] > 0.0:
                if end < 0:
                    end = t
                run_hi[t] = end
            else:
                end = -1
        for t in range(n):
            s0[t + 1] = s0[t] + d[t]
            s1[t + 1] = s1[t] + t * d[t]
            p0[t + 1] = p0[t] + per[t]
            p1[t + 1] = p1[t] + t * per[t]
        conv = 0.0
        for i in range(i0, i1):
            di = d[i]
            if di <= 0.0:
                continue
            w = max(beta * di / pixel, 1e-9)
            lo = max(run_lo[i], int(np.ceil(i - w)))
            hi = min(run_hi[i], int(np.floor(i + w)))
            a_sum = (1.0 - i / w) * (s0[i + 1] - s0[lo]) + (s1[i + 1] - s1[lo]) / w
            a_sum += (1.0 + i / w) * (s0[hi + 1] - s0[i + 1]) - (s1[hi + 1] - s1[i + 1]) / w
            p_sum = (1.0 - i / w) * (p0[i + 1] - p0[lo]) + (p1[i + 1] - p1[lo]) / w
            p_sum += (1.0 + i / w) * (p0[hi + 1] - p0[i + 1]) - (p1[hi + 1] - p1[i + 1]) / w
            radius = pixel * a_sum / p_sum if p_sum > 0.0 else di
            conv += weight[i - i0] * di * np.cbrt(radius) ** 2
        tab[r, 1] = (pixel * n_inv * conv * length) ** 0.6


@njit(cache=True)
def _lined(pixel_n: float, cell_n: float) -> float:
    """Conveyance of a pixel over what the cell's n gives it."""
    return 1.0 if np.isnan(pixel_n) else cell_n / pixel_n


@njit(cache=True, parallel=True)
def tile_tables(
    z: np.ndarray,
    k: int,
    tile: int,
    pixel: float,
    nman: np.ndarray,
    npix: np.ndarray,
    xcrest: np.ndarray,
    xlen: np.ndarray,
    ycrest: np.ndarray,
    ylen: np.ndarray,
    e_lo: float,
    e_hi: float,
    zmin: np.ndarray,
    relmean: np.ndarray,
    hc: np.ndarray,
    dtab: np.ndarray,
    zfx: np.ndarray,
    efx: np.ndarray,
    ftabx: np.ndarray,
    zfy: np.ndarray,
    efy: np.ndarray,
    ftaby: np.ndarray,
) -> None:
    """One tile. ``z`` is (tile*k + 1, tile*k + 1) pixels: one extra row north and one extra column west, so own
    west and north faces see the pixels on both sides. Cell (j, i) covers rows 1 + j*k .. of ``z``.

    Along a face, the ground is the higher of the two pixels that meet there: the face sees a ridge exactly one
    pixel wide, on either side of it, and takes that pixel's lining. ``npix`` is a Manning n per pixel of ``z``, NaN
    where the cell's own n holds; a 1 x 1 array means no pixel is lined.
    """
    rows = dtab.shape[2]
    lined = npix.shape[0] > 1
    for j in prange(tile):
        prof = np.empty(k)
        weight = np.ones(k)
        for i in range(tile):
            r0, c0 = 1 + j * k, 1 + i * k
            cell = z[r0 : r0 + k, c0 : c0 + k]
            zmin[j, i], relmean[j, i], hc[j, i] = _cell_table(cell, rows, dtab[j, i])
            for q in range(k):
                near, far = z[r0 + q, c0], z[r0 + q, c0 - 1]
                prof[q] = max(far, near)
                if lined:
                    weight[q] = _lined(npix[r0 + q, c0 - 1] if far > near else npix[r0 + q, c0], nman[j, i])
            zfx[j, i], efx[j, i] = _face_table(
                prof, xcrest[j, i], pixel, 1.0 / nman[j, i], weight, xlen[j, i], e_lo, e_hi, ftabx[j, i]
            )
            for q in range(k):
                near, far = z[r0, c0 + q], z[r0 - 1, c0 + q]
                prof[q] = max(far, near)
                if lined:
                    weight[q] = _lined(npix[r0 - 1, c0 + q] if far > near else npix[r0, c0 + q], nman[j, i])
            zfy[j, i], efy[j, i] = _face_table(
                prof, ycrest[j, i], pixel, 1.0 / nman[j, i], weight, ylen[j, i], e_lo, e_hi, ftaby[j, i]
            )


def centre_beds(z: np.ndarray, k: int, tile: int) -> tuple[np.ndarray, np.ndarray]:
    """The bed on each cell's centre lines (W47): the lowest pixel of its middle pixel column (for x faces) and of its
    middle pixel row (for y faces), the mean of the two middle ones when k is even. ``z`` is a tile's pixel block whose
    first row and column belong to the neighbours, as ``tile_tables`` reads it. On a cell of one pixel it is the pixel."""
    c = np.asarray(z, np.float64)[1 : 1 + tile * k, 1 : 1 + tile * k].reshape(tile, k, tile, k)
    columns = c.min(axis=1)  # (j, i, pixel column)
    rows = c.min(axis=3)  # (j, pixel row, i)
    if k % 2:
        zcx, zcy = columns[:, :, k // 2], rows[:, k // 2, :]
    else:
        zcx = 0.5 * (columns[:, :, k // 2 - 1] + columns[:, :, k // 2])
        zcy = 0.5 * (rows[:, k // 2 - 1, :] + rows[:, k // 2, :])
    return zcx, zcy


@njit(cache=True, parallel=True)
def tile_local_radius(
    zbig: np.ndarray,
    margin: int,
    k: int,
    tile: int,
    pixel: float,
    nman: np.ndarray,
    npix: np.ndarray,
    xcrest: np.ndarray,
    xlen: np.ndarray,
    ycrest: np.ndarray,
    ylen: np.ndarray,
    zfx: np.ndarray,
    efx: np.ndarray,
    ftabx: np.ndarray,
    zfy: np.ndarray,
    efy: np.ndarray,
    ftaby: np.ndarray,
    beta: float,
    e_hi: float,
) -> None:
    """The local hydraulic radius on a tile's own faces, after ``tile_tables`` (W49). ``zbig`` is the tile's pixel block
    of ``tile_tables`` with ``margin`` more pixels on every side, so a face's line reaches past its own ends; ``npix``
    is the lining of the block without the margin. Crest faces keep their table: their cap reads the crest.

    A face's table top is raised to the relief of its whole window, at most ``e_hi``, and its table rebuilt at the new
    levels: above its top a table grows its conveyance with its area, which is the strips sum's law on a flat face but
    not the local radius's, so a flat face in a deep narrow channel must not reach its top while the walls still count."""
    lined = npix.shape[0] > 1
    for j in prange(tile):
        weight = np.ones(k)
        full = np.empty(k + 2 * margin)
        for i in range(tile):
            r0, c0 = 1 + j * k, 1 + i * k
            if np.isnan(xcrest[j, i]):
                for t in range(k + 2 * margin):
                    full[t] = max(zbig[r0 + t, margin + c0 - 1], zbig[r0 + t, margin + c0])
                for q in range(k):
                    near, far = zbig[margin + r0 + q, margin + c0], zbig[margin + r0 + q, margin + c0 - 1]
                    weight[q] = _lined(npix[r0 + q, c0 - 1] if far > near else npix[r0 + q, c0], nman[j, i]) if lined else 1.0
                _raise_top(full, margin, k, zfx, efx, ftabx, j, i, pixel, nman[j, i], weight, xlen[j, i], e_hi)
                e = min(margin, int(np.ceil(beta * efx[j, i] / pixel)))
                _local_radius_conveyance(full[margin - e : margin + k + e], e, e + k, zfx[j, i], efx[j, i], pixel, 1.0 / nman[j, i], weight, xlen[j, i], beta, ftabx[j, i])
            if np.isnan(ycrest[j, i]):
                for t in range(k + 2 * margin):
                    full[t] = max(zbig[margin + r0 - 1, c0 + t], zbig[margin + r0, c0 + t])
                for q in range(k):
                    near, far = zbig[margin + r0, margin + c0 + q], zbig[margin + r0 - 1, margin + c0 + q]
                    weight[q] = _lined(npix[r0 - 1, c0 + q] if far > near else npix[r0, c0 + q], nman[j, i]) if lined else 1.0
                _raise_top(full, margin, k, zfy, efy, ftaby, j, i, pixel, nman[j, i], weight, ylen[j, i], e_hi)
                e = min(margin, int(np.ceil(beta * efy[j, i] / pixel)))
                _local_radius_conveyance(full[margin - e : margin + k + e], e, e + k, zfy[j, i], efy[j, i], pixel, 1.0 / nman[j, i], weight, ylen[j, i], beta, ftaby[j, i])


@njit(cache=True)
def window_top(line: np.ndarray, zf: float, top: float, e_hi: float) -> float:
    """A face's table top in local-radius mode (W49): its own top, or the relief of its window over its invert if
    higher, at most ``e_hi``. NaN ground is not relief."""
    hi = -np.inf
    for t in range(line.size):
        if line[t] > hi:
            hi = line[t]
    return max(top, min(hi - zf, e_hi))


@njit(cache=True)
def _raise_top(full, margin, k, zf, ef, ftab, j, i, pixel, n, weight, length, e_hi) -> None:
    """Rebuild one lattice face's table at its window's top (W49); the conveyance column is overwritten after."""
    top = window_top(full, zf[j, i], ef[j, i], e_hi)
    if top > ef[j, i]:
        prof = full[margin : margin + k].copy()
        zf[j, i], ef[j, i] = _face_table(prof, np.nan, pixel, 1.0 / n, weight, length, top, e_hi, ftab[j, i])
