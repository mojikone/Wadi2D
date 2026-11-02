// Local time stepping: what the level stepper adds to the face and cell kernels. Those stay as they are: a level is a
// list of tiles and a dt. The Numba twin is solver/cpu/levels.py; keep the statement order the same.
//
// An edge joins a fine tile to a tile one time level coarser. Its faces are stepped at the fine rate, whoever owns
// them. The coarse tile goes first over its whole step, taking the edge discharge of that moment as its estimate; the
// fine tile then reads the coarse level interpolated in time, and what the fine steps actually carried beyond the
// estimate goes into the coarse cell's residual. So no water is lost across an edge however the levels change.
//
// An edge row is (fine tile, side of the fine tile, coarse tile, edge number). Sides: 0 west, 1 north, 2 east, 3 south.

// The face q along a side, in the state arrays of tile t.
__device__ __forceinline__ int edge_face(const int t, const int side, const int q) {
    const int base = t * STRIDE2;
    if (side == 0) return base + (q + HALO) * STRIDE + HALO;
    if (side == 1) return base + HALO * STRIDE + q + HALO;
    if (side == 2) return base + (q + HALO) * STRIDE + HALO + TILE;
    return base + (HALO + TILE) * STRIDE + q + HALO;
}

// The cell of the coarse tile that the fine tile's side q looks at.
__device__ __forceinline__ int edge_cell(const int c, const int side, const int q) {
    const int base = c * STRIDE2;
    if (side == 0) return base + (q + HALO) * STRIDE + HALO + TILE - 1;
    if (side == 1) return base + (HALO + TILE - 1) * STRIDE + q + HALO;
    if (side == 2) return base + (q + HALO) * STRIDE + HALO;
    return base + HALO * STRIDE + q + HALO;
}

// Faces owned by the coarse tile: the fine tile's east or south side, stepped at the fine rate. One block per edge.
extern "C" __global__ void strips(
    const int* __restrict__ edges, const float dt, const int want_wave, const float* __restrict__ om,
    const float* __restrict__ h, const float* __restrict__ d, const float* __restrict__ u,
    const float* __restrict__ v, const float* __restrict__ mx, const float* __restrict__ my,
    const float* __restrict__ qx, const float* __restrict__ qy,
    const float* __restrict__ flx, const float* __restrict__ frx, const float* __restrict__ glx,
    const float* __restrict__ grx, const float* __restrict__ efx, const float* __restrict__ cwx,
    const float* __restrict__ ftabx,
    const float* __restrict__ fly, const float* __restrict__ fry, const float* __restrict__ gly,
    const float* __restrict__ gry, const float* __restrict__ efy, const float* __restrict__ cwy,
    const float* __restrict__ ftaby,
    float* __restrict__ u1, float* __restrict__ v1, float* __restrict__ mx1, float* __restrict__ my1,
    float* __restrict__ qx1, float* __restrict__ qy1, float* __restrict__ wave) {
    const int* e = edges + 4 * blockIdx.x;
    const int fine = e[0];
    const int side = e[1];
    const int t = e[2];
    const int q = threadIdx.x;
    float w;
    if (side == 2) {
        const int k = t * STRIDE2 + (q + HALO) * STRIDE + HALO;
        const int id = t * TILE2 + q * TILE;
        w = face_step<1, STRIDE>(k, id, dt, P.dx, want_wave, om, h, d, u, mx, qx, qy, v, flx, frx, glx, grx, efx, cwx, ftabx,
                                 u1, mx1, qx1);
    } else {
        const int k = t * STRIDE2 + HALO * STRIDE + q + HALO;
        const int id = t * TILE2 + q;
        w = face_step<STRIDE, 1>(k, id, dt, P.dx, want_wave, om, h, d, v, my, qy, qx, u, fly, fry, gly, gry, efy, cwy, ftaby,
                                 v1, my1, qy1);
    }
    if (want_wave) {
        atomic_fmax(wave + t, w);
        atomic_fmax(wave + fine, w);
    }
}

// Halo of the listed tiles, reading a coarser tile at time n through its old and new values.
extern "C" __global__ void halo_levels(const int* __restrict__ active, const int* __restrict__ slot,
                                       const int* __restrict__ src, const int nhalo,
                                       const int* __restrict__ level, const int n, float* h,
                                       const float* __restrict__ h0, float* d, const float* __restrict__ d0,
                                       float* u, float* v, float* qx, float* qy) {
    const int t = active[blockIdx.x];
    const int m = blockDim.x * threadIdx.y + threadIdx.x;
    if (m >= nhalo) return;
    const int dst = t * STRIDE2 + slot[m];
    const int s = src[(t - 1) * nhalo + m];
    const int span = 1 << level[s / STRIDE2];
    const int part = n & (span - 1);
    if (part == 0) {
        h[dst] = h[s];
        d[dst] = d[s];
    } else {
        const float w = (float)part / (float)span;
        h[dst] = h0[s] + w * (h[s] - h0[s]);
        d[dst] = d0[s] + w * (d[s] - d0[s]);
    }
    u[dst] = u[s];
    v[dst] = v[s];
    qx[dst] = qx[s];
    qy[dst] = qy[s];
}

// The values a coarse tile had before this step, for the fine tiles beside it.
extern "C" __global__ void save_old(const int* __restrict__ active, const float* __restrict__ h,
                                    const float* __restrict__ d, float* __restrict__ h0, float* __restrict__ d0) {
    const int t = active[blockIdx.x];
    const int i = threadIdx.x;
    for (int c = 0; c < CELLS_PER_THREAD; ++c) {
        const int j = threadIdx.y * CELLS_PER_THREAD + c;
        const int k = t * STRIDE2 + (j + HALO) * STRIDE + i + HALO;
        h0[k] = h[k];
        d0[k] = d[k];
    }
}

// The swap of the uniform step, tile by tile: tiles out of step keep their faces.
extern "C" __global__ void commit(const int* __restrict__ active, const float* __restrict__ u1,
                                  const float* __restrict__ v1, const float* __restrict__ mx1,
                                  const float* __restrict__ my1, float* __restrict__ u, float* __restrict__ v,
                                  float* __restrict__ mx, float* __restrict__ my) {
    const int t = active[blockIdx.x];
    const int i = threadIdx.x;
    for (int c = 0; c < CELLS_PER_THREAD; ++c) {
        const int j = threadIdx.y * CELLS_PER_THREAD + c;
        const int k = t * STRIDE2 + (j + HALO) * STRIDE + i + HALO;
        u[k] = u1[k];
        v[k] = v1[k];
        mx[k] = mx1[k];
        my[k] = my1[k];
    }
}

// The same for the faces ``strips`` stepped in a tile that is out of step.
extern "C" __global__ void commit_strips(const int* __restrict__ edges, const float* __restrict__ u1,
                                         const float* __restrict__ v1, const float* __restrict__ mx1,
                                         const float* __restrict__ my1, float* __restrict__ u, float* __restrict__ v,
                                         float* __restrict__ mx, float* __restrict__ my) {
    const int* e = edges + 4 * blockIdx.x;
    const int t = e[2];
    const int q = threadIdx.x;
    if (e[1] == 2) {
        const int k = t * STRIDE2 + (q + HALO) * STRIDE + HALO;
        u[k] = u1[k];
        mx[k] = mx1[k];
    } else {
        const int k = t * STRIDE2 + HALO * STRIDE + q + HALO;
        v[k] = v1[k];
        my[k] = my1[k];
    }
}

// The discharge of an edge as both tiles apply it when the coarse step starts: the estimate.
extern "C" __global__ void edge_estimate(const int* __restrict__ edges, const float* __restrict__ qx1,
                                         const float* __restrict__ qy1, const float* __restrict__ r,
                                         float* __restrict__ est) {
    const int* e = edges + 4 * blockIdx.x;
    const int side = e[1];
    const int q = threadIdx.x;
    const int k = edge_face(e[0], side, q);
    const int s = (side & 1) ? STRIDE : 1;
    const float f = (side & 1) ? qy1[k] : qx1[k];
    est[e[3] * TILE + q] = scaled(f, r[k - s], r[k]);
}

// A later fine step: the coarse cell owes the difference from the estimate. A coarse tile that owns the face stores its
// discharge, which the balance and the next coarse step read. Launched for one axis at a time, so no cell is written twice.
extern "C" __global__ void edge_flux(const int* __restrict__ edges, const float dt, const float* __restrict__ qx1,
                                     const float* __restrict__ qy1, const float* __restrict__ r,
                                     const float* __restrict__ est, float* __restrict__ res, float* __restrict__ qx,
                                     float* __restrict__ qy) {
    const int* e = edges + 4 * blockIdx.x;
    const int side = e[1];
    const int q = threadIdx.x;
    const int k = edge_face(e[0], side, q);
    const int s = (side & 1) ? STRIDE : 1;
    const float f = (side & 1) ? qy1[k] : qx1[k];
    const float qs = scaled(f, r[k - s], r[k]);
    const float sign = side < 2 ? -1.0f : 1.0f;
    res[edge_cell(e[2], side, q)] += sign * dt * (qs - est[e[3] * TILE + q]) / (P.dx * P.dx);
    if (side == 2) qx[e[2] * STRIDE2 + (q + HALO) * STRIDE + HALO] = qs;
    if (side == 3) qy[e[2] * STRIDE2 + HALO * STRIDE + q + HALO] = qs;
}
