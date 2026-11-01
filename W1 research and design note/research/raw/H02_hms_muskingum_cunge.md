# H02 HEC-HMS Muskingum-Cunge routing: algorithm, section shapes and parameter selection

Date: 2026-10-29

## Scope

What HEC-HMS (4.12, the Block 2 version) does when a reach is routed with Muskingum-Cunge: the equations, the per-step
recalculation of the parameters, how it chooses the time and distance steps, what the index flow / index celerity is for, the six
cross-section shapes and the eight-point section with three Manning n values, the limits of applicability, what the `.basin` file
stores per reach, and the discrete algorithm in enough detail to reimplement it and compare the result with HMS output. The Ponce
papers HMS cites (1978 variable parameters, 1982 accuracy criteria, 1986 catchment dynamics, 1994 revisited) are read for the parts
HMS leaves unstated. Todini (2007) is read for the mass-conservation fix Wadi2D will need. Sources: 18 primary (17 web, one local
HMS model plus a survey of 138 local `.basin` files). Not covered: the other HMS routing methods, kinematic-wave subbasins, HEC-1
details beyond the HMS comparison page.

Tags: [Certain] read in a primary source (quoted or seen on a rendered page); [Likely] strong inference or secondary statement;
[Guessing] filling a gap.

Caveat on quotes: the HMS Technical Reference Manual of March 2000 (CPD-74B) was read from the PDF; its equation pages were rendered
to images and read visually because text extraction garbles the equations. The current TRM (confluence) carries the same equations
renumbered (Eqs 1-16).

## Findings

1. **HMS Muskingum-Cunge is the diffusion-wave approximation**: continuity with lateral inflow plus the momentum simplification
   `S_f = S_o - dy/dx`, combined into the convective-diffusion equation with celerity `c = dQ/dA` and diffusivity
   `mu = Q/(2 B S_o)`. [Certain] "Combining these and using a linear approximation yields the convective diffusion equation (Miller
   and Cunge, 1975)". https://www.hec.usace.army.mil/software/hec-hms/documentation/HEC-HMS_Technical%20Reference%20Manual_(CPD-74B).pdf
   (p. 91) and https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/channel-flow/muskingum-cunge-model (Eqs 1-5).

2. **The routing equation has four coefficients, the fourth for lateral inflow**:
   `O_t = C1 I_(t-1) + C2 I_t + C3 O_(t-1) + C4 (q_L dx)` with `K = dx/c` and `X = 1/2 (1 - Q/(B S_o c dx))`. [Certain] "The parameters
   K and X are (Cunge, 1969; Ponce, 1978)" (TRM 2000 Eqs 8-23 to 8-29, same as current TRM Eqs 7-13). Same URLs as finding 1.

3. **The parameters are recomputed at every time and distance step** ("variable parameter"), but HMS names only Ponce (1986) for
   the algorithm and nowhere states which grid points it averages or whether it iterates. [Certain for the recomputation]
   "HEC-HMS recomputes them at each time and distance step, dt and dx, using the algorithm proposed by Ponce (1986)" (TRM 2000,
   p. 92). The current TRM: "the routing parameters are recalculated every time step based upon channel properties and the flow
   depth". Ponce (1986) itself gives the four-point stencil and the C-D coefficients but no averaging or iteration rule [Certain,
   read]. https://ponce.sdsu.edu/diffusion_wave_modeling_of_catchment_dynamics.html

4. **Two undocumented iteration caps are written for every Muskingum-Cunge reach in HMS 4.12 files**: `Maximum Depth Iterations: 20`
   and `Maximum Route Step Iterations: 30` (7,230 reaches in 138 local `.basin` files, all with these two keys; absent from the
   user's manual, the TRM and the 4.3 release notes). [Certain that they exist] [Likely] that the first caps the normal-depth solve
   (discharge to depth) and the second the four-point iteration on the unknown outflow, as in Ponce and Yevjevich (1978) and
   TP-135. Local file `D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\HEC_HMS_Block_02\Basin_1.basin`.

5. **HMS finds the depth for each discharge exactly, then area, top width and wave speed at that depth; HEC-1 interpolated 20-depth
   tables.** [Certain] "HEC-HMS guarantees that the area, top width, and wave speed are computed exactly for each discharge value."
   HMS "uses Manning's formula for velocity". https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/4.13/hec-hms-and-hec-1-differences/muskingum-cunge-routing

6. **Time step (2000 rule)**: `dt` is the minimum of the control-specification step, the travel time through the reach, and 1/20 of
   the time of rise of the steepest inflow, rounded to a multiple or divisor of the user step. [Certain] "or 1/20th the time to rise
   of the peak inflow with the steepest rising limb, rounded to the nearest multiple or divisor of the user time step" (TRM 2000,
   p. 92). Same URL as finding 1.

7. **Time step (current rule, since the 4.3 restructuring)**: `dt` is "the minimum of either the user-specified time step or the
   travel time through the reach"; the 1/20-of-rise term is gone because the inflow hydrograph is no longer known before the reach
   is computed. [Certain for the current rule; Likely for the reason] Current TRM: "the minimum of either the user-specified time
   step or the travel time through the reach". Release notes 4.3: "the upstream hydrograph is no longer available for each reach".
   https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/channel-flow/muskingum-cunge-model and
   https://www.hec.usace.army.mil/software/hec-hms/documentation/HEC-HMS_Release_Notes_4.3.pdf

8. **Distance step**: `dx = c dt`, constrained by `dx < 1/2 (c dt + Q_o/(B S_o c))` with the reference flow
   `Q_o = Q_B + 1/2 (Q_peak - Q_B)`. In the current HMS the constraint is reported as a "reference" `dx_ref` (from EM 1110-2-1417) and a
   note is issued when it differs from `dx`. [Certain] "The value is constrained so that:" Eq 8-31 (TRM 2000, p. 92); current TRM Eqs
   14-16. The constraint is exactly Ponce and Theurer's criterion with kappa = 2, i.e. Courant + cell-Reynolds >= 2 (see section
   Equations). Same URLs as findings 1 and 7.

9. **Index celerity or index flow is mandatory since 4.3**; it exists only to size `dx` (Courant condition) and `dt`; with both `dx`
   and `dt` specified it is not needed. [Certain] "The user must now manually enter either an index flow or an index wave celerity.
   If the index flow is entered, the wave celerity is automatically calculated". Release notes 4.3, p. 12.
   https://www.hec.usace.army.mil/software/hec-hms/documentation/HEC-HMS_Release_Notes_4.3.pdf

10. **Reference value guidance**: mid-way between base flow and peak; a peak-based value accelerates the wave numerically, a low value
    slows it (Ponce 1983); the HMS tutorials use an index celerity of 5 ft/s. [Certain] "tend to numerically accelerate the flood
    wave more than would occur in nature". https://www.hec.usace.army.mil/confluence/hmsdocs/hmsguides/applying-reach-routing-methods-within-hec-hms/applying-the-muskingum-cunge-routing-method
    The Block 2 model carries `Index Celerity: 1.524` (m/s) on all eight reaches, which is 5 ft/s converted, i.e. the tutorial
    default, not a value derived from the sections. [Certain, local file + arithmetic]

11. **Six cross-section shapes**: circle (diameter), eight point (paired station-elevation data), rectangle (bottom width), tabular
    (elevation-discharge, elevation-area, elevation-width functions), trapezoid (bottom width, side slope), triangle (side slope).
    Side slope is horizontal per one vertical. Shapes must contain every simulated depth. An optional invert elevation turns depth
    into stage. [Certain] "zero, one, or three Manning's n roughness coefficients are required" and "A separate Manning's n value is
    entered for each overbank." https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/4.8/reach-elements/selecting-a-reach-routing-method
    (also the "latest" page, same text).

12. **Eight-point layout**: points 3 and 6 are the left and right banks, 4 and 5 are in the channel, 1-2 the left overbank, 7-8 the
    right overbank; three n values (left overbank, main channel, right overbank). [Certain] "Points labeled 3 and 6 represent the
    left and right banks of the channel at the representative cross section." (TRM 2000, p. 93, Fig. 8-5). The data are entered in
    the Paired Data Manager as a "Cross Sections" curve, distilled to eight points from a survey. [Certain]
    https://www.hec.usace.army.mil/confluence/hmsdocs/hmsguides/applying-reach-routing-methods-within-hec-hms/creating-cross-section-paired-data-curves
    Negative elevations are allowed since 4.3 with a warning. [Certain] Release notes 4.3, p. 12.

13. **Tabular shape (added in 4.3)** takes discharge, area and top width as functions of depth and needs no n; the conceptual and
    8-point shapes compute the same three properties from Manning and geometry. [Certain] "The underlying equations require several
    properties as a function of flow depth: discharge, flow area, and top width." Release notes 4.3, p. 5.

14. **Applicability**: no backwater, no downstream condition (computations run upstream to downstream); MC can route slow-rising waves
    on flat slopes but not rapidly rising ones; error below 5% when `T S_o (g/d_o)^(1/2) >= 30` (Ponce 1978); the kinematic-wave model
    needs `T S_o u_o/d_o >= 171` and slope above 0.002. [Certain] "it should not be used for rapidly-rising hydrographs in the same
    channels, because it omits acceleration terms" (TRM 2000, p. 95, Eqs 8-33, 8-34, Table 8-3). The HMS guide adds: the full
    unsteady equations are needed for slopes under about 2 ft/mile or extensive backwater; a slope above 0.0006 gives good results.
    [Certain] Guide URL as in finding 10. TP-135: the method "diverges from the full unsteady flow solution for very rapidly rising
    hydrographs in flat channels with slope less than 0.0002 (Brunner, 1989)". [Certain]
    https://www.hec.usace.army.mil/Publications/TechnicalPapers/TP-135.pdf

15. **Ponce and Yevjevich (1978)**: coefficients in Courant number `C = c dt/dx` and cell Reynolds number `D = q/(S_o c dx)`; a two-point
    average of q and c is inaccurate (85% mass conservation, smaller peak, slower travel); three-point and iterative four-point are
    "sufficiently accurate"; the four-point iteration starts from the three-point result. [Certain] "a two-point approach is shown to
    be inaccurate in the calculation of peak discharge and travel time".
    https://ponce.sdsu.edu/muskingum_cunge_method_with_variable_parameters.html

16. **Ponce and Theurer (1982) accuracy criterion**: accuracy depends only on the coefficient of the new inflow, `C2 >= zeta`, recommended
    `zeta = 0.33` giving `kappa = 2`; hence `dx <= (1/kappa)(c dt + q_o/(S_o c))`; `dt <= T_r/n` with `n >= 5`; negative values of the other
    two coefficients do not harm accuracy; no theoretical lower limit on dx or dt. [Certain] "A value of zeta = 0.33 is recommended,
    from which kappa = 2." https://ponce.sdsu.edu/accuracy_criteria_in_diffusion_routing.html

17. **Variable-parameter MC does not conserve mass**: Ponce and Chaganti (1994) report worst-case losses after 500 miles of up to
    4.6% (three-point) and 2.4% (modified four-point) at a 20:1 peak-to-base ratio; the constant-parameter method conserves mass
    exactly. [Certain] "ranging from less than 2.5% for MVPMC4 to less than 5% for VPMC3".
    https://ponce.sdsu.edu/variable_parameter_muskingum_cunge_method_revisited.html Todini (2007) cites 8-10% at slopes of order 1e-4.
    [Certain] "reaching values of the order of 8 to 10% at slopes of the order of 10-4 (Tang et al. 1999)".
    https://hess.copernicus.org/articles/11/1645/2007/hess-11-1645-2007.pdf

18. **Todini (2007) explains and fixes the loss**: the Muskingum derivation assumes constant K and X within a step; evaluating each
    product `[K X]` and `[K(1-X)]` at its own time level restores mass balance, and a factor `beta = c A/Q` applied to C and D restores
    the steady-state storage; the method is iterated twice and yields the average stage in the reach. [Certain] "the loss of mass
    balance in MC is caused by the use of time variant parameters which violate the implicit assumption". Same URL as finding 17.

19. **Lateral inflow and order of accuracy (Wang et al. 2018, arXiv 1802.04429)**: with constant parameters the scheme is second-order
    for any grid, third-order when `Cr^2 + 3/Pe^2 = 1` (`Pe = c dx/(2 mu)`); the lateral-inflow coefficient is `C4 = 1 - C3`; the
    second-order average lateral inflow is the mean of the two time levels. [Certain] "The CPMC method is second-order accurate
    without restrictions on temporal and spatial discretizations". https://arxiv.org/abs/1802.04429 (PDF p. 6-8). Their sinusoidal
    test (L = 10 km, T = 10,000 s, 2 m rectangular channel, slope 0.01, n = 0.035) has an analytical solution usable as a unit test.

20. **HEC's own 1991 network routing (TP-135)** used the four-point iteration with a linear-projection first guess, power-function
    rating curves, a reference discharge of two thirds of the peak above base, and routed main channel and overbank separately; this
    is not what HMS does but it is the HEC pedigree of the method. [Certain] "The reference discharge is generally two thirds of the
    peak flow above base flow". https://www.hec.usace.army.mil/Publications/TechnicalPapers/TP-135.pdf (p. 15).

21. **NRCS TR-20 rules for comparison**: the routing step is the inflow-hydrograph step, interpolated so that at least ten intervals
    reach the peak; the reach is subdivided when `dx` is less than 2/3 of the reach length; celerity `c = m V` with `m = 5/3` for a wide
    Manning channel and a weighted m from the rating table in compound sections. [Certain] "if there are less than ten time intervals
    to the peak of the inflow hydrograph, the hydrograph is interpolated". https://www.hydrocad.net/pdf/Merkel-MC-paper.pdf

22. **What the Block 2 `.basin` stores per Muskingum-Cunge reach** (HMS 4.12, `Unit System: Metric`): `Route: Muskingum Cunge`,
    `Channel: Trapezoid`, `Length` (m), `Energy Slope` (m/m), `Mannings n`, `Bottom Width` (m), `Side Slope` (H per 1 V),
    `Initial Variable: Combined Inflow`, `Space-Time Method: Automatic DX and DT`, `Index Parameter Type: Index Celerity`,
    `Index Celerity` (m/s), `Number Subreaches: 1`, `Maximum Depth Iterations: 20`, `Maximum Route Step Iterations: 30`,
    `Channel Loss: None`, plus `Downstream`, canvas coordinates and modification stamps. [Certain] Local file as in finding 4.
    The eight reaches: lengths 660-26,009 m, energy slopes 0.0093-0.0152, n = 0.100, bottom widths 50-100 m, side slopes 0.7-5.
    No local file (138 scanned) uses Index Flow, a non-trapezoid shape, channel loss or a specified DX, so the keys for those
    options are not observed. [Certain]

## Equations and algorithms

Notation: `I` inflow, `O` outflow, `t` the current step, `t-1` the previous; `dt` routing step, `dx` subreach length; `Q` discharge,
`A` area, `B` top width, `P` wetted perimeter, `R = A/P`, `y` depth, `V = Q/A`; `S_o` the slope entered as "Energy Slope" (HMS uses it
as the friction slope for the depth solve); `c` wave celerity; `q = Q/B` unit-width discharge; `q_L` lateral inflow per unit length.

### E1. HMS Muskingum-Cunge equations (TRM 2000 Eqs 8-18 to 8-32; current TRM Eqs 1-16) [Certain]

```
Continuity:            dA/dt + dQ/dx = q_L
Momentum (diffusion):  S_f = S_o - dy/dx
Combined:              dQ/dt + c dQ/dx = mu d2Q/dx2 + c q_L
Celerity, diffusivity: c = dQ/dA              mu = Q / (2 B S_o)

Routing:   O_t = C1 I_(t-1) + C2 I_t + C3 O_(t-1) + C4 (q_L dx)

           C1 = (dt/K + 2X)        / (dt/K + 2(1-X))     coefficient of the OLD inflow
           C2 = (dt/K - 2X)        / (dt/K + 2(1-X))     coefficient of the NEW inflow
           C3 = (2(1-X) - dt/K)    / (dt/K + 2(1-X))     coefficient of the OLD outflow
           C4 = 2 (dt/K)           / (dt/K + 2(1-X))     coefficient of the lateral inflow q_L dx

           K = dx / c              X = 1/2 (1 - Q / (B S_o c dx))

Steps:     dx = c dt                                                   (auto DX, auto DT)
           dx < 1/2 ( c dt + Q_o / (B S_o c) )                          (constraint; "dx_ref" in current HMS)
           Q_o = Q_B + 1/2 (Q_peak - Q_B)                               (reference flow, from the inflow hydrograph)
           dt = min(user dt, travel time L/c [, time of rise / 20 in the 2000 rule]), rounded to a multiple or divisor of user dt
```

C1 + C2 + C3 = 1. Note the numbering: HMS (and Ponce 1978) call the old-inflow coefficient C1; Ponce's "explained" page and Ponce
(1986) call the new-inflow coefficient C0 and shift the others. Ponce and Theurer's accuracy coefficient "C2" is the new-inflow
coefficient, i.e. HMS C2.

### E2. The same in Courant and cell-Reynolds form (Ponce and Yevjevich 1978; Ponce 1986) [Certain]

```
C = c dt / dx                    Courant number (ratio of celerities)
D = q / (S_o c dx) = Q / (B S_o c dx) = 2 mu / (c dx)      cell Reynolds number (physical / numerical diffusivity)
K = dt / C                       X = (1 - D) / 2

C1 = (1 + C - D) / (1 + C + D)   old inflow
C2 = (C + D - 1) / (1 + C + D)   new inflow
C3 = (1 - C + D) / (1 + C + D)   old outflow
C4 = 2 C       / (1 + C + D)     lateral inflow (Ponce 1986 "C3"; Wang et al. C4 = 1 - C3)
```

HMS's dx constraint divided by dx reads `C + D > 2`, which is identical to Ponce and Theurer's `C2 >= 1/3` (`kappa = 2`):
`(C + D - 1)/(C + D + 1) >= 1/3  <=>  C + D >= 2`. Their weaker "modified Koussis" bound is `C2 >= 0 <=> C + D >= 1`; `C2 >= 0.5`
gives `C + D >= 3`. Ponce and Theurer: `dt <= T_r / n`, `n >= 5` (T_r the time of rise). [Certain]

Third-order accuracy of the constant-parameter scheme (Wang et al. 2018 Eqs 7-10, after Bajracharya and Barry 1997, Szel and
Gaspar 2000) [Certain, read on the rendered page]:

```
dx = sqrt( c^2 dt^2 + 12 mu^2 / c^2 )     or     Cr^2 + 3 / Pe^2 = 1,  Pe = c dx / (2 mu),  Cr = c dt / dx
```

In Ponce's variables `1/Pe = D`, so the third-order grid is `C^2 + 3 D^2 = 1` (my algebra, [Certain]); it tends to C = 1 when the
diffusion is small, which is Ponce's "Courant number equal to or slightly greater than one" advice.

### E3. Section hydraulics HMS needs at each step [Certain for the inputs; Likely for the derivative form]

For the depth solve HMS uses Manning with the entered slope: `Q = (1/n) A(y) R(y)^(2/3) S_o^(1/2)`; depth is found iteratively
(the `Maximum Depth Iterations` cap, [Likely]). Then `A`, `B` and `c = dQ/dA` at that depth. The analytic derivative for a prismatic
shape (standard open-channel result; HMS does not state whether it differentiates analytically or numerically):

```
c = dQ/dA = (Q/A) [ 5/3 - (2/3) (A/P) (dP/dA) ],    dP/dA = (dP/dy) / (dA/dy) = (dP/dy) / B

Trapezoid (b, z): A = (b + z y) y;  P = b + 2 y sqrt(1 + z^2);  B = b + 2 z y;  dP/dy = 2 sqrt(1 + z^2)
Rectangle: z = 0.   Triangle: b = 0.   Wide channel limit: c = (5/3) V.
Circle (diameter Dc), theta = 2 arccos(1 - 2y/Dc):  A = Dc^2/8 (theta - sin theta);  P = Dc theta / 2;
        B = Dc sin(theta/2);  dP/dA = 4 / (Dc (1 - cos theta))
Eight point: three subsections (left overbank n_L, channel n_C, right overbank n_R, split at points 3 and 6);
        Q(y) = S_o^(1/2) sum_i (1/n_i) A_i R_i^(2/3)  [Likely: the HEC subdivided-conveyance convention; HMS does not state it];
        c = (dQ/dy) / (dA/dy) = (dQ/dy) / B, evaluated numerically.
Tabular: Q(y), A(y), B(y) given; c = (dQ/dy) / (dA/dy).
```

### E4. The HMS discrete algorithm, step by step, as far as the sources fix it

Items marked [Likely] are the gaps HMS does not document; they are the knobs to tune in the replication test.

```
Per reach, before the time loop
 A1  Read L, S_o (Energy Slope), n (or n_L, n_C, n_R), shape and dimensions, index (c_idx, or Q_idx), user step dt_u,
     space-time option, N_sub (used only when DX is specified), initial condition (inflow = outflow, or a discharge).
 A2  If Index Flow: y_idx from Manning at S_o; c_idx = dQ/dA(y_idx).                                  [Certain that this happens;
                                                                                                        Likely that S_o is the slope used]
 A3  dt = min(dt_u, L / c_idx)  [2000 rule also: T_rise/20];  round to a multiple or divisor of dt_u.  [Certain]
 A4  dx = c_idx dt;  N = L / dx rounded to an integer and dx = L / N                                  [Likely: rounding rule unstated]
     dx_ref = 1/2 (c_idx dt + Q_o / (B S_o c_idx)) with Q_o from the index; note issued if dx != dx_ref.  [Certain]
     Specified DX: N = N_sub, dx = L / N_sub, dt auto (longest stable) or specified as dt_u / N_t.       [Certain]

Time loop, for each dt and each subreach j = 1..N (upstream to downstream)
 B1  Known: I_(t-1) = Q_(j-1)^(t-1), I_t = Q_(j-1)^t, O_(t-1) = Q_j^(t-1). q_L = 0 for an HMS reach (no lateral inflow element).
 B2  Reference discharge for the cell: three-point Q_ref = (I_(t-1) + I_t + O_(t-1)) / 3, or four-point
     Q_ref = (I_(t-1) + I_t + O_(t-1) + O_t) / 4 iterated on O_t from the three-point start                [Likely: Ponce 1978 / TP-135;
                                                                                                        'Maximum Route Step Iterations' = cap]
 B3  y_ref from Manning(Q_ref, S_o, n, shape); A, B, c = dQ/dA at y_ref.                              [Certain for 'depth then
                                                                                                        area, top width, wave speed']
 B4  K = dx / c;  X = 1/2 (1 - Q_ref / (B S_o c dx));  C1..C4 from E1;  O_t = C1 I_(t-1) + C2 I_t + C3 O_(t-1).   [Certain]
 B5  If four-point: repeat B2-B4 with the new O_t until |dO| < tol or the cap; tol unstated.             [Likely]
 B6  Store Q_j^t = O_t. Stage = invert + y (if an invert elevation is given).                           [Certain]
Output: the outflow of subreach N at every dt, resampled to the control interval when dt is a divisor.    [Certain, from A3]
```

### E5. Todini's (2007) mass-conservative, storage-consistent variant (MCT) [Certain, Eqs 29-56]

```
First guess          O^_(t+dt) = O_t + (I_(t+dt) - I_t)
Reference discharge  Q_t = (I_t + O_t)/2;  Q_(t+dt) = (I_(t+dt) + O^_(t+dt))/2
Depths               y_t, y_(t+dt) from Manning (Newton-Raphson) at Q_t, Q_(t+dt); celerities c_t, c_(t+dt) at those depths
Correction           beta = c A / Q (= c/V);   C* = C / beta;   D* = D / beta   (each at its own time level)
Coefficients         C1 = (-1 + C*_(t+dt) + D*_(t+dt)) / (1 + C*_(t+dt) + D*_(t+dt))                         new inflow
                     C2 = ((1 + C*_t - D*_t)   / (1 + C*_(t+dt) + D*_(t+dt))) * (C*_(t+dt) / C*_t)            old inflow
                     C3 = ((1 - C*_t + D*_t)   / (1 + C*_(t+dt) + D*_(t+dt))) * (C*_(t+dt) / C*_t)            old outflow
Outflow              O_(t+dt) = C1 I_(t+dt) + C2 I_t + C3 O_t;  repeat the t+dt quantities twice to remove the first guess
Storage and stage    S_(t+dt) = ((1 - D*)/(2 C*)) dt I_(t+dt) + ((1 + D*)/(2 C*)) dt O_(t+dt);  A_mean = S/dx;  y_mean = y(A_mean)
```

The point of beta: the Muskingum `K` is the travel time of the storage (`dx/V`), not of the wave (`dx/c`); using `dx/c` understates
the stored volume by the factor `beta` (5/3 for a wide Manning channel). The scheme is always mass conservative in Todini's tests
and the storage from the continuity and from the Muskingum relation coincide.

### E6. Regime checks (TRM 2000 Eqs 8-33, 8-34; Ponce 1978) [Certain]

```
Kinematic wave error < 5%:    T S_o u_o / d_o >= 171
Muskingum-Cunge error < 5%:   T S_o (g / d_o)^(1/2) >= 30
```
`T` hydrograph duration, `u_o`, `d_o` reference mean velocity and depth (average conditions of the inflow hydrograph). HMS Table 8-3:
slope > 0.002 with the first criterion met, any model; 0.002-0.0004, Muskingum-Cunge, modified Puls or Muskingum; below 0.0004 and the
second criterion met, Muskingum-Cunge; below 0.0004 and not met, none of the HMS methods.

## Numbers

| Value | Context | Source |
|---|---|---|
| 1/20 of the time of rise | third term in the 2000 dt rule, dropped in the current rule | TRM 2000 p. 92; current TRM |
| dx < 1/2 (c dt + Q_o/(B S_o c)) | HMS dx constraint = C + D > 2 | TRM 2000 Eq 8-31 |
| Q_o = Q_B + 1/2 (Q_peak - Q_B) | HMS reference flow | TRM 2000 Eq 8-32 |
| 2/3 of the peak above base | reference discharge in HEC's 1991 DNCFR | TP-135 p. 15 |
| zeta = 0.33, kappa = 2 | Ponce-Theurer accuracy criterion on the new-inflow coefficient | Ponce and Theurer 1982 |
| dt <= T_r/n, n >= 5 | time-step criterion | Ponce and Theurer 1982 |
| >= 10 intervals to the peak | TR-20 interpolation rule | Merkel (NRCS) |
| dx < 2/3 L -> subdivide | TR-20 subreach rule | Merkel (NRCS) |
| 5 ft/s = 1.524 m/s | HMS tutorial index celerity; the Block 2 value on all 8 reaches | HMS guide; local `.basin` |
| 85% | mass conservation of the two-point scheme (rejected) | Ponce and Yevjevich 1978 |
| 95.4-97.4% / 96.5-98.4% | mass conservation after 500 mi, q_p/q_b = 20, conventional / modified 3- and 4-point | Ponce and Chaganti 1994 |
| 8-10% | mass loss at slopes ~1e-4 (Tang et al. 1999) | Todini 2007 |
| 0.002 | minimum slope for the kinematic-wave simplification | TRM 2000 p. 95 |
| 0.0006; 2 ft/mi (0.00038) | "large enough for good results"; below it use full unsteady equations | HMS guide |
| 0.0002 | slope below which MC diverges for very rapidly rising waves | TP-135 (Brunner 1989) |
| 171; 30 | kinematic and diffusion criteria (dimensionless) | TRM 2000 Eqs 8-33/34 |
| 20 depths | HEC-1 property table replaced by exact solve in HMS | UM 4.13 differences |
| 20; 30 | `Maximum Depth Iterations`; `Maximum Route Step Iterations` (HMS 4.12 defaults, undocumented) | local `.basin` |
| 5 min, 48 h | Block 2 control interval and run length | local `Control_1.control` |
| 660-26,009 m; 0.0093-0.0152; n = 0.100 | Block 2 reach lengths, energy slopes, roughness | local `.basin` |
| 340 tests, > 80% | Younkin and Merkel: cases meeting 1% peak, 1-step timing, 95% shape correlation | TP-135 p. 13 |
| 1 order of magnitude | DNCFR speed vs DAMBRK/UNET; < 10% network discrepancies | TP-135 p. 27 |
| 5 min - 1 day | DNCFR variable time increment bounds | TP-135 p. 14 |
| 1/5 of the inflow duration; 1/20 of the wavelength | DNCFR rules of thumb for the travel time per dx and for overbank mixing | TP-135 p. 15-16 |
| c = 2.157 m/s, mu = 50 m^2/s, dt = 4637 s, Cr = 1.00 | third-order grid of the arXiv sinusoid test (L = 10 km, dx = L) | Wang et al. 2018 p. 8 |
| C ~ 2.1, D ~ 0.26, C3 ~ -0.25 | Block 2 reach R1 at Q = 300 m3/s, dt = 300 s, dx = 456 m, if N = round(L/dx) = 57: the real celerity (~3.2 m/s, wide-channel Manning) is twice the index celerity, so the Courant number is ~2, still within C + D >= 2 and with an admissible negative C3 | my arithmetic on the local reach, [Likely] |
| T S_o u_o/d_o ~ 220; T S_o (g/d_o)^(1/2) ~ 540 | R1 with T = 6 h: kinematic regime by a wide margin; attenuation will be small, timing set by c | my arithmetic, [Likely] |

## Recommendation for Wadi2D

1. **Implement the lumped reach as an "HMS replication" scheme first, exactly E1 + E4, not a textbook MC.** The replication test of
   mode (a) (CLAUDE.md decision 6) only means something if the reach routine reproduces HMS 4.12 to within the Younkin-Merkel
   tolerances (peak within 1%, timing within one 5-min step, volume within 1%). Build it with the current dt rule (min of control
   step and travel time, rounded to a divisor or multiple), `dx = c_idx dt`, the index read from the `.basin`, depth from Manning at
   the entered slope with Newton iteration, analytic `dQ/dA` for the four standard shapes and numerical for 8-point and tabular,
   and the four-point iteration as default with a three-point switch. Expose `N`, `dx`, `dt`, `C`, `D` and `C2` per reach in the run
   log so a mismatch with HMS's own notes is visible.

2. **Treat the three undocumented points as tunable, and tune them against HMS output on the eight Block 2 reaches**: the rounding of
   `N = L/dx`, the averaging stencil (three- or four-point) with its tolerance, and the overbank compositing of the 8-point section.
   Do it as a pytest that runs the HMS reach hydrographs (DSS export of inflow and outflow per reach) through the routine; fix the
   three knobs to whichever combination matches, then freeze them. The eight Block 2 reaches cannot test the 8-point path (all
   trapezoids), so add one HMS run with an 8-point section and one with Index Flow before freezing.

3. **Offer Todini's MCT (E5) as the production option and keep HMS mode for replication only.** The hydrograph of a lumped hill
   subbasin enters the 2D domain at the wadi mouth; the 2D solver conserves volume to round-off and the first thing a reviewer does
   with a hybrid run is a volume check. A variable-parameter MC that loses 2-5% (more on flat reaches) would put a visible error in
   the one place the model can be audited. MCT also returns the mean stage in the reach, which the HMS scheme does not.

4. **Keep the Ponce-Theurer check as a run-time warning, not a hard stop**: `C + D >= 2` (HMS's own constraint), and warn separately
   when `C > 1.5`, because with the 5 ft/s index on Block 2's steep wadis the actual Courant number is about 2 (Numbers table). Do
   not "fix" this silently: HMS makes the same choice and replication requires matching it.

5. **Reject**: the two-point parameter average (85% mass conservation); constant-parameter MC as the design routine (the result depends
   on the chosen reference flow), but keep it with the Wang et al. sinusoid and the third-order grid `C^2 + 3D^2 = 1` as the exact
   unit test; TP-135's separate overbank routing (not HMS, and the 2D domain handles overbank storage anyway); a kinematic-wave-only
   routine (no attenuation, no diffusion term, no reviewer acceptance gain).

6. **Make the terrain-derived reach (CLAUDE.md decision 8) write HMS's own containers**: an 8-point "Cross Sections" paired-data curve
   with the banks at points 3 and 6 and three n values, or a fitted trapezoid (`Bottom Width`, `Side Slope`), plus `Length` and
   `Energy Slope` from the burned stream profile, so the HMS model built from Wadi2D is apples to apples with the Wadi2D run. For the
   index, write `Index Flow` at the design flow rather than the 5 ft/s default: it ties `dx` to the section and is defensible to a
   reviewer. This is a modelling choice for the owner, not a code decision; flag it in the design note.

7. **Scope**: MC only in confined hill wadis (kinematic regime, slopes above 0.002, where both HMS criteria are met by a wide margin,
   Numbers table). Fans and braided reaches are 2D by decision 5-6; never route them with MC, and never route a reach that the 2D
   domain backs up (MC has no downstream boundary).

## Open issues

- Which averaging stencil HMS uses (three-point or iterative four-point), the iteration tolerance, and the exact meaning of
  `Maximum Depth Iterations` / `Maximum Route Step Iterations` (not in the UM, TRM or 4.3 release notes; the 4.10-4.12 release-note
  URLs tried do not exist). Resolve by the replication test, or by one question to HEC.
- How HMS rounds `N = L / (c dt)` and whether it applies the Ponce-Theurer constraint to `dx` or only reports `dx_ref`.
- Whether the celerity from an Index Flow is computed at the entered energy slope with normal depth (assumed) and whether the 8-point
  conveyance is subdivided (assumed) or composite-n.
- `.basin` keys and units for circle, eight point, tabular, Index Flow, specified DX/DT and channel loss were not observed in any of
  the 138 local files (all 7,230 reaches are trapezoid, index celerity, automatic DX/DT, no loss). One manual HMS session that saves
  one reach of each kind closes this in ten minutes; the search budget for a web answer was exhausted.
- Whether the current HMS still honours a time-of-rise term in some form (the 2000 rule) when the inflow is known before the reach
  computes (it may, for a run with a single upstream subbasin); only HMS's own notes in the run log will tell.
- Metric units of the 8-point paired data (`M:M` by analogy with the `FT:FT` tutorial) and whether station must be monotonic.
- EM 1110-2-1417 (the source HMS names for `dx_ref`) returned HTTP 403; its chapter 9 was not read, so its wording of the constraint
  is unverified; the HMS statements were used instead.

## Sources

1. HEC-HMS Technical Reference Manual (current), Muskingum-Cunge Model.
   https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/channel-flow/muskingum-cunge-model — Eqs 1-16, dt/dx rules, reference flow,
   shapes, recalculation statement.
2. HEC-HMS Technical Reference Manual, March 2000, CPD-74B (PDF; pp. 91-96 rendered and read).
   https://www.hec.usace.army.mil/software/hec-hms/documentation/HEC-HMS_Technical%20Reference%20Manual_(CPD-74B).pdf — Eqs 8-18 to
   8-34, the 1/20 time-of-rise rule, Fig. 8-5 eight-point layout, Table 8-3 applicability, Ponce (1986) citation.
3. HEC-HMS guide, Applying the Muskingum-Cunge Routing Method.
   https://www.hec.usace.army.mil/confluence/hmsdocs/hmsguides/applying-reach-routing-methods-within-hec-hms/applying-the-muskingum-cunge-routing-method
   — index method, 5 ft/s, dx_ref note, slope guidance, three n values.
4. HEC-HMS User's Manual 4.8, Selecting a Reach Routing Method.
   https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/4.8/reach-elements/selecting-a-reach-routing-method — parameters, six shapes,
   space-time options, invert elevation. Also the "latest" page (same text):
   https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/latest/reach-elements/selecting-a-reach-routing-method
5. HEC-HMS User's Manual 4.13, HEC-HMS and HEC-1 differences: Muskingum Cunge Routing.
   https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/4.13/hec-hms-and-hec-1-differences/muskingum-cunge-routing — exact depth solve
   vs 20-depth tables; Manning velocity.
6. HEC-HMS Version 4.3 Release Notes (PDF). https://www.hec.usace.army.mil/software/hec-hms/documentation/HEC-HMS_Release_Notes_4.3.pdf
   — index flow/celerity requirement and reason, tabular shape, negative elevations.
7. HEC-HMS guide, Creating Cross Section Paired Data Curves.
   https://www.hec.usace.army.mil/confluence/hmsdocs/hmsguides/applying-reach-routing-methods-within-hec-hms/creating-cross-section-paired-data-curves
   — how the 8-point curve is entered.
8. Garbrecht and Brunner (1991), A Muskingum-Cunge Channel Flow Routing Method for Drainage Networks, HEC TP-135 (PDF).
   https://www.hec.usace.army.mil/Publications/TechnicalPapers/TP-135.pdf — HEC's four-point iterative implementation, reference
   discharge 2/3, Ponce-Theurer dx limit with lambda = 2, slope 0.0002 limit, verification numbers.
9. Ponce and Yevjevich (1978), Muskingum-Cunge method with variable parameters (author reprint).
   https://ponce.sdsu.edu/muskingum_cunge_method_with_variable_parameters.html — C-D coefficients, two/three/four-point schemes.
10. Ponce and Theurer (1982), Accuracy criteria in diffusion routing (author reprint).
    https://ponce.sdsu.edu/accuracy_criteria_in_diffusion_routing.html — C2 >= 0.33, kappa = 2, dx and dt criteria.
11. Ponce and Chaganti (1994), Variable-parameter Muskingum-Cunge method revisited (author reprint).
    https://ponce.sdsu.edu/variable_parameter_muskingum_cunge_method_revisited.html — averaging schemes, mass-conservation numbers.
12. Ponce, Muskingum-Cunge method explained. https://ponce.sdsu.edu/muskingum_cunge_method_explained.html — C0/C1/C2 form, Courant ~1
    advice, linear vs nonlinear mass statements.
13. Ponce (1986), Diffusion wave modeling of catchment dynamics (author reprint).
    https://ponce.sdsu.edu/diffusion_wave_modeling_of_catchment_dynamics.html — the algorithm HMS cites: four-point stencil, lateral
    inflow coefficient 2C/(1+C+D), Froude-corrected D, criterion 30.
14. Wang, Lapin, Wu, Elliot, Fiedler (2018), Accuracy of the Muskingum-Cunge method for constant-parameter diffusion-wave channel
    routing with lateral inflow, arXiv:1802.04429. https://arxiv.org/abs/1802.04429 (PDF read, pp. 1-8) — C4 = 1 - C3, second/third-order
    conditions, analytical test case.
15. Todini (2007), A mass conservative and water storage consistent variable parameter Muskingum-Cunge approach, HESS 11:1645-1659.
    https://hess.copernicus.org/articles/11/1645/2007/hess-11-1645-2007.pdf — cause of the mass loss, MCT algorithm Eqs 29-56.
16. Merkel (NRCS), Muskingum-Cunge Flood Routing Procedure in NRCS Hydrologic Models. https://www.hydrocad.net/pdf/Merkel-MC-paper.pdf
    — TR-20 dt/dx rules, c = m V, test programme.
17. Local HMS 4.12 model, Block 2: `D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\HEC_HMS_Block_02\Basin_1.basin` and
    `Control_1.control` (read-only) — the per-reach keys, units and values; plus a key survey of the 138 `.basin` files under
    `D:\Mojtaba\Renardet\2224 WS11` (7,230 Muskingum-Cunge reaches).
18. Not read (for the record): EM 1110-2-1417 (HTTP 403); Ponce and Yevjevich's ASCE original (paywalled; the author reprint was used);
    HMS release notes 4.10-4.12 (URLs not found).
