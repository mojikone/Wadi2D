# Open-source 2D mesh generators for a square-tile lattice plus breakline-aligned strips (Wadi2D)

Survey date 2026-11-07. Tags: [Certain] = read in a primary source this session (licence file, official site, PyPI/conda metadata, official docs); [Likely] = strong inference, a secondary source, or a search-result summary of a primary source; [Guessing] = gap-filling. Context assumed from the project: GPL-3.0-or-later, Windows, Python engine with CUDA (NVRTC/CuPy) and Numba twin, QGIS plugin; staggered scheme (level per cell, momentum per face, implicit friction); sub-grid tables per cell and per face from a 0.5 m DEM; 32 x 32 square tiles, optional 2:1 block quadtree; breaklines today rasterised as a face staircase up to half a cell off the line (-11.1 % of a dam peak on Faydh 01 at 20 m).

The uncomfortable point first, so the reader does not lose it in the table: **no surveyed tool builds "square tiles plus an aligned strip joined to them" as a product feature.** Every candidate either (a) meshes the whole domain unstructured, or (b) gives the pieces (strip, rectangular block, a way to stitch, an orthogonality optimiser) that Wadi2D would have to assemble. The mesher is the small part of the job; the transition cells between strip and lattice, and a second (unstructured-face) kernel path in the solver, are the large part. [Likely, from the findings below.]

## 1. Licence and GPL-3.0-or-later fit: (a) calling as a library from Python, (b) shipping binaries in a Windows installer

### Takeaway
Gmsh (GPLv2+), MeshKernel (LGPL-2.1, Python wrapper MIT), Netgen (LGPL-2.1), MMG (LGPL-3), CGAL Mesh_2 (GPL-3+), OceanMesh2D/oceanmesh (GPL-3), qmesh (GPL-3), Shingle (LGPL-3), admesh2D (Apache-2.0) and OCSMesh (CC0) are all usable and shippable under GPL-3.0-or-later. **Triangle (and everything that bundles it: `triangle`, MeshPy) and JIGSAW/jigsawpy carry non-commercial or no-compensation clauses, which the FSF treats as non-free and therefore GPL-incompatible; they cannot go into the installer.** TetGen is AGPLv3+ and 3D only, so it is irrelevant anyway. Blue Kenue is closed freeware and cannot be redistributed.

### Cited Findings
- [Certain] FSF rule: "A nonfree license is automatically incompatible with the GNU GPL"; licences forbidding commercial distribution are listed as non-free. LGPLv2.1 "is compatible with GPLv2 and GPLv3"; LGPLv3 compatible with GPLv3; Apache 2.0 compatible with GPLv3 (not GPLv2); Expat/MIT compatible; AGPLv3 "technically not compatible with GPLv3 in a strict sense", but separate modules under the two may be combined in one project — [FSF licence list](https://www.gnu.org/licenses/license-list.en.html)
- [Certain] **Gmsh**: "distributed under the terms of the GNU General Public License (GPL) (version 2 or later, with an exception to allow for easier linking with external libraries)"; closed-source software cannot include Gmsh without a commercial licence from the authors (dual track exists) — [gmsh.info](https://gmsh.info/)
- [Certain] Gmsh PyPI: licence field "GPLv2 or later"; latest 4.15.2, 24 Mar 2026 — [PyPI gmsh](https://pypi.org/project/gmsh/)
- [Likely] Gmsh's quad recombination historically uses the Blossom IV / Concorde code; a Debian packaging note says the "Concorde license is granted only for use within the Gmsh system"; Gmsh 2.8.4 docs list `ENABLE_BLOSSOM` "(needed for full quad meshing) (default: ON)" — [Debian science commits 2012](https://lists.alioth.debian.org/pipermail/debian-science-commits/2012-March/010636.html); [Gmsh 2.8.4 build options](https://manpagez.com/info/gmsh/gmsh-2.8.4/gmsh_87.php)
- [Certain] **pygmsh** 7.1.17, classifier "GPLv3 or later", requires `gmsh` and `meshio` — [PyPI JSON pygmsh](https://pypi.org/pypi/pygmsh/json)
- [Certain] **Triangle**: "may not be sold or included in commercial products without a license"; version 1.6, 28 Jul 2005 — [Triangle home](https://www.cs.cmu.edu/~quake/triangle.html)
- [Certain] Triangle terms as bundled in MeshPy: "Private, research, and institutional use is free." / "Distribution of this code as part of a commercial system is permissible ONLY BY DIRECT ARRANGEMENT WITH THE AUTHOR." MeshPy (the wrapper) is MIT/X; TetGen "is distributed under a dual licensing scheme", AGPL v3 or later, commercial licences from WIAS — [MeshPy licensing FAQ](https://documen.tician.de/meshpy/faq.html)
- [Certain] The `triangle` Python wrapper declares LGPL-3.0 on PyPI and says nothing about the bundled C code's licence (the C code still carries Shewchuk's terms above) — [PyPI triangle](https://pypi.org/project/triangle/)
- [Certain] **CGAL** 6.2.1: "2D Conforming Triangulations and Meshes" (Mesh_2) and 2D Triangulations are GPL; CGAL ≥ 4.0 uses GPL v3+ and LGPL v3+; "you can buy a commercial license for CGAL or parts of CGAL from GeometryFactory" — [CGAL licence](https://www.cgal.org/license.html); [CGAL package overview](https://doc.cgal.org/latest/Manual/packages.html)
- [Certain] **MeshKernel** (C++): "LGPL-2.1 license" — [GitHub Deltares/MeshKernel](https://github.com/Deltares/MeshKernel). **MeshKernelPy**: "uses the MIT license"; "the PyPI wheels bundle MeshKernel, which is LGPL-licensed" — [MeshKernelPy docs](https://deltares.github.io/MeshKernelPy/); [PyPI meshkernel](https://pypi.org/project/meshkernel/)
- [Certain] **JIGSAW**: may be redistributed only if "no compensation is received through use of the software"; modifications must remain under the original author's copyright; "Distribution of this code as part of a commercial system is permissible ONLY BY DIRECT ARRANGEMENT WITH THE AUTHOR" — [JIGSAW LICENSE.md](https://github.com/dengwirda/jigsaw/blob/master/LICENSE.md); same terms in [jigsaw-python](https://github.com/dengwirda/jigsaw-python); conda-forge lists jigsawpy licence as "Custom" — [conda-forge jigsawpy](https://anaconda.org/conda-forge/jigsawpy)
- [Certain] **OceanMesh2D**: GPL-3.0 — [GitHub OceanMesh2D](https://github.com/CHLNDDEV/OceanMesh2D). **oceanmesh** (Python): "published under the GPLv3 license", needs CGAL — [GitHub oceanmesh](https://github.com/CHLNDDEV/oceanmesh)
- [Likely] **qmesh**: GPL v3, by Avdis and Hill; built on QGIS and Gmsh "released under the GNU General Public Licence" — [qmesh architecture docs](https://qmesh-synoptic-manual.readthedocs.io/en/latest/architecture.html)
- [Certain] **MMG**: "under the terms of the GNU Lesser General Public License" (GPL-3.0 and LGPL-3.0 files in repo) — [GitHub MmgTools/mmg](https://github.com/MmgTools/mmg)
- [Certain] **Netgen** (`netgen-mesher`): LGPL-2.1-only — [PyPI netgen-mesher](https://pypi.org/project/netgen-mesher/)
- [Certain] **TetGen** page describes only "tetrahedral meshes of any 3D polyhedral domains", version 1.5.0 of 4 Nov 2013 on that page — [TetGen](https://wias-berlin.de/software/tetgen/)
- [Certain] **Shingle**: LGPL-3.0 (GitHub sidebar) — [GitHub Shingle](https://github.com/shingleproject/Shingle)
- [Certain] **admesh2D** (Python port of ADMESH) 1.0.6: Apache-2.0 — [PyPI JSON admesh2D](https://pypi.org/pypi/admesh2D/json); [Likely] its 0.2.0 was yanked and relicensed from PolyForm Noncommercial — [PyPI admesh2D 0.2.0](https://pypi.org/project/admesh2D/0.2.0/)
- [Certain] **OCSMesh** (NOAA): CC0-1.0 — [GitHub OCSMesh](https://github.com/noaa-ocs-modeling/OCSMesh)
- [Certain] **MDAL** (QGIS mesh I/O): MIT — [GitHub MDAL](https://github.com/lutraconsulting/MDAL)
- [Likely] **Blue Kenue**: NRC grants "at no cost ... a non-exclusive, non-transferable licence"; formerly "EnSimTelemac" — [NRC Blue Kenue download form](https://nrc.canada.ca/en/research-development/products-services/software-applications/blue-kenuetm-request-download-form)
- [Likely] **MeshKit**: no licence statement found; SIGMA site footer "All Rights Reserved" — [SIGMA](https://sigma.mcs.anl.gov/)

### Inferences
- [Likely] GPLv2-or-later (Gmsh, pygmsh's GPLv3+) can be taken under GPLv3, so Gmsh can be called from Wadi2D and its wheel/DLL shipped in the installer, with the source-offer obligation for the Gmsh binary. The linking exception is irrelevant for us (it helps closed linkers, not GPL code).
- [Likely] LGPL-2.1 (MeshKernel, Netgen) and LGPL-3 (MMG, Shingle) DLLs can be shipped beside GPL-3 code; the LGPL relinking/replace-the-library duty is met trivially by shipping the unmodified wheel and pointing at its source.
- [Likely] Triangle's clause and JIGSAW's "no compensation" clause make both non-free; Wadi2D's business model (support, training, hosted runs, consultancy, dual licence) is "compensation through use", so even telling users to install JIGSAW themselves is a risk for the consultancy side. Use for private experiments only.
- [Guessing] The Blossom/Concorde code inside the Gmsh wheel is the one licence item that needs a check before shipping Gmsh: if the 4.15 wheels are built with Blossom, its "use within Gmsh only" grant is compatible with shipping Gmsh unmodified, but it would be a non-free component inside a GPL binary. Gmsh's default recombination in recent versions is not Blossom ("Simple" or "Blossom" selectable) — not verified this session.
- [Likely] CGAL's GPL-3+ is fine, but Mesh_2 has no maintained Python wheel for Windows (see section 2), so the GPL fit is moot unless Wadi2D compiles C++.

### Gaps
- Gmsh 4.15 CREDITS/LICENSE text could not be read (GitLab blocked by an anti-bot page); whether the PyPI wheels include Blossom/Concorde, and their current terms, is unconfirmed.
- MeshKit's licence was not found in a primary source.
- Whether MeshKernel is LGPL-2.1-only or -or-later was not read from the LICENSE file (both are GPL-3 compatible per the FSF).

## 2. Windows and Python integration; maintenance and last release

### Takeaway
Only four candidates install from pip on Windows / Python 3.11-3.12 with no compiler: **Gmsh** (py2.py3-none-win_amd64, 42 MB, 4.15.2 of Mar 2026), **MeshKernel** (py3-none-win_amd64, 1.1 MB, 8.4.0 of 29 Oct 2026), **Netgen** (cp310-cp314 win_amd64, 6.2.2608 of 1 Oct 2026) and **Triangle** (cp311-cp313 win_amd64, but licence-excluded). Everything else needs a C++/CGAL build on Windows, MATLAB, or is stale.

### Cited Findings
- [Certain] Gmsh 4.15.2 (24 Mar 2026); 4.15.1 (16 Feb 2026), 4.15.0 (26 Oct 2025), 4.14.1 (2 Sep 2025), 4.14.0 (3 Jul 2025); wheel `gmsh-4.15.2-py2.py3-none-win_amd64.whl` 42.2 MB, not tied to a CPython ABI — [PyPI gmsh](https://pypi.org/project/gmsh/). C++, C, Python, Julia and Fortran APIs — [gmsh.info](https://gmsh.info/)
- [Certain] pygmsh latest 7.1.17 (thin wrapper on gmsh + meshio); recent upload dates not visible in the metadata read — [PyPI JSON pygmsh](https://pypi.org/pypi/pygmsh/json)
- [Certain] meshkernel 8.4.0, 29 Oct 2026, `meshkernel-8.4.0-py3-none-win_amd64.whl` 1.1 MB, Python ≥ 3.8; 27 releases since May 2021; 8.3.0 May 2026, 8.2.2 Jan 2026, 8.2.1 Nov 2025 — [PyPI meshkernel](https://pypi.org/project/meshkernel/). C++20 library with Python and .NET wrappers — [GitHub MeshKernel](https://github.com/Deltares/MeshKernel)
- [Certain] netgen-mesher 6.2.2608, 1 Oct 2026, Windows x86-64 wheels for CPython 3.10-3.14 — [PyPI netgen-mesher](https://pypi.org/project/netgen-mesher/)
- [Certain] triangle 20250106 (7 Jan 2025), win_amd64 wheels for cp311, cp312, cp313 — [PyPI triangle](https://pypi.org/project/triangle/); meshpy 2026.1.1 — [MeshPy](https://documen.tician.de/meshpy/)
- [Certain] Triangle C code itself unchanged since v1.6 (2005) — [Triangle](https://www.cs.cmu.edu/~quake/triangle.html)
- [Certain] jigsaw-python: build with `python3 build.py` then `pip install .`, needs "a c++ compiler and the cmake utility"; tested on 64-bit Linux, Windows, Mac — [jigsaw-python](https://github.com/dengwirda/jigsaw-python). conda-forge jigsawpy 0.3.3, uploaded 22 Apr 2025 (0.3.6.rc2 listed) — [conda-forge jigsawpy](https://anaconda.org/conda-forge/jigsawpy)
- [Certain] oceanmesh: wheels only for Apple Silicon; on Windows build CGAL with `install_cgal.bat`, then `install_oceanmesh.bat`; needs Visual Studio C++, CMake, Git; warns of DLL conflicts — [GitHub oceanmesh](https://github.com/CHLNDDEV/oceanmesh)
- [Certain] OceanMesh2D: "pure MATLAB", "no toolboxes required", newest changelog version 6.0.0 of 28 Feb 2024, later changes unreleased on the Projection branch — [GitHub OceanMesh2D](https://github.com/CHLNDDEV/OceanMesh2D)
- [Certain] CGAL 6.2.1 current — [CGAL packages](https://doc.cgal.org/latest/Manual/packages.html). [Likely] the only pip CGAL wrapper with Windows wheels found, `pycglib`, says it is "not intended for public use yet" — [PyPI pycglib](https://pypi.org/project/pycglib/)
- [Certain] admesh2D 1.0.6 uploaded 12 Oct 2026, "Production/Stable", Python ≥ 3.10, numpy/scipy/numba/shapely; wheels for macOS and manylinux plus sdist, **no Windows wheel** — [PyPI JSON admesh2D](https://pypi.org/pypi/admesh2D/json)
- [Likely] qmesh follows "a closed-development approach"; `qmesh3` is a stopgap release — [PyPI qmesh3](https://pypi.org/project/qmesh3/)
- [Certain] Shingle shows Travis CI (travis-ci.org) and Python 2 badges, Dockerfiles for Ubuntu Trusty-Bionic, 119 commits — [GitHub Shingle](https://github.com/shingleproject/Shingle)
- [Likely] MeshKit 1.5.0 release candidate with SIGMA 1.3, June 2017, the latest found — [meshkit-announce 2017](https://lists.mcs.anl.gov/pipermail/meshkit-announce/2017/000008.html)
- [Certain] MMG repo: 4,607 commits, C/C++/Fortran, CMake; the GitHub page states no Windows or Python packaging — [GitHub mmg](https://github.com/MmgTools/mmg)
- [Certain] MDAL ships inside QGIS; MDAL 1.3.2 paired with QGIS 3.44.4 — [GitHub MDAL](https://github.com/lutraconsulting/MDAL)

### Inferences
- [Likely] For a QGIS-plugin product whose installer already builds a venv, Gmsh and MeshKernel add one pip line each; Gmsh adds 42 MB, MeshKernel 1.1 MB. Neither needs NVRTC, CUDA or MSVC, which matches the project's "no toolkit on the user's PC" decision.
- [Likely] Calling Gmsh from inside the QGIS Python process risks DLL clashes (Gmsh's wheel carries its own OpenCASCADE/FLTK-era dependencies); running the mesher in the engine process, as Wadi2D already does for the solver, avoids that.
- [Guessing] pygmsh adds nothing the official `gmsh` API lacks for this use; use the API directly.

### Gaps
- Whether jigsawpy on conda-forge has win-64 builds was not visible on the page read.
- MMG and Shingle latest release dates were not visible.
- No primary source read for current pygmsh maintenance status.

## 3. Breakline constraints, aligned strips, and joining a strip to a square lattice (hanging nodes or transition elements)

### Takeaway
Exact faces on polylines: Gmsh (embedded curves), Triangle and CGAL (constrained Delaunay), Netgen (boundary/interface edges), JIGSAW (constrained edges), MMG (required edges), OceanMesh2D (user edge constraints, thin weirs). Aligned strips: **Gmsh** (transfinite surfaces plus Recombine; BoundaryLayer field along curves) and **MeshKernel** (orthogonal curvilinear grids grown from splines by advancing front, or transfinite from splines). Joining to a lattice: **Gmsh produces conforming meshes only** (no hanging nodes), so the join must be a conforming transition band whose outer boundary is the lattice's own nodes; **MeshKernel has the whole chain as API calls**: rectangular mesh, curvilinear-from-splines, curvilinear-to-mesh2d, connect meshes, find/delete hanging edges, then orthogonalise.

### Cited Findings
- [Certain] Gmsh: "internal points and curves can be embedded in surfaces"; `Curve { } In Surface` "Add a meshing constraint to embed the point(s) or curve(s) in the given surface" — [Gmsh reference manual](https://gmsh.info/doc/texinfo/gmsh.html) §1.1, §5.3.3
- [Certain] Gmsh: `Transfinite Surface` uses "a transfinite interpolation algorithm in the parametric plane of the surface to connect the nodes on the boundary using a structured grid"; `Recombine Surface` turns triangles into "mixed triangular/quadrangular meshes"; "To create quadrangles instead of triangles, one can use the `Recombine' command" — [Gmsh manual](https://gmsh.info/doc/texinfo/gmsh.html) t6, §5.3.2-5.3.3
- [Certain] Gmsh boundary-layer meshing constraint: the manual says of it "It only works in 2D however, and is a meshing constraint" — [Gmsh manual](https://gmsh.info/doc/texinfo/gmsh.html) §5.3
- [Certain] Gmsh: "all meshes produced by Gmsh are conforming in the sense of finite element meshes" — [Gmsh manual](https://gmsh.info/doc/texinfo/gmsh.html) §1.6
- [Certain] Gmsh 2D algorithms named in the manual: MeshAdapt, Delaunay, Frontal-Delaunay, Frontal-Delaunay for Quads, BAMG, plus "other experimental algorithms" — [Gmsh manual](https://gmsh.info/doc/texinfo/gmsh.html) §1.2
- [Certain] Triangle produces constrained and conforming Delaunay triangulations and Voronoi diagrams — [Triangle](https://www.cs.cmu.edu/~quake/triangle.html)
- [Certain] MeshKernelPy API: `mesh2d_make_rectangular_mesh`, `mesh2d_make_rectangular_mesh_from_polygon`, `mesh2d_make_rectangular_mesh_on_extension`; `curvilinear_compute_orthogonal_from_splines` ("Generates a curvilinear grid from splines using an advancing front"); `curvilinear_compute_transfinite_from_splines`; `curvilinear_orthogonalize`; `curvilinear_refine`; `curvilinear_convert_to_mesh2d`; `mesh2d_connect_meshes` ("Joins a mesh to an existing one, optionally adding connecting edges"); `mesh2d_get_hanging_edges`, `mesh2d_delete_hanging_edges`; `mesh2d_merge_nodes`; `mesh2d_casulli_refinement`, `mesh2d_casulli_refinement_on_polygon`, `mesh2d_casulli_derefinement`; land boundaries as inputs to `mesh2d_compute_orthogonalization` and `mesh2d_flip_edges` — [MeshKernelPy API](https://deltares.github.io/MeshKernelPy/api/meshkernel.meshkernel.html)
- [Certain] MeshKernelPy spline example: `SplinesToCurvilinearParameters` with `aspect_ratio`, `aspect_ratio_grow_factor`, `average_width`, `min_cosine_crossing_angles`, `curvature_adapted_grid_spacing`, `remove_skinny_triangles` — [MeshKernelPy curvilinear example](https://deltares.github.io/MeshKernelPy/examples/04_curvilineargrid_basics.html). "Curvilinear meshes for rivers can be generated using splines" — [GitHub MeshKernel](https://github.com/Deltares/MeshKernel)
- [Likely] The RGFGRID manual (Delft3D) covers defining splines and generating an orthogonal curvilinear grid from them; "curvilinear grids for Delft3D-FLOW have to be orthogonal" — [RGFGRID manual (copy)](https://www.scribd.com/document/501816558/Rgfgrid-User-Manual)
- [Certain] OceanMesh2D: "'high-fidelity' option for automatically forming and constraining edges", saved user edge constraints, fixed points kept during cleaning; Example 5 inserts "two thin weirs" at an estuary mouth (weir/barrier mapping in changelog) — [GitHub OceanMesh2D](https://github.com/CHLNDDEV/OceanMesh2D)
- [Certain] oceanmesh (Python) README documents no fixed-edge or breakline API; domains come from shoreline signed-distance functions and DistMesh — [GitHub oceanmesh](https://github.com/CHLNDDEV/oceanmesh)
- [Certain] admesh2D: "the 1D–2D constraint extraction is not implemented" (roadmap #186) — [PyPI JSON admesh2D](https://pypi.org/pypi/admesh2D/json)
- [Certain] MMG covers "two-dimensional and three-dimensional surface and volume remeshing", tagged isotropic and anisotropic adaptation — [GitHub mmg](https://github.com/MmgTools/mmg)
- [Likely] JIGSAW examples cover "sharp features in piecewise smooth domains" and "user-defined mesh-spacing constraints" — [jigsaw-python](https://github.com/dengwirda/jigsaw-python)
- [Likely] HEC-RAS (closed, not a candidate, but the precedent for "a strip of cells aligned with a breakline"): enforcing a breakline makes RAS redraw the mesh "respecting the breakline and the specified breakline cell center spacing"; much smaller breakline spacing than the surrounding mesh gives "> 8 sided cells", and practitioners step the spacing down gradually — [Kleinschmidt RAS post](https://kleinschmidtgroup.com/ras-post/2d-mesh-leaking-part-2-2d-area-breaklines); [RAS Solution forum, roads](https://therassolution.kleinschmidtgroup.com/the-ras-solution-forum/topic/breakline-and-cell-spacign-techniques-at-roadslinear-strutures-in-2d/)

### Inferences
- [Likely] Gmsh recipe for one breakline: offset the polyline both sides by the strip half-width, split into quadrilateral patches between transverse cuts, make each patch `Transfinite Surface` + `Recombine` (exact quads, faces on the breakline itself as the strip's centre curve or as one of its long sides); then mesh the band between the strip and the surrounding lattice cells (whose edges are given as fixed boundary nodes at the lattice spacing) with Frontal-Delaunay (triangles) or Frontal-Delaunay for Quads. Because Gmsh is conforming only, there are no hanging nodes: the band's outer polygon is the staircase of lattice cells removed around the strip, so the band shares the lattice edges exactly. The breakline faces are exact; the band cells are mixed triangles/quads of uncontrolled orthogonality.
- [Likely] MeshKernel recipe: `mesh2d_make_rectangular_mesh` (or keep Wadi2D's own lattice and pass it in), `curvilinear_compute_orthogonal_from_splines` along each breakline (the spline is the breakline; rows = strip width), `curvilinear_convert_to_mesh2d`, delete lattice cells under the strip, `mesh2d_connect_meshes` to stitch (it can add connecting edges; hanging edges can be listed and removed), then `mesh2d_compute_orthogonalization` with the breakline as a land boundary. This is the D-Flow FM workflow for rivers inside a rectangular/triangular sea mesh, so the stitching and orthogonality steps are exercised by a production staggered solver [Likely]. Unconfirmed: whether orthogonalisation moves nodes off the breakline (see Gaps).
- [Likely] Triangle and CGAL give exact constrained edges but no strip or quad capability; they would be the "band filler" only, and Triangle is licence-excluded.
- [Likely] MMG is useful only as a post-processor (adapt a strip+band mesh to a metric while keeping required edges); not a strip builder.
- [Likely] A strip on a curved breakline cannot be both exactly aligned and exactly orthogonal unless the transverse lines are normals of the curve; that is precisely what an orthogonal curvilinear (advancing-front, spline-based) generator does and what transfinite interpolation does not guarantee. This favours MeshKernel's orthogonal-from-splines over Gmsh's transfinite patches for the strip itself.
- [Guessing] An in-house strip builder (Shapely offset curves, transverse normals at fixed spacing, quads; band cells by clipping lattice cells against the strip outline, i.e. cut cells) avoids any mesher dependency and keeps the lattice untouched outside the strip; its cost is writing the transition logic Wadi2D needs anyway for its kernels.

### Gaps
- No primary source read on whether Gmsh's BoundaryLayer field can generate quad rows along an internal (embedded) curve on both sides; the manual chunk read only said it is a 2D meshing constraint.
- No source read on whether MeshKernel orthogonalisation keeps embedded breakline nodes fixed (land boundaries snap the mesh boundary; internal breaklines are not documented).
- `mesh2d_connect_meshes` documentation does not say what cell shapes it creates at the junction (triangles, pentagons, or hanging nodes).
- No open tool found that couples an aligned strip to a 2:1 block quadtree; nothing in 2023-2026 found that does "tiles + strip" (see section 6).

## 4. Orthogonality (face perpendicular to the line joining the two cell centres), as a staggered scheme needs

### Takeaway
Only **MeshKernel** treats orthogonality as an explicit objective with a per-edge metric (`mesh2d_get_orthogonality`) and an optimiser (`mesh2d_compute_orthogonalization`, `curvilinear_orthogonalize`), and it states the reason in Wadi2D's own terms: "Finite volume staggered flow solvers require the mesh to be as much orthogonal as possible". **JIGSAW** has the strongest published evidence for orthogonal primal-dual (Delaunay/Voronoi) grids, but is licence-excluded. Gmsh, Netgen, Triangle and CGAL produce Delaunay or quad meshes whose orthogonality is a by-product, not optimised or reported.

### Cited Findings
- [Certain] MeshKernel: "Finite volume staggered flow solvers require the mesh to be as much orthogonal as possible"; the orthogonalisation balances orthogonality and smoothness — [GitHub MeshKernel](https://github.com/Deltares/MeshKernel)
- [Certain] `mesh2d_compute_orthogonalization` "Adjusts the mesh to improve edge-to-circumcenter-segment orthogonality"; `mesh2d_get_orthogonality` "Returns the orthogonality value for each edge"; `mesh2d_get_smoothness` returns the area ratio of neighbouring faces per edge — [MeshKernelPy API](https://deltares.github.io/MeshKernelPy/api/meshkernel.meshkernel.html)
- [Likely] JIGSAW-GEO (Engwirda 2017, GMD 10, 2117) generates "locally orthogonal" staggered unstructured grids: Frontal-Delaunay triangulation, Voronoi dual as the polygonal grid, hill-climbing optimisation, grids that meet C-grid finite-volume constraints including MPAS-O — [GMD 2017 JIGSAW-GEO](https://gmd.copernicus.org/articles/10/2117/2017/)
- [Likely] A NASA summary reports JIGSAW "power" grids with all cells well-centred and centroidal even with complex coastlines and grading, and notes vorticity reconstruction breaks down when staggering is poor — [NASA NTRS 20200001066](https://ntrs.nasa.gov/api/citations/20200001066/downloads/20200001066.pdf)
- [Certain] jigsaw-python provides "routines to assemble (restricted) Delaunay tessellations, Voronoi complexes and Power diagrams" — [jigsaw-python](https://github.com/dengwirda/jigsaw-python)
- [Certain] Triangle outputs Voronoi diagrams; v1.6 adds a no-large-angle guarantee "even for domains that have lots of tiny input angles"; tiny input angles make a no-small-angle guarantee impossible — [Triangle](https://www.cs.cmu.edu/~quake/triangle.html)
- [Certain] OceanMesh2D's quality goal is "worst case triangle quality" by a force-balance algorithm plus topological fixes (not orthogonality) — [GitHub OceanMesh2D](https://github.com/CHLNDDEV/OceanMesh2D)
- [Likely] RGFGRID (Delft3D) states that curvilinear grids for Delft3D-FLOW must be orthogonal and includes an orthogonality check — [RGFGRID manual (copy)](https://www.scribd.com/document/501816558/Rgfgrid-User-Manual)

### Inferences
- [Likely, geometry] A straight strip of rectangles is exactly orthogonal; a strip of trapezoids on a curved line is orthogonal only if the transverse lines are curve normals and the cell centre is taken on them. For triangles, the centre-to-centre line is perpendicular to the shared face only when the centres are circumcentres (the Voronoi dual), and the circumcentre stays inside only for non-obtuse triangles; Triangle's and Gmsh's angle guarantees (minimum angle, no-large-angle in Triangle 1.6) do not imply all-acute triangles.
- [Likely] For Wadi2D the orthogonality question concentrates in the transition band between strip and lattice: lattice cells are orthogonal, strip cells can be made orthogonal, the band is where the error lives. Only MeshKernel can measure and optimise it with a ready call; with Gmsh, Wadi2D would compute its own per-face orthogonality and either accept it or add a non-orthogonal correction in the face momentum equation.
- [Likely] Wadi2D's sub-grid face tables (wet width and conveyance against level) remove part of the need: the face carries its own hydraulic geometry from the DEM, so a mildly non-orthogonal face mainly errs in the pressure-gradient term (level difference over the centre distance projected on the face normal), not in conveyance.

### Gaps
- No published numeric orthogonality reached by MeshKernel (e.g. maximum or 99th-percentile cosine) was found; the D-Flow FM acceptance threshold was not read in a primary source (a cosine of 0.02 circulates for Delft3D practice, unverified).
- No published orthogonality statistics for Gmsh, Netgen or CGAL 2D meshes were found.

## 5. Size control from a raster (DEM slope, distance-to-breakline) and speed/memory at 1-20 million cells

### Takeaway
Raster-driven size: MeshKernel (refine on gridded samples with bilinear interpolation, ridge detection on gridded samples, Casulli refinement on depths), oceanmesh/OceanMesh2D (DEM gradient, wavelength, feature size, distance functions), Gmsh (background size fields; a field reading a structured size grid [Likely]), JIGSAW (user spacing functions). **No primary benchmark at 1-20 M cells was found for any of them.** For Wadi2D's design it matters less than it looks: if only the strips are unstructured, the unstructured cell count is of order 10^5, not 10^7.

### Cited Findings
- [Certain] MeshKernel: `mesh2d_refine_based_on_gridded_samples` ("Refines using gridded samples and bilinear interpolation"), `mesh2d_refine_ridges_based_on_gridded_samples` ("Refines along automatically detected ridges in a sample set"), `mesh2d_refine_based_on_samples`, `mesh2d_refine_based_on_polygon`, `mesh2d_casulli_refinement_based_on_depths` — [MeshKernelPy API](https://deltares.github.io/MeshKernelPy/api/meshkernel.meshkernel.html)
- [Certain] oceanmesh sizing: `distance_sizing_function`, `feature_sizing_function`, `wavelength_sizing_function`, `bathymetric_gradient_sizing_function`, `compute_minimum`, `enforce_mesh_gradation`; meshing "uses the DistMesh algorithm" — [GitHub oceanmesh](https://github.com/CHLNDDEV/oceanmesh)
- [Certain] OceanMesh2D: "bathymetric mesh size functions" and a polyline/thalweg size function along a ship channel (Example 6) — [GitHub OceanMesh2D](https://github.com/CHLNDDEV/OceanMesh2D)
- [Certain] admesh2D sizing from "curvature, medial axis, bathymetry, tide; min-stacked", optional `background="octree"`, Numba solver replacing the C MEX — [PyPI JSON admesh2D](https://pypi.org/pypi/admesh2D/json)
- [Certain] Gmsh manual §1.2.2 lists background mesh size fields; `Field[expression]` syntax in §5.3.1 — [Gmsh manual](https://gmsh.info/doc/texinfo/gmsh.html)
- [Likely] A 2018 comparison found Gmsh's 2D Delaunay mode "not competitive" with Triangle in speed on its tests — [FEATool comparison 2018](https://featool.com/grid/2018/03/06/Matlab-Mesh-Generation-Comparison)
- [Likely] SPEC CPU 2026 includes a Gmsh benchmark (737.gmsh_r), timing 3D meshing, not 2D throughput — [SPEC 737.gmsh_r](https://spec.org/cpu2026/Docs/benchmarks/737.gmsh_r/737.gmsh_r.html)

### Inferences
- [Likely, arithmetic] Strip-only cell count: 300 km of breaklines (banks, roads, dam crests), strips 4 cells wide at 10 m along-line spacing → 300,000 / 10 x 4 = 120,000 strip cells, plus a transition band of similar order. Any of the surveyed meshers handles 10^5 cells in seconds [Likely], so speed at 1-20 M only matters if the whole domain goes unstructured, which design decision 4 already rejected (unstructured 2-4 x slower per cell on the GPU).
- [Likely] Gmsh's distance and threshold fields (distance to the embedded breaklines, size ramp from near to far) are the standard way to grade the band from strip spacing to lattice spacing; a size field read from a raster lets the DEM slope set it. Field names other than the generic background-field mechanism were not read this session.
- [Guessing] Triangle is generally the fastest 2D Delaunay mesher (millions of triangles in seconds) and Gmsh Frontal-Delaunay one to two orders slower per element; irrelevant at 10^5 cells.

### Gaps
- No primary source for Gmsh, MeshKernel, Netgen, JIGSAW or CGAL 2D throughput or memory at 1-20 M cells.
- The Gmsh "Structured" size field (reading a gridded size file) and the "Distance"/"Threshold" field descriptions sit in a part of the manual not read (the HTML is 766 k characters).

## 6. Use in flood and ocean modelling; newcomers 2023-2026; quad-dominant, curvilinear and quadtree generators

### Takeaway
Ocean and coastal models dominate the open meshers: JIGSAW (MPAS-O, E3SM), OceanMesh2D and ADMESH (ADCIRC-type coastal models), qmesh (Gmsh for TELEMAC, Fluidity, Thetis), OCSMesh (NOAA, wraps Triangle, Gmsh, JIGSAW), Blue Kenue (TELEMAC). MeshKernel is the only open mesher built for a **staggered orthogonal flood/river solver** (D-Flow FM). Newcomers 2023-2026: admesh2D (Apache-2.0, 2026), MeshKernel 8.x, Gmsh 4.14-4.15, OceanMesh2D 6.0, OCSMesh 2.0; none targets tiles plus aligned strips. Quadtree flood models (BG_Flood, GeoFlood/ForestClaw, TUFLOW HPC) build their own grids rather than calling a mesher.

### Cited Findings
- [Likely] JIGSAW is the mesh generator for multi-resolution MPAS-O/SI configurations in E3SM — [E3SM E4.4](https://e3sm.atlassian.net/wiki/spaces/ECM/pages/844333124/E4.4+Multi-resolution+Unstructured+Mesh+Generation+for+MPAS); [GMD 2017](https://gmd.copernicus.org/articles/10/2117/2017/)
- [Certain] OceanMesh2D 1.0 paper: Roberts, Pringle & Westerink 2019, "two-dimensional unstructured mesh generation in coastal ocean modeling", GMD — [doi 10.5194/gmd-12-1847-2019](https://doi.org/10.5194/gmd-12-1847-2019)
- [Likely] ADMESH: Conroy, Kubatko & West 2012, Ocean Dynamics 62, 1503-1517, "an advanced, automatic unstructured mesh generator for shallow water models"; original MATLAB no longer maintained, admesh2D is "a faithful Python port" — [doi 10.1007/s10236-012-0574-0](https://doi.org/10.1007/s10236-012-0574-0); [PyPI admesh2D](https://pypi.org/project/admesh2D/)
- [Certain] admesh2D roadmap names integration with "QuADMESH and CHILmesh", single-mesh parallelisation and 3D ADMESH — [PyPI JSON admesh2D](https://pypi.org/pypi/admesh2D/json)
- [Likely] qmesh meshes are used in TELEMAC, Fluidity and Thetis — [qmesh docs](https://qmesh-synoptic-manual.readthedocs.io/en/latest/architecture.html)
- [Likely] Shingle 2.0 (Candy & Pietrzak 2018, GMD 11, 213): self-consistent automated domain discretisation for multi-scale geophysical models — [GMD 2018 Shingle](https://gmd.copernicus.org/articles/11/213/2018/)
- [Likely] OCSMesh turns DEMs into georeferenced unstructured meshes with jigsaw-python; v2.0.0 adds Triangle and Gmsh engines — [PyPI ocsmesh 2.0.0](https://pypi.org/project/ocsmesh/2.0.0/); [GitHub OCSMesh](https://github.com/noaa-ocs-modeling/OCSMesh)
- [Likely] Blue Kenue is "Free for use with models such as open TELEMAC" — [NRC presentation](https://www.sambuz.com/doc/blue-kenue-enhancements-from-2014-to-2019-ppt-presentation-772767)
- [Certain] MeshKernel mesh orthogonalisation is motivated by staggered finite-volume flow solvers; curvilinear grids for rivers from splines; 1D-2D contacts (`contacts_compute_*`) — [GitHub MeshKernel](https://github.com/Deltares/MeshKernel); [MeshKernelPy API](https://deltares.github.io/MeshKernelPy/api/meshkernel.meshkernel.html)
- [Likely] QGIS Gmsh front ends exist as plugins (`gmsh`, `qgis-gmsh`) and QGmesh — [QGIS plugin gmsh](https://plugins.qgis.org/plugins/gmsh/); [QGIS plugin qgis-gmsh](https://plugins.qgis.org/plugins/qgis-gmsh); [QGmesh](https://github.com/calypso-science/QGmesh)
- [Certain] MDAL reads/writes 2DM and UGRID mesh frames, reads HEC-RAS and XMDF results; "Mesh creation" credited to QGIS 3.16 / MDAL 0.7.1 — [GitHub MDAL](https://github.com/lutraconsulting/MDAL)
- [Likely] BG_Flood: GPU shallow-water model on a block-uniform quadtree; GeoFlood: shallow water on quadtree grids managed by ForestClaw, tested on Malpasset — [BG_Flood listing](https://awesome.ecosyste.ms/projects/github.com%2FCyprienBosserelle%2FBG_Flood); [GeoFlood arXiv 2403.15435](https://arxiv.org/html/2403.15435v4)
- [Likely] MeshKit's newest release found is 1.5.0 RC (2017), with a parallel advancing-front surface mesher — [meshkit-announce](https://lists.mcs.anl.gov/pipermail/meshkit-announce/2017/000008.html)

### Inferences
- [Likely] D-Flow FM is the closest published analogue to what Wadi2D wants (staggered, level per cell, normal velocity per face, mixed cell shapes, curvilinear river strips stitched into a coarser mesh); MeshKernel is the Deltares library behind its grid editing [Likely; the link to D-Flow FM was not confirmed in a primary source read this session]. That is the strongest "used in flood modelling" argument any candidate has for this design.
- [Likely] Gmsh's flood/ocean track record is indirect (through qmesh, OCSMesh, TELEMAC/Thetis users), always for finite-element or cell-centred triangle meshes, not for staggered orthogonal ones.
- [Likely] Quad-dominant and quasi-structured quad generators (Gmsh Frontal-Delaunay for Quads, Recombine, and a quasi-structured quad algorithm in Gmsh 4.9+ [Likely, not read]; Netgen quad-dominated 2D [Likely, not read]) optimise element shape for finite elements, not face orthogonality; they would give the band a quad look without the property the scheme needs.
- [Likely] Quadtree generators as libraries (p4est, t8code, ForestClaw) add nothing for Wadi2D, which already has its own 2:1 block quadtree; the gap is the strip and its join, not the tree.
- [Likely] TetGen is 3D only and irrelevant; MeshKit and Shingle are stale; Blue Kenue is closed and Windows-GUI only; OceanMesh2D requires MATLAB, which a QGIS plugin cannot ship; oceanmesh and OCSMesh are coastal triangle tools with no breakline API.

### Gaps
- No primary source confirmed that D-Flow FM or the Delft3D FM Suite uses MeshKernel internally.
- No 2023-2026 paper or repository was found that couples a Cartesian/quadtree flood grid with breakline-aligned strips; CHILmesh and QuADMESH were named only on the admesh2D roadmap and not examined.
- HEC-RAS breakline behaviour was read only in practitioner posts, not the official manual.

## 7. Ranked shortlist for Wadi2D and comparison table

### Takeaway
1 MeshKernel (meshkernelpy), 2 Gmsh (official Python API), 3 an in-house strip builder on Shapely, 4 Netgen; everything else is excluded by licence (Triangle, MeshPy, JIGSAW), by platform (OceanMesh2D, oceanmesh, admesh2D on Windows, CGAL), by scope (TetGen, MMG, MDAL/QGIS, Blue Kenue) or by staleness (MeshKit, Shingle, qmesh, pygmsh). The owner's leading idea names Gmsh; I would test MeshKernel first, because orthogonality is the property the staggered scheme needs and only MeshKernel measures and optimises it, and it already has the strip-from-spline and stitch-to-rectangular-mesh calls.

### Cited Findings
- [Certain] MeshKernel: LGPL-2.1 core, MIT wrapper, Windows wheel 1.1 MB, 8.4.0 on 29 Oct 2026; rectangular mesh, orthogonal curvilinear from splines, convert, connect, hanging-edge tools, orthogonalisation and per-edge orthogonality — [PyPI meshkernel](https://pypi.org/project/meshkernel/); [MeshKernelPy API](https://deltares.github.io/MeshKernelPy/api/meshkernel.meshkernel.html)
- [Certain] Gmsh: GPLv2+, Windows wheel 42.2 MB, 4.15.2 on 24 Mar 2026; embedded curves, transfinite, recombine, boundary-layer constraint in 2D, conforming meshes only — [PyPI gmsh](https://pypi.org/project/gmsh/); [Gmsh manual](https://gmsh.info/doc/texinfo/gmsh.html)
- [Certain] Netgen: LGPL-2.1-only, Windows wheels cp310-cp314, 6.2.2608 on 1 Oct 2026 — [PyPI netgen-mesher](https://pypi.org/project/netgen-mesher/)
- [Certain] Triangle and JIGSAW carry commercial/compensation restrictions; non-free licences are GPL-incompatible — [Triangle](https://www.cs.cmu.edu/~quake/triangle.html); [JIGSAW LICENSE](https://github.com/dengwirda/jigsaw/blob/master/LICENSE.md); [FSF](https://www.gnu.org/licenses/license-list.en.html)

### Inferences

**Ranked shortlist** (reasons; tags as above)

1. **MeshKernel / meshkernelpy** [Likely best fit]. Licence clean (LGPL core, MIT wrapper); one 1.1 MB Windows wheel; released monthly to quarterly through Oct 2026; built for a staggered orthogonal solver; has every piece of the "lattice + strip + stitch + orthogonalise + measure" chain as API calls; refines on gridded samples, so DEM-driven size is native. Risks: whether orthogonalisation keeps internal breakline nodes on the line; what `mesh2d_connect_meshes` makes at the junction; mixed-shape cells (pentagons etc.) Wadi2D's kernels would have to accept. First test: one Faydh 01 gorge bank pair, strip from `curvilinear_compute_orthogonal_from_splines`, stitched into a 20 m rectangular mesh, report the per-face orthogonality histogram and the distance of strip faces from the breakline.
2. **Gmsh (official `gmsh` Python API, not pygmsh)** [Likely]. Licence fine (GPLv2+); one wheel; very active; exact embedded curves; structured quad strips by transfinite + recombine; size grading by fields; conforming transition band whose outer boundary is the lattice's own nodes, so no hanging nodes. Weak where it matters most: no orthogonality objective or metric, so the band cells would be measured and corrected by Wadi2D itself; strips on curves come from transfinite interpolation, which does not make transverse lines curve normals; 42 MB; the Blossom licence question. Best role: building the transition band if MeshKernel's stitching proves unsuitable, and as the general-purpose fallback.
3. **In-house strip builder on Shapely** [Guessing]. No new dependency; offset curves and curve normals give exactly aligned, near-orthogonal strip cells; the join is cut cells of the lattice against the strip outline, which keeps every lattice cell square and every tile intact. Costs code Wadi2D must write anyway (the transition faces and their sub-grid tables). Worth costing beside 1 and 2.
4. **Netgen (`netgen-mesher`)** [Likely]. Licence fine, Windows wheels, active; 2D meshing with respected edges and quad-dominated output [Likely, not read]; no orthogonality control; a substitute for Gmsh if Gmsh's size or licence detail becomes a problem.
5. **CGAL Mesh_2** [Likely]. Exact constrained Delaunay, GPL-3+ fine, but no maintained Windows Python wheel exposing Mesh_2; only if Wadi2D accepts a C++ build.
6. **MMG (mmg2d)** [Likely]. LGPL-3; metric-based adaptation keeping required edges; a post-processor, not a strip builder; no official Python wheel.

Excluded, with the deciding reason: Triangle, `triangle`, MeshPy (non-free Triangle clause; MeshPy also bundles AGPL TetGen); JIGSAW/jigsawpy (no-compensation clause; strongest orthogonality evidence, keep as a reference for method only); TetGen (3D only, AGPLv3+); OceanMesh2D (MATLAB; GPL-3; its thin-weir constraint is a useful precedent); oceanmesh (Windows needs a CGAL build; no breakline API); admesh2D (no Windows wheel; constraints not implemented; watch it); OCSMesh (coastal wrapper of other engines); qmesh (closed development, stopgap release); Shingle (stale, Python 2 era); MeshKit (last release 2017, licence unclear); Blue Kenue (closed, non-transferable); QGIS mesh tools and MDAL (I/O, display and TIN creation, not a strip mesher; MDAL is the right format layer for showing the hybrid mesh in QGIS via UGRID); pygmsh (adds nothing over the official API).

**Comparison table** (tags apply to each cell's main claim; "lib" = call from Python under GPL-3.0-or-later; "ship" = include binaries in the Windows installer)

| Candidate | Licence; GPL-3+ fit (lib / ship) | Windows / Python 3.11-3.12 | Breakline as exact faces | Aligned strip | Orthogonality | Square lattice / quadtree coupling | Maturity (Nov 2026) |
|---|---|---|---|---|---|---|---|
| MeshKernel + meshkernelpy | LGPL-2.1 core, MIT wrapper [Certain]; yes / yes | pip py3-none-win_amd64, 1.1 MB [Certain] | Spline/land boundary; internal fixity unconfirmed [Likely] | Orthogonal curvilinear from splines, transfinite from splines [Certain] | Optimiser + per-edge metric [Certain]; no published numbers | Rectangular mesh, convert, connect, hanging-edge tools [Certain] | Active, 8.4.0 29 Oct 2026 [Certain]; D-Flow FM lineage [Likely] |
| Gmsh (gmsh API) | GPLv2+ with linking exception, commercial track [Certain]; yes / yes, Blossom caveat [Likely] | pip py2.py3-none-win_amd64, 42 MB [Certain] | Embedded curves [Certain] | Transfinite + Recombine; 2D boundary-layer constraint [Certain] | Not an objective [Likely] | Conforming only, no hanging nodes [Certain]; band to lattice nodes [Likely] | Very active, 4.15.2 Mar 2026 [Certain] |
| pygmsh | GPLv3+ [Certain]; yes / yes | pure Python on gmsh [Certain] | via Gmsh | via Gmsh | via Gmsh | via Gmsh | 7.1.17; maintenance doubtful [Guessing] |
| Netgen (netgen-mesher) | LGPL-2.1-only [Certain]; yes / yes | win_amd64 cp310-314 [Certain] | Edges respected [Likely] | Quad-dominated 2D [Likely]; no strip tool | Not an objective [Likely] | Conforming [Likely] | Active, 6.2.2608 Oct 2026 [Certain] |
| Triangle, `triangle`, MeshPy | Triangle non-free (no commercial) [Certain]; experiments only / no | wheels cp311-313 [Certain] | Constrained Delaunay [Certain] | No | Voronoi output; no max-90° guarantee [Likely] | Conforming triangles only | C code frozen 2005 [Certain]; wrappers 2025-2026 |
| TetGen | AGPLv3+ dual [Certain]; n/a | via MeshPy | 3D only [Certain] | n/a | n/a | n/a | 1.5.0 page (2013) [Certain]; irrelevant |
| CGAL Mesh_2 | GPL-3+, commercial via GeometryFactory [Certain]; yes / yes | no maintained wheel exposing Mesh_2 [Likely] | Constrained/conforming Delaunay [Certain] | No | Delaunay only [Likely] | Conforming triangles | CGAL 6.2.1 active [Certain] |
| MMG (mmg2d) | LGPL-3 [Certain]; yes / yes | build needed [Likely] | Required edges [Likely] | No (adaptation) | Not an objective [Likely] | Conforming | Active repo [Certain] |
| JIGSAW / jigsawpy | Custom, no compensation, commercial by arrangement [Certain]; no / no | build with cmake; conda-forge 0.3.3 Apr 2025 [Certain] | Constrained edges [Likely] | No | Best evidence: orthogonal primal-dual, well-centred [Likely] | Triangles/Voronoi only | Active-ish [Likely] |
| OceanMesh2D (MATLAB) | GPL-3 [Certain]; yes / not shippable (MATLAB) | MATLAB, no toolboxes [Certain] | User edge constraints, thin weirs [Certain] | No | Triangle quality, not orthogonality [Certain] | Triangles only | 6.0.0 Feb 2024 [Certain] |
| oceanmesh (Python) | GPL-3 [Certain]; yes / yes | Windows needs CGAL build via .bat [Certain] | Not documented [Certain] | No | DistMesh quality [Likely] | Triangles only | 1.0 stable API [Certain] |
| qmesh | GPL-3 [Likely]; yes / yes | Gmsh + QGIS based [Likely] | via Gmsh | via Gmsh | via Gmsh | via Gmsh | Closed development, stopgap release [Likely] |
| ADMESH / admesh2D | Apache-2.0 (1.0.6) [Certain]; yes / yes | no Windows wheel; sdist + Numba [Certain] | Constraints not implemented [Certain] | No | Not stated | Octree background option [Certain]; triangles | Active, Oct 2026 [Certain] |
| Shingle | LGPL-3.0 [Certain]; yes / yes | Python 2 era tooling [Certain] | Geometry from GIS [Likely] | No | Not stated | No | Stale [Likely] |
| OCSMesh | CC0-1.0 [Certain]; yes / yes | pip, engines separate [Likely] | via engine | No | via engine | No | 2.0.0 [Likely] |
| MeshKit | unconfirmed [Gap] | build needed [Likely] | n/a | n/a | n/a | n/a | last RC 2017 [Likely] |
| QGIS mesh tools / MDAL / Crayfish | MDAL MIT [Certain]; QGIS GPL | inside QGIS [Certain] | TIN creation only [Likely] | No | No | Display and I/O of the result (UGRID, 2DM) [Certain] | Active [Certain] |
| Blue Kenue | NRC freeware, non-transferable [Likely]; no / no | Windows GUI [Likely] | Yes (TELEMAC meshing) [Likely] | Unverified | Not stated | No | Maintained by NRC [Likely] |
| HEC-RAS mesher (precedent, closed) | proprietary; n/a | n/a | Enforced breaklines with cell spacing [Likely] | Aligned cells along breaklines [Likely] | Voronoi-type, orthogonal by construction [Likely] | No lattice | Production |

### Gaps
- None of the ranked candidates has been run on Wadi2D ground; the ranking rests on documented capability, not on measured orthogonality or face-to-line distance on a wadi bank.
- The cost of the solver side (an unstructured-face kernel path on the GPU beside the tile kernels, sub-grid tables for strip and band faces) is outside this survey and is likely the larger cost whichever mesher wins.
