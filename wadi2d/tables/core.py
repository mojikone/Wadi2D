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
    length: float,
    e_lo: float,
    e_hi: float,
    tab: np.ndarray,
) -> tuple[float, float]:
    """Fill ``tab`` (rows, 2) for one face from its along-face ground. Returns invert and table top."""
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


@njit(cache=True, parallel=True)
def tile_tables(
    z: np.ndarray,
    k: int,
    tile: int,
    pixel: float,
    nman: np.ndarray,
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
    pixel wide, on either side of it.
    """
    rows = dtab.shape[2]
    for j in prange(tile):
        prof = np.empty(k)
        for i in range(tile):
            r0, c0 = 1 + j * k, 1 + i * k
            cell = z[r0 : r0 + k, c0 : c0 + k]
            zmin[j, i], relmean[j, i], hc[j, i] = _cell_table(cell, rows, dtab[j, i])
            for q in range(k):
                prof[q] = max(z[r0 + q, c0 - 1], z[r0 + q, c0])
            zfx[j, i], efx[j, i] = _face_table(
                prof, xcrest[j, i], pixel, 1.0 / nman[j, i], xlen[j, i], e_lo, e_hi, ftabx[j, i]
            )
            for q in range(k):
                prof[q] = max(z[r0 - 1, c0 + q], z[r0, c0 + q])
            zfy[j, i], efy[j, i] = _face_table(
                prof, ycrest[j, i], pixel, 1.0 / nman[j, i], ylen[j, i], e_lo, e_hi, ftaby[j, i]
            )
