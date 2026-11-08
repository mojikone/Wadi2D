# Wall shear in depth-averaged and sub-grid friction: what the literature says

Scope and reading depth, stated up front because it matters for every claim below.
**Read in full (text extracted and checked):** Volp, van Prooijen & Stelling 2013 (Ch. 2 of Volp's TU Delft thesis, friction section), van Ormondt et al. 2025 (SFINCS sub-grid, GMD), Spada et al. 2015 (HESSD, "Uniform flow formulas for irregular sections", the local hydraulic radius method), Tavakkol & Zarrati 2018 (wall and bed shear force in rectangular channels, arXiv), Van Emelen, Zech & Soares-Frazao (UCLouvain, steep-slope shallow water), the Rana (3Di) documentation pages on surface flow and simulation settings.
**Abstract or listing only:** Knight, Demetriou & Hamed 1984; Shiono & Knight 1991; Liao & Knight 2007; Knight, Omran & Tang 2007; Guo 2015; Kennedy et al. 2019; Sehili et al. 2014; Yen 2002; Seckin 2004; Stelling 2012 (from the project's N01 note).
**Not obtained:** Chow 1959, Henderson, Einstein 1942, Johnson 1942, Vanoni & Brooks 1957, Casulli 2009, Guo & Julien 2005 (empty download; its numbers come via Tavakkol & Zarrati), the HEC-RAS 2D reference manual's friction equation, TUFLOW's SGS friction formulation.
Equations marked "transcribed" come from automated extraction of the source; where symbols were lost it is said.

---

## 1. Divided-channel (Lotter) sum against single-channel hydraulic-radius Manning: which predicts stage better, and by how much

### Takeaway
The Wadi2D face sum K = sum (1/n) d^(5/3) dy is the divided-channel method (DCM) taken to infinitesimal vertical strips with plan width as perimeter. The flume and field literature says plainly that DCM **overestimates** discharge, so it under-predicts stage. The one published method calibrated to sit between DCM and single-channel Manning (SCM), Spada et al.'s local hydraulic radius, gives **5.34 m on the gorge**, against 5.39 m from SCM and 4.40 m from the strip sum. Their calibrated window is 9 depths, wider than the gorge. In a straight prismatic section narrower than about 18 depths, the evidence favours SCM, within about 1 %.

### Cited Findings
- **DCM's known bias.** Spada et al. describe two practices. SCM "simply ignore[s] the problem" and in compound sections leads to "strong underestimation of the discharge". DCM sums subsection discharges at one water level, keeping each subsection's own wetted perimeter and dropping the shared division lines. They say that dropping those lines neglects the shear from vortices with vertical axes and "results in overestimation of discharge capacity", citing Lyness et al. 2001. [full text] — [Spada et al. 2015, HESSD 12:2607](https://hess.copernicus.org/preprints/12/2607/2015/hessd-12-2607-2015.pdf)
- **Knight & Hamed 1984** compared subdivision methods with the vertical division line included in or excluded from the wetted perimeter. Spada et al. report their finding that "conventional calculation methods result in larger errors". Wormleaton et al. 1982 and Wormleaton & Hadjipanos 1985 found horizontal division no better. [secondary, via Spada] — [Spada et al. 2015](https://hess.copernicus.org/preprints/12/2607/2015/hessd-12-2607-2015.pdf)
- **The local hydraulic radius method (LHRM), as written.** Discharge is q = ∫_0^L h(y) U(y) dy (eq. 14), with U = l^(2/3) S0^(1/2) / n (eq. 15). The local hydraulic radius is l(y) = ∫_a^b h(s) N(y,s) ds / ∫_a^b N(y,s) sqrt(ds² + dz²) (eq. 16a), over a = max(0, y − βh), b = min(L, y + βh) (16b, c). N is a linear shape function, equal to zero at a distance from y proportional to the depth (eq. 17). The β was lost in text extraction, and the text calls it "an empirical positive coefficient". In the authors' words: "If β is close to zero, LHRM is equivalent to the DCM, while if β is very large LHRM is equivalent to the traditional Manning formula." [full text] — [Spada et al. 2015](https://hess.copernicus.org/preprints/12/2607/2015/hessd-12-2607-2015.pdf)
- **Calibration.** β = 9 was calibrated on the HR Wallingford Flood Channel Facility (FCF) series F1, F2, F3 and F6. The sensitivity of discharge to the parameter is weak: a one-digit β gives under 2 % discharge variability. [full text] — [Spada et al. 2015](https://hess.copernicus.org/preprints/12/2607/2015/hessd-12-2607-2015.pdf)
- **Validation (Nash-Sutcliffe of discharge, Table 3, in the order DCM / IDCM / INCM / LHRM).**

  | Series | DCM | IDCM | INCM | LHRM |
  |---|---|---|---|---|
  | F8 | −0.079 | 0.988 | 0.989 | 0.996 |
  | F10 | −0.089 | 0.997 | 0.998 | 0.998 |
  | K1 | −14.49 | −0.70 | −8.29 | 0.997 |
  | K2 | −0.98 | 0.35 | −1.83 | 0.962 |
  | K3 | 0.18 | 0.65 | −0.39 | 0.979 |
  | K4 | 0.29 | 0.89 | 0.35 | 0.996 |

  The K series is Knight & Demetriou 1983, all with a vertical main-channel wall. K1 has B/b = 1, "simply rectangular", in smooth Perspex with n 0.01. "The DCM results are always worse and are particularly bad for all the K series." [full text] — [Spada et al. 2015](https://hess.copernicus.org/preprints/12/2607/2015/hessd-12-2607-2015.pdf)
- **Against a 3D solver** (ANSYS CFX on a reach of the Alzette), "DCM ... clearly overestimates averaged velocities". INCM and LHRM agree with CFX within about 7 % in the centre of the section. Near the banks the 1D methods differ from CFX because "close to the bank the wall resistance is stronger" and secondary flows carry the exchange. Near-bank cells contribute little discharge. [full text] — [Spada et al. 2015](https://hess.copernicus.org/preprints/12/2607/2015/hessd-12-2607-2015.pdf)
- **Composite-roughness formulas** as reproduced in a software reference (the R package iemisc):
  - Horton (equal velocity): n_c = [Σ P_i n_i^(3/2) / P]^(2/3).
  - Einstein & Banks (the same form attributed to Pavlovskii, total force): n_c = [Σ P_i n_i² / P]^(1/2).
  - Lotter (total discharge): n_c = P R^(5/3) / Σ (P_i R_i^(5/3) / n_i).

  [listing] — [iemisc nc.R](https://rdrr.io/cran/iemisc/src/R/nc.R); [iemisc nc2](https://search.r-project.org/CRAN/refmans/iemisc/html/nc2.html)
- **Yen 2002**, J. Hydraul. Eng. 128(1):20-39, reviews about 16 composite-n relations grouped by assumption: mean velocity, total force, total discharge. It covers point, cross-sectional and reach resistance coefficients, and momentum against energy resistance. A secondary source says Yen did not state which subdivision suits which formula, only that vertical division is generally used. [secondary] — [Korean review, koreascience](https://koreascience.kr/article/JAKO201001039068355.pdf)
- **Lotter against measurements.**
  - In natural rivers, Lotter's method gave the smallest error against values computed from measured data (Motayed & Krishnamurthy 1980).
  - In small trapezoidal flumes it was "considerably lower" in accuracy (Djajadi 2009).

  [secondary] — [koreascience](https://koreascience.kr/article/JAKO201001039068355.pdf)
- **Compound-channel error levels.**
  - A Turkish study: SCM and DCM both exceed 10 % relative error at low flows, and DCM falls below 2 % at high flows, in a compound channel with a trapezoidal main channel. [listing] — [Bartin Univ. repository](https://acikerisim.bartin.edu.tr/handle/11772/1076)
  - Seckin 2004: Ackers' method and the exchange discharge method (EDM) gave discharge errors generally under 10 % on smooth and fixed beds and up to 20 % on mobile beds, with means of 5.4 % (Ackers) and 7.1 % (EDM). [abstract] — [Seckin 2004, Can. J. Civ. Eng.](https://avesis.cu.edu.tr/yayin/c4fba43c-e5df-410b-83b8-ce5a11d9f4d5/a-comparison-of-one-dimensional-methods-for-estimating-discharge-capacity-of-straight-compound-channels)

### Inferences
- [Certain, algebra] With uniform n, Horton-Einstein and Pavlovskii both reduce to n_c = n, so both give SCM exactly. Lotter's formula is the only one of the three that keeps the subdivision at uniform roughness, and on vertical strips that drop the division lines from P it is the DCM.
- [Certain, algebra] The Wadi2D face sum is a second step beyond Lotter. It also replaces each strip's wall perimeter by its plan width dy. With the true slant length, a strip's conveyance is (1/n) d^(5/3) dy / (1 + z_y²)^(1/3).
- [Certain, own computation on the stated section: 12 m bed, walls 7 m over 1.5 m, n 0.05, S 1 %, 300 m³/s] Normal depths:

  | Method | Normal depth, m |
  |---|---|
  | Strip sum, plan width | 4.398 |
  | Strips with slant length (bed-area factor) | 4.494 |
  | LHRM, β → 0 (DCM limit) | 4.52 |
  | LHRM, β = 1 | 4.92 |
  | LHRM, β = 3 | 5.22 |
  | **LHRM, β = 9 (calibrated)** | **5.34** |
  | LHRM, β = 1000 | 5.388 |
  | SCM | 5.388 |

  The LHRM's two limits reproduce DCM-with-slant and SCM, which checks the implementation. Script in the session scratchpad, not kept. The LHRM shape function was rebuilt from garbled text as N = 1 − |s − y| / (βh(y)), so treat the β = 9 value as [Likely].
- [Likely] On this gorge, the slant length of the walls is worth only about 0.1 m (+2 %). Almost all of the 1 m gap between the strip sum and SCM is the lateral transfer of wall drag into the core flow, which DCM by construction leaves out. Only a lateral-exchange term recovers it: SCM's implied full mixing, LHRM's window, or SKM's λ term.
- [Likely] The calibrated evidence (Spada's K1 rectangular series and FCF) says the plan-width or DCM sum is the wrong end for a narrow section. The +23 % SCM depth is right to within about 1 %, if the n was meant as a whole-section Manning n, as hand-calculation n tables are. This holds for a straight, prismatic channel with one n on bed and walls.
- [Guessing] The K1 result (DCM NS −14.5 on a rectangle) depends on how Spada et al. subdivided a rectangle for DCM, which the text I read does not state. It may be horizontal division at the former bank level. Do not quote it as "DCM on a rectangle" without checking their Fig. 1 and Table 1.

### Gaps
- Chow 1959 (ch. 6), Henderson and Yen 2002 themselves were not read. Their exact statements, and any numbers they give comparing composite methods in narrow deep sections, are not verified.
- No study was found that tests the infinitesimal-strip, plan-width sum (the sub-grid face form) against measured stage in a single narrow deep channel. The nearest tests are the DCM results above.
- No data were found for rock gorges, or for walls rougher than the bed; every flume result here is smooth or uniform roughness.

---

## 2. Bed shear on a sloping bed in a depth-averaged model: the sqrt(1 + |grad z_b|²) or 1/cos factor, who uses it, and how wall shear enters depth-averaged equations

### Takeaway
The bed-area factor belongs in the depth-integrated friction term. It appears explicitly in the lateral-distribution (SKM) family as sqrt(1 + 1/s²) on side slopes, and in steep-slope SWE written in global coordinates. I found no mainstream 2D flood engine (SFINCS, 3Di, TUFLOW, HEC-RAS) that documents it. A vertical wall is not a slope at all in a 2D model. It is a lateral boundary, and its shear enters only through a lateral friction boundary condition, as TELEMAC-2D offers with its own roughness, plus the horizontal turbulent stress. A sub-grid face that contains the wall loses both. On the gorge, the factor alone recovers only about 0.1 m of the missing 1 m.

### Cited Findings
- **SKM boundary terms.** The SKM is derived from the depth-integrated RANS equations for straight channels. The abstract says it includes "bed-generated turbulence, lateral shear turbulence and secondary flows" and gives lateral distributions of depth-mean velocity and boundary shear "for channels of any shape". [abstract] — [Shiono & Knight 1991, J. Fluid Mech. 222:617](https://www.cambridge.org/core/services/aop-cambridge-core/content/view/S0022112091001246)
- **The side-slope parameter.** In SKM the side slope is written 1:s (vertical:horizontal), and the analytic solution splits the section into zones of constant s: floodplain s = ∞, bank s = 1 and so on. The coefficients carry terms in K/s. [search excerpts] — [Springer EFM s10652-024-10003-3](https://link.springer.com/10.1007/s10652-024-10003-3); [Springer EFM s10652-018-09655-9](https://link.springer.com/article/10.1007/s10652-018-09655-9)
- **Stage-discharge formulae from SKM.** Liao & Knight 2007 (Adv. Water Resour. 30(11):2283-2295) derive analytic stage-discharge formulae for straight trapezoidal channels "together with physically based hydraulic parameters, such as local friction factor (f)", and discuss the influence of f, λ and Γ. Knight, Omran & Tang 2007 (J. Hydraul. Eng. 133(1):39) cover depth-averaged velocity and boundary shear in trapezoidal channels with secondary flows. [abstract / title] — [Liao & Knight 2007](https://research.birmingham.ac.uk/portal/en/publications/analytic-stagedischarge-formulae-for-flow-in-straight-trapezoidal-open-channels(93241e4f-626c-4341-a679-78c9839fc02e).html); [Knight, Omran & Tang 2007](https://ascelibrary.com/doi/10.1061/%28ASCE%290733-9429%282007%29133%3A1%2839%29)
- **Steep longitudinal slope** (Van Emelen, Zech & Soares-Frazao).
  - Classical SWE: S_f = n²q² / h^(10/3) (eq. 3). In the modified model the pressure is hydrostatic normal to the bed, p = ρg(z_w − z) cos θ (eq. 7), with H = h / cos θ and dX = dx cos θ (eq. 9).
  - In global coordinates the momentum source becomes "−gH cos²θ ∂Z_b/∂X − cos θ S_f", with S_f = n²q² / (cos^(10/3) θ H^(10/3)) (eqs. 10-11). The friction is reduced by cos θ and the depth is converted.
  - Uniform depth: local coordinates h_u = (n²q0² / sin θ)^(3/10) (eq. 21); classical SWE in global coordinates H_u = (n²q² / tan θ)^(3/10) (eq. 22).
  - Conclusion: the classical model is fine for fast transients on steep slopes, but "more accurate models should be used" for steady uniform flow.

  [full text] — [Van Emelen, Zech & Soares-Frazao, UCLouvain](https://research.dial.uclouvain.be/bitstreams/df62ced1-23dc-4e2a-a8a1-93251152689a/download)
- **TELEMAC-2D** sets lateral-boundary friction apart from bed friction, with keywords `LAW OF FRICTION ON LATERAL BOUNDARIES` (for example 4, Manning) and `ROUGHNESS COEFFICIENT OF BOUNDARIES` (for example 0.03). [tutorial excerpt] — [hydro-informatics TELEMAC-2D steady tutorial](https://hydro-informatics.github.io/numerics/telemac/telemac2d-steady.html)
- **Granular analogue.** Depth-averaged models of narrow-channel granular flows carry an explicit side-wall friction term. Example: "2D granular flows with the μ(I) rheology and side walls friction: a well balanced multilayer discretization". [title only] — [arXiv 1707.01256](https://arxiv.org/pdf/1707.01256)
- **Rana (3Di)** on sloping terrain with its default sub-grid: "the wet cross-sectional area will be overestimated, and the friction will be underestimated", which its limiters address. [full page] — [Rana docs, 2D surface flow](https://docs.ranawaterintelligence.com/h_surfaceflow.html)

### Inferences
- [Likely; recalled from Shiono & Knight 1991, NOT verified against the primary this session] The SKM depth-averaged streamwise equation is ρgHS0 − ρ(f/8) U_d² (1 + 1/s²)^(1/2) + ∂/∂y[ρλH² (f/8)^(1/2) U_d ∂U_d/∂y] = ∂/∂y[H(ρUV)_d]. The (1 + 1/s²)^(1/2) is the ratio of wetted bed length to plan width. In Cartesian terms, 1/s = |∂z_b/∂y| and the factor is sqrt(1 + |∇z_b|²). The report writer should check this against Shiono & Knight 1991 or Knight, Omran & Tang 2007 before quoting.
- [Certain, geometry] As s → 0 (a vertical wall) the factor goes to infinity over zero plan width. The product, wall length times τ_w, stays finite, so a vertical wall cannot be carried by a bed term on a plan-width strip. It must be a boundary force, a wall function at a lateral boundary, or a term in the face conveyance.
- [Likely] In a resolved 2D model the wall's drag reaches the core flow only through the horizontal eddy-viscosity term and the lateral boundary condition. With a slip wall and no eddy viscosity, a resolved 2D model also returns roughly the strip-sum depth. That matches Wadi2D's 4.40 m at every cell size.
- [Certain, own arithmetic from eqs. 21-22] For longitudinal slopes the correction is negligible at 1 %. At θ = 30° the classical global-coordinate SWE gives a vertical uniform depth cos^1.3 θ = 0.83 of the bed-normal-consistent one, a 17 % underestimate. For the gorge, the lateral slope of the walls is what matters, not the longitudinal slope.

### Gaps
- The SKM equation with the side-slope factor was not retrieved from a primary text (paywalls), and no SKM accuracy numbers on discharge were obtained.
- I found no documentation that HEC-RAS 2D, TUFLOW HPC, SFINCS or 3Di apply a bed-area factor to friction. That is absence of evidence, not evidence of absence.
- TELEMAC-2D's default lateral friction law (believed to be 0, no friction) was not confirmed.
- No derivation was found of a side-wall term for a sub-grid face whose profile contains a wall.

---

## 3. Sub-grid friction (Volp 2013, Casulli 2009, Sehili 2014, Kennedy 2019, van Ormondt 2025): does any include wall shear or a wetted-perimeter term, and why

### Takeaway
None does. Every published sub-grid friction closure found builds friction from the **local vertical depth of each pixel** under a uniform water level and a uniform friction slope (or local friction/pressure balance). That is the Lotter/DCM assumption applied per pixel, with no wetted perimeter, no bed-area factor and no wall term. None of these papers discusses the omission. Their benchmarks are fine-resolution depth-averaged runs, which carry the same omission, so the closures were never tested on it.

### Cited Findings
- **Volp, van Prooijen & Stelling 2013** (WRR 49, Ch. 2 of Volp's thesis) [full text of the friction section, transcribed]:
  - Uniform flow direction per quarter domain: u_p = u / α_p (eq. 2.14).
  - Friction: F̃_fric = u |U| ∬ (c_f / α_p²) dΩ (eq. 2.15).
  - "The main assumption for defining α_p is assuming a uniform friction slope": S = c_f u_p² / (gH) = uniform (eq. 2.17). Here H is the local pixel depth.
  - α_p = sqrt(c_f/H) · (1/V) ∬ H sqrt(H/c_f) dΩ (eq. 2.18).
  - F̃_fric = u |U| V / H_f (eq. 2.19).
  - "Friction depth" H_f = [∬ H sqrt(H/c_f) dΩ / V]² (eq. 2.20). It "only depends on the subgrid depths and roughness coefficients", and with one sub-grid cell it reduces to H_f = H / c_f.
  - The discussion says the model is depth-averaged, so "the flow around three-dimensional roughness elements is not resolved and has to be modeled within the friction coefficient".
  - No wetted perimeter, wall or bed-slope term appears.

  — [Volp thesis, VLIZ](https://www.vliz.be/imisdocs/publications/ocrd/300563.pdf); DOI 10.1002/wrcr.20324
- **van Ormondt et al. 2025** (SFINCS 2.1.1, GMD 18:843-861) [full text; fraction bars inferred by the extraction, and the square root on the slope i appears lost]:
  - Wet-average flux: ⟨q_u⟩_W = (i / (φ_u N)) Σ_{k=1}^{N} h_k^(5/3) / n_k (eq. 9).
  - Roughness: n_{u,W} = ⟨H_u⟩_W^(5/3) / ⟨H_u^(5/3)/n⟩_W (eq. 11).
  - Momentum update: ⟨q_u⟩_G^(t+Δt) = [⟨q_u⟩_G^t − gΔt ⟨H_u⟩_G Δz/Δx + φ_u F Δt] / [1 + gΔt n_u² |⟨q_u⟩_G^t| / ⟨H_u⟩_G^(7/3)] (eq. 12), with n_u = ⟨H_u⟩_G^(5/3) / ⟨H_u^(5/3)/n⟩_G (eq. 13).
  - Pixel depths are h_k = max(z_m − z_b,k, 0) (eq. 17).
  - Grid averages were chosen because wet-average depth and roughness "can vary much more rapidly and irregularly". n_u "should not be interpreted as a physical quantity" but as a flux control.
  - Assumption: "the water level within the velocity point is constant".
  - Results: a straight channel within 2 % of the analytical solution at all resolutions; unresolved meanders "may overestimate discharges by more than a factor of 5" at sinuosity up to 3 (473 against 313 m³/s at 500 m); the recommended grid spacing "does not exceed the width of the river channel".
  - No wall or bank shear is discussed.

  — [van Ormondt et al. 2025](https://gmd.copernicus.org/articles/18/843/2025/gmd-18-843-2025.html)
- **Rana (3Di):** "In the 2D domain, the friction is calculated using the flow depth at each subgrid pixel in the momentum domain", with Chezy or Manning. The `friction shallow water correction` setting (0 to 3) computes friction "classically" and from averaged depth, velocity and roughness, and "the maximum friction computed by the two is used". Value 1 uses "the maximum depth at the edge of the cell"; values 2 and 3 define the depth "similar to the cross-sectional area limiter". The friction-depth limiter is "obligatory in combination with" the cross-sectional-area limiter. [full pages] — [Rana surface flow](https://docs.ranawaterintelligence.com/h_surfaceflow.html); [Rana simulation settings](https://docs.ranawaterintelligence.com/h_simulation_settings.html)
- **Stelling 2012** (Proc. ICE Water Management) lists the 3Di components, including "friction by a divided-channel method". [abstract, from the project's N01 note] — [doi 10.1680/wama.12.00018](https://doi.org/10.1680/wama.12.00018)
- **Kennedy et al. 2019** (Ocean Modelling 144, 101491):
  - The systems carry extra terms tied to integrals of fine-scale bathymetry and flow, which need closures; these were tested against high-resolution SWE solutions. [abstract-level] — [CCHT summary](https://ccht.ccee.ncsu.edu/ocemod-2019-subgrid/)
  - In the ADCIRC implementation, "Level 0" is the wet-fraction correction and "Level 1" adds advection and bottom friction corrections that depend on the overall depth and local velocities. [slide-level] — [Dietrich USNCCM slides](https://ccht.ccee.ncsu.edu/wp-content/uploads/sites/10/2023/07/Dietrich-USNCCM.pdf)
  - The extended abstract derives improvements to Casulli's techniques for "bottom friction, wind stress, flow connectivity, and convective stresses". [read; 1-page extended abstract] — [Kennedy et al., ICCE](https://icce-ojs-tamu.tdl.org/icce/article/download/8405/7213/32925)
- **Sehili, Lang & Lippert 2014** (Ocean Dynamics 64:519-535): the abstract says bottom friction "requires a particular treatment". As characterised by the Kennedy et al. paper (secondary), Sehili et al. computed friction from mean depth and velocity rather than as an integral over the sub-grid bathymetry, applying Casulli's formulation to storm surge around Hamburg. [abstract plus secondary] — [CORE postprint](https://core.ac.uk/download/326243017.pdf)
- **TUFLOW HPC SGS** builds non-linear relations of water level to face area and face width ("i.e. wetted perimeter"). How the friction term uses them was not found. [manual excerpt] — [TUFLOW manual 3.2](https://docs.tuflow.com/classic-hpc/manual/2025.2/ModelResolutionDiscretisation-2.html); [TUFLOW SGS FAQ](https://wiki.tuflow.com/Quadtree_and_Sub-Grid_Sampling_FAQ)
- **HEC-RAS 2D**, per HEC staff forum posts, a training deck and a vendor article:
  - Each face is treated as a cross-section, with elevation tables of area, wetted perimeter and roughness, from which hydraulic radius and conveyance are computed.
  - Face hydraulic parameters use the higher of the two neighbouring cells' water levels.

  [secondary] — [CivilGEO, HEC-RAS 2D grid and subgrid](https://knowledge.civilgeo.com/hec-ras-2d-grid-subgrid-computations); [RAS Solution, subgrid theory](https://therassolution.kleinschmidtgroup.com/ras-post/hec-ras-subgrid-bathymetry-theory-and-application); [HEC-RAS webinar deck](https://awschool.com.au/wp-content/uploads/ALL-HEC-RAS-Webinar-PPTs-Final.pdf)

### Inferences
- [Certain, from the equations] Volp's H_f, SFINCS's eq. 9 and 3Di's per-pixel depth are each the Lotter sum on pixel strips with vertical depth. Under Manning it is the form Wadi2D uses (SFINCS eq. 9 is literally Σ h_k^(5/3)/n_k). Volp's is the Chezy analogue (q ∝ Σ H^(3/2)/sqrt(c_f)) over 2D quarter domains.
- [Likely] The reason none adds a wall term is structural, not argued. These closures aim to make a coarse grid reproduce a **fine-grid depth-averaged** solution (Kennedy: "tested against high-resolution shallow water solutions"; SFINCS: a 25 m regular reference and an analytical channel), and that reference has bed friction on vertical depth and no wall shear. Their validation therefore cannot reveal the omission.
- [Likely] HEC-RAS is the odd one out: one hydraulic radius per face from the face's own profile, which is a per-face SCM. The project's emulation (`wadi2d_gorge_facts.md` in this folder) reproduces HEC-RAS's 5.28 m at 20 m and 4.70 m at 5 m, falling toward the strip sum as faces shrink. HEC-RAS therefore carries "wall shear" only as an artefact of face width, not as a converged physical term. Neither HEC-RAS number is evidence for the physics.

### Gaps
- Casulli 2009 (IJNMF 60) and Casulli & Stelling 2011 were not read. Their friction form (believed to be Chezy on local depth over wet sub-areas) is unverified.
- Kennedy et al.'s exact Level 1 friction closure (their R_v and effective C_f) was not retrieved; the NSF PAR server refused the connection.
- The HEC-RAS 2D reference manual's friction term (believed to be c_f = g n² |V| / R^(4/3), with R the face hydraulic radius) was not retrieved from the manual itself.
- TUFLOW's SGS friction formulation is undocumented in what was found.
- No sub-grid paper was found, to 2026, that tests a narrow deep channel against measured stage or a 3D model.

---

## 4. Side-wall correction in flume work (Einstein 1942, Johnson 1942, Vanoni & Brooks 1957, Knight): the walls' share of resistance against aspect ratio B/h

### Takeaway
In smooth rectangular flumes the walls carry about 36 to 38 % of the total boundary shear at b/h ≈ 3. That is 0.93 to 0.95 of their share of the perimeter, so a uniform-stress (SCM) split is close at that aspect ratio. The walls carry about 69 % at b/h ≈ 1.2, slightly more than the perimeter share, and 18 to 19 % at b/h ≈ 5.3 to 6.0, about 0.7 of the perimeter share. The bed shear lies between ρgRS (the hydraulic-radius method, lower bound) and ρghS (the depth method, upper bound). The gorge has B/h 2.2 to 2.7, wall perimeter share 43 to 48 %, so its walls should carry roughly 40 % of the resistance, which the strip sum sets to zero.

### Cited Findings
- **Knight, Demetriou & Hamed 1984**, "Boundary Shear in Smooth Rectangular Channels" (J. Hydraul. Eng. 110(4):405-422), give an empirical equation for the percentage of total shear force on the walls, %SF_w, as a function of B/H, with ancillary equations for mean wall, bed and centreline bed shear. [abstract; coefficients not retrieved] — [ASCE](https://ascelibrary.com/doi/10.1061/%28ASCE%290733-9429%281984%29110%3A4%28405%29)
- **Tavakkol & Zarrati 2018** (Scientia Iranica) [full text]:
  - Measured %SF_w at b/h ≈ 1.16 is 69 % (Gaussian-weighted mean of several experiments). Their model gives 71 %, the Knight et al. 1984 equation 63.2 %, and Guo & Julien 2005 62.9 %.
  - Table 1 (measured / Guo & Julien 2005 / their eq. 21):

    | Data | b/h | Measured | G&J 2005 | Eq. 21 |
    |---|---|---|---|---|
    | Xie 1998 | 3.2 | 36 % | 36.4 % | 36.6 % |
    | Xie 1998 | 2.9 | 38 % | 39.3 % | 39.6 % |
    | Chanson 2000 | 3.24 | 37 % | 36.1 % | 36.3 % |
    | Chanson 2000 | 5.32 | 19 % | 23.4 % | 23.0 % |
    | Chanson 2000 | 5.95 | 18 % | 21.0 % | 20.5 % |

    The Chanson rows are realigned from a garbled table; take them as [Likely].
  - Mean relative error on unseen data: 4.7 % for their model, 7.7 % for Guo & Julien.
  - Ignoring secondary currents and keeping only zero-shear division lines underestimates the bed shear force and "is not acceptable".
  - Schlichting, Keulegan, Haywood, Johnson (1942) and Einstein (1942) divided the section by zero-shear lines into bed and wall areas, each balancing its own weight component.

  — [Tavakkol & Zarrati, arXiv 1611.01608](https://arxiv.org/pdf/1611.01608)
- **Guo 2015**, "Sidewall and non-uniformity corrections for flume experiments" (J. Hydraul. Res. 53(2):218-229), reviews the flow-depth method, the hydraulic-radius method and Einstein's sidewall correction against log-law data. "The flow-depth and hydraulic radius methods set the upper and lower bounds for bed-shear stress." [abstract] — [Taylor & Francis listing](https://informahealthcare.com/doi/abs/10.1080/00221686.2014.971449); [IAHR listing](https://www.iahr.org/library/info?pid=4361)
- **Vanoni & Brooks.** A 2025 study cited with Guo 2015 notes that the classic Vanoni-Brooks sidewall correction rests on an approximation that "does not work as well in very narrow flumes". [search excerpt] — [citedrive, JGR Earth Surface 2025](https://www.citedrive.com/en/discovery/generalizing-sediment-transport-experiments-from-narrow-flumes-to-wider-channels/)

### Inferences
- [Certain, arithmetic] The perimeter shares 2h/(b + 2h) at those b/h values:

  | b/h | Perimeter share | Measured wall share |
  |---|---|---|
  | 1.16 | 63.3 % | 69 % |
  | 2.9 | 40.8 % | 38 % |
  | 3.2 | 38.5 % | 36 % |
  | 5.3 to 6.0 | 25 to 27 % | 18 to 19 % |

  The measured share runs near the perimeter share around b/h 1 to 3, and well below it by b/h 5 to 6.
- [Certain, geometry] On the gorge the wall perimeter share is 42.8 % at 4.40 m and 47.9 % at 5.39 m (b/h 2.7 and 2.2), with walls at 1.5:7, close to vertical.
- [Likely] By the smooth-flume evidence, the walls carry about 0.93 to 1.0 of their perimeter share at this b/h, so 40 to 45 % of the resistance. SCM's implicit uniform stress is therefore close for the walls. The strip sum's 0 % is not.
- [Likely] Guo's bounds bear on the bed. At the centre the true bed stress lies between ρgRS (SCM) and ρghS (the strip sum, which applies ρghS on every central strip because each strip balances its own weight). The strip sum puts the bed at the upper bound and the walls at zero, the extreme case.
- [Recalled from the literature, not verified this session; check before quoting] Einstein's 1942 hydraulic-radius separation assigns the walls a hydraulic radius from a smooth-wall friction law, at the same mean velocity as the whole section, and gives the bed the rest, R_b = A_b / b. Vanoni & Brooks 1957 write it as f_b = f + (2h/b)(f − f_w). With equal friction on bed and walls, both reduce to the SCM split.

### Gaps
- The coefficients of Knight et al.'s 1984 %SF_w equation, and Knight's trapezoidal-channel equivalent, were not retrieved.
- Einstein 1942, Johnson 1942 and Vanoni & Brooks 1957 were not read; the formulas above are from memory.
- All shear-split data found are for smooth flumes with equal roughness. Rough, irregular rock walls (n 0.05) could carry more or less than their perimeter share, and no data were found.

---

## 5. Lateral (momentum-exchange) shear in compound and narrow channels and its treatment in depth-averaged models (SKM and relatives)

### Takeaway
The resistance that Wadi2D misses on the gorge is mostly lateral momentum exchange: the walls' drag carried into the core by lateral turbulence and secondary currents. The bed-area factor is a small part of it. Lateral-distribution methods carry this exchange explicitly: SKM with λ for lateral eddy viscosity and Γ for secondary flow; Spada's LHRM empirically, through a window of β = 9 depths. A 2D model resolving the cross-section carries it only through horizontal eddy viscosity and a wall-friction boundary condition. A sub-grid face sum carries it not at all.

### Cited Findings
- **SKM** derives lateral distributions of depth-mean velocity and boundary shear for any shape, including "bed-generated turbulence, lateral shear turbulence and secondary flows", validated on the SERC Flood Channel Facility. [abstract] — [Shiono & Knight 1991](https://www.cambridge.org/core/services/aop-cambridge-core/content/view/S0022112091001246)
- **The secondary-flow term** enters as a coefficient K times U_d². Shiono and Knight first set it to zero, and later work found that including it "made a significant improvement in the prediction of boundary shear stress". [search excerpts] — [Springer EFM s10652-024-10003-3](https://link.springer.com/10.1007/s10652-024-10003-3); [Springer AWS s13201-018-0663-4](https://link.springer.com/article/10.1007/s13201-018-0663-4)
- **Spada et al.:**
  - DCM neglects "the shear stresses coming from the vortices with vertical axes".
  - LHRM replaces explicit turbulent stresses by a window of β depths over which the hydraulic radius is taken; it "gives up the ambition of estimating turbulent stresses" yet is the best performer on all series.
  - Against CFX the residual differences are near the banks, where "the wall resistance is stronger and the velocity field is more sensitive to the turbulent exchange of energy with the central area", which CFX carries through secondary flows.

  [full text] — [Spada et al. 2015](https://hess.copernicus.org/preprints/12/2607/2015/hessd-12-2607-2015.pdf)
- **Tavakkol & Zarrati:** dividing a rectangular section by zero-shear lines while ignoring secondary currents leaves part of the weight unbalanced and underestimates the bed shear force. [full text] — [arXiv 1611.01608](https://arxiv.org/pdf/1611.01608)
- **TELEMAC-2D** provides a separate friction law and roughness for lateral boundaries, the 2D route by which a resolved wall's drag enters the depth-averaged momentum. [tutorial] — [hydro-informatics](https://hydro-informatics.github.io/numerics/telemac/telemac2d-steady.html)

### Inferences
- [Likely] On the gorge the decomposition is roughly this, from the section 1 numbers:

  | Contribution | Depth, m |
  |---|---|
  | Strip sum | 4.40 |
  | + walls' slant length | +0.10 |
  | + lateral exchange of the wall drag across a section of about 2.5 depths | +0.85 to +0.9, to reach 5.34 to 5.39 |

  The physics that closes the gap is lateral exchange, so the remedy for a depth-averaged sub-grid face is a section-level hydraulic radius, as HEC-RAS does at coarse faces and SCM does. A local window of order 9 depths (LHRM) is the published, calibrated middle ground. Pixel-level fixes are not enough.
- [Likely] For a sub-grid face, the choice between section and window must not depend on the cell size. That is the defect of HEC-RAS's per-face hydraulic radius: 5.28 m at 20 m against 4.70 m at 5 m. A window tied to depth (βh) and not to face width is mesh-independent by construction, which is LHRM's argument transplanted to 2D.
- [Guessing] For a 2D model that resolves the gorge in many cells, the consistent alternative is a lateral wall-friction boundary condition plus a depth-scaled horizontal eddy viscosity. I found no paper quantifying how close that gets to SCM in a section of b/h ≈ 2.5.

### Gaps
- No SKM discharge-accuracy numbers, and no values of λ or Γ for narrow deep rectangular or near-vertical-walled sections, were retrieved.
- Nothing was found that applies SKM or LHRM inside a 2D sub-grid face conveyance. That combination appears unpublished as of 2026.
- No published 2D test was found of eddy viscosity plus wall friction against measured stage in a narrow deep channel.

### Reading log (all questions)
- **Full text read this session:**
  - Volp thesis Ch. 2 friction section (pp. 17-19, 28-29) and discussion (p. 39).
  - van Ormondt et al. 2025, GMD, equations 8-17 and limitations.
  - Spada et al. 2015, HESSD, sections 1, 3.2, 4 and Table 3.
  - Tavakkol & Zarrati 2018, arXiv, sections 1-3 and Table 1.
  - Van Emelen, Zech & Soares-Frazao, UCLouvain conference paper, sections 2-3.
  - Rana documentation, 2D surface flow and simulation settings.
- **Abstract, listing or excerpt only:** Knight, Demetriou & Hamed 1984; Shiono & Knight 1991; Liao & Knight 2007; Knight, Omran & Tang 2007; Guo 2015; Kennedy et al. 2019 (summary, slides and a 1-page extended abstract); Sehili et al. 2014; Yen 2002 (via a Korean review); Seckin 2004; Stelling 2012; TUFLOW manual and FAQ; HEC-RAS forum, vendor and training material; the TELEMAC tutorial.
- **Own computations** (normal depths of the stated gorge under the strip sum, the strip sum with slant length, SCM, and LHRM at β 0.05, 1, 3, 9 and 1000) were run in the session scratchpad and are reported as inferences.
