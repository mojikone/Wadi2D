# Wadi2D. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The sums of a strip's pixel maps, in one order on both backends (W86).

:class:`wadi2d.strips.pixels.StripMaxima` sums a cell's pixels with scatter-adds. On the host that is NumPy's
``add.at``, one addition at a time in the pixels' order, about a microsecond a pixel and map. On the card it is an
atomic add from 1,600 threads to one address a cell: they queue behind each other, 100 ns a pixel and map on the
Bidah window, hours for Block 2, and the order they arrive in changes from run to run, so two runs of the same job
did not give the same last digits.

Here each sum is a loop over what it sums, in the order ``add.at`` takes it: a cell's pixels from first to last, a
node's cells by rising number, a pixel's node slots as NumPy's pairwise sum takes them. The Numba kernels are the
host's, the CUDA kernels the card's, statement for statement, with float32 kept at every step and no multiply fused
into an add. So the sums are what ``add.at`` gave to the digit, the card's maps are the host's, and a run gives the
same rasters twice.

One step of the rule itself is changed, on the owner's word (2026-11-15): a cell's Newton fill stops on the cell's
own step, as a square cell's does, where the old fill went on until every cell of the strip had settled. A cell's
pixels then do not depend on which other cells are worked with it, so a strip cut into any blocks gives one answer.
Against the old fill a cell's offset moves by less than the fill's tolerance, 0.1 mm.
"""

from __future__ import annotations

import numpy as np
from numba import njit, prange

UNROLL = 8
"""NumPy's pairwise sum adds fewer than this many values one after another, and this many at a time above it."""
PAIRWISE_BLOCK = 128
"""And halves a run longer than this; a ring has far fewer nodes, which :func:`check_width` holds it to."""
THREADS = 128
"""CUDA threads a block."""


def check_width(width: int) -> None:
    if width > PAIRWISE_BLOCK:
        raise ValueError(f"a strip cell of {width} nodes is beyond the pixel maps' sum, {PAIRWISE_BLOCK} at most")


@njit(cache=True, nogil=True, inline="always")
def _slot_sum(slots, weights, c, i, width):
    """sum(slots[c, k] * weights[i, k]) in float32, as NumPy sums the row of products."""
    zero = np.float32(0.0)
    if width < UNROLL:
        res = zero
        for k in range(width):
            res += slots[c, k] * weights[i, k]
        return res
    r0 = slots[c, 0] * weights[i, 0]
    r1 = slots[c, 1] * weights[i, 1]
    r2 = slots[c, 2] * weights[i, 2]
    r3 = slots[c, 3] * weights[i, 3]
    r4 = slots[c, 4] * weights[i, 4]
    r5 = slots[c, 5] * weights[i, 5]
    r6 = slots[c, 6] * weights[i, 6]
    r7 = slots[c, 7] * weights[i, 7]
    k = UNROLL
    while k < width - width % UNROLL:
        r0 += slots[c, k] * weights[i, k]
        r1 += slots[c, k + 1] * weights[i, k + 1]
        r2 += slots[c, k + 2] * weights[i, k + 2]
        r3 += slots[c, k + 3] * weights[i, k + 3]
        r4 += slots[c, k + 4] * weights[i, k + 4]
        r5 += slots[c, k + 5] * weights[i, k + 5]
        r6 += slots[c, k + 6] * weights[i, k + 6]
        r7 += slots[c, k + 7] * weights[i, k + 7]
        k += UNROLL
    res = ((r0 + r1) + (r2 + r3)) + ((r4 + r5) + (r6 + r7))
    while k < width:
        res += slots[c, k] * weights[i, k]
        k += 1
    return res


@njit(cache=True, nogil=True, parallel=True)
def _at_pixels(slots, cell, weights, out):
    width = slots.shape[1]
    for i in prange(cell.size):
        out[i] = _slot_sum(slots, weights, cell[i], i, width)


@njit(cache=True, nogil=True, parallel=True)
def _cell_sums(ptr, values, out):
    for c in prange(ptr.size - 1):
        total = np.float32(0.0)
        for i in range(ptr[c], ptr[c + 1]):
            total += values[i]
        out[c] = total


@njit(cache=True, nogil=True, parallel=True)
def _newton(ptr, relief, water, offset, step, moving, tolerance):
    one = np.float32(1.0)
    for c in prange(ptr.size - 1):
        if not moving[c]:
            continue
        at = offset[c]
        held = np.float32(0.0)
        count = np.float32(0.0)
        for i in range(ptr[c], ptr[c + 1]):
            gap = at - relief[i]
            if gap > 0.0:
                held += gap
                count += one
        move = (held - water[c]) / max(count, one)
        moved = at - move
        step[c] = move
        moving[c] = abs(move) > tolerance
        offset[c] = moved


@njit(cache=True, nogil=True)
def _label_sums(label, own, weight, total, count):
    for i in range(label.size):
        total[label[i]] += own[i] * weight[i]
        count[label[i]] += weight[i]


CUDA_SOURCE = r"""
static __device__ float slot_sum(const float* v, const float* w, int width) {
    if (width < 8) {
        float res = 0.0f;
        for (int k = 0; k < width; ++k) res += v[k] * w[k];
        return res;
    }
    float r0 = v[0] * w[0], r1 = v[1] * w[1], r2 = v[2] * w[2], r3 = v[3] * w[3];
    float r4 = v[4] * w[4], r5 = v[5] * w[5], r6 = v[6] * w[6], r7 = v[7] * w[7];
    int k = 8;
    for (; k < width - width % 8; k += 8) {
        r0 += v[k] * w[k];         r1 += v[k + 1] * w[k + 1]; r2 += v[k + 2] * w[k + 2]; r3 += v[k + 3] * w[k + 3];
        r4 += v[k + 4] * w[k + 4]; r5 += v[k + 5] * w[k + 5]; r6 += v[k + 6] * w[k + 6]; r7 += v[k + 7] * w[k + 7];
    }
    float res = ((r0 + r1) + (r2 + r3)) + ((r4 + r5) + (r6 + r7));
    for (; k < width; ++k) res += v[k] * w[k];
    return res;
}

extern "C" __global__ void at_pixels(const float* slots, const int* cell, const float* weights, float* out,
                                     long long n, int width) {
    long long i = (long long)blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= n) return;
    out[i] = slot_sum(slots + (long long)cell[i] * width, weights + i * width, width);
}

extern "C" __global__ void cell_sums(const long long* ptr, const float* values, float* out, long long n) {
    long long c = (long long)blockIdx.x * blockDim.x + threadIdx.x;
    if (c >= n) return;
    float total = 0.0f;
    for (long long i = ptr[c]; i < ptr[c + 1]; ++i) total += values[i];
    out[c] = total;
}

extern "C" __global__ void newton(const long long* ptr, const float* relief, const float* water, float* offset,
                                  float* step, bool* moving, long long n, float tolerance) {
    long long c = (long long)blockIdx.x * blockDim.x + threadIdx.x;
    if (c >= n || !moving[c]) return;
    float at = offset[c], held = 0.0f, count = 0.0f;
    for (long long i = ptr[c]; i < ptr[c + 1]; ++i) {
        float gap = at - relief[i];
        if (gap > 0.0f) { held += gap; count += 1.0f; }
    }
    float move = (held - water[c]) / fmaxf(count, 1.0f);
    float moved = at - move;
    step[c] = move;
    moving[c] = fabsf(move) > tolerance;
    offset[c] = moved;
}

// incidences sorted by label, and within a label by their own number: each run summed from its first
extern "C" __global__ void label_sums(const long long* order, const long long* label, const float* own,
                                      const float* weight, float* total, float* count, long long n) {
    long long j = (long long)blockIdx.x * blockDim.x + threadIdx.x;
    if (j >= n) return;
    long long mine = label[order[j]];
    if (j > 0 && label[order[j - 1]] == mine) return;
    float sum = 0.0f, held = 0.0f;
    for (long long k = j; k < n && label[order[k]] == mine; ++k) {
        long long i = order[k];
        sum += own[i] * weight[i];
        held += weight[i];
    }
    total[mine] = sum;
    count[mine] = held;
}
"""


class StripKernels:
    """The four sums on ``xp``'s device: NumPy arrays in and out on the host, CuPy arrays on the card."""

    def __init__(self, xp) -> None:
        self.xp = xp
        self.cuda = None
        if xp is not np:
            module = xp.RawModule(code=CUDA_SOURCE, options=("--fmad=false",))  # a*b+c stays two roundings
            self.cuda = {name: module.get_function(name) for name in ("at_pixels", "cell_sums", "newton", "label_sums")}

    def _launch(self, name: str, n: int, args: tuple) -> None:
        if n > 0:
            self.cuda[name]((-(-n // THREADS),), (THREADS,), args)

    def at_pixels(self, slots, cell, weights):
        """A node value at every pixel: the pixel's cell's slots times the pixel's weights, summed."""
        xp = self.xp
        out = xp.empty(cell.size, xp.float32)
        if self.cuda is None:
            _at_pixels(slots, cell, weights, out)
        else:
            self._launch("at_pixels", cell.size, (slots, cell, weights, out, np.int64(cell.size), np.int32(slots.shape[1])))
        return out

    def cell_sums(self, ptr, values):
        """Each cell's sum of its pixels' values, the pixels from first to last."""
        xp = self.xp
        out = xp.empty(ptr.size - 1, xp.float32)
        if self.cuda is None:
            _cell_sums(ptr, values, out)
        else:
            self._launch("cell_sums", ptr.size - 1, (ptr, values, out, np.int64(ptr.size - 1)))
        return out

    def newton(self, ptr, relief, water, offset, step, moving, tolerance: float) -> None:
        """One Newton step of the fill for every cell still moving, in place: its offset, its step, and whether
        that step was over ``tolerance``, so the cell goes on."""
        limit = np.float32(tolerance)
        if self.cuda is None:
            _newton(ptr, relief, water, offset, step, moving, limit)
        else:
            self._launch("newton", ptr.size - 1, (ptr, relief, water, offset, step, moving, np.int64(ptr.size - 1), limit))

    def label_order(self, label):
        """The incidences by label and, in a label, by their own number: what :meth:`label_sums` on the card walks."""
        if self.cuda is None:
            return None
        xp = self.xp
        return xp.argsort(label * label.size + xp.arange(label.size, dtype=label.dtype))

    def label_sums(self, label, order, own, weight):
        """Per label, the sum of ``own * weight`` and of ``weight`` over its incidences, by rising number."""
        xp = self.xp
        total = xp.zeros(label.size, xp.float32)
        count = xp.zeros(label.size, xp.float32)
        if self.cuda is None:
            _label_sums(label, own, weight, total, count)
        else:
            self._launch("label_sums", label.size, (order, label, own, weight, total, count, np.int64(label.size)))
        return total, count


__all__ = ["StripKernels", "check_width"]
