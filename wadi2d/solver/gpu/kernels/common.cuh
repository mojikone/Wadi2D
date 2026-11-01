// Device helpers shared by the kernels. TILE, HALO, STRIDE, STRIDE2 and TILE2 come from the generated header, so
// the layout has one source of truth (wadi2d/solver/layout.py). The Numba twin lives in solver/cpu/kernels.py;
// keep the statement order the same.

struct Params {
    float g;
    float dx;
    float e_wet;
    float h_cfl;
    float u_max;
    int rows;
    int second;
    int sheet;
};

__constant__ Params P;

__device__ __forceinline__ float minmod(const float a, const float b) {
    if (a * b <= 0.0f) return 0.0f;
    return fabsf(a) < fabsf(b) ? a : b;
}

// Velocity at a cell centre from its upwind face uc, with a limited second-order correction.
__device__ __forceinline__ float ustar(const float uc, const float uup, const float udown) {
    if (!P.second) return uc;
    return uc + 0.5f * minmod(uc - uup, udown - uc);
}

// Level above zmin from the mean depth; linear in the row coordinate, which is exact on a plane.
__device__ __forceinline__ float cell_level(const float hb, const float Hc, const float* __restrict__ tab) {
    if (Hc <= 0.0f) return hb;
    const int last = P.rows - 1;
    if (hb >= Hc) return tab[last] + (hb - Hc);
    const float s = sqrtf(hb / Hc) * (float)last;
    const int r = (int)s;
    return tab[r] + (s - (float)r) * (tab[r + 1] - tab[r]);
}

// Area A, conveyance^(3/5) T and wet width W at depth e over the face invert. Prismatic above the table top.
__device__ __forceinline__ void face_lookup(const float e, const float E, const float* __restrict__ tab, float& A,
                                            float& T, float& W) {
    const int last = P.rows - 1;
    const float m = (float)last;
    if (e >= E) {
        const float a1 = tab[2 * last];
        const float a0 = tab[2 * last - 2];
        const float c = (m - 1.0f) / m;
        W = (a1 - a0) / (E * (1.0f - c * c));
        A = a1 + W * (e - E);
        T = tab[2 * last + 1] * (A / fmaxf(a1, 1e-12f));
        return;
    }
    const float s = sqrtf(e / E) * m;
    const int r = (int)s;
    const float c0 = (float)r / m;
    const float c1 = (float)(r + 1) / m;
    const float e0 = c0 * c0 * E;
    const float de = (c1 * c1 - c0 * c0) * E;
    const float f = (e - e0) / de;
    const float a0 = tab[2 * r];
    const float a1 = tab[2 * r + 2];
    const float t0 = tab[2 * r + 1];
    A = a0 + f * (a1 - a0);
    T = t0 + f * (tab[2 * r + 3] - t0);
    W = (a1 - a0) / de;
}

// Positive floats order like their bit patterns, so a float maximum can use the integer atomic.
__device__ __forceinline__ void atomic_fmax(float* p, const float v) {
    const int bits = *reinterpret_cast<const int*>(&v);
    atomicMax(reinterpret_cast<int*>(p), bits);
}
