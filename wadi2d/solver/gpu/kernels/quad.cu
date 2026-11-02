// Interfaces of the quadtree: a side of a fine tile that faces a coarser tile. The Numba twin is solver/cpu/quad.py.
//
// An interface holds 32 fine faces. They run through ``face_step`` like any face, with the true distance between the fine
// and the coarse centre, and they read the coarse cell through the fine tile's halo. The coarse tile's face on that side
// is closed: it takes the sum of the two fine faces beside each coarse cell, through the residual, so the fine fluxes add
// up to the coarse face exactly. A coarse tile a time level slower gets that sum as an estimate and the difference later.
//
// A row is (fine tile, side of the fine tile, coarse tile, number, offset, first table id, table id step).

extern "C" __global__ void quad_halo(const int* __restrict__ active, const int* __restrict__ slot,
                                     const int* __restrict__ cell, const int* __restrict__ fu,
                                     const int* __restrict__ fv, const float* __restrict__ qu,
                                     const float* __restrict__ qv, const int nhalo, const int* __restrict__ level,
                                     const int n, float* h, const float* __restrict__ h0, float* d,
                                     const float* __restrict__ d0, float* u, float* v, float* qx, float* qy) {
    const int t = active[blockIdx.x];
    const int m = blockDim.x * threadIdx.y + threadIdx.x;
    if (m >= nhalo) return;
    const int dst = t * STRIDE2 + slot[m];
    const int at = (t - 1) * nhalo + m;
    const int s = cell[at];
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
    u[dst] = u[fu[at]];
    v[dst] = v[fv[at]];
    qx[dst] = qu[at] * qx[fu[at]];
    qy[dst] = qv[at] * qy[fv[at]];
}

extern "C" __global__ void quad_faces_done(const int* __restrict__ active, const int* __restrict__ slot,
                                           const int* __restrict__ fu, const int* __restrict__ fv, const int nhalo,
                                           float* u1, float* v1, float* qx1, float* qy1) {
    const int t = active[blockIdx.x];
    const int m = blockDim.x * threadIdx.y + threadIdx.x;
    if (m >= nhalo) return;
    const int dst = t * STRIDE2 + slot[m];
    const int at = (t - 1) * nhalo + m;
    u1[dst] = u1[fu[at]];
    qx1[dst] = qx1[fu[at]];
    v1[dst] = v1[fv[at]];
    qy1[dst] = qy1[fv[at]];
}

// The fine faces of an interface. One block per row, launched with the module of the fine tile's cell size.
extern "C" __global__ void iface_faces(
    const int* __restrict__ rows, const float dt, const int want_wave, const float* __restrict__ om,
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
    const int* r = rows + 7 * blockIdx.x;
    const int t = r[0];
    const int side = r[1];
    const int q = threadIdx.x;
    const int k = edge_face(t, side, q);
    const int id = r[5] + q * r[6];
    const float L = 1.5f * P.dx;
    float w;
    if (side == 0) {
        w = face_step<1, STRIDE>(k, id, dt, L, want_wave, om, h, d, u, mx, qx, qy, v, flx, frx, glx, grx, efx, cwx, ftabx,
                                 u1, mx1, qx1);
    } else if (side == 1) {
        w = face_step<STRIDE, 1>(k, id, dt, L, want_wave, om, h, d, v, my, qy, qx, u, fly, fry, gly, gry, efy, cwy, ftaby,
                                 v1, my1, qy1);
    } else if (side == 2) {
        w = face_step<1, STRIDE, 1>(k, id, dt, L, want_wave, om, h, d, u, mx, qx, qy, v, flx, frx, glx, grx, efx, cwx,
                                    ftabx, u1, mx1, qx1);
    } else {
        w = face_step<STRIDE, 1, 1>(k, id, dt, L, want_wave, om, h, d, v, my, qy, qx, u, fly, fry, gly, gry, efy, cwy,
                                    ftaby, v1, my1, qy1);
    }
    if (want_wave) {
        atomic_fmax(wave + t, w);
        atomic_fmax(wave + r[2], w);
    }
}

// The coarse tile's copy of a face, for its positivity ratio: the sum of the two fine faces.
extern "C" __global__ void iface_load(const int* __restrict__ rows, float* u1, float* v1, float* qx1, float* qy1) {
    const int* r = rows + 7 * blockIdx.x;
    const int side = r[1];
    const int c = threadIdx.x;
    const int f1 = edge_face(r[0], side, 2 * c);
    const int f2 = edge_face(r[0], side, 2 * c + 1);
    const int kc = edge_face(r[2], side ^ 2, r[4] + c);
    if (side & 1) {
        qy1[kc] = qy1[f1] + qy1[f2];
        v1[kc] = 0.5f * (v1[f1] + v1[f2]);
    } else {
        qx1[kc] = qx1[f1] + qx1[f2];
        u1[kc] = 0.5f * (u1[f1] + u1[f2]);
    }
}

__device__ __forceinline__ float iface_sum(const int* __restrict__ r, const int c, const float* __restrict__ qx1,
                                           const float* __restrict__ qy1, const float* __restrict__ rr) {
    const int side = r[1];
    const int s = (side & 1) ? STRIDE : 1;
    const float* q1 = (side & 1) ? qy1 : qx1;
    const int f1 = edge_face(r[0], side, 2 * c);
    const int f2 = edge_face(r[0], side, 2 * c + 1);
    return scaled(q1[f1], rr[f1 - s], rr[f1]) + scaled(q1[f2], rr[f2 - s], rr[f2]);
}

// The coarse step starts: the coarse cell takes the sum for its whole step, and its own copy of the face stops counting.
extern "C" __global__ void iface_estimate(const int* __restrict__ rows, const float dt, float* __restrict__ qx1,
                                          float* __restrict__ qy1, const float* __restrict__ rr,
                                          float* __restrict__ est, float* __restrict__ res) {
    const int* r = rows + 7 * blockIdx.x;
    const int side = r[1];
    const int c = threadIdx.x;
    const float sum = iface_sum(r, c, qx1, qy1, rr);
    est[r[3] * (TILE / 2) + c] = sum;
    const float sign = side < 2 ? -1.0f : 1.0f;
    res[edge_cell(r[2], side, r[4] + c)] += sign * dt * sum / (4.0f * P.dx * P.dx);
    const int kc = edge_face(r[2], side ^ 2, r[4] + c);
    if (side & 1) qy1[kc] = 0.0f;
    else qx1[kc] = 0.0f;
}

// A later fine step inside the coarse step: the coarse cell owes the difference from the estimate.
extern "C" __global__ void iface_flux(const int* __restrict__ rows, const float dt, const float* __restrict__ qx1,
                                      const float* __restrict__ qy1, const float* __restrict__ rr,
                                      const float* __restrict__ est, float* __restrict__ res) {
    const int* r = rows + 7 * blockIdx.x;
    const int side = r[1];
    const int c = threadIdx.x;
    const float sum = iface_sum(r, c, qx1, qy1, rr);
    const float sign = side < 2 ? -1.0f : 1.0f;
    res[edge_cell(r[2], side, r[4] + c)] += sign * dt * (sum - est[r[3] * (TILE / 2) + c]) / (4.0f * P.dx * P.dx);
}

// After the update: what the next step reads. The fine tile's east and south faces are not its own cells' faces, and the
// coarse tile's copy holds the sum.
extern "C" __global__ void iface_store(const int* __restrict__ rows, const float* __restrict__ qx1,
                                       const float* __restrict__ qy1, const float* __restrict__ rr,
                                       const float* __restrict__ u1, const float* __restrict__ v1,
                                       const float* __restrict__ mx1, const float* __restrict__ my1, float* u, float* v,
                                       float* mx, float* my, float* qx, float* qy) {
    const int* r = rows + 7 * blockIdx.x;
    const int side = r[1];
    const int q = threadIdx.x;
    const int s = (side & 1) ? STRIDE : 1;
    const int k = edge_face(r[0], side, q);
    const float qf = (side & 1) ? qy1[k] : qx1[k];
    const float qs = scaled(qf, rr[k - s], rr[k]);
    if (side == 2) {
        u[k] = u1[k];
        mx[k] = mx1[k];
        qx[k] = qs;
    }
    if (side == 3) {
        v[k] = v1[k];
        my[k] = my1[k];
        qy[k] = qs;
    }
    if (q & 1) return;
    const int c = q / 2;
    const int f2 = edge_face(r[0], side, q + 1);
    const float qf2 = (side & 1) ? qy1[f2] : qx1[f2];
    const float qs2 = scaled(qf2, rr[f2 - s], rr[f2]);
    const int kc = edge_face(r[2], side ^ 2, r[4] + c);
    if (side & 1) {
        qy[kc] = qs + qs2;
        v[kc] = 0.5f * (v1[k] + v1[f2]);
    } else {
        qx[kc] = qs + qs2;
        u[kc] = 0.5f * (u1[k] + u1[f2]);
    }
}
