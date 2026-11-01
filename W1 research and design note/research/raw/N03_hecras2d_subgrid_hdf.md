# N03 HEC-RAS 2D sub-grid property tables and the geometry and plan HDF5 layout

Date: 2026-10-29

## Scope

How HEC-RAS 6.x builds the per-cell elevation-volume curve and the per-face property tables (elevation, area, wetted perimeter,
Manning's n; conveyance derived), what "face minimum elevation" does to the flux, how the three solvers (Diffusion Wave, SWE-ELM,
SWE-EM) consume face area and conveyance, the time-step rules, the exact HDF5 dataset paths in `.g0x.hdf` (geometry) and `.p0x.hdf`
(plan results) as read by rashdf, pyHMT2D and RAS-Commander, the layout differences across 5.0.7 and 6.0-6.6, and how a square-cell
mesh is produced in RAS Mapper so that Wadi2D's own table builder can be checked one to one against RAS.

Sources: HEC Confluence manuals (2D Modeling User's Manual 6.0/6.2/6.5/latest, RAS Mapper User's Manual 6.0, Hydraulic Reference
Manual pages, labelled "latest" = 7.0 on the site but with version selectors back to 6.0), the HEC-RAS 5.0 Hydraulic Reference
Manual PDF (text extracted locally, chapter 2), the source code of rashdf (fema-ffrd), pyHMT2D (psu-efd) and RAS-Commander
(gpt-cmdr), the RAS-Commander pull request on the legacy 6.0-6.3 log table, the 6.6 release notes, and one open paper (arXiv
1412.0966) for sub-grid application numbers. Ten distinct primary sources, 24 pages/files. Casulli (2009) and Sehili et al. (2014)
are paywalled and were not read; see Open issues. The web-search budget of the session was exhausted near the end, so three
secondary checks listed under Open issues were not made.

Confidence tags: [Certain] read in a primary source; [Likely] strong inference or secondary source; [Guessing] gap-filling.
Quotes are at most 25 words and are verbatim from the source named.

## Findings

### A. What the pre-processor builds (cells and faces)

1. Every cell gets an elevation-volume curve computed from the full-resolution terrain inside the cell polygon, every face gets
   a table of elevation versus wetted perimeter, area and roughness; both are built by the RAS Mapper 2D pre-processor and
   re-built automatically if the mesh or the Manning's n changes. [Certain]
   "The 2D mesh pre-processor computes a detailed elevation-volume relationship for each cell."
   https://www.hec.usace.army.mil/confluence/rasdocs/r2dum/latest/development-of-a-2d-or-combined-1d-2d-model/creating-hydraulic-property-tables-for-2d-flow-areas

2. The face is treated as a cross section: the pre-processor extracts the terrain profile along the face line, and flow between
   the two cells is computed from that profile's tables, so the terrain detail acts on storage and conveyance regardless of
   cell size. [Certain]
   "detailed hydraulic property curves for each cell face (elevation vs. wetted perimeter, area, and roughness)"
   https://www.hec.usace.army.mil/confluence/rasdocs/r2dum/6.0/development-of-a-2d-or-combined-1d-2d-model/development-of-the-2d-computational-mesh
   Also: "each computational cell face is evaluated similar to a cross section"
   https://www.hec.usace.army.mil/confluence/rasdocs/r2dum/6.0/introduction/hec-ras-2d-modeling-advantages-capabilities

3. The cell curve is stored as a piecewise-constant wetted (plan) area between table elevations, which makes the cell volume
   piecewise linear and exact between breakpoints; the face curve is a piecewise-constant wetted width, so the face area is
   piecewise linear. The Reference Manual says hydraulic radius and conveyance are then "easily computed", i.e. derived, not
   stored. [Certain]
   "The cell volume curves can be described exactly from relatively simple piece-wise linear curves"
   https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/theoretical-basis-for-one-dimensional-and-two-dimensional-hydrodynamic-calculations/2d-unsteady-flow-hydrodynamics/subgrid-bathymetry

4. The stored face table has exactly four columns, elevation, area, wetted perimeter, Manning's n; the cell table has two,
   elevation and volume; the cell plan area is a separate per-cell scalar. The readers of all three libraries unpack exactly
   these columns. [Certain]
   "Four columns: first column-elevation, second column-area third column-wetted perimeter, fourth column-Manning's n (a constant as of now RAS version <=6)"
   https://github.com/psu-efd/pyHMT2D/blob/main/pyHMT2D/Hydraulic_Models_Data/RAS_2D/RAS_2D_Data.py
   "Cell surface area is stored separately in 'Cells Surface Area' dataset (one value per cell), not in the elevation-volume table."
   https://github.com/gpt-cmdr/ras-commander/blob/main/ras_commander/hdf/HdfMesh.py

5. Face conveyance is a single-section value, K = A R^(2/3) / n with R = A / P from the stored columns (unit coefficient 1.486 in
   US units, 1.0 in SI). RAS does not integrate conveyance pixel by pixel along the face; the face profile only sets A(z) and
   P(z). [Certain]
   "hydraulic radius R which is obtained from the sub-grid bathymetry data. The solver must maintain a table relating the hydraulic radius to the water elevation"
   HEC-RAS 5.0 Hydraulic Reference Manual, p. 2-69, https://www.hec.usace.army.mil/software/hec-ras/documentation/HEC-RAS%205.0%20Reference%20Manual.pdf
   and K_k = A_k R_k^(2/3) / n_k on https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/6.4/theoretical-basis-for-one-dimensional-and-two-dimensional-hydrodynamic-calculations/2d-unsteady-flow-hydrodynamics/numerical-methods/diffusion-wave-equation-solver

6. Manning's n per face: by default one value, taken from the land-cover and calibration-region layers at the face centroid,
   so the fourth column is constant down the table; with the "Spatially Varied Manning's n" option the pre-processor computes a
   composite n per elevation from the wetted-perimeter weights of the land-cover segments along the face, constant once the face
   is fully wet. [Certain]
   "The second option (Spatially Varied Manning's N) computes a composite Manning's n values as a function of elevation."
   https://www.hec.usace.army.mil/confluence/rasdocs/r2dum/latest/development-of-a-2d-or-combined-1d-2d-model/creating-hydraulic-property-tables-for-2d-flow-areas
   Solver side: "The Manning's n, also depends on the sub-grid bathymetry. For every time-step and for every face this quantity is interpolated from a pre-computed table."
   HEC-RAS 5.0 Hydraulic Reference Manual p. 2-69 (same PDF as 5).

7. Table thinning is controlled by three filter tolerances, all defaulting to 0.01 ft: "Cell Elev-Vol Filter Tol" (points of the
   cell curve), "Face Profile Filter Tol" (terrain points extracted along the face), "Face Area-Elev Filter Tol" (points of the
   face table). Larger values speed the run and lose accuracy. [Certain]
   "The default tolerance for filtering these points is 0.01 ft."
   https://www.hec.usace.army.mil/confluence/rasdocs/r2dum/6.0/development-of-a-2d-or-combined-1d-2d-model/development-of-the-2d-computational-mesh

8. A fourth control, "Face Conveyance Tol Ratio" (default 0.02), re-densifies the face table: conveyance is computed at every
   table elevation, then at the midpoint between neighbours; where the midpoint value differs from linear interpolation by more
   than 2 % a point is inserted. So the table breakpoints are chosen by conveyance error, not by a fixed dz. [Certain]
   "The default value is 0.02, which represents a 2% change."
   same URL as 7.

9. Porosity (6.6 "Porosity and Flow Drag" layers) enters the same tables multiplicatively: cell wetted area = cell porosity x
   porosity-free area, face wetted width = face porosity x porosity-free width, and the wetted perimeter the same way; cell and
   face porosity are piecewise constant in elevation. [Certain]
   "The face wetted width is described with the piecewise constant curves"
   same URL as 3.

### B. Face minimum elevation and blocking

10. A face's lowest profile point is stored per face ("Faces Minimum Elevation"), the cell's lowest terrain point per cell
    ("Cells Minimum Elevation"); below the face minimum the face area A_f(z_s) = integral of W_f from z_b is zero, so the mass
    flux u_N A_k and the DWE conveyance vanish: no flow crosses a face until the water surface in a neighbour exceeds the face's
    low point. This is the HEC-RAS mechanism for "faces aware of topography". [Certain]
    "flow does not spill out of the channel until the water is high enough to cross over the outer cell faces"
    https://www.hec.usace.army.mil/confluence/rasdocs/r2dum/6.0/development-of-a-2d-or-combined-1d-2d-model/development-of-the-2d-computational-mesh
    Dataset names: `{base_path}/Faces Minimum Elevation`, `{base_path}/Cells Minimum Elevation`
    https://github.com/gpt-cmdr/ras-commander/blob/main/ras_commander/hdf/HdfMesh.py

11. The barrier is the terrain along the straight face line (or the breakline polyline the face follows), not a crest profile
    object: a breakline only aligns faces with the ridge, after which the terrain profile along the face carries the high ground.
    Faces that follow a breakline can be polylines; the intermediate vertices are stored in "Faces Perimeter Info/Values".
    [Certain]
    "Faces Perimeter Values rows when the count is positive, then its end point"
    https://github.com/gpt-cmdr/ras-commander/blob/main/ras_commander/hdf/HdfMesh.py

12. Face areas enter the mass equation explicitly (A_k^n), which "limits the wetting and drying to one cell at a time for each
    time step"; a dry cell has all a_ij = 0 and keeps its water surface until an inflow arrives. [Certain]
    "limits the wetting and drying to one cell at a time for each time step"
    https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/6.4/theoretical-basis-for-one-dimensional-and-two-dimensional-hydrodynamic-calculations/2d-unsteady-flow-hydrodynamics/numerical-methods/diffusion-wave-equation-solver
    "dry cells remain dry until water flows into them" (HEC-RAS 5.0 Reference Manual p. 2-66).

13. Dry faces carry zero velocity by construction of the momentum equation in the limit h -> 0; there is no minimum-depth
    threshold in the documentation, wetting is "continuous and consistent with the equations". [Certain]
    "dry faces continue to have zero velocity until water flows into them."
    https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/latest/theoretical-basis-for-one-dimensional-and-two-dimensional-hydrodynamic-calculations/2d-unsteady-flow-hydrodynamics/numerical-methods/eulerian-lagrangian-shallow-water-equation-solver

### C. How the solvers use area and conveyance

14. All three solvers share the finite-volume mass equation on the cell volume curve: (Omega_i^(n+1) - Omega_i^n)/dt + sum_k
    s_ik u_N,k^(n+theta) A_k^n = Q_i, and solve the resulting mildly non-linear system for the water surface with a Newton-like
    iteration whose Jacobian is the diagonal matrix of cell wet surface areas (the derivative of the volume curve). [Certain]
    "The continuity equation is discretized using finite volume approximations."
    same URL as 13; 5.0 manual eq. 2-128 and 2-155.

15. Diffusion Wave: the face normal velocity is u_N,k = -(alpha_k / A_k) (dz_s/dx_N ...) with alpha_k = K_k / |grad z_s|^(1/2)
    and K_k = A_k R_k^(2/3)/n_k, i.e. the face conveyance divided by the square root of the water-surface slope between the two
    cell centres across the face (distance dx_N). The scheme is unconditionally stable for theta in [1/2, 1]. [Certain]
    "Flow movement is driven by a barotropic pressure gradient balanced by bottom friction."
    https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/latest/theoretical-basis-for-one-dimensional-and-two-dimensional-hydrodynamic-calculations/2d-unsteady-flow-hydrodynamics/hydraulic-equations/diffusion-wave-approximation-to-the-shallow-water-equations

16. SWE-ELM: momentum is solved normal to each face with a theta-weighted (Crank-Nicolson) pressure gradient, Eulerian-Lagrangian
    backtracking for advection, and an implicit bottom friction c_f = n^2 g |V| / R^(4/3) in which R and n are interpolated from
    the face tables at the theta-averaged level at every iteration. [Certain]
    "In HEC-RAS, momentum is computed normal to each face."
    https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/latest/theoretical-basis-for-one-dimensional-and-two-dimensional-hydrodynamic-calculations/2d-unsteady-flow-hydrodynamics/hydraulic-equations/momentum-conservation

17. SWE-EM: Kramer and Stelling (2008) momentum-conserving advection built from face inflows Q^-_{c,k} and upwinded cell
    velocities reconstructed by Perot weighting; in 6.5 and earlier the advection was fully explicit (Courant <= 1), in 6.6 its
    implicit part is treated semi-implicitly so larger steps are allowed; the explicit diffusion adds dt < dx^2/(2 nu_t) when
    turbulence is on. [Certain]
    "In HEC-RAS versions 6.5 and earlier both components were treated explicitly."
    https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/latest/theoretical-basis-for-one-dimensional-and-two-dimensional-hydrodynamic-calculations/2d-unsteady-flow-hydrodynamics/numerical-methods/eulerian-shallow-water-equation-solver

18. The face depth used in the EM advection is the weighted cell depth h_i = Omega_i / A_i^W (volume over wetted plan area), not
    water surface minus minimum elevation; cell weights alpha^L_f, alpha^R_f are the cell-centre distances to the face. [Certain]
    "h_i = Omega_i / A_i^W" (same URL as 17; see Equations).

19. Pressure gradient and conveyance use the distance between the two cell centres across the face (dx_N); on non-orthogonal
    meshes the normal derivative is split into a finite-difference part along the centre-to-centre line and a finite-volume part
    on the dual cell, and orthogonal regions get a two-point stencil ("hybrid discretization"). [Certain]
    "locally orthogonal grids produce two-point discretization stencils, while non-orthogonal grids require a larger stencil"
    HEC-RAS 5.0 Reference Manual p. 2-65 (PDF in 5).

20. Classical box scheme is a special case: with Omega(H) = P h and A_k(H) = l_k h the sub-grid equations collapse to a
    constant-area scheme, which is the test case for Wadi2D's table code. [Certain]
    "the classical "box scheme" can be very easily recovered by making Omega(H)=P*h"
    HEC-RAS 5.0 Reference Manual p. 2-55.

### D. Time-step rules

21. User's-manual Courant guidance (V = flood wave velocity, dX = average cell size): SWE-ELM C = V dT/dX <= 1.0 (max 3.0);
    SWE-EM C <= 1.0 (max 1.0); Diffusion Wave C <= 2.0 (max 5.0); a dry-started 2D area needs C = 1.0. [Certain]
    "a Courant number as high as 3.0 for the SWE's and 5.0 for the Diffusion Wave equations"
    https://www.hec.usace.army.mil/confluence/rasdocs/r2dum/6.5/running-a-model-with-2d-flow-areas/selecting-an-appropriate-grid-size-and-time-step

22. SWE-EM (through 6.5) is explicit in advection and "requires time steps to be selected to ensure the Courant number will be
    less than 1.0, in general (not always)"; the 2D computation options default to Diffusion Wave, theta = 1.0 (0.6-1.0), water
    surface tolerance 0.01 ft (max 0.2 ft), volume tolerance 0.01 ft, 20 iterations (0-40), PARDISO. [Certain]
    "the time step must be selected to ensure the Courant number is less than 1.0"
    https://www.hec.usace.army.mil/confluence/rasdocs/r2dum/6.5/running-a-model-with-2d-flow-areas/2d-computation-options-and-tolerances

23. Adaptive stepping ("Adjust Time Step Based on Courant"): the Courant number is face velocity x dt / (distance between the two
    cell centres); exceeding the maximum halves the step for the very next interval; the step doubles only when every location is
    below the minimum Courant for N consecutive steps (typical N 5-10); minimum must be less than half the maximum (example 1.0 and
    0.45); doubling/halving are bounded by powers of two of the base step; every step must land on the mapping output interval.
    [Certain]
    "If the maximum Courant number is exceeded, then the time step is cut in half for the very next time interval."
    https://www.hec.usace.army.mil/confluence/rasdocs/r2dum/latest/running-a-model-with-2d-flow-areas/variable-time-step-capabilities

24. Diffusion-wave theta scheme: unconditionally stable for 1/2 <= theta <= 1; for theta < 1/2 the condition is
    dt/dx^2 < 1/(2 - 4 theta). [Certain]
    "The linearized scheme is unconditionally stable for" 1/2 <= theta <= 1 (HEC-RAS 5.0 Reference Manual p. 2-66, eq. 2-156).

### E. HDF5 layout, geometry file `.g0x.hdf`

25. Collection level `Geometry/2D Flow Areas/`: `Attributes` (compound; fields include `Name`, `Cell Count`, `Face Count`),
    `Cell Info` (one row per mesh: [global start, physical cell count]), `Cell Points` (all meshes' cell centres, x y),
    `Polygon Info/Parts/Points` (perimeters), plus `Geometry/2D Flow Area Break Lines`, `Geometry/2D Flow Area Refinement
    Regions`, `Geometry/Land Cover (Manning's n)/Calibration Table`. [Certain]
    "Cell Info columns: [global_start_offset, cell_count]."
    https://github.com/psu-efd/pyHMT2D/blob/main/pyHMT2D/Hydraulic_Models_Data/RAS_2D/RAS_2D_Data.py
    and `f"{self.FLOW_AREA_2D_PATH}/Cell Info"`, `.../Cell Points` in
    https://github.com/fema-ffrd/rashdf/blob/main/src/rashdf/geom.py

26. Per mesh `Geometry/2D Flow Areas/<mesh>/`: `Perimeter`; `Cells Center Coordinate` (x y, no z); `Cells FacePoint Indexes`;
    `Cells Face and Orientation Info` ([start, count]) and `Values` (column 0 = face index; column 1 = orientation);
    `Cells Minimum Elevation`; `Cells Surface Area`; `Cells Volume Elevation Info` ([start, count]) and `Values` ([z, volume]);
    `Faces FacePoint Indexes` ([point A, point B]); `Faces Cell Indexes` ([cell left, cell right]); `Faces NormalUnitVector and
    Length` ([nx, ny, length]); `Faces Minimum Elevation`; `Faces Area Elevation Info` ([start, count]) and `Values`
    ([z, area, wetted perimeter, n]); `Faces Perimeter Info/Values` (polyline vertices); `FacePoints Coordinate` (x y,
    float32); `FacePoints Face and Orientation Info/Values`. [Certain]
    "The HDF path for this data is 'Geometry/2D Flow Areas/{mesh_name}/Faces Area Elevation Info'"
    https://github.com/gpt-cmdr/ras-commander/blob/main/ras_commander/hdf/HdfMesh.py
    Info-table semantics: "Two columns: first column-starting index, second column-length of record" (pyHMT2D, URL in 25).

27. Ghost cells: the per-mesh cell arrays (and the cell result arrays) list the physical cells first and then ghost cells outside
    the perimeter; the physical count is `Attributes/Cell Count` (equal to `Cell Info[:,1]`); pyHMT2D notes 5.0.7 already did
    this. Any table comparison must slice `[:Cell Count]`. [Certain]
    "HEC-RAS lists a 2D area's physical cells first in Cells Center Coordinate and in cell result arrays, followed by ghost cells outside the perimeter."
    https://github.com/gpt-cmdr/ras-commander/blob/main/ras_commander/hdf/HdfMesh.py

28. The face normal vector and length dataset has at least three columns and column 2 is the face length in model units; the
    orientation sign in `Cells Face and Orientation Values` column 1 is not interpreted by any of the three readers (they use
    column 0 only). Cells FacePoint Indexes is padded to the 8-face maximum. [Likely for the padding value (-1) and the
    orientation meaning; Certain for the rest]
    "Read a face length from Faces NormalUnitVector and Length when available."
    https://github.com/gpt-cmdr/ras-commander/blob/main/ras_commander/hdf/HdfMesh.py

29. Manning's n source layers are referenced by the geometry-group attributes `Land Cover Filename` and `Land Cover Layername`
    (6.x land-cover HDF holds "Raster Map, Variables"; 5.0.7 held "IDs, ManningsN, and Names"); per-face n is only in the face
    table. The terrain file name is not reliably recorded in the geometry HDF. [Certain for the attributes; Likely for the
    terrain remark]
    "It is not very clear how HEC-RAS organizes the terrain data in the HDF file regarding the terrain TIFF file names."
    https://psu-efd.github.io/pyHMT2D_API_Web/pyHMT2D_API.html

30. Cross-section property tables (1D) live in a different place, `Geometry/Cross Sections/Property Tables/{XSEC Info, XSEC Value}`
    (23 columns incl. conveyance); the 2D face tables do not store conveyance. [Certain]
    "Property tables are stored in geometry HDF files (.g##.hdf), NOT plan HDF files."
    https://github.com/gpt-cmdr/ras-commander/blob/main/ras_commander/hdf/HdfHydraulicTables.py

31. The plan HDF carries a copy of the `Geometry` group (attribute `Complete Geometry`), and the pre-processor writes the 2D
    tables into the plan file when it runs at compute time; readers therefore accept either file for the mesh. [Likely]
    "Temporary result HDF must have Complete Geometry=True before face-property writes."
    https://github.com/gpt-cmdr/ras-commander/blob/main/ras_commander/hdf/HdfMesh.py

### F. HDF5 layout, plan file `.p0x.hdf`

32. Base paths: `Plan Data/Plan Information` (attrs incl. `Simulation Start Time`), `Plan Data/Plan Parameters`,
    `Event Conditions/Meteorology/Precipitation` (`Values`, `Timestamp`, raster attrs), `Results/Unsteady/Summary/Volume
    Accounting` (attrs), `Results/Unsteady/Output/Output Blocks/Base Output/Unsteady Time Series/` with `Time`, `Time Date
    Stamp (ms)`, `2D Flow Areas/<mesh>/<variable>`, `Reference Lines`, `Reference Points`, `Boundary Conditions`, and
    `.../Base Output/Summary Output/2D Flow Areas/<mesh>/<variable>`. [Certain]
    `BASE_OUTPUT_PATH = "Results/Unsteady/Output/Output Blocks/Base Output"`, `SUMMARY_OUTPUT_2D_FLOW_AREAS_PATH`
    https://github.com/fema-ffrd/rashdf/blob/main/src/rashdf/plan.py

33. Time-series variables (cell: time x cell_id; face: time x face_id): `Water Surface`, `Depth` (optional output), `Cell Invert
    Depth`, `Cell Hydraulic Depth`, `Cell Volume`, `Cell Volume Error`, `Cell Water Surface Error`, `Cell Courant`, `Cell Velocity -
    Velocity X/Y`, `Cell Cumulative Precipitation Depth`, `Cell Flow Balance`, `Cell Storage Term`, `Cell Water Source Term`,
    `Cell Divergence Term`, `Cell Eddy Viscosity - Eddy Viscosity X/Y`; `Face Velocity` (normal component), `Face Flow`, `Face
    Flow Period Average`, `Face Cumulative Volume`, `Face Water Surface`, `Face Shear Stress`, `Face Tangential Velocity`, `Face
    Courant`, `Face Friction Term`, `Face Pressure Gradient Term`, `Face Wind Term`, `Face Eddy Viscosity`; `Node Velocity -
    Velocity X/Y` (optional). [Certain]
    `FACE_VELOCITY = "Face Velocity"` ... `CELL_INVERT_DEPTH = "Cell Invert Depth"` (rashdf plan.py, URL in 32);
    "The node velocities (Node X Vel and Node Y vel) are not automatically written to the HDF output file."
    https://www.hec.usace.army.mil/confluence/rasdocs/r2dum/6.2/viewing-2d-or-1d-2d-output-using-hec-ras-mapper/2d-output-file-hdf5-binary-file

34. Summary datasets per mesh: `Maximum Water Surface`, `Minimum Water Surface`, `Maximum Face Velocity`, `Minimum Face Velocity`
    (each 2 rows: row 0 value, row 1 time in the unit named by the `Units per row` / `Units` attribute, days), and `Cell Maximum
    Water Surface Error`, `Cell Cumulative Iteration`, `Cell Last Iteration` (1 row). Cell summaries carry the ghost cells at the
    end with "bogus" values. [Certain]
    "extra points are appended to the end of the mesh data and contain bogus output values (e.g., 0.0, NaN)"
    https://github.com/fema-ffrd/rashdf/blob/main/src/rashdf/plan.py

35. Depth when not written is reconstructed by readers as Water Surface minus `Cells Minimum Elevation`; RAS-Commander documents
    that maxima in `Summary Output` are solver-step maxima and can exceed the maximum of the saved output-interval series. [Certain
    for the reconstruction rule in code; Likely that `Depth` equals WS - cell minimum elevation in RAS]
    "Water Surface plus Cells Minimum Elevation are not both available"
    https://github.com/gpt-cmdr/ras-commander/blob/main/ras_commander/hdf/HdfResultsMesh.py

36. HEC's manual page prints the group as "2D flow areas"; the files use `2D Flow Areas` (HDF5 names are case-sensitive; all
    three readers use the capitalised form). [Certain]
    `"Results/Unsteady/Output/Output Blocks/Base Output/Unsteady Time Series/2D Flow Areas/{mesh_name}/{var_name}"`
    https://github.com/gpt-cmdr/ras-commander/blob/main/ras_commander/hdf/HdfResultsMesh.py

### G. Differences 5.0.7 and 6.0-6.6

37. The geometry dataset names in 26 are stable from 5.0.7 to 6.6 (pyHMT2D reads 5.0.7, 6.0.0, 6.1.0, 6.2 and 6.6 files through
    the same paths; the root attribute `File Version` carries the producer, e.g. "HEC-RAS 6.3 August 2022", and the geometry
    group has `Geometry Version`, e.g. 1.0.18 for the 6.2/6.3 era). [Certain]
    "Supported versions: 5.0.7, 6.0.0, 6.1.0, 6.2, and 6.6"
    https://github.com/psu-efd/pyHMT2D/blob/main/pyHMT2D/Hydraulic_Models_Data/RAS_2D/RAS_2D_Data.py

38. Result names changed between 5.0.7 and 6.x: `Depth` and `Node X Vel`/`Node Y Vel` (5.0.7) versus `Cell Invert Depth` and
    `Node Velocity - Velocity X/Y` (6.0+); `Cell Velocity - Velocity X/Y` exists in 6.6; pyHMT2D works around 6.6 node velocities.
    [Certain that the code branches exist; Likely for the 6.6 defect]
    "For v6.6, the nodal velocity is not exported correctly; thus, we use the cell center velocity."
    same URL as 37.

39. HEC-RAS 6.0 to 6.3.x wrote a per-mesh diagnostic table `.../Unsteady Time Series/2D Flow Areas/<mesh>/Log Hydraulics`
    (10 columns, "Column 0..9" attributes: iterations, max WS correction and cell, volume residual, volume balance, max/min WS);
    it is absent from 5.0.x and from 6.4.1 onward. [Certain]
    "producer strings in the HEC-RAS 6.0-6.3.1 solver binaries (absent from 5.0.x and 6.4.1+)"
    https://github.com/gpt-cmdr/ras-commander/pull/594 and HdfResultsMesh.py (URL in 36).

40. HEC-RAS 6.6 leaves placeholder datasets with no stored chunks: `Face Wind Term` when there is no wind forcing (6.6 and 7.0.1)
    and `Face Water Surface` in 6.6 Diffusion-Wave runs; a reader must check the stored byte count, not the dataset's presence.
    [Certain]
    "HEC-RAS 6.6 and 7.0.1 leave Face Wind Term (no wind forcing) and 6.6 leaves Face Water Surface this way"
    https://github.com/gpt-cmdr/ras-commander/blob/main/ras_commander/hdf/HdfResultsMesh.py

41. Some 6.2/6.3-era geometry HDFs report the 2D areas but omit the per-mesh face topology (only the collection-level `Cell
    Info`/`Cell Points` and perimeters are present), so cell polygons cannot be rebuilt from such a file; the plan HDF of the run
    has them. [Likely]
    "This HEC-RAS 6.2/6.3-era geometry reports 2D data but omits named-area face topology."
    https://github.com/gpt-cmdr/ras-commander/blob/main/ras_commander/hdf/HdfMesh.py

42. 5.0.x summary arrays lack the `Location` and `Units per row` attributes and keep units in per-row attributes; 6.x carries
    `Location`, `Units per row`. [Likely; from the RAS-Commander fast-hdf PR description, not read in full]
    "Observed without Location in HEC-RAS 5.0.7 (e.g. FEMA eBFE AustinOyster.p03.hdf)"
    https://github.com/gpt-cmdr/ras-commander/blob/main/ras_commander/hdf/HdfResultsMesh.py

43. Solver changes in 6.6 that alter results but not the file layout: semi-implicit SWE-EM advection ("no longer strictly limited
    by the Courant number"), optional advanced convergence criteria for the 2D solvers, wave forcing, HEC-RAS 2025 mesh import
    (locked meshes), beta pipe networks. [Certain]
    "HEC-RAS 6.6 has the option to use additional convergence criteria for the 2D flow solvers."
    https://www.hec.usace.army.mil/confluence/rasdocs/rasrn/6.6/new-features

### H. Producing a square-cell mesh in RAS Mapper for a one-to-one table check

44. The mesh is made from computation points: the user enters a nominal point spacing (DX, DY in the 2D Flow Area editor), presses
    "Generate Computation Points" (with or without breaklines), and RAS triangulates the points (Delaunay) and takes the Voronoi
    diagram as the cells. With DX = DY and no breaklines the interior cells are therefore exact squares centred on the points;
    only cells cut by the perimeter are irregular. [Certain for the construction; the square consequence is geometric]
    "HEC-RAS makes the computational mesh by following the Delaunay Triangulation technique and then constructing a Voronoi diagram."
    https://www.hec.usace.army.mil/confluence/rasdocs/r2dum/6.0/development-of-a-2d-or-combined-1d-2d-model/development-of-the-2d-computational-mesh
    "This will create computational mesh based on an evenly distributed "grid" of points"
    https://www.hec.usace.army.mil/confluence/rasdocs/rmum/6.0/geometry-data/2d-flow-areas

45. Build order and constraints: computation points, refinement-region points and perimeter as breaklines, breakline points
    (overriding points in a buffer), triangulation, mesh; cells may have at most 8 faces, must be strictly convex, must not have
    collinear faces (the run proceeds but the face computation is wrong). [Certain]
    "Each cell is limited to having 8 faces (sides)."
    same r2dum 6.0 URL as 44.

46. The computation points are editable as a table (Add, Multiply, Set, Replace, paste), and the generated mesh is recomputed on
    the fly, so the lattice can be shifted to put cell centres on DEM pixel centres; no base-grid rotation option is documented in
    6.x (HEC-RAS 2025 has a new mesher). [Certain for the editing; Guessing on the absence of rotation]
    "Add, Multiply, Set, Replace, and Adjust decimal places"
    https://www.hec.usace.army.mil/confluence/rasdocs/rmum/6.0/geometry-data/2d-flow-areas

47. For a one-to-one check the mesh geometry need not be reproduced at all: the exact cell polygons (face points, faces, polyline
    faces), the cell centres and all tables are in the HDF (26), so the Wadi2D builder can be run on RAS's own polygons and
    compared breakpoint by breakpoint. [Certain]
    "Each face is (pnt_a, pnt_b) from Faces FacePoint Indexes, indexing FacePoints Coordinate."
    https://github.com/fema-ffrd/rashdf/blob/main/src/rashdf/geom.py (the `mesh_cell_faces` / `polygonize_full` logic)

48. Application scale of a Casulli-type sub-grid model, for calibration of expectations: a 200 m base grid with a 40 x 40 nested
    5 m sub-grid per cell (11,601 elements, 4.5 million sub-grid cells) resolved street-level inundation in New York during
    Sandy. [Certain]
    "200m base grid with a 40x40 nested 5m sub-grid within each grid cell"
    https://arxiv.org/pdf/1412.0966

## Equations and algorithms

Notation: z_s water surface elevation [L]; z_b lowest bed elevation of the cell or face [L]; Omega_c cell volume [L^3];
A_c^W cell wetted (plan) area [L^2]; A_f face vertical area [L^2]; W_f face wetted width [L]; P_f face wetted perimeter [L];
R hydraulic radius [L]; n Manning's n [T L^-1/3]; phi porosity [-]; u_N face-normal velocity [L/T]; s_ik = +1/-1 outward sign
of face k for cell i; K(i) faces of cell i; N(i) neighbours; dx_N distance between the two cell centres across the face [L];
theta implicit weight [-]; dt time step [T]; Q_i source [L^3/T].

E1. Cell curves (HEC Reference Manual, Subgrid Bathymetry, unnumbered on the page):
    Omega_c(z_s) = integral_{z_b}^{z_s} A_c^W(z) dz ;  A_c^W(z_s) = d Omega_c / d z_s
    A_c^W(z_s) = A_{c,i}^W for z_{s,i} <= z_s < z_{s,i+1}; = A_{c,N}^W for z_s >= z_{s,N}  (piecewise constant)
    Omega_c(z_s) = Omega_{c,i} + A_{c,i}^W (z_s - z_{s,i}) on the same intervals  (piecewise linear, exact)
    The stored dataset is the breakpoint list (z_{s,i}, Omega_{c,i}); A_{c,i}^W is the slope between breakpoints.

E2. Face curves (same page):
    A_f(z_s) = integral_{z_b}^{z_s} W_f(z) dz ;  W_f(z_s) = d A_f / d z_s
    W_f piecewise constant, A_f piecewise linear: A_f(z_s) = A_{f,i} + W_{f,i}(z_s - z_{s,i})
    P_f(z_s) = integral sqrt(1 + (dx/dy)^2) dy  along the wetted profile (no porosity)
    Porosity: A_c^W = phi_c(z_s) * A~_c^W ;  W_f = phi_f(z_s) * W~_f ; perimeter treated like the width.
    Stored dataset: rows (z_{s,i}, A_{f,i}, P_{f,i}, n_i).

E3. Face conveyance and friction (Reference Manual DWE solver page; Momentum Conservation page):
    R_k = A_k / P_k ;  K_k = A_k R_k^{2/3} / n_k  (times 1.486 in US customary units; RAS-Commander reproduces this)
    tau_b = rho C_D |V| V ;  C_D = n^2 g / R^{1/3} ;  c_f = C_D |V| / R = n^2 g |V| / R^{4/3} ;  u_* = sqrt(tau_b / rho)
    R and n for a face are interpolated from the face table at the theta-averaged water level at every iteration.

E4. Composite Manning's n per face when "Spatially Varied Manning's n" is on (2D User's Manual, property tables page):
    n_c = [ (1/P) * sum_i P_i n_i^{3/2} ]^{2/3},  P = total wetted perimeter, P_i and n_i per land-cover segment along the face.
    Constant above the elevation at which the face is fully wet. Developed for n in 0.01-0.1; buildings at n 0.25-0.5 dominate.

E5. Face conveyance refinement (2D User's Manual 6.0): for each pair of neighbouring breakpoints (z_i, z_{i+1}) compute
    K(z_mid) from the exact profile and K_lin = (K_i + K_{i+1})/2; if |K(z_mid) - K_lin| / K(z_mid) > 0.02 insert z_mid as a
    breakpoint; repeat. Independent filters first thin the terrain points along the face (0.01 ft), the face table (0.01 ft) and
    the cell curve (0.01 ft).

E6. Mass conservation, all solvers (ELM page eq. 1; 5.0 manual eq. 2-128):
    (Omega_i^{n+1} - Omega_i^n)/dt + sum_{k in K(i)} s_ik u_{N,k}^{n+theta} A_k^n = Q_i
    Box scheme recovered with Omega = P h and A_k = l_k h.

E7. Diffusion wave (DWE solver page eqs. 1-7):
    u_{N,k}^{n+theta} = -(alpha_k / A_k) [ (z_{s,R} - z_{s,L})^{n+theta} / dx_{N,k} - tau_{s,N}/(rho g h) + (p_{a,R} - p_{a,L})/(rho g dx_{N,k}) ]
    alpha_k = K_k / | grad z_s + grad p_a/(rho g) - tau_s/(rho g h) |^{1/2}
    Omega_i^{n+1} + sum_{j in C(i)} a_ij z_{s,j}^{n+1} = b_i ;  a_ij = -dt theta alpha_k / dx_{N,k} (j in N(i)); a_ii = -sum a_ij
    b_i = Omega_i^n + dt (S_i + Q_i) - ((1-theta)/theta) sum_j a_ij z_{s,j}^n
    Matrix form Omega(Z) + Psi Z = b ; Newton-like iteration Z^{m+1} = Z^m - [Psi + A^m]^{-1} (Omega^m + Psi Z^m - b),
    A = diag(cell wet surface areas) = d Omega / d z_s. Stop when residual or correction < tolerance (0.01 ft default, 20 iterations).
    Stability: unconditional for theta in [1/2, 1]; dt/dx^2 < 1/(2 - 4 theta) for theta < 1/2.
    Continuous form: V = -(beta/h)(grad z_s + ...), beta = h R^{2/3} / (n sqrt|grad z_s|) ; dh/dt = div(beta grad z_s) + S + q.

E8. SWE-ELM (ELM page eqs. 1-12): material derivative by backtracking, DV/Dt = (V^{n+1} - V_X^n)/dt;
    second fractional step at the face:
    (u_{N,f}^{n+1} - u_N^*)/dt = -g dz_s^{n+theta}/dN + M_D - c_{f,f} u_{N,f}^{n+1} + tau_{s,N}/(rho h_f) - (1/(rho g)) dp_a/dN
    u_{N,f}^{n+1} = -(dt g / (1 + dt c_{f,f})) dz_s^{n+theta}/dN + F_f ;  F_f = B_f^n / (1 + dt c_{f,f})
    System: Omega_i^{n+1} + sum_j a_ij z_{s,j}^{n+1} = b_i ;  a_ij = -dt^2 theta^2 g A_k / ((1 + dt c_{f,f}^{n+theta}) dx_N)
    b_i = Omega_i^n + dt Q_i - ((1-theta)/theta) sum_j a_ij z_{s,j}^n - dt sum_k s_ik [theta F_k + (1-theta) u_{N,k}^n] A_k
    Dry faces: u = 0 until water arrives; eddy viscosity from u_* with R and n from the face tables.

E9. SWE-EM (EM page eqs. 1-11): advection [(V . grad) u_N]_f = A_{e,f} + A_{i,f} u_{N,f}^{n+1},
    A_{e,f} = (1/h_f) sum_{c in L,R} (alpha_f^c / A_c) sum_{k in K(c)} Q^-_{c,k} (V_k^u . n_f),
    A_{i,f} = -(1/h_f) sum_c (alpha_f^c / A_c) sum_k Q^-_{c,k},  Q^-_{i,k} = min(s_ik Q_k, 0),  h_i = Omega_i / A_i^W,
    alpha_f^L = dx_f^L / (dx_f^L + dx_f^R), h_f = alpha_f^R h_R + alpha_f^L h_L, V^u upwinded cell velocity (Perot reconstruction).
    u_{N,f}^{n+1} = -(dt g / (1 + dt (c_{f,f} + A_{i,f}))) dz_{s,f}^{n+theta}/dN + F_f ;
    a_ij = -dt^2 theta^2 g A_k / ([1 + dt (c_{f,f} + A_{i,f})] dx_N).
    Stability (as printed): C = u dx/dt <= C_max = 1 (the page's fraction is inverted; read C = u dt/dx); dt < dx^2 / (2 nu_t).
    6.5 and earlier: both advection terms explicit; 6.6: A_i implicit.

E10. Gradient on the dual grid (5.0 manual eqs. 2-147 to 2-151): grad H ~ (1/A') integral_L H n dL summed over dual faces,
    contributions n_k' l_k' (H_1 + H_2)/2; directional derivative split dH/dn = (n . n') dH/dn' + (n . T') dH/dT' with the first
    term by finite differences between the two cell centres and the second by the dual-cell finite volume; orthogonal regions
    reduce to two-point stencils.

E11. Courant controls (User's Manual): C = V dT / dX with V the face velocity and dX the distance between the two cell centres
     (adaptive stepping) or the average cell size (design guidance); limits per solver in finding 21; adaptive state machine in
     finding 23: halve immediately above C_max, double after N consecutive steps everywhere below C_min, bounded by 2^k of the
     base step, and always hit the mapping output interval.

E12. Reader algorithm for the tables (rashdf/RAS-Commander/pyHMT2D, identical in all three):
     for face f: s, c = Info[f]; rows = Values[s : s + c]; columns (z, A, P, n). Same for cells with (z, Omega).
     Cell polygons: faces of cell = Values_cellface[Info[cell,0] : Info[cell,0] + Info[cell,1], 0]; each face polyline = FacePoints
     [A], Faces Perimeter Values[start : start + count], FacePoints[B]; polygonize. Physical cells = first `Cell Count` rows.
     Summary max: values = ds[0, :Cell Count], times = ds[1, :Cell Count] in `Units per row`[1] (days) from `Simulation Start Time`.
     Depth fallback: Water Surface[t, :Cell Count] - Cells Minimum Elevation[:Cell Count].

## Numbers

| Value | Context | Source |
|---|---|---|
| 0.01 ft (3.05 mm) | Default Cell Elev-Vol Filter Tol, Face Profile Filter Tol, Face Area-Elev Filter Tol | r2dum 6.0 mesh page |
| 0.02 (2 %) | Default Face Conveyance Tol Ratio (midpoint conveyance vs linear interpolation) | r2dum 6.0 mesh page |
| 8 | Maximum faces per cell; cells strictly convex; no collinear faces | r2dum 6.0; Ref. Manual Grid and Dual Grid |
| 4 columns | Face table: elevation, area, wetted perimeter, Manning's n | pyHMT2D, RAS-Commander code |
| 2 columns | Cell table: elevation, volume; plan area separate ("Cells Surface Area") | RAS-Commander code |
| 3 columns | Faces NormalUnitVector and Length: nx, ny, length | RAS-Commander code |
| 1.486 / 1.0 | Manning conveyance coefficient US / SI used to derive K from the table | RAS-Commander HdfMesh |
| 0.01-0.1 | Range of n for which the composite-n formula was developed | r2dum latest property-tables page |
| 0.25-0.5 | Suggested Manning's n for buildings in the composite-n option | same |
| Diffusion Wave; theta 1.0 (0.6-1.0); WS tol 0.01 ft (max 0.2 ft); volume tol 0.01 ft; 20 iterations (0-40) | 2D computation option defaults | r2dum 6.5 options page |
| PARDISO; relaxation 1.3 (1.1-1.5); restart iterations 10 (8-20); convergence 1e-4 x WS tol | Matrix solver defaults | same |
| C <= 1.0, max 3.0 | SWE-ELM Courant guidance (C = V dT/dX) | r2dum 6.5 time-step page |
| C <= 1.0, max 1.0 | SWE-EM Courant guidance (<= 6.5 explicit advection) | same |
| C <= 2.0, max 5.0 | Diffusion Wave Courant guidance | same |
| 1.0 / 0.45 / 5-10 | Example max Courant / min Courant / steps before doubling; min < max/2 | r2dum latest variable time step page |
| dt < dx^2/(2 nu_t) | Extra explicit limit of SWE-EM with turbulence on | Ref. Manual EM solver page |
| dt/dx^2 < 1/(2-4 theta) | DWE stability for theta < 1/2; unconditional for theta >= 1/2 | 5.0 Ref. Manual eq. 2-156 |
| 7.292115855306587e-5 1/s | Earth angular velocity in f_c = 2 omega sin(phi) | Ref. Manual Momentum Conservation |
| 2 rows | Summary max/min datasets: row 0 value, row 1 time (days) | rashdf plan.py |
| 10 columns | Log Hydraulics table, HEC-RAS 6.0-6.3.x only | RAS-Commander PR #594 |
| [6.0, 6.4) | File-version range that may contain Log Hydraulics | RAS-Commander HdfResultsMesh |
| 5.0.7, 6.0.0, 6.1.0, 6.2, 6.6 | File versions pyHMT2D reads with the same geometry paths | pyHMT2D RAS_2D_Data.py |
| 1.0.18 | Geometry Version attribute flagged as 6.2/6.3-era by RAS-Commander | RAS-Commander HdfMesh |
| 200 m / 5 m (40 x 40) / 4,496,833 | Base grid, nested sub-grid, sub-grid cells of a Casulli-type model for NYC (Sandy) | arXiv 1412.0966 |
| 15,000 | Max computation points displayed in the RAS Mapper edit view | rmum 6.0 2D Flow Areas page |

## Recommendation for Wadi2D

1. Adopt HEC's table *semantics* as the interchange format, not its storage: per cell a breakpoint list (z, Omega) with the wetted
   plan area as the slope (E1), per face (z, A, P, n_eff) with z_min = first breakpoint (E2), both built from the 0.5 m DEM and
   thinned by an elevation tolerance (3 mm as RAS) plus a conveyance-error criterion (E5, 2 %). This is what makes a one-to-one
   check against RAS possible and what reviewers already accept. Keep RAS's rule that A_f = 0 below the face minimum: it is the
   whole "faces aware of topography" mechanism (findings 10-12), and it costs nothing in an explicit solver.

2. Reject HEC's single-section face conveyance K = A (A/P)^(2/3) / n with a composite n (E3-E4) as Wadi2D's *default*. It treats a
   braided wadi face of several channels as one section with one hydraulic radius, which under-represents the deep threads. Build
   the face conveyance by integrating along the face profile over the sub-grid segments, K(z) = sum_j w_j h_j^(5/3) / n_j
   (the Casulli / Volp-style sub-grid friction, to be confirmed in topic N02/N04 against TUFLOW SGS), and keep a "HEC-RAS mode"
   switch (single R, composite n) only for the Block 2 head-to-head comparison and for explaining differences. Decide by the
   comparison, not by argument. Store K(z) or the (A, P, n) triple, not both; recomputing K per step from (A, P, n) is cheap on
   GPU but the per-pixel integral is not, so K(z) must be pre-tabulated.

3. Store the tables GPU-friendly: RAS's CSR (Info/Values) layout with variable row counts is right for the file and the reader,
   wrong for a CUDA kernel. Fix a per-entity breakpoint count (e.g. 16 or 32 levels at non-uniform z chosen by the 2 % conveyance
   criterion, with the last level repeated) so that lookups are branch-free and coalesced; export/import RAS-style CSR in the
   Python layer only. [Guessing on the count; benchmark 8/16/32 in the solver micro-benchmark.]

4. Store depth, not level, in the solver (project decision 3 stands), but store the tables in elevation like RAS and convert once at
   load (z - z_min of the entity); the EM solver's face depth definition h_i = Omega_i / A_i^W (finding 18) is the right "hydraulic"
   depth for friction and Courant checks on sub-grid cells and should be the one Wadi2D uses, not z_s - z_min.

5. Write a 300-line Python reader (h5py) now, modelled on rashdf geom.py/plan.py, that reads the paths of findings 25-26 and 32-34,
   slices ghost cells by `Cell Count`, and reconstructs cell polygons from faces (E12). Do not depend on rashdf or RAS-Commander as
   libraries (licence audit pending; RAS-Commander is large and LLM-generated), but credit them. Test it on the Block 2 wadi head
   RAS model that will be built for the validation ladder.

6. One-to-one comparison protocol: build the RAS mesh with DX = DY = 10 m (a multiple of the 0.5 m DEM), no breaklines, square
   perimeter; read the exact polygons and the tables from the `.g0x.hdf` (or the plan file, finding 31); run the Wadi2D builder on
   the same DEM and on RAS's own polygons; compare z_min per cell and face, Omega(z) and A_f(z), P_f(z) at RAS's breakpoints, and
   K(z) in HEC mode. Expect agreement to the 3 mm filter and to the terrain sampling along the face (open issue 1); report the
   residual distribution, not a pass/fail. Then repeat with Wadi2D's own square grid to measure the cost of grid misalignment.

7. Time stepping: nothing to copy from the implicit solvers except the adaptive state machine of finding 23 (halve at once, double
   only after N quiet steps, bound by powers of two, land on the output interval), which is a good pattern for the CFL-driven
   explicit step and for the live view. Wadi2D's step is CFL <= ~0.9 by the fastest cell; RAS's "C up to 3 for SWE-ELM" is an
   implicit-scheme property and not transferable.

8. Output in a RAS-shaped HDF5 (paths of findings 32-34 with the same names, `Units per row`, 2-row summaries, `Time Date Stamp
   (ms)`) so that rashdf and RAS-Commander read Wadi2D results unchanged. That gives free post-processing, lets reviewers use tools
   they know, and makes the Block 2 head-to-head a dataset-by-dataset diff. [Likely worth it; cost is a day.]

9. Validation implication (decision 12 of the project): the two-model comparison must be done in RAS 6.6 (semi-implicit SWE-EM,
   finding 17), the version to be stated in every figure; results of 6.0-6.5 SWE-EM differ by construction.

## Open issues

1. The exact terrain sampling HEC uses along a face (spacing, interpolation, whether pixel-exact area integration is used for the
   cell volume) is not documented; infer it from the breakpoints of a real table (the z list equals the thinned profile elevations)
   before claiming a residual is a Wadi2D error.
2. Meaning of column 1 of `Cells Face and Orientation Values` and the padding value of `Cells FacePoint Indexes` (expected -1): no
   reader interprets them; confirm in HDFView on a Block 2 file.
3. Whether the geometry HDF records the terrain file used (the `.rasmap` does); pyHMT2D says the attribute scheme is unclear.
4. Casulli (2009) and Sehili et al. (2014) are paywalled; the per-pixel face conveyance form recommended in point 2 was not read in
   its original and must be taken from N02/N04 (TUFLOW SGS, Volp et al. 2013) or an open copy.
5. Whether the face table gains columns when 6.6 porosity layers are used (readers unpack four; the Reference Manual folds porosity
   into A and W, so probably not).
6. `Depth` vs `Cell Invert Depth` vs `Cell Hydraulic Depth`: names are certain, definitions are inferred (WS - cell minimum
   elevation; Omega / A^W); check on a file with all three written.
7. Rotation of the base point lattice in 6.x RAS Mapper: not found in the pages read; HEC-RAS 2025 has a new mesher whose meshes
   6.6 imports locked.
8. The Reference Manual pages were read in their "latest" (7.0) rendering; the version selector goes back to 6.0, and the 6.x
   wording was not diffed (the 5.0 PDF agrees on every equation checked).
9. Web-search budget ran out before: the HEC page on the HDF5 Write Parameters tab (which optional outputs exist per version),
   the RAS-Commander fast-hdf PR on 5.0 summary attributes, and a secondary check of the 2015 forum claim that the plan HDF holds
   the full geometry group.

## Sources

1. HEC-RAS 2D Modeling User's Manual (latest), "Creating Hydraulic Property Tables for 2D Flow Areas". Used for: cell/face table
   purpose, default n at the face centroid, composite n formula, automatic re-preprocessing.
   https://www.hec.usace.army.mil/confluence/rasdocs/r2dum/latest/development-of-a-2d-or-combined-1d-2d-model/creating-hydraulic-property-tables-for-2d-flow-areas
2. HEC-RAS 2D Modeling User's Manual 6.0, "Development of the 2D Computational Mesh". Used for: Delaunay/Voronoi mesh, breaklines,
   filter tolerances and defaults, conveyance tolerance algorithm, 8 faces, convexity, collinear faces, channel faces holding flow.
   https://www.hec.usace.army.mil/confluence/rasdocs/r2dum/6.0/development-of-a-2d-or-combined-1d-2d-model/development-of-the-2d-computational-mesh
3. HEC-RAS 2D Modeling User's Manual 6.5, "2D Computation Options and Tolerances". Used for: equation sets, theta, tolerances,
   iterations, solver defaults, SWE-EM Courant statement.
   https://www.hec.usace.army.mil/confluence/rasdocs/r2dum/6.5/running-a-model-with-2d-flow-areas/2d-computation-options-and-tolerances
4. HEC-RAS 2D Modeling User's Manual 6.5, "Selecting an Appropriate Grid Size and Time Step". Used for: Courant limits per solver.
   https://www.hec.usace.army.mil/confluence/rasdocs/r2dum/6.5/running-a-model-with-2d-flow-areas/selecting-an-appropriate-grid-size-and-time-step
5. HEC-RAS 2D Modeling User's Manual (latest), "Variable Time Step Capabilities". Used for: adaptive Courant stepping rules.
   https://www.hec.usace.army.mil/confluence/rasdocs/r2dum/latest/running-a-model-with-2d-flow-areas/variable-time-step-capabilities
6. HEC-RAS 2D Modeling User's Manual 6.2 and latest, "2D Output File (HDF5 binary file)". Used for: output group path, base and
   optional variables, node velocity option.
   https://www.hec.usace.army.mil/confluence/rasdocs/r2dum/6.2/viewing-2d-or-1d-2d-output-using-hec-ras-mapper/2d-output-file-hdf5-binary-file
7. HEC-RAS 2D Modeling User's Manual 6.0, "HEC-RAS 2D Modeling Advantages/Capabilities". Used for: face evaluated like a cross
   section, partially wet cells, 8 sides, implicit solver statement.
   https://www.hec.usace.army.mil/confluence/rasdocs/r2dum/6.0/introduction/hec-ras-2d-modeling-advantages-capabilities
8. HEC-RAS Mapper User's Manual 6.0, "2D Flow Areas". Used for: point spacing, generation buttons, build order, point editing.
   https://www.hec.usace.army.mil/confluence/rasdocs/rmum/6.0/geometry-data/2d-flow-areas
9. HEC-RAS Hydraulic Reference Manual (web), "Subgrid Bathymetry". Used for: E1-E2, porosity.
   https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/theoretical-basis-for-one-dimensional-and-two-dimensional-hydrodynamic-calculations/2d-unsteady-flow-hydrodynamics/subgrid-bathymetry
10. HEC-RAS Hydraulic Reference Manual 6.4 (web), "Diffusion Wave Equation Solver". Used for: E7, conveyance, explicit face area,
    stability.
    https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/6.4/theoretical-basis-for-one-dimensional-and-two-dimensional-hydrodynamic-calculations/2d-unsteady-flow-hydrodynamics/numerical-methods/diffusion-wave-equation-solver
11. HEC-RAS Hydraulic Reference Manual (web), "Eulerian-Lagrangian Shallow Water Equation Solver". Used for: E6, E8, dry faces.
    https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/latest/theoretical-basis-for-one-dimensional-and-two-dimensional-hydrodynamic-calculations/2d-unsteady-flow-hydrodynamics/numerical-methods/eulerian-lagrangian-shallow-water-equation-solver
12. HEC-RAS Hydraulic Reference Manual (web), "Eulerian Shallow Water Equation Solver". Used for: E9, 6.6 semi-implicit change,
    stability limits.
    https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/latest/theoretical-basis-for-one-dimensional-and-two-dimensional-hydrodynamic-calculations/2d-unsteady-flow-hydrodynamics/numerical-methods/eulerian-shallow-water-equation-solver
13. HEC-RAS Hydraulic Reference Manual (web), "Momentum Conservation". Used for: E3 friction, Coriolis constant.
    https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/latest/theoretical-basis-for-one-dimensional-and-two-dimensional-hydrodynamic-calculations/2d-unsteady-flow-hydrodynamics/hydraulic-equations/momentum-conservation
14. HEC-RAS Hydraulic Reference Manual (web), "Diffusion Wave Approximation to the Shallow Water Equations". Used for: beta, E7
    continuous form.
    https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/latest/theoretical-basis-for-one-dimensional-and-two-dimensional-hydrodynamic-calculations/2d-unsteady-flow-hydrodynamics/hydraulic-equations/diffusion-wave-approximation-to-the-shallow-water-equations
15. HEC-RAS Hydraulic Reference Manual (web), "Mass Conservation" and "Grid and Dual Grid". Used for: porosity continuity form,
    grid properties, 8-side limit, dual grid.
    https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/latest/theoretical-basis-for-one-dimensional-and-two-dimensional-hydrodynamic-calculations/2d-unsteady-flow-hydrodynamics/hydraulic-equations/mass-conservation
    https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/latest/theoretical-basis-for-one-dimensional-and-two-dimensional-hydrodynamic-calculations/2d-unsteady-flow-hydrodynamics/grid-and-dual-grid
16. HEC-RAS 5.0 Hydraulic Reference Manual (PDF, Feb 2016), chapter 2, pp. 2-52 to 2-71 (text extracted locally with pypdf).
    Used for: eqs. 2-126 to 2-128, 2-147 to 2-156, the DSW solution algorithm, per-face R and n tables, hybrid discretization.
    https://www.hec.usace.army.mil/software/hec-ras/documentation/HEC-RAS%205.0%20Reference%20Manual.pdf
17. rashdf (fema-ffrd), `src/rashdf/geom.py` and `src/rashdf/plan.py`, branch main. Used for: collection-level geometry paths,
    face/polygon reconstruction, result and summary paths, enums, 2-row summaries, ghost-cell comment.
    https://github.com/fema-ffrd/rashdf/blob/main/src/rashdf/geom.py and https://github.com/fema-ffrd/rashdf/blob/main/src/rashdf/plan.py
18. pyHMT2D (psu-efd), `pyHMT2D/Hydraulic_Models_Data/RAS_2D/RAS_2D_Data.py`, branch main, and the API documentation page. Used
    for: table column semantics, Info table semantics, version branches 5.0.7/6.x/6.6, land-cover attributes, ghost cells.
    https://github.com/psu-efd/pyHMT2D/blob/main/pyHMT2D/Hydraulic_Models_Data/RAS_2D/RAS_2D_Data.py and
    https://psu-efd.github.io/pyHMT2D_API_Web/pyHMT2D_API.html
19. RAS-Commander (gpt-cmdr), `ras_commander/hdf/HdfMesh.py`, `HdfResultsMesh.py`, `HdfHydraulicTables.py`, branch main. Used
    for: full per-mesh dataset list, conveyance derivation, ghost cells, 6.2/6.3 legacy signature, 6.6 placeholders, depth
    fallback, Log Hydraulics bounds, 1D property tables.
    https://github.com/gpt-cmdr/ras-commander/tree/main/ras_commander/hdf
20. RAS-Commander pull request #594 (legacy 2D Log Hydraulics reader). Used for: 6.0-6.3.x table columns and version evidence.
    https://github.com/gpt-cmdr/ras-commander/pull/594
21. HEC-RAS Release Notes 6.6, "New Features". Used for: 6.6 solver and mesh-import changes.
    https://www.hec.usace.army.mil/confluence/rasdocs/rasrn/6.6/new-features
22. Loftis, Wang, Hamilton, Forrest, "Combination of Lidar Elevations, Bathymetric Data, and Urban Infrastructure in a Sub-Grid
    Model for Predicting Inundation in New York City during Hurricane Sandy", arXiv 1412.0966 (PDF, text extracted locally).
    Used for: application numbers of a Casulli-type sub-grid model.
    https://arxiv.org/pdf/1412.0966
23. (secondary) serapeum-org/pyramids-mesh issue #28. Used for: the note that some older models expose only `Cell Points`.
    https://github.com/serapeum-org/pyramids-mesh/issues/28
24. (not read, paywalled) Casulli, V. (2009) "A high-resolution wetting and drying algorithm for free-surface hydrodynamics",
    IJNMF 60(4) 391-408, doi 10.1002/fld.1896; Sehili, Lang, Lippert (2014) Ocean Dynamics, doi 10.1007/s10236-014-0693-x.
