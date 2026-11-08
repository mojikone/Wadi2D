# Face depth on sloping cells: published treatments in staggered and sub-grid shallow-water schemes

Reading status used below: [full] = full text read (relevant sections at least); [manual] = official manual sections read; [code] = source code read; [abstract] = abstract or metadata only; [secondary] = reported by another paper, original not read. Equations are transcribed from PDF text extraction; where the layout was garbled this is said.

Context arithmetic used throughout (not from a source): with the level held at eta_U and the face invert about S dx/2 below the upwind cell's bed, the face depth exceeds the true one by S dx/2 = 0.10 m at dx = 20 m and S = 1 %. In uniform flow the cell then settles at h_n - S dx/2, so a 3.4 % low depth implies h_n of about 2.9 m. That is consistent with a pure first-order offset of S dx/2 in the face depth.

## 1. Stelling and Duinmeijer 2003, Kramer and Stelling 2008: which face depth, what order, what about slopes

### Takeaway
The Stelling-Duinmeijer "flooding scheme" takes the flow-through height at a velocity point from the upwind water level. The bed is a staircase whose face value is the higher of the two cell beds. On a downslope this makes the face depth the upwind cell's own depth, not the upwind level over a lower face invert. The scheme's second order and minmod limiting apply to momentum advection, not to the continuity depth. The only depth limiter it documents is a critical-depth cap for flow up a step. Neither paper's full text was reachable, and neither abstract says anything about deep flow on a uniform slope.

### Cited Findings
- [abstract] Stelling and Duinmeijer (2003) build on classical staggered grids and implicit integration, for hydraulic jumps, bores and inundation past road banks. They use a momentum-consistent approximation in expansions and a Bernoulli-consistent one in contractions. Both converge to the same solution when the flow is smooth. The abstract says nothing about face depth or slopes. — [Stelling and Duinmeijer 2003, IJNMF 43, doi:10.1002/fld.537](https://doi.org/10.1002/fld.537); abstract via [OpenAlex](https://api.openalex.org/works/doi:10.1002/fld.537)
- [abstract] Kramer and Stelling (2008) is a semi-implicit staggered finite-volume scheme on unstructured meshes. It conserves momentum locally or, by choice, keeps energy head constant along a streamline, through a special interpolation and momentum control volumes. Advection is locally implicit to escape the Courant limit, and the pressure gradient needs an orthogonal grid. The abstract says nothing about face depth or slopes. — [Kramer and Stelling 2008, IJNMF 58, doi:10.1002/fld.1722](https://doi.org/10.1002/fld.1722)
- [manual] Delft3D-FLOW's "Flooding scheme" is documented as the Stelling and Duinmeijer (2003) scheme. Its bottom is a staircase of tiles centred on the water-level points (DPUOPT=MIN), and its flow-through height at a U-point is always based on an upwind water level. Its approximations are second order but drop to first order near extrema through a minmod slope limiter; the text attaches this to the advection approximations. — [Delft3D-FLOW User Manual, sections 10.5.1 and 10.8.2](https://content.oss.deltares.nl/delft3d4/Delft3D-FLOW_User_Manual.pdf)
- [manual] Delft3D-FLOW defines the total depth at a U-point (eq. 10.63) as H^U_{m,n} = d̄^U + ζ̄^U. d is depth below datum, positive down, and ζ̄ defaults to ½(ζ_{m,n} + ζ_{m+1,n}). The bed option DPUOPT has three settings:
  - MEAN: average of the vertex depths;
  - MIN: d̄ = min(d_{m,n}, d_{m+1,n}), the shallower depth, i.e. the higher bed;
  - UPW: d̄ = d_{m,n} if U > 0, d_{m+1,n} if U < 0, and min(d_{m,n}, d_{m+1,n}) if U = 0.

  With DPUOPT = UPW, a hydraulic structure or the Z-model (eq. 10.64), the water level is taken upwind too: H^U = d̄^U + ζ_{m,n} for U > 0, d̄^U + ζ_{m+1,n} for U < 0, and d̄^U + max(ζ_{m,n}, ζ_{m+1,n}) for U = 0. — [Delft3D-FLOW User Manual §10.8.2](https://content.oss.deltares.nl/delft3d4/Delft3D-FLOW_User_Manual.pdf)
- [manual] Delft3D-FLOW states both sides of the trade-off.
  - Averaging the level near steep bottom gradients sets velocity points dry too early and leaves water stranded on tidal flats, which artificially raises storage.
  - Upwinding the level raises the discharge, because the upwind level is generally above the average, so the flow area is larger.
  - The upwind choice is less realistic when the flow runs against the level gradient (wind-driven flow).

  The upwind approach is attributed to Stelling (1984). — [Delft3D-FLOW User Manual §10.8.2](https://content.oss.deltares.nl/delft3d4/Delft3D-FLOW_User_Manual.pdf)
- [manual] Flooding scheme, critical-flow limiter for steep bed steps (eq. 10.65; the min/max layout was garbled in extraction and reconstructed): if U_{m,n} > 0 and d_{m,n} > d_{m+1,n} + DGCUNI, i.e. the downstream bed is higher by more than a threshold, then H^U_{m,n} = min[ H^U_{m,n}, max( (2/3) H_{m,n}, H_{m+1,n} ) ]. The U < 0 case is mirrored. The manual presents it as improving the critical discharge for flow with steep bed slopes. It acts only where the bed rises in the flow direction. — [Delft3D-FLOW User Manual §10.8.2](https://content.oss.deltares.nl/delft3d4/Delft3D-FLOW_User_Manual.pdf)
- [manual] For rapidly varying flow the manual says the depth at velocity points may be discontinuous. Slope limiters keep the local depths accurate and positive, which needs a local linearisation of the continuity equation (eq. 10.17), and this is less stable in shallow areas. — [Delft3D-FLOW User Manual §10.4](https://content.oss.deltares.nl/delft3d4/Delft3D-FLOW_User_Manual.pdf)
- [manual] Delft3D-FLOW's optional "Slope Limiter" (SlpLim, Appendix B.27) targets rain on steep dry banks. When a cell's level is below the higher of the two beds, the pressure gradient is corrected with the high-lying cell's bed: dpdx = dpdx − g (s0 − dpsmax)/dxu. This is a gradient limiter for dry, high cells. It is not a face-depth correction for deep flow on a slope. — [Delft3D-FLOW User Manual App. B.27](https://content.oss.deltares.nl/delft3d4/Delft3D-FLOW_User_Manual.pdf)

### Inferences
- [Likely] With DPUOPT=MIN and the upwind level, the Delft3D/Stelling-Duinmeijer face depth for downhill flow is ζ_U minus the higher bed (the upwind bed), which is h_U. That is exact for uniform flow on a uniform slope in a non-sub-grid model.
  - The Wadi2D read, upwind level over the face's own lowest invert, corresponds instead to D-Flow FM's hu = ζ_U − min(bl1, bl2) (section 2).
  - It also corresponds to a sub-grid face table whose invert sits below the upwind cell's bed.
  - The documented Delft3D choice is therefore not the one that produced the 2.5 to 9 % storage loss.
- [Likely] In this school, the "second order" lives in momentum advection (minmod, expansion/contraction switch). The continuity depth stays first-order upwind, with the critical-depth cap as its only depth limiter, and that cap fires only on upward steps.

### Gaps
- The full texts of Stelling and Duinmeijer (2003) and Kramer and Stelling (2008) were not reachable (Wiley paywall; the TU Delft repository refused connections from this machine). Their own statement of the face-depth order and any remark on slopes are unverified. What is reported above comes through the Delft3D-FLOW manual's account of the Flooding scheme.

## 2. Second-order staggered schemes: how the face depth is reconstructed (Herbin-Latché group, Doyen-Gunawan, Zijlema; D-Flow FM in production)

### Takeaway
Several staggered sources give an upwind-biased, limited reconstruction of the continuity face value.
- Herbin and co-workers do it on the depth h, with positivity proved under a CFL condition half that of upwind and the lake at rest kept by a centred h in the pressure-bathymetry term.
- D-Flow FM (Deltares) ships it on the face water level as option `Limtyphu` (minmod, van Leer, Koren, MC), default 0 = first-order upwind. Its 2027.01 technical manual says higher order is not available "regardless of limtyphu", while the current source code implements it.
- Zijlema/SWASH keep continuity first-order upwind and put the second order in momentum advection as a limited deferred correction.

None of these reports a MacDonald or uniform-slope test of the face-depth reconstruction itself.

### Cited Findings
- [full] Zijlema writes the mass flux as q_{m+1/2} = h_{m+1/2} u_{m+1/2} (eq. 20), with the first-order upwind face depth (eq. 21): h_{m+1/2} ≈ ĥ_{m+1/2} = h_m if u_{m+1/2} > 0, h_{m+1} if u_{m+1/2} < 0. He states that it allows conditional preservation of non-negative depth.
  - He names the alternative of taking the surface elevation upwind and the bed by a min operator on depth (positive down, i.e. the higher bed). He notes it may be more accurate, particularly on coarse grids, but does not use it in the paper.
  - Non-negativity holds under a velocity Courant condition (Section 5, eq. 38).
  - Source: preprint submitted to Computers and Fluids, 14 August 2019. — [Zijlema, The role of the Rankine-Hugoniot relations in staggered finite difference schemes for the shallow water equations](https://swash.sourceforge.io/online_doc/rh.pdf)
- [full] Zijlema's momentum advection averages the mass flux to the momentum-cell face, q̄_m = ½(q_{m−1/2} + q_{m+1/2}) (eq. 23), and takes the transported velocity first-order upwind (eq. 24). Second order comes from a higher-order upwind scheme, with or without a flux limiter, applied as a deferred correction on the right-hand side; the MUSCL limiter is used in the step test (lines 609-612).
  - Steady jump conditions hold only when the depth-averaged velocity is upwinded by the mass flux. Other choices allow odd-even decoupling.
  - In the solitary-wave run-up test all schemes were first order in space. The stable maximum Courant numbers were 0.7 for Stagg(ζ,u), 0.4 for Stagg U(h,q) and 0.3 for Stagg C(h,q), the variant with a centrally defined face velocity u = q/h_{m+1/2} (eq. 33). — [Zijlema preprint](https://swash.sourceforge.io/online_doc/rh.pdf)
- [full] Herbin, Latché, Nasseri and Therme (2021; IMA J. Numer. Anal. 43(1), 2023) build a MAC staggered scheme with a "MUSCL-like" interpolation of the convection operators for water height and momentum.
  - The face height h_σ must satisfy two conditions:
    - eq. 8: h_σ = α h_K + (1 − α) h_L with α ∈ [0,1], a convex combination;
    - eq. 9: for u·n_{K,σ} ≥ 0, h_σ − h_K = β_K (h_K − h_{M_K}) with β_K ∈ [0,1] and M_K a neighbouring cell.
  - On uniform Cartesian meshes they suggest the van Leer-type form h_σ − h_K = ½ minmod( ½(h_L − h_J), β⁺(h_L − h_K), β⁻(h_K − h_J) ), with β± ∈ [0,2] and J the upstream neighbour of K. With β± = 1 this is the two-slope minmod. Quasi-second order requires β ≥ 1 − ε(M), ε → 0 as the mesh is refined.
  - In CALIF3S they use an affine interpolation h̃_σ, then h_σ − h_K = ½ minmod( 2(h̃_σ − h_K), 2(h_K − h_J) ) (eq. 10; layout partly garbled). — [Herbin et al., arXiv:2111.09726](https://arxiv.org/abs/2111.09726)
- [full] Herbin et al. take the depth in the pressure-bathymetry term as centred, h_{σ,c} = ½(h_K + h_L) (eq. 15). This makes ∇p + g h_c ∇z = 0 whenever ∇(h + z) = 0 (eq. 14), so the lake at rest is preserved. The reconstructed variable for the mass flux is the depth h, not the level. — [Herbin et al.](https://arxiv.org/abs/2111.09726)
- [full] Herbin et al., positivity (Lemma 3.1, eq. 25): h_K^{n+1} > 0 under 2Δt Σ_{σ∈E(K)} |σ| |u_σ^n·n_{K,σ}| ≤ |K|. That is half the time step allowed for upwind fluxes. Heun additionally needs the same bound with u^{n+1} (eq. 26). — [Herbin et al.](https://arxiv.org/abs/2111.09726)
- [full] Herbin et al., results:
  - Smooth travelling vortex, second-order scheme: L1 order 2 for h and 1.5 for u.
  - MUSCL with forward Euler ("segregated") is the most accurate on the coarsest mesh but oscillates and loses convergence on refinement. Heun's smoothing was needed to offset the oscillatory MUSCL.
  - 1D Riemann problem on a flat bed: h = 1 / 0.2, Δx = 1/200, Δt = Δx/10.
  - In the partly dry test the second-order scheme needed a CFL of about 1/8; the first-order upwind scheme ran with time steps four times larger.
  - No MacDonald, sloping-channel or hydraulic-jump case is reported. — [Herbin et al.](https://arxiv.org/abs/2111.09726)
- [abstract] Doyen and Gunawan (2014) use explicit upwind for mass, explicit upwind convection fluxes for momentum, and implicit centred pressure and topography fluxes. They state an explicit pressure term would not be consistent with the entropy inequality. — [Doyen and Gunawan, FVCA VII, doi:10.1007/978-3-319-05684-5_21](https://link.springer.com/chapter/10.1007/978-3-319-05684-5_21)
- [manual] D-Flow FM technical reference, version 2027.01:
  - Face depth (Algorithm 4, eq. 6.14): hu_j = ζ_{L(j)} − min(bl1_j, bl2_j) if u_j > 0 or (u_j = 0 and ζ_L > ζ_R); ζ_{R(j)} − min(bl1_j, bl2_j) otherwise.
  - bl1_j and bl2_j are the bed levels at the face's two end nodes, and hu is the maximum depth in the face.
  - Remark 6.2.2: this upwind reconstruction is first order, and higher order is not available at present whatever the value of `limtyphu`. — [D-Flow FM Technical Reference Manual 2027.01](https://content.oss.deltares.nl/delft3d/D-Flow_FM_Technical_Reference_Manual.pdf)
- [manual] The D-Flow FM user manual (2027.01) lists the MDU keyword `Limtyphu`, the limiter type for water depth in the continuity equation: 0 = none (default), 1 = minmod, 2 = van Leer, 3 = Koren, 4 = monotone central. `Limtypmom` (cell-centre advection velocity) defaults to 4. — [D-Flow FM User Manual 1D2D 2027.01](https://content.oss.deltares.nl/delft3dfm1d2d/D-Flow_FM_User_Manual_1D2D.pdf)
- [code] Current D-Flow FM source, `sethu.f90` (module m_sethu), contradicts Remark 6.2.2.
  - `set_upstream_water_level_getter(limtyphu)` selects the face level: 0 upwind, s0(up); 21 central, ½(s0(L) + s0(R)); 22 a Perot-weighted average; 23 linear interpolation; any other value the "usual limiters".
  - The "usual limiters" give upstream_water_level = s0(up) + dslim(ds1, ds2, limtyphu), with ds1 = (s0(up) − s_uu)·slnup(3) and ds2 = s0(down) − s0(up). If no upwind-upwind value exists, the upwind level is used.
  - The face depth is that level minus the face bed at the u-point.
  - Source: [sethu.f90](https://github.com/Deltares/Delft3D/blob/main/src/engines_gpl/dflowfm/packages/dflowfm_kernel/src/dflowfm_kernel/compute/sethu.f90)
- [code] Limiter definitions in D-Flow FM: `dslim` type 1 = d1·dminmod(d1,d2), with dminmod = min(1, d2/d1) if d1·d2 > 0 else 0. Type 2 = d1·dvanleer(d1,d2), with dvanleer = 2 d2/(d1 + d2) if d1·d2 > 0. Comments in both functions say the limiter is doubled to account for the face-distance factor (`acl`). `slnup(3)` = dx(L)/dxk, the link length over the distance to the upwind-upwind point, so it is 1 on a uniform grid. — [dslim.f90](https://github.com/Deltares/Delft3D/blob/main/src/engines_gpl/dflowfm/packages/dflowfm_kernel/src/dflowfm_kernel/limiters/dslim.f90), [dminmod.f90](https://github.com/Deltares/Delft3D/blob/main/src/engines_gpl/dflowfm/packages/dflowfm_kernel/src/dflowfm_kernel/limiters/dminmod.f90), [dvanleer.f90](https://github.com/Deltares/Delft3D/blob/main/src/engines_gpl/dflowfm/packages/dflowfm_kernel/src/dflowfm_kernel/limiters/dvanleer.f90), [setupwslopes.f90](https://github.com/Deltares/Delft3D/blob/main/src/engines_gpl/dflowfm/packages/dflowfm_kernel/src/dflowfm_kernel/prepost/setupwslopes.f90)

### Inferences
- [Certain, algebra] The centred face value of the earlier Wadi2D test violates Herbin's condition 9. For u·n ≥ 0, h_σ − h_K = ½(h_L − h_K) points toward the downwind cell, so β would have to be negative relative to any upstream M_K. The positivity proof (Lemma 3.1) therefore does not cover it. An upwind-biased limited value uses the upstream slope (h_K − h_J), bounded by the downwind difference, and satisfies both conditions 8 and 9.
- [Certain, algebra] Every TVD limiter has φ(1) = 1. A limited upwind-biased reconstruction is therefore exact for a uniform gradient, which is the uniform-flow-on-a-slope case. It reverts to upwind (φ = 0) wherever the upstream and downstream differences change sign, which happens at a jump on a downslope: the level falls upstream and rises across the jump.
- [Certain, algebra] Herbin's choice of reconstructing the depth h rather than the level is exact for uniform flow on any slope even without a limiter, since h is constant there.
- [Guessing, unverified intent] On a uniform grid, D-Flow FM's `limtyphu = 1` adds the full minmod of the upstream and downstream differences, with no ½ factor in `sethu.f90`. For a uniform gradient this puts the face level at the downstream cell's level rather than midway. That may be why the option is off by default and the manual calls it unavailable. It should not be copied without checking.
- [Likely] The cost of the limited reconstruction, by Herbin's Lemma 3.1, is a positivity CFL halved relative to upwind. Their partly dry test ran at about 1/8 against four times that for first order.

### Gaps
- No paper found reports a staggered scheme with a reconstructed continuity face depth or level on MacDonald's supercritical or transcritical profiles, on Ritter, or on uniform flow on a slope. Herbin et al. test only flat-bed shocks, a smooth vortex and closed-domain topography.
- Gunawan and Lhébrard: no staggered face-depth paper by these two authors was found. The search returned only Gunawan's 2015 thesis title and Doyen-Gunawan. A Gunawan-Lhébrard 2015 relaxation scheme for shallow-water Exner exists to my knowledge, but it was not retrieved, so this is not confirmed.
- The first-order companion of Herbin et al. ([arXiv:1906.11001](https://arxiv.org/abs/1906.11001)) was downloaded but not read.

## 3. 3Di/Rana: the slope limiters, what each computes, which regime, and Stelling 2012 and 2022 on slopes

### Takeaway
The 3Di/Rana limiters are built for thin sheet flow and for steep level steps. The area limiter (type 2 or 3) replaces the level-based face area with a volume-over-area depth. It switches on only when the downstream depth is below the thin-layer definition, 0.3 m in the sloping preset; above that the uniform-level area is used unchanged. Nothing in the Rana documentation addresses deep flow on a slope. Stelling 2022 (VCE + TLC) is, by its abstract, a thin-layer runoff remedy; its full text was unreachable.

### Cited Findings
- [manual] Rana states that a cell holds a uniform water level while the bed varies. This overestimates the wet cross-section at a cell edge, and so the discharge, and it is not valid where water runs down a slope as sheet flow. — [Rana simulation settings](https://docs.ranawaterintelligence.com/h_simulation_settings.html); [3Di 2D surface flow](https://docs.3di.lizard.net/h_surfaceflow.html)
- [manual] `limiter_slope_crossectional_area_2d` has four values:
  - 0 (default): no limiter.
  - 1: as summarised from the page, applies when the downstream depth is zero. For a large level difference it sums the upstream and downstream volumes and divides by the total maximum surface area of the two cells; for a small difference it uses the average of the two levels. The page calls this mathematically second order.
  - 2: an upstream sheet-flow method; the edge depth is the upstream volume divided by the upstream cell's maximum surface area.
  - 3: needs `thin_layer_definition` and blends smoothly between the default depth and the type-2 depth, depending on local depth and the thin layer. — [Rana simulation settings](https://docs.ranawaterintelligence.com/h_simulation_settings.html)
- [manual] Regimes as Rana states them:
  - Edge depth, taken from the downstream level, above the thin-layer definition: the uniform-level assumption applies.
  - Downstream level below it: the type-2 area.
  - In between: weighted (type 3).
  - On slopes, sheet flow is treated with uniform depth instead of uniform level. — [Rana simulation settings](https://docs.ranawaterintelligence.com/h_simulation_settings.html)
- [manual] `limiter_slope_friction_2d` estimates the effective friction depth with the same kind of limiter. It is obligatory with the area limiter, or friction is underestimated on slopes. — [Rana simulation settings](https://docs.ranawaterintelligence.com/h_simulation_settings.html)
- [manual] `limiter_grad_2d` limits a water-level gradient to the actual depth, for jumps in the bottom: φ_{m+1} = min[1, H / (σ_{m+1} − σ_m)], where H is water depth and σ water level. — [Rana simulation settings](https://docs.ranawaterintelligence.com/h_simulation_settings.html)
- [manual] Friction shallow-water depth correction, values 0 to 3 (the page names the key `friction_shallow_water_correction`):
  - When on, friction is computed both classically and from averaged depth, velocity and roughness, and the larger is used.
  - 1 uses the maximum depth at the cell edge; 2 and 3 define the depth as the area limiter does.
  - The slope tutorial names value 3 "linearized depth based on weighted average". No formula is given. — [Rana simulation settings](https://docs.ranawaterintelligence.com/h_simulation_settings.html); [Rana slope tutorial](https://docs.ranawaterintelligence.com/e_2d_slope_tutorial.html)
- [manual] Rana's "Sloping" preset sets:
  - water-level gradient limiter on in 1D and off in 2D;
  - area limiter type 3 (thin water layer), with the thin layer at 0.3 m;
  - friction slope limiter on;
  - friction shallow-water depth correction 3.

  The stated reason is that the uniform-level assumption fails on steep slopes. No quantitative comparison is given. — [Rana slope tutorial](https://docs.ranawaterintelligence.com/e_2d_slope_tutorial.html)
- [manual] The Rana surface-flow page builds a 2D edge cross-section from the pixel pairs either side of the cell boundary, taking the maximum of each pair. It does not say which water level is used. — [Rana 2D surface flow](https://docs.ranawaterintelligence.com/h_surfaceflow.html)
- [abstract] Stelling (2012) combines four parts: sub-grid, friction from the divided-channel method, staggered finite volumes for rapidly varying flow, and quadtrees. The abstract says nothing about slopes. — [Stelling 2012, Water Management 165, doi:10.1680/wama.12.00018](https://doi.org/10.1680/wama.12.00018)
- [abstract] Stelling (2022) says overland flow on hills has accuracy and stability problems with sub-grid methods, especially in downhill flooding and runoff on inclined planes. It proposes a volume correction equation with intrinsic wetting and drying and no stability constraint, and a thin-layer calculation said to be accurate for runoff on coarse grids with sloping sub-grids. According to search snippets of the repository record, the introduction names a time-step limit on slopes with thin water layers under semi-implicit integration. — [Stelling 2022, Computers and Fluids 247, 105645](https://doi.org/10.1016/j.compfluid.2022.105645); [TU Delft record](https://repository.tudelft.nl/record/uuid:592fec09-2b93-4802-b382-887d1eab29a1); abstract via [OpenAlex](https://api.openalex.org/works/doi:10.1016/j.compfluid.2022.105645)

### Inferences
- [Likely] For the Wadi2D case, deep flow of 1 to 3 m on 1 to 3 % slopes, every Rana limiter is inactive by construction: the edge depth exceeds the 0.3 m thin layer. Rana's own model therefore carries the same first-order S dx/2 face-area excess the Wadi2D runs measured. Their documentation acknowledges the overestimate but does not correct it for deep flow.
- [Likely] Rana's type 2 (upstream volume over maximum area) is a depth-carry rule, h_face = V_U/A_U,max, for thin flow. It is exact for a uniform sheet whatever the slope, because it carries a depth, not a level.

### Gaps
- Stelling 2022 full text not read: the TU Delft repository refused connections, ScienceDirect returned 403, and CORE has no full text. Whether the thin-layer calculation has any deep-flow component is unknown.
- No Rana formula was found for type-3 weighting or friction correction 3.
- The type-1 description is ambiguous as summarised.

## 4. SFINCS sub-grid (van Ormondt et al. 2020, 2025): uv-point level and slopes

### Takeaway
SFINCS takes the face level as the maximum of the two adjacent cell levels, which in downhill flow is the upwind level, and reads the face's sub-grid tables at it. That is the same first-order construction as the Wadi2D baseline. The 2025 paper states the constant-level assumption is invalid where gradients are steep but offers no slope correction.

### Cited Findings
- [full] Regular SFINCS: the interface depth is h_u = max(zs_m, zs_{m+1}) − max(zb_m, zb_{m+1}), and the local-inertial momentum update uses h_u and the level gradient. — [van Ormondt et al. 2025, GMD 18, 843-861](https://gmd.copernicus.org/articles/18/843/2025/)
- [full] SFINCS sub-grid computes the velocity-point level as z_u = max(zs_{m,n}, zs_{m+1,n}). It queries the face lookup tables with it for the grid-average depth H_u^G, the adjusted Manning n and the conveyance factor, interpolating linearly for partly wet points. Above z_max, H_u^G grows linearly with z_u. The key stated assumption is a constant level over all sub-grid pixels of the velocity point. — [van Ormondt et al. 2025](https://gmd.copernicus.org/articles/18/843/2025/)
- [full] SFINCS uses grid-average rather than wet-average quantities, following Kennedy et al. (2019)'s notation, because wet averages vary too irregularly with level. — [van Ormondt et al. 2025](https://gmd.copernicus.org/articles/18/843/2025/)
- [full] The authors note that their downscaling has limited use where gradients are steep, because the constant-level-per-cell assumption fails there. For connectivity they use a sub-grid weir formulation in place of cell clones or artificial diffusion. — [van Ormondt et al. 2025](https://gmd.copernicus.org/articles/18/843/2025/)

### Inferences
- [Likely] Downhill, max(zs) = zs_U, and the u-point table spans the pixels between the two cell centres, including the lower downstream half. SFINCS therefore overestimates face depth on a slope by about S dx/2, as Wadi2D does. Its non-sub-grid form, max(zs) − max(zb), is instead the upwind depth and exact for uniform flow.

### Gaps
- SFINCS 2020 (van Ormondt et al., GMD) was not re-read.
- No SFINCS test on a uniform slope or a supercritical profile was found.

## 5. LISFLOOD-FP: h_flow = max(η) − max(z), its behaviour on slopes, and Almeida-Bates on stability and accuracy

### Takeaway
LISFLOOD-FP's ACC face depth h_f = max(η_i, η_{i−1}) − max(z_i, z_{i−1}) equals the upwind cell's own depth for downhill flow, and so is exact for uniform flow on a uniform slope. The scheme is second order in space by a linearised flat-bed analysis. Its known weakness is supercritical flow and steep depth gradients, where the local inertial equations become inaccurate (Fr above about 0.5) or unstable (about 1 and above). Nothing published examines h_f's slope behaviour specifically.

### Cited Findings
- [full] The ACC update (eq. 19): q^{n+1}_{i−1/2} = [ q^n_{i−1/2} − g h_f Δt (η^n_i − η^n_{i−1})/Δx ] / [ 1 + g Δt n_M² |q^n_{i−1/2}| / h_f^{7/3} ], with h_f = max(η^n_i, η^n_{i−1}) − max(z_i, z_{i−1}). The grid is a staggered Arakawa C. — [Shaw et al. 2021, LISFLOOD-FP 8.0, GMD 14, 3577](https://gmd.copernicus.org/articles/14/3577/2021/)
- [full] By a linearised small-perturbation analysis (their Appendix B, after de Almeida et al. 2012), ACC is first order in time and second order in space. In the flat-floodplain EA test ACC is close to DG2 and needs a 2 m grid where FV1 needs 0.5 m for the same wave front. — [Shaw et al. 2021](https://gmd.copernicus.org/articles/14/3577/2021/)
- [full] In the rapidly propagating valley-wave test, ACC developed spurious oscillations downstream of an abrupt depth change where Fr reached about 1.5. The authors attribute this to the local inertial equations being invalid for abrupt depth changes and supercritical flow. — [Shaw et al. 2021](https://gmd.copernicus.org/articles/14/3577/2021/)
- [abstract] de Almeida and Bates (2013) find local inertial and full-dynamic models agree well for Fr < 0.5. Steady non-uniform profiles get milder depth gradients, unsteady waves propagate more slowly, and errors grow with Fr and depth gradient. — [de Almeida and Bates 2013, WRR, doi:10.1002/wrcr.20366](https://doi.org/10.1002/wrcr.20366)
- [abstract] de Almeida et al. (2012) proposed two modifications that improve the stability of the Bates et al. (2010) scheme in low-friction areas at no extra cost. — [de Almeida et al. 2012, WRR, doi:10.1029/2011WR011570](https://doi.org/10.1029/2011WR011570)

### Inferences
- [Certain, algebra] For flow down a uniform slope with the level falling in the flow direction, max(η) = η_U and max(z) = z_U, so h_f = h_U, the upwind depth. For flow up an adverse step, h_f = η_U − z_D. For flow against the level gradient (wind or inertia), h_f uses the higher level, which is then the downstream one. In both other cases it is not "upwind".
- [Likely] LISFLOOD's second-order claim is a flat-bed linear result. It says nothing about the depth-versus-level choice on slopes, but the max/max form happens to be the depth-carry choice that is exact in uniform flow.

### Gaps
- No paper was found that tests h_f = max η − max z against analytic profiles on slopes (MacDonald) or discusses its first-order error on bed gradients.
- Bates et al. (2010) and Neal et al. (2012) were not re-read.

## 6. Casulli 2009, Sehili 2014, Volp 2013, Kennedy 2019, other sub-grid second-order work, and blends of upwind and central (or level and depth) by Froude number or limiter

### Takeaway
The semi-implicit sub-grid papers (Casulli, Volp, Kennedy) treat the level as uniform per cell. Their corrections are for friction and advection (a uniform friction slope gives a "friction depth"), not for the face level on a slope. The only published evidence that a planar, second-order reconstruction of the free surface inside sub-grid cells fixes slope-type errors comes from collocated Godunov sub-grid models:
- Bitsch et al. 2026 (arXiv, DHI/DTU) cut the error by about 45 times on MacDonald;
- Shamkhalchian and de Almeida 2023;
- PRIMo (secondary report).

No Froude-number fade of the face depth was found in any staggered scheme. The nearest published analogue is collocated: Aureli et al. 2008's weighted surface-depth gradient method (WSDGM) blends level-based and depth-based intercell depths with a Froude-dependent weight; its formula was not read.

### Cited Findings
- [abstract] Casulli (2009) derives a mildly nonlinear system for the level by requiring correct mass balance in wet and wet-to-dry areas, with high-resolution sub-grid bathymetry. It needs no threshold depth and produces no negative depths. — [Casulli 2009, IJNMF 60, doi:10.1002/fld.1896](https://doi.org/10.1002/fld.1896)
- [abstract] Volp et al. (2013) compute on a coarse grid with sub-grid bathymetry and roughness, assuming a uniform flow direction and uniform friction slope within part of a coarse cell. — [Volp et al. 2013, WRR, doi:10.1002/wrcr.20324](https://doi.org/10.1002/wrcr.20324)
- [full, degraded text] In Volp's thesis:
  - Chapter 2 defines the edge cross-section as A_s(t) = ∫ H(x, y, t) dy along edge s (eq. 2.10), with a uniform coarse level.
  - The friction coefficient comes from assuming S = c_f u_p²/(gH) uniform within a momentum domain (eq. 2.17), which gives the friction depth.
  - In Chapter 3 (morphodynamics), coarse levels are linearly interpolated onto pixels by a three-point plane (eq. 3.1), on the argument that the hydrodynamics is accurate only when the level varies gradually at grid scale. A dry neighbour takes the cell's own level. This interpolation serves the bed grid, not the continuity flux. — [Volp 2017 thesis (VLIZ)](https://www.vliz.be/imisdocs/publications/ocrd/300563.pdf)
- [abstract] Kennedy et al. (2019) derive upscaled shallow-water equations with sub-grid terms needing closures "of different levels of complexity". These greatly improve accuracy on coarse grids in complex geometry. — [Kennedy et al. 2019, Ocean Modelling 144, 101491](https://doi.org/10.1016/j.ocemod.2019.101491)
- [secondary, search snippet only] A Woodruff ASBPA 2021 slide deck describes "Level 1" corrections as correcting friction and advection. — [Woodruff ASBPA 2021](https://ccht.ccee.ncsu.edu/wp-content/uploads/sites/10/2021/10/Woodruff_ASBPA_2021.pdf); [Woodruff et al. 2021, Ocean Modelling, doi:10.1016/j.ocemod.2021.101887](https://doi.org/10.1016/j.ocemod.2021.101887)
- [full] Bitsch, Heilmann, Sørensen, Engsig-Karup and Grooss (arXiv 2601.01895 v2, October 2026) describe a cell-centred unstructured sub-grid finite volume with WENO and RK2. The second-order version uses a planar free surface per coarse cell, h_{(m,k)} = max(0, η_m + ∇η·(x_{(m,k)} − x_m) + d_{(m,k)}) (eq. 35). The volume is matched by shifting η_m with the gradient frozen. — [Bitsch et al. 2026](https://arxiv.org/abs/2601.01895)
- [full] Bitsch et al. 2026, MacDonald-type test: L = 5000 m, Manning 0.03, q = 2 m²/s, steady after 100 min.
  - First-order (constant level per cell, no sub-grid) L2(h) = 9.65e-2 at about 70 m cells, falling to 4.73e-2 at about 36 m (order 1.0).
  - Second order (planar level) gives 2.16e-3 to 5.42e-4 (order 1.9 to 2.4).
  - The first-order scheme gains nothing from sub-grid cells, because a constant surface and a nearly constant bed slope average them out. The second-order scheme improves with sub-grid cells.
  - Their constant-level water distribution concentrates water at the downhill end of an element on steep slopes, modelling the flow as a series of waterfalls when it runs parallel to the slope. They cite Begmohammadi et al. 2021 and Stelling 2022 as proposed mitigations. — [Bitsch et al. 2026](https://arxiv.org/abs/2601.01895)
- [secondary] Bitsch et al. report that PRIMo (Sanders and Schubert 2019), an explicit Riemann-based Cartesian sub-grid model, uses a second-order reconstruction of the free surface, and that Shamkhalchian and de Almeida (2021; 2023) extended a face-averaged upscaled scheme to second order. — [Bitsch et al. 2026](https://arxiv.org/abs/2601.01895); [Sanders and Schubert 2019, doi:10.1016/j.advwatres.2019.02.007](https://doi.org/10.1016/j.advwatres.2019.02.007)
- [abstract] Shamkhalchian and de Almeida (2023) use a nested-mesh upscaled Godunov finite volume with piecewise-linear reconstruction. Against their first-order version and a conventional second-order finite volume, accuracy improved, and on coarse meshes the reconstruction of variables plays a major role in accuracy. — [Shamkhalchian and de Almeida 2023, JHR 61(3), doi:10.1080/00221686.2023.2201210](https://doi.org/10.1080/00221686.2023.2201210)
- [abstract and secondary] Aureli, Maranzoni, Mignosa and Ziveri (2008), in the SLIC framework, compute intercell water depths as a weighted average of depth-gradient (DGM) and surface-gradient (SGM) reconstructions, with a weight depending on the local Froude number.
  - SGM keeps still water still over topography (the C-property); DGM is robust near wet-dry fronts.
  - The weighted method was better than or equal to SGM and DGM in all their tests. — [Aureli et al. 2008, Adv. Water Resour. 31(7), 962-974, doi:10.1016/j.advwatres.2008.03.005](https://doi.org/10.1016/j.advwatres.2008.03.005); [University of Parma record](https://air.unipr.it/handle/11381/1875621)

### Inferences
- [Likely] The literature splits the face value into two families.
  - Level-based: SGM; the Wadi2D baseline; D-Flow FM; SFINCS sub-grid. Exact for still water, first order on a sloping bed unless reconstructed.
  - Depth-based: DGM; Herbin's h-MUSCL; LISFLOOD's max η − max z; Delft3D DPUOPT=UPW or MIN with the upwind level; Rana type 2. Exact for uniform flow on a slope even at first order.
- [Likely] In a sub-grid cell "depth" has no single meaning. The depth-based analogue for Wadi2D is to read the face table at η_U − Δz_ref: the level carried down by the bed drop between the upwind cell's reference bed and the face's reference bed. It must be capped at η_U, or a crest face (weir) would see the upstream pool's depth over the crest.
- [Likely] The limited level reconstruction, η_f = η_U + ½ φ(r)(η_U − η_UU) with r = (η_D − η_U)/(η_U − η_UU), carries the actual surface slope. It is exact in uniform flow and second order on smooth gradually varied profiles such as MacDonald's sub- and supercritical branches.
- [Likely] The same limited reconstruction reverts to upwind wherever r ≤ 0: at a jump, at the head of a front, and at local extrema. That is the property the central reading lacked when it worsened the supercritical and jump profiles and Ritter.
- [Likely] Because the limited value lies between η_D and η_U, the face area never exceeds A(η_U).
- [Likely] A Froude fade, weight w(Fr) between central (or depth-carry) and upwind, has no staggered precedent. Its closest published relative is WSDGM, which blends depth-based and level-based reconstructions, not central and upwind.
- [Guessing] Why central failed in supercritical flow: in supercritical flow, central brings downstream information into the continuity flux. That is consistent with the measured discharge deficit of 1.4 to 4 % in supercritical flow. No source tests this directly.
- [Likely] Why central failed in the 45-degree channel: averaging across a staircase face pairs a wet cell with a bank cell. This matches Delft3D's "dry too early" remark on averaging near steep bed gradients.

### Gaps
- No paper found applies a Froude-number fade to the face depth or level in a staggered or sub-grid scheme. This is stated plainly as absent from everything searched.
- The WSDGM weight function was not read. The journal text is restricted and the Ziveri 2008 thesis pages did not load.
- Sehili, Lang and Lippert (2014, Ocean Dynamics) was not retrieved; its DOI could not be resolved from here.
- Kennedy et al. (2019) full text was not read (par.nsf.gov unreachable from this machine). Its closure "levels" and any face treatment are unverified.
- Shamkhalchian and de Almeida 2023 full text returned 403, so which variable they reconstruct (level or depth), their limiter and their test cases are unverified.
- PRIMo's reconstruction is known only through Bitsch et al.
- Bitsch et al. 2026 is a preprint and collocated, not staggered. Its 45-fold MacDonald gain mixes the planar surface with WENO momentum and RK2, so it does not isolate the face-depth effect.
