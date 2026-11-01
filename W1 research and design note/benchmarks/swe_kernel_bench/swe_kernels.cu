// swe_kernels.cu - Wadi2D micro-benchmark kernels (throwaway, not the product).
//
// Explicit second-order shallow-water step on a uniform grid, float32, depth-based state (h, hu, hv) + bed z.
// Grid: nx x ny interior cells padded by 2 ghost cells on every side; stride sx = nx + 4; padded index
// k = (j + 2) * sx + (i + 2). eta = h + z is formed in registers only (decision 3: store depth, not level).
//
// Scheme per face: MUSCL (minmod) reconstruction of eta, h, hu, hv -> z_face = eta_face - h_face;
// hydrostatic reconstruction (Audusse et al. 2004) at the face; HLLC; the Audusse face source terms plus the
// centred bed-slope term (Audusse & Bristeau 2005) -> well balanced; point-implicit Manning friction after the
// flux update; wet/dry threshold HEPS. Integrators: MUSCL-Hancock (predictor on the reconstructed faces) and
// SSP-RK2 (two flux evaluations). Organisations: fused per cell, split (face arrays), tiled (shared memory).

#ifndef EARLY_EXIT
#define EARLY_EXIT 0
#endif
#define G 9.81f
#define HEPS 1e-4f
#define NMAN 0.03f
#define TX 32
#define TY 32
#define HALO 2
#define TW 36

struct St { float h, z, hu, hv; };
struct Face { float h, z, hu, hv; };

__device__ __forceinline__ float minmod(float a, float b) {
    return (a * b <= 0.f) ? 0.f : ((fabsf(a) < fabsf(b)) ? a : b);
}

__device__ __forceinline__ St ld(const float* __restrict__ h, const float* __restrict__ z,
                                 const float* __restrict__ hu, const float* __restrict__ hv, int k) {
    St s; s.h = h[k]; s.z = z[k]; s.hu = hu[k]; s.hv = hv[k]; return s;
}

// Two faces of cell c along one axis; m = minus-side neighbour, p = plus-side neighbour.
// First order (zero slopes) when the cell or either neighbour is dry.
__device__ __forceinline__ void recon1(const St& m, const St& c, const St& p, Face& lo, Face& hi) {
    float se = 0.f, sh = 0.f, su = 0.f, sv = 0.f;
    if (c.h >= HEPS && m.h >= HEPS && p.h >= HEPS) {
        float ec = c.h + c.z;
        se = 0.5f * minmod(ec - (m.h + m.z), (p.h + p.z) - ec);
        sh = 0.5f * minmod(c.h - m.h, p.h - c.h);
        su = 0.5f * minmod(c.hu - m.hu, p.hu - c.hu);
        sv = 0.5f * minmod(c.hv - m.hv, p.hv - c.hv);
    }
    lo.h = c.h - sh;        hi.h = c.h + sh;
    lo.z = c.z + (sh - se); hi.z = c.z + (se - sh);   // z_face = eta_face - h_face
    lo.hu = c.hu - su;      hi.hu = c.hu + su;
    lo.hv = c.hv - sv;      hi.hv = c.hv + sv;
}

// Only the bed elevation of the two faces (used where predicted faces are stored without z).
__device__ __forceinline__ void recon_z1(const St& m, const St& c, const St& p, float& zlo, float& zhi) {
    float se = 0.f, sh = 0.f;
    if (c.h >= HEPS && m.h >= HEPS && p.h >= HEPS) {
        float ec = c.h + c.z;
        se = 0.5f * minmod(ec - (m.h + m.z), (p.h + p.z) - ec);
        sh = 0.5f * minmod(c.h - m.h, p.h - c.h);
    }
    zlo = c.z + (sh - se); zhi = c.z + (se - sh);
}

__device__ __forceinline__ void pflux_x(const Face& f, float& f0, float& f1, float& f2) {
    float u = (f.h >= HEPS) ? f.hu / f.h : 0.f, v = (f.h >= HEPS) ? f.hv / f.h : 0.f;
    f0 = f.h * u; f1 = f.h * u * u + 0.5f * G * f.h * f.h; f2 = f.h * u * v;
}
__device__ __forceinline__ void pflux_y(const Face& f, float& g0, float& g1, float& g2) {
    float u = (f.h >= HEPS) ? f.hu / f.h : 0.f, v = (f.h >= HEPS) ? f.hv / f.h : 0.f;
    g0 = f.h * v; g1 = f.h * u * v; g2 = f.h * v * v + 0.5f * G * f.h * f.h;
}

__device__ __forceinline__ void clampface(Face& f) {
    if (f.h < HEPS) { if (f.h < 0.f) f.h = 0.f; f.hu = 0.f; f.hv = 0.f; }
}

// MUSCL-Hancock predictor: advance the four reconstructed faces by dt/2 with the flux divergence of the cell
// and the centred bed-slope term. hdt = 0.5 * dt / dx (dx = dy). A dry cell stays dry (zero fluxes, zero source).
__device__ __forceinline__ void hancock(Face& W, Face& E, Face& S, Face& N, float hdt) {
    float fw0, fw1, fw2, fe0, fe1, fe2, gs0, gs1, gs2, gn0, gn1, gn2;
    pflux_x(W, fw0, fw1, fw2); pflux_x(E, fe0, fe1, fe2);
    pflux_y(S, gs0, gs1, gs2); pflux_y(N, gn0, gn1, gn2);
    float dh  = -hdt * ((fe0 - fw0) + (gn0 - gs0));
    float dhu = -hdt * ((fe1 - fw1) + (gn1 - gs1) - 0.5f * G * (W.h + E.h) * (W.z - E.z));
    float dhv = -hdt * ((fe2 - fw2) + (gn2 - gs2) - 0.5f * G * (S.h + N.h) * (S.z - N.z));
    W.h += dh; W.hu += dhu; W.hv += dhv; clampface(W);
    E.h += dh; E.hu += dhu; E.hv += dhv; clampface(E);
    S.h += dh; S.hu += dhu; S.hv += dhv; clampface(S);
    N.h += dh; N.hu += dhu; N.hv += dhv; clampface(N);
}

// HLLC for the SWE in the face-normal frame: (h, un, ut) on both sides, depths already hydrostatically
// reconstructed. Returns mass flux f0, normal-momentum flux fn, tangential-momentum flux ft.
__device__ __forceinline__ void hllc(float hL, float unL, float utL, float hR, float unR, float utR,
                                     float& f0, float& fn, float& ft) {
    bool wL = hL >= HEPS, wR = hR >= HEPS;
    if (!wL && !wR) { f0 = 0.f; fn = 0.f; ft = 0.f; return; }
    if (!wL) { unL = 0.f; utL = 0.f; }
    if (!wR) { unR = 0.f; utR = 0.f; }
    float cL = sqrtf(G * hL), cR = sqrtf(G * hR);
    float sL, sR;
    if (!wL)      { sL = unR - 2.f * cR; sR = unR + cR; }
    else if (!wR) { sL = unL - cL;       sR = unL + 2.f * cL; }
    else {
        float us = 0.5f * (unL + unR) + cL - cR;
        float cs = 0.5f * (cL + cR) + 0.25f * (unL - unR);
        sL = fminf(unL - cL, us - cs);
        sR = fmaxf(unR + cR, us + cs);
    }
    float FL0 = hL * unL, FR0 = hR * unR;
    float FL1 = FL0 * unL + 0.5f * G * hL * hL, FR1 = FR0 * unR + 0.5f * G * hR * hR;
    if (sL >= 0.f) { f0 = FL0; fn = FL1; ft = FL0 * utL; return; }
    if (sR <= 0.f) { f0 = FR0; fn = FR1; ft = FR0 * utR; return; }
    float inv = 1.f / (sR - sL);
    f0 = (sR * FL0 - sL * FR0 + sL * sR * (hR - hL)) * inv;
    fn = (sR * FL1 - sL * FR1 + sL * sR * (FR0 - FL0)) * inv;
    float num = sL * hR * (unR - sR) - sR * hL * (unL - sL);
    float den = hR * (unR - sR) - hL * (unL - sL);
    float sM = (fabsf(den) > 1e-12f) ? num / den : 0.5f * (unL + unR);
    ft = (sM >= 0.f) ? f0 * utL : f0 * utR;
}

// x face: L = east face of the left cell, R = west face of the right cell.
// sL, sR: Audusse face terms 0.5 g (h^2 - h*^2) of the left and right side.
__device__ __forceinline__ void face_x(const Face& L, const Face& R,
                                       float& f0, float& f1, float& f2, float& sL, float& sR) {
    float zf = fmaxf(L.z, R.z);
    float hL = fmaxf(0.f, L.h + L.z - zf);
    float hR = fmaxf(0.f, R.h + R.z - zf);
    float uL = (L.h >= HEPS) ? L.hu / L.h : 0.f, vL = (L.h >= HEPS) ? L.hv / L.h : 0.f;
    float uR = (R.h >= HEPS) ? R.hu / R.h : 0.f, vR = (R.h >= HEPS) ? R.hv / R.h : 0.f;
    hllc(hL, uL, vL, hR, uR, vR, f0, f1, f2);
    sL = 0.5f * G * (L.h * L.h - hL * hL);
    sR = 0.5f * G * (R.h * R.h - hR * hR);
}
// y face: L = north face of the south cell, R = south face of the north cell. g1 = hu flux, g2 = hv flux.
__device__ __forceinline__ void face_y(const Face& L, const Face& R,
                                       float& g0, float& g1, float& g2, float& sL, float& sR) {
    float zf = fmaxf(L.z, R.z);
    float hL = fmaxf(0.f, L.h + L.z - zf);
    float hR = fmaxf(0.f, R.h + R.z - zf);
    float uL = (L.h >= HEPS) ? L.hu / L.h : 0.f, vL = (L.h >= HEPS) ? L.hv / L.h : 0.f;
    float uR = (R.h >= HEPS) ? R.hu / R.h : 0.f, vR = (R.h >= HEPS) ? R.hv / R.h : 0.f;
    hllc(hL, vL, uL, hR, vR, uR, g0, g2, g1);
    sL = 0.5f * G * (L.h * L.h - hL * hL);
    sR = 0.5f * G * (R.h * R.h - hR * hR);
}

// Cell update from the four face fluxes and terms, plus the centred source. r = dt / dx.
__device__ __forceinline__ void cell_rhs(const St& c, float r,
        float fw0, float fw1, float fw2, float sRw, float fe0, float fe1, float fe2, float sLe,
        float gs0, float gs1, float gs2, float sRs, float gn0, float gn1, float gn2, float sLn,
        float hW, float zW, float hE, float zE, float hS, float zS, float hN, float zN,
        float& hn, float& hun, float& hvn) {
    hn  = c.h  - r * ((fe0 - fw0) + (gn0 - gs0));
    hun = c.hu - r * ((fe1 - fw1) + (sLe - sRw) + (gn1 - gs1) - 0.5f * G * (hW + hE) * (zW - zE));
    hvn = c.hv - r * ((fe2 - fw2) + (gn2 - gs2) + (sLn - sRs) - 0.5f * G * (hS + hN) * (zS - zN));
}

// Positivity clamp, dry-cell momentum, point-implicit Manning friction.
__device__ __forceinline__ void finish(float& hn, float& hun, float& hvn, float dt) {
    if (hn < HEPS) { if (hn < 0.f) hn = 0.f; hun = 0.f; hvn = 0.f; return; }
    float u = hun / hn, v = hvn / hn;
    float sp = sqrtf(u * u + v * v);
    float inv = 1.f / (1.f + dt * G * NMAN * NMAN * sp / (hn * cbrtf(hn)));
    hun *= inv; hvn *= inv;
}

// ------------------------------------------------------------------ ghost cells (reflective walls)
extern "C" __global__ void ghost_x(float* __restrict__ h, float* __restrict__ hu, float* __restrict__ hv,
                                   float* __restrict__ z, int nx, int ny, int sx, int do_z) {
    int j = blockIdx.x * blockDim.x + threadIdx.x;
    if (j >= ny + 4) return;
    int base = j * sx;
    int src[4] = {3, 2, nx + 1, nx};
    int dst[4] = {0, 1, nx + 2, nx + 3};
    #pragma unroll
    for (int q = 0; q < 4; ++q) {
        int kd = base + dst[q], ks = base + src[q];
        h[kd] = h[ks]; hu[kd] = -hu[ks]; hv[kd] = hv[ks];
        if (do_z) z[kd] = z[ks];
    }
}
extern "C" __global__ void ghost_y(float* __restrict__ h, float* __restrict__ hu, float* __restrict__ hv,
                                   float* __restrict__ z, int nx, int ny, int sx, int do_z) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= nx + 4) return;
    int src[4] = {3, 2, ny + 1, ny};
    int dst[4] = {0, 1, ny + 2, ny + 3};
    #pragma unroll
    for (int q = 0; q < 4; ++q) {
        int kd = dst[q] * sx + i, ks = src[q] * sx + i;
        h[kd] = h[ks]; hu[kd] = hu[ks]; hv[kd] = -hv[ks];
        if (do_z) z[kd] = z[ks];
    }
}

// ------------------------------------------------------------------ CFL reduction (two pass, no host sync)
extern "C" __global__ void cfl_partial(const float* __restrict__ h, const float* __restrict__ hu,
                                       const float* __restrict__ hv, int nx, int ny, int sx,
                                       float* __restrict__ partial) {
    __shared__ float red[256];
    float m = 0.f;
    for (int j = blockIdx.x; j < ny; j += gridDim.x) {
        int base = (j + 2) * sx + 2;
        for (int i = threadIdx.x; i < nx; i += blockDim.x) {
            int k = base + i;
            float hh = h[k];
            if (hh >= HEPS) {
                float u = hu[k] / hh, v = hv[k] / hh;
                m = fmaxf(m, fmaxf(fabsf(u), fabsf(v)) + sqrtf(G * hh));
            }
        }
    }
    red[threadIdx.x] = m;
    __syncthreads();
    for (int s = blockDim.x / 2; s > 0; s >>= 1) {
        if (threadIdx.x < s) red[threadIdx.x] = fmaxf(red[threadIdx.x], red[threadIdx.x + s]);
        __syncthreads();
    }
    if (threadIdx.x == 0) partial[blockIdx.x] = red[0];
}
extern "C" __global__ void cfl_final(const float* __restrict__ partial, int n, float* __restrict__ dt,
                                     float cfl_dx, float dtmax) {
    __shared__ float red[1024];
    float m = 0.f;
    for (int i = threadIdx.x; i < n; i += blockDim.x) m = fmaxf(m, partial[i]);
    red[threadIdx.x] = m;
    __syncthreads();
    for (int s = blockDim.x / 2; s > 0; s >>= 1) {
        if (threadIdx.x < s) red[threadIdx.x] = fmaxf(red[threadIdx.x], red[threadIdx.x + s]);
        __syncthreads();
    }
    if (threadIdx.x == 0) dt[0] = (red[0] > 1e-6f) ? fminf(dtmax, cfl_dx / red[0]) : dtmax;
}

// ------------------------------------------------------------------ (1) fused: one kernel per stage / step
// SSP-RK2 stage: U_out = a * U_prev + b * F(U_in), F = flux update + friction. Stage 1: a=0,b=1; stage 2: a=b=0.5.
extern "C" __global__ void __launch_bounds__(256)
rk2_fused(const float* __restrict__ h, const float* __restrict__ z, const float* __restrict__ hu,
          const float* __restrict__ hv, const float* __restrict__ hp, const float* __restrict__ hup,
          const float* __restrict__ hvp, float* __restrict__ ho, float* __restrict__ huo,
          float* __restrict__ hvo, const float* __restrict__ dtp, int nx, int ny, int sx, float dx,
          float a, float b) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    int j = blockIdx.y * blockDim.y + threadIdx.y;
    if (i >= nx || j >= ny) return;
    int k = (j + 2) * sx + (i + 2);
    float hc = h[k], hw = h[k - 1], he = h[k + 1], hs = h[k - sx], hnn = h[k + sx];
#if EARLY_EXIT
    if (hc < HEPS && hw < HEPS && he < HEPS && hs < HEPS && hnn < HEPS) {
        ho[k] = a * hp[k] + b * hc; huo[k] = a * hup[k] + b * hu[k]; hvo[k] = a * hvp[k] + b * hv[k];
        return;
    }
#endif
    St c, w, e, s, n;
    c.h = hc;  c.z = z[k];      c.hu = hu[k];      c.hv = hv[k];
    w.h = hw;  w.z = z[k - 1];  w.hu = hu[k - 1];  w.hv = hv[k - 1];
    e.h = he;  e.z = z[k + 1];  e.hu = hu[k + 1];  e.hv = hv[k + 1];
    s.h = hs;  s.z = z[k - sx]; s.hu = hu[k - sx]; s.hv = hv[k - sx];
    n.h = hnn; n.z = z[k + sx]; n.hu = hu[k + sx]; n.hv = hv[k + sx];
    St ww = ld(h, z, hu, hv, k - 2), ee = ld(h, z, hu, hv, k + 2);
    St ss = ld(h, z, hu, hv, k - 2 * sx), nn = ld(h, z, hu, hv, k + 2 * sx);
    Face cW, cE, cS, cN, wE, eW, sN, nS, tmp;
    recon1(w, c, e, cW, cE);
    recon1(s, c, n, cS, cN);
    recon1(ww, w, c, tmp, wE);
    recon1(c, e, ee, eW, tmp);
    recon1(ss, s, c, tmp, sN);
    recon1(c, n, nn, nS, tmp);
    float fw0, fw1, fw2, sLw, sRw, fe0, fe1, fe2, sLe, sRe;
    float gs0, gs1, gs2, sLs, sRs, gn0, gn1, gn2, sLn, sRn;
    face_x(wE, cW, fw0, fw1, fw2, sLw, sRw);
    face_x(cE, eW, fe0, fe1, fe2, sLe, sRe);
    face_y(sN, cS, gs0, gs1, gs2, sLs, sRs);
    face_y(cN, nS, gn0, gn1, gn2, sLn, sRn);
    float dt = *dtp;
    float hn, hun, hvn;
    cell_rhs(c, dt / dx, fw0, fw1, fw2, sRw, fe0, fe1, fe2, sLe, gs0, gs1, gs2, sRs, gn0, gn1, gn2, sLn,
             cW.h, cW.z, cE.h, cE.z, cS.h, cS.z, cN.h, cN.z, hn, hun, hvn);
    finish(hn, hun, hvn, dt);
    ho[k] = a * hp[k] + b * hn; huo[k] = a * hup[k] + b * hun; hvo[k] = a * hvp[k] + b * hvn;
}

// MUSCL-Hancock, one kernel per step: predictor for the cell and its four neighbours (13-cell stencil).
extern "C" __global__ void __launch_bounds__(256)
mh_fused(const float* __restrict__ h, const float* __restrict__ z, const float* __restrict__ hu,
         const float* __restrict__ hv, float* __restrict__ ho, float* __restrict__ huo,
         float* __restrict__ hvo, const float* __restrict__ dtp, int nx, int ny, int sx, float dx) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    int j = blockIdx.y * blockDim.y + threadIdx.y;
    if (i >= nx || j >= ny) return;
    int k = (j + 2) * sx + (i + 2);
    float hc = h[k], hw = h[k - 1], he = h[k + 1], hs = h[k - sx], hnn = h[k + sx];
#if EARLY_EXIT
    if (hc < HEPS && hw < HEPS && he < HEPS && hs < HEPS && hnn < HEPS) {
        ho[k] = hc; huo[k] = hu[k]; hvo[k] = hv[k];
        return;
    }
#endif
    St c, w, e, s, n;
    c.h = hc;  c.z = z[k];      c.hu = hu[k];      c.hv = hv[k];
    w.h = hw;  w.z = z[k - 1];  w.hu = hu[k - 1];  w.hv = hv[k - 1];
    e.h = he;  e.z = z[k + 1];  e.hu = hu[k + 1];  e.hv = hv[k + 1];
    s.h = hs;  s.z = z[k - sx]; s.hu = hu[k - sx]; s.hv = hv[k - sx];
    n.h = hnn; n.z = z[k + sx]; n.hu = hu[k + sx]; n.hv = hv[k + sx];
    float dt = *dtp;
    float hdt = 0.5f * dt / dx;
    Face cW, cE, cS, cN;
    recon1(w, c, e, cW, cE); recon1(s, c, n, cS, cN); hancock(cW, cE, cS, cN, hdt);
    Face a0, a1, a2, a3;
    St ww = ld(h, z, hu, hv, k - 2), wS = ld(h, z, hu, hv, k - 1 - sx), wN = ld(h, z, hu, hv, k - 1 + sx);
    recon1(ww, w, c, a0, a1); recon1(wS, w, wN, a2, a3); hancock(a0, a1, a2, a3, hdt);
    Face wE = a1;
    St ee = ld(h, z, hu, hv, k + 2), eS = ld(h, z, hu, hv, k + 1 - sx), eN = ld(h, z, hu, hv, k + 1 + sx);
    recon1(c, e, ee, a0, a1); recon1(eS, e, eN, a2, a3); hancock(a0, a1, a2, a3, hdt);
    Face eW = a0;
    St ss = ld(h, z, hu, hv, k - 2 * sx);
    recon1(wS, s, eS, a0, a1); recon1(ss, s, c, a2, a3); hancock(a0, a1, a2, a3, hdt);
    Face sN = a3;
    St nn = ld(h, z, hu, hv, k + 2 * sx);
    recon1(wN, n, eN, a0, a1); recon1(c, n, nn, a2, a3); hancock(a0, a1, a2, a3, hdt);
    Face nS = a2;
    float fw0, fw1, fw2, sLw, sRw, fe0, fe1, fe2, sLe, sRe;
    float gs0, gs1, gs2, sLs, sRs, gn0, gn1, gn2, sLn, sRn;
    face_x(wE, cW, fw0, fw1, fw2, sLw, sRw);
    face_x(cE, eW, fe0, fe1, fe2, sLe, sRe);
    face_y(sN, cS, gs0, gs1, gs2, sLs, sRs);
    face_y(cN, nS, gn0, gn1, gn2, sLn, sRn);
    float hn, hun, hvn;
    cell_rhs(c, dt / dx, fw0, fw1, fw2, sRw, fe0, fe1, fe2, sLe, gs0, gs1, gs2, sRs, gn0, gn1, gn2, sLn,
             cW.h, cW.z, cE.h, cE.z, cS.h, cS.z, cN.h, cN.z, hn, hun, hvn);
    finish(hn, hun, hvn, dt);
    ho[k] = hn; huo[k] = hun; hvo[k] = hvn;
}

// ------------------------------------------------------------------ (2) split: face-state and face-flux arrays
// fs layout: [16][npad], q = 0..3 W(h,z,hu,hv), 4..7 E, 8..11 S, 12..15 N. fx/fy: [5][npad] (f0,f1,f2,sL,sR),
// an x face stored at the index of its right cell, a y face at the index of its north cell.
extern "C" __global__ void __launch_bounds__(256)
recon_cells(const float* __restrict__ h, const float* __restrict__ z, const float* __restrict__ hu,
            const float* __restrict__ hv, float* __restrict__ fs, const float* __restrict__ dtp,
            int nx, int ny, int sx, float dx, int predict) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;   // 0 .. nx+1  (interior plus one ring of ghosts)
    int j = blockIdx.y * blockDim.y + threadIdx.y;   // 0 .. ny+1
    if (i >= nx + 2 || j >= ny + 2) return;
    int k = (j + 1) * sx + (i + 1);
    int np = sx * (ny + 4);
    St c = ld(h, z, hu, hv, k), w = ld(h, z, hu, hv, k - 1), e = ld(h, z, hu, hv, k + 1);
    St s = ld(h, z, hu, hv, k - sx), n = ld(h, z, hu, hv, k + sx);
    Face W, E, S, N;
    recon1(w, c, e, W, E);
    recon1(s, c, n, S, N);
    if (predict) hancock(W, E, S, N, 0.5f * (*dtp) / dx);
    fs[0 * np + k] = W.h;  fs[1 * np + k] = W.z;  fs[2 * np + k] = W.hu;  fs[3 * np + k] = W.hv;
    fs[4 * np + k] = E.h;  fs[5 * np + k] = E.z;  fs[6 * np + k] = E.hu;  fs[7 * np + k] = E.hv;
    fs[8 * np + k] = S.h;  fs[9 * np + k] = S.z;  fs[10 * np + k] = S.hu; fs[11 * np + k] = S.hv;
    fs[12 * np + k] = N.h; fs[13 * np + k] = N.z; fs[14 * np + k] = N.hu; fs[15 * np + k] = N.hv;
}

extern "C" __global__ void __launch_bounds__(256)
flux_x(const float* __restrict__ fs, float* __restrict__ fx, int nx, int ny, int sx) {
    int f = blockIdx.x * blockDim.x + threadIdx.x;   // 0 .. nx : face between padded cells f+1 and f+2
    int j = blockIdx.y * blockDim.y + threadIdx.y;
    if (f > nx || j >= ny) return;
    int kR = (j + 2) * sx + (f + 2), kL = kR - 1;
    int np = sx * (ny + 4);
    Face L, R;
    L.h = fs[4 * np + kL]; L.z = fs[5 * np + kL]; L.hu = fs[6 * np + kL]; L.hv = fs[7 * np + kL];
    R.h = fs[0 * np + kR]; R.z = fs[1 * np + kR]; R.hu = fs[2 * np + kR]; R.hv = fs[3 * np + kR];
    float f0, f1, f2, sL, sR;
    face_x(L, R, f0, f1, f2, sL, sR);
    fx[0 * np + kR] = f0; fx[1 * np + kR] = f1; fx[2 * np + kR] = f2; fx[3 * np + kR] = sL; fx[4 * np + kR] = sR;
}

extern "C" __global__ void __launch_bounds__(256)
flux_y(const float* __restrict__ fs, float* __restrict__ fy, int nx, int ny, int sx) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    int f = blockIdx.y * blockDim.y + threadIdx.y;   // 0 .. ny : face between padded rows f+1 and f+2
    if (i >= nx || f > ny) return;
    int kN = (f + 2) * sx + (i + 2), kS = kN - sx;
    int np = sx * (ny + 4);
    Face L, R;
    L.h = fs[12 * np + kS]; L.z = fs[13 * np + kS]; L.hu = fs[14 * np + kS]; L.hv = fs[15 * np + kS];
    R.h = fs[8 * np + kN];  R.z = fs[9 * np + kN];  R.hu = fs[10 * np + kN]; R.hv = fs[11 * np + kN];
    float g0, g1, g2, sL, sR;
    face_y(L, R, g0, g1, g2, sL, sR);
    fy[0 * np + kN] = g0; fy[1 * np + kN] = g1; fy[2 * np + kN] = g2; fy[3 * np + kN] = sL; fy[4 * np + kN] = sR;
}

extern "C" __global__ void __launch_bounds__(256)
update_cells(const float* __restrict__ h, const float* __restrict__ hu, const float* __restrict__ hv,
             const float* __restrict__ hp, const float* __restrict__ hup, const float* __restrict__ hvp,
             float* __restrict__ ho, float* __restrict__ huo, float* __restrict__ hvo,
             const float* __restrict__ fs, const float* __restrict__ fx, const float* __restrict__ fy,
             const float* __restrict__ dtp, int nx, int ny, int sx, float dx, float a, float b) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    int j = blockIdx.y * blockDim.y + threadIdx.y;
    if (i >= nx || j >= ny) return;
    int k = (j + 2) * sx + (i + 2);
    int np = sx * (ny + 4);
    St c; c.h = h[k]; c.z = 0.f; c.hu = hu[k]; c.hv = hv[k];
    float fw0 = fx[0 * np + k], fw1 = fx[1 * np + k], fw2 = fx[2 * np + k], sRw = fx[4 * np + k];
    float fe0 = fx[0 * np + k + 1], fe1 = fx[1 * np + k + 1], fe2 = fx[2 * np + k + 1], sLe = fx[3 * np + k + 1];
    float gs0 = fy[0 * np + k], gs1 = fy[1 * np + k], gs2 = fy[2 * np + k], sRs = fy[4 * np + k];
    float gn0 = fy[0 * np + k + sx], gn1 = fy[1 * np + k + sx], gn2 = fy[2 * np + k + sx], sLn = fy[3 * np + k + sx];
    float hW = fs[0 * np + k], zW = fs[1 * np + k], hE = fs[4 * np + k], zE = fs[5 * np + k];
    float hS = fs[8 * np + k], zS = fs[9 * np + k], hN = fs[12 * np + k], zN = fs[13 * np + k];
    float dt = *dtp;
    float hn, hun, hvn;
    cell_rhs(c, dt / dx, fw0, fw1, fw2, sRw, fe0, fe1, fe2, sLe, gs0, gs1, gs2, sRs, gn0, gn1, gn2, sLn,
             hW, zW, hE, zE, hS, zS, hN, zN, hn, hun, hvn);
    finish(hn, hun, hvn, dt);
    ho[k] = a * hp[k] + b * hn; huo[k] = a * hup[k] + b * hun; hvo[k] = a * hvp[k] + b * hvn;
}

// ------------------------------------------------------------------ (3) tiled: 32x32 cells per block, 2-cell halo
// Block = 32 x 8 threads; thread (tx, ty) owns the cells (tx, ty + 8q), q = 0..3, of the tile.
#define TILE(name, r, c) name[(r) * TW + (c)]
__device__ __forceinline__ St tld(const float* sh, const float* sz, const float* shu, const float* shv, int r, int c) {
    St s; int t = r * TW + c; s.h = sh[t]; s.z = sz[t]; s.hu = shu[t]; s.hv = shv[t]; return s;
}

// SSP-RK2 stage, each face computed once into a shared flux buffer (x pass, then y pass reusing the buffer).
extern "C" __global__ void __launch_bounds__(256)
rk2_tiled(const float* __restrict__ h, const float* __restrict__ z, const float* __restrict__ hu,
          const float* __restrict__ hv, const float* __restrict__ hp, const float* __restrict__ hup,
          const float* __restrict__ hvp, float* __restrict__ ho, float* __restrict__ huo,
          float* __restrict__ hvo, const float* __restrict__ dtp, int nx, int ny, int sx, float dx,
          float a, float b) {
    __shared__ float sh[TW * TW], sz[TW * TW], shu[TW * TW], shv[TW * TW];   // 20.7 KB
    __shared__ float sf[5 * TX * (TX + 1)];                                  // 21.1 KB, reused for x and y
    const int NF = TX * (TX + 1);
    int tx = threadIdx.x, ty = threadIdx.y, tid = ty * 32 + tx;
    int i0 = blockIdx.x * TX, j0 = blockIdx.y * TY;   // interior origin; padded origin of the tile = (j0, i0)
    for (int t = tid; t < TW * TW; t += 256) {
        int r = t / TW, c = t - r * TW;
        int k = (j0 + r) * sx + (i0 + c);
        sh[t] = h[k]; sz[t] = z[k]; shu[t] = hu[k]; shv[t] = hv[k];
    }
    __syncthreads();
#if EARLY_EXIT
    {
        int wet = 0;
        for (int t = tid; t < TW * TW; t += 256) wet |= (sh[t] >= HEPS);
        if (!__syncthreads_or(wet)) {
            for (int q = 0; q < 4; ++q) {
                int r = ty + 8 * q;
                int k = (j0 + r + 2) * sx + (i0 + tx + 2);
                int t = (r + 2) * TW + tx + 2;
                ho[k] = a * hp[k] + b * sh[t]; huo[k] = a * hup[k] + b * shu[t]; hvo[k] = a * hvp[k] + b * shv[t];
            }
            return;
        }
    }
#endif
    // x faces: 32 rows x 33 faces; face f lies between tile columns f+1 and f+2
    for (int t = tid; t < NF; t += 256) {
        int r = t / (TX + 1), f = t - r * (TX + 1);
        int tr = r + HALO, cl = f + 1;
        St m = tld(sh, sz, shu, shv, tr, cl - 1), l = tld(sh, sz, shu, shv, tr, cl);
        St rr = tld(sh, sz, shu, shv, tr, cl + 1), p = tld(sh, sz, shu, shv, tr, cl + 2);
        Face tmp, LE, RW;
        recon1(m, l, rr, tmp, LE);
        recon1(l, rr, p, RW, tmp);
        float f0, f1, f2, sL, sR;
        face_x(LE, RW, f0, f1, f2, sL, sR);
        sf[t] = f0; sf[NF + t] = f1; sf[2 * NF + t] = f2; sf[3 * NF + t] = sL; sf[4 * NF + t] = sR;
    }
    __syncthreads();
    float dH[4], dHU[4], dHV[4];
    #pragma unroll
    for (int q = 0; q < 4; ++q) {
        int r = ty + 8 * q;
        int tw = r * (TX + 1) + tx, te = tw + 1;
        dH[q]  = -(sf[te] - sf[tw]);
        dHU[q] = -((sf[NF + te] - sf[NF + tw]) + (sf[3 * NF + te] - sf[4 * NF + tw]));
        dHV[q] = -(sf[2 * NF + te] - sf[2 * NF + tw]);
    }
    __syncthreads();
    // y faces: 33 face rows x 32 columns; face row f lies between tile rows f+1 and f+2
    for (int t = tid; t < NF; t += 256) {
        int fr = t / TX, c = t - fr * TX;
        int tc = c + HALO, rl = fr + 1;
        St m = tld(sh, sz, shu, shv, rl - 1, tc), l = tld(sh, sz, shu, shv, rl, tc);
        St rr = tld(sh, sz, shu, shv, rl + 1, tc), p = tld(sh, sz, shu, shv, rl + 2, tc);
        Face tmp, LN, RS;
        recon1(m, l, rr, tmp, LN);
        recon1(l, rr, p, RS, tmp);
        float g0, g1, g2, sL, sR;
        face_y(LN, RS, g0, g1, g2, sL, sR);
        sf[t] = g0; sf[NF + t] = g1; sf[2 * NF + t] = g2; sf[3 * NF + t] = sL; sf[4 * NF + t] = sR;
    }
    __syncthreads();
    float dt = *dtp;
    float r_ = dt / dx;
    #pragma unroll
    for (int q = 0; q < 4; ++q) {
        int r = ty + 8 * q;
        int ts = r * TX + tx, tn = ts + TX;
        dH[q]  += -(sf[tn] - sf[ts]);
        dHU[q] += -(sf[NF + tn] - sf[NF + ts]);
        dHV[q] += -((sf[2 * NF + tn] - sf[2 * NF + ts]) + (sf[3 * NF + tn] - sf[4 * NF + ts]));
        int tr = r + HALO, tc = tx + HALO;
        St c = tld(sh, sz, shu, shv, tr, tc);
        St w = tld(sh, sz, shu, shv, tr, tc - 1), e = tld(sh, sz, shu, shv, tr, tc + 1);
        St s = tld(sh, sz, shu, shv, tr - 1, tc), n = tld(sh, sz, shu, shv, tr + 1, tc);
        Face W, E, S, N;
        recon1(w, c, e, W, E); recon1(s, c, n, S, N);
        dHU[q] += 0.5f * G * (W.h + E.h) * (W.z - E.z);
        dHV[q] += 0.5f * G * (S.h + N.h) * (S.z - N.z);
        float hn = c.h + r_ * dH[q], hun = c.hu + r_ * dHU[q], hvn = c.hv + r_ * dHV[q];
        finish(hn, hun, hvn, dt);
        int k = (j0 + tr) * sx + (i0 + tc);
        ho[k] = a * hp[k] + b * hn; huo[k] = a * hup[k] + b * hun; hvo[k] = a * hvp[k] + b * hvn;
    }
}

// MUSCL-Hancock: the predictor is shared through shared memory (computed ~1.06x per cell per pass, two passes),
// the four face fluxes are computed per owned cell. Predicted faces stored as (h, hu, hv); z recomputed.
#define NPF (34 * 32)
extern "C" __global__ void __launch_bounds__(256)
mh_tiled(const float* __restrict__ h, const float* __restrict__ z, const float* __restrict__ hu,
         const float* __restrict__ hv, float* __restrict__ ho, float* __restrict__ huo,
         float* __restrict__ hvo, const float* __restrict__ dtp, int nx, int ny, int sx, float dx) {
    __shared__ float sh[TW * TW], sz[TW * TW], shu[TW * TW], shv[TW * TW];   // 20.7 KB
    __shared__ float pf[6 * NPF];                                            // 26.1 KB
    int tx = threadIdx.x, ty = threadIdx.y, tid = ty * 32 + tx;
    int i0 = blockIdx.x * TX, j0 = blockIdx.y * TY;
    for (int t = tid; t < TW * TW; t += 256) {
        int r = t / TW, c = t - r * TW;
        int k = (j0 + r) * sx + (i0 + c);
        sh[t] = h[k]; sz[t] = z[k]; shu[t] = hu[k]; shv[t] = hv[k];
    }
    __syncthreads();
#if EARLY_EXIT
    {
        int wet = 0;
        for (int t = tid; t < TW * TW; t += 256) wet |= (sh[t] >= HEPS);
        if (!__syncthreads_or(wet)) {
            for (int q = 0; q < 4; ++q) {
                int r = ty + 8 * q;
                int k = (j0 + r + 2) * sx + (i0 + tx + 2);
                int t = (r + 2) * TW + tx + 2;
                ho[k] = sh[t]; huo[k] = shu[t]; hvo[k] = shv[t];
            }
            return;
        }
    }
#endif
    float dt = *dtp;
    float hdt = 0.5f * dt / dx;
    // pass X: predicted W/E faces of the cells in tile columns 1..34, rows 2..33; index t = r*34 + c
    for (int t = tid; t < NPF; t += 256) {
        int r = t / 34, c = t - r * 34;
        int tr = r + 2, tc = c + 1;
        St cc = tld(sh, sz, shu, shv, tr, tc);
        St w = tld(sh, sz, shu, shv, tr, tc - 1), e = tld(sh, sz, shu, shv, tr, tc + 1);
        St s = tld(sh, sz, shu, shv, tr - 1, tc), n = tld(sh, sz, shu, shv, tr + 1, tc);
        Face W, E, S, N;
        recon1(w, cc, e, W, E); recon1(s, cc, n, S, N); hancock(W, E, S, N, hdt);
        pf[t] = W.h; pf[NPF + t] = W.hu; pf[2 * NPF + t] = W.hv;
        pf[3 * NPF + t] = E.h; pf[4 * NPF + t] = E.hu; pf[5 * NPF + t] = E.hv;
    }
    __syncthreads();
    float dH[4], dHU[4], dHV[4], hWc[4], hEc[4], zWc[4], zEc[4];
    #pragma unroll
    for (int q = 0; q < 4; ++q) {
        int r = ty + 8 * q;
        int tr = r + 2, tc = tx + 2;
        int tc_ = r * 34 + tx + 1, tw_ = tc_ - 1, te_ = tc_ + 1;
        St ww = tld(sh, sz, shu, shv, tr, tc - 2), w = tld(sh, sz, shu, shv, tr, tc - 1);
        St c = tld(sh, sz, shu, shv, tr, tc);
        St e = tld(sh, sz, shu, shv, tr, tc + 1), ee = tld(sh, sz, shu, shv, tr, tc + 2);
        float zlo, zhi;
        Face wE, cW, cE, eW;
        recon_z1(ww, w, c, zlo, zhi); wE.z = zhi;
        recon_z1(w, c, e, cW.z, cE.z);
        recon_z1(c, e, ee, eW.z, zhi);
        wE.h = pf[3 * NPF + tw_]; wE.hu = pf[4 * NPF + tw_]; wE.hv = pf[5 * NPF + tw_];
        cW.h = pf[tc_]; cW.hu = pf[NPF + tc_]; cW.hv = pf[2 * NPF + tc_];
        cE.h = pf[3 * NPF + tc_]; cE.hu = pf[4 * NPF + tc_]; cE.hv = pf[5 * NPF + tc_];
        eW.h = pf[te_]; eW.hu = pf[NPF + te_]; eW.hv = pf[2 * NPF + te_];
        float fw0, fw1, fw2, sLw, sRw, fe0, fe1, fe2, sLe, sRe;
        face_x(wE, cW, fw0, fw1, fw2, sLw, sRw);
        face_x(cE, eW, fe0, fe1, fe2, sLe, sRe);
        dH[q] = -(fe0 - fw0); dHU[q] = -((fe1 - fw1) + (sLe - sRw)); dHV[q] = -(fe2 - fw2);
        hWc[q] = cW.h; hEc[q] = cE.h; zWc[q] = cW.z; zEc[q] = cE.z;
    }
    __syncthreads();
    // pass Y: predicted S/N faces of the cells in tile rows 1..34, columns 2..33; index t = r*32 + c
    for (int t = tid; t < NPF; t += 256) {
        int r = t / 32, c = t - r * 32;
        int tr = r + 1, tc = c + 2;
        St cc = tld(sh, sz, shu, shv, tr, tc);
        St w = tld(sh, sz, shu, shv, tr, tc - 1), e = tld(sh, sz, shu, shv, tr, tc + 1);
        St s = tld(sh, sz, shu, shv, tr - 1, tc), n = tld(sh, sz, shu, shv, tr + 1, tc);
        Face W, E, S, N;
        recon1(w, cc, e, W, E); recon1(s, cc, n, S, N); hancock(W, E, S, N, hdt);
        pf[t] = S.h; pf[NPF + t] = S.hu; pf[2 * NPF + t] = S.hv;
        pf[3 * NPF + t] = N.h; pf[4 * NPF + t] = N.hu; pf[5 * NPF + t] = N.hv;
    }
    __syncthreads();
    float r_ = dt / dx;
    #pragma unroll
    for (int q = 0; q < 4; ++q) {
        int r = ty + 8 * q;
        int tr = r + 2, tc = tx + 2;
        int tc_ = (r + 1) * 32 + tx, ts_ = tc_ - 32, tn_ = tc_ + 32;
        St ss = tld(sh, sz, shu, shv, tr - 2, tc), s = tld(sh, sz, shu, shv, tr - 1, tc);
        St c = tld(sh, sz, shu, shv, tr, tc);
        St n = tld(sh, sz, shu, shv, tr + 1, tc), nn = tld(sh, sz, shu, shv, tr + 2, tc);
        float zlo, zhi;
        Face sN, cS, cN, nS;
        recon_z1(ss, s, c, zlo, zhi); sN.z = zhi;
        recon_z1(s, c, n, cS.z, cN.z);
        recon_z1(c, n, nn, nS.z, zhi);
        sN.h = pf[3 * NPF + ts_]; sN.hu = pf[4 * NPF + ts_]; sN.hv = pf[5 * NPF + ts_];
        cS.h = pf[tc_]; cS.hu = pf[NPF + tc_]; cS.hv = pf[2 * NPF + tc_];
        cN.h = pf[3 * NPF + tc_]; cN.hu = pf[4 * NPF + tc_]; cN.hv = pf[5 * NPF + tc_];
        nS.h = pf[tn_]; nS.hu = pf[NPF + tn_]; nS.hv = pf[2 * NPF + tn_];
        float gs0, gs1, gs2, sLs, sRs, gn0, gn1, gn2, sLn, sRn;
        face_y(sN, cS, gs0, gs1, gs2, sLs, sRs);
        face_y(cN, nS, gn0, gn1, gn2, sLn, sRn);
        dH[q]  += -(gn0 - gs0);
        dHU[q] += -(gn1 - gs1) + 0.5f * G * (hWc[q] + hEc[q]) * (zWc[q] - zEc[q]);
        dHV[q] += -((gn2 - gs2) + (sLn - sRs)) + 0.5f * G * (cS.h + cN.h) * (cS.z - cN.z);
        float hn = c.h + r_ * dH[q], hun = c.hu + r_ * dHU[q], hvn = c.hv + r_ * dHV[q];
        finish(hn, hun, hvn, dt);
        int k = (j0 + tr) * sx + (i0 + tc);
        ho[k] = hn; huo[k] = hun; hvo[k] = hvn;
    }
}
