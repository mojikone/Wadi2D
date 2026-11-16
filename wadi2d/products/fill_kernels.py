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

_KERNEL: dict = {}


def _masked_gap(xp):
    if "masked_gap" not in _KERNEL:
        module = xp.RawModule(code=SOURCE, options=("--fmad=false",))
        _KERNEL["masked_gap"] = module.get_function("masked_gap")
    return _KERNEL["masked_gap"]


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
