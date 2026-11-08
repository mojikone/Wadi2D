# HEC-RAS 2D: the water level a face's hydraulic properties are read at, and cell size on sloping ground

Date: 2026-11-08. Versions: HEC-RAS 5.0 (manuals of Feb 2016), 6.0 to 6.6, and the "latest" Confluence pages, which carry a
7.0 (HEC-RAS 2025 line) version selector. Tags: [Certain] read in the primary source named; [Likely] strong inference or a
secondary source; [Guessing] gap-filling. HEC manuals are US government works; quotes are short and verbatim.

Bottom line for the report writer: **HEC's documentation never states how a face's water surface is formed from its two cells.**
It says that a face water surface exists (6.6 Diffusion Wave solution algorithm, step 5), that face area, hydraulic radius and n
are read from the face tables at it, and at which time level. The only explicit rule found, "the higher of the two neighbouring
water surface elevations", is in a 2015 practitioner blog that cites no HEC source. No HEC user option selects a face water
surface or a face conveyance method. HEC's own cell-size guidance is qualitative (smaller cells where the water-surface slope is
steep or changing) and never quantifies a storage or level bias on a slope.

## 1. At which water surface do the three solvers evaluate face area, wetted perimeter, hydraulic radius and Manning's n?

### Takeaway
All three solvers read A, P (hence R) and n from the face's own elevation table at a single face water surface per time step or
iteration; the documented choice is about the time level (theta-averaged; explicit in Diffusion Wave, semi-implicit in SWE-ELM as
now documented), not about the spatial rule. The spatial rule (upwind, higher cell, mean, interpolation) is undocumented by HEC;
the SWE-EM page defines a face depth for advection as a weighted mean of the two cells' volume depths, which is not the depth used
for the face area.

### Cited Findings
- [Certain] HEC-RAS 5.0 Hydraulic Reference Manual, Diffusion Wave solution algorithm, step 5 (p. 2-67): "Compute the
  θ-averaged water elevation H = (1-θ)Hj^n + θHj^n+1 and sub-grid bathymetry quantities that depend on it (face areas, fluid
  surface areas, hydraulic radii, Manning's n, etc.)". H carries the cell subscript j; the manual does not say which of a face's
  two cells (or what combination) sets the face's H. — [HEC-RAS 5.0 Reference Manual, PDF](https://www.hec.usace.army.mil/software/hec-ras/documentation/HEC-RAS%205.0%20Reference%20Manual.pdf)
- [Certain] Same manual, p. 2-66: the coefficients a_j "must be evaluated at time n+θ ... creating a circular dependence on the
  solution", corrected by iteration (steps 5 to 8). — [HEC-RAS 5.0 Reference Manual](https://www.hec.usace.army.mil/software/hec-ras/documentation/HEC-RAS%205.0%20Reference%20Manual.pdf)
- [Certain] Same manual (eddy viscosity, SWE): for every time step and face the hydraulic radius R "is obtained from the sub-grid
  bathymetry data. The solver must maintain a table relating the hydraulic radius to the water elevation"; Manning's n is
  likewise "interpolated from a pre-computed table". — [HEC-RAS 5.0 Reference Manual](https://www.hec.usace.army.mil/software/hec-ras/documentation/HEC-RAS%205.0%20Reference%20Manual.pdf)
- [Certain] HEC-RAS 6.6 Hydraulic Reference Manual, Diffusion Wave Equation Solver: "Note that the face areas are treated
  explicitly", which "increases the stability of the solver but reduces the accuracy for large time steps" and "limits the wetting
  and drying to one cell at a time for each time step". Solution algorithm step 5 now reads "Compute the face water surface
  elevation and subgrid bathymetry quantities that depend on it (face area, horizontal surface area, hydraulic radius, Manning's
  n, etc.)", and "the face water surface and hydraulic property tables are not updated in the outer loop (step 6)". K_k = A_k
  R_k^(2/3)/n_k and alpha_k = K_k / |grad z_s ...|^(1/2) carry no time superscript; the face water surface is not defined. — [HEC-RAS 6.6 DWE solver page](https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/6.6/theoretical-basis-for-one-dimensional-and-two-dimensional-hydrodynamic-calculations/2d-unsteady-flow-hydrodynamics/numerical-methods/diffusion-wave-equation-solver)
- [Certain] Latest (7.0-labelled) SWE-ELM page: continuity flux written u_N,k^(n+θ) A_k with no time index on A_k; "The treatment
  of the face areas is semi-implicit", which "allows for wetting and drying of multiple cells in a single time step and improves
  the accuracy of the model". Solution step 6: compute the time-averaged water surface and the sub-grid quantities that depend on it
  "(face areas, fluid surface areas, hydraulic radii, Manning's n, etc.)". The page is internally inconsistent on the level: Eq. 3
  uses z_s^(n+θ), step 6 prints z_s^(n+1/2). — [SWE-ELM solver page, latest](https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/latest/theoretical-basis-for-one-dimensional-and-two-dimensional-hydrodynamic-calculations/2d-unsteady-flow-hydrodynamics/numerical-methods/eulerian-lagrangian-shallow-water-equation-solver)
- [Certain] SWE-ELM friction: c_f is "not computed once per time step, but as many times as iterations are required for
  convergence", θ-weighted between n and n+1 (Eq. 12 carries c_f,f^(n+θ)); the velocity in the friction law is fully implicit.
  The diffusion face depth is h̄_f = α_f^L h_L + α_f^R h_R with α_f^L = Δx_f^L/(Δx_f^L + Δx_f^R) (Eq. 5); the h_f^n in the wind term
  is not defined. — [SWE-ELM solver page, latest](https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/latest/theoretical-basis-for-one-dimensional-and-two-dimensional-hydrodynamic-calculations/2d-unsteady-flow-hydrodynamics/numerical-methods/eulerian-lagrangian-shallow-water-equation-solver)
- [Certain] SWE-EM page (latest): "The water depth at the face ... is calculated as a weighted average of the average water depths
  of the left and right cells", h̄_f = α_f^R h_R + α_f^L h_L, with h_i = Ω_i / A_i^W (cell volume over wetted plan area) and the
  same Δx weights, said to be "based on the area of the control volume". This h̄_f enters the advection terms; face flows are
  Q_k = A_k u_N,k and the page does not say how A_k is evaluated. Upwinding is applied only to velocities in the advection
  ("Upwinded velocities are taken at the cell centers upwind of the faces"). — [SWE-EM solver page, latest](https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/latest/theoretical-basis-for-one-dimensional-and-two-dimensional-hydrodynamic-calculations/2d-unsteady-flow-hydrodynamics/numerical-methods/eulerian-shallow-water-equation-solver)
- [Certain] Momentum Conservation page (latest): C_D = n²g/R^(1/3), c_f = n²g|V|/R^(4/3); nothing on how R or h is taken at a
  face, nothing on a sub-grid friction integral. — [Momentum Conservation, latest](https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/latest/theoretical-basis-for-one-dimensional-and-two-dimensional-hydrodynamic-calculations/2d-unsteady-flow-hydrodynamics/hydraulic-equations/momentum-conservation)
- [Certain] Subgrid Bathymetry page (latest): A_f(z_s) = ∫ from z_b to z_s of W_f(z) dz with W_f piecewise constant; "From these
  variables other hydraulic variables such as the hydraulic radius and conveyance can be easily computed." No statement on which
  z_s is used at a face. — [Subgrid Bathymetry, latest](https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/latest/theoretical-basis-for-one-dimensional-and-two-dimensional-hydrodynamic-calculations/2d-unsteady-flow-hydrodynamics/subgrid-bathymetry)
- [Likely, secondary, pre-release] Chris Goodell (Kleinschmidt, "The RAS Solution" blog, 18 Feb 2015, written before the official
  5.0 release, no HEC document cited): "the cell face hydraulic parameters between the two cell centers is based on the higher of the
  two neighboring water surface elevations"; he adds that averaging the two would be more physically sound but errs where high
  ground lies between the centres, and links the rule to fragmented inundation on steep slopes with large cells. — [Goodell 2015, The RAS Solution](https://therassolution.kleinschmidtgroup.com/ras-post/2d-troubleshooting-fragmented-inundation/)
- [Certain] No user option for the face level or the face conveyance method: the 2D Computation Options page (latest, 7.0) lists
  equation set, solver cores, time slices, boundary-condition volume check, theta (1.0 default, 0.5-1.0), theta warm-up, water-
  surface and volume tolerances (0.01 ft), maximum iterations (20), advanced convergence (max 0.15 ft, RMS 0.002 ft, stalling 1 %),
  turbulence, matrix solver and secondary-flow options, and nothing on face water surface, face conveyance or hydraulic radius. — [2D Computation Options, latest](https://www.hec.usace.army.mil/confluence/rasdocs/r2dum/latest/running-a-model-with-2d-flow-areas/2d-computation-options-and-tolerances)
- [Certain] The only face-property option is for roughness: one n per face from the face centroid (default) or "Spatially Varied
  Manning's N", a composite n as a function of elevation. — [Creating Hydraulic Property Tables, latest](https://www.hec.usace.army.mil/confluence/rasdocs/r2dum/latest/development-of-a-2d-or-combined-1d-2d-model/creating-hydraulic-property-tables-for-2d-flow-areas)
- [Certain] The solver carries a per-face level as an output: the HDF5 output page lists "Face WSEL" among the optional variables,
  without a definition. [Likely, from reader code] HEC-RAS 6.6 Diffusion-Wave runs leave the `Face Water Surface` dataset as an
  empty placeholder, so the stored face level is a SWE-solver output. — [2D Output File (HDF5), latest](https://www.hec.usace.army.mil/confluence/rasdocs/r2dum/latest/viewing-2d-or-1d-2d-output-using-hec-ras-mapper/2d-output-file-hdf5-binary-file); [RAS-Commander HdfResultsMesh.py](https://github.com/gpt-cmdr/ras-commander/blob/main/ras_commander/hdf/HdfResultsMesh.py)

### Inferences
- [Likely] The 5.0 to 6.6 change in wording ("θ-averaged water elevation" to "face water surface elevation") shows that by 6.6
  the code forms an explicit per-face level before reading the face table; HEC documents its time level (θ-averaged, frozen in the
  Diffusion Wave outer loop) but not its spatial construction.
- [Likely] If the 2015 "higher of the two" rule still holds, HEC-RAS reads a face exactly as Wadi2D does under downhill flow (the
  upwind, higher cell's level over the face's own table), so on a slope S with spacing dx its face area is read about S·dx/2 too
  high, the same bias. It is consistent with HEC's documented face-minimum blocking (flow cannot cross until a neighbour's surface
  passes the face low point) and with the "patchwork" inundation HEC itself describes in steep terrain with large cells (see 2).
  It is not confirmed by any HEC document read.
- [Likely] HEC-RAS's implicit θ-averaging does not remove such a bias at steady or slowly varying flow: θ chooses the time
  level, not the location. In Diffusion Wave the face area is explicit (time n), in SWE-ELM semi-implicit; neither is a mean of the
  two cells' levels as documented.
- [Guessing] The SWE-EM weighting h̄_f = α^R h_R + α^L h_L with α^L = Δx^L/(Δx^L+Δx^R) puts more weight on the cell whose share of
  the face's control volume is larger (a control-volume mean, as the page says), not a linear interpolation to the face, and it
  uses volume depths Ω/A^W, not levels. If the face area A_k followed the same rule, a SWE-EM face would sit near the two-cell mean,
  which per the brief fixes uniform flow but hurts supercritical flow; the page does not say A_k does.
- [Likely] The decisive test is cheap: on a tilted plane or a uniform-slope channel in HEC-RAS 6.6 with SWE-ELM and SWE-EM, write
  `Face Water Surface` and compare it, face by face, with the two adjacent cells' `Water Surface`; repeat in a Diffusion Wave run,
  which leaves that dataset empty in 6.6, by reading `Face Flow` against A(z) from the face table.

### Gaps
- No HEC document defines the face water surface (upwind, higher, mean, distance-weighted). Searched: 5.0 Reference and 2D User's
  Manuals (full text), 6.0 mesh page, 6.6 DWE page, latest ELM, EM, Momentum, Subgrid Bathymetry, 2D options, HDF output pages,
  the 2D sediment "Subgrid Concept" page, and the HEC training deck on sub-grid bathymetry. All silent on the spatial rule.
- Whether the 2015 "higher of the two" rule describes 6.x or 7.0 is unknown; the post predates the 5.0 release and cites no source.
- When the SWE-ELM face area changed from explicit (5.0 manual, A_k^n) to semi-implicit (latest page) is not documented in any release
  note found; 6.1 to 6.6 "Problems Repaired" lists were not read.
- HEC-RAS 2025's new solver documentation was not checked beyond the pages labelled "latest".

## 2. What do HEC's manuals, release notes, training and papers say about cell size on steep slopes, water surfaces too low or too high in coarse cells, face conveyance options and the filter tolerances?

### Takeaway
HEC's guidance is qualitative and unchanged from 5.0 to 7.0: size cells to resolve the water-surface slope and its changes, use
smaller cells where slopes are steep or changing, align faces with high ground. HEC acknowledges a steep-terrain, large-cell
artefact only in mapping (the rendered surface showing more or less water than computed, and patchwork inundation), and warns
against steep cells down embankments. Nowhere does HEC quantify a storage, level or attenuation bias of coarse cells on a slope.
There is no face-conveyance method option; conveyance is always A R^(2/3)/n from the face table, with thinning tolerances.

### Cited Findings
- [Certain] 5.0 2D User's Manual (CPD-68, Feb 2016) and the 6.0 mesh page, same text: "In general, the cell size should be based
  on the slope of the water surface in a given area, as well as barriers to flow within the terrain"; flat, slowly changing slopes
  allow larger cells; "Steeper slopes, and localized areas where the water surface elevation and slope change more rapidly will
  require smaller grid cells". Sub-grid tables mean the terrain enters storage and conveyance "regardless of the computational cell
  size. However, there are still limits to what cell size should be used". — [HEC-RAS 5.0 2D User's Manual, PDF](https://www.hec.usace.army.mil/software/hec-ras/documentation/HEC-RAS%205.0%202D%20Modeling%20Users%20Manual.pdf); [r2dum 6.0, Development of the 2D Computational Mesh](https://www.hec.usace.army.mil/confluence/rasdocs/r2dum/6.0/development-of-a-2d-or-combined-1d-2d-model/development-of-the-2d-computational-mesh)
- [Certain] 7.0 "Selecting an Appropriate Grid Size and Time Step": "A single water surface elevation is computed in the center of
  each cell", so the larger the cell "the further apart are the computed values of the water surface" and the slope is "averaged
  over longer distances"; "This is acceptable for some areas, but not appropriate for others"; where slope and velocity vary rapidly,
  smaller cells. No steep-slope rule, no equation-set recommendation for steep or supercritical flow; "the Diffusion Wave equations
  are more forgiving numerically than the SWE". Courant guidance: SWE-ELM C <= 1 (up to 3), SWE-EM C <= 1 (max 1), Diffusion Wave
  C <= 2 (up to 5), C <= 1 for very rapidly rising hydrographs. — [Selecting Grid Size and Time Step, latest](https://www.hec.usace.army.mil/confluence/rasdocs/r2dum/latest/running-a-model-with-2d-flow-areas/selecting-an-appropriate-grid-size-and-time-step)
- [Certain] 5.0 2D User's Manual, RAS Mapper render modes: the Sloping mode "can also have the appearance of more water or less
  water volume in the 2D cells than what was computed in the simulation. This problem generally occurs in steep terrain with large
  2D grid cells." The Horizontal mode fills each cell to its computed level and gives a "patchwork" of isolated inundation, "more
  visible in areas of steep terrain, using large grids cells, with shallow flood depths." — [HEC-RAS 5.0 2D User's Manual, ch. 5](https://www.hec.usace.army.mil/software/hec-ras/documentation/HEC-RAS%205.0%202D%20Modeling%20Users%20Manual.pdf)
- [Certain] Same manual, structures: "don't put very small cells down the face of a steep embankment because the small boundary cells
  may end up with a transitional water surface" between headwater and tailwater; on a levee, steep cells on the back side "could
  cause the model to have stability issues when flow overtops the levee (i.e. the flow may appear to be going over a water fall)",
  so make cells large enough to take in the embankment slope. — [HEC-RAS 5.0 2D User's Manual, ch. 3](https://www.hec.usace.army.mil/software/hec-ras/documentation/HEC-RAS%205.0%202D%20Modeling%20Users%20Manual.pdf)
- [Certain] Same manual, ch. 1 and 3: a channel narrower than the cell (500 ft cells, canals under 100 ft, 2 ft terrain) still
  carries flow through the face tables "in a 1D-type of mode"; for two-dimensional velocities and "varying water surface
  elevations" in the channel "a cell size smaller than the channel width is needed". — [HEC-RAS 5.0 2D User's Manual](https://www.hec.usace.army.mil/software/hec-ras/documentation/HEC-RAS%205.0%202D%20Modeling%20Users%20Manual.pdf)
- [Certain] Filters (6.0 mesh page): cell elevation-volume filter, fewer points "reduce the accuracy of the elevation volume
  relationship"; face profile filter thins the points extracted along each face, no accuracy statement; face area-elevation filter
  reduces "the accuracy of the face hydraulic property relationships"; face conveyance tolerance ratio, "A higher tolerance will
  result in fewer points in the hydraulic property tables of the cell faces, but less hydraulic accuracy for the flow movement across
  the faces". Defaults 0.01 ft for the three filters and 0.02 for the conveyance ratio (midpoint conveyance against linear
  interpolation; a point inserted above 2 %). — [r2dum 6.0, Development of the 2D Computational Mesh](https://www.hec.usace.army.mil/confluence/rasdocs/r2dum/6.0/development-of-a-2d-or-combined-1d-2d-model/development-of-the-2d-computational-mesh)
- [Certain] "Face conveyance (tables versus hydraulic radius)": no such option exists in the pages read. The face table stores
  elevation, area, wetted perimeter and n, and conveyance is derived as K = A R^(2/3)/n with R = A/P, one section per face. — [DWE solver page 6.4](https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/6.4/theoretical-basis-for-one-dimensional-and-two-dimensional-hydrodynamic-calculations/2d-unsteady-flow-hydrodynamics/numerical-methods/diffusion-wave-equation-solver); [pyHMT2D RAS_2D_Data.py](https://github.com/psu-efd/pyHMT2D/blob/main/pyHMT2D/Hydraulic_Models_Data/RAS_2D/RAS_2D_Data.py)
- [Certain] HEC training, Ackerman and Jensen, "HEC-RAS Subgrid Bathymetry" (HEC PROSPECT deck, 2024): the premise is that "Water
  levels usually vary much more smoothly than the terrain" and the approach "Utilize a grid resolution sufficient to resolve the
  hydraulics". EU (UK EA) Test 5 at 25, 50 and 100 m: 30,340 cells, 2 s step, 7 min 34 s; 7,460 cells, 5 s, 1 min 38 s; 1,809
  cells, 10 s, 13 s (full Saint-Venant). A levee-breach case at 25, 50, 100 and 200 ft (7.6 to 61 m), Diffusion Wave and full
  equations, 21,719 to 321 cells; hydrographs shown as figures only; adding breaklines brings the grid sizes together at one
  location. No slope-bias statement. — [Ackerman and Jensen, HEC training PDF](https://www.hec.usace.army.mil/confluence/prospect/files/179605245/187668864/1/1711733317029/1.3+-+Subgrid+Bathymetry.pdf)
- [Certain] Subgrid Bathymetry page: the method suits many applications "because the free water surface is smoother than the
  bathymetry"; no limit stated for large cells or slopes. — [Subgrid Bathymetry, latest](https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/latest/theoretical-basis-for-one-dimensional-and-two-dimensional-hydrodynamic-calculations/2d-unsteady-flow-hydrodynamics/subgrid-bathymetry)
- [Likely, secondary] Goodell 2015: fragmented inundation appears "where cells are too large on a steep slope"; the mapped against
  computed depth difference at a face "can be considered a schematization error"; the cure is smaller cells and cells aligned with
  the flow. — [Goodell 2015, The RAS Solution](https://therassolution.kleinschmidtgroup.com/ras-post/2d-troubleshooting-fragmented-inundation/)

### Inferences
- [Likely] HEC treats the one-level-per-cell limit on slopes as a resolution problem for the user (refine where the water-surface
  slope is large or changing) and as a mapping artefact, not as a conveyance or storage bias to be corrected in the scheme. The
  brief's mechanism (face read too high, cells too low, less attenuation) has no counterpart in HEC's documentation.
- [Likely] HEC's mapping warning (the sloping render shows more or less water than computed in steep terrain with large cells) is
  the visible half of the same geometry: a level per cell on a slope cannot be both the cell's volume level and the level at its
  faces.

### Gaps
- No HEC manual, release note or training read gives a numerical rule (such as dx against depth and slope) for cell size on steep
  ground, or states the sign of the error of coarse cells on a slope for storage, level or peak.
- 6.1 to 6.6 and 2025 release notes were not read in full; a search found no release note on face hydraulic-radius or face-level
  changes in 6.x.
- The HEC PROSPECT deck's hydrograph comparisons are figures; their values were not extractable.

## 3. Published mesh-convergence or cell-size studies of HEC-RAS 2D on steep or sloping ground, with numbers

### Takeaway
One open, controlled study on steep ground was found: Costabile et al. (2020), HEC-RAS 5.0.7 rain-on-grid on a 13.75 km2
catchment of 24.6 % mean slope. With full momentum, coarsening the same triangular mesh from 5 to 10 m lowered HEC-RAS's outlet peak
by about 4 % while the reference finite-volume model moved under 0.7 %; the diffusion wave read about 12 % high and faster, the gap
narrowing on the coarser mesh. HEC-RAS coarse cells therefore attenuated more there, not less. A 2026 study on mild ground found
peaks stable within 2.3 %. No study isolating storage or level bias of HEC-RAS cells on a uniform slope was found.

### Cited Findings
- [Certain] Costabile, Costanzo, Ferraro, Macchione, Petaccia (2020), Water 12(9), 2326, doi 10.3390/w12092326: HEC-RAS 5.0.7 against
  the authors' 2D fully dynamic finite-volume model (SWE-FVM); Scuropasso sub-catchment, 13.75 km2, mean slope 24.57 % (basin 12.95 %);
  the same triangular meshes in both models, 5 m (1,293,762 elements) and 10 m (323,161); HEC-RAS's sub-grid tables in use. — [Costabile et al. 2020, Water](https://www.mdpi.com/2073-4441/12/9/2326)
- [Certain] Same paper, Table 2, outlet peak (m3/s) and time to peak (h):
  T 30 yr: HEC-RAS full momentum 152.8 (5 m) and 147.0 (10 m), -3.8 %; SWE-FVM 152.8 and 151.8, -0.7 %; HEC-RAS diffusion wave 170.6
  and 163.2. T 200 yr: full momentum 242.3 and 232.9, -3.9 %; SWE-FVM 241.9 and 242.0; diffusion wave 270.7 and 261.5. Times to peak,
  full momentum 2.92 to 2.95 h (30 yr) and 2.83 to 2.87 h (200 yr), SWE-FVM 2.90 to 2.92 and 2.80 to 2.82. The authors: on the 10 m
  grid the HEC-RAS peak is "slightly lower (approximately 4%)"; the diffusion wave overestimates peaks "about 12 %" and gives faster
  waves; "These differences seem to decrease with the increase of the grid size", explained by the diffusion-wave velocity depending
  almost entirely on terrain slope. — [Costabile et al. 2020, Water](https://www.mdpi.com/2073-4441/12/9/2326)
- [Certain] Same paper: flooded area above 0.10 to 0.20 m depth thresholds, HEC-RAS over SWE-FVM by 5 to 10 % (5 m) and 20 to 30 %
  (10 m), for example T 30 yr at 0.10 m: 0.43 against 0.40 km2 (5 m), 0.59 against 0.45 km2 (10 m); at 0.05 m HEC-RAS is lower and its
  low-order streams fragment into disconnected patches; hazard class H1 is overestimated, which the authors ascribe to "the way HEC-RAS
  redistributes the water depth in the computational cell, defined as the sub-grid approach". — [Costabile et al. 2020, Water](https://www.mdpi.com/2073-4441/12/9/2326)
- [Certain] Paşa (2026), Sci 8(8), 219, doi 10.3390/sci8080219: calibrated HEC-RAS 2D against TUFLOW Classic, 15 to 55 ft cells, a
  low-gradient domain (maximum stream slope 0.0018 ft/ft, domain basin slope 0.118), inflow-driven. HEC-RAS outlet peak, observed event:
  4,466.15 cfs (15 ft), 4,431.36 (25 ft), 4,365.50 (55 ft), -2.3 % over the range; design floods within about 0.2 % (Q100 30,409.5 at
  15 ft, 30,433.3 at 55 ft). The author: HEC-RAS "retained greater depth consistency, plausibly because its sub-grid property tables
  preserve cell-scale volume and conveyance information"; no grid finer than 15 ft and no grid convergence index. HEC-RAS version and
  equation set not found in the extracted text. — [Paşa 2026, Sci](https://www.mdpi.com/2413-4155/8/8/219)
- [Likely, abstract or search snippet only, not read] A Nepal study (Kankai River) reports that the steeper the river, the more
  sensitive the water-surface elevation to mesh size, and that flow parameters are less sensitive to mesh size than inundation
  extent. — [ResearchGate, Kankai River Basin](https://www.researchgate.net/publication/359023789_Optimization_of_Model_Parameters_of_HEC-RAS_2D_Model_on_Flood_Inundation_Mapping_A_Case_Study_of_Kankai_River_Basin)
- [Likely, snippet only] A Teton Dam failure study (GeoClaw and HEC-RAS) reports that the mesh controlled the peak arrival time
  with similar peak flows. — [arXiv 2206.00766](https://arxiv.org/pdf/2206.00766)

### Inferences
- [Likely] On the one steep case with numbers, HEC-RAS full momentum shows the opposite sign to the brief's mechanism: the coarser
  mesh gives a lower peak (more attenuation), on triangles of 5 and 10 m on a 24.6 % mean slope. That fits a face read at the higher
  cell's level only if other coarse-mesh effects (lost hillslope connectivity, the fragmented low-order streams the authors map,
  more storage in the coarse cells) outweigh it, or it fits a face rule that is not the upwind level. The study cannot tell which.
- [Guessing] The project's own squares behave as HEC-RAS does there (20 m 1,835, 10 m 1,871, 5 m 1,887 m3/s, coarse lower); it is the
  aligned cells that converge from above. So HEC-RAS's published behaviour matches Wadi2D's squares, not its aligned cells.
- [Likely] Mild-slope studies (Paşa 2026) show HEC-RAS peaks insensitive to cell size, as expected when S·dx/2 is small against depth.

### Gaps
- No published HEC-RAS 2D study was found that varies cell size on a uniform slope or a sinuous incised channel and reports stored
  volume, cell level against the true surface, or attenuation of a flood peak as functions of S·dx.
- No HEC-authored grid-convergence study on steep ground with tabulated numbers was found; HEC's training shows figures only.
- The Kankai and Teton results were seen only in abstracts or snippets; their numbers were not read.

## 4. How does HEC-RAS treat a partly wet sub-grid face, and does it use an upwind face depth for the continuity flux?

### Takeaway
A partly wet face is handled entirely by its elevation table: the area grows from zero at the face's lowest profile point, so a face
passes nothing until a level above that point is applied to it. The continuity flux is u_N A_k with A_k from the table at the face
level: explicit (time n) in the Diffusion Wave solver, semi-implicit in SWE-ELM as now documented. No HEC document says the
continuity area comes from an upwind depth; SWE-EM upwinds only the advected velocity and uses a weighted mean of the cells' volume
depths for its face depth.

### Cited Findings
- [Certain] Face tables: A_f(z_s) = ∫ from z_b to z_s of W_f(z) dz, W_f piecewise constant, A_f piecewise linear, so a face is wet
  over only part of its length at low stage by construction. — [Subgrid Bathymetry, latest](https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/latest/theoretical-basis-for-one-dimensional-and-two-dimensional-hydrodynamic-calculations/2d-unsteady-flow-hydrodynamics/subgrid-bathymetry)
- [Certain] Each face "is evaluated similar to a cross section" and pre-processed into tables of elevation against wetted perimeter,
  area and roughness; with breaklines on the banks "flow does not spill out of the channel until the water is high enough to cross
  over the outer cell faces". — [r2dum 6.0, Advantages and Capabilities](https://www.hec.usace.army.mil/confluence/rasdocs/r2dum/6.0/introduction/hec-ras-2d-modeling-advantages-capabilities); [r2dum 6.0, mesh page](https://www.hec.usace.army.mil/confluence/rasdocs/r2dum/6.0/development-of-a-2d-or-combined-1d-2d-model/development-of-the-2d-computational-mesh)
- [Certain] HEC training: "Cells can be partially wet"; the face table "Controls flow into and out of cell". — [Ackerman and Jensen, HEC training PDF](https://www.hec.usace.army.mil/confluence/prospect/files/179605245/187668864/1/1711733317029/1.3+-+Subgrid+Bathymetry.pdf)
- [Certain] Diffusion Wave (6.6): face areas explicit, wetting and drying one cell per time step; dry cells remain dry until water
  flows into them. SWE-ELM (latest): face areas semi-implicit, multiple cells may wet in one step; dry faces keep zero velocity until
  water flows into them. — [DWE 6.6](https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/6.6/theoretical-basis-for-one-dimensional-and-two-dimensional-hydrodynamic-calculations/2d-unsteady-flow-hydrodynamics/numerical-methods/diffusion-wave-equation-solver); [SWE-ELM, latest](https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/latest/theoretical-basis-for-one-dimensional-and-two-dimensional-hydrodynamic-calculations/2d-unsteady-flow-hydrodynamics/numerical-methods/eulerian-lagrangian-shallow-water-equation-solver)
- [Certain] SWE-EM: Q_k = A_k u_N,k; the face depth for advection is the distance- or control-volume-weighted mean of the cells'
  Ω/A^W; inflows Q^- = min(s Q_k, 0) select upwind velocities for the advection only. Nothing on an upwind depth or area for the
  mass flux. — [SWE-EM, latest](https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/latest/theoretical-basis-for-one-dimensional-and-two-dimensional-hydrodynamic-calculations/2d-unsteady-flow-hydrodynamics/numerical-methods/eulerian-shallow-water-equation-solver)
- [Likely, secondary] Goodell 2015: the face parameters follow the higher of the two cell levels, which for flow downhill is the
  upwind cell. — [Goodell 2015, The RAS Solution](https://therassolution.kleinschmidtgroup.com/ras-post/2d-troubleshooting-fragmented-inundation/)

### Inferences
- [Likely] For a partly wet face, the brief's "level over the face's own invert" is what HEC's table construction does: A is the
  integral of the wetted width from the face's lowest profile point up to the applied level. The open question is only which level
  is applied, which HEC does not document.
- [Likely] A rule "higher of the two levels" equals the upwind level whenever flow runs downhill, so HEC-RAS would carry the same
  continuity flux area as an upwind-depth scheme in all ordinary flood flow, without stating it in those words; the difference
  would show only in adverse-slope flow, where the higher cell is downstream.

### Gaps
- No HEC statement on whether the continuity area A_k uses an upwind, higher-cell or averaged level.
- How the semi-implicit SWE-ELM face area is linearised (Newton update of A_k against the level) is not written out.
- The partly wet face's wetted perimeter and n under "Spatially Varied Manning's N" are described as composite by wetted-perimeter
  weights, but how n varies as a face wets from one end is not stated beyond being a function of elevation.
