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

// The masked gaps summed in the kernel, in the order CUB's segmented sum adds a row that fits one tile of its
// 256 threads (what CuPy's sum along a row calls): each thread its pixels j, j + 256, ... in turn, then each warp
// by halving down (peers 1, 2, 4, 8, 16 lanes on, while they hold items), then the warps' sums one after another,
// then zero plus that. Used only where a check against CuPy's own sum, on this card, gave the same bits.
extern "C" __global__ void masked_sum(const float* relief, const long long* rows, const float* offset,
                                      float* total, long long* count, int pixels) {
    __shared__ long long part[256];
    __shared__ float warps[8];
    long long r = blockIdx.x;
    long long row = rows[r];
    float at = offset[row];
    const float* own = relief + row * (long long)pixels;
    int t = threadIdx.x;
    float acc = 0.0f;
    long long under = 0;
    for (int j = t; j < pixels; j += 256) {
        float gap = at - own[j];
        float wet = gap > 0.0f ? 1.0f : 0.0f;
        float v = gap * wet;
        acc = j == t ? v : acc + v;
        under += gap > 0.0f ? 1 : 0;
    }
    int valid = pixels < 256 ? pixels : 256;
    int lane = t & 31, warp = t >> 5;
    int warp_valid = valid - warp * 32;
    warp_valid = warp_valid < 0 ? 0 : (warp_valid > 32 ? 32 : warp_valid);
    for (int step = 1; step < 32; step <<= 1) {
        float peer = __shfl_down_sync(0xffffffffu, acc, step);
        if (lane + step < warp_valid) acc = peer + acc;
    }
    if (lane == 0) warps[warp] = acc;
    part[t] = under;
    __syncthreads();
    for (int s = 128; s > 0; s >>= 1) {
        if (t < s) part[t] += part[t + s];
        __syncthreads();
    }
    if (t == 0) {
        float sum = warps[0];
        for (int w = 1; w < 8; ++w) {
            if (w * 32 < valid) sum = sum + warps[w];
        }
        total[r] = 0.0f + sum;
        count[r] = part[0];
    }
}
"""

STEP_SOURCE = r"""
// One Newton step of every cell still moving, whole in the kernel: the sum of masked_sum, the step, the offset and
// whether the cell goes on, as the array steps take them; a cell that has stopped is left as it is.
extern "C" __global__ void newton_step(const float* relief, float* offset, const float* water, bool* moving,
                                       int pixels, float tolerance) {
    __shared__ long long part[256];
    __shared__ float warps[8];
    long long r = blockIdx.x;
    if (!moving[r]) return;
    float at = offset[r];
    const float* own = relief + r * (long long)pixels;
    int t = threadIdx.x;
    float acc = 0.0f;
    long long under = 0;
    for (int j = t; j < pixels; j += 256) {
        float gap = at - own[j];
        float wet = gap > 0.0f ? 1.0f : 0.0f;
        float v = gap * wet;
        acc = j == t ? v : acc + v;
        under += gap > 0.0f ? 1 : 0;
    }
    int valid = pixels < 256 ? pixels : 256;
    int lane = t & 31, warp = t >> 5;
    int warp_valid = valid - warp * 32;
    warp_valid = warp_valid < 0 ? 0 : (warp_valid > 32 ? 32 : warp_valid);
    for (int step = 1; step < 32; step <<= 1) {
        float peer = __shfl_down_sync(0xffffffffu, acc, step);
        if (lane + step < warp_valid) acc = peer + acc;
    }
    if (lane == 0) warps[warp] = acc;
    part[t] = under;
    __syncthreads();
    for (int s = 128; s > 0; s >>= 1) {
        if (t < s) part[t] += part[t + s];
        __syncthreads();
    }
    if (t == 0) {
        float sum = warps[0];
        for (int w = 1; w < 8; ++w) {
            if (w * 32 < valid) sum = sum + warps[w];
        }
        float total = 0.0f + sum;
        long long count = part[0] > 1 ? part[0] : 1;
        float move = (total - water[r]) / (float)count;
        offset[r] = at - move;
        moving[r] = move > tolerance;
    }
}
"""

CHECK_EVERY = 3
"""Newton steps between the looks at whether any cell still moves: each look waits for the card."""

ONE_TILE = 256 * 16
"""Pixels a cell may hold for :func:`masked_sum`'s order: one tile of CUB's segmented sum for float32."""

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
        module = xp.RawModule(code=SOURCE + STEP_SOURCE + RAISE_SOURCE, options=("--fmad=false",))
        for each in ("masked_gap", "masked_sum", "newton_step", "may_raise"):
            _KERNEL[each] = module.get_function(each)
    return _KERNEL[name]


def _masked_gap(xp):
    return _function(xp, "masked_gap")


CHECK_ROWS = 512
_SUMS_AGREE: dict[int, bool] = {}


def sums_agree(xp, pixels: int) -> bool:
    """Whether :func:`masked_sum` gives CuPy's own sum of the masked gaps to the bit for cells of ``pixels``, on
    this card and this CuPy: tried once a size on gaps that are wet, dry and mixed, of every scale a fill meets.
    Where it does not, the fill keeps the masked array and CuPy's sum."""
    if pixels not in _SUMS_AGREE:
        agree = 0 < pixels < ONE_TILE
        if agree:
            rng = np.random.default_rng(pixels)
            scale = np.exp(rng.uniform(np.log(1e-4), np.log(50.0), (CHECK_ROWS, 1)))
            relief = xp.asarray((rng.normal(0.0, 1.0, (CHECK_ROWS, pixels)) * scale).astype(np.float32))
            offset = xp.asarray((rng.normal(0.0, 1.0, CHECK_ROWS) * scale[:, 0]).astype(np.float32))
            rows = xp.arange(CHECK_ROWS)
            gap = offset[:, None] - relief
            want = (gap * (gap > 0.0)).sum(axis=1)
            got = xp.empty(CHECK_ROWS, xp.float32)
            count = xp.empty(CHECK_ROWS, xp.int64)
            _function(xp, "masked_sum")((CHECK_ROWS,), (THREADS,), (relief, rows, offset, got, count, np.int32(pixels)))
            agree = bool(xp.all(want.view(xp.int32) == got.view(xp.int32)))
            agree = agree and bool(xp.all(count == (gap > 0.0).sum(axis=1)))
        _SUMS_AGREE[pixels] = agree
    return _SUMS_AGREE[pixels]


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
    fused = sums_agree(xp, pixels)  # the sum in the kernel too, where it is CuPy's to the bit
    if fused:  # the whole step in the kernel, the cells that stopped left alone, a look every few steps
        still = xp.ones(relief.shape[0], bool)
        water = xp.ascontiguousarray(water, xp.float32)
        for n in range(steps):
            _function(xp, "newton_step")((relief.shape[0],), (THREADS,), (relief, offset, water, still, np.int32(pixels), np.float32(tolerance)))
            if (n + 1) % CHECK_EVERY == 0 and n + 1 < steps and not bool(still.any()):
                break
        return offset
    kernel = _function(xp, "masked_sum" if fused else "masked_gap")
    buffer = xp.empty(relief.shape[0] if fused else relief.shape, xp.float32)
    under = xp.empty(relief.shape[0], xp.int64)
    for _ in range(steps):
        m = int(moving.size)
        masked, count = buffer[:m], under[:m]
        kernel((m,), (THREADS,), (relief, moving, offset, masked, count, np.int32(pixels)))
        excess = (masked if fused else masked.sum(axis=1)) - water[moving]
        step = excess / xp.maximum(count, 1).astype(xp.float32)
        offset[moving] = offset[moving] - step
        going = step > tolerance
        if not bool(going.any()):
            break
        moving = moving[going]
    return offset


__all__ = ["newton_card"]
