// The polygon step on the GPU (W45, stage 5): decision 19's scheme on the strip's cells and faces, the twin of
// wadi2d/solver/poly/kernel.py statement for statement. One thread per face or per cell; a cell gathers over its
// faces through a CSR (ptr, face, sign) so no sum needs an atomic and every launch is deterministic. The last
// cells of the list are ghosts, the tile cells the strip touches: they read the lattice arrays through their state
// index (P.dx, STRIDE from the generated header) exactly as wadi2d/strips/hybrid.py adds them on the CPU.

// [3b] The face level differences, or zero on a closed, dry or thin face.
extern "C" __global__ void poly_levels(const int nf, const int* __restrict__ L, const int* __restrict__ R,
                                       const float* __restrict__ fl, const float* __restrict__ fr,
                                       const float* __restrict__ h, const float* __restrict__ d,
                                       float* __restrict__ Dl) {
    const int f = blockIdx.x * blockDim.x + threadIdx.x;
    if (f >= nf) return;
    const int a = L[f], b = R[f];
    const float e_l = d[a] - fl[f];
    const float e_r = d[b] - fr[f];
    Dl[f] = (e_l > P.e_wet && e_r > P.e_wet && h[a] > 0.0f && h[b] > 0.0f) ? e_r - e_l : 0.0f;
}

// [3a] Perot cell momentum vectors and [3b] Green-Gauss gradients, a ghost's lattice part first.
extern "C" __global__ void poly_sums(const int nc, const int nreal, const int* __restrict__ ptr,
                                     const int* __restrict__ cf, const float* __restrict__ cs,
                                     const float* __restrict__ xf, const float* __restrict__ yf,
                                     const float* __restrict__ cx, const float* __restrict__ cy,
                                     const float* __restrict__ ln, const float* __restrict__ nfx,
                                     const float* __restrict__ nfy, const float* __restrict__ q,
                                     const float* __restrict__ h, const float* __restrict__ area,
                                     const float* __restrict__ Dl, const int* __restrict__ ghost,
                                     const unsigned char* __restrict__ ow, const unsigned char* __restrict__ oe,
                                     const unsigned char* __restrict__ on, const unsigned char* __restrict__ os,
                                     const float* __restrict__ zmin_t, const float* __restrict__ h_t,
                                     const float* __restrict__ d_t, const float* __restrict__ qx_t,
                                     const float* __restrict__ qy_t, float* __restrict__ Ux, float* __restrict__ Uy,
                                     float* __restrict__ Gx, float* __restrict__ Gy) {
    const int c = blockIdx.x * blockDim.x + threadIdx.x;
    if (c >= nc) return;
    float ux = 0.0f, uy = 0.0f, gx = 0.0f, gy = 0.0f;
    if (c >= nreal) {
        const int g = c - nreal;
        const int k = ghost[g];
        const float dx = P.dx;
        ux += 0.5f * dx * (qx_t[k] + qx_t[k + 1]);
        uy -= 0.5f * dx * (qy_t[k] + qy_t[k + STRIDE]);
        const float eta = zmin_t[k] + d_t[k];
        if (ow[g] && h_t[k - 1] > 0.0f && h_t[k] > 0.0f) gx += 0.5f * (eta - (zmin_t[k - 1] + d_t[k - 1])) * dx;
        if (oe[g] && h_t[k + 1] > 0.0f && h_t[k] > 0.0f) gx += 0.5f * ((zmin_t[k + 1] + d_t[k + 1]) - eta) * dx;
        if (on[g] && h_t[k - STRIDE] > 0.0f && h_t[k] > 0.0f)
            gy -= 0.5f * (eta - (zmin_t[k - STRIDE] + d_t[k - STRIDE])) * dx;
        if (os[g] && h_t[k + STRIDE] > 0.0f && h_t[k] > 0.0f)
            gy -= 0.5f * ((zmin_t[k + STRIDE] + d_t[k + STRIDE]) - eta) * dx;
    }
    for (int p = ptr[c]; p < ptr[c + 1]; ++p) {
        const int f = cf[p];
        const float s = cs[p];
        const float qf = q[f];
        if (qf != 0.0f) {
            ux += s * (xf[f] - cx[c]) * qf;
            uy += s * (yf[f] - cy[c]) * qf;
        }
        const float de = Dl[f];
        if (de != 0.0f) {
            const float w = 0.5f * de * ln[f];
            gx += w * nfx[f];
            gy += w * nfy[f];
        }
    }
    const float vol = h[c] * area[c];
    if (vol > 1e-9f) {
        Ux[c] = ux / vol;
        Uy[c] = uy / vol;
    } else {
        Ux[c] = 0.0f;
        Uy[c] = 0.0f;
    }
    Gx[c] = gx / area[c];
    Gy[c] = gy / area[c];
}

// [3a] The advection rate per cell: outflow times the upwind cell's velocity, a ghost's lattice part first.
extern "C" __global__ void poly_rates(const int nc, const int nreal, const int* __restrict__ ptr,
                                      const int* __restrict__ cf, const float* __restrict__ cs,
                                      const int* __restrict__ L, const int* __restrict__ R,
                                      const float* __restrict__ q, const float* __restrict__ Ux,
                                      const float* __restrict__ Uy, const int* __restrict__ ghost,
                                      const unsigned char* __restrict__ ow, const unsigned char* __restrict__ oe,
                                      const unsigned char* __restrict__ on, const unsigned char* __restrict__ os,
                                      const float* __restrict__ h_t, const float* __restrict__ qx_t,
                                      const float* __restrict__ qy_t, float* __restrict__ Rx,
                                      float* __restrict__ Ry) {
    const int c = blockIdx.x * blockDim.x + threadIdx.x;
    if (c >= nc) return;
    float rx = 0.0f, ry = 0.0f;
    if (c >= nreal) {
        const int g = c - nreal;
        const int k = ghost[g];
        const float dx = P.dx;
        for (int side = 0; side < 4; ++side) {
            bool opened;
            float q_out;
            int n;
            if (side == 0) { opened = ow[g]; q_out = -qx_t[k]; n = k - 1; }
            else if (side == 1) { opened = oe[g]; q_out = qx_t[k + 1]; n = k + 1; }
            else if (side == 2) { opened = on[g]; q_out = -qy_t[k]; n = k - STRIDE; }
            else { opened = os[g]; q_out = qy_t[k + STRIDE]; n = k + STRIDE; }
            if (!opened || q_out == 0.0f) continue;
            float ux, uy;
            if (q_out > 0.0f) {
                ux = Ux[c];
                uy = Uy[c];
            } else {
                const float vol = h_t[n] * dx * dx;
                if (vol > 1e-9f) {
                    ux = 0.5f * dx * (qx_t[n] + qx_t[n + 1]) / vol;
                    uy = -0.5f * dx * (qy_t[n] + qy_t[n + STRIDE]) / vol;
                } else {
                    ux = 0.0f;
                    uy = 0.0f;
                }
            }
            rx += q_out * ux;
            ry += q_out * uy;
        }
    }
    for (int p = ptr[c]; p < ptr[c + 1]; ++p) {
        const int f = cf[p];
        const float qf = q[f];
        if (qf != 0.0f) {
            const int up = qf > 0.0f ? L[f] : R[f];
            rx += cs[p] * qf * Ux[up];
            ry += cs[p] * qf * Uy[up];
        }
    }
    Rx[c] = rx;
    Ry[c] = ry;
}

// [1] to [6] on every face; the largest wave frequency into *wave when asked.
extern "C" __global__ void poly_faces(
    const int nf, const float dt, const int want_wave, const int* __restrict__ L, const int* __restrict__ R,
    const float* __restrict__ ln, const float* __restrict__ nfx, const float* __restrict__ nfy,
    const float* __restrict__ xf, const float* __restrict__ yf, const float* __restrict__ dn,
    const float* __restrict__ sx, const float* __restrict__ sy, const float* __restrict__ fl,
    const float* __restrict__ fr, const float* __restrict__ gl, const float* __restrict__ gr,
    const float* __restrict__ ef, const float* __restrict__ cw, const float* __restrict__ ftab,
    const float* __restrict__ area, const float* __restrict__ cx, const float* __restrict__ cy,
    const float* __restrict__ h, const float* __restrict__ d, const float* __restrict__ om,
    const float* __restrict__ u, const float* __restrict__ m, const float* __restrict__ q,
    const float* __restrict__ Ux, const float* __restrict__ Uy, const float* __restrict__ Rx,
    const float* __restrict__ Ry, const float* __restrict__ Gx, const float* __restrict__ Gy,
    const float* __restrict__ Dl, float* __restrict__ u1, float* __restrict__ m1, float* __restrict__ q1,
    float* __restrict__ wave) {
    const int f = blockIdx.x * blockDim.x + threadIdx.x;
    if (f >= nf) return;
    const float g = P.g, dx = P.dx;
    const int a = L[f], b = R[f];
    const float e_l = d[a] - fl[f];
    const float e_r = d[b] - fr[f];
    const float uf = u[f];
    const float e_lp = fmaxf(e_l, 0.0f);
    const float e_rp = fmaxf(e_r, 0.0f);
    const bool from_left = uf > 0.0f || (uf == 0.0f && e_l >= e_r);
    const float eup = from_left ? e_lp : e_rp;
    if (eup <= P.e_wet) {
        u1[f] = 0.0f;
        m1[f] = 0.0f;
        q1[f] = 0.0f;
        return;
    }
    const float* tab = ftab + 2 * P.rows * f;
    float A, T, W;
    face_lookup(eup, ef[f], tab, A, T, W);
    const float dnf = dn[f];
    const float v_l = h[a] * area[a];
    const float v_r = h[b] * area[b];
    const float hup = from_left ? h[a] : h[b];
    // [1] section: thin flow on a slope spreads over the cell; the limit fades as the downstream side fills
    float rho = 1.0f;
    float d_eta = e_rp - e_lp;
    if (Dl[f] != 0.0f) d_eta -= 0.5f * ((Gx[a] + Gx[b]) * sx[f] + (Gy[a] + Gy[b]) * sy[f]);
    if (P.sheet) {
        const float avol = hup * ln[f];
        const float edown = from_left ? e_rp : e_lp;
        if (avol < A) {
            const float s = fminf(e_lp, e_rp) / fmaxf(e_lp, e_rp);
            const float s2 = s * s;
            const float alpha = s2 * s2;
            rho = alpha + (1.0f - alpha) * avol / A;
        }
        if (edown <= 0.0f) {
            // [2] disconnected: the driver is the mean-surface drop, clipped at the crest
            const float g_u = from_left ? gl[f] : gr[f];
            const float g_d = from_left ? gr[f] : gl[f];
            const float h_d = from_left ? h[b] : h[a];
            const float drop = (hup - g_u) - fmaxf(h_d - g_d, 0.5f * (g_u - g_d));
            const float level_drop = e_l > e_r ? e_l - e_r : e_r - e_l;
            const float drive = fmaxf(eup, fminf(drop, level_drop));
            d_eta = from_left ? -drive : drive;
        }
    }
    // [3] advection from the cell vectors, [4] momentum and pressure
    const float abar = 0.5f * (v_l + v_r) / dnf;
    const float press = dt * g * d_eta / dnf;
    float us;
    if (abar > 1e-6f * dx) {
        const float flux = 0.5f * (nfx[f] * (Rx[a] + Rx[b]) + nfy[f] * (Ry[a] + Ry[b]));
        us = (m[f] - dt * flux / dnf) / abar - press;
    } else {
        us = uf - press;
    }
    // [5] friction, implicit in the speed, with the transverse velocity from the cell vectors
    const float tx = -nfy[f], ty = nfx[f];
    const float wa = v_l > 1e-9f ? 1.0f : 0.0f;
    const float wb = v_r > 1e-9f ? 1.0f : 0.0f;
    float vb = 0.0f;
    if (wa + wb > 0.0f) vb = (wa * (Ux[a] * tx + Uy[a] * ty) + wb * (Ux[b] * tx + Uy[b] * ty)) / (wa + wb);
    const float T3 = T * T * T * cbrtf(T);
    float fric = A * A / fmaxf(T3, 1e-30f);
    if (rho < 1.0f) fric = fric / fmaxf(rho * cbrtf(rho), 1e-12f);
    const float aa = dt * g * fric;
    const float sp = sqrtf(us * us + vb * vb);
    float un = 2.0f * us / (1.0f + sqrtf(1.0f + 4.0f * aa * sp));
    if (fabsf(un) > P.u_max) un = un > 0.0f ? P.u_max : -P.u_max;
    // [6] crest face: at most critical flow over the crest for this head
    float qn = A * rho * un;
    float c = cw[f];
    if (c != 0.0f) {
        float Ac = A, Wc = W;
        if (c < 0.0f) {
            // the energy head of the upstream cell, this face's own flow left out of its velocity (W43)
            c = -c;
            const int up = from_left ? a : b;
            const float vup = from_left ? v_l : v_r;
            const float sign = from_left ? 1.0f : -1.0f;
            float ux = Ux[up], uy = Uy[up];
            if (vup > 1e-9f) {
                ux -= sign * (xf[f] - cx[up]) * q[f] / vup;
                uy -= sign * (yf[f] - cy[up]) * q[f] / vup;
            }
            float Tc;
            face_lookup(eup + 0.5f * (ux * ux + uy * uy) / g, ef[f], tab, Ac, Tc, Wc);
        }
        const float qc = c * Ac * sqrtf(Ac / fmaxf(Wc, 1e-9f));
        if (fabsf(qn) > qc) {
            qn = qn > 0.0f ? qc : -qc;
            un = qn / fmaxf(A * rho, 1e-12f);
        }
    }
    u1[f] = un;
    m1[f] = abar * un;
    q1[f] = qn;
    if (want_wave) {
        if (not_finite(un)) {
            atomic_fmax(wave, 1e30f);
            return;
        }
        const float dup = from_left ? d[a] : d[b];
        if (dup > P.h_cfl) {
            const int up_c = from_left ? a : b;
            const int dn_c = from_left ? b : a;
            float wet_plan = om[up_c] * area[up_c];
            if (d[dn_c] > P.h_cfl) wet_plan = fminf(wet_plan, om[dn_c] * area[dn_c]);
            const float w = sqrtf(fmaxf(g * A * rho * dnf / fmaxf(wet_plan, P.a_min * dx * dx), 0.0f));
            const float fr_ = (fabsf(un) + fminf(P.lead * fabsf(un - uf), 2.0f * w) + w) / dnf;
            if (fr_ > 0.0f) atomic_fmax(wave, fr_);
        }
    }
}

// What each cell would give out this step, and its ratio: a real cell gives at most what it holds, a ghost at most
// what its lattice faces, which come first, left it.
extern "C" __global__ void poly_limit(const int nc, const int nreal, const float dt, const int* __restrict__ ptr,
                                      const int* __restrict__ cf, const float* __restrict__ cs,
                                      const float* __restrict__ q1, const float* __restrict__ h,
                                      const float* __restrict__ area, const int* __restrict__ ghost,
                                      const float* __restrict__ h_t, const float* __restrict__ r_t,
                                      const float* __restrict__ qx1_t, const float* __restrict__ qy1_t,
                                      float* __restrict__ out, float* __restrict__ r) {
    const int c = blockIdx.x * blockDim.x + threadIdx.x;
    if (c >= nc) return;
    float o = 0.0f;
    for (int p = ptr[c]; p < ptr[c + 1]; ++p) {
        const float qo = cs[p] * q1[cf[p]];
        if (qo > 0.0f) o += qo;
    }
    out[c] = o;
    if (c < nreal) {
        const float have = fmaxf(h[c], 0.0f) * area[c];
        r[c] = o * dt > have ? have / (o * dt) : 1.0f;
    } else {
        const int k = ghost[c - nreal];
        const float lattice = fmaxf(qx1_t[k + 1], 0.0f) + fmaxf(-qx1_t[k], 0.0f) + fmaxf(qy1_t[k + STRIDE], 0.0f) +
                              fmaxf(-qy1_t[k], 0.0f);
        const float have = fmaxf(h_t[k], 0.0f) * P.dx * P.dx;
        const float avail = fmaxf(have - dt * r_t[k] * lattice, 0.0f);
        r[c] = o * dt > avail ? avail / (o * dt) : 1.0f;
    }
}

// The scaled discharges.
extern "C" __global__ void poly_scale(const int nf, const int* __restrict__ L, const int* __restrict__ R,
                                      const float* __restrict__ q1, const float* __restrict__ r,
                                      float* __restrict__ q) {
    const int f = blockIdx.x * blockDim.x + threadIdx.x;
    if (f >= nf) return;
    const float qf = q1[f];
    q[f] = qf * (qf > 0.0f ? r[L[f]] : r[R[f]]);
}

// The divergence of every cell, the new depth, level and wet share of the real ones; res carries what the clamp at
// zero took, as the tile kernel's residual does.
extern "C" __global__ void poly_update(const int nc, const int nreal, const float dt, const int want_wave,
                                       const int* __restrict__ ptr, const int* __restrict__ cf,
                                       const float* __restrict__ cs, const float* __restrict__ area,
                                       const float* __restrict__ hc, const float* __restrict__ dtab,
                                       const float* __restrict__ q, const float* __restrict__ src,
                                       float* __restrict__ div, float* __restrict__ res, float* __restrict__ h,
                                       float* __restrict__ d, float* __restrict__ om) {
    const int c = blockIdx.x * blockDim.x + threadIdx.x;
    if (c >= nc) return;
    float dv = 0.0f;
    for (int p = ptr[c]; p < ptr[c + 1]; ++p) dv += cs[p] * q[cf[p]];
    div[c] = dv;
    if (c >= nreal) return;
    const float inc = res[c] + dt * src[c] - dt * dv / area[c];
    const float total = h[c] + inc;
    const float hn = fmaxf(total, 0.0f);
    res[c] = total > 0.0f ? inc - (total - h[c]) : 0.0f;
    h[c] = hn;
    const float* tab = dtab + P.rows * c;
    d[c] = cell_level(hn, hc[c], tab);
    if (want_wave) om[c] = cell_plan(hn, hc[c], tab);
}

// A ghost's net outflow into the tile's source term, and the source saved to restore after the tile update.
extern "C" __global__ void poly_ghost_src(const int ng, const int nreal, const int* __restrict__ ghost,
                                          const float* __restrict__ div, float* __restrict__ saved,
                                          float* __restrict__ src_t) {
    const int g = blockIdx.x * blockDim.x + threadIdx.x;
    if (g >= ng) return;
    const int k = ghost[g];
    const float s = src_t[k];
    saved[g] = s;
    src_t[k] = s - div[nreal + g] / (P.dx * P.dx);
}

// Each interface's discharge and velocity into the tile's closed face on that edge: one thread per unique slot sums
// its faces (a fixed order, no atomic), writes the discharge, then every copy of the slot gets the velocity.
extern "C" __global__ void poly_edges(const int nslot, const int nreal, const int* __restrict__ slot_ptr,
                                      const int* __restrict__ slot_face, const float* __restrict__ slot_sign,
                                      const int* __restrict__ unique, const int* __restrict__ ghost_of,
                                      const int* __restrict__ copy_ptr, const int* __restrict__ copies,
                                      const float* __restrict__ q, const float* __restrict__ h,
                                      float* __restrict__ discharge, float* __restrict__ velocity) {
    const int s = blockIdx.x * blockDim.x + threadIdx.x;
    if (s >= nslot) return;
    double q_edge = 0.0;
    for (int p = slot_ptr[s]; p < slot_ptr[s + 1]; ++p) q_edge += (double)q[slot_face[p]] * (double)slot_sign[p];
    const double depth = fmax((double)h[nreal + ghost_of[s]], 1e-6);
    const float speed = (float)(q_edge / (depth * (double)P.dx));
    discharge[unique[s]] = (float)q_edge;
    for (int p = copy_ptr[s]; p < copy_ptr[s + 1]; ++p) velocity[copies[p]] = speed;
}

// The ghosts' state from the tile arrays, one launch in place of three gathers.
extern "C" __global__ void poly_mirror(const int ng, const int nreal, const int* __restrict__ ghost,
                                       const float* __restrict__ h_t, const float* __restrict__ d_t,
                                       const float* __restrict__ om_t, float* __restrict__ h, float* __restrict__ d,
                                       float* __restrict__ om) {
    const int g = blockIdx.x * blockDim.x + threadIdx.x;
    if (g >= ng) return;
    const int k = ghost[g];
    h[nreal + g] = h_t[k];
    d[nreal + g] = d_t[k];
    om[nreal + g] = om_t[k];
}

// The tile's source restored after its update took the ghosts' outflow.
extern "C" __global__ void poly_restore(const int ng, const int* __restrict__ ghost, const float* __restrict__ saved,
                                        float* __restrict__ src_t) {
    const int g = blockIdx.x * blockDim.x + threadIdx.x;
    if (g >= ng) return;
    src_t[ghost[g]] = saved[g];
}

// The run's maxima per real cell: depth, mean depth, speed where deeper than speed_depth, and depth x speed.
extern "C" __global__ void poly_cell_maxima(const int n, const float speed_depth, const float* __restrict__ d,
                                            const float* __restrict__ h, const float* __restrict__ Ux,
                                            const float* __restrict__ Uy, float* __restrict__ max_d,
                                            float* __restrict__ max_h, float* __restrict__ max_s,
                                            float* __restrict__ max_dv) {
    const int c = blockIdx.x * blockDim.x + threadIdx.x;
    if (c >= n) return;
    const float dc = d[c];
    const float s = dc > speed_depth ? hypotf(Ux[c], Uy[c]) : 0.0f;
    max_d[c] = fmaxf(max_d[c], dc);
    max_h[c] = fmaxf(max_h[c], h[c]);
    max_s[c] = fmaxf(max_s[c], s);
    max_dv[c] = fmaxf(max_dv[c], dc * s);
}

// The largest discharge of every face.
extern "C" __global__ void poly_face_maxima(const int nf, const float* __restrict__ q, float* __restrict__ max_q) {
    const int f = blockIdx.x * blockDim.x + threadIdx.x;
    if (f >= nf) return;
    max_q[f] = fmaxf(max_q[f], fabsf(q[f]));
}

// What crossed the interface faces onto boundary cells this step: the running total and each ghost's own, in double.
extern "C" __global__ void poly_tally(const int nb, const int* __restrict__ faces, const int* __restrict__ ghosts,
                                      const float* __restrict__ q, const float dt, double* __restrict__ left,
                                      double* __restrict__ left_ghost) {
    __shared__ double part[256];
    const int i = blockIdx.x * blockDim.x + threadIdx.x;
    const double crossed = i < nb ? (double)q[faces[i]] : 0.0;
    part[threadIdx.x] = crossed;
    if (i < nb) atomicAdd(&left_ghost[ghosts[i]], crossed * (double)dt);
    __syncthreads();
    for (int stride = blockDim.x / 2; stride > 0; stride >>= 1) {
        if (threadIdx.x < stride) part[threadIdx.x] += part[threadIdx.x + stride];
        __syncthreads();
    }
    if (threadIdx.x == 0) atomicAdd(left, part[0] * (double)dt);
}
