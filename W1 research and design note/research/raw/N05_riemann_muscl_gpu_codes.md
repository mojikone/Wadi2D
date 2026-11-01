# N05 Riemann solvers, reconstruction and time integration chosen by GPU shallow-water codes

Date: 2026-10-29

## Scope

Question answered: which approximate Riemann solver (HLLC, Roe with entropy fix, HLL, central-upwind), which MUSCL reconstruction (variables, limiter, behaviour at the dry front), which time integrator (MUSCL-Hancock, SSP-RK2, Euler, RK4) and which CFL number the production GPU shallow-water codes use, what they report on accuracy versus speed and on float32 versus float64, and what Wadi2D should adopt.

Codes covered: TRITON (Morales-Hernández et al. 2021), SERGHEI-SWE (Caviedes-Voullième et al. 2023; same scheme as TRITON), HiPIMS (Xia, Liang; read from the CUDA source), Iber+ (García-Feal et al. 2018), LISFLOOD-FP 8.0 FV1/DG2 (Shaw et al. 2021), PARFLOOD (Vacondio group, read through Ferrari et al. 2020), PRIMo (Sanders and Schubert 2019, abstract only), the Kurganov-Petrova central-upwind GPU code of Brodtkorb et al. 2012, TUFLOW HPC (Collecutt and Syme 2017; Huxley et al. 2022; TUFLOW wiki), plus independent comparison or survey papers (Ginting and Mundani 2019; Delmas and Soulaïmani 2020; Hu et al. 2022; SWEpy 2025 preprint; Villalobos et al. 2025 on SERGHEI kernels).

How it was read: 16 primary sources (papers as PDF text, source code files, official wiki and documentation pages). Three codes could not be read in full: TRITON (the OSTI manuscript exceeds the fetch size limit; abstract, documentation page and the SERGHEI description of the same scheme were used), PRIMo (paywalled; abstract only) and PARFLOOD's 2014 paper (paywalled; the group's 2020 NHESS paper describes the scheme). The web-search budget of this workflow run was exhausted after the first two rounds, so the Kurganov central-upwind review, Toro's book, Iber's reference manual and Hou et al.'s MUSCL papers were not fetched; where their content is used it is tagged [Likely] or [Guessing].

Tags: [Certain] = read in a primary source; [Likely] = strong inference or secondary description; [Guessing] = gap filled from general knowledge.

## Findings

### A. What each code chose

1. **TRITON is first-order, augmented Roe, explicit Euler, with a local implicit friction treatment.** [Certain] Quote: "time-explicit first order upwind scheme" (abstract). The documentation sets the Courant number example to 0.5 with the rule "According to the stability condition, this value should not exceed 0.5." and a wet/dry tolerance `hextra=0.001` m below which velocities are zeroed. Source: https://www.osti.gov/biblio/1783054 and https://triton.ornl.gov/documentation/

2. **SERGHEI-SWE uses the TRITON scheme: first-order upwind finite volume, augmented Riemann solver on the Roe linearisation, forward Euler.** [Certain] Quote: "SERGHEI-SWE uses a first-order accurate upwind finite-volume scheme with a forward Euler time integration" and "The numerical scheme, presented in detail in Morales-Hernández et al. (2021)". Fluxes: "augmented Riemann solvers (Murillo and García-Navarro, 2010, 2012) based on the Roe linearisation". Source: https://gmd.copernicus.org/articles/16/977/2023/

3. **SERGHEI's stated reason for first order is pragmatism at very high resolution, and it admits the cost: numerical diffusion and sub-linear convergence.** [Certain] Quotes: "first-order schemes are still a pragmatic choice (Ayog et al., 2021), especially when dealing with very high resolutions"; "a diffusive behaviour attributed to the numerical diffusion introduced by the first-order scheme"; dam-break convergence rate "below the theoretical convergence rate of R=1". Source: https://gmd.copernicus.org/articles/16/977/2023/

4. **SERGHEI/TRITON take CFL <= 0.5 with wave speeds evaluated per cell, not per edge, to save a pass.** [Certain] Quote: "the corresponding cell values are used instead for the CFL condition" and this "does not compromise the stability of the system but accelerates the computations". Source: https://gmd.copernicus.org/articles/16/977/2023/

5. **SERGHEI chose a uniform Cartesian grid explicitly for GPU memory behaviour.** [Certain] Quote: "we opt for Cartesian grids to avoid issues with memory mapping, coalescence and cache misses in GPUs". Source: https://gmd.copernicus.org/articles/16/977/2023/

6. **The augmented Roe flux kernels are about 40 % of SERGHEI's run time, the kernels are memory-bound, and the global time-step reduction is about 5 %.** [Certain] Quotes: "typically demanding around 40% of the simulation time"; "the majority of the profiled kernels are situated within the memory-bound region"; on NVIDIA at > 1e7 cells "the kernel is primarily limited by memory latency, rather than raw bandwidth" (attributed to flattened 1D indexing). Source: https://arxiv.org/abs/2511.01001

7. **HiPIMS production flood solvers are first order in the flow variables with an HLLC flux, a limited bed-gradient face reconstruction, forward Euler and a Newton-iterated implicit Manning friction; the "integrated" solver is second order (reconstructs h, eta and the velocity u, minmod-type limiter) with a two-stage Runge-Kutta.** [Certain for the code; Likely that the published HiPIMS flood results used the first-order path] Quotes from the source: `typedef double Scalar;`; `cuAdaptiveTimeControl2D time_controller(0.005, t_all, 0.5, t_current);` (Courant 0.5); dry threshold `if (h_ >= 1e-10)`; maximum step `dt_ = std::min(dt_, 60.0);`. Source: https://github.com/HEMLab/HiPIMS-CUDA (files lib/src/operators/cuda_riemann_solvers.cuh, cuda_advection_NSWEs.cu, cuda_limiter.cu, cuda_friction.cu, lib/src/utilities/cuda_adaptive_time_control.cu, lib/include/primitives/Scalar.h, apps/*/*.cu)

8. **HiPIMS's HLLC is Toro's: two-rarefaction star-state estimate, Einfeldt-type outer speeds, explicit dry-bed branches, star mass flux times the upwind tangential velocity for the shear wave.** [Certain] (formulas in the Equations section). The HLLC file also contains a Lax-Friedrichs and a George (GeoClaw-style augmented) solver, unused by the flood apps. Source: https://raw.githubusercontent.com/HEMLab/HiPIMS-CUDA/master/lib/src/operators/cuda_riemann_solvers.cuh

9. **HiPIMS reverts to first order next to thin or dry neighbours ("order reducer"): gradients are zeroed when a wet neighbour's depth is <= 0.05 times the cell's depth, or when the wet-depth ratio is <= 0.1 and the free-surface gradient is non-trivial.** [Certain] Quote (code): `ratio = fmax(0.0, fmin(1.0, ratio));` (limiter clamp). Source: https://raw.githubusercontent.com/HEMLab/HiPIMS-CUDA/master/lib/src/operators/cuda_advection_NSWEs.cu and cuda_limiter.cu

10. **The Xia-Liang friction scheme (HiPIMS lineage) is implicit and analytic, needs no iteration and leaves the CFL condition as the only time-step restriction.** [Likely] (abstract via OpenAlex; full text not accessible). Paraphrase: pairs HLLC and the surface reconstruction method with an implicit, analytically derived friction update that "requires only the CFL condition". Source: https://doi.org/10.1016/j.advwatres.2018.05.004

11. **Iber (and Iber+) use Roe first order with a second-order extension and the DHD scheme for rain; validation was run first order with a wet-dry tolerance of 0.1 mm.** [Certain] Quotes: "It implements the first order and second order extension of the upwind scheme of Roe"; tests "were run with the first order of the discretization scheme of Roe and a wet-dry tolerance of 0.0001 m". Source: https://www.mdpi.com/2073-4441/10/10/1459

12. **Iber+ runs the GPU in single precision and found no significant differences on the EA benchmark cases; the CPU code is double.** [Certain] Quote: "the GPU computations were performed in single precision because no significant differences were found in the cases analyzed"; and "double precision could be from two to more than ten times slower". Speed-ups versus single-thread Iber: 16x (Test 1), 25.7x, 39.1x and up to 94x (GTX 1080). Source: https://www.mdpi.com/2073-4441/10/10/1459

13. **LISFLOOD-FP 8.0 DG2 uses HLL fluxes, a two-stage RK2, Courant 0.33; FV1 is forward Euler at Courant 0.5 (forced by the well-balanced wet/dry treatment); ACC uses 0.7.** [Certain] Quotes: "denote HLL approximate Riemann fluxes across western, eastern, northern and southern interfaces"; "maximum stable Courant number of 0.33 (Cockburn and Shu, 2001)"; "The well-balanced wetting and drying treatment necessitates a maximum stable Courant number of 0.5". Source: https://gmd.copernicus.org/articles/14/3577/2021/

14. **LISFLOOD-DG2 switches its slope limiter off for flood cases because limiting costs 5x and floods over dry beds have no shocks to limit.** [Certain] Quotes: "can achieve a 5-fold speed-up over a standard tensor-product stencil with local slope limiting"; limiter = "generalised minmod slope limiter (Cockburn and Shu, 2001) localised by the Krivodonova shock detector". Source: https://gmd.copernicus.org/articles/14/3577/2021/

15. **LISFLOOD FV1 is "more vulnerable to grid coarsening" than DG2; DG2 on a grid 2-4x coarser matches FV1/ACC accuracy, and on EA test 4 DG2 at 10x coarser was 140x faster than FV1-CPU and 28x than FV1-GPU; GPU solvers are 2.5-4x a 16-core CPU above 1 M cells.** [Certain] Quotes: "FV1 is more vulnerable to grid coarsening since artificial discontinuities between elements tend to be enlarged"; "competitive with FV1 and ACC predictions on 2–4 times finer grids"; "2.5–4 times faster than the corresponding 16-core CPU solvers". Hardware: Tesla V100 vs 2 GHz Xeon Gold 6138. Source: https://gmd.copernicus.org/articles/14/3577/2021/

16. **LISFLOOD-FP runs in double precision, and DG2 pays a time-step penalty on thin overland flow because its friction scheme sees Gauss-point depths smaller than the cell mean.** [Certain] Quotes: "LISFLOOD-FP is configured with double precision for all calculations."; "DG2 time step size is expected to be substantially reduced compared to LISFLOOD-FV1". In the Eden catchment test DG2-GPU was "substantially slower than other solvers on the same, coarse grid". Source: https://gmd.copernicus.org/articles/14/3577/2021/

17. **PARFLOOD is HLLC with depth-positive MUSCL (minmod), second-order Runge-Kutta, Liang-Marche well-balancing with a centred bed slope, the Kurganov-Petrova velocity correction at wet/dry fronts and Caleffi's implicit friction.** [Certain, via the group's 2020 paper] Quotes: "Flux computation is performed using the HLLC approximate Riemann solver"; "depth-positive MUSCL extrapolation at cell boundaries"; "with the minmod slope limiter and the second-order Runge–Kutta method". On a Tesla P100, 1100 km2 at 5-40 m (BUQ grid, ~13 M cells), 72 h events ran in 1-5 h: "The ratio of physical time to computational time is between 15 and 80". CFL and precision are not stated. Source: https://nhess.copernicus.org/articles/20/59/2020/

18. **PRIMo is a Godunov-type scheme that is formally first order but reconstructs its fluxes with free-surface slopes on a dual grid (fine topography, coarse flow).** [Likely] (abstract paraphrase; the Riemann solver is not named in the accessible text; the Sanders group's earlier codes used Roe). Source: https://www.sciencedirect.com/science/article/abs/pii/S0309170818308698

19. **The Kurganov-Petrova central-upwind GPU code reconstructs the free surface w, hu and hv with the generalized minmod limiter (theta = 1.3), fixes positivity by altering the slope of w, desingularizes u = hu/h, and runs at CFL 1/4 with a TVD RK2.** [Certain] Quotes: "we use θ = 1.3 which is close to the optimal value"; CFL "ensures that disturbances travel at most one quarter grid cell per time step". The positivity fix has a price: "this handling of dry zones violates the well-balancedness of the scheme along the wet-dry interface". Source: https://brodtkorb.org/files/publications/brodtkorb_kp_on_gpus.pdf

20. **TUFLOW HPC is not a Riemann-solver code: upwinded face depth, a hybrid first/second-order velocity interpolation, classic RK4 in time, three control numbers; the EA tests still pass.** [Certain] Quotes: "propagated forward in time using the classic fourth order Runge-Kutta method"; "The time step was adjusted to maintain these at or below 1.0, 1.6, and 0.3 respectively." (Courant, celerity, diffusion; the current wiki gives 1.0, 1.0, 0.3). Source: Collecutt and Syme, Proc. 37th IAHR World Congress 2017, pp. 5141-5150 (PDF read; see Sources) and https://wiki.tuflow.com/HPC_Adaptive_Timestepping

### B. Riemann solvers compared

21. **At equal MUSCL/RK4 settings the central-upwind flux was 1.4x cheaper than HLLC and 1.25x cheaper than Roe with "similar accuracies"; the cost difference is branching.** [Certain] Quotes: "the central-upwind scheme was able to outperform the HLLC and Roe schemes 1.4× and 1.25×, respectively, by exhibiting similar accuracies"; "The Roe scheme needs branchings for the intermediate variables and entropy correction computations". Measured on AVX/AVX2/AVX-512 CPUs with guided vectorisation, four dam-break and tsunami cases; transfer of the ratio to a GPU is [Likely], not measured. Source: https://www.mdpi.com/2073-4441/11/4/639

22. **Roe is not positivity preserving; HLLC and central-upwind are.** [Certain] Quote: "the Roe scheme may in some cases produce negative depths" (none observed in their four cases). Source: https://www.mdpi.com/2073-4441/11/4/639

23. **HLL loses the shear (contact) wave; HLLC restores it.** [Certain] Quote: "One major flaw of the HLL scheme is related to both contact discontinuities and shear waves leading to a missing contact (middle) wave". Source: https://www.mdpi.com/2073-4441/11/4/639

24. **HLLC with Toro's dry-bed wave speeds runs stably at CFL 0.9 when the CFL length is the inscribed radius (a conservative length), first order in time (explicit Euler), unstructured triangles.** [Certain] Quote: "This is a very conservative condition and has proven to result in great stability for CFL = 0.9." Source: https://arxiv.org/abs/2010.14416

25. **Among open GPU flood codes HLLC is the majority choice (PARFLOOD, HiPIMS, B-flood, FullSWOF, HMS), augmented/plain Roe the minority (TRITON, SERGHEI, Iber), HLL/HLLE in LISFLOOD-DG2, SW2D-Lemon and GeoClaw; HEC-RAS 2D is implicit FV.** [Certain] (SWEpy Table 1, cross-checked with SERGHEI Table 1). Source: https://egusphere.copernicus.org/preprints/2025/egusphere-2025-3900/ and https://gmd.copernicus.org/articles/16/977/2023/

26. **TUFLOW's own benchmarking shows first order is not cheaper in practice and does not converge with cell size, while second order (with SGS) does.** [Certain] Quotes: "There are negligible simulation speed benefits associated with the simplier 1st Order Traditional scheme" (sic); "1st Order Traditional: Modelled water levels do not match the recorded peak flood levels well at any of the tested 2D cell resolutions". Source: Huxley, Syme, Ryan, Collecutt, HWRS 2022 (PDF read; see Sources)

### C. Reconstruction and the dry front

27. **Reconstructed variables differ by code: KP07 reconstructs free surface w and discharges; HiPIMS's second-order kernel reconstructs depth h, free surface eta and velocity u (the bed at the face follows from eta minus h, face bed = max of the two sides, depths clipped at zero); LISFLOOD-DG2 carries planar h, qx, qy and planar z; PARFLOOD uses depth-positive (Audusse-type) extrapolation.** [Certain] Quote (HiPIMS code): `Scalar z_face = fmax(_z_this, _z_neib);` and `Scalar h_L = fmax(_h_this + _z_this - z_face, 0.0);`. Sources: Brodtkorb 2012; HiPIMS cuda_advection_NSWEs.cu; LISFLOOD-FP 8.0 paper; Ferrari et al. 2020.

28. **Every second-order code read drops to first order at wet-dry edges, and one comparison paper states it as a rule.** [Certain] Quote: "it must be turned back to first-order accuracy to ensure computational stability by simply defining the edge values according to the corresponding centers". LISFLOOD switches its limiter off for flood cases; HiPIMS zeroes gradients near thin neighbours; KP07 alters the w slope. Sources: https://www.mdpi.com/2073-4441/11/4/639 ; findings 9 and 14.

29. **Plain hydrostatic reconstruction (Audusse 2004) is known to fail on steep slopes, which is exactly Wadi2D's hill case.** [Certain] Quote: "where water runs down a hill, Audusse' scheme converges slowly or fails". The HiPIMS production kernel addresses it by extrapolating the bed with a limited gradient and lowering the face bed to the wet cell's free surface when the neighbour is dry (Equations section). Source: Chen and Noelle, IGPM preprint 440, Dec 2015 (PDF read; see Sources) and HiPIMS cuda_advection_NSWEs.cu

30. **Velocity desingularization is the standard companion of float32 near the dry front.** [Certain] KP07 code: u = sqrt(2) h (hu) / sqrt(h^4 + max(h^4, kappa)), kappa = K0 max{1, min{dx, dy}}, K0 = 1e-2 in single precision ("a smaller constant for double precision"); Malpasset needed kappa = 0.40 m at dx = 15 m, chosen by experiment. Source: https://brodtkorb.org/files/publications/brodtkorb_kp_on_gpus.pdf

### D. Time integration and CFL

31. **RK2 doubles the per-step cost of Euler, and on Malpasset the first-order Euler step changed the results only marginally.** [Certain] Quotes: "running the second order accurate scheme takes twice as long as the first order scheme"; Euler versus RK2 "gives minimal changes in the results". Source: https://brodtkorb.org/files/publications/brodtkorb_kp_on_gpus.pdf

32. **Two-stage RK2 is the choice of every second-order GPU flood code read (LISFLOOD-DG2, PARFLOOD, KP07, HiPIMS integrated solver); RK4 is used by TUFLOW HPC and by Ginting's CPU code; none of the nine codes uses MUSCL-Hancock.** [Certain for what was read; the absence of MUSCL-Hancock is an observation, not a judgement on it] Sources: findings 7, 13, 17, 19, 20, 21.

33. **A higher-order reconstruction with forward Euler is unstable in long runs; the SSP integrator fixes it.** [Certain] Quotes: WENO "in combination with forward Euler integration it can develop basin-scale oscillations"; "The SSP RK4,3 integrator mitigates this instability while preserving much of WENO's accuracy". (Central-upwind on triangles; minmod with theta in [1, 2]; CFL 0.25 with Euler, 0.5 with RK.) Source: https://egusphere.copernicus.org/preprints/2025/egusphere-2025-3900/

34. **CFL numbers in production: 0.5 is the norm for explicit second-order structured codes (SERGHEI/TRITON, HiPIMS, LISFLOOD FV1, Ginting); DG2 0.33; KP07 0.25; 0.9 only with a conservative length definition (Delmas, Hu); TUFLOW runs Courant and celerity numbers to 1.0 but converges in time only at 0.8.** [Certain] Quotes: "Cr is the Courant number, which is set to 0.9" (Hu, unstructured); "time-step convergence has been achieved at Co = 0.8" (TUFLOW EA test 6a); TUFLOW wiki: "The HPC solver, by default, treats a 20% exceedance of a control number as a violation." Sources: findings 4, 7, 13, 19, 24; https://www.mdpi.com/2073-4441/14/6/922 ; https://wiki.tuflow.com/HPC_Adaptive_Timestepping

35. **Local time stepping gave up to 5x on a GPU HLLC code (up to 10x on CPU) with negligible accuracy change; GPU versus one CPU core was about 100x (Tesla K80).** [Certain] Quote: "the speed ups of GPU can be as high as a hundred, whereas those for multi-core CPU are only 2–3". Source: https://www.mdpi.com/2073-4441/14/6/922

### E. Precision

36. **Single precision was judged sufficient for the KP07 scheme on real cases, with an explicit caveat that synthetic thin-water cases break both precisions.** [Certain] Quotes: "errors caused by handling of the wet-dry interface will typically shadow the errors imposed by the use of single precision"; "it is also trivial to construct synthetic cases in which both single and double precision is insufficiently accurate". Source: https://brodtkorb.org/files/publications/brodtkorb_kp_on_gpus.pdf

37. **Every rainfall-runoff or catchment-oriented code read chose double: SERGHEI, LISFLOOD-FP, HiPIMS (typedef), Hu et al.; Hu gives the reason.** [Certain] Quote: "The present models adopted double precision because of the need to deal with complex topography, wet/dry fronts." Sources: findings 6, 7, 16; https://www.mdpi.com/2073-4441/14/6/922

38. **The precision failure mode is storing a small quantity as the difference of two large ones; the ocean GPU code of the Brodtkorb group reformulated in terms of the surface deviation to keep float32.** [Likely] (search snippet of the Tellus A 2021 paper; the PDF link redirected to a different article, so not read). This is the same principle as Wadi2D decision 3 (store depth, not level). Source: https://tellusjournal.org/articles/64 (not verified)

39. **Earlier GPU work by de la Asunción et al. reported single precision as not sufficiently accurate for a first-order Roe-type scheme, so the verdict is scheme-dependent.** [Certain, as cited] Quote: "reporting numbers indicating that single precision calculations are not sufficiently accurate". Source: https://brodtkorb.org/files/publications/brodtkorb_kp_on_gpus.pdf

### F. GPU cost structure

40. **The flux kernel dominates: 87.5 % of run time in the KP07 code (second-order, early-exit off), about 40 % in first-order SERGHEI; dry-block early exit doubled KP07 throughput (350 to 700-750 Mcells/s on a GTX 480).** [Certain] Quotes: "our flux kernel is by far most time consuming, using 87.5% of the runtime"; "peak performance of 700 to 750 megacells per second for domain sizes larger than five megacells". Sources: https://brodtkorb.org/files/publications/brodtkorb_kp_on_gpus.pdf ; https://arxiv.org/abs/2511.01001

41. **Multi-GPU HiPIMS synchronises the time step with a global minimum across domain threads and spinning barriers; SERGHEI does the same by MPI reduction and found it to be about 5 % of the time.** [Certain] Sources: HiPIMS apps/cudaMultiGPUsFloodSolver/cuda_mgpus_flood_solver.cu ; https://arxiv.org/abs/2511.01001

42. **LISFLOOD-DG2-GPU caches each face's Riemann flux in shared memory with a dimensionally split RK2 so each flux is evaluated once per block with one barrier.** [Certain] Source: https://gmd.copernicus.org/articles/14/3577/2021/ (Sect. 2.1.5)

## Equations and algorithms

Notation: h depth [m]; z bed elevation [m]; eta = z + h free surface [m]; u, v depth-averaged velocities [m/s]; qx = hu, qy = hv unit discharges [m2/s]; g gravity [m/s2]; n Manning coefficient [s/m^1/3]; dx, dy cell sizes [m]; dt time step [s]. At a face, L and R are the two sides in the face-normal frame (u normal, v tangential).

### E1. Governing system (SERGHEI Eq. 1; LISFLOOD Eq. 1-2; identical form)

dU/dt + dF/dx + dG/dy = Sr + Sb + Sf, with
U = [h, qx, qy]^T, F = [qx, qx^2/h + g h^2/2, qx qy/h]^T, G = [qy, qx qy/h, qy^2/h + g h^2/2]^T,
Sr = [ro - rf, 0, 0]^T (rain minus infiltration), Sb = [0, -g h dz/dx, -g h dz/dy]^T, Sf = [0, -sigma_x, -sigma_y]^T with the Manning friction slope sigma_x = g n^2 u sqrt(u^2+v^2) / h^(1/3) (written as C_f u sqrt(u^2+v^2), C_f = g n^2 / h^(1/3) in LISFLOOD).

### E2. Augmented Roe update (TRITON / SERGHEI, SERGHEI Eq. 2-4) [Certain]

U*_i = U^n_i - (dt/dx) sum_{k=1..4} sum_{m=1..3} [ (lambda~^- / lambda~) (lambda~ alpha~ - beta~) e~ ]^n_{m,k}
U^{n+1}_i = U*_i + (ro - rf)^n_i dt

lambda~_m, e~_m: eigenvalues and eigenvectors of the Roe-averaged Jacobian at edge k; lambda~^- = min(lambda~, 0) gives the upwind selection; alpha~_m: wave strengths from the jump dU = sum alpha~_m e~_m; beta~_m: strengths of the bed-slope and friction source terms projected on the same eigenvectors (T . n_k = P~ B~, Villalobos et al. Eq. 6-7). The source terms therefore enter the fluxes themselves ("upwind friction discretisation"), which is what makes the scheme well-balanced and depth-positive without a separate reconstruction. Time step:

dt = CFL min_i [ dx / (|qx/h|_i + sqrt(g h_i)), dx / (|qy/h|_i + sqrt(g h_i)) ], CFL <= 0.5, with cell (not edge) wave speeds.

### E3. HLLC flux as implemented in HiPIMS (Toro 2001 form) [Certain from the code]

Dry threshold h_small = 1e-10 (double precision). If h_K <= h_small then u_K = v_K = 0. Both sides dry: zero flux.

a_L = sqrt(g h_L), a_R = sqrt(g h_R)
h* = (1/g) [ (a_L + a_R)/2 + (u_L - u_R)/4 ]^2          (two-rarefaction estimate)
u* = (u_L + u_R)/2 + a_L - a_R,  a* = sqrt(g h*)
s_L = u_R - 2 a_R                      if h_L <= h_small (left dry)
    = min(u_L - a_L, u* - a*)          otherwise
s_R = u_L + 2 a_L                      if h_R <= h_small (right dry)
    = max(u_R + a_R, u* + a*)          otherwise
s_M = [ s_L h_R (u_R - s_R) - s_R h_L (u_L - s_L) ] / [ h_R (u_R - s_R) - h_L (u_L - s_L) ]
F_K = [ h_K u_K, h_K u_K^2 + g h_K^2 / 2, h_K u_K v_K ]^T, K = L, R
Star (HLL) fluxes for mass and normal momentum:
F*_1 = [ s_R F_L1 - s_L F_R1 + s_L s_R (h_R - h_L) ] / (s_R - s_L)
F*_2 = [ s_R F_L2 - s_L F_R2 + s_L s_R (q_R - q_L) ] / (s_R - s_L)
Selection: 0 <= s_L: F_L; s_L <= 0 <= s_M: (F*_1, F*_2, F*_1 v_L); s_M <= 0 <= s_R: (F*_1, F*_2, F*_1 v_R); s_R <= 0: F_R.

Delmas and Soulaïmani write the same solver with Toro's depth-ratio speeds s_L = u_L - a_L p_L, s_R = u_R + a_R p_R, where p_K = sqrt( h* (h* + h_K) / 2 ) / h_K if h* > h_K (shock side) and p_K = 1 otherwise [Certain for the shock/rarefaction logic; the extracted text of p_K is garbled, the standard Toro form is given here, Likely], with h* chosen by a first guess h*_0 = (h_L + h_R)/2 - (u_R - u_L)(h_L + h_R) / (4 (a_R + a_L)); if h*_0 <= min(h_L, h_R) use the two-rarefaction h* above, else the two-shock h* = (h_L g_L + h_R g_R + u_L - u_R)/(g_L + g_R) with g_K = sqrt( g (h*_0 + h_K) / (2 h*_0 h_K) ). Dry-bed cases: h_L = 0: s_L = u_R - 2 a_R, s_R = u_R + a_R, s* = s_L; h_R = 0: s_L = u_L - a_L, s_R = u_L + 2 a_L, s* = s_R.

HLL flux (Delmas Eq. 17-18; LISFLOOD uses the same): F_HLL = F_L if s_L >= 0; F_R if s_R <= 0; otherwise [ s_R F_L - s_L F_R + s_R s_L (U_R - U_L) ] / (s_R - s_L). HLLC differs only in the tangential component (finding 23).

### E4. Central-upwind (Kurganov-Petrova 2007) reconstruction and desingularization, as coded by Brodtkorb [Certain]

Variables Q = (w, hu, hv) with w = h + B, B the bed (piecewise bilinear from the corner values). Slopes by the generalized minmod limiter:
Q_x = MM(theta f, c, theta b), MM(a, b, c) = min(a, b, c) if all > 0; max(a, b, c) if all < 0; 0 otherwise; f, c, b forward, central, backward differences; theta = 1.3 (theta = 1 is minmod, theta = 2 the least dissipative).
Positivity: where the reconstructed h at an integration point is negative, the slope of w is altered so that h >= 0 (this limits the scheme to second order and breaks exact well-balance at the shore).
Desingularized velocity for h < kappa: u = sqrt(2) h (hu) / sqrt( h^4 + max(h^4, kappa) ), kappa = K0 max{1, min{dx, dy}}, K0 = 1e-2 (single precision); depths below eps_m (near machine epsilon) are set to zero.
Time step: dt <= (1/4) min{ dx / max|u +- sqrt(gh)|, dy / max|v +- sqrt(gh)| }.
TVD RK2: Q* = Q^n + dt R(Q^n); Q^{n+1} = Q^n/2 + (Q* + dt R(Q*))/2. Friction semi-implicit: H_f(Q*) ~ Q* H~_f(Q^n).

### E5. HiPIMS face reconstruction [Certain from the code]

Second-order kernel (cuAdvectionNSWEs2nd..., d = vector from cell centroid to face centroid):
_h = h + grad h . d; _eta = eta + grad eta . d; _z = _eta - _h; _u = u + grad u . d (velocity, not discharge, is reconstructed)
z_face = max(_z_this, _z_neib); h_L = max(_eta_this - z_face, 0); h_R = max(_eta_neib - z_face, 0)
Riemann states (h_L, h_R; h_L u_L, h_R u_R) in the face frame -> HLLC (E3)
Momentum balance adds the bed/pressure term _z_flux = -(1/2) g_face h_L^2 n + (1/2) g_this (_eta_this - z_this)^2 n (the hydrostatic-reconstruction correction that keeps a lake at rest).
Limiter (Cartesian): per neighbour r = clamp( (phi_neib - phi_this) / (grad phi . d_neib), 0, 1 ); the x gradient is scaled by the minimum r over the two x-neighbours, likewise y; the limiter returns 1 if |downwind| <= 1e-10. Order reducer before the kernel: gradients set to zero when a wet neighbour has h_neib <= 0.05 h_this, or when the wet-depth ratio on an axis is <= 0.1 and |grad eta|^2 >= 1e-10.
Time stepping (integrated solver): stage 1 Euler to the intermediate state, stage 2 recomputes gradients, limiters and fluxes, then averages the two advection terms over dt/2 each (Heun RK2) [Likely that this is intended as the published two-stage RK]; depth zeroed below 1e-10, momentum zeroed below 1e-6.

First-order production kernel (cuAdvectionMSWEsCartesian; h, hU piecewise constant; z extrapolated with a limited z gradient over a half cell, area = sqrt(volume)):
_z_this = z_this + grad z_this . (0.5 n area); _z_neib likewise with -0.5 n area
z_f = max(z_this, z_neib); dz_clip = _z_neib - _z_this (0 at boundaries); dz = z_neib - z_this - dz_clip
deta_this = max(0, min(dz, eta_neib - eta_this)); deta_neib = max(0, min(-dz, eta_this - eta_neib))
eta_L = eta_this + deta_this; eta_R = eta_neib + deta_neib; h_L = max(0, eta_L - z_f); h_R = max(0, eta_R - z_f)
Dry neighbour (h_neib < h_small): z_f <- z_f - max(0, z_f - eta_this); wet neighbour: z_f <- z_f - max(0, min(dz_clip, z_f - eta_this))
Bed term: _z_flux = (1/2) g (h_L + h_this)(z_f - z_this) n; flux = HLLC(h_L, h_R, h_L u_L, h_R u_R).
This is the practical content of the "surface reconstruction method" of Xia et al. 2017 [Likely]: a dry higher neighbour acts as a wall only up to the wet cell's free surface, so water on a hill keeps its gravity force.

### E6. Friction

Liang-Marche split implicit (LISFLOOD Eq. 11-13; same formula appears in HiPIMS's point-implicit kernel) [Certain]:
q_fx = qx + dt S_fx / D_x, D_x = 1 + (dt C_f / h) (2 u^2 + v^2) / sqrt(u^2 + v^2), S_fx = -C_f u sqrt(u^2 + v^2), C_f = g n^2 / h^(1/3); D_y with (u^2 + 2 v^2). The scheme "limit[s] the frictional force to prevent unphysical flow reversal" (LISFLOOD).
HiPIMS iterative fully implicit (active in the flood apps): U_{k+1} = U_k + J^{-1} [ dt (S_b - C_f |U_k| U_k) - U_k + U ], C_f = g n^2 h^(-4/3) on velocity, tolerance 1e-3, at most 10 iterations.
TUFLOW HPC implicit friction (Collecutt and Syme Eq. 4): u' = (u + dt u_dot) / (1 + a sqrt(u'^2 + v'^2)), a = dt g n^2 / h^(4/3), solved iteratively for u', v' with the other forcings frozen.

### E7. Time integrators and CFL

Heun / TVD RK2 (LISFLOOD Eq. 8; Brodtkorb Eq. 7): U_int = U^n + dt L(U^n); U^{n+1} = (1/2)[ U^n + U_int + dt L(U_int) ]. Two flux evaluations per step; cost 2x Euler (finding 31).
Low-storage RK4 (Ginting Eq. 6): W_p = W_0 + alpha_p [ -(dt/A) sum_faces (F n_x + G n_y) dL + dt (Sb + Sf) ]_{p-1}, alpha = 1/4, 1/3, 1/2, 1, p = 1..4; four flux evaluations per step. TUFLOW uses the classic RK4 (also four).
MUSCL-Hancock [Likely; standard form, not read in these sources]: half-step predictor per cell U^{n+1/2}_{i,L/R} = U^n_{i,L/R} - (dt / 2 dx)[ F(U^n_{i,R}) - F(U^n_{i,L}) ] + (dt/2) S_i using the cell's own reconstructed face states (no neighbour data), then one Riemann flux per face with the half-step states. One flux evaluation per step and no halo exchange inside the step; none of the nine codes read uses it.
LISFLOOD-DG2 operator (Eq. 9a, 9b): L0 = -[ (F~E - F~W)/dx + (G~N - G~S)/dy ] + [0, 2 sqrt(3) g h0 z_1x / dx, 2 sqrt(3) g h0 z_1y / dy]^T; L1x = -(sqrt(3)/dx)[ F~W + F~E - F(U^Gx1) - F(U^Gx2) ] + [0, 2 g h_1x z_1x, 0]^T, with face values U^W/E = U0 -+ sqrt(3) U_1x and Gauss values U^Gx1/Gx2 = U0 -+ U_1x; the overlined terms are the well-balancing/non-negativity modifications of Kesserwani et al. 2018.

CFL formulas in use: SERGHEI (E2, cell speeds, <= 0.5); HiPIMS dt_i = C min( sqrt(A_i)/(sqrt(g h_i)+|u_i|), sqrt(A_i)/(sqrt(g h_i)+|v_i|) ), C = 0.5, dry cells (h < 1e-10) excluded, dt <= 60 s, no growth limit; Delmas CFL = dt max( sqrt(gh) + sqrt(u^2+v^2) ) / R_L with R_L the inscribed-circle radius, CFL = 0.9; Hu dt_i = Cr R_mi / ( sqrt(u_i^2+v_i^2) + sqrt(g h_i) ), Cr = 0.9, R_mi the minimum centroid-to-face distance, h_thr = 1e-6 m; TUFLOW N_u = max(|u| dt/dx, |v| dt/dy) <= 1.0, N_c = max( sqrt(gh) dt/dx, sqrt(gh) dt/dy ) <= 1.0 (1.6 in the 2017 paper), N_d = max( nu_T dt/dx^2, nu_T dt/dy^2 ) <= 0.3, with a 20 % exceedance tolerance, retained-step rollback and halving on NaN or violation, stop after 10 consecutive repeats.

TUFLOW HPC second-order face velocity (Collecutt and Syme Eq. 7): u_face = (1 - xi) u_n1 + xi u_cc, xi = 2 x (1 - x), x = (u_n1 - u_11)/(u_cc - u_11) clamped to [0, 1], where n1 is the upwind cell and 11 the cell beyond it; pure second order when the profile is linear, pure upwind when it reverses.

## Numbers

| Value | Context | Source |
|---|---|---|
| CFL <= 0.5, cell-based wave speeds | SERGHEI/TRITON first-order augmented Roe, Euler | SERGHEI GMD 2023 Eq. 4; TRITON docs |
| Courant 0.5; dt <= 60 s; h_dry = 1e-10; momentum zeroed below 1e-6 (integrated solver) | HiPIMS-CUDA | HiPIMS source |
| Courant 0.33 (DG2), 0.5 (FV1), 0.7 (ACC) | LISFLOOD-FP 8.0 | Shaw et al. 2021 |
| CFL 1/4 | Kurganov-Petrova central-upwind, RK2 | Brodtkorb 2012 Eq. 8 |
| CFL <= 0.5 (constant dt) | Roe/HLLC/CU with MUSCL minmod + RK4 | Ginting and Mundani 2019 |
| CFL 0.9 with inscribed-radius length | HLLC, Euler, triangles | Delmas and Soulaïmani 2020 |
| Cr 0.9 with min centroid-face distance; h_thr 1e-6 m | HLLC unstructured + LTS | Hu et al. 2022 |
| CFL 0.25 (Euler) / 0.5 (SSP RK(4,3)); recommended <= 1/3 | central-upwind on triangles | SWEpy 2025 |
| N_u <= 1.0, N_c <= 1.0 (1.6 in 2017), N_d <= 0.3; converged at 0.8 of targets; 20 % exceedance tolerated | TUFLOW HPC RK4 | Collecutt and Syme 2017; TUFLOW wiki |
| theta = 1.3 | generalized minmod parameter, KP07 | Brodtkorb 2012 |
| K0 = 1e-2 (single precision); kappa = 0.40 m at dx = 15 m for Malpasset | velocity desingularization | Brodtkorb 2012 |
| wet-dry tolerance 0.0001 m | Iber+ validation | García-Feal et al. 2018 |
| hextra = 0.001 m | TRITON velocity-zeroing tolerance (example) | TRITON docs |
| order reducer: h_neib <= 0.05 h_this; depth ratio <= 0.1 with grad-eta^2 >= 1e-10 | HiPIMS second-order kernel | HiPIMS source |
| CU 1.4x faster than HLLC, 1.25x than Roe; 1.31x / 1.26x without vectorisation | edge-driven level, AVX/AVX2/AVX-512 CPUs | Ginting and Mundani 2019 |
| 5x | cost of local slope limiting (tensor-product stencil) vs slope-decoupled no-limiter DG2 | Shaw et al. 2021 |
| RK2 = 2x Euler per step | KP07 GPU | Brodtkorb 2012 |
| 87.5 % of run time in the flux kernel; 12 % time integration | KP07, 4000x4000, RK2, no early exit | Brodtkorb 2012 |
| ~40 % of run time in the two flux kernels; ~5 % in the time-step reduction | SERGHEI first order | Villalobos et al. 2025 |
| 350 Mcells/s -> 700-750 Mcells/s with dry-block early exit | KP07 on GeForce GTX 480, single precision | Brodtkorb 2012 |
| DG2 at 2-4x coarser grid = FV1/ACC accuracy; DG2 at 10x coarser 140x faster than FV1-CPU, 28x than FV1-GPU (EA test 4) | LISFLOOD-FP 8.0 | Shaw et al. 2021 |
| GPU 2.5-4x a 16-core Xeon Gold 6138 above 1e6 elements (V100) | LISFLOOD DG2/FV1 | Shaw et al. 2021 |
| GPU speed-up vs a 48-core node: 6.5x A100, 3.4x V100, 2.2x RTX 3070 (Malpasset 10 m) | SERGHEI | Caviedes-Voullième et al. 2023 |
| 16x, 25.7x, 39.1x, 94x vs single-thread Iber (GTX 1080); single precision | Iber+ | García-Feal et al. 2018 |
| ~100x vs one CPU core (Tesla K80); LTS +5x on GPU, +10x on CPU | HLLC unstructured | Hu et al. 2022 |
| 13x (minmod+Euler) and 20.8x (WENO+SSPRK) vs serial CPU on a GTX 1650 | SWEpy | SWEpy 2025 |
| physical/compute time ratio 15-80; 1100 km2, 13 M cells, 72 h in 1-5 h (Tesla P100) | PARFLOOD BUQ grid | Ferrari et al. 2020 |
| first order needs re-tuning per cell size; second order + SGS converged at 50 m, second order at 30 m; speed "comparable" | TUFLOW HPC case studies | Huxley et al. HWRS 2022 |
| double precision | SERGHEI, LISFLOOD-FP, HiPIMS, Hu et al. | respective papers / source |
| single precision (GPU) | Iber+, Brodtkorb KP07 | respective papers |

## Recommendation for Wadi2D

1. **Riemann solver: HLLC in Toro's form (E3), with the two-rarefaction star estimate, Einfeldt-type outer speeds and explicit dry-bed branches.** It is positivity preserving (finding 22), keeps the shear wave that braided-channel splits and fan avulsions depend on (finding 23), is the majority choice of the open GPU flood codes (finding 25), and its wet/dry behaviour is documented in code that can be copied (HiPIMS, GPLv3; Wadi2D's licence choice must stay compatible or the code must be re-written from the formulas). Reject Roe with entropy fix: more branches, not positivity preserving, no accuracy gain (findings 21-22); the augmented Roe of TRITON/SERGHEI is attractive only as a first-order scheme, which is rejected below. Reject plain HLL for the production flux (finding 23); keep it as a one-line fallback for faces where the star-speed denominator in s_M vanishes. Keep the Kurganov-Petrova central-upwind flux as the one benchmark alternative in the stack micro-benchmark: it is branch-free and 1.25-1.4x cheaper on SIMD CPUs (finding 21), proven in float32 (finding 36), but needs CFL 1/4 instead of 0.5 (twice the steps) and its positivity fix breaks well-balance at the shore (finding 19); on the RTX 5080 measure, do not argue.

2. **Spatial order: second order (MUSCL) by default, first order as a switch.** The evidence against first order as the design-flow scheme is direct: TUFLOW's own case studies show first order does not converge with cell size and saves nothing (finding 26); LISFLOOD shows FV1 needs a 2-4x finer grid (finding 15); SERGHEI admits the diffusion (finding 3). Reconstruct **eta, h and u** (HiPIMS pattern, E5): the bed at the face follows as eta - h, so a sub-grid face crest (decision 2) enters as z_face = max(crest, reconstructed beds) and water higher than the crest flows while lower water is blocked, with no separate wall logic. Reconstruct velocity, not discharge, so thin cells do not inherit large momentum gradients [Likely, HiPIMS choice]. Limiter: minmod (every code that limits uses minmod or generalized minmod); expose theta in [1, 1.5] as a tuning knob for the Block 2 benchmark (KP07 uses 1.3). Reject van Leer / MC / van Albada as defaults: no GPU flood code read uses them and the dry front needs the most dissipative choice [Likely]. At the dry front: zero the gradients of cells adjacent to dry or thin neighbours (HiPIMS thresholds in finding 9) and never limit per face with a shock detector (LISFLOOD's 5x cost, finding 14).

3. **Bed and wet/dry treatment: the HiPIMS/SRM-type face bed (E5 first-order kernel), not plain Audusse hydrostatic reconstruction.** Audusse's scheme "converges slowly or fails" when water runs downhill (finding 29) and Wadi2D's hills are that case; lowering the face bed to the wet cell's free surface when the neighbour is dry keeps the gravity force on steep slopes. Add the Kurganov-Petrova velocity desingularization (E4) only if the float32 path is kept (finding 30).

4. **Time integration: Heun SSP-RK2 at CFL 0.5 with cell-evaluated wave speeds as the reference; MUSCL-Hancock as a benchmarked option; Euler only with the first-order switch.** RK2 is what every second-order GPU flood code chose (finding 32) and it costs 2x Euler per step (finding 31), which the fluxes dominate anyway (finding 40). MUSCL-Hancock halves the flux evaluations and needs no halo exchange within the step, which favours the tiled multi-GPU design of decision 16, but no code read uses it, so it is an experiment, not the baseline. Reject RK4 (TUFLOW): four flux evaluations for no demonstrated accuracy need in these flows. Reject DG2 for the first release: better per cell but the friction time-step penalty on thin overland flow made it the slowest solver in the only catchment test read (finding 16). Local time stepping stays deferred (decision 18 already covers the steep-cell step; Hu's +5x is the upper bound to expect, finding 35).

5. **CFL and thresholds: CFL 0.5 (cell wave speeds, E7), a dry threshold of 1e-6 m for velocity zeroing in float32 (HiPIMS's 1e-10 is a double-precision value), a maximum step (HiPIMS: 60 s) and a step-growth limit; roll back and halve on NaN like TUFLOW (finding 34).** Expect time-step convergence to need a lower effective Courant number (TUFLOW: 0.8 of target) and test it on the Block 2 wadi head-to-head run (decision 12).

6. **Friction: point-implicit Liang-Marche form (E6) applied after the flux update, with the flow-reversal limiter; the analytic fully implicit scheme of Xia and Liang 2018 is the upgrade if thin-flow time steps collapse (finding 10, not read in full).** This is what LISFLOOD, HiPIMS, PARFLOOD (Caleffi variant) and TUFLOW all do in one form or another.

7. **Precision: float32 state and fluxes with float64 reductions and a compile-time Scalar switch, validated early on the Block 2 hills.** The float32 verdict is scheme-dependent (findings 12, 36, 37, 39): it held for a second-order scheme that stores the free surface with desingularized velocities and for Iber+ on the EA tests, but every catchment rainfall-runoff code chose double. Decision 3 (store depth) removes the large-minus-large failure mode (finding 38) but the thin-rain case (0.056 mm per step) is exactly the "synthetic case" Brodtkorb warns about, so the benchmark must include it. Keep eta = z + h out of stored state; compute it where needed with a cell-local datum, and do the mass-balance and dt reductions in float64.

8. **Kernel design follows the cost structure, not the flux algebra:** the flux kernel is 40-88 % of run time and memory-bound (findings 6, 40); use SERGHEI's finding that flattened 1D indexing hit memory latency on NVIDIA at > 1e7 cells, LISFLOOD's shared-memory flux caching with one barrier (finding 42) and KP07's dry-block early exit (2x on Malpasset-type domains, finding 40) from the first prototype.

## Open issues

- TRITON's full text was not read (fetch size limit): whether its augmented Roe uses an entropy fix, how `hextra` interacts with the flux, and whether the code offers a float32 build are unknown. [Gap]
- PRIMo's Riemann solver and its free-surface-slope flux reconstruction are known only from the abstract; the dual-grid idea (fine topography, coarse flow) is close to Wadi2D's sub-grid faces and deserves a full read when access exists. [Gap]
- PARFLOOD's CFL number and precision are not stated in the accessible paper; Vacondio et al. 2014 and Dazzi et al. 2018 (LTS) are paywalled. [Gap]
- Xia et al. 2017 (SRM equations) was read only through the HiPIMS code and the abstract; the published equations may differ in the wet-neighbour branch. [Gap]
- No source read measures MUSCL-Hancock against SSP-RK2 on a GPU; the single-flux-evaluation argument is theoretical here. [Gap, benchmark item]
- No head-to-head float32 vs float64 study exists for a steep-catchment rain-on-grid case; the only quantitative precision statements are from a flat-ish dam-break/coastal scheme (KP07) and EA benchmark tests (Iber+). [Gap, benchmark item]
- The central-upwind cost advantage was measured on vectorised CPUs; its GPU advantage over HLLC (warp divergence vs branch cost) is not measured in the sources read. [Gap, benchmark item]
- How HLLC wave speeds should use sub-grid face tables (which depth defines a_L, a_R on a partially wet face) has no precedent in the codes read; TUFLOW HPC's SGS scheme is not a Riemann solver and HEC-RAS 2D is implicit. [Design question for the sub-grid topics]
- Iber's default CFL (reportedly 0.45) and its second-order limiter were not read; the Iber reference manual was not fetched. [Guessing]
- HiPIMS's time-step reduction kernel has an apparent bug (second-stage reduction only reads 256 block results); do not copy the reduction code, only the per-cell formula.

## Sources

1. https://gmd.copernicus.org/articles/16/977/2023/ — Caviedes-Voullième et al. 2023, SERGHEI-SWE v1.0 (GMD), read in full (HTML and PDF text): scheme Eq. 1-4, justification of first order and Cartesian grids, precision, test cases, GPU speed-ups, solver survey Table 1.
2. https://arxiv.org/abs/2511.01001 — Villalobos, Caviedes-Voullième, Rizzi, Meneses 2025, cross-architecture evaluation of SERGHEI-SWE (HTML and PDF text): kernel cost shares, roofline, NVIDIA memory-latency drop, portability metrics, time-step reduction cost.
3. https://www.osti.gov/biblio/1783054 and https://triton.ornl.gov/documentation/ — TRITON abstract (Morales-Hernández et al. 2021, EMS 141, 105034) and configuration documentation (courant, hextra); full manuscript not read (fetch size limit).
4. https://github.com/HEMLab/HiPIMS-CUDA — HiPIMS-CUDA source (GPLv3): cuda_riemann_solvers.cuh (HLLC formulas), cuda_advection_NSWEs.cu (face reconstruction, order reducer, bed term), cuda_limiter.cu, cuda_friction.cu, cuda_adaptive_time_control.cu, Scalar.h, cuda_integrators.h, the three solver apps (time loops, Courant 0.5, thresholds, multi-GPU reduction).
5. https://doi.org/10.1016/j.advwatres.2018.05.004 (abstract via https://api.openalex.org) — Xia and Liang 2018, implicit friction scheme; abstract only.
6. https://doi.org/10.1002/2016WR020055 (abstract via OpenAlex) — Xia, Liang, Ming, Hou 2017, surface reconstruction method; abstract only (Wiley and repository copies refused the fetch).
7. https://www.mdpi.com/2073-4441/10/10/1459 — García-Feal et al. 2018, Iber+ (PDF text via the MDPI CDN): Roe first/second order, DHD, wet-dry tolerance, single precision on GPU, speed-ups and hardware.
8. https://gmd.copernicus.org/articles/14/3577/2021/ — Shaw et al. 2021, LISFLOOD-FP 8.0 (HTML and PDF text): DG2/FV1/ACC formulations Eq. 1-19, HLL, RK2, Courant numbers, limiter policy, friction, precision, hardware, results and conclusions.
9. https://nhess.copernicus.org/articles/20/59/2020/ — Ferrari, Dazzi, Vacondio, Mignosa 2020 (NHESS): PARFLOOD numerical model description (HLLC, depth-positive MUSCL minmod, RK2, well-balancing, KP07 wet/dry correction, implicit friction), BUQ grid, P100 run times.
10. https://www.sciencedirect.com/science/article/abs/pii/S0309170818308698 — Sanders and Schubert 2019, PRIMo (AWR 126, 79-95); abstract fragments only (page refused the fetch; Crossref/OpenAlex carry no abstract).
11. https://brodtkorb.org/files/publications/brodtkorb_kp_on_gpus.pdf — Brodtkorb, Sætra, Altinakar 2012 (Computers & Fluids), Kurganov-Petrova on GPUs (PDF text): reconstruction, limiter theta, positivity fix, desingularization, CFL 1/4, RK2 vs Euler, single precision, early exit, throughput, kernel profile.
12. https://www.mdpi.com/2073-4441/11/4/639 — Ginting and Mundani 2019 (Water), Roe vs HLLC vs central-upwind with MUSCL minmod and RK4 (PDF text): cost ratios, branching, positivity, first order at wet-dry edges, CFL.
13. https://arxiv.org/abs/2010.14416 — Delmas and Soulaïmani 2020, multi-GPU HLLC solver (PDF text): HLL/HLLC flux and Toro wave-speed formulas with dry-bed cases, explicit Euler, CFL 0.9 definition, hardware.
14. https://www.mdpi.com/2073-4441/14/6/922 — Hu et al. 2022 (Water), GPU + local time stepping HLLC model (PDF text): scheme, Courant 0.9, h_thr, double precision rationale, speed-ups.
15. https://egusphere.copernicus.org/preprints/2025/egusphere-2025-3900/ — SWEpy preprint 2025 (PDF text): central-upwind on triangles, minmod theta, WENO, Euler vs SSP RK, CFL values, GPU speed-ups, Table 1 survey of existing solvers.
16. Collecutt and Syme 2017, "Experimental benchmarking of mesh size and time-step convergence for a 1st and 2nd order SWE finite volume scheme", Proc. 37th IAHR World Congress, Kuala Lumpur, pp. 5141-5150 — PDF read from this session's download folder (original URL not recorded; the paper is distributed on tuflow.com): TUFLOW HPC scheme, RK4, control numbers, 1st vs 2nd order, time-step convergence at 0.8.
17. Huxley, Syme, Ryan, Collecutt 2022, "Hydraulic Modelling 2D Cell Size Result Convergence – Comparing the Performance of Different Shallow Water Equation Solution Schemes", HWRS 2022 (ISBN 978-1-925627-64-0) — PDF read from this session's download folder: 1st order vs 2nd order vs 2nd order SGS convergence and speed.
18. https://wiki.tuflow.com/HPC_Adaptive_Timestepping — TUFLOW wiki: control numbers 1.0/1.0/0.3, 20 % exceedance rule, rollback and repeat logic, Control Number Factor 0.8.
19. Chen and Noelle 2015, "A new hydrostatic reconstruction scheme motivated by the wet-dry front", IGPM preprint 440, RWTH Aachen (later J. Comput. Phys. 2017) — PDF read from this session's download folder: failure of Audusse hydrostatic reconstruction on downhill flow.
20. https://tellusjournal.org/articles/64 — Brodtkorb and Holm, Tellus A 2021, coastal ocean forecasting on the GPU; cited for the surface-elevation reformulation argument from a search snippet only (the PDF link resolved to a different article); [Likely].
