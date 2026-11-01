// Momentum update of all own faces of the active tiles. One thread handles CELLS_PER_THREAD rows of a tile column.
//
// Scheme: level per cell, velocity per face. Momentum M = Abar u is conservative, because the velocity form
// converges to the wrong shock speed. Still water gives exactly no drive: the pressure term is the difference of
// the two depths over the same invert, so no absolute elevation and no bed-slope term exists to cancel.

template <int S, int Q_P>
__device__ __forceinline__ float face_step(
    const int k, const int id, const float dt,
    const float* __restrict__ h, const float* __restrict__ d, const float* __restrict__ u,
    const float* __restrict__ m, const float* __restrict__ q, const float* __restrict__ qp,
    const float* __restrict__ vp, const float* __restrict__ fl, const float* __restrict__ fr,
    const float* __restrict__ gl, const float* __restrict__ gr, const float* __restrict__ ef,
    const float* __restrict__ cw, const float* __restrict__ ftab,
    float* __restrict__ u1, float* __restrict__ m1, float* __restrict__ q1) {
    const float eL = d[k - S] - fl[id];
    const float eR = d[k] - fr[id];
    const float uf = u[k];
    const float eLp = fmaxf(eL, 0.0f);
    const float eRp = fmaxf(eR, 0.0f);
    const bool from_left = uf > 0.0f || (uf == 0.0f && eL >= eR);
    const float eup = from_left ? eLp : eRp;
    if (eup <= P.e_wet) {
        u1[k] = 0.0f;
        m1[k] = 0.0f;
        q1[k] = 0.0f;
        return 0.0f;
    }
    float A, T, W;
    face_lookup(eup, ef[id], ftab + 2 * P.rows * id, A, T, W);
    const float hL = h[k - S];
    const float hR = h[k];
    const float hup = from_left ? hL : hR;
    const float dx = P.dx;

    // [1] section: thin flow on a slope spreads over the cell, so the section is limited by volume / length.
    // The limit fades as the downstream side fills: a drowned face passes its whole area.
    float rho = 1.0f;
    float dEta = eRp - eLp;
    if (P.sheet) {
        const float Avol = hup * dx;
        const float edown = from_left ? eRp : eLp;
        if (Avol < A) {
            const float s = fminf(edown / eup, 1.0f);
            const float s2 = s * s;
            const float alpha = s2 * s2;
            rho = alpha + (1.0f - alpha) * Avol / A;
        }
        if (edown <= 0.0f) {
            // [2] disconnected: the downstream level is below the invert; the driver is the mean-surface drop,
            // clipped at the crest, so thin sheet flow feels the bed slope and a crest does not
            const float gU = from_left ? gl[id] : gr[id];
            const float gD = from_left ? gr[id] : gl[id];
            const float hD = from_left ? hR : hL;
            const float drop = (hup - gU) - fmaxf(hD - gD, 0.5f * (gU - gD));
            const float level_drop = eL > eR ? eL - eR : eR - eL;
            const float drive = fmaxf(eup, fminf(drop, level_drop));
            dEta = from_left ? -drive : drive;
        }
    }

    // [3] upwinded momentum fluxes at the two cell centres, then the transverse pair
    const float um = u[k - S];
    const float up = u[k + S];
    const float QcL = 0.5f * (q[k - S] + q[k]);
    const float QcR = 0.5f * (q[k] + q[k + S]);
    const float sL = QcL > 0.0f ? ustar(um, u[k - 2 * S], uf) : ustar(uf, up, um);
    const float sR = QcR > 0.0f ? ustar(uf, um, up) : ustar(up, u[k + 2 * S], uf);
    float flux = QcR * sR - QcL * sL;
    const float QyS = 0.5f * (qp[k - S] + qp[k]);
    const float QyN = 0.5f * (qp[k - S + Q_P] + qp[k + Q_P]);
    const float uS = u[k - Q_P];
    const float uN = u[k + Q_P];
    const float usS = QyS > 0.0f ? ustar(uS, u[k - 2 * Q_P], uf) : ustar(uf, uN, uS);
    const float usN = QyN > 0.0f ? ustar(uf, uS, uN) : ustar(uN, u[k + 2 * Q_P], uf);
    flux += QyN * usN - QyS * usS;

    // [4] momentum and pressure
    const float Abar = 0.5f * (hL + hR) * dx;
    const float press = dt * P.g * dEta / dx;
    float us = Abar > 1e-6f * dx ? (m[k] - dt * flux / dx) / Abar - press : uf - press;

    // [5] friction, implicit in the speed, with the transverse velocity at the face
    const float vb = 0.25f * (vp[k - S] + vp[k] + vp[k - S + Q_P] + vp[k + Q_P]);
    const float T3 = T * T * T * cbrtf(T);
    float fric = A * A / fmaxf(T3, 1e-30f);
    if (rho < 1.0f) fric /= fmaxf(rho * cbrtf(rho), 1e-12f);
    const float a = dt * P.g * fric;
    const float sp = sqrtf(us * us + vb * vb);
    float un = 2.0f * us / (1.0f + sqrtf(1.0f + 4.0f * a * sp));
    if (fabsf(un) > P.u_max) un = copysignf(P.u_max, un);

    // [6] crest face: the discharge cannot exceed critical flow over the crest for this head
    float qn = A * rho * un;
    const float c = cw[id];
    if (c > 0.0f) {
        const float qc = c * A * sqrtf(A / fmaxf(W, 1e-9f));
        if (fabsf(qn) > qc) {
            qn = copysignf(qc, qn);
            un = qn / fmaxf(A * rho, 1e-12f);
        }
    }
    u1[k] = un;
    m1[k] = Abar * un;
    q1[k] = qn;
    const float dup = from_left ? d[k - S] : d[k];
    return dup > P.h_cfl ? fabsf(un) + sqrtf(P.g * dup) : 0.0f;
}

extern "C" __global__ void faces(
    const int* __restrict__ active, const float dt, const int want_wave,
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
    const int t = active[blockIdx.x];
    const int i = threadIdx.x;
    float w = 0.0f;
    for (int r = 0; r < CELLS_PER_THREAD; ++r) {
        const int j = threadIdx.y * CELLS_PER_THREAD + r;
        const int k = t * STRIDE2 + (j + HALO) * STRIDE + i + HALO;
        const int id = t * TILE2 + j * TILE + i;
        const float wx = face_step<1, STRIDE>(k, id, dt, h, d, u, mx, qx, qy, v, flx, frx, glx, grx, efx, cwx, ftabx,
                                              u1, mx1, qx1);
        const float wy = face_step<STRIDE, 1>(k, id, dt, h, d, v, my, qy, qx, u, fly, fry, gly, gry, efy, cwy, ftaby,
                                              v1, my1, qy1);
        w = fmaxf(w, fmaxf(wx, wy));
    }
    if (want_wave) atomic_fmax(wave + t, w);
}
