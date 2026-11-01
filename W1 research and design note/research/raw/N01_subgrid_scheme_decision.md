# N01 Which discrete formulation carries the sub-grid tables

Date: 2026-10-31

## Scope and how to read this note

Question: which discrete formulation should carry cell volume-vs-level and face area/width/conveyance-vs-level tables (0.5 m DEM, 10-40 m cells) in an explicit solver, on wadi terrain with supercritical flow, jumps, wet/dry fronts, thin rain-on-grid films on 2-30 % slopes and crest faces. Candidate A: collocated Godunov with porosity. Candidate B: staggered C-grid.

Read in full: Volp et al. 2013 (as chapter 2 of Volp's thesis), Zijlema's Rankine-Hugoniot paper (preprint), Herbin et al. 2021, the SWASH technical documentation, the Rana/3Di limiter and sloping-terrain pages, van Ormondt et al. 2025 (SFINCS sub-grid). Abstract or highlights only: Stelling and Duinmeijer 2003, Stelling 2022, Casulli 2009, Stelling 2012, Oezgen et al. 2016. **Not reachable**: Stelling 2022 full text (ScienceDirect refused, the TU Delft repository is unreachable from this machine, so the VCE and TLC equations are unread), Kernkamp et al. 2011 (same), Sanders and Schubert 2019 (title only), Guinot et al. 2017 (bot wall). Stelling and Duinmeijer's equations here come through Zijlema and Volp, who reproduce them.

Tags: [Certain] read in a primary source or arithmetic; [Tested] my own 1D run, this session; [Likely] strong inference; [Guessing] gap filled by reasoning. Evidence is paraphrased with source and equation numbers; the session's copyright rule allows one short quotation and it is used once.

**The own tests are 1D, frictionless or friction-dominated, on flat-bottom or plane geometry, with no real DEM. Nothing here has been run in 2D.** Harness (throwaway, not in the repo): scratchpad `n01/` of this session. Scheme A in that harness is my implementation of MUSCL (eta, h, u) + HLLC + hydrostatic reconstruction + Heun at CFL 0.45.

## 1. Verdict

**B, staggered: one level per cell, one velocity per face, volume as the stored state.** [Likely]

Reasons, strongest first:

1. **The tables have a natural home in B and none in A.** V(eta) belongs to a cell, A_f(eta) and K_f(eta) to a face, and B's unknowns sit exactly there. Conveyance is a face quantity; in A momentum lives at the cell centre, so face conveyance has no place to act without splitting it across two cells. Volp's discrete momentum equation (eq. 2.34) needs no wave speed, no Riemann problem and no reconstruction of a partly wet face. N05's open issue "which depth defines a_L, a_R on a partially wet face" simply does not arise. [Certain for B; Likely for the contrast, since the Godunov sub-grid papers were not read in full]
2. **Well-balance is exact by construction.** The pressure term per unit mass is g (eta_R - eta_L) / dx, whatever the tables say; A_f never enters it, because Volp's V cancels between eq. 2.23 and 2.34. Still water stays still on any table, on any slope, with no source-term balancing. Zijlema lists the balancing and wet/dry repairs that Godunov schemes need and that this form avoids. [Certain]
3. **Rapidly varied flow is not B's weakness, provided the scheme is written correctly.** Zijlema proves a two-point upwind form satisfies both discrete Rankine-Hugoniot relations (his eq. 19, 27), reproduces momentum flux 137.909 exactly and head loss 5.49 cm against 5.55 cm (Table 1, 2). Herbin et al. prove that a MUSCL plus Heun staggered scheme keeps positive depth under a CFL condition, preserves the lake at rest, and is consistent with weak solutions. [Certain]
4. **Crest faces are native.** A face with A_f = 0 passes nothing and carries no velocity; a wall is the same case. In A a crest must be expressed through reconstructed face beds. [Certain, Rana obstacle behaviour in N09 finding 28]
5. **The thin-film remedy exists only on the B side.** Rana ships it, Stelling 2022 publishes one. No Godunov sub-grid treatment of flat level on steep cells was found. [Certain for what was found]
6. **It costs less per simulated second.** Forward-backward runs to about CFL 0.9 with one pressure and continuity pass and two advection passes per step; A at CFL 0.45 needs two full reconstruction-plus-Riemann passes. Stoker at N = 800: B 243 steps, A 381 x 2 flux passes. [Tested for the counts; the GCUPS of a staggered kernel are unmeasured]
7. **Precedent.** TUFLOW HPC, 3Di/Rana, SWASH, SFINCS and HEC-RAS 2D all carry a level per cell and a velocity or flux per face. [Certain; N02 findings 13, 16; N03]

**The strongest arguments against this verdict** [Tested unless tagged]:

- **A plain staggered scheme gets a thin crest badly wrong.** With a free overfall on a thin face the whole level drop drives the face velocity: discharge came out **5 to 100 times** critical, at the same head. A Godunov face stays within 54-122 % of critical without any rule (N09 finding 34). B therefore cannot go without the control-level rule in section 2.7. The rule is exact in my 1D test, but it is my derivation, not a published method.
- **Conservation in B is a property of careful coding, not of the form.** I broke it twice while building the test. Using the wrong mass flux in the advection, or the new velocity in the flux-divergence term, gives a shock in the wrong place that converges to the wrong answer (h_m 0.425 against 0.396), with no warning and machine-perfect mass. Rule 2.4(c) exists because of this.
- **A is more accurate per cell in L1: about 2 times on Stoker and 3 times on Ritter at N = 800** (section 4). B's upwind mass flux is first order; MUSCL on the mass flux narrows this to 1.4 and 2 times.
- **The evidence stops at 1D.** Zijlema says his findings carry over to 2D; he does not show it. EA Test 6A, an oblique jump, and a rotated channel are the tests that could reverse this verdict. They must be the first runs of the prototype.

Reject A for the production kernel. Keep the existing HLLC kernel only as the comparison baseline for 2D tests.

## 2. The discrete explicit equations

Square grid, cell size dx, all in one uniform-grid form. Cell c: state V_c (m3). Face f between cells L and R, positive from L to R: state u_f (m/s). Tables per cell: V(eta), its derivative Omega(eta) = dV/deta (wet plan area). Tables per face: A(eta), W(eta) (flow width), K(eta), with invert z_fmin. Crest faces also carry z_crest and a length factor phi_L = L_true / sum of staircase lengths (N09 E8), which multiplies W and A on that face.

### 2.1 Levels

eta_c from the inverse of V(eta). Store V and a per-cell datum. Compute level differences as (z_ref,R - z_ref,L) + (eta'_R - eta'_L), with z_ref differences stored per face, so float32 never subtracts two numbers near 1500 m. This extends decision 3 from "store depth" to "store volume, and never difference absolute levels". [Certain, arithmetic]

### 2.2 Order of one step (Zijlema Variant III, eq. 45-46; SWASH leapfrog) [Certain]

Known: V^n, u^(n-1/2), Q^(n-1/2) = the flux that actually moved the water in the previous continuity step, after the positivity limiter.

1. eta^n from V^n.
2. Predictor: u* = u^(n-1/2) - dt [ g (eta_R - eta_L)/dx + Adv1(u^(n-1/2)) ].
3. Corrector: u** = u^(n-1/2) - dt [ g (eta_R - eta_L)/dx + 0.5 (Adv1 + Adv2(u*)) ].
4. Choose upstream cell and read A_f, K_f (2.5, 2.6).
5. Friction (2.8): u^(n+1/2) from u**.
6. Positivity (2.9), Q_f = u_f A_f.
7. V^(n+1) = V^n - dt sum_f s_cf Q_f + dt S_c, with S_c rain minus losses, s_cf = +1 for outward. Mass conservation is exact: each face flux is unique. [Certain, Zijlema eq. 18-19; van Ormondt eq. 23 is the same volume form]

### 2.3 Why forward-backward and not Heun or RK4

Gravity on a C-grid is a pure oscillation with z = omega dt on the imaginary axis. Forward-backward is neutral up to z = 2 and second order by staggering in time; Zijlema's three variants all have this. Heun's amplification on that axis is |1 + iz - z^2/2|^2 = 1 + z^4/4 > 1, so it grows for any dt and relies on upwind dissipation; Herbin et al. run it near Courant 1/3. RK4 reaches z = 2.83 with four evaluations. [Certain, arithmetic and sources] Forward Euler with MUSCL advection is unsafe: Herbin's segregated Euler lost convergence through oscillations on refinement (their Table 3), and Heun cured it. That is why the corrector stays on the advection. [Certain]

### 2.4 Momentum advection, 2D, second order [Certain for 1D, Zijlema eq. 22-27 and Volp eq. 2.24-2.32; Likely for this 2D composition, unrun]

For an x-face f, momentum domain = half of L plus half of R, volume V_f = 0.5 (V_L + V_R).

Transport fluxes through the domain walls, all from Q^(n-1/2):

    QW = 0.5 (Q_f-1 + Q_f)                 through the centre of L
    QE = 0.5 (Q_f + Q_f+1)                 through the centre of R
    QS = 0.5 (Qy_south,L + Qy_south,R)     south wall
    QN = 0.5 (Qy_north,L + Qy_north,R)     north wall

Upwind transported velocities: uW = u_f-1 if QW > 0 else u_f; uE = u_f if QE > 0 else u_f+1; uS = u_south if QS > 0 else u_f; uN = u_f if QN > 0 else u_north.

    Adv(u) = (1/V_f) { QE uE - QW uW + QN uN - QS uS  -  u_f^(n-1/2) [ QE - QW + QN - QS ] }

(a) This reduces for positive 1D flow to (Q/V_f)(u_f - u_f-1), the momentum-conservative expansion form of Stelling and Duinmeijer. It conserves momentum because V_f^n - V_f^(n-1) = -dt [QE - QW + QN - QS] exactly when the Q are the continuity fluxes; the averages above satisfy that identity in 2D too. [Certain, algebra]

(b) Second order: in the corrector only, replace each upwind velocity by a limited extrapolation, for example for QW > 0: uW = u_f-1 + 0.5 minmod(u_f-1 - u_f-2, u_f - u_f-1). Zijlema states the jump relation survives a deferred correction of this kind; he reports MUSCL superior to first order on coarse grids. Fall back to first order wherever a stencil cell is thin (V/dx^2 below h_2nd; 1 mm in my tests), as every second-order code does (N05 finding 28). [Certain, Tested]

(c) **Two rules that must not be broken.** The Q in Adv must be the fluxes of the last continuity step, not u^(n-1/2) times a newly read area. The u_f multiplying the flux divergence stays at the old time level in both predictor and corrector, even when the transported velocities come from u*. Violating either gives a wrong shock speed. [Tested: h_m 0.425 against 0.396 at N = 400 with the second fault]

(d) **Expansion-contraction switch.** At a geometric contraction Stelling and Duinmeijer use the Bernoulli-consistent form, because strict momentum conservation raises energy head wrongly there (Zijlema, footnote 2). I reconstruct it as, along the x direction,

    Adv_x = sign(u_f) (u_f^2 - u_up^2) / (2 dx),   u_up = the upstream face velocity,
    when u_f u_up >= 0 and |u_f| > |u_up|.

Cross terms stay in the momentum form. [Likely: the paper's own equation was not read; this form conserves zeta + u^2/2g between cell values and has the same difference as (a)]

**Do not apply it everywhere.** Used on every accelerating face it put h_m in Stoker at 0.3998 against 0.3962, +0.9 %, because a rarefaction also accelerates. Restrict it to crest faces and to faces with a real area contraction, A_f(eta_U) < A_up(eta_U). [Tested for the harm; the trigger itself is Guessing and Stelling and Duinmeijer's criterion is unread]

### 2.5 Which level selects A_f and K_f [Certain for the upwind rule; Tested for the blend]

U = upstream cell by sign(u**); if u** = 0, the cell with the higher level. D = the other. d_U = eta_U - z_fmin, d_D = eta_D - z_fmin.

- **U below the invert (d_U <= 0): A_f = 0, u_f = 0.** Do not evolve momentum on such a face; this is TUFLOW's dry-face inertia lesson (N02 finding 15). Reverse flow starts when the pressure term turns the sign, and U then changes.
- **Otherwise read the blended volume-consistent area of section 3:**

      A_fl  = A(eta_U)
      A_vol = min( A_fl, V_U / L_U )          L_U = cell length along the flow = dx
      alpha = clamp(d_D / d_U, 0, 1)^4
      A_f   = alpha A_fl + (1 - alpha) A_vol
      K_f   = K( A^-1(A_f) )                  one inverse lookup on the same table

Optional second-order mass flux, on the flat branch where the stencil is wet: eta_U + 0.5 minmod(eta_U - eta_UU, eta_D - eta_U) replaces eta_U. It satisfies Herbin's conditions 8-9 and improved L1 by about 30 % on Stoker and 5 times on Thacker [Tested], at the cost of a positivity factor of 2 in Herbin's Lemma 3.1 and a CFL I only tested at 0.7.

### 2.6 Upstream below the crest, downstream above

Covered by the first bullet of 2.5: flow from the deep side goes over only if that side is above the crest. The dry side gets flow when its upstream level passes z_crest. A crest face therefore blocks until overtopped, in both directions, with no special case. [Certain, follows from the rule]

### 2.7 Free overfall and the control-level rule [Tested; my derivation, not published in anything read]

Apply to flagged crest faces and to raised faces, z_fmin above the lowest level of both adjoining cells by more than a tolerance [Guessing on the unflagged trigger]. With velocity head from the upstream face:

    E_U     = eta_U + u_up^2 / (2 g)
    eta_c   = control level: E_U - eta = A(eta) / (2 W(eta))
              rectangular crest: eta_c = z_crest + (2/3)(E_U - z_crest)
    eta_ctl = min( eta_U, max(eta_D, eta_c) )

On that face, replace eta_D by eta_ctl in the pressure term, read A_f = A(eta_ctl), and use the Bernoulli advection of 2.4(d). Steady state then gives u_f^2 / 2 = g (E_U - eta_ctl), hence with no coefficient:

- free, eta_D < eta_c: Q = (2/3)^1.5 sqrt(g) W (E_U - z_crest)^1.5 = 1.705 W H^1.5, critical depth at the crest;
- drowned, eta_D > eta_c: Q = W (eta_D - z_crest) sqrt(2 g (E_U - eta_D)), identical to N09 E4 and continuous with the free branch at r = 2/3.

Since eta_ctl <= eta_U, A_f never exceeds the upwind area, so positivity is unaffected. Cd, if wanted, multiplies A on that face (default 1). A spillway keeps its own imposed law, Q = C L H^1.5 with his C of about 2.1, as a structure face (N09 recommendation 6): 2.1 is above critical, and the rule cannot give it.

Results, steady inflow, 10 m cells, crest 2 m, Q divided by 1.705 H^1.5 at the water-level head H:

| Mode at the crest face | q = 1 | q = 4 | q = 10 m2/s |
|---|---|---|---|
| Upwind area, momentum advection | 100.6 | 11.6 | 5.3 |
| Upwind area, Bernoulli advection | 12.5 | 6.4 | 4.4 |
| Same, level drop capped at the depth over the crest (my emulation of the Rana phi limiter, N09 finding 28) | 2.63 | 2.73 | 2.90 |
| **Control-level rule** | **1.015** | **1.053** | **1.100** |

The residual in the last row is exactly the approach velocity head: E_U - z_crest came out 0.7007, 1.766, 3.2523 m against ideal 0.7007, 1.7657, 3.2524 m. Drowned: Csf 0.969, 0.881, 0.834 at r = 0.758, 0.835, 0.861 against the E4 curve 0.969, 0.881, 0.834, with r taken from the adjacent cell. The far tailwater ratio is higher (0.862, 0.910, 0.926) because the momentum form recovers pressure downstream, so the apparent modular limit against far tailwater is about 0.8. [Tested]

### 2.8 Friction, point-implicit, using K [Certain for the form; the closed solve is algebra]

Friction slope S_f = Q |Q| / K^2 with Q = u A gives du/dt = -g (A^2/K^2) |U| u, and A^2/K^2 = n^2 / R^(4/3) recovers Manning. With s* the speed from u** and the interpolated tangential velocity v_bar at the face, frozen, and beta = dt g A_f^2 / K_f^2:

    s = 2 s* / ( 1 + sqrt(1 + 4 beta s*) )
    u_f = u** s / s*

Exact for the quadratic, no iteration, stable for any dt, and it keeps the form finite as beta tends to 0. Volp's friction depth (eq. 2.20) is the theory behind K on a sub-grid: uniform friction slope across the section. Note that Volp sums four quarter domains; van Ormondt instead uses a grid-average depth for smooth tables; a single face K, as TUFLOW uses, is the v1 choice. [Likely]

### 2.9 Positivity, volume based [Certain]

    f_c = min( 1, V_c^n / ( dt sum_out Q_f ) ),   Q_f <- f_U Q_f

One sweep guarantees V >= 0 because inflows are ignored. Store the limited Q for the next Adv. On the sheet branch A_f <= V_U / dx, so Zijlema's velocity Courant condition is sufficient and the limiter stays idle; it does real work only on flat reads. [Certain, algebra; Zijlema: non-negative depth when the velocity Courant number is at most 1]

### 2.10 Time-step rule on sub-grid cells [Certain, algebra; bound checked numerically]

Linearising continuity and the pressure term gives Omega_c deta/dt = -sum s A_f u_f, du_f/dt = -(g/dx) Delta eta, so d2eta/dt2 = -Omega^-1 G eta with G the graph Laplacian of weights g A_f / dx. Gershgorin gives

    omega_c^2 = ( 2 g / (Omega_c dx) ) sum_f A_f
    dt_g      = 2 / max_c omega_c = min_c sqrt( 2 Omega_c dx / (g sum_f A_f) )

The gravity speed that follows from the tables is c^2 = g A_f / (Omega_c / dx): face area over the cell's wet width, not the mean depth. On a uniform 2D cell the bound reduces to dt = dx / sqrt(2 g h), which is precisely TUFLOW's N_c <= 1 (N02 E2), and in 1D to dx/c. Combined with advection, per cell:

    dt_c = C / ( sum_out |u_f| / dx + omega_c / 2 )

This combined form is proposed, not run. My dam-break tests used its 1D uniform limit, dt = C dx / (|u|_max + c_max), with C = 0.9 (0.7 with MUSCL mass flux); Zijlema gives the same 1D condition with C = 1.

On random sub-grid fields (Omega 3-100 % of dx^2, A_f 0-2 m x dx) the bound exceeded the true largest eigenvalue by a factor 1.9-2.0, always on the safe side, which costs a factor of 1.4 in dt on rough terrain. [Tested]

Wedge cell on slope S: c^2 = g S dx regardless of how thin the water is, 3.1 m/s at 5 % and 20 m. This is why thin films do not relax the gravity limit on flat reads. [Certain, arithmetic]

Exclude cells below a depth threshold from the search and let 2.9 protect them (decision 18c). On Thacker with table-style face beds, doing so cut steps from 47,543 to 2,930 at N = 800. [Tested] The price was an error floor (L1 7.6e-5 against 2.7e-5), partly from the velocity cap I added, so tune it.

### 2.11 Eddy viscosity

Not needed for jumps: Zijlema shows that at a discontinuity the upwind viscosity takes the value conservation requires, with no added term. [Certain] Upwind numerical viscosity near 0.5 |u| dx is about 30 m2/s at 3 m/s and 20 m, far above any physical value, wherever the limiter drops to first order. [Certain, arithmetic] Keep a Wu-type hook with N_d <= 0.3 (N02 E3), off by default, and decide on the rotated-channel and U-bend tests; BMT's experience on sharp shear layers says it may be needed at second order. [Likely]

## 3. Thin films on steep cells

**What goes wrong.** [Certain, arithmetic; Rana documents the mechanism] A plane cell at slope S filled from its lowest point holds a wedge. Mean depth d, cell dx: depth at the low edge h = sqrt(2 d S dx), wet length h/S. With d = 1 mm, S = 5 %, dx = 20 m: h = 44.7 mm over the lowest 0.89 m, 4.5 % of the cell. The downhill face reads the table at that level:

- A_f 45 times too large; Manning velocity 12.6 times too large; K about 560 times too large.
- Cell drain time V/Q falls from about 270 s to 0.5 s, so the outflow limit sets dt, not the wave speed.
- Seen the other way, at the correct discharge the cell stores about 1/2000 of the true volume at depth 1 mm, so storage vanishes and runoff arrives almost at once.

Rana states the same overestimate of wet area, the same underestimate of friction, and the consequent discharge overestimate, and says the uniform level is invalid in sheet flow. [Certain]

**The remedy, known form.** Rana (Stelling's group) drops uniform level for uniform depth in sheet flow. Its limiter type 2 takes depth = upstream volume / maximum surface area of the upstream cell. Type 3 blends from the default to type 2 by comparing the depth at the edge, based on the downstream level, with a user thin-layer thickness. A companion friction limiter is obligatory, and their sloping-terrain preset uses 0.3 m. [Certain] Stelling 2022 proposes "a simple thin layer calculation" plus a volume-correction equation; its formulas are unread. [Certain that the paper exists and what it claims; the mechanism is not known to me]

**Best form for Wadi2D** (section 2.5), my generalisation of type 2 and 3 [Tested in 1D]:

    A_vol = min( A(eta_U), V_U / L_U )
    alpha = clamp(d_D / d_U, 0, 1)^4
    A_f   = alpha A(eta_U) + (1 - alpha) A_vol
    K_f   = K( A^-1(A_f) )

**Difference from Rana's type 2.** V/L is a cross-section, not a depth spread across the whole cell, so the face table keeps the section's shape. A 5 m wide channel 1 m deep in a 40 m cell: V = 200 m3. Type 2 as worded gives depth 0.125 m over 40 m and K = 1.25/n. V/L = 5 m2 inverts on the face table to 1 m depth, K = 5/n, the true value. [Certain, arithmetic; Rana's internal implementation may differ from its wording]

**The properties asked for.**
- Mass: conserved, since the unique face flux just changes size. [Certain]
- Well-balance: exact, since A_f multiplies u, which is zero at rest, and the pressure term stays on flat levels. [Certain]
- Crest and hollows: the min() guard means the read can only reduce the area, so a depression or crest below eta_U still blocks. Without that guard a cell holding a pond would leak through a dry face. [Certain, algebra]
- Positivity: see 2.9. [Certain]
- Cost: no new table, one extra lookup per face. [Certain]

**Level, mean depth, or blend?** A blend, in area rather than level, and steered by submergence at the face, not by an absolute thickness. Read at the level when the two sides are connected (d_D near d_U), at the volume-consistent area when the downstream level is below or near the invert. The mean depth itself is the rectangular-section special case of V/L. Friction must follow the same read (Rana makes this obligatory); van Ormondt independently prefers a grid-average depth for friction, because wet-average values vary too irregularly with level. [Certain]

Rain on a plane, 100 mm/h, L = 1000 m, n = 0.03, against the analytic kinematic wave [Tested]:

| S | dx | Mode | t50 s (exact) | t90 s (exact) | V / V exact at end | Mean dt s |
|---|---|---|---|---|---|---|
| 5 % | 20 | flat level | 20 (829) | 20 (1179) | 0.013 | 0.18 |
| 5 % | 20 | **volume-consistent** | **840** (829) | **1210** (1179) | **1.016** | >= 5 (capped) |
| 5 % | 40 | flat level | 20 | 20 | 0.0066 | 0.21 |
| 5 % | 40 | **volume-consistent** | **840** | **1260** | **1.032** | >= 5 (capped) |
| 30 % | 20 | flat level | 10 (484) | 10 (689) | 0.0013 | 0.010 |
| 30 % | 20 | **volume-consistent** | **490** | **710** | **1.016** | >= 5 (capped) |

Flat tables collapse the time of concentration by about 40 times and cost 28 to 500 times in dt. This is the time-step limit on slopes with thin layers that Stelling 2022 names; the read removes it because A_f <= V/dx.

Steep channel, S = 5 %, n = 0.08, inflow peak 20 m2/s, 6 km, Fr < 1, arrival time of q > 1 m2/s, reference 1725 s from a 1 m flat run [Tested]:

| dx | S dx (m) | Flat | Volume | alpha^1 | alpha^2 | alpha^4 | alpha^8 | Rana-style, 0.3 m |
|---|---|---|---|---|---|---|---|---|
| 20 | 1 | 1140 | 1735 | 1570 | 1635 | **1695** | 1730 | 1360 |
| 40 | 2 | 615 | 1730 | 1560 | 1660 | **1720** | 1730 | 1270 |
| 80 | 4 | 355 | 1715 | 1660 | 1710 | **1715** | 1715 | 1255 |

Flow at that front is 0.54 m deep, so cell drop reached 7 times the depth with the read still within 10 s. Peak values in this test are not reported: the rising limb steepens into a kinematic shock, which a model with no advection term rings on. The smooth runs peak near 20 at 2390-2415 s, against 2390 s by the kinematic celerity.

**Why not pure volume, since it won here.** Plane tests cannot show its failure. A channel clipping the corner of a cell has a wet path much shorter than dx; V/L then under-reads the true section and would throttle flow on a mild slope, the case flat-level tables handle correctly. The blend exists for that case, and alpha near 1 protects it. Unrun, so this risk stays open. [Guessing]

## 4. Expected accuracy

**Published.** No Stoker or Thacker error table for B was found; Stelling and Duinmeijer 2003 are the likely place and were not readable. What exists: Zijlema's backward step, exact momentum flux and 5.49 cm head loss against 5.55; his dry-bed dam-break and step cases in figures only; a convergence rate of 1.6-1.7 in rms with central terms. Herbin et al.: L1 errors 3.61e-3 to 1.53e-5 in h on 32-512 cells, order about 2 in h and 1.5 in u (travelling vortex, second order), against order 0.5-0.85 at first order; their shock is captured with one intermediate cell. Casulli 2009 claims accuracy on a severe analytic wet/dry test with no threshold depth. [Certain]

**Own 1D numbers** [Tested]. L1 of h, flat bed, depth 1 m on the left, plus or minus 30 m, t = 3 s. B1 first order, B2 second-order advection, B2m plus MUSCL mass flux at CFL 0.7. A at CFL 0.45, with step counts x 2 flux passes.

| Case | N | B1 | B2 | B2m | A |
|---|---|---|---|---|---|
| Stoker, h_r = 0.1 | 100 | 0.00971 | 0.00826 | 0.00694 | 0.00545 |
| | 200 | 0.00545 | 0.00459 | 0.00331 | 0.00263 |
| | 400 | 0.00322 | 0.00264 | 0.00179 | 0.00132 |
| | 800 | 0.00187 | 0.00149 | 0.00095 | 0.00067 |
| Ritter, dry | 100 | 0.01093 | 0.00970 | 0.00900 | 0.00521 |
| | 200 | 0.00693 | 0.00592 | 0.00485 | 0.00263 |
| | 400 | 0.00414 | 0.00349 | 0.00256 | 0.00130 |
| | 800 | 0.00240 | 0.00200 | 0.00136 | 0.00065 |

Stoker at N = 400: h_m 0.3959 (B2), 0.3961 (A), exact 0.3962; shock in the same cell for both, 9.23 against 9.32 m. Observed order about 0.8 for B2 and 1.0 for A. Ritter front at 1 mm depth at N = 400: B2 15.5 m, A 15.8 m, ideal tip 18.8 m. Mass is at machine zero in every run. Steps at N = 800, Stoker: B2 243, B2m 313, A 381 x 2.

Thacker 1D, a = 1, h0 = 0.5, B = 0.5, two periods, L1 of h:

| N | B2, face bed = max of sides | B2m, face bed = mean | B2m, mean, thin cells out of the CFL | A |
|---|---|---|---|---|
| 200 | 0.00194 | 0.000230 | 0.000247 | 0.000440 |
| 400 | 0.00091 | 0.000075 | 0.000120 | 0.000156 |
| 800 | 0.00043 | 0.000027 | 0.000076 | 0.000047 |

The mean-bed columns are the relevant ones: a sub-grid table gives the true face elevation rather than the max of two samples. B then matches or beats A at coarse resolution.

**Expectation for Wadi2D.** [Likely] Shocks: correct position and depth, about 2 times A's L1 without MUSCL mass flux and about 1.4 times with it (Stoker); dry-bed fronts about 3 and 2 times (Ritter). Smooth wet/dry on a table bed: as good as A. EA 2D benchmarks: TUFLOW passes them with this class of scheme (N02 finding 28), though its internals differ. 2D and oblique behaviour: unknown until run.

## 5. What this overturns in the records

**Overturned**

1. **N05 recommendations 1-4 and 6 as the production scheme** (HLLC, MUSCL on eta/h/u, SRM face bed, Heun at CFL 0.5). HLLC is no longer the kernel; the face-bed question is moot. N05's open issue on wave speeds on partly wet faces disappears. Project decision 1 stands as worded ("second order, well-balanced") but should gain "staggered"; the open question "Roe vs HLLC" closes.
2. **N09 recommendation 4 and the idea that "the ordinary scheme handles overtopping".** True for a Godunov face, false for B: 5-100 times critical with no rule. N09 E7 (hydrostatic reconstruction at a crest, marked [Guessing]) is replaced by 2.7, as is the weir blending in recommendation 5 and open issue 11. Coefficient-free control replaces TUFLOW's weir law; N09's crest-length rule E8, verification list and spillway recommendation 6 stand.
3. **The attribution in decision 18(a) and CLAUDE.md to Volp 2013 for a sloped sub-grid free surface.** Volp 2013 keeps a uniform level in every cell; it is a friction paper. The correct references are Stelling 2022 and the Rana limiters.
4. **Decision 18(a), the rule dx <= h/S, as a hard cap.** It is a limit of flat-level reads, not of the scheme: in my 1D channel the read held arrival within 10 s with S dx at 7 times the depth. Keep it as a mesher guide until a 2D test confirms this. [Tested in 1D only]
5. **Decision 18(c), Kurganov-Petrova desingularisation.** Not applicable: velocity is a primary variable here and is not recovered from hu/h. The depth threshold on the CFL search stays.
6. **The illustrative time steps in decision 18(a)** use dx / (|u| + sqrt(g h)) with a mean depth. On sub-grid cells replace with 2.10.
7. **W1 kernel benchmark as the stack evidence.** `benchmarks/swe_kernel_bench` measures HLLC-MUSCL kernels only (about 10 GCUPS wet). Throughput for the chosen scheme is unmeasured; the staggered kernel needs its own run, including table lookups, which that benchmark does not have.

**Extended, not overturned**

8. Decision 3: store volume, and difference levels through per-face datum offsets (2.1).
9. Decision 2: the crest length factor multiplies W and A on the crest face; add a control level per crest face.
10. N02 recommendation 4 and open issue 1 (how tables enter the pressure term): answered by section 2. TUFLOW's own method remains unpublished.
11. N02 open issue 3: N_c <= 1 with sqrt(2 g h) is exactly the 2D forward-backward gravity limit (2.10). Whether RK4 justifies TUFLOW's other printed value remains open.
12. The package stub `wadi2d/solver/__init__.py` already says staggered; the records now agree with it.

**Note:** Stelling 2012's quadtree staggered form and N02's quadtree findings keep the version-2 door open. Tiles, halos and the 32 x 32 layout are unaffected, with a 2-cell halo for u in the corrector.

## 6. Findings with sources

1. **The subgrid C-grid form.** Volume in continuity, velocity at faces, level uniform per cell, pressure term g (zeta_R - zeta_L)/dx, friction via a friction depth under uniform friction slope, momentum-conservative advection after Stelling and Duinmeijer, Kramer and Stelling, Kernkamp et al. Eq. 2.7-2.34. [Certain] https://www.vliz.be/imisdocs/publications/ocrd/300563.pdf
2. **Stelling and Duinmeijer use momentum-consistent approximations in expansions and Bernoulli-consistent ones in contractions, on a staggered grid, for hydraulic jumps, bores and road-bank obstacles.** [Certain, abstract] https://doi.org/10.1002/fld.537 ; abstract via https://api.openalex.org/works/doi:10.1002/fld.537
3. **Discrete jump relations hold only with depth-averaged velocity upwinded by the mass flux; alternatives give odd-even oscillations; upwind face depth preserves non-negative depth at velocity Courant at most 1; centred depth is formally more accurate and less robust.** Eq. 19-27, 38, 45-46, Tables 1-2. [Certain] https://swash.sourceforge.io/online_doc/rh.pdf
4. **MUSCL plus Heun staggered scheme: positivity under CFL (Lemma 3.1, with a factor 2), lake at rest (Lemma 3.2, requires centred depth in the bathymetry term), Lax-Wendroff consistency; Euler plus MUSCL loses convergence.** [Certain] https://arxiv.org/abs/2111.09726
5. **Explicit staggered recipe in production: leapfrog, surface elevation taken upwind with bed by min of depths, non-negative under dt S |u| <= A, wave CFL at most 1.** Chapter 6. [Certain] https://swash.sourceforge.io/download/zip/swashtech.pdf
6. **Uniform level fails on slopes: wet area overestimated, friction underestimated, discharge overestimated; limiters based on uniform depth; types 1-3; friction limiter obligatory with the area limiter; gradient limiter phi = min[1, H / d(eta)].** [Certain] https://docs.ranawaterintelligence.com/h_simulation_settings.html , https://docs.ranawaterintelligence.com/h_surfaceflow.html
7. **Sloping preset: type 3, thin layer 0.3 m, friction limiter on, friction shallow-water correction 3.** [Certain] https://docs.ranawaterintelligence.com/e_2d_slope_tutorial.html
8. **Stelling 2022: subgrid methods can be unstable and inaccurate on steep runoff slopes; a volume correction equation plus a thin-layer calculation are claimed to make them robust without Newton iteration of big systems. Full text unread.** [Certain for the claims] https://doi.org/10.1016/j.compfluid.2022.105645 ; abstract via https://api.core.ac.uk/v3/outputs/534008201
9. **SFINCS sub-grid: volume continuity, friction on grid-average depth because wet-average values vary too irregularly, a face level from the maximum of adjacent levels; the authors note the constant-level assumption fails on steep gradients.** Eq. 12-16, 23. [Certain] https://gmd.copernicus.org/articles/18/843/2025/gmd-18-843-2025.html
10. **Porosity models report three orders of magnitude speed-up but sensitivity of edge porosities to resolution.** [Certain, abstracts] https://doi.org/10.1016/j.apm.2015.12.012 , https://doi.org/10.1016/j.jhydrol.2016.08.025
11. **Casulli's sub-grid wetting and drying needs no threshold depth and yields no negative depths.** [Certain, abstract] https://doi.org/10.1002/fld.1896
12. **Stelling 2012's four components: sub-grid, friction by a divided-channel method, staggered finite volume for rapidly varying flow, quadtrees.** [Certain, abstract] https://doi.org/10.1680/wama.12.00018

## 7. What remains unresolved

1. **All of it in 2D.** Cross-advection (2.4), oblique jumps, EA Test 6A, rotated channel, U-bend. First prototype runs, and the tests that could reverse the verdict.
2. Stelling 2022's VCE and TLC: unread. If reachable it may replace or sharpen section 3, and it may address item 3 below. Ask for the PDF if he has access; it is CC-BY.
3. The pressure term stays on flat levels for well-balance, so dzeta/dV is strongly amplified in thin cells (22 times at 1 mm, 5 %, 20 m). Harmless in friction-dominated 1D; unproven with inertia.
4. The corner-clipping channel (end of section 3): whether alpha protects it. Needs a 2D test on real DEM cells.
5. Exponent p = 4 rests on one 1D test.
6. The trigger for the control rule on unflagged raised faces, and for the Bernoulli branch. Stelling and Duinmeijer's own criterion is unread.
7. Discontinuous steps downward with deep flow: the full level drop drives the face; the rule is not applied there because the bed is not raised. Untested.
8. Throughput of the staggered kernel on the RTX 5080, with table lookups in the loop.
9. A second-order mass flux on the sheet branch; the CFL limit with MUSCL mass flux, tested only at 0.7.
10. Momentum source of injected hydrographs (N09 open issue 1): B changes where it goes (u_f, Q in Adv) but not whether it is needed.

## 8. Sources

Primary read in full:
1. Volp, van Prooijen, Stelling 2013, WRR 49, as Chapter 2 of Volp 2017 thesis. https://www.vliz.be/imisdocs/publications/ocrd/300563.pdf ; DOI 10.1002/wrcr.20324
2. Zijlema, The role of the Rankine-Hugoniot relations in staggered finite difference schemes for the shallow water equations (Computers and Fluids, preprint August 2019). https://swash.sourceforge.io/online_doc/rh.pdf
3. Herbin, Latche, Nasseri, Therme 2021. https://arxiv.org/abs/2111.09726
4. SWASH scientific and technical documentation, version 12.01. https://swash.sourceforge.io/download/zip/swashtech.pdf
5. Rana (3Di) simulation settings. https://docs.ranawaterintelligence.com/h_simulation_settings.html
6. Rana 2D surface flow, sub-grid, sloping-terrain tutorial. https://docs.ranawaterintelligence.com/h_surfaceflow.html , https://docs.ranawaterintelligence.com/h_subgrid.html , https://docs.ranawaterintelligence.com/e_2d_slope_tutorial.html
7. van Ormondt, Leijnse, de Goede, Nederhoff, van Dongeren 2025, GMD 18. https://gmd.copernicus.org/articles/18/843/2025/gmd-18-843-2025.html

Abstract or highlights only:
8. Stelling and Duinmeijer 2003, IJNMF 43, 1329-1354. https://doi.org/10.1002/fld.537
9. Stelling 2022, Computers and Fluids 247, 105645. https://doi.org/10.1016/j.compfluid.2022.105645
10. Casulli 2009, IJNMF 60. https://doi.org/10.1002/fld.1896
11. Stelling 2012, Water Management 165. https://doi.org/10.1680/wama.12.00018
12. Oezgen, Zhao, Liang, Hinkelmann 2016. https://doi.org/10.1016/j.jhydrol.2016.08.025 ; 2015 https://doi.org/10.1016/j.apm.2015.12.012

Tried and not reachable:
13. Kernkamp et al. 2011, Ocean Dynamics 61. https://doi.org/10.1007/s10236-011-0423-6
14. Sanders and Schubert 2019, AWR 126. https://doi.org/10.1016/j.advwatres.2019.02.007
15. Guinot, Delenne, Rousseau, Boutron 2017, dual integral and critical assessment. https://doi.org/10.1016/j.advwatres.2017.02.009 , https://doi.org/10.1016/j.advwatres.2017.09.002

Prior notes: N02, N03, N05, N09 in this folder.
