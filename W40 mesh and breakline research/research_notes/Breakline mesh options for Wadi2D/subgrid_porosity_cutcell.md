# Sub-grid, porosity and cut-cell methods for breaklines on coarse grids: options for Wadi2D

Date: 2026-11-07. Scope: methods that represent breaklines and diagonal barriers without a fine mesh, what each needs from the mesh, and how each fits Wadi2D's explicit staggered sub-grid GPU scheme (level per cell, momentum per face, square 10-40 m cells in 32 x 32 tiles, optional block quadtree, tables from a 0.5 m DEM). It builds on `W1 .../research/raw/N01_subgrid_scheme_decision.md` and does not repeat it.

How the sources were read. **Full text read:** Bruwier et al. 2017 (accepted manuscript), Begmohammadi et al. 2021, Gao, Collecutt and Syme 2020 (BMT/TUFLOW), Zijlema's unSWASH paper (preprint), the Janet/UnTRIM grid manual, the Rana (3Di) 2D surface-flow page, the TUFLOW 2023-03 release notes (domain construction section). **Abstract or a search summary only:** Sehili et al. 2014 (full text refused, HTTP 403), Kernkamp et al. 2011, Casulli 2019, Liang et al. 2007, An and Yu 2012, Causon et al. 2000, Ryoo and Mandli 2021, Bitsch et al. 2026, Weller 2014, Guinot et al. 2017, Sanders and Schubert 2019. A search summary is an aggregator, so it is tagged [Likely] at best. **Not reached:** the TUFLOW manual body on Z shapes under SGS, the HEC-RAS 2D manual, the D-Flow FM technical reference, Stelling 2012 and Casulli and Stelling 2011 full text.

Tags: [Certain] read in a primary source, or arithmetic; [Likely] strong inference, or read only through a search summary; [Guessing] my construction, not in any source.

## 1. Staggered sub-grid on unstructured orthogonal grids: what the mesh must satisfy, and how face tables are built along arbitrary faces

### Takeaway
Every staggered sub-grid code in this family needs the line between two cell centres to cross the shared face at a right angle. This holds for UnTRIM2/Janet, D-Flow FM, unSWASH and 3Di, because a two-point level difference drives the face velocity. The face table itself is only the ground sampled along the face or beside it, so the face's orientation is free. None of these codes puts a barrier inside a cell: they move faces onto the feature by meshing. The one exception keeps the lattice: the cell clones of Casulli 2019, extended by Begmohammadi et al. 2021, split a cell by pixel connectivity.

### Cited Findings
- [Certain] unSWASH. A staggered scheme needs cell circumcentres, so that the segment joining the circumcentres of two cells crosses their shared face at a right angle; triangles and rectangles are the common polygons with a unique circumcentre. The pressure-gradient term is formally second order only if the two circumcentres lie at equal distances from the face (footnote 2). The covolume method is first order on general unstructured meshes and uses the Delaunay-Voronoi dual pair; it cites Perot, Kramer and Stelling, and Kleptsova et al. for reconstructing tangential velocity. — [Zijlema, SWASH on unstructured grids](https://swash.sourceforge.io/online_doc/unswash.pdf)
- [Certain] UnTRIM, through Janet. A grid of 3- and 4-sided polygons is strictly orthogonal when each polygon's vertices lie on a single circumcircle. For a quad whose vertices do not, Janet places the centre at the mean of two three-point circumcircles, which leaves a measurable deviation. Janet reports the maximum and mean deviation from orthogonality and a centre-distance to side-length ratio, and calls a grid strictly orthogonal when every centre connection deviates by less than 0.1 (the formula is an image and did not extract). Classic UnTRIM, before sub-grid, gives each polygon side one constant depth, and the polygon takes the maximum of its sides' depths. — [Janet UnTRIM support manual](https://smileconsult.de/files/janet-untrim-support.pdf)
- [Likely, search summary of the paper] Kernkamp, van Dam, Stelling and de Goede 2011, the basis of D-Flow FM, use a staggered C-grid on an orthogonal grid so that the pressure gradient across a face depends on two water levels only. An orthogonalisation step moves nodes iteratively to reduce non-orthogonal flow links. The reported speed is comparable to the structured Delft codes. Ocean Dynamics 61, 1175-1188. — [DOI 10.1007/s10236-011-0423-6](https://doi.org/10.1007/s10236-011-0423-6)
- [Likely, aggregator summary; full text refused] Sehili, Lang and Lippert 2014 (Ocean Dynamics 64, 519-535): the Janet preprocessor generates unstructured orthogonal grids with sub-grid bathymetry, using "subdivision" and "terracing topography" strategies. The grids are mostly flow-aligned quadrilaterals with a few triangles. The solver is UnTRIM2, run operationally on the Elbe estuary. Speed-up is about 20 against a classic fine unstructured model, with very good agreement of water levels. — [scholarhub record](https://scholarhub.vn/publication/:slug/fc4c4654-6d4f-4bbd-bc41-1cef98eff21c); [bohrium record](https://www.bohrium.com/paper-details/high-resolution-subgrid-models-background-grid-generation-and-implementation/813157051986345984-215)
- [Certain] 3Di/Rana. A flowline's 2D cross-section and exchange level come from the two pixel rows either side of the cell boundary, taking the higher pixel of each pair. A narrow obstacle that is not on the boundary changes neither, and water passes through it because the cell has one level. An explicit obstacle (a line with a crest level) overrides the exchange level of every flowline it intersects. Friction uses the depth at each pixel of the momentum domain. On sloping terrain the default overestimates wet area and underestimates friction. — [Rana 2D surface flow](https://docs.ranawaterintelligence.com/h_surfaceflow.html). A release note says every flowline intersecting an obstacle or levee is assigned to it [Likely, via search summary] — [3Di computational core release notes](https://docs.3di.lizard.net/a_releasenotes_computational_core.html)
- [Certain] Cell clones, as Begmohammadi et al. describe Casulli 2019:
  - At the maximum surface level, a host cell is cloned once for each group of connected pixels.
  - Clones of one host cell are not connected to each other; they share the cell's geometric centre and each keeps its own level.
  - An edge clone is a group of edge pixels shared by two clones of neighbouring cells, and each edge clone has its own velocity.
  - The lattice therefore stays, and only the number of unknowns grows.
  - Clones remove artificial cross-flow at the maximum level, but it can persist at lower levels where barriers emerge.

  — [Begmohammadi et al. 2021, AWR 153, 103939](https://ccht.ccee.ncsu.edu/wp-content/uploads/sites/10/2021/05/Begmohammadi-2021-AWR.pdf), [DOI 10.1016/j.advwatres.2021.103939](https://doi.org/10.1016/j.advwatres.2021.103939). Casulli 2019 is "Computational grid, subgrid, and pixels", IJNMF 90(3), 140-155 (citation from Begmohammadi's reference list; DOI not verified).
- [Certain] Begmohammadi et al. extend clones to sub-clones that split and merge with the level:
  - A sharp-crested weir, Q = (2/3) sqrt(2g) L_ew h^1.5 with L_ew = dx, joins a source sub-clone to a receiver until the receiver reaches the connection level. The pair then merges, and the merged level comes from inverting the merged V(eta) curve, so mass is conserved.
  - An edge is wet when the mean of its two cells' levels exceeds the highest pixel bed on the edge clone.
  - The solver is a staggered C-grid, semi-implicit, Newton-Raphson on the mildly nonlinear volume system (Casulli 2009), with the upscaled equations of Kennedy et al. 2019 (Ocean Modelling 144, 101491).

  — [Begmohammadi et al. 2021](https://ccht.ccee.ncsu.edu/wp-content/uploads/sites/10/2021/05/Begmohammadi-2021-AWR.pdf)
- [Certain, bibliographic only, unread] Later staggered sub-grid work: Casulli and Stelling 2011, IJNMF 67(4), 441-449, on 3D sub-grid; Platzek, Stelling, Jankowski, Patzwahl and Pietrzak 2016, IJNMF 80(12), 715-741, a semi-implicit sub-grid method on hierarchical grids; Viero and Valipour 2017, AWR 104, 1-14, on anisotropy in shallow inundation flow. — reference list of [Begmohammadi et al. 2021](https://ccht.ccee.ncsu.edu/wp-content/uploads/sites/10/2021/05/Begmohammadi-2021-AWR.pdf)
- [Certain, abstract] Bitsch, Heilmann, Engsig-Karup, Sørensen and Grooss 2026 (arXiv, revised October 2026):
  - Unstructured triangles, with selected elements subdivided into finer sub-grid triangles; bathymetry lives on the fine mesh and velocities on the coarse one.
  - WENO2 reconstruction and explicit RK2 time stepping.
  - A new sub-grid face-value reconstruction for partly wet cells, and a gravity-source discretisation that is well-balanced at sub-grid level.

  This is the only recent explicit unstructured sub-grid scheme found, and it is collocated finite volume. Barrier handling and error tables are not in the abstract. — [arXiv 2601.01895](https://arxiv.org/abs/2601.01895)
- [Certain, via N01] Volp et al. 2013 compute friction over the momentum domain, the two half cells, under a uniform friction slope. That reads a band, not the face line. — [Volp thesis chapter 2](https://www.vliz.be/imisdocs/publications/ocrd/300563.pdf), DOI 10.1002/wrcr.20324

### Inferences
- In every code read, the face table is built from pixels touching the face: 3Di uses the two adjacent pixel rows, TUFLOW samples points along the face, classic UnTRIM uses one value per side. Arbitrary orientation is therefore not the hard part. An unstructured orthogonal mesh fixes breaklines only because the mesher puts faces on them, not because of any better table. [Likely]
- For Wadi2D, an orthogonal mesh that conforms to arbitrary bank lines (Delaunay-Voronoi, or circumcentric quads as in Janet) is a meshing project of its own. It ends the 32 x 32 tile kernels, because cells would need indirect addressing. [Likely]
- Clones are the only published method in this family that keeps both the lattice and the staggered form and still puts a barrier inside a cell. Its published form is semi-implicit, not explicit or on a GPU. [Certain for what was found]

### Gaps
- The face-table construction in UnTRIM2 along arbitrary edges (Sehili 2014; Casulli and Stelling 2011) is unread; the text was refused or not reached.
- Whether 3Di applies a weir law at explicit obstacles was not found.
- No source found on how D-Flow FM snaps fixed weirs to net links. One search found nothing.
- Casulli 2019 itself is unread; its content is known only through Begmohammadi et al.

## 2. Porosity methods for barriers inside coarse cells: reported accuracy on diagonal walls and levees

### Takeaway
On a Cartesian grid, anisotropic porosity (a storage porosity per cell and a conveyance porosity per edge) has the same structure as Wadi2D's cell and face tables. Bruwier et al. 2017 measured the same pathology Wadi2D has. An oblique channel 4 cells wide on a 30 m grid overestimates normal depth by up to about 40 % without porosity. Edge porosity together with merging of low-storage cells brings the error to 1-3 % at every angle from 0 to 45 degrees. Edge porosity read over half a cell either side of the edge (their PS-A-2) detects nearby obstacles that a read along the edge misses, and it beat the along-edge read (porosity model error on depth about 1 % against 4 %).

### Cited Findings
- [Certain] Definitions:
  - The storage porosity is the void fraction of a cell; the conveyance porosity is the void fraction along an edge (Sanders et al. 2008).
  - PS-A-1, the standard edge read, is strongly mesh-dependent. It needs a gap-conforming mesh, which an unstructured mesh can provide and a Cartesian grid hardly can, and a read along the edge can miss nearby obstacles (Chen et al. 2012; Özgen et al. 2016).
  - PS-A-2 takes the minimum fraction of free length parallel to the edge over half a cell on either side of it.

  — [Bruwier et al. 2017, J. Hydrol. 554, 693-709, accepted manuscript](https://orbi.uliege.be/bitstream/2268/214640/1/Revision%202%2C%20Manuscript.pdf); [ORBi record](https://orbi.uliege.be/handle/2268/214640)
- [Certain] Merging:
  - A cell whose storage porosity is below a threshold phi_min is merged with the neighbour across the border of highest conveyance porosity; ties go to the neighbour of lowest storage, then split evenly.
  - The neighbour's storage porosity grows by the merged cell's.
  - Edge topology is rewritten: the outer edge of the merged cell connects to the receiver, and one shared edge becomes impervious.
  - Without merging, cells below phi_min are removed from the domain.

  — [Bruwier et al. 2017](https://orbi.uliege.be/bitstream/2268/214640/1/Revision%202%2C%20Manuscript.pdf)
- [Certain] **The oblique channel test**: rectangular channel, length 15 km, width 120 m, slope 0.2 %, Manning n 0.025, Q 2,000 m3/s, normal depth 2.517 m, dx 30 m, so 4 cells across, rotated from 0 to 45 degrees in 1-degree steps.
  - Classical shallow water: the numerical normal depth rises with angle, exceeds the theoretical value by almost 40 % between 20 and 35 degrees, and the excess falls again towards 45 degrees.
  - PS-A-1 is much closer at every angle and nearly compensates the staircase effect as phi_min is lowered.
  - With merging at phi_min 0.2, the excess drops from about 16 % to about 1 %; at low phi_min the depth is underestimated, by no more than 5 %.
  - To hold the error within 5 % over all angles: phi_min 0.05 without merging (worst 4 %), costing 14.5 x the classical model; or phi_min 0.75 with merging (worst 3 %), costing 1.9 x.
  - The classical model at 5 m (24 cells across) still errs by about 11 %, at about 63 x the cost of the 30 m model and about two orders of magnitude slower than PS-A-1 with merging for similar accuracy.

  — [Bruwier et al. 2017](https://orbi.uliege.be/bitstream/2268/214640/1/Revision%202%2C%20Manuscript.pdf)
- [Certain] Urban tests:
  - Meso scale: PS-A-1 at 10 m keeps upstream depths within about 0.5 % of a 1 m run and cuts run time by about two orders of magnitude.
  - Between meso and macro scale, uncalibrated: PS-A-2 has a porosity model error on depth of about 1 %, PS-A-1 about 4 %, and PS-A-2 is more accurate in every case of their Table 5.
  - Overall speed-ups are 10 to 100, with depth errors of a few per cent.
  - The best way to set the porosity parameters depends on the grid size relative to the obstacles.

  — [Bruwier et al. 2017](https://orbi.uliege.be/bitstream/2268/214640/1/Revision%202%2C%20Manuscript.pdf); merging follow-up [Bruwier et al. 2018, E3S 40, 06023](https://www.e3s-conferences.org/10.1051/e3sconf/20184006023)
- [Likely, abstract and search summary] Dual integral porosity (Guinot, Sanders and Schubert 2017, AWR 103, 16-31) separates cell-based and edge-based flow variables, adds a transient momentum-dissipation term, and outperforms the single integral porosity model. It was applied to a hypothetical levee breach near West Sacramento. Guinot 2017 (AWR 107, 43-55) explains integral porosity's oversensitivity to mesh design by a polarisation of fluxes. — [HAL hal-01465071](https://hal.archives-ouvertes.fr/hal-01465071), DOI 10.1016/j.advwatres.2017.02.009; Bruwier's text confirms that dual integral porosity outperforms the anisotropic integral model
- [Likely, abstract and search summary] PRIMo (Sanders and Schubert 2019, AWR 126, 79-95) solves the shallow-water equations on an upscaled grid far coarser than the raster DTM, with a sub-grid approach. It solves the Riemann problem with downscaled depths and velocities, runs sub-, super- and transcritical flow, and uses a 2D domain decomposition for whole-city runs. Its accuracy numbers were not reached. — [DOI 10.1016/j.advwatres.2019.02.007](https://doi.org/10.1016/j.advwatres.2019.02.007); [Shamkhalchian and de Almeida](https://eprints.soton.ac.uk/476689/2/Effects_of_reconstruction_of_variables_on_the_accuracy_and_computational_performance_of_upscaling_solutions_of_the_shallow_water_equations.pdf)
- [Certain] Özgen et al. 2016 introduced a depth-dependent anisotropic porosity model (cited in Bruwier's text). N01 recorded that edge porosities are sensitive to resolution. — [Bruwier et al. 2017](https://orbi.uliege.be/bitstream/2268/214640/1/Revision%202%2C%20Manuscript.pdf); [DOI 10.1016/j.jhydrol.2016.08.025](https://doi.org/10.1016/j.jhydrol.2016.08.025)

### Inferences
- Wadi2D's tables amount to a depth-dependent anisotropic porosity: V(eta) integrates the storage porosity, W(eta) and A(eta) are the edge porosity times the face length. That makes Bruwier's oblique channel the nearest published analogue of the `W3` rotated-channel test. Wadi2D's +6 % at 3 cells wide and 45 degrees lies between their classical model (+40 % at 20-35 degrees, falling towards 45, with 4 cells across) and porosity with merging (1-3 %). [Likely; the geometries differ: their 4 cells against Wadi2D's 3, their worst angle 20-35 against 45 degrees]
- The mechanism is different, so the cure does not transfer one for one. Bruwier's 16 % came largely from removing cells below phi_min, which merging undid. Wadi2D removes no cells. Its residual comes from sliver cells and dry faces along the staircase wall carrying advected momentum (`W6`). Merging each sliver cell along a wall into the cell that holds most of the channel would remove both the sliver and its dry-face momentum path. Whether that takes +6 % to Bruwier's 1-3 % is unknown. [Guessing; needs the `W3` test rerun]
- Wadi2D's ridge test (lift a face only where the line stands above the ground half a cell out on both sides) is the PS-A-2 window in another form: a published precedent for the `W36` diagnostic. [Likely]
- An edge porosity that is a function of depth carries a crest profile; one constant value cannot. Wadi2D's W(eta) on a lifted face already is that function, so the porosity literature adds a sampling rule (the window) and merging, not a new unknown. [Likely]

### Gaps
- Sanders et al. 2008, the dual integral porosity paper and PRIMo were not read in full, so I have no accuracy figures from them for diagonal levees.
- Every porosity paper found is urban or on flat ground. None tests a wall on steep ground, such as a bank on a gorge wall.

## 3. Cut-cell and embedded-boundary methods: can a breakline cut a square cell into two sub-cells on a lattice?

### Takeaway
Shallow-water cut cells come from the Godunov family and were built for solid boundaries: Causon et al. 2000, Liang et al. 2007 on a quadtree, An and Yu 2012 on a well-balanced quadtree. Small cells are handled by merging, or by a ghost-cell immersed-boundary update. A thin, overtoppable barrier inside a cell exists only as a research prototype, by cell merging (Ryoo and Mandli 2021). I found no GPU implementation and no staggered (level per cell, velocity per face) shallow-water cut-cell scheme. Sub-grid clones are the staggered-family equivalent: they split a cell by pixel connectivity, not by geometry, and keep the lattice and the cell centre.

### Cited Findings
- [Likely, abstract via search] Causon, Ingram, Mingham, Yang and Pearson 2000 (AWR 23(5), 545-562) cut solid regions out of a background Cartesian mesh and represent the boundaries by cut cells, with a multidimensional high-resolution upwind finite-volume scheme and an approximate Riemann solver. A 2001 sequel treats moving boundaries (AWR 24(8), 899-911). — [MMU e-space record](https://e-space.mmu.ac.uk/13420); [2001 record](https://repository.geologyscience.ru/items/8af146bf-46fa-4cd2-bc8d-fc8e2b4f0cb4)
- [Likely, abstract via search] Liang, Zang, Borthwick and Taylor 2007 (IJNMF 53(12), 1777-1799) use MUSCL-Hancock and HLLC on dynamically adaptive quadtree grids, with cut cells for curved boundaries. A ghost-cell immersed boundary updates the smallest cut cells to avoid the time-step restriction they would impose. Efficiency is much better than a uniform grid with cut cells. — [DOI 10.1002/fld.1363](https://doi.org/10.1002/fld.1363)
- [Likely, search summaries] An and Yu 2012 (AWR 39, 60-70): well-balanced shallow-water flow on quadtree cut-cell grids, which a later paper describes as built on hydrostatic reconstruction. The group's analysis of the Gerris solver (second-order Godunov, source and flux terms kept in balance on quadtree cut cells) covers the Malpasset dam break and the Baeksan levee failure. — [DOI 10.1016/j.advwatres.2012.01.003](https://doi.org/10.1016/j.advwatres.2012.01.003); [Gerris analysis](https://research.knu.ac.kr/en/publications/analysis-of-an-open-source-quadtree-grid-shallow-water-flow-solve/); [Ghazizadeh et al. citing it](https://arxiv.org/pdf/1911.12002)
- [Certain, abstract] Ryoo and Mandli 2021 apply cell merging to shallow water with a barrier embedded in a Cartesian grid: wave propagation with gradient reconstruction, minmod and Barth-Jespersen limiters. They report second-order convergence for a straight and a V-shaped barrier, plus island inundation. The abstract says nothing on well-balance, overtopping or GPUs. — [arXiv 2112.09566](https://arxiv.org/abs/2112.09566)
- [Likely, search summaries] Merging builds control volumes comparable to regular cells, and some methods merge only cells below a set partial length [arXiv 1711.11361](https://arxiv.org/pdf/1711.11361). A depth-averaged cut-cell model merges small cells with neighbours to satisfy the CFL condition [CSDMS 2011 poster, C. Yu](https://csdms.colorado.edu/wiki/CSDMS_2011_annual_meeting_poster_Chunshui_Yu).
- [Certain] BMT claim that a fixed grid with sub-grid sampling gives results of the same quality as a well-designed flexible mesh or a cut-cell model.
  - U-bend flume, 1.7 m wide: sub-grid sampling removes the saw-tooth velocities and the artefact energy loss at walls not aligned with the grid, and the water-surface drop round the bend matches the flume.
  - Brisbane River: the head loss differs by 0.25 m (under 10 %) between 10 m and 50 m cells with sub-grid sampling, against 0.94 m without it.

  — [Gao, Collecutt and Syme 2020, IAHR-APD](https://www.tuflow.com/media/5020/2020-application-of-higher-order-bathymetry-representation-in-fixed-grid-shallow-water-solvers-gao-et-al-iahr-apd-japan.pdf)
- [Certain] Clones as the connectivity form of a cut cell: see section 1. — [Begmohammadi et al. 2021](https://ccht.ccee.ncsu.edu/wp-content/uploads/sites/10/2021/05/Begmohammadi-2021-AWR.pdf)

### Inferences
- **Well-balance is not the obstacle in Wadi2D's form; the small cell is.** A cut sub-cell with its own V(eta) and its own face tables stays well-balanced by construction, because the pressure term is a level difference (N01 finding 2). The well-balance trouble of Godunov cut cells, reconstructing the bed on an irregular cell, does not arise. A sliver sub-cell still has a tiny wet area Omega, so N01's gravity bound dt = sqrt(2 Omega dx / (g sum A_f)) collapses or the cell empties in one step. Merging, or a floor on Omega, is mandatory. [Likely]
- A geometric cut cell needs geometry: the sub-cell centroid, the cut face's length and normal. The cut face is oblique to the lattice, so the two-point pressure gradient across it is non-orthogonal (section 5). Clones avoid this: they share the cell centre and never take a gradient across the barrier, which they cross through a weir law instead of a momentum face. [Likely]
- On the GPU, cut cells break the uniform stencil. A per-tile list of flagged cells, with a second layer of sub-cell unknowns, is feasible, but every face kernel gains a branch and an indirection. [Guessing]

### Gaps
- Zhou, Causon, Mingham and Ingram 2004 (cut cells over complex bed topography) and the Causon/Ingram full texts are unread.
- No staggered shallow-water cut-cell scheme was found, and no GPU shallow-water cut-cell code (two searches).
- Berger and LeVeque's h-box method for thin barriers was not read.
- Ryoo and Mandli's handling of overtopping is not in the abstract.

## 4. Cell-centred versus face-centred surface: why a face up to half a cell off a bank line misreads the ground, and the published remedies

### Takeaway
Every code read takes a face's ground from the pixels on the face or right beside it, so a line feature only counts where it touches a face. Tools that let a drawn line override faces apply the line's elevation to every face the line crosses, which is the staircase: TUFLOW thin breaklines, 3Di explicit obstacles, and Wadi2D's `W36` breakline. These tools were made for ridges (levees, road crests), not for banks on a wall. The published safeguards are of two kinds:

- "Only raise" rules: TUFLOW's RIDGE/MAX, 3Di's higher-pixel-of-each-pair.
- Window rules: Bruwier's half-cell band.

No source samples the line's ground and imposes it on a face up to half a cell away on steep ground, and that is the `W36` failure. Separately, every sub-cell barrier method found pairs the barrier with an overtopping law, which `W36` dropped.

### Cited Findings
- TUFLOW:
  - [Certain] With thin breaklines only cell-side and cell-corner elevations change (2023-03 release, section 2.2.6); the default high-resolution output adjustment is ON CELL SIDES.
  - [Certain] Sub-grid sampling takes an odd number of points per face so the mid-point is sampled: 11 by default (121 per cell), capped at 31 by default, hard limit 127.
  - [Certain] "SGS Approach == Method C", the default, keeps sampled elevations for cells and faces that terrain layers modify only in part.

  — [TUFLOW 2023-03 release notes, domain construction](https://docs.tuflow.com/classic-hpc/release/2023-03-AE/TwoDDomConstr-1.html)
  - [Certain] With sub-grid sampling every face captures the lowest elevation along its length, to the sampling resolution, so sub-cell flow paths survive. — [Gao et al. 2020](https://www.tuflow.com/media/5020/2020-application-of-higher-order-bathymetry-representation-in-fixed-grid-shallow-water-solvers-gao-et-al-iahr-apd-japan.pdf)
  - [Likely, search summaries of TUFLOW pages] ZU and ZV cell-side points wet and dry independently of the cell centre, which allows thin obstructions without changing storage [Zpt description](https://wiki.tuflow.com/Zpt_Description). A face lower than the lowest centre on either side is raised automatically [Message 3520](https://wiki.tuflow.com/TUFLOW_Message_3520). Z lines are legacy and some of their options may not work with sub-grid sampling; thin Z shape lines are recommended [Topography guidance](https://wiki.tuflow.com/Topography_Guidance).
  - [Likely, secondary slides] A thin line changes ZH, ZU and ZV only under MAX/RIDGE, while GULLY/MIN also connects ZC for a continuous path. — [Topography modifications in TUFLOW](https://www.slideshare.net/slideshow/topography-modifications-in-tuflow/87234242)
- [Certain] 3Di takes the higher pixel of each pair across the boundary, a two-pixel window (1 m on a 0.5 m DEM) that keeps a ridge only if it lies on the boundary. An explicit obstacle imposes its crest level on every flowline it crosses. — [Rana 2D surface flow](https://docs.ranawaterintelligence.com/h_surfaceflow.html)
- [Likely, secondary forum posts] HEC-RAS:
  - A ridge running diagonally through a cell is missed by its faces, because the cell reduces to a volume curve.
  - Breaklines exist to put faces on high ground.
  - Flow passes through every low point of a face, even when a dry ridge divides the face.

  — [Kleinschmidt, 2D mesh leaking part 2](https://forum.kleinschmidtgroup.com/ras-post/2d-mesh-leaking-part-2-2d-area-breaklines); [HEC-RAS blog](https://hecrasmodel.blogspot.com/2015/04/2d-mesh-leaking-part-2-2d-area.html). A consultant report is said to quote the manual: a face should represent a consistent overbank elevation rather than sit as close to the bank as possible [Guessing: the manual itself was not read]
- [Certain] Bruwier PS-A-2: the edge read takes the minimum free fraction over half a cell either side, and was more accurate than the along-edge read in every macro-scale case. — [Bruwier et al. 2017](https://orbi.uliege.be/bitstream/2268/214640/1/Revision%202%2C%20Manuscript.pdf)
- [Certain] Clones find barriers by the connectivity of pixels below a level, and join sub-clones across a barrier by a sharp-crested weir until they merge. — [Begmohammadi et al. 2021](https://ccht.ccee.ncsu.edu/wp-content/uploads/sites/10/2021/05/Begmohammadi-2021-AWR.pdf)
- [Certain, bibliographic, unread] Hodges 2015, NHESS 15, 1011-1023, on representing hydrodynamically important blocking features in lidar topography; Li and Hodges 2019 on channel connectivity in 2D marsh models. Both are candidates for automatic ridge detection. — reference list of [Begmohammadi et al. 2021](https://ccht.ccee.ncsu.edu/wp-content/uploads/sites/10/2021/05/Begmohammadi-2021-AWR.pdf)
- [Certain, N01 and the design note] A staggered face with the whole level drop driving it passes 5 to 100 x critical flow at a thin crest in 1D. The `cw` critical-flow limit on crest faces gives 0.996 of critical. — `W1 .../N01_subgrid_scheme_decision.md` section 2.7; `design_note.md` sections 1 and 3

### Inferences
- **Problem 1, by arithmetic.** [Certain, arithmetic; that it is the cause of the -11.1 % is Likely, consistent with the `W36` ridge diagnostic]
  - A staircase face lies up to delta = dx/2 from the true line. On a wall of cross-slope S_w, the line's ground differs from the face's own ground by up to S_w delta.
  - On a 1:1 gorge wall that is up to 10 m at dx = 20 m and 5 m at 10 m.
  - Imposing the line's profile closes faces inside the gorge up to wall height. That matches a loss of 11.1 % at 20 m with a smaller loss at 10 m.
- **The fix in published form** is a window test, and the sources offer two versions:
  - (a) Raise a face only where the feature is a ridge relative to half a cell either side, and never lower it. This is PS-A-2's window with TUFLOW's RIDGE/MAX semantics, and the `W36` diagnostic is this rule, within 0.3 %. [Likely]
  - (b) Use connectivity instead of a line, as clones do. [Guessing: my construction, untested]
    - For each face, define a blocking elevation z_b: the lowest level at which pixels of cell L join pixels of cell R inside L ∪ R. That is the minimax ("pour-point") path between the two cells' low areas, found by a priority flood over the 2 (dx/0.5)^2 pixels at preprocessing.
    - Floor the face table's invert at z_b. A ridge anywhere in the two cells then blocks the face up to its saddle level.
    - A gorge face is never lifted, because the gorge floor connects along the gorge.
    - The drawn line only marks where to compute z_b.
    - Limit: if a ridge splits one cell into two water bodies, a single level per cell cannot hold both. That case needs clones.
- **Problem 3.** Every sub-cell barrier method found carries an overtopping law: Begmohammadi's weir between sub-clones, Wadi2D's own `cw` limit on crest faces. A lifted breakline face without one behaves like N01's thin crest, which explains `W36`'s 2.6-3.8 x critical. The literature and the project's own 1D evidence both say: a face whose invert sits above both adjoining mean beds needs the critical-flow cap. Apply it to breakline faces wherever the lift is active (natural-crest trigger: invert above both mean beds by 5 cm). [Likely]

### Gaps
- The TUFLOW manual sections on Z shape layers under sub-grid sampling (7.2.6.2) and on sub-grid sampling itself (7.3.3) were not reached: only the table of contents loaded. So whether a thin line replaces the face's sampled profile or only sets its minimum, and whether RIDGE survives under sub-grid sampling, remains unknown.
- The HEC-RAS 2D manual text on face profiles under breaklines was not read directly.
- No source applies a window or connectivity rule on steep ground.

## 5. A strip of aligned quads beside square tiles: interface faces, non-orthogonal error, and correction terms

### Takeaway
A rotated strip meeting axis-aligned squares makes faces that are both non-conforming and non-orthogonal. Across such a face the staggered two-point gradient measures the slope along the centre line, not normal to the face, and picks up sin(theta) of the tangential slope. Production staggered codes (D-Flow FM, UnTRIM, unSWASH) avoid this by orthogonalising the mesh, not by correction terms. Non-orthogonal C-grid corrections exist in atmospheric modelling (Weller 2014), at the price of exact energy conservation. A strip whose long sides are open 2D interfaces therefore carries a lateral error along its whole length. The variant that works is a strip whose banks are walls, crossed only by weir links, as 1D-2D models do.

### Cited Findings
- [Certain] Orthogonality as the staggered requirement, and second-order accuracy only with equidistant centres. — [Zijlema, unSWASH](https://swash.sourceforge.io/online_doc/unswash.pdf)
- [Likely, search summary of the paper] D-Flow FM relies on an orthogonal grid and an orthogonalisation step, for efficiency and the two-point pressure gradient. — [Kernkamp et al. 2011](https://doi.org/10.1007/s10236-011-0423-6)
- [Certain] Janet checks every centre connection for orthogonality and recentres quads that are not circumscribable, at the cost of a measurable deviation. — [Janet manual](https://smileconsult.de/files/janet-untrim-support.pdf)
- [Likely, search summary] Weller 2014 (GMD 7, 779-797) builds a C-grid for arbitrary non-orthogonal grids that keeps some mimetic properties and gives up exact energy conservation for accuracy, including a non-orthogonal correction tested on a diamond grid; Thuburn and Cotter 2012 set the constraints, and Thuburn et al. 2014 give a scheme for duals of triangles and quadrilaterals. Peixoto 2016 lists three sources of inconsistency for TRSK-type C-grids on non-uniform grids. — [Weller 2014](https://gmd.copernicus.org/articles/7/779/2014/gmd-7-779-2014.pdf); [Peixoto 2016](https://pedrosp.ime.usp.br/papers/Peixoto2016.pdf)
- [Guessing: secondary source quoting the manual] HEC-RAS runs with collinear faces but may compute wrongly across such a cell. — search summary of [Kleinschmidt forum posts](https://forum.kleinschmidtgroup.com/ras-post/2d-mesh-leaking)
- [Certain, bibliographic] Sub-grid on hierarchical (refined) staggered grids exists: Platzek et al. 2016, and Stelling 2012 quadtree in 3Di (see N01). Wadi2D already runs a 2:1 block quadtree (`W10`).

### Inferences
- **The error, in numbers.** [Certain, arithmetic]
  - The two-point gradient (eta_R - eta_L)/d equals grad(eta)·s, with s = cos(theta) n + sin(theta) t.
  - Its error in the normal gradient is (cos(theta) - 1) d(eta)/dn + sin(theta) d(eta)/dt.
  - Where a 45-degree strip meets squares along its long side, theta = 45 degrees and the tangential share is 0.71. The tangential slope there is the channel's longitudinal slope, so 71 % of it drives a false lateral flux.
  - At theta = 5 degrees the share is 0.087.
- **A strip interface is also a cut-cell interface.** A strip cell's edge crosses several square faces obliquely, so each interface face is a polygon intersection, which is the geometry of section 3. A strip therefore brings both problems along its whole length, unless its long sides are not open interfaces. [Likely]
- **The variant that works** makes the strip's banks walls, crossed only by overtopping through a weir or control-level link and never by a momentum face, and joins the strip to the tiles only at its two ends, which can be made orthogonal. That is a 2D channel domain with lateral weir links, the 1D-2D pattern HEC-RAS and TUFLOW use. It fits wadis with defined banks, not fans or braided reaches. [Likely]
- **A correction term keeps well-balance.** A deferred correction that rebuilds the tangential gradient from cell levels and subtracts it is zero when the water is at rest, so the lake at rest is kept. It costs exact energy conservation (Weller) and adds a stencil wider than two points. [Guessing for the staggered sub-grid case; no shallow-water sub-grid source found]
- **Wadi2D's quadtree precedent.** Its 2:1 interfaces offset the centre line from the face centre by dx/4 without rotating it, so they stay orthogonal and are not evidence that rotated faces would be tolerated. [Likely]

### Gaps
- The D-Flow FM technical reference (orthogonality tolerance, any correction term) was not read.
- No source quantifies the error a rotated non-orthogonal face adds in a staggered shallow-water scheme.

## 6. Ranking for Wadi2D's staggered sub-grid GPU scheme

### Takeaway
Keep the lattice and make the faces smarter: a ridge-only lift with a half-cell window (or a connectivity-derived face invert), the critical-flow cap on every lifted face, and merging of sliver cells along staircase walls. This is the only option that addresses all three measured problems with evidence, needs no kernel rewrite, and keeps the tiles. Clones are the principled next step for a ridge that splits a cell. Geometric cut cells, an aligned strip and a fully unstructured orthogonal mesh each cost a second engine, with no GPU staggered sub-grid precedent for the first two.

### Cited Findings
The table cites sections 1 to 5. The tags in it are the evidence behind each expected accuracy.

| Rank | Option | Expected accuracy at diagonal breaklines | What changes in the kernels | Risk |
|---|---|---|---|---|
| 1 | **Keep the lattice, smarter faces**: (a) lift a face only where the line is a ridge over half a cell either side, never lower it (PS-A-2 window, TUFLOW RIDGE semantics); optionally (b) a face invert floored at the minimax pour-point elevation between the two cells; (c) the `cw` critical-flow cap on every lifted face; (d) sliver cells along staircase walls merged into the main neighbour | Problem 1: within 0.3 % in all four `W36` cases with (a) [project diagnostic, `W36`]. Problem 3: thin crest 0.996 of critical with the cap [project, design note]; without it 2.6-3.8 x. Problem 2: +6 % today; the porosity analogue reaches 1-3 % with merging [Certain for Bruwier's 4-cell 30 m channel; Guessing for Wadi2D] | (a) and (b) are preprocessing in the face-table builder only. (c) uses the existing `cw` branch with a new trigger. (d) changes the table builder and the cell-to-face map at flagged cells; kernels unchanged if a merged cell is represented as a cell with zero-area internal faces | **Low.** Residual: a ridge diagonal inside one cell that touches no face still leaks, as in TUFLOW and HEC-RAS [Likely]; a cell split by a ridge still has one level |
| 2 | **Porosity ideas beyond that**: merging thresholds tuned on the `W3` channel; separate edge parameters for the mass, momentum-flux and pressure terms (Bruwier's PS-A-D); the dual-integral-porosity momentum dissipation | Bruwier: 16 % to 1 % at phi_min 0.2; worst 3 % over 0-45 degrees at 1.9 x cost [Certain]. Separate edge parameters: small gain, needs a priori flow knowledge [Certain that they flag it] | Table builder; a second face coefficient in the momentum kernel for PS-A-D | Low to medium; the gain is incremental because Wadi2D's staggered form already separates cell and face variables [Likely] |
| 3 | **Clones**, cut cells by connectivity (Casulli 2019; Begmohammadi et al. 2021): a cell crossed by a ridge gets a second level; faces split into edge clones; the ridge is an internal weir or control-level link; clones merge when the ridge drowns | Removes artificial cross-flow at barriers smaller than the cell; Begmohammadi report considerable improvement but no percentage extracted [Certain qualitative]. The `W36` gorge-wall error cannot arise, because a wall does not disconnect pixels [Likely] | A sparse second layer of unknowns per tile; the face kernel loops over edge clones; continuity per clone; split and merge are branch-heavy. The published solver is semi-implicit with Newton; explicit on a GPU is unproven | **Medium to high.** Small clones throttle dt (needs a floor or merging); no explicit GPU precedent found |
| 4 | **Aligned strip** of quads along a wadi, banks as walls with weir links, joined to the tiles at its ends | Inside the strip as an aligned channel: normal depth within 1 % at 3 cells wide [project, design note]. With open long sides, a false lateral drive of sin(theta) of the longitudinal slope, 71 % at 45 degrees [Certain, arithmetic] | A second mesh type with indirect addressing, an interface flux kernel, a strip mesher, tangential-velocity reconstruction for advection in the strip | **High**; fits defined wadis only, not fans or braids, and duplicates what option 1 already gives at 1-3 % |
| 5 | **Geometric cut cells**: the line cuts a square into two polygons with their own centroids and an oblique cut face | Godunov cut cells converge at second order on embedded barriers [Certain, Ryoo and Mandli abstract]. In the staggered form well-balance is kept by construction [Likely]; the oblique cut face reintroduces the non-orthogonal error of section 5 [Likely] | Per-cut-cell geometry, a non-orthogonal gradient or a weir across the cut, small-cell merging or immersed-boundary updates, branches in every face kernel | **High**; no staggered shallow-water or GPU cut-cell precedent found |
| 6 | **Fully unstructured orthogonal** (UnTRIM2, D-Flow FM, HEC-RAS style): faces put on every breakline by the mesher | Exact by meshing where the mesher conforms [Likely]; sub-grid speed-up about 20 against a classic fine unstructured model [Likely, Sehili summary] | A new engine: indirect addressing at 2-4 x the cost per cell (decision 4), an orthogonal mesher, Perot-type reconstruction; tiles and quadtree lost | **Highest**; it is the reference solution to compare against, not the next step |

### Inferences
- Problems 1 and 3 are both face-table and face-rule problems, not mesh problems. The literature's answers (window or ridge rules, only-raise semantics, an overtopping law at every sub-cell barrier) all fit inside option 1 with no kernel change beyond the existing crest branch. [Likely]
- Problem 2 is the only one that resembles a mesh problem, and Bruwier's evidence says merging, not meshing, is the cheap fix on a Cartesian grid. It must be retested on Wadi2D's own `W3` case, because Wadi2D's mechanism (dry-face advection) differs from theirs (cells removed below phi_min). [Likely]
- Order of tests that would change this ranking: (1) the `W3` 45-degree, 3-cell channel with sliver merging; (2) a diagonal levee inside cells, the case option 1 cannot fix, to measure how much a clone would buy; (3) the `W36` four cases with the face invert from option 1(b) against the ridge-only lift. [Guessing on the order]

### Gaps
- No quantitative clone results were extracted, and no explicit or GPU clone implementation was found.
- No source tests any of these methods on steep wadi terrain; all evidence is urban, coastal, riverine or flume.
- The full texts of Casulli 2019, Sehili 2014, Stelling 2012, the TUFLOW sub-grid sampling manual body and the D-Flow FM technical reference were not reached.
