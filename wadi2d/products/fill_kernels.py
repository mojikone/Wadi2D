"""The square cells' Newton fill on the card in fewer passes over memory, with the same numbers (W93).

:func:`wadi2d.products.surface.fill_offset` takes each Newton step as five array operations over the pixels of the
cells still moving, and copies those cells' pixels out again as the others stop: on Block 2 at the 0.5 m pixel the
fill was most of a saved map's time. Here one kernel reads a moving cell's pixels in place and writes the step's
masked gaps, ``gap * (gap > 0)``, with the count of pixels under the water. The sum of the gaps is then CuPy's own
``sum`` over an array of the same values, shape and layout as before, so the fill gives the old offsets to the last
digit; the count is a whole number, the same however it is added up.
"""

from __future__ import annotations

import numpy as np

THREADS = 256
"""CUDA threads a cell's pixels are read by; a power of two for the count's halving."""

SOURCE = r"""
extern "C" __global__ void masked_gap(const float* relief, const long long* rows, const float* offset,
                                      float* masked, long long* count, int pixels) {
    __shared__ long long part[256];
    long long r = blockIdx.x;
    long long row = rows[r];
    float at = offset[row];
    const float* own = relief + row * (long long)pixels;
    float* out = masked + r * (long long)pixels;
    long long under = 0;
    for (int j = threadIdx.x; j < pixels; j += blockDim.x) {
        float gap = at - own[j];
        float wet = gap > 0.0f ? 1.0f : 0.0f;
        out[j] = gap * wet;
        under += gap > 0.0f ? 1 : 0;
    }
    part[threadIdx.x] = under;
    __syncthreads();
    for (int s = blockDim.x / 2; s > 0; s >>= 1) {
        if (threadIdx.x < s) part[threadIdx.x] += part[threadIdx.x + s];
        __syncthreads();
    }
    if (threadIdx.x == 0) count[r] = part[0];
}
"""

RAISE_SOURCE = r"""
// Whether a map may raise a cell's held maxima anywhere: the Newton fill walks down from start, the offset where
// every pixel is wet, so no pixel is deeper than start - relief, and the speed at a pixel is a weighted mean of its
// corners', never over their largest. Margins far over float32's rounding; a NaN anywhere asks for the fill.
extern "C" __global__ void may_raise(const float* relief, const float* start, const float* top_speed,
                                     const long long* on, const float* held_depth, const float* held_speed,
                                     const float* held_dv, int* need, int pixels, float floor_depth) {
    __shared__ int part[256];
    long long r = blockIdx.x;
    const float* own = relief + r * (long long)pixels;
    long long at = on[r] * (long long)pixels;
    float c = start[r];
    float s = top_speed[r] * 1.00001f + 1e-7f;
    int any = 0;
    for (int j = threadIdx.x; j < pixels; j += blockDim.x) {
        float b = c - own[j];
        b = b + fabsf(b) * 1e-3f + 1e-3f;
        if (!(b <= 0.0f)) {
            if (!(b <= held_depth[at + j])) any = 1;
            if (!(b < floor_depth)) {
                if (!(s <= held_speed[at + j])) any = 1;
                if (!(b * s * 1.00001f <= held_dv[at + j])) any = 1;
            }
        }
    }
    part[threadIdx.x] = any;
    __syncthreads();
    for (int k = blockDim.x / 2; k > 0; k >>= 1) {
        if (threadIdx.x < k) part[threadIdx.x] |= part[threadIdx.x + k];
        __syncthreads();
    }
    if (threadIdx.x == 0) need[r] = part[0];
}
"""

_KERNEL: dict = {}


def _function(xp, name: str):
    if name not in _KERNEL:
        module = xp.RawModule(code=SOURCE + RAISE_SOURCE, options=("--fmad=false",))
        for each in ("masked_gap", "may_raise"):
            _KERNEL[each] = module.get_function(each)
    return _KERNEL[name]


def _masked_gap(xp):
    return _function(xp, "masked_gap")


def may_raise(xp, relief, mean_depth, top_speed, on, held, floor_depth: float):
    """Per cell of ``relief`` (its rows), whether this map may raise any of its pixels' three held maxima (W93):
    the cells that cannot are not filled, and what they hold stays as it is, as the fill would have left it.
    ``held`` are the batch's (depth, speed, depth x speed) arrays and ``on`` the rows of the cells in them."""
    m, pixels = relief.shape
    need = xp.zeros(m, xp.int32)
    if m == 0:
        return need.astype(bool)
    start = (relief.mean(axis=1) + mean_depth).astype(xp.float32)
    relief = xp.ascontiguousarray(relief)
    depth, speed, dv = (xp.ascontiguousarray(a) for a in held)
    args = (relief, start, xp.ascontiguousarray(top_speed, xp.float32), xp.ascontiguousarray(on, xp.int64))
    _function(xp, "may_raise")((m,), (THREADS,), (*args, depth, speed, dv, need, np.int32(pixels), np.float32(floor_depth)))
    return need.astype(bool)


def newton_card(xp, relief, mean_depth, steps: int, tolerance: float):
    """The offset per cell of :func:`wadi2d.products.surface.fill_offset` for ``relief`` on the card, its steps
    statement for statement: the same start, the same sums, each cell stopping on its own step."""
    pixels = relief.shape[1]
    water = mean_depth * pixels
    offset = relief.mean(axis=1) + mean_depth
    moving = xp.arange(relief.shape[0])
    if relief.shape[0] == 0 or pixels == 0:
        return offset
    relief = xp.ascontiguousarray(relief)
    kernel = _masked_gap(xp)
    buffer = xp.empty(relief.shape, xp.float32)
    under = xp.empty(relief.shape[0], xp.int64)
    for _ in range(steps):
        m = int(moving.size)
        masked, count = buffer[:m], under[:m]
        kernel((m,), (THREADS,), (relief, moving, offset, masked, count, np.int32(pixels)))
        excess = masked.sum(axis=1) - water[moving]
        step = excess / xp.maximum(count, 1).astype(xp.float32)
        offset[moving] = offset[moving] - step
        going = step > tolerance
        if not bool(going.any()):
            break
        moving = moving[going]
    return offset


__all__ = ["newton_card"]
