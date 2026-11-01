# H01 HEC-HMS SCS CN loss, SCS unit hydrograph and Clark unit hydrograph: the exact discrete algorithms

Date: 2026-10-29

## Scope

What HEC-HMS (4.1 through 4.14) actually computes, step by step, for the three lumped-hydrology components that Wadi2D must
reproduce within 1% in mode (a) of decision 6 (all-lumped replication of the Block 2 HMS model): the SCS curve-number loss
(lumped and gridded), the SCS dimensionless unit hydrograph (lag, PRF, interpolation to the computation step, convolution), the
Clark unit hydrograph (Tc, R, synthetic time-area curve, linear-reservoir discretisation, ModClark), how the control-specification
time step enters each, and the baseflow options (none, recession with ratio-to-peak). Sources are the primary documents: the 2000
Technical Reference Manual (CPD-74B, the only HEC document that states the time-step rule and the discretisation in equations), the
current online TRM and User's Manual pages, the 4.1 User's Manual PDF, the HEC-1 manual (CPD-1A, 1998; HEC-HMS inherited its
unit-hydrograph arithmetic and the manual states it more explicitly than any HMS document), and NRCS NEH 630 chapters 10 and 16
(the equations and tables HMS cites). Out of scope: frequency storm, ARF and depth-area (other topics), Muskingum-Cunge, Snyder,
kinematic wave, continuous loss methods.

Confidence tags: [Certain] read in a primary source or arithmetic reproduced here; [Likely] strong inference; [Guessing] gap-filling.
The web-search budget ran out after the sources below were secured; the items it would have closed are listed under Open issues.

## Findings

1. **HMS applies the CN equation to cumulative rainfall and differences it per time step; there is no infiltration-rate form.**
   [Certain] "Incremental excess for a time interval is computed as the difference between the accumulated excess at the end of and
   beginning of the period." CPD-74B p. 41, https://ponce.sdsu.edu/HEC-HMS_Technical%20Reference%20Manual_(CPD-74B).pdf (same
   statement in the 4.1 UM p. 201 and in HEC-1 section 3.2.3).

2. **In the lumped method Ia is an optional absolute depth (mm or in), default 0.2 S; the "initial abstraction ratio" and the
   "potential retention scale factor" exist only in the gridded method.** [Certain] "If this value is left blank, it will be
   automatically calculated as 0.2 times the potential retention" and, for gridded, "The default initial abstraction ratio is 0.2 but
   may optionally be changed." https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/latest/subbasin-elements/selecting-a-loss-method
   Consequence: a user-entered Ia changes only Ia; S stays (1000/CN - 10) [Certain, HEC-1 eqs 3.17-3.19]. NEH warns that a ratio other
   than 0.2 invalidates the published CN values: "if a relationship different from Ia = 0.2S is used, a new set of curve numbers must
   be developed." NEH 630 ch. 10 p. 10-3, https://mail.irrigationtoolbox.com/NEH/Part630_Hydrology/H_210_630_10.pdf

3. **S from CN, both unit systems, and the CN range.** [Certain] "CN values range from 100 (for water bodies) to approximately 30 for
   permeable soils with high infiltration rates." CPD-74B p. 41 (eq. 5-6: S = (1000 - 10 CN)/CN in, S = (25400 - 254 CN)/CN mm).
   HMS gives no validity check beyond this range in the documents read.

4. **Impervious area: no loss on the directly-connected impervious fraction; its rainfall is added to the pervious excess before the
   transform; the composite CN must exclude it; TR-55 urban CNs already include it.** [Certain] "excess on pervious portions of the
   watershed is added to the precipitation on directly-connected impervious area" CPD-74B pp. 38-39; "No loss calculations are carried
   out on the impervious area; all precipitation on that portion of the subbasin becomes excess" 4.1 UM p. 201. The same percent
   impervious factor works with every loss method (HEC-1 section 3.2, RTIMP).

5. **Gridded CN is the same equation per cell with the cell CN and the cell rainfall; it can only be routed with ModClark.**
   [Certain] "HEC-HMS computes precipitation excess for each cell independently, using Equation 5-5, and routes the excess to the
   watershed outlet, using the ModClark method." CPD-74B p. 42. Per-cell Ia = ratio x (scale x S(CN_cell)) [Certain, UM latest].
   The UM sentence "All cells are initialized by scaling based on the curve number at each cell" is not explained anywhere [Guessing
   on its meaning: the per-cell S and Ia are set from the cell CN at the start].

6. **Weighted-CN (what HMS lumped does) and weighted-Q (what a per-cell CN does) are not the same volume.** [Certain] "where
   differences in CN for a watershed are large, this method either under- or over-estimates Q, depending on the size of the storm"
   NEH 630 ch. 10 p. 10-16. The weighted-Q method "always gives the correct result (in terms of the given data)". This is a built-in,
   explainable reason why Wadi2D mode (c) (per-cell CN) will not reproduce mode (a) (composite CN) even with identical rain.

7. **The CN method is event-only in HMS: nothing ever drains the retained volume.** [Certain] "Since no means for extracting infiltrated
   water is included, this method should only be used for event simulation."
   https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/canopy-surface-infiltration-and-runoff-volume/infiltration/scs-curve-number-loss-model

8. **Direct runoff is the discrete convolution of the excess pulses with the dt-duration unit hydrograph.** [Certain] Q_n = sum over
   m = 1..min(n, M) of P_m U_(n-m+1); "P_m: rainfall excess depth in the interval from m dt to (m+1) dt"; "U: unit hydrograph ordinate at
   time (n-m+1) dt". https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/transform/unit-hydrograph-basic-concepts

9. **SCS UH peak and time to peak, with the unit constant.** [Certain] "C = conversion constant (2.08 in SI and 484 in foot-pound
   system)" CPD-74B p. 58 (eq. 6-8: Up = C A/Tp; eq. 6-9: Tp = dt/2 + tlag; "dt = the excess precipitation duration (which is also the
   computational interval in HEC-HMS)"). Arithmetic [Certain]: 484 cfs/(mi2 in/h) = 0.2083 (m3/s)/(km2 mm/h) = 2.083 (m3/s)/(km2 cm/h),
   so the TRM's "2.08 in SI" is per **centimetre** of excess; with millimetres the constant is 0.2083.

10. **Time-step rule for the SCS UH: dt < 29% of lag, derived from D = 0.2 Tp (max 0.25 Tp).** [Certain] "a computational interval,
    dt, that is less than 29% of tlag must be used (USACE, 1998)" CPD-74B p. 58; HEC-1 p. 24: "The selection of the program computation
    interval ... is based on the relationship dt = 0.2 * TPEAK" and "the duration of the unit graph should not exceed dt = 0.25 * Tpeak".
    https://www.hec.usace.army.mil/publications/ComputerProgramDocumentation/HEC-1_UsersManual_(CPD-1a).pdf
    The current online TRM, UM and "program setup" pages do **not** state the rule at all [Certain, checked]; the "lag/3" and "lag/5" rules
    of thumb circulating in tutorials bracket it (0.33 lag is above the bound, 0.2 lag below).

11. **The standard dimensionless UH is the tabulated NEH curve (0.1 Tp spacing to 2.0 Tp, then 0.2 and 0.5), with 37.5% of volume
    before the peak, PRF 484; HMS "interpolates" it at the computation step and scales by Up.** [Certain for HEC-1, Likely that HMS
    inherited it unchanged] "The unit hydrograph is interpolated for the specified computation interval and computed peak flow from the
    dimensionless unit hydrograph" HEC-1 p. 24. NEH: "it should be no greater than 0.25 Tp" and "If D is 0.2 Tp, then during
    computations, every second point is used" NEH 630 ch. 16 App. 16A p. 16A-3,
    https://directives.nrcs.usda.gov/sites/default/files2/1720461096/Chapter%2016%20-%20Hydrographs.pdf
    No HEC document says whether the sampled SCS UH is renormalised to unit volume (the Clark UH is, finding 14).

12. **PRF: standard 484; range 100 (flat) to 600 (steep); Delmarva for flat coastal basins; other PRFs come from the NEH gamma curve.**
    [Certain for NEH and the UM text; Likely that HMS builds a non-484 PRF from the gamma equation] "Unit hydrographs with specific peak
    rate factors are defined in the National Engineering Handbook (NRCS, 2007)." 4.1 UM p. 212; "The gamma equation may be used to
    develop a DUH with any desired peak rate factor." NEH 16 p. 16-15, and App. 16B tables for PRF 100-600 "developed using the gamma
    equation". Arithmetic [Certain]: gamma with m = 3.7 gives PRF 484.2, but its ordinates differ from the tabulated standard by +4% at
    t/Tp = 0.5, +3.6% at 1.5 and +15% at 2.0, so the gamma curve is not the standard 484 curve.

13. **PRF is a unit constant times a dimensionless shape factor: PRF = 645.33 K, K = 2/(1 + Tr/Tp) = 0.75 for the standard shape.**
    [Certain] "645.33 = conversion factor for the rate required to discharge 1 inch from 1 square mile in 1 hour" NEH 16 App. 16A
    p. 16A-2. Hence Up = K A D/Tp in any consistent units (checked: 0.75 x 1 km2 x 1 mm / 1 h = 0.2083 m3/s).

14. **Clark discretisation: time-area curve sampled at dt gives the translation hydrograph; linear reservoir with CA = dt/(R + 0.5 dt),
    CB = 1 - CA; the dt-UH ordinate is the mean of consecutive instantaneous outflows; stop at 0.995 of unit volume (HEC-1 also at 150
    ordinates); HMS then rescales to exactly one unit, HEC-1 did not.** [Certain] "HEC-HMS continues computation of the UH ordinates
    until the volume of the outflow exceeds 0.995 inches or mm." CPD-74B p. 62; HEC-1 p. 23: "terminated when its volume exceeds
    0.995 inch (mm) or 150 ordinates, whichever occurs first"; UM: HEC-HMS "applies a flow-weighting adjustment so the volume is exactly
    100%. HEC-1 made no such adjustment."
    https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/latest/hec-hms-and-hec-1-differences/clark-unit-hydrograph

15. **Default Clark time-area curve.** [Certain] A_t/A = 1.414 (t/Tc)^1.5 for t <= Tc/2; 1 - 1.414 (1 - t/Tc)^1.5 for t >= Tc/2, CPD-74B
    eq. 6-22 (HEC-1 eqs 3.33-3.34). The UM calls the shape "diamond" (4.1) and "elliptical" (4.8 onward) [Certain]; the equation on the
    TRM page is unchanged [Likely that the code is too]. A user curve is a monotonic percentage curve (% of Tc vs cumulative % area).

16. **The Clark scheme is the trapezoidal (Crank-Nicolson) step of dS/dt = I - O with S = R O; CB < 0 when dt > 2R.** [Certain,
    arithmetic] CB = (R - 0.5 dt)/(R + 0.5 dt). HMS documents no check; a short R with a long step gives a sign-alternating UH.

17. **ModClark: per-cell travel time t_cell = Tc d_cell/d_max, one R for all cells, one linear reservoir per cell, outflows summed.**
    [Certain] "t_cell = Tc,watershed x (D_cell / D_max)" https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/transform/modclark-unit-hydrograph-model
    (CPD-74B eq. 6-23). Each cell's inflow per step is cell area x cell excess.

18. **Recession baseflow: Q_t = Q_0 k^t with k per day; threshold as ratio-to-peak or flow; after the threshold the total flow is the
    recession from the threshold value and "baseflow" is recession minus direct runoff; the method does not conserve mass.**
    [Certain] "k is defined as the ratio of the baseflow at time t to the baseflow one day earlier" CPD-74B p. 76; "It does not conserve
    mass within the subbasin." 4.1 UM p. 223; HEC-1 conversion k = 1/RTIOR^24 (UM, HEC-1 differences page). Typical k: groundwater 0.95,
    interflow 0.8-0.9, surface 0.3-0.8 (Table 7-1). https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/baseflow/recession-model

19. **"None" baseflow means outflow = direct runoff only.** [Certain] "the subbasin will not compute baseflow and the outflow will only
    include direct runoff from the Transform Method" https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/latest/subbasin-elements/selecting-a-baseflow-method

20. **The control-specification interval (1 min to 1 day) is the UH duration and the output step; gage and grid data are linearly
    interpolated to it; some methods sub-step internally.** [Certain] "In some cases, computations may be carried out at a shorter time
    interval and results interpolated to the interval specified" 4.1 UM p. 66 and
    https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/latest/projects-and-control-specifications/control-specifications
    Which methods sub-step is not stated [Likely: kinematic wave, Muskingum-Cunge and reservoir routing, not the UH methods].
    Consequence [Certain, arithmetic]: the HMS peak itself depends on dt through Tp = dt/2 + tlag; for tlag = 60 min, dt = 5 vs 15 min
    moves Tp from 62.5 to 67.5 min and Up by 8%. Replication must use the Block 2 control-specification interval, not a finer one.

21. **Sampling the DUH at dt conserves volume to 0.3% for dt <= 0.33 Tp, but the sampled peak can sit 1.6% below Up when Tp is not a
    multiple of dt.** [Certain, arithmetic in this note, Table 16-1 linearly interpolated; HMS makes Tp = dt/2 + tlag, which is a
    multiple of dt only by accident.] Comparisons with HMS must be made on hydrographs, not on UH peaks.

## Equations and algorithms

Notation: dt = computation interval of the control specification, P(t) = cumulative rainfall since the start of the run on the
pervious fraction, D = unit depth (1 mm or 1 in), A = subbasin area. All HMS series are stored at the end of each interval.

### A. SCS CN loss, lumped (CPD-74B eqs 5-3 to 5-7; HEC-1 eqs 3.17-3.19; NEH 10 eqs 10-1, 10-10 to 10-13)

Parameters: CN (composite, pervious part only), Ia (depth, optional), f_imp (directly-connected impervious fraction, 0-1).

    S  = 1000/CN - 10                  [in]        S = 25400/CN - 254        [mm]      (eq. 5-6)
    Ia = 0.2 S                                     unless the user enters Ia (then S is unchanged)
    Pe(P) = 0                                      for P <= Ia
    Pe(P) = (P - Ia)^2 / (P - Ia + S)              for P > Ia                                           (eq. 5-3)
    with Ia = 0.2 S:  Pe = (P - 0.2 S)^2 / (P + 0.8 S)                                                  (eq. 5-5)
    CN_composite = sum_i (A_i CN_i) / sum_i A_i                                                         (eq. 5-7)
    NEH form of CN from S: CN = 1000/(10 + S[in]) = 1000/(10 + S[mm]/25.4)                              (eqs 10-12, 10-13)

Per step n (end of interval n), with dP_n the interval rainfall:

    P_n      = P_(n-1) + dP_n
    Pe_n     = Pe(P_n)
    dPe_n    = Pe_n - Pe_(n-1)                     (pervious excess this step; >= 0 by construction since dPe/dP >= 0)
    loss_n   = dP_n - dPe_n
    excess_n = (1 - f_imp) dPe_n + f_imp dP_n      (what enters the transform; impervious rain is 100% excess)

Incremental runoff coefficient (useful for checks): dPe/dP = 1 - [S/(P - Ia + S)]^2, which is 0 at P = Ia and tends to 1.
State carried: P_n and Pe_n per subbasin (or per cell). Nothing recovers between storms (finding 7).

### B. SCS CN loss, gridded (CPD-74B p. 42; UM latest)

Parameters: CN grid, initial abstraction ratio lambda (default 0.2), potential retention scale factor sigma (default 1.0). Per cell c:

    S_c = sigma (25400/CN_c - 254)      Ia_c = lambda S_c      P_c from the gridded rainfall of that cell
    dPe_(c,n) = Pe_c(P_(c,n)) - Pe_c(P_(c,n-1))      with Pe_c as in A
    cell inflow to ModClark = A_c dPe_(c,n) / dt

HMS routes gridded excess only with ModClark (algorithm F). No impervious percentage is documented for the gridded CN method.

### C. SCS unit hydrograph at the computation step (CPD-74B eqs 6-8, 6-9; HEC-1 eqs 3.41, 3.42; NEH 16 Table 16-1, App. 16A)

Parameters: lag tlag (HMS asks minutes; guidance tlag = 0.6 Tc), PRF (default 484; Delmarva option; user value in current versions).

    Tp = dt/2 + tlag                                                                                     (eq. 6-9)
    K  = PRF/645.33                                 (dimensionless; 0.75 for PRF 484; 645.33 = 5280^2/12/3600 cfs h/(mi2 in))
    Up = K A D / Tp                                 (any consistent units; = 484 A[mi2] D[in]/Tp[h] cfs; = 0.2083 A[km2] D[mm]/Tp[h] m3/s)
    U_i = Up f(i dt / Tp),  i = 0, 1, 2, ... until f = 0 (t/Tp = 5)                                     ("interpolated for the specified computation interval")
    f(x) = linear interpolation of Table 16-1 below (standard, PRF 484)
    optional (recommended, see Recommendation): U_i <- U_i (A D) / (sum_i U_i dt)   so that the discrete volume is exactly one unit

Standard dimensionless unit hydrograph, NEH 630 ch. 16 Table 16-1 (t/Tp, q/qp, Qa/Q):

    0.0 0.000 0.000 | 0.1 0.030 0.001 | 0.2 0.100 0.006 | 0.3 0.190 0.017 | 0.4 0.310 0.035 | 0.5 0.470 0.065
    0.6 0.660 0.107 | 0.7 0.820 0.163 | 0.8 0.930 0.228 | 0.9 0.990 0.300 | 1.0 1.000 0.375 | 1.1 0.990 0.450
    1.2 0.930 0.522 | 1.3 0.860 0.589 | 1.4 0.780 0.650 | 1.5 0.680 0.705 | 1.6 0.560 0.751 | 1.7 0.460 0.790
    1.8 0.390 0.822 | 1.9 0.330 0.849 | 2.0 0.280 0.871 | 2.2 0.207 0.908 | 2.4 0.147 0.934 | 2.6 0.107 0.953
    2.8 0.077 0.967 | 3.0 0.055 0.977 | 3.2 0.040 0.984 | 3.4 0.029 0.989 | 3.6 0.021 0.993 | 3.8 0.015 0.995
    4.0 0.011 0.997 | 4.5 0.005 0.999 | 5.0 0.000 1.000

Trapezoid area of this table = 1.3359 (dimensionless), so PRF = 645.33/1.3359 = 483.0; NEH states 483.4 "due to rounding of the
discharge ratios"; the equivalent triangle (Tb = 2.67 Tp, Tr = 1.67 Tp, inflection at 1.7 Tp) gives exactly 484.

Non-standard PRF (NEH 16 eqs 16-1, 16-2; HMS implementation [Likely]):

    q/qp = e^m (t/Tp)^m e^(-m t/Tp)                 (eq. 16-1), area = e^m Gamma(m+1)/m^(m+1),  PRF = 645.33/area
    m -> PRF (NEH Table 16-5, reproduced here): 0.26->101, 1->238, 2->349, 3->433, 3.7->484, 4->504, 5->566
    solve m for the target PRF by bisection on PRF(m) (monotonic), then sample as in C.

Time-step chain (HEC-1 p. 24; NEH App. 16A eqs 16A-10 to 16A-13): D = 0.2 Tp ideal, D <= 0.25 Tp maximum; with tlag = 0.6 Tc and
Tc + D = 1.7 Tp: D = 0.133 Tc; in HMS terms dt = 0.2 Tp <=> dt = 0.222 tlag, and dt = 0.25 Tp <=> dt = 0.29 tlag (the TRM rule).

### D. Convolution (TRM, UH basic concepts; CPD-74B eq. 6-1)

    Q_n = sum_(m=1)^(min(n, M)) P_m U_(n-m+1)        P_m = excess_m [depth], U in flow per unit depth, Q_n at t = n dt
    total outflow_n = Q_n + baseflow_n

### E. Clark unit hydrograph (CPD-74B eqs 6-16 to 6-22; HEC-1 eqs 3.33-3.38)

Parameters: Tc, R (hours), time-area curve F(tau), tau = t/Tc in [0,1], F(0) = 0, F(1) = 1, monotonic.

    default F(tau) = 1.414 tau^1.5                       for tau <= 0.5
    default F(tau) = 1 - 1.414 (1 - tau)^1.5             for 0.5 <= tau <= 1                              (eq. 6-22)
    translation hydrograph (inflow to the reservoir for unit instantaneous excess):
        I_i = A D [F(min(i dt/Tc, 1)) - F(min((i-1) dt/Tc, 1))] / dt,   i = 1 .. ceil(Tc/dt);  I_i = 0 after
    linear reservoir, trapezoidal step of dS/dt = I - O with S = R O:
        CA = dt/(R + 0.5 dt),  CB = 1 - CA = (R - 0.5 dt)/(R + 0.5 dt)                                   (eqs 6-19, 6-20)
        O_0 = 0;  O_i = CA I_i + CB O_(i-1)                                                             (eq. 6-18)
        U_i = (O_(i-1) + O_i)/2                      (dt-duration UH ordinate at the end of interval i)  (eq. 6-21; HEC-1 eq. 3.38)
    stop when sum U_i dt >= 0.995 A D (HEC-1: or i = 150), then U_i <- U_i (A D)/(sum U_i dt)  [HMS; HEC-1 skipped the rescale]
    constraint: dt < 2R (else CB < 0 and U oscillates); HMS documents no check.

Variable-parameter option: Tc and R scaled by percentage curves of excess rate relative to an index excess (default 1 mm/h or
1 in/h) [Certain, UM]; Maricopa option: Tc, R from L, Kb, S and the mean of the ten largest 5-min excess values from a preliminary 5-min
run [Certain, UM]. Neither is in the Block 2 model.

### F. ModClark (CPD-74B eq. 6-23; TRM page)

    t_c = Tc d_c/d_max   per cell c (d = travel distance to the outlet; d_max = the most distant cell)
    each cell: inflow I_(c,n) = A_c excess_(c,n)/dt delayed by t_c (translation), then the reservoir of E with the single R
    subbasin direct runoff = sum_c O_c (the delays make this a cell-wise time-area histogram)

### G. Recession baseflow (CPD-74B eq. 7-1, pp. 75-77; UM baseflow page)

Parameters: Q_0 (flow, or flow per area x A), k (per day), threshold type: ratio r to the event peak, or absolute Q_thr.

    per-step factor: kappa = k^(dt/(1 day))
    before the threshold: B_n = B_(n-1) kappa, B_0 = Q_0;  total_n = Q_n + B_n
    track the event peak of total_n; on the receding limb, when total_n <= r x peak (or <= Q_thr):
        set the recession anchor Q* = total_n at that step, then total_(n+j) = Q* kappa^j and B_(n+j) = total_(n+j) - Q_(n+j)
    if later Q_(n+j) + (initial recession) exceeds the recession, the second rise is direct runoff plus the initial recession
    (CPD-74B Fig. 7-3), and the threshold logic restarts for the new event (UM: "automatically reset after each storm event")
    "none": total_n = Q_n

### H. Where the control-specification dt enters

    SCS UH:  Tp = dt/2 + tlag; U sampled at i dt; rule dt < 0.29 tlag (ideal 0.22 tlag = 0.133 Tc)
    Clark:   I sampled at i dt; CA, CB; rule dt < 2R (hard), D <= 0.25 Tp style guidance -> dt <= Tc/5 as a working rule [Likely]
    CN:      step-independent in the cumulative form; only the hyetograph resampling matters
    Rain:    gage/grid series linearly interpolated to dt; the manuals do not say whether the interpolation is on cumulative depth
             [Likely cumulative, the HEC-DSS PER-CUM convention] - verify before comparing at a dt different from the gage step
    Output:  all series at dt, end-of-interval; start and end minutes must be multiples of dt

## Numbers

| Value | Context | Source |
|---|---|---|
| S = 1000/CN - 10 in; 25400/CN - 254 mm | potential maximum retention | CPD-74B eq. 5-6; NEH 10 eqs 10-12/13 |
| Ia = 0.2 S | default initial abstraction (lumped: depth; gridded: ratio 0.2 x scale 1.0) | CPD-74B eq. 5-4; UM latest |
| CN 30 to 100 | stated CN range | CPD-74B p. 41 |
| 484 cfs/(mi2 in/h) | standard PRF, US | CPD-74B eq. 6-8; NEH 16 eq. 16A-6 |
| 2.08 (per cm) = 0.2083 (per mm) (m3/s)/(km2 h) | SI equivalent of 484 | CPD-74B p. 58; arithmetic here |
| 645.33 cfs h/(mi2 in) | 1 in from 1 mi2 in 1 h | NEH 16 eq. 16A-5; arithmetic 5280^2/12/3600 |
| K = 0.75 | dimensionless shape factor, PRF = 645.33 K | NEH 16 eq. 16A-3 |
| 37.5% | volume before the peak, standard DUH | NEH 16 p. 16A-1; UM |
| Tb = 2.67 Tp, Tr = 1.67 Tp, inflection 1.7 Tp | equivalent triangle | NEH 16 App. 16A |
| Tp = dt/2 + tlag | time to peak in HMS | CPD-74B eq. 6-9; HEC-1 eq. 3.41 |
| tlag = 0.6 Tc | lag guidance | NEH 16 eq. 16A-8; TRM page |
| D = 0.2 Tp ideal; <= 0.25 Tp max; D = 0.133 Tc | unit duration vs Tp | NEH 16 App. 16A; HEC-1 p. 24 |
| dt < 0.29 tlag | HMS computational-interval rule | CPD-74B p. 58 (USACE 1998) |
| PRF 100-600; flat about 100, steep about 600 | PRF range | UM; NEH 16 p. 16-14 |
| m = 3.7 <-> PRF 484 (gamma); 0.26->101, 1->238, 2->349, 3->433, 4->504, 5->566 | gamma DUH shape factor | NEH 16 Table 16-5; reproduced here |
| gamma vs Table 16-1: +4% at 0.5 Tp, +3.6% at 1.5 Tp, +15% at 2.0 Tp | gamma is not the standard curve | arithmetic here |
| Table 16-1 area 1.3359 -> PRF 483.0 (NEH: 483.4) | rounding of the standard table | NEH 16 p. 16A-2; arithmetic here |
| discrete volume error <= 0.3% for dt <= 0.33 Tp; sampled peak down to 0.984 Up | sampling the DUH at dt | arithmetic here |
| A/Ac = 1.414 (t/Tc)^1.5 (t <= Tc/2) | default time-area curve | CPD-74B eq. 6-22; HEC-1 eq. 3.33 |
| CA = dt/(R + 0.5 dt), CB = 1 - CA | Clark routing coefficients | CPD-74B eqs 6-19/20; HEC-1 eqs 3.36/37 |
| CB < 0 for dt > 2R | Clark stability | arithmetic here |
| 0.995 of unit volume; 150 ordinates (HEC-1) | Clark UH truncation | CPD-74B p. 62; HEC-1 p. 23 |
| k per day; kappa = k^(dt/day); k = 1/RTIOR^24 | recession constant | CPD-74B p. 76; UM HEC-1 differences |
| k: 0.95 groundwater, 0.8-0.9 interflow, 0.3-0.8 surface | typical values (Pilgrim and Cordery 1992) | CPD-74B Table 7-1 |
| ratio-to-peak example 0.10 of 1000 -> 100 m3/s | threshold | CPD-74B p. 76 |
| 1 min to 1 day | control-specification interval choices | UM 4.1 p. 66; UM latest |
| dt 5 -> 15 min at tlag 60 min: Up -8% | peak depends on dt through Tp | arithmetic here |
| 1 in/h or 1 mm/h | Clark variable-parameter index excess default | UM latest |
| <= 20 mi2 subareas, largest/smallest <= 10 | NEH guidance on subdivision for the DUH | NEH 16 p. 16-3 |

## Recommendation for Wadi2D

1. **Implement the lumped engine as a literal transcription of algorithms A, C, D, E and G, in SI, with the dimensionless K =
   PRF/645.33 and no 484/2.08 constant anywhere.** The 2.08 "SI" constant is per centimetre; one wrong unit here is a 10x error that
   a reviewer will find. Keep the cumulative-difference CN form (A) exactly; do not re-express CN as an infiltration rate (HEC-RAS and
   SWMM variants differ from HMS and will not replicate it).

2. **Build the unit hydrograph at the control-specification dt of the Block 2 model, and only there.** HMS's answer depends on dt
   through Tp = dt/2 + tlag (8% on Up between 5 and 15 min at a 60 min lag). Wadi2D's 2D solver runs at its own sub-second steps;
   the lumped hydrology must run on the HMS grid of time and be interpolated into the 2D model, never the other way round. Read dt,
   lag, CN, Ia, impervious percentage, graph type/PRF and the baseflow method from the Block 2 `.control` and `.basin` files (read-only)
   before coding the comparison [the file keys are Guessing until the files are opened].

3. **Standard DUH = Table 16-1 with linear interpolation; renormalise the sampled UH to unit volume; use the gamma curve only for
   a non-484 PRF.** The volume error of sampling is <= 0.3% for dt <= 0.33 Tp, so renormalising cannot break the 1% target whether or
   not HMS does it (unverified, open issue 1); the gamma curve for PRF 484 would miss the tabulated ordinates by 4-15% and must be
   rejected for replication. Compare hydrographs, not UH peaks (the sampled peak alone can be 1.6% low).

4. **Enforce the step rules as engine checks:** warn at dt > 0.29 tlag (SCS), warn at dt > Tc/5 and refuse at dt >= 2R (Clark).
   HMS itself warns on none of these in the documents read [Certain for the documents; the run-log message text could not be searched].

5. **Expect, and explain in the design note, that mode (c) cannot reproduce mode (a) volumes:** per-cell CN is NEH's weighted-Q
   method, HMS's composite CN is the weighted-CN method, and NEH says they diverge when CNs differ widely (Batinah: rock hills next to
   gravel fans). This is a documented property of the method, not a Wadi2D error; show it with the NEH example 10-5 logic on one Block 2
   subbasin before anyone asks.

6. **Baseflow: implement "none" and "recession with ratio-to-peak" only; nothing else is needed for Block 2.** Recession must keep
   the HMS semantics (anchor the recession to the total flow at the threshold, baseflow = recession - direct runoff, no mass
   conservation) or the comparison fails on the falling limb. Reject bounded recession, linear reservoir and Boussinesq for version 1.

7. **Reject for version 1:** gridded CN plus ModClark as an HMS-replication path (Wadi2D's 2D solver is the distributed path; ModClark
   adds a second, different distributed answer), the Clark variable-parameter and Maricopa options, the Delmarva UH (no Batinah
   relevance; its ordinates were not retrieved), and any "lag/3" rule of thumb (it sits above HEC's own 0.29 bound).

## Open issues

1. Whether HMS renormalises the sampled SCS UH to unit volume (documented only for Clark). Settle by a one-subbasin HMS run with a
   coarse dt and a 1-unit excess pulse: the output volume tells.
2. How HMS builds a user PRF (gamma equation vs. the NEH App. 16B tables at 0.1 Tp) and what ordinates/PRF the Delmarva option uses
   (PRF 284 [Likely]). The 4.3-era release notes that introduced the user PRF could not be fetched (search budget exhausted).
3. The meaning of "All cells are initialized by scaling based on the curve number at each cell" in the gridded CN method.
4. Whether HMS interpolates hyetographs to dt on cumulative depth (volume-conserving) or on intensities; matters only when the Block 2
   gage/pattern step differs from the control-specification step.
5. The exact run-log warning (if any) HMS issues when dt exceeds 0.29 of the lag; the online manuals have dropped the rule entirely.
6. Which Block 2 settings are actually in use (dt, PRF, Ia, impervious, baseflow): read from the HMS project files, not assumed.
7. Whether HMS samples the DUH at the end of each interval (i dt) as HEC-1 does, or at interval midpoints; HEC-1's statement "ordinate
   at end of computation interval" (Clark, eq. 3.38) makes end-of-interval [Likely] for both.

## Sources

1. HEC-HMS Technical Reference Manual, CPD-74B, March 2000 (Feldman ed.), PDF copy: https://ponce.sdsu.edu/HEC-HMS_Technical%20Reference%20Manual_(CPD-74B).pdf - eqs 5-3 to 5-7 (CN, composite, gridded), impervious handling pp. 38-39, eqs 6-8/6-9 and the 29% rule p. 58, Clark eqs 6-16 to 6-22 and the 0.995 truncation pp. 61-62, ModClark eq. 6-23, recession eq. 7-1 and threshold logic pp. 75-77, Table 7-1.
2. HEC-HMS TRM online, SCS Unit Hydrograph Model: https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/transform/scs-unit-hydrograph-model - Tp = tr/2 + tp, Qp = PRF A/Tp, tp = 0.6 Tc, PRF range, 37.5%; confirmed the time-step rule is absent.
3. HEC-HMS TRM online, Clark Unit Hydrograph Model: https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/transform/clark-unit-hydrograph-model - same equations as source 1 plus the 0.995 stop and rescale, X = R/(Tc+R), variable-parameter and Maricopa notes.
4. HEC-HMS TRM online, SCS Curve Number Loss Model: https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/canopy-surface-infiltration-and-runoff-volume/infiltration/scs-curve-number-loss-model - current statement of the equations, optional Ia, impervious, event-only limitation.
5. HEC-HMS TRM online, Unit Hydrograph Basic Concepts: https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/transform/unit-hydrograph-basic-concepts - assumptions and the discrete convolution.
6. HEC-HMS TRM online, ModClark Unit Hydrograph Model: https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/transform/modclark-unit-hydrograph-model - t_cell equation, per-cell reservoir, grid parameters.
7. HEC-HMS TRM online, Recession Model: https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/baseflow/recession-model - k definition, thresholds, reset, initial discharge forms.
8. HEC-HMS TRM online, Losses and Runoff Volume Basic Concepts: https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/canopy-surface-infiltration-and-runoff-volume/losses-and-runoff-volume-basic-concepts - impervious vs pervious definitions.
9. HEC-HMS TRM online, Applicability and Limitations of Transform Models, and Program Setup and Application: https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/transform/applicability-and-limitations-of-transform-models and https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/program-components/program-setup-and-application - checked: no time-step rule stated.
10. HEC-HMS User's Manual 4.14 (latest), Selecting a Loss Method: https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/latest/subbasin-elements/selecting-a-loss-method - lumped Ia as depth, gridded ratio and scale factor, impervious.
11. HEC-HMS UM latest / 4.11 / 4.8, Selecting a Transform Method: https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/latest/subbasin-elements/selecting-a-transform-method (also the /4.11/ and /4.8/ paths) - SCS PRF text, Delmarva, lag definition, Clark time-area options, variable parameter, Maricopa.
12. HEC-HMS UM latest, Selecting a Baseflow Method: https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/latest/subbasin-elements/selecting-a-baseflow-method - "None", recession parameters, bounded recession.
13. HEC-HMS UM latest, Control Specifications: https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/latest/projects-and-control-specifications/control-specifications - interval range, sub-stepping, interpolation of gage/grid data, alignment rule.
14. HEC-HMS UM latest, HEC-HMS and HEC-1 differences, Clark: https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/latest/hec-hms-and-hec-1-differences/clark-unit-hydrograph - 99.5% truncation and HMS-only rescale.
15. HEC-HMS UM latest, HEC-HMS and HEC-1 differences, Recession: https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/latest/hec-hms-and-hec-1-differences/recession-baseflow - k per day vs RTIOR per hour.
16. HEC-HMS User's Manual 4.1 (2015), PDF: http://caee.webhost.utexas.edu/prof/Maidment/CE365KSpr16/HEC/HEC-HMS_Users_Manual_4.1.pdf - pp. 66 (time interval), 198 (gridded CN), 201 (SCS CN), 207 (Clark, "diamond"), 212-213 (SCS UH), 223 (recession, no mass conservation), k = 1/RTIOR^24.
17. HEC-1 Flood Hydrograph Package User's Manual, CPD-1A, June 1998: https://www.hec.usace.army.mil/publications/ComputerProgramDocumentation/HEC-1_UsersManual_(CPD-1a).pdf - section 3.2.3 eqs 3.17-3.19, impervious RTIMP, section 3.3 eqs 3.33-3.38 (Clark discretisation, 150-ordinate stop), eqs 3.41-3.42 and the dt = 0.2 Tp / 0.25 Tp / 0.29 TLAG derivation p. 24.
18. NRCS NEH Part 630 Chapter 16 Hydrographs, March 2007: https://directives.nrcs.usda.gov/sites/default/files2/1720461096/Chapter%2016%20-%20Hydrographs.pdf - Table 16-1 (full DUH), eqs 16-1, 16-2, Table 16-5, App. 16A eqs 16A-1 to 16A-13, App. 16B provenance (gamma), D <= 0.25 Tp.
19. NRCS NEH Part 630 Chapter 10 Estimation of Direct Runoff from Storm Rainfall, July 2004: https://mail.irrigationtoolbox.com/NEH/Part630_Hydrology/H_210_630_10.pdf - eqs 10-1 to 10-13, Ia = 0.2S caveat, weighted-CN vs weighted-Q, Table 10-2 incremental runoff.

Seven distinct primary documents (sources 1, 16, 17, 18, 19 and the two online manuals of sources 2-15). The extracted text of
the five PDFs and the arithmetic script live in the session scratchpad only; nothing outside this file was written in the project.
