# Fix the faces, keep the tiles

**[Likely] Tiles plus aligned strips would fix one of the three measured failures and half of another, and would leave the free overfall exactly where it is. All three are errors in the face rules of the lattice Wadi2D already has, so fix them there first: no mesher and no second kernel path.**

The leading idea works on the wrong layer. [Certain, measured] A free overfall over a breakline face passes **2.62 to 3.81 x critical flow**, and the ratio hardly moves with the cell (2.95 at 5 m, 2.87 at 20 m). A staggered face has no critical section of its own. An aligned strip is built from the same kind of face and would over-carry the same way, so the cap the owner already wants is the whole fix for that issue. [Certain, measured as a diagnostic] Faydh 01's **-11.1 % at 20 m** comes from ground read wrongly onto faces up to half a cell off a bank line (median rise 0.55 m, maximum 22.1 m). **Lifting a face only where the line is a true ridge brought all four bank cases within 0.3 % of no lines.** A strip would also cure it, by putting the face on the line, at the price of a new engine path. [Likely] Most of the W26 bank-line loss (-9.7 to -35.5 %) is the crest law, not the geometry: the same lines a metre underground still cost 7.8 %. Today's cap is depth-based, so it binds at a face Froude number of 0.544. A 45-degree line then multiplies it by 0.71 on every face, while the flood runs along the line. The recommendation is three changes to the table builder and to step [6] of the face kernels:

- a ridge-only lift, with its distance as a named setting;
- a coefficient-free energy bound on breakline and natural-crest faces;
- a crest-line cap on the line-normal component only, with D-Flow FM's projected width on the weir branch and nothing on the tangential flow.

If a mesher is ever needed, MeshKernel leads Gmsh. It has an LGPL-2.1 core, an MIT wrapper and a 1.1 MB Windows wheel, and it is the only candidate that measures and optimises orthogonality. Triangle and JIGSAW cannot ship under GPL-3.0. Every face-law claim beyond the ridge diagnostic is unproven until the dock tests in section 5 pass, because no production code documents the line-normal split. The strip comes back only if those tests fail, or if narrow diagonal wadis need better than the lattice's worst case today: +4.2 % on vertical walls and +5.9 % on 2:1 banks, at three cells and 45 degrees.

## Each failure sits in a face rule, not in the mesh

**The staircase error is a sampling error, and the industry shares it.** [Certain, arithmetic] A staircase face lies up to dx/2 from its line. On a wall of cross-slope S_w, the line's ground therefore stands up to S_w dx/2 above the face's own ground: up to 10 m on a 1:1 gorge wall at 20 m cells, 5 m at 10 m. W36's breakline imposes the line's ground on the face. At Faydh 01, 20 m, half the faces rose more than 0.5 m, the 90th percentile by 4.39 m and the worst by 22.1 m, which walls in the gorge by up to half a cell on every bank (W36, `feature/breakline-faces:W36 breakline faces/README.md`).

[Likely] Wadi2D is not the outlier here. The lattice family raises every face whose centre-to-centre link crosses the line:

- TUFLOW: cross-hair selection, and each face point takes its elevation from the perpendicular intersection with the line ([TUFLOW Manual 2026.3, 7.2.5-7.2.6](https://docs.tuflow.com/classic-hpc/manual/2026.3/06-2D-Domains.html)).
- 3Di: obstacles override the exchange level of every flowline they intersect ([Rana docs](https://docs.ranawaterintelligence.com/h_surfaceflow.html)).
- D-Flow FM: fixed weirs snap to the net links of crossed flow links ([D-Flow FM TRM s.6.7.7](https://content.oss.deltares.nl/delft3dfm2d3d/D-Flow_FM_Technical_Reference_Manual.pdf)).
- SFINCS and MIKE dikes follow the same rule.

So TUFLOW would put a bank's wall elevation onto gorge faces exactly as W36 did.

The cure also has precedents:

- ICM measures a Height crest from "the highest of the ground levels of the two computational elements" ([ICM 2026, Base Linear Structure](https://help.autodesk.com/cloudhelp/2026/ENU/ICMLIVE-Help/files/GUID-1178A2A1-7294-41D3-B939-000A2CBD494B.htm)).
- D-Flow FM keeps a toe level on each side and defines the weir only where the crest stands above it.
- Bruwier's PS-A-2 reads edge porosity over a window of half a cell either side. It was more accurate than the along-edge read in every macro-scale case, with a porosity model error on depth of about 1 % against 4 % ([Bruwier et al. 2017](https://orbi.uliege.be/bitstream/2268/214640/1/Revision%202%2C%20Manuscript.pdf)).

W36's ridge-only diagnostic is that window, and it gave -0.0, +0.0, -0.0 and -0.3 % on the four cases. The uncomfortable half of the finding stands: **a stream bank on a slope is not a ridge.** Under the rule, a bank breakline is a no-op by construction. A strip would also cure issue 1, since a face on the line reads the line's true ground, but the ridge rule gets there in the table builder.

**The overfall error is a missing critical section, and no mesh supplies one.** [Certain, arithmetic] A face that carries the full upstream depth H at the velocity sqrt(2gH), which converts the full head, passes q = sqrt(2) sqrt(g) H^1.5. That is 2.598 x the critical q_max(H) = 1.7046 H^1.5. W36 measured 2.62 at a 1.5 m head. [Likely] In the steady face balance u du/dx = -g dη/dx, dx cancels, which is why the ratio does not fall with refinement. HEC-RAS's 2D overflow has the same structure: W11 measured 4.6 x critical on Bidah. HEC itself concedes that its 2D equations over-predict free-falling weir flow (`W11 validation round two/drafts/_t1_section.md`).

Every production code that handles overtopping well puts the control on the crest face:

- D-Flow FM floors the crest depth at two thirds of the energy head, h_u = max(ζ_R − z_c, 2/3 E). In free flow that gives exactly q_max(E), and it drowns continuously ([D-Flow FM TRM eq. 6.217-6.234](https://content.oss.deltares.nl/delft3dfm2d3d/D-Flow_FM_Technical_Reference_Manual.pdf)).
- TUFLOW HPC applies a weir equation on breakline faces, with upstream energy as the head by default ([TUFLOW 2023-03 release notes](https://docs.tuflow.com/classic-hpc/release/2023-03-AF/TwoDSolv-1.html)).

The owner is right that a cap is needed whatever the mesh. The evidence goes further: a cap, or a modified drive, is the entire fix for issue 2, and a strip adds nothing to it.

**The bank-line loss is the cap's form acting on flow that runs along the line.** [Certain, code] Step [6] of `wadi2d/solver/gpu/kernels/faces.cu` caps a positive-coefficient face at |q| ≤ c A sqrt(A/W), on the face's current flow area with no velocity head. Only shaped objects read the energy head. [Certain, arithmetic] That cap binds on uniform flow whenever Fr_n > (2/3)^1.5 = 0.544. With the 45-degree length factor of 0.71 on every face, it binds above about 0.385. W26's diagnostic isolates the law: bank lines placed 1 m below the ground change no face elevation and still cost **7.8 %** of Bidah's peak at 10 m, with the same 3.3 x steps (`W26 suggested breaklines/README.md`). W36 points the same way from the other side: keeping the natural-crest depth cap on breakline faces cost -5.8 % and -13.0 % on Faydh 01, against -2.4 % and -11.1 % without it.

[Likely] The mechanism is a zigzag. Drowned along-line flow crosses the staircase faces back and forth with zero net flux across the line. At a gorge Froude number of 1.5, those faces are allowed about 36 % of what they carry ([overfall note, section 6](../research_notes/Breakline%20mesh%20options%20for%20Wadi2D/overfall_weir_cap.md)). This is a prediction to test (T4), not an observation. [Certain, arithmetic] An energy cap on the normal head E_n = e + u_n²/2g cannot bind on any uniform flow: the ratio Fr_n / ((2/3)(1 + Fr_n²/2))^1.5 is 0.770 at Fr_n 0.5, 1.000 at 1.0 and 0.890 at 1.5.

A strip would stop along-line flow crossing faces. But a design flood stands metres above a bank placed 0.5 m above the low-flow bed, so the strip's long sides would be open 2D interfaces. [Certain, arithmetic] An open interface between a rotated strip and the squares picks up sin θ of the tangential slope in its two-point gradient, 0.71 of the channel's longitudinal slope at 45 degrees ([subgrid note, section 5](../research_notes/Breakline%20mesh%20options%20for%20Wadi2D/subgrid_porosity_cutcell.md)). The strip moves the error from the law to the interface.

**Where the evidence agrees with him, and where it does not.**

It agrees on three points:

- The square tiles stay. Wadi2D's 0.6 ns per cell step sits beside the best published structured GPU code once bandwidth-scaled: Brodtkorb's second-order solver is 0.26 to 0.53 ns on an RTX 5080 equivalent [Guessing on the scaling] ([Brodtkorb et al.](https://brodtkorb.org/files/publications/brodtkorb_kp_on_gpus.pdf)). Unstructured kernels cost 1.5 to 2 x per cell on the same card and scheme ([Castro et al. 2011](https://comptes-rendus.academie-sciences.fr/mecanique/item/10.1016/j.crme.2010.12.004.pdf)).
- The critical-flow cap is needed whatever the mesh.
- Crest geometry matters most. The only multi-package levee benchmark found that crest-elevation errors were "often comparable to, if not larger than overtopping depths" ([EA 2010, SC080035, s.4.7](https://assets.publishing.service.gov.uk/media/5a75765c40f0b6360e4744dd/scho0510bsno-e-e.pdf)).

It disagrees on two:

- The strip as the fix for the three issues.
- Gmsh as the mesher.

## Seven options against his six criteria

The table scores each option on exactly his six criteria, plus the three issues: (1) the staircase error, Faydh 01 at 20 m, -11.1 %; (2) the free overfall, 2.6 to 3.8 x critical; (3) the W26 bank-line loss. GPU speed is relative to today's 0.6 ns per cell step. Effort figures are [Guessing] unless a project record gives them.

| Option | GPU speed per cell | Accuracy at breaklines | Licence fit with GPL-3.0 | Windows and Python integration | Sub-grid compatibility | Effort | Solves which of the three issues |
|---|---|---|---|---|---|---|---|
| **Lattice with smarter faces**: ridge-only lift; energy cap on the normal component; per-face projection width on the weir only | 1.0 [Certain, measured base]; a few operations and one float2 per line face [Likely]; no step penalty (W36 breaklines took at most 1.11 x the steps of no lines) | Ridge rule: four bank cases within 0.3 % [Certain, diagnostic]; crest cap 0.977-0.997 of critical [Certain]; oblique and along-line law not yet run [Guessing]; residual 45-degree 3-cell channel up to +4.21 % (W6) | Nothing new | Nothing new: table builder and step [6] of both kernels | Native; the ridge window is PS-A-2 in table form [Likely] | 2-4 weeks with dock tests | 1 measured; 2 by construction; 3 predicted |
| **Tiles plus aligned strips** (MeshKernel or Gmsh) | Tile cells 1.0-1.05, strip cells 2-4, domain mean 1.01-1.1 at a 0.3-3 % strip share; global step x1.6-4 if the strip is thinner than dx/2-dx/4 in the limiting flow, 1.02-1.2 with its own LTS class [Guessing] | Exact faces inside the strip; open long sides carry sin θ of the longitudinal slope (0.71 at 45°) [Certain, arithmetic]; W3's moved-vertex interface oscillated to +29 % on banks [Certain, prototype] | MeshKernel LGPL-2.1 core and MIT wrapper; Gmsh GPLv2+, Blossom check pending [Certain/Likely] | pip wheels of 1.1 MB or 42 MB, run in the engine process; display through MDAL UGRID [Likely] | Strip faces fine; interface faces need polygon-intersection tables; only MeshKernel measures orthogonality [Likely] | Months: strip mesher, second cell and face kernels, interface kernel, LTS class, plugin | 1 yes; 2 no; 3 partly |
| **Fully unstructured orthogonal** (MeshKernel) | 2-4 x per cell step [Likely]; the worst cell sets the global step unless per-cell LTS | W3 triangles under 1.4 % at every bend and junction, Q within 0.11 %, the only option that held everywhere [Certain, CPU prototype, first-order momentum] | MeshKernel fits | Wheel; results stop being rasters without resampling (W3) | Face tables fine; orthogonality mandatory; well-balance kept [Likely] | A new engine: all kernels, CPU twin, tile layout, table builder, parity tests (W3) | 1 yes; 2 no; 3 partly |
| **Quadtree refined at lines** | 1.05-1.3 per cell [Likely]; extra cells and a smaller step at lines; tile LTS pays only at scale (W10: 1.6 x at 4.8 M cells, slower on 90 tiles) | Halves the offset per level: on uniform cells Faydh 01 passes at 10 m (-2.4 %) where 20 m fails; an 8-row band alone read 6.8 % low (W23); refining did not cure W3's bend error (+3.39 % at 5 m) | Nothing new | Exists (W10, W23); W36 breaklines already refine | Native (W10) | Days | 1 partly; 2 no; 3 no (W26 at 10 m: -9.7 % and -30.1 %) |
| **Cut cells** | About 1.0 per lattice cell; step 0.70 x median, 0.34 x worst; 568 bytes per cell in line tiles (W3 option c) [Certain, prototype] | W3: passes 7 of 8 phases, worst +3.80 %, no gain over the dry-face fix, fails at every junction; folding small bodies broke a phase (+10.6 %) | In-house | In-house | Each body keeps its own V(η), well-balanced by construction; slivers down to 0.0075 dx² need merging [Likely] | Weeks to months; no staggered or GPU precedent found | 1 yes; 2 no (needs a weir across the cut); 3 partly |
| **Cell clones** (Casulli 2019) | Unknown; a sparse second layer per tile, branch-heavy split and merge [Guessing] | Removes cross-flow at sub-cell barriers, qualitative only; a gorge wall cannot trigger it [Likely] | In-house (published method) | In-house | Born in sub-grid; published only semi-implicit ([Begmohammadi et al. 2021](https://ccht.ccee.ncsu.edu/wp-content/uploads/sites/10/2021/05/Begmohammadi-2021-AWR.pdf)) | Months, research grade | 1 yes; 2 through its weir link; 3 unknown |
| **Porosity** (window rule, cell merging) | 1.0; merging rewrites the cell-to-face map only at flagged cells [Likely] | Bruwier: oblique 4-cell channel 16 % to 1 % with merging, worst 3 % over 0-45° at 1.9 x cost [Certain] | In-house | In-house | Wadi2D's tables already are depth-dependent anisotropic porosity [Likely] | Window = the ridge rule; merging 1-3 weeks | 1 yes (the window); 2 no; 3 no; aims at the residual 45° channel error |

The strip's cost row is the weakest-evidenced line in the table. [Certain] The research found no shallow-water code, open or commercial, that runs square tiles at structured speed beside breakline-aligned strips ([GPU note, section 3](../research_notes/Breakline%20mesh%20options%20for%20Wadi2D/gpu_speed_by_mesh.md)), so every strip figure is arithmetic on other codes. Its per-cell cost is small because strips are small. [Guessing on line lengths] 200 km of lines at 10 m, two rows of 5 m cells, is 40,000 cells, 0.5 % of Block 2's 8.1 M. Its real risk is the time step. [Certain, arithmetic] With the staggered gravity-wave bound, a strip cell of width w inside dx tiles multiplies the whole run's step count by sqrt((dx²/w² + 1)/2): 1.58 at w = dx/2, 2.92 at dx/4. Published GPU local time stepping recovers only 1.03 to 1.28 x on triangles ([Water 2025, 17(18) 2662](https://www.mdpi.com/2073-4441/17/18/2662)). Below about 1 M cells, each added kernel costs 3 to 10 µs of launch per step whatever its size ([NVIDIA, CUDA Graphs](https://developer.nvidia.com/blog/cuda-graphs)). That is why the W10 mesh already loses on Bidah's 90 tiles.

The project's own W3 bench is the strongest evidence on the aligned options, and it is not new (`W3 breakline faces test/README.md`). It ran 1,035 rotated-channel cases. Cut cells (option c) gained nothing over the dry-face fix and failed at every junction, because a two-layer tile cannot hold three bodies. Vertices moved onto the line (option b) failed at bends of 135 degrees and over and at junctions, and oscillated to +29 % on 2:1 banks at a thin wet wedge. That interface failure is the one a strip would have to survive. Conforming triangles passed everything, at a median step of 0.83 x and a worst of 0.37 x, and W3 priced them as "100 % of the kernels and the tile layout". Perot cell vectors (option P) passed every case at 1.04 x cost and keep the tiles. **If the residual channel error of narrow diagonal wadis must fall, P is the cheaper step, before any strip.**

## MeshKernel leads a short list; Triangle and JIGSAW cannot ship

[Certain] The FSF's rule decides the exclusions: "A nonfree license is automatically incompatible with the GNU GPL", and licences that forbid commercial distribution are non-free ([FSF licence list](https://www.gnu.org/licenses/license-list.en.html)). Triangle "may not be sold or included in commercial products without a license" ([Triangle](https://www.cs.cmu.edu/~quake/triangle.html)). JIGSAW may be redistributed only if "no compensation is received through use of the software" ([JIGSAW LICENSE.md](https://github.com/dengwirda/jigsaw/blob/master/LICENSE.md)). [Likely] Wadi2D's business model is support, training, hosted runs and consultancy, which is compensation through use. So even telling users to install JIGSAW themselves is a risk. That is a pity: JIGSAW has the best published evidence for orthogonal primal-dual grids ([Engwirda 2017, GMD](https://gmd.copernicus.org/articles/10/2117/2017/)). Keep it as a method reference only.

| Rank | Mesher | Licence | GPL-3.0: call / ship | Windows and Python | Why here |
|---|---|---|---|---|---|
| 1 | **MeshKernel 8.4.0** (29 Oct 2026) | LGPL-2.1 core, MIT wrapper [Certain] | yes / yes | pip `py3-none-win_amd64`, 1.1 MB [Certain] | Orthogonalisation plus a per-edge metric, motivated by staggered solvers; curvilinear grids grown from splines; rectangular mesh, connect, hanging-edge tools; refines on gridded samples [Certain] ([MeshKernelPy API](https://deltares.github.io/MeshKernelPy/api/meshkernel.meshkernel.html), [GitHub](https://github.com/Deltares/MeshKernel)) |
| 2 | **Gmsh 4.15.2** (24 Mar 2026) | GPLv2-or-later with linking exception [Certain] | yes / yes, Blossom-Concorde terms to check [Likely] | pip wheel 42.2 MB [Certain] | Embedded curves, transfinite plus recombine strips, size fields; conforming only, no orthogonality objective [Certain] ([Gmsh manual](https://gmsh.info/doc/texinfo/gmsh.html), [PyPI](https://pypi.org/project/gmsh/)) |
| 3 | In-house strip builder | Project's GPL-3.0 | n/a | Nothing new | Offset curves and curve normals give near-orthogonal strip cells; the join is cut cells of the lattice [Guessing] |
| 4 | Netgen 6.2.2608 | LGPL-2.1-only [Certain] | yes / yes | Windows wheels cp310-cp314 [Certain] | Respects edges, quad-dominated 2D; no orthogonality control [Likely] ([PyPI](https://pypi.org/project/netgen-mesher/)) |
| 5 | CGAL Mesh_2 | GPL-3+, commercial via GeometryFactory [Certain] | yes / yes | No maintained Windows wheel [Likely] | Exact constrained Delaunay; only with a C++ build ([CGAL licence](https://www.cgal.org/license.html)) |
| 6 | MMG (mmg2d) | LGPL-3 [Certain] | yes / yes | Build needed [Likely] | Metric adaptation keeping required edges; a post-processor, not a strip builder ([GitHub](https://github.com/MmgTools/mmg)) |
| Out | Triangle, `triangle`, MeshPy | Non-free (no commercial use) [Certain] | experiments / no | Wheels exist | Licence; C code frozen since 2005; MeshPy also bundles AGPL TetGen ([MeshPy FAQ](https://documen.tician.de/meshpy/faq.html)) |
| Out | JIGSAW, jigsawpy | Custom, no compensation [Certain] | no / no | cmake build | Licence |
| Out | TetGen | AGPLv3+ dual [Certain] | n/a | | 3D only ([TetGen](https://wias-berlin.de/software/tetgen/)) |
| Out | OceanMesh2D / oceanmesh | GPL-3 [Certain] | yes / MATLAB cannot ship | MATLAB; Python port needs a CGAL build on Windows [Certain] | Coastal triangles; no breakline API in the Python port ([OceanMesh2D](https://github.com/CHLNDDEV/OceanMesh2D), [oceanmesh](https://github.com/CHLNDDEV/oceanmesh)) |
| Out | admesh2D 1.0.6 (Oct 2026) | Apache-2.0 [Certain] | yes / yes | No Windows wheel [Certain] | Constraint extraction "not implemented"; watch it ([PyPI](https://pypi.org/pypi/admesh2D/json)) |
| Out | MeshKit | Licence not found | | Last release candidate 2017 [Likely] | Stale ([announce](https://lists.mcs.anl.gov/pipermail/meshkit-announce/2017/000008.html)) |
| Display | MDAL / QGIS mesh layer | MIT [Certain] | yes / yes | Inside QGIS | The format layer for a hybrid mesh in the plugin, not a mesher ([MDAL](https://github.com/lutraconsulting/MDAL)) |

**Why MeshKernel and not Gmsh.** For this solver, "most advanced" has to mean orthogonality, because the staggered two-point gradient needs the centre-to-centre line normal to the face ([Zijlema, unSWASH](https://swash.sourceforge.io/online_doc/unswash.pdf)). Only MeshKernel treats it as an objective: "Finite volume staggered flow solvers require the mesh to be as much orthogonal as possible" ([GitHub MeshKernel](https://github.com/Deltares/MeshKernel)). It also has every link of the lattice-plus-strip chain as an API call. Gmsh is the more general and more active generator, but its transfinite strips do not make the transverse lines normal to a curved breakline, and its band cells would need Wadi2D's own orthogonality check. [Likely] MeshKernel's own open questions decide whether it survives a first trial:

- whether orthogonalisation keeps internal breakline nodes on the line;
- what cell shapes `mesh2d_connect_meshes` makes at the join.

A one-day trial answers both, on one Faydh 01 gorge bank pair stitched into a 20 m rectangular mesh, reporting the orthogonality histogram and the distance of the strip faces from the line.

**The named precedents are not callable meshers.**

- HEC-RAS enforces a breakline by deleting cell centres in a buffer and regenerating cells along it, with near spacing and repeats. The manual warns that collinear faces from close parallel breaklines run but "will not be correct" ([HEC-RAS 2D manual](https://www.hec.usace.army.mil/confluence/rasdocs/r2dum/latest/development-of-a-2d-or-combined-1d-2d-model/development-of-the-2d-computational-mesh)). That is a warning for Wadi2D's W26 bank pairs, two to three cells apart.
- TUFLOW HPC's quadtree selects faces by a spider-web test, like the cross-hair test on uniform cells. A single-level quadtree is "on average 20%" slower than HPC, and it pays only from three levels of cell size ([TUFLOW quadtree FAQ](https://wiki.tuflow.com/Quadtree_and_Sub-Grid_Sampling_FAQ)). Wadi2D's W10 already matches that shape.

Newer work changes nothing:

- HEC-RAS 2025 announces an SMS-like mesher with quad or triangle regions, and an explicit solver [Likely, poster summary] ([CWEMF 2024](https://cwemf.org/wp/wp-content/uploads/2024/11/18.6-RAS-2025-Mesh-Gneration-Explicit-Solver.pdf)).
- Bitsch et al. publish an explicit sub-grid scheme on triangles, but collocated ([arXiv 2601.01895](https://arxiv.org/abs/2601.01895)).
- None of the 2023-2026 tools builds tiles plus strips.

## One face law in three tiers, all on the line-normal energy head

The law has one geometry rule and three flux tiers. Each tier is evaluated per face from the upwind cell's state, and the upstream velocity comes from the cell-centre discharge over the cell's mean area, never from the face's own over-carried velocity. That is D-Flow FM's continuity estimate (eq. 6.224, Algorithm 45). Without it the bound becomes an identity and never binds ([D-Flow FM TRM](https://content.oss.deltares.nl/delft3dfm2d3d/D-Flow_FM_Technical_Reference_Manual.pdf)).

| Tier | Applies to | Law | Today | Basis |
|---|---|---|---|---|
| **G**, geometry | Breakline faces | Lift a face pixel only where the line stands above the ground half a cell out on both sides; never lower; the distance is a named setting | The line's ground on every staircase face | W36 ridge diagnostic, within 0.3 % [Certain]; ICM Height crest, D-Flow toe, Bruwier PS-A-2 [Certain] |
| **0**, universal bound | Breakline and natural-crest faces; all faces only after a scope decision | E_f = e_U + (V_U·e_f)²/2g; \|q_f\| ≤ 1.7046 E_f^1.5 per unit width, C = 1 | Breaklines uncapped (2.62-3.81 x); natural crests on the depth cap c A sqrt(A/W) | Cannot bind on uniform flow at any Froude number [Certain, arithmetic] |
| **1**, line law | Crest lines, roads, dam crests, dykes, each face with its stored line normal n | V = u_f e_f + v_f e_f⊥; V_n = V·n, V_t = V·t; E_n = e_U + (V_U·n)²/2g; cap \|V_n\| e ≤ C q_max(E_n) with C = 1; reassemble u_f = V_n(n·e_f) + V_t(t·e_f); share by projection \|n·e_f\| in place of 1/(\|n_x\|+\|n_y\|); no explicit drowned switch | Depth cap on the whole face flux, uniform length factor per segment | D-Flow FM projection (eq. 6.216, 6.247); De Marchi side-weir head; TUFLOW Method B Energy [Certain]; the split itself is the agent's construction [Guessing] |
| **2**, structures | Spillways, roads with a user curve | Tier 1 x C_d, x S(r), r = e_D/E_n; S = 2.598 r sqrt(1−r) above r = 2/3, or (1−r^a)^b with TUFLOW's pairs (broad 8.55/0.556, roadway 21.15/0.627); off above r = 0.98; under-relax at 0.6 only if it oscillates | User C on the depth cap | HEC 0.98 switch, D-Flow relaxation 0.6, TUFLOW pairs [Certain] |
| Banks | Suggested bank lines | Refinement lines (W26) or ridge-only breaklines; no line law | The Suggest message still sends them to Crest lines | W26, W36 [Certain] |
| Reserve | Line faces, only if T2 or T3 fail | D-Flow scheme 6: h_f = max(e_D, 2/3 E_n), drive floored at z_c + 2/3 E_n, Bernoulli advection on that face | Not built | Exact free and drowned laws ([D-Flow FM TRM 6.7.3](https://content.oss.deltares.nl/delft3dfm2d3d/D-Flow_FM_Technical_Reference_Manual.pdf)); Dutch practice avoids it where weirs crowd cells [Likely] ([D-HYDRO spec](https://iplo.nl/publish/pages/141332/specificaties-zesde-generatie-modellen-met-d-hydro-v1-2023.pdf)) |

**Why the normal component and the projection.** [Certain, arithmetic] A straight line of length L at angle θ has x-faces of total length L|sin θ| and y-faces of total length L|cos θ|. Projected on the line normal, they add to exactly L at every angle, so the projection |n·e_f| partitions the crossing flux exactly. Today's factor is uniform along a segment: the walk in `wadi2d/terrain/crest.py` gives every edge of a straight segment about the same share [Likely]. That equals the projection only at 0 and 45 degrees. At 15 degrees it is 0.816 on every face, where the projection gives 0.966 and 0.259, so faces near the normal are throttled whenever only some faces bind. The projection also has a known trap: D-Flow FM applies it to the wet area too, which throttles along-line conveyance, and the manual says plainly that "Oblique weirs are not fully understood at this moment." The tier-1 split avoids that by capping only V_n and passing V_t untouched.

[Certain, arithmetic] Tier 0 alone is not enough on a staircase. Each face passing critical flow over its own width behaves like a labyrinth weir and over-carries by cos θ + sin θ: 1.225 at 15°, 1.366 at 30°, 1.414 at 45°. The line law removes this where a line exists. [Certain, arithmetic] The line-normal head matters for lateral outflow. Tangential momentum crosses a crest unchanged, and using the full energy instead over-allows lateral outflow by 1.07 at a tangential Froude number of 0.3 and by 1.28 at 0.6. With no explicit drowned switch, tier 1 releases continuously as the tailwater rises. Wadi2D measured release near r = 0.85 under the present cap (`W1 research and design note/design_note.md`, section 2).

**A scope decision before tier 0 ships.** [Likely] Tier 0 on every face is a global change. It would move every old job wherever steep natural ground over-carries today, which is most rain-on-grid hill cells. Ship it on breakline and natural-crest faces behind a named setting, with old jobs held to the last digit while it is off. Decide the default only after the I3 gate and a Bidah rain-on-grid rerun. Agreement with HEC-RAS (622.0 against 621.9 m³/s at 10 m) proves nothing here, because RAS over-carries free fall too.

## Gates that must move today's numbers through the dock

**There is no dock baseline for the worst case yet.** The W36 rule and the W26 runs came from frozen engine jobs (`bank_runs.py`). W36's only dock run used the Bidah 03 domain at 20 m, where the dam lines moved -1.2 %. So gate G0 builds the missing dock scenarios on today's `main` and records their own baselines before any law changes.

**Build order.** Each step gets its own branch and W folder, merged behind its gate:

1. Rule G on `feature/breakline-faces` (W36 decision 1).
2. Tier 0 on breakline faces (W36 decision 2).
3. Tier 1 with the projection.
4. Tier 2.

**Guards on every merge:**

- old jobs 750 of 750 identical with every new setting off (`old_jobs_check.py`);
- still water at a crest below 1e-6 m/s;
- CPU twin against GPU;
- the full suite;
- the W36 levee bed.

| Gate | Case and harness | Today | Pass mark | Shown through the real dock |
|---|---|---|---|---|
| G0 baseline | W36 and W26 jobs on `main` and the branch; W36 flume | Steps reproduce W26's 78,914 / 42,220 / 154,391 / 88,589 [Certain] | Same steps and peaks | New dock scenarios: Faydh 01 ground at 20 m and Bidah 03; Suggest breaklines; banks sent as Breaklines and as Crest lines; record the dock's own numbers |
| **I1 staircase** | Four W36 rule cases with rule G | **Faydh 01 20 m -11.1 %**; Bidah 10/20 m -1.3/-2.2 %; Faydh 01 10 m -2.4 % | All four within 3 % of no lines (diagnostic -0.0/+0.0/-0.0/-0.3 %); levee bed still holds 101.01 m (99.00 m without lines) | Faydh 01 20 m and Bidah 03 through the dock, banks as Breaklines, dam line within 3 % of the dock's no-line run |
| **I2 overfall** | W36 flume: breakline faces under G plus tier 0, crest lines under tier 1; 5, 10, 20 m; CPU and GPU | **3.81 / 3.35 / 2.92 / 2.62 x** at 0.3-1.5 m (10 m cells); 2.95 / 2.87 at 5 / 20 m; crest lines 0.997-0.977 | 0.97-1.01 at every head and cell for both kinds | A road on Bidah ground drawn as a Breakline and overtopped into a free fall: within 3 % of 1.7046 E^1.5 per true metre; Bidah dam axis at 94 m as a crest line within 1 % of RAS's 534.0 m³/s (today 536.6) and pool within 0.01 m |
| **I3 bank loss** | W26 jobs, banks as crest lines under tiers 0 and 1; the 1 m-underground diagnostic | **-9.7 / -21.6 (W26 table: -21.7) / -30.1 / -35.5 %**, steps 1.6-3.3 x; underground -7.8 % | Within 3 % of no lines; steps within 1.15 x [the agent's mark]; underground within 1 % | W26's own dock path (Suggest, banks to Crest lines) on Bidah 03 and Faydh 01 |
| T1 free overfall, aligned | W36 flume; H 0.3-1.5 m | As I2 | Tiers 0 and 1: 0.97-1.01; tier 2 at C_d 0.9: 0.87-0.91 | Through I2 |
| T2 drowned crest | Flume tailwater at r = 0.5, 0.67, 0.75, 0.85, 0.90, 0.95 | Release near r = 0.85 measured under the depth cap | q/q_free 1.00, 1.00, 0.974, 0.855, 0.739, 0.552, within ±5 % to r = 0.9; monotone; no oscillation over 1 % of q; no jump over 2 % between steps | Engine harness; the dock only through T7 |
| T3 oblique overfall | Straight crest at 0, 15, 30, 45° across a wide basin; H 0.6 and 1.0 m | W3's prototype read the staircase at 0.93 of critical at 45° (aligned options 0.98-1.02) | Per true metre within ±3 % of T1 at every angle; outflow within 5° of the crest normal; tier 0 alone should read 1.22 / 1.37 / 1.41 | Engine harness |
| T4 along-line flow | W3/W6 channel at 30° and 45°: a crest line on the axis at bed + 0.1 m, and banks one cell off; Fr 0.5, 1.0, 1.5 | Channel error with no line -0.45 to +4.21 % (W6, 45°, 3 cells) | Within 1 % of the same channel with no line. Prediction for today's cap: loss above Fr ≈ 0.55. No loss today would mean the zigzag is wrong and W26's loss lies elsewhere | Engine harness |
| T5 side weir | Aligned channel at Fr 0.3 and 0.6 past a 200 m side crest | Not run | Lateral outflow within ±10 % of De Marchi with the ideal coefficient | Engine harness |
| T6 EA Tests 1 and 3 | 100 x 700 m depression; 0.25 m obstruction on 1:200 | Not run | Test 1 final level 10.25 ± 0.01 m; Test 3 point-2 rise 5-6 cm after about 150 s, within 1 cm of the no-cap run ([TUFLOW EA update 2019](https://tuflow.com/media/5019/2019-uk-ea-2d-benchmarking-results-update-latest-tuflow-solvers.pdf)) | Engine harness |
| T7 field checks | Bidah axis; W26 banks; W36 breaklines | As I1-I3 | As I1-I3 | The I-gate scenarios |
| T8 EA Test 7 | Severn reach, 20 m grid, embankments as 3D lines | Not run | Final levels at each storage's controlling crest within 0.05 m [the agent's mark]; peak floodplain level inside the packages' 13.15-13.45 m spread ([EA 2010](https://assets.publishing.service.gov.uk/media/5a75765c40f0b6360e4744dd/scho0510bsno-e-e.pdf)) | Engine harness; dock optional |
| T9 Iber weir flume set | 194 runs on 9 weirs, oblique included ([García-Alén et al. 2021](https://doi.org/10.3390/w13162152), Zenodo 10.5281/zenodo.5062775) | Not run | Head error inside Iber's internal-condition band, 0.9-5.6 % mean relative error; Iber with the weir as topography read 5.0-22.9 % ([paper](https://mdpi-res.com/d_attachment/water/water-13-02152/article_deploy/water-13-02152.pdf)) | Engine harness |

EA Test 2 is depression filling, not a levee, so it is left out. The levee case is Test 7.

T8 has an unresolved reading. The two notes take different control levels from the 2010 report: 12.13 m at a localised low between two higher points about 70 m apart, and about 12.5 m elsewhere. Read the report before fixing the mark.

T9 has a scale problem. The flume weirs are centimetre-scale against Wadi2D's 0.5 m pixel, so they need either a Froude-scaled geometry or a fine synthetic DEM [Guessing on which the engine tolerates].

**Both T8 and T9 are downloads.** The EA data is already item 5 on his waiting list, and the Zenodo set needs the same yes.

**What proves what.** I1, I2 and I3 are the owner's three issues against today's numbers. T1 with T3 proves the cap does not depend on orientation. T2 proves the free-to-drowned transition. T4 and I3 prove it leaves along-line and drowned flow alone. T6 proves momentum-driven overtopping survives.

## What is unproven, and what would bring the strip back

The evidence is uneven, and the report rests most on its two best-measured pieces. Those are the ridge diagnostic (four runs) and the overfall arithmetic (exact against the flume's 2.62). Everything else is less certain:

- **Rule G** has been run only as a diagnostic. The levee case was checked by hand under it, not as a test. A real dyke on a cross-slope lower than the upslope ground half a cell away would not be lifted [Likely]. That is why the distance is a named setting.
- **Tiers 0 to 2** have never run.
- **The zigzag** is inferred, not observed: no face-flux field along a W26 line has been inspected.
- **The line-normal split** is not documented in any production code.
- **The critical floor on an oblique staircase** is untested anywhere read. D-Flow FM calls oblique weirs not understood, and Dutch practice drops its numerical weir where several weirs touch one cell, which is the staircase's normal state [Likely].
- **Smaller unknowns:** the effective width for tier 0 on a notched sub-grid face (W or A/e_U); whether the cell-centre discharge already carries enough of the face to bias the upstream head; whether the transverse velocity at a staircase face is a fair estimate of V_t; the GPU cost of one float2 and a decomposition in both kernels.
- **No terrain match.** No source tests any of these methods on steep wadi ground. The porosity, cut-cell and clone evidence is urban, coastal, riverine or flume.

**What would change the recommendation:**

- **I3 or T4 fails under tier 1.** Then the bank loss is not the law, and the step or the face area is the next suspect, as W26 itself said. Only then does the strip's along-line benefit earn its cost.
- **A diagonal ridge inside one cell leaks.** If it touches no face, rule G cannot see it, as in TUFLOW and HEC-RAS. That calls for clones or a zero-width cut face, not a strip. The cut face is reported to need about five times fewer steps than refining at the barrier ([Ryoo and Mandli, arXiv 2112.09696](https://arxiv.org/abs/2112.09696)).
- **Narrow diagonal engineered channels need better than W6's worst case.** That worst case is +4.21 % on vertical walls and +5.88 % on 2:1 banks at three cells. The next step is Perot advection, which passed every W3 case at 1.04 x, and the strip only after that.
- **The product must carry exact crests and channels through bends and junctions.** Then the honest alternative is W3's triangles as a full unstructured engine on MeshKernel, a separate decision and not a step towards strips.
- **MeshKernel fails its one-day trial** on internal breakline fixity or junction cell shapes. Then Gmsh with Wadi2D's own orthogonality check takes first place.

**If the strip is built later, its design is already constrained.** [Likely]

- Leave the tile kernel untouched and mask the cells under the strip.
- Let the strip own its cells, its transition polygons (slivers merged) and an interface face list.
- Gather interface fluxes in a fixed order per cell, never with atomics, to keep the bitwise repeatability that W31 and W33 rely on.
- Store strip cells as structure-of-arrays in along-line order.
- Run one cell kernel and one face kernel for all strips, in their own power-of-two LTS class one level below the tiles, with cells no thinner than dx/2.
- Capture the whole step in one CUDA Graph for small domains.
- Make the long sides walls with weir links where the channel is defined, the 1D-2D pattern. Elsewhere, open them with a deferred non-orthogonal correction, which is zero at rest but costs exact energy conservation ([Weller 2014](https://gmd.copernicus.org/articles/7/779/2014/gmd-7-779-2014.pdf)).
- Show it in QGIS through MDAL's UGRID, and resample it to rasters for the pixel outputs.
- Apply the face law above unchanged, since on an aligned face n = e_f and tier 1 becomes the ordinary weir face.

## Conclusion

The research turned a mesher question into a face-law question. A mesh decides where faces are, but none of the three failures is about where faces are as much as about what a face does once it is there. A line face either carries the wrong ground, has no critical section, or carries a cap that cannot tell crossing from running along. The production field confirms this: every staggered code that handles crests well puts the control in the face (D-Flow FM's critical floor, TUFLOW HPC's energy-head weir), and the lattice family lives with the staircase. What that family has not published is a crest law that caps the line-normal flux on energy and leaves the tangential flux alone. If T3 and T4 pass, Wadi2D has a lattice crest that is independent of orientation, which removes the main argument for alignment in this family of models. If they fail, the failing test shows which half is wrong, the head or the split, before anyone commits months to a second kernel path.

The cheapest correct product decision follows from W36's uncomfortable finding, not from any mesh. A bank on a slope is neither a ridge nor a weir, so the plugin should stop offering bank lines as barriers at all and route them to refinement. Crest lines and breaklines are kept for roads, dams, dykes and levees, where rule G lifts the face and tier 1 holds the overfall to critical. That leaves the mesher a separable, later decision, ranked and licence-cleared now, with MeshKernel first, and taken only when a measured case shows the lattice cannot reach the 3 % rule.
