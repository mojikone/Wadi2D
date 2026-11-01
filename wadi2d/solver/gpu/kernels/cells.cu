// Cell kernels: positivity ratio, continuity and level lookup; halo exchange; boundary cells; wet-tile flags.

// r: the share of its demanded outflow each own cell can actually give.
extern "C" __global__ void limit(const int* __restrict__ active, const float dt, const float* __restrict__ h,
                                 const float* __restrict__ qx1, const float* __restrict__ qy1,
                                 float* __restrict__ r) {
    const int t = active[blockIdx.x];
    const int i = threadIdx.x;
    const float area = P.dx * P.dx;
    for (int c = 0; c < CELLS_PER_THREAD; ++c) {
        const int j = threadIdx.y * CELLS_PER_THREAD + c;
        const int k = t * STRIDE2 + (j + HALO) * STRIDE + i + HALO;
        const float out = fmaxf(qx1[k + 1], 0.0f) + fmaxf(-qx1[k], 0.0f) + fmaxf(qy1[k + STRIDE], 0.0f) +
                          fmaxf(-qy1[k], 0.0f);
        const float have = fmaxf(h[k], 0.0f) * area;
        r[k] = out * dt > have ? have / (out * dt) : 1.0f;
    }
}

// Scaled face discharge: the upwind cell's ratio applies, so both neighbours see the same number.
__device__ __forceinline__ float scaled(const float q, const float rl, const float rr) {
    return q * (q > 0.0f ? rl : rr);
}

extern "C" __global__ void update(const int* __restrict__ active, const float dt, const int want_wet,
                                  const float* __restrict__ qx1, const float* __restrict__ qy1,
                                  const float* __restrict__ r, const float* __restrict__ src,
                                  const float* __restrict__ Hc, const float* __restrict__ dtab,
                                  float* __restrict__ h, float* __restrict__ d, float* __restrict__ qx,
                                  float* __restrict__ qy, int* __restrict__ wet) {
    const int t = active[blockIdx.x];
    const int i = threadIdx.x;
    const float area = P.dx * P.dx;
    int any = 0;
    for (int c = 0; c < CELLS_PER_THREAD; ++c) {
        const int j = threadIdx.y * CELLS_PER_THREAD + c;
        const int k = t * STRIDE2 + (j + HALO) * STRIDE + i + HALO;
        const int id = t * TILE2 + j * TILE + i;
        const float rc = r[k];
        const float qw = scaled(qx1[k], r[k - 1], rc);
        const float qe = scaled(qx1[k + 1], rc, r[k + 1]);
        const float qn = scaled(qy1[k], r[k - STRIDE], rc);
        const float qs = scaled(qy1[k + STRIDE], rc, r[k + STRIDE]);
        qx[k] = qw;
        qy[k] = qn;
        const float hn = fmaxf(h[k] - dt * (qe - qw + qs - qn) / area + dt * src[k], 0.0f);
        h[k] = hn;
        d[k] = cell_level(hn, Hc[id], dtab + P.rows * id);
        any |= hn > 0.0f;
    }
    if (want_wet && any) wet[t] = 1;
}

// Fill the halos of the active tiles from the owning tiles. dst offsets are fixed; src holds one entry per halo slot.
extern "C" __global__ void exchange(const int* __restrict__ active, const int* __restrict__ slot,
                                    const int* __restrict__ src, const int nhalo, float* a, float* b, float* c,
                                    float* e) {
    const int t = active[blockIdx.x];
    const int n = blockDim.x * threadIdx.y + threadIdx.x;
    if (n >= nhalo) return;
    const int dst = t * STRIDE2 + slot[n];
    const int s = src[(t - 1) * nhalo + n];
    a[dst] = a[s];
    if (b) b[dst] = b[s];
    if (c) c[dst] = c[s];
    if (e) e[dst] = e[s];
}

// Boundary cells: kind 0 fixed level (d0, h0); kind 1 free (dry); kind 2 follows its interior neighbour, lowered.
extern "C" __global__ void boundary(const int n, const int* __restrict__ cell, const int* __restrict__ ref,
                                    const int* __restrict__ kind, const float* __restrict__ d0,
                                    const float* __restrict__ h0, float* __restrict__ h, float* __restrict__ d) {
    const int m = blockIdx.x * blockDim.x + threadIdx.x;
    if (m >= n) return;
    const int k = cell[m];
    if (kind[m] == 0) {
        h[k] = h0[m];
        d[k] = d0[m];
    } else if (kind[m] == 1) {
        h[k] = 0.0f;
        d[k] = 0.0f;
    } else {
        h[k] = h[ref[m]];
        d[k] = fmaxf(d[ref[m]] + d0[m], 0.0f);
    }
}
