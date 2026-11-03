# Wadi2D - profile and live state (read first; then `README.md`)

**His decisions of 2026-11-02 applied (local `main`; `origin/main` is at `a783afc`, the work order, pushed on his word): the generated basin's lag is his HEC-HMS Kirpich expression by default, 0.6 x L^0.77 / (52 S^0.385) on the 10-85 path, which is exactly the 0.474 x Kirpich that W24 read off the HMS lags (0.6 x 0.75^0.77 x 51.3 / 52), so that constant is gone; the Muskingum-Cunge stays HMS-faithful and gains `hydrology.reach_routing: conserving` (Todini 2007), volume 1.000000 on all eight Block 2 reaches with peaks within 0.14 % of the HMS path, 29 of 29 through the dock (`W29 conserving routing`); a run saves the face discharges with every map (`outputs.face_discharge`, on) and a line drawn after the run reads 1.001 of the upfront record on every line shape, against 0.94 before, at 1.58 x the disk per map (`W30 face frames`); the combinations nobody had run give 4 of 6 (`W32 combinations test`): a generated basin with a gridded storm, with the mesh, on the full extent, and the hand-back at a dam through crest faces all pass, but **the CPU twin and the GPU diverge deterministically on the Block 2 hybrid** (Faydh 01 -2.5 %, a ring -23 %; Bidah matches to six digits) and **a resumed run re-phases its series clock by one interval** (`monitor.py`, `next_series = t + every`), both open. The productivity ideas are his to schedule later, scenarios with compare and a batch run first.**

**Work order done (2026-11-02, pushed the same day): all nine items of his side-chat decisions are in the plugin and tested through the real dock, each on its own branch, merged one at a time behind the full suite: D2 `W17`, D8 `W18`, D1 `W19`, D5 `W20`, D9 `W21`, D7 `W22`, D3 `W23`, D4 `W26`, D6 in three pieces `W24`, `W25`, `W27`. Findings that need his word: HMS's lags are 0.474 x Kirpich, not NRCS, so the generated basin reads 1.05 to 1.59 x HMS under NRCS and 0.88 to 1.26 under the HMS-style lag, a switch in the job; the HMS-faithful Muskingum-Cunge does not conserve volume; bank lines used as crest lines cost a peak 10 to 36 %, so banks are refinement lines; flow read from saved frames is 0.6 to 1.0 of the upfront lines; `S5_ring` and `S11_ring` flicker at 40 m, so a raw peak near a lumped inflow reads high; bed loss at 150 mm/h leaves Fizh at 2.2 x Q100. The productivity ideas are still his to decide.**

**Released 2026-11-02 as a pre-release, on his word: `v0.1.0` at `540bf10`, https://github.com/mojikone/Wadi2D/releases/tag/v0.1.0 (`W16 release package`): `Wadi2D-0.1.0-windows.zip` with a double-click installer. From a fresh environment and throwaway QGIS profiles, 34 of 34 checks, the Block 2 hybrid equal to the record at all five dams, Install from ZIP and the CPU engine through the dock both pass. **Passed on a second PC the same day, his laptop with an RTX 3070 Ti, from the published zip: real download 7 min 25 s, real default profile, a run through the dock, Make map. A PC with no NVIDIA card is still untested; the small fixes it found are in `v0.1.1`, published the same day as a pre-release on his word, https://github.com/mojikone/Wadi2D/releases/tag/v0.1.1, 35 of 35 here, not yet rerun on the laptop.**

**Latest (2026-11-02, `main`): the plugin passes 207 of 207 checks through the real dock on `06a4d40`, small areas, and Make map handles the full extent in 2 min (`W15 final plugin test`); by his rule the ARF study and `initial_levels` are not done, they are not in the dock. The full-extent rerun passes its rule and the peak rise is explained: it is the dry-face fix, +3.42 % at Z4C on the same ground against +3.62 % seen, up to +8 % on a narrow ring (`W12 full extent rerun`). Maps remade with the cell-edge fix; H1 +2.2 %, the rest under 0.4 %. Clean timing: the mesh gains 1.6 x on Block 2 at 10 m, not the 2.9 x first reported, and costs up to 2.7 % at a dam and 5.8 % on one ring (`W10 mesher`). **Round two of validation found real flow records (`W11 validation round two`): Block 2's Z4C and Faydh catchments lie above two ministry gauges, and Cyclone Shaheen has rain and flow together at Lihban, 197.5 km2. With the volume imposed and nothing tuned, Wadi2D reads 0.96 of the Shaheen peak under a phi loss and 0.59 under a constant fraction, first crest within about 5 min; the SCS lag of the project's HMS reads 0.61 and 0.44. But the 100-yr design run gives 2,582 m3/s at the Fizh gauge against a report Q100 of 770, 3.4 x, and HMS 2.2 x upstream: the storm or the losses look too large for this ground, whichever model carries them.** Extent F 0.40 was mostly the comparison: 0.60 inside his model's perimeter. Crest lines: no independent check of crest discharge exists, RAS's 2D overflow runs 4.6 to 6.2 x critical flow. Second catchment, Faydh 01, 74 km2, 10 m: Wadi2D 1,873.8 against RAS 1,872.2 m3/s, 1.001, read as about 5 %; both 1.89 x HMS, so the gap to HMS is method on a second basin too, and that says nothing on which is right.**

**State line (2026-11-01, end of the first build): version 1 engine and QGIS plugin built; `main` is public on GitHub; 1,769 tests pass; the plugin ran a real GPU job in a real QGIS window. Block 2 validated as far as it can be without a gauge: lumped hydrology replicates HMS, mode (b) matches it within 3 %, both dams route within 1.6 % of Modified Puls, one easy HEC-RAS window agrees to 2.6 cm. **HEC-RAS rain-on-grid on Bidah agrees with mode (c): 622.0 against 621.9 m3/s at 10 m, read as within about 4 %, and RAS alone gives 1.72 x HMS. So the gap to HMS is method, not a Wadi2D defect. Still open: whether the SCS lag or the 2D response is right; Block 2 has no gauges (his word), so that needs outside evidence (decision 20).** **Full project boundary run on 2026-11-01 (`W2 full extent run`): 15,398 km2, 17.1 M cells at 30 m, 68 min, Block 2's 200-yr storm, mass error 4e-8; against his 200-yr layer, depth agrees where both are wet (median -0.11 m); extent F 0.40 at 0.3 m counted ground his model never covered, 0.60 inside his perimeter, and the rest to 0.66 is unexplained (`W11 validation round two`, test 4).** The next step is his answers to the list under Next steps. **Worst finding for the dam work: the GGC terrain lies 2.39 m above the NSA datum of the dam levels and EAV.**
**Merged and pushed: embankment, channel and channel with dykes in engine and plugin (decision 23); 54 of 54 through the real dock on Block 2 ground. Overtopping is within 5 % only for a crest up to half a cell wide.**
**Merged and pushed: runs make pixel depth, hazard H1 to H6, smooth polygons and a depth drawing by themselves, on the modified terrain, and the dock has Make map; `W9 pixel outputs/README.md`.**

The user's global CLAUDE.md rules apply (advisor register, confidence tags, W# iterations never overwritten, live documents, one
logical change per commit, **never push without his explicit word**). This file is the live state of the project: update the state
line on every substantive change. It was written at the end of the Block 2 chat of 2026-10-26..29 where the idea was born; that
chat is not available to the next session, so this page is the record of what was said and decided.

## What it is

A **CUDA 2D shallow-water solver with the hydrology inside the same model**, for wadi flood work of the Batinah type: steep hill
catchments, alluvial fans, braided wadis that join and separate, several outfalls to the sea. Full shallow-water equations (not
diffusion wave), sub-grid terrain in every cell and face, faces that know the ground along them (a breakline on high ground is a
wall until overtopped), a mesh generator, catchment delineation, HEC-HMS-style lumped hydrology for the hills with rain-on-grid for
the plain, ARF handled the HMS depth-area way, gridded rainfall input (netCDF, GRIB2, radar), terrain modification for dams and
channels, a Windows UI that shows the flow live while the GPU runs. Two uses: **design flows at design points** (dam sites, channel
heads, culverts) and **full-catchment flood maps**. That is the full scope; **version 1 is the subset fixed in decision 17 and the
Version 1 scope section**, the rest is the roadmap.

Why: today he runs HEC-HMS (hydrology, ARF through depth-area analyses) and exports hydrographs into HEC-RAS 2D (plains, braided
wadis, fans with several outfalls). HEC-RAS is CPU-only and slow, has no ARF (rain falls uniformly), and no hydrology of its own.
HEC-HMS 4.1x has a 2D subbasin, but the mesh must be built in HEC-RAS and it runs only the diffusion wave. He wants one model, fast.

## Owner, repo, machine, rules

- Owner: Mojtaba; a personal project, open source (decision 15) with services sold around it (see Product requirements). Data may go on GitHub
  (files of 100 MB and more stay out, listed). No deadline.
- Repo: `https://github.com/mojikone/Wadi2D.git` (remote `origin` set on 2026-10-29; **public; `main` first pushed on his
  word on 2026-11-01**; pushing needs his explicit word, every time).
- Folder: `D:\Mojtaba\Renardet\Wadi2D` (outside the Batinah block folders). Working folders carry a short description in the name:
  `W<n> <what it holds>` (his instruction of 2026-10-29, now rule 15 of his global CLAUDE.md).
- Stack: his words, "whatever yields the fastest 2D solver possible". My pick, not yet benchmarked or approved: CUDA C++ core as a
  DLL, Python/Qt UI on top (his PyQGIS habits carry over). To be decided in the design note with a micro-benchmark.
  **2026-10-29**: the hardware-adaptive requirement is in tension with CUDA-only; single-source performance-portable layers (Kokkos, as
  SERGHEI uses) and portable GPU APIs join the candidates. See Product requirements. **Decided by the build, 2026-11-01**: CUDA C++ kernels compiled at
  run time by NVRTC through CuPy, so no CUDA toolkit or MSVC is needed; a Numba CPU twin with the same statement order; a Python engine process; pydantic
  configuration. Licence in practice GPL-3.0-or-later.
- Machine: NVIDIA GeForce RTX 5080 16 GB (Blackwell, needs CUDA 12.8+), AMD Ryzen 9 9950X3D 16 cores / 32 threads, 126 GB RAM,
  Windows 11 Pro. [Certain, read on 2026-10-29]
- Test data and reference: Block 2 of the Batinah project, `D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2` (read its `CLAUDE.md`):
  HEC-HMS 4.12 model `Hydrology\HEC_HMS_Block_02` (18 subbasins, 599 km², SCS CN with the project CN grid, SCS lag, Muskingum-Cunge
  reaches, 13 frequency storms with the `ARF FM` table, 13 depth-area analyses), terrain `Hydrology\Terrain\GGC_2_MERGE_HDSM.tif`
  (0.5 m) and the 2 m / 5 m rasters, the W1 inflow peaks at the five dam sites (`Claude Block 02\W1`). His files are read-only.
  Also the user-level skill `batinah-block-channel-design` and the Block 04 repo (`mojikone/Channel-desing-of-Block-04`).

## The market, as surveyed on 2026-10-29 (why build at all)

| Solver | Cost | GPU | Sub-grid | Hydrology inside | Note |
|---|---|---|---|---|---|
| HEC-RAS 6.x | free | no | yes (cell volume and face tables) | no (needs HMS) | implicit; gains little beyond ~8 cores; no ARF |
| HEC-HMS 2D subbasin | free | no | via RAS mesh | yes | diffusion wave only, mesh from RAS |
| TUFLOW HPC | paid (~EUR 6-7k a seat [Guessing]; GPU module = 50% of the engine licence) | CUDA | SGS | no | explicit; ~43x a 32-core CPU on an RTX 4090 (vendor figure); the accepted GCC tool |
| Iber+ | free | CUDA | **no** (mesh = terrain, 2-5 m needed on wadis) | rain-on-grid, CN/Green-Ampt/Horton | Roe scheme, GiD pre/post; V3.2b; 50-series support unconfirmed |
| LISFLOOD-FP 8 | free | yes | no | rain | local-inertial weak at Fr > 1; FV1/DG2 for steep ground; CLI |
| TRITON, HiPIMS, SERGHEI | free, research | multi-GPU | no | partial | no GUI |
| InfoWorks ICM 2D, MIKE 21 FM | expensive | yes | no (ICM: subcatchments draining to 2D zones; the hybrid pattern we want) | ICM yes | only if a licence exists |

Nothing free does sub-grid + GPU + hydrology + ARF. That is the gap.

## Design decisions so far (with reasons; each may be re-opened in the design note)

1. **Solver** (**scheme overturned by decision 19**; the requirements stand): full shallow-water equations, finite volume, explicit, CUDA; second order (MUSCL-type), well-balanced (still water
   stays still on steep ground), robust wet/dry, supercritical flow and jumps; adaptive global time step on CFL; local time stepping
   to be evaluated (the steep fine cells set the step for everyone; the strategy is decision 18).
2. **Sub-grid**: per cell a volume-vs-level table, per face a wet-width / conveyance-vs-level table, built from the 0.5 m DEM. Faces
   snap to breaklines and carry the crest profile, so **high ground blocks the flow until the level passes the crest**. This is the
   feature he asked for first ("edges aware of topography"). **Version 1 (2026-10-29)**: on the uniform grid a crest line is rasterised
   onto the face lattice as a staircase of blocked faces, each closed up to the crest elevation at its crossing, with a per-face length
   factor for the overtopping discharge (the staircase is up to 41% longer than the line at 45 degrees [Certain, geometry]). A DEM-sampled
   face table alone leaks under a thin diagonal dyke, because every crossed face is only partly blocked [Likely]; the explicit object is
   what makes the barrier watertight, as TUFLOW's Z lines do on its uniform grid [Likely]. Snapped faces (version 2) make the line exact.
3. **Store depth, not water level.** [Certain, arithmetic] Float32 at 1,500 m elevation resolves ~0.12 mm; a 2 s step of 100 mm/h
   rain adds 0.056 mm; a level-based float32 solver loses the rain in the hills. Depth storage or mixed precision; FP64 on a GeForce is
   ~64x slower, so avoid it in the main loop.
4. **Mesh generator**: built in-app from the DEM, breaklines and refinement zones; quadtree (TUFLOW-HPC-like) is the first candidate,
   unstructured the alternative; refinement bands along the delineated streams so the mountains keep the wadis at full resolution
   (his requirement for full-catchment flood maps); coarse cells elsewhere in the hills. **Revised 2026-10-29 (decision 17): deferred to
   version 2.** Version 1 builds a **uniform grid in-app** from a domain polygon and a cell size (an integer multiple of the 0.5 m DEM
   pixel, aligned to the DEM raster), cells outside the polygon inactive, and its own sub-grid tables from the 0.5 m DEM; the solver works
   on **tiles of 32 x 32 cells with an active-tile list from day one**, so the tiles become the leaves of the later quadtree (PARFLOOD
   block-uniform quadtree, TUFLOW HPC [Likely]) and the unit of domain splitting (decision 16 b) without a rewrite. Uniform with sub-grid
   was TUFLOW's only grid until about 2020 [Likely]: a production configuration, not a test rig. **HEC-RAS meshes are not imported**: an
   unstructured solver is 2-4x slower per cell [Likely], harder at second order, and would tie every mesh edit to RAS Mapper, the
   dependency HMS 2D has and this project exists to escape; RAS supplies its geometry-HDF cell-volume and face-area tables as the oracle
   for our table builder (a RAS mesh with the same square cells on the same terrain) and its results for the head-to-head; HEC's rashdf
   library reads the file [Likely].
5. **Hydrology inside, hybrid by design.** Subbasins are first-class objects; each is either *lumped* (HMS methods: SCS CN losses,
   SCS lag or Clark unit hydrograph, Muskingum-Cunge reaches) or *2D* (rain-on-grid with CN or Green-Ampt losses, depth-varying
   Manning n). A lumped subbasin polygon **masks the rain on every 2D cell beneath it** (no double rainfall; his point). Its hydrograph
   enters at its delineated outlet, into the wadi cells at the mountain front, not smeared along a boundary line. Same concept as the
   HMS 2D subbasin and ICM subcatchments draining to 2D zones, which is what he intended from the start.
6. **Three modes, compared on Block 2 at the five dam sites against the W1 HMS peaks**: (a) all lumped, which must reproduce HMS within
   a few per cent and validates the hydrology engine; (b) hybrid, lumped hills and 2D plain; (c) full 2D with coarse sub-grid hills and
   refined streams. Expectation [Guessing]: (b) for design flows (reviewers know the methods; fastest, the steep cells leave the 2D
   domain), (c) for full-catchment flood maps. Rain-on-grid and SCS-lag peaks will not coincide; the comparison is to know why before
   anyone else asks. If (c) matches HMS, his stated preference is the single full-2D model. **Version 1 (2026-10-29)**: mode (c) runs on
   the uniform grid, so the hill wadis get the plain's cell size: full catchment at 20 m, 1.5 M cells, minutes; at 10 m, 6 M cells, 30-60 min
   [Guessing]; the fine-wadi full-catchment map waits for the quadtree. Mode (b) loses nothing: plain and fans at 10 m, ~2 M cells, ~10 min
   [Guessing]. **Measured 2026-11-01 (`validation/block2_full.md`)**: (a) within 0.002 %; (b) within 3 % at the five dams with HMS's own reach n 0.1,
   up to +26 % at wadi n 0.04; (c) right volume, peaks 1.39 to 2.08 x HMS and 0.2 to 2.0 h early, with no defensible Manning closing it. (b) saved
   no run time on that domain, because rain on the plain keeps the tiles active. See decision 20 for what this does and does not mean.
7. **Delineation is preprocessing, not run-time load.** Flow direction and accumulation on the 2 m or 5 m raster (599 km² at 5 m =
   24 M cells, seconds), once per terrain, cached on disk. **Catchment area at any point is one lookup in the accumulation grid**;
   catchment polygons only on demand (display). Wall and burn objects shared with terrain modification, as HMS does. **Version 1
   (2026-10-29)**: no delineation code of our own (decision 17); subbasins, outlets and the drainage areas of design points come from the
   HMS basin file or GIS layers; the accumulation grid for the composite map (decision 9), when wanted, comes from a QGIS processing
   algorithm (GRASS r.watershed or SAGA) called by the plugin and cached as above.
8. **Muskingum-Cunge parameters from terrain**: reach length and slope from the stream profile on the (burned) DEM; cross-sections
   sampled perpendicular to the stream every ~100 m and reduced to a representative **8-point section** (HMS supports it) or a fitted
   trapezoid (bottom width, side slope) when he wants the HMS look; Manning n from land use. Valid in confined hill wadis; fans and
   braided reaches are 2D anyway. [Likely] **Version 1 (2026-10-29)**: deferred to version 2; version 1 reads the reach parameters from
   the HMS basin file.
9. **ARF, the HMS depth-area way with one shortcut.** HMS reruns the whole basin once per analysis point with the storm area set to
   that point's drainage area (Block 2: 14 points, 14 runs per return period). Here: **one run per storm-area value**, 6-8 log-spaced
   areas covering 10-600 km² (the 24 h ARF steps between neighbours are ~2%, so interpolation error is well under 1%), rain x ARF from
   his `ARF FM` table applied to lumped and 2D parts alike; **each design point reads the run matching its own drainage area** (a
   lookup from the accumulation grid); optional **composite map** where every cell reads the run matching its own drainage area, a
   flood map consistent with the design flows at every point. Cost is bounded by the number of storm areas, never by the number of
   cells. His reservation: speed is the purpose; his stance: keep ARF if it stays cheap. Fallbacks: a single run at the storm area of
   the point of interest (what HEC-RAS users do by hand), or ARF = 1 (the HEC-RAS default: conservative for hazard maps, uneconomical
   for channel sizing). Alternative flagged, not chosen: a storm-centred spatial storm whose isohyets carry the depth-area relation
   (fixed-area ARF tables, which his are, differ from storm-centred ARF, so the conversion is not exact). **Decision pending in the
   design note**, including how it is presented to MAFWWR reviewers. **Kept in version 1 (decision 17)**: cheap orchestration and the
   differentiator; design-point drainage areas from the HMS basin file or the user, the accumulation grid from QGIS processing (decision 7).
10. **Terrain modification as vector objects**, applied when the sub-grid tables are built, **the DEM file never changes**: dam crest
    line with an elevation profile (a wall face; overtopping automatic), spillway structure at a face (Q = C L H^1.5, C ~ 2.1 for his
    dams), channel template on an alignment (burned), wall, burn line. The reservoir is the DEM behind the crest, so routing comes
    free (no EAV curve, no Modified Puls); a direct cross-check for Block 2 W2 when the dam data (FSL, crest, spillway length) arrives.
    The same objects feed delineation (HMS wall and burn layers). **Version 1 (2026-10-29)**: crest line, spillway, burn line and wall;
    channel templates deferred to version 2.
11. **Rainfall inputs**: uniform hyetograph; the HMS frequency storm (point depths, 24 h specified pattern, storm area, ARF table);
    gridded time series: netCDF (CF conventions), GRIB2 (NOAA, ECMWF), GeoTIFF stacks, HEC-DSS grids, weather-radar products (GCC
    meteorological services run radars now; Oman DGMAN), satellite (GPM IMERG). Observed events become validation cases; candidate:
    Cyclone Shaheen, October 2021, over Al Batinah [Likely data exist; not checked]. **Version 1 (2026-10-29)**: uniform hyetograph, the
    HMS frequency storm and GeoTIFF stacks; netCDF, GRIB2, DSS grids, radar and satellite products deferred to version 2 (only validation
    events need them; each format is about a week [Guessing]).
12. **Validation ladder**: analytic cases (still water on steep ground, Stoker/Ritter dam-break, Thacker oscillation), the UK
    Environment Agency 2D benchmark tests, HMS replication on Block 2, one Block 2 wadi head to head with HEC-RAS on the same terrain
    (depth, extent, run time), an observed event. Acceptance by reviewers is unknown; the benchmarks and the HMS replication are the
    argument. **Version 1 (2026-10-29)**: all of it except the observed event, which waits for data.
13. **Outputs**: max depth, velocity and hazard GeoTIFFs; hydrographs and levels at design points; per-storm-area and composite maps;
    live view of the flow on the GPU during the run. **Version 1 (2026-10-29)**: the live view is a raster layer refreshed in QGIS every
    few hundred steps.
14. **UI (Windows)**: load DEM and rasters, draw breaklines, boundaries, structures and subbasins (or import shapefiles), mesh, set the
    storm, run, watch, export. Reads the HMS project files (`.basin`, `.met`, `.control`, `.pdata`, DSS) so test (a) is apples to apples. **Revised 2026-10-29**: the
    product requirements apply; toolkit and architecture are open questions for the design note. **Revised again 2026-10-29 (decision 17):
    version 1 is a QGIS plugin**; open source re-admits it, canvas, layers, drawing, GDAL and the processing algorithms come free, and
    TUFLOW ships a QGIS plugin [Likely]. The standalone Windows UI is version 2. The HMS file readers stay in version 1.
15. **Open source** (his decision, 2026-10-29). Licence open for the design note: GPL-3.0 (keeps forks open, keeps a dual-licence sale
    path, re-admits a QGIS plugin and PyQt), Apache-2.0 (widest adoption and embedding by others), or AGPL-3.0 (if hosted runs become the
    business). My pick [Likely]: GPL-3.0. "Saleable" now means support, training, hosted runs, consultancy and a dual licence, not the
    code. Every dependency is audited against the chosen licence; a contributor licence agreement if contributors come. Precedent to
    research: SWMM and EPANET (public-domain engines, vendors sell UIs on top), QGIS, OpenFOAM, Delft3D, and the licences of LISFLOOD-FP,
    SERGHEI, TRITON, HiPIMS. Open source also turns reviewer acceptance from a weakness into an argument: anyone can read and rerun the
    method.
16. **Distributed execution in two levels** (his wish, 2026-10-29: "several PCs, or shared hardware in a network"). (a) **Job level, the
    first of the two** (moved out of version 1 the same day, see c): a node service on every PC that has the engine, a job queue, and the UI submitting runs to any node on the LAN.
    The ARF design (decision 9) and the return periods give 50-100 independent runs per study, so this is linear speedup for his actual
    workflow and nearly free once the engine is a service; unequal PCs are scheduled by a benchmark score per node. (b) **Domain level,
    one run split across GPUs or PCs**: the engine is built on tiles with halos and no global state from the first stage so it stays
    possible, but it is not built in the prototype. Expectation [Likely]: over office Ethernet the per-step halo exchange and the global
    time-step reduction cost 0.2-0.5 ms against a few ms of compute per step, so the speedup is sub-linear and pays only for the largest
    domains; two GPUs in one PC pay sooner. Precedent to research: TRITON and SERGHEI multi-GPU via MPI, NCCL, MPI on Windows.
    (c) **His clarification, 2026-10-29**: "several PCs" means an office where colleagues' PCs sit idle after hours and a user wants them
    to expedite runs. Possible at job level, **deferred**: office PCs have no GPU, a CPU build runs tens of times slower than the RTX 5080
    [Likely], so ten idle PCs add a fraction of one card; and a service on every PC brings IT approval, firewall rules and sleep policies
    with it. It pays only in an office with several GPU workstations. The door stays open at no cost: the engine is a separate process
    driven by files and a pipe from day one, and a job runner that starts that process on another PC is a small later step. Not in
    version 1 (decision 17).
17. **Version-1 scope** (his instruction, 2026-10-29: ship the product as fast as possible; before any research, name the bottlenecks and
    what to drop). The keep/defer list is the **Version 1 scope** section below; he agreed to it ("most of it") and confirmed the uniform
    grid. In one line: GPU solver with sub-grid and crest-aware faces on a **uniform grid**, HMS-file hydrology, rain-on-grid, ARF
    multi-run, frequency storm, dam objects, HEC-RAS HDF reader, **QGIS plugin** as the UI, minimal live view, the validation ladder minus
    the observed event. **Deferred to version 2**: mesh generator, standalone UI, in-app delineation and Muskingum-Cunge from terrain,
    gridded rainfall beyond GeoTIFF stacks, channel templates, local time stepping, multi-PC runs and domain decomposition, portability
    beyond NVIDIA plus CPU unless the benchmark says otherwise.
18. **Steep cells and the time step** (his question, 2026-10-29: "the small cells on steep slopes bite the run time; is there an
    intelligent way to manage it?"). [Certain] The explicit step is dt = CFL dx / (|u| + sqrt(g h)), so the cost per unit area grows as
    1/dx^3: halving the cell is eight times the work. The strategy, in the order it pays:
    (a) **Do not make the steep cells small.** With sub-grid tables a confined hill wadi is resolved by its conveyance and storage curves,
    not by the cell size; a 20-40 m cell on a steep reach is correct where the bed drop inside the cell stays below the flow depth (the
    flat free surface per cell is the limit), so the cell-size rule on steep ground is **dx <= h / S** (about 40 m at 5%, 20 m at 10% for
    2 m of flow [Likely]), with refinement spent where the extent matters: fans, the plain, structures. The version-2 mesher takes dx from
    slope and expected depth, not from channel width. Research item: a sloped sub-grid free surface inside steep cells (Volp 2013 and
    successors [Likely]) would lift that cap. Illustration [Guessing: assumed depths and velocities]: a hill wadi channel at 5 m cells, 2 m
    deep at 5 m/s, dt ~0.5 s; the same channel at 40 m with sub-grid, ~3.8 s; the plain at 10 m, 1 m deep at 2 m/s, ~1.8 s; a sheet of
    rain on a hillslope at 5 m, ~3 s. The steep channel is the limiter only when it is meshed fine.
    (b) **Mode (b) removes the hills from the 2D domain** for design flows; nothing to manage.
    (c) **Hygiene, in version 1**: friction treated point-implicitly so it never sets the step; velocity desingularised in thin cells
    (Kurganov-Petrova type) and cells below a depth threshold excluded from the CFL search, so one near-dry cell with a spurious
    velocity cannot throttle the whole domain. [Likely] This is the commonest cause of tiny steps in rain-on-grid runs.
    (d) **Tile-level local time stepping, version 2**: each 32 x 32 tile advances in a power-of-two multiple of the global minimum step,
    halos interpolated in time (PARFLOOD's LTS on the block-uniform quadtree, Dazzi et al. 2018 [Likely]); speed-up 2-3x on real
    catchments [Likely], bounded by the share of cells in the finest class. The tile design of decision 4 makes it a contained addition.
    (e) **Not chosen**: a semi-implicit or implicit scheme (the HEC-RAS answer; a different engine with a sparse solve per step), and a
    second equation set (kinematic or diffusive wave) in the hill cells; both are heavy and the second muddies acceptance.
19. **Staggered scheme, not collocated HLLC** (2026-11-01, decided by prototype and by the source review `research/raw/N01_subgrid_scheme_decision.md`,
    which agreed independently). Level per cell, conservative momentum per face, friction implicit, crest faces limited by critical flow, thin
    sheet flow read by volume over length with a mean-surface drive. Reasons: sub-grid tables sit exactly on these unknowns; still water is exact by
    construction; TUFLOW HPC works this way. Measured: a plain flat-surface sub-grid holds 14 % of the correct storage on a 5 % plane, this one
    100 %; thin crest 0.996 of critical flow; Stoker plateau exact; 2.2 to 2.9 G cell-updates/s with real tables on the RTX 5080. Weakness, corrected 2026-11-01 (`W3 breakline faces test`): a channel with
    vertical walls at 45 degrees runs +7 to +8 % at 3 cells wide and about +3.5 % at 6, averaged over lateral position; the +2 % recorded before was a lucky
    position and +11 % an old kernel. 2:1 banks +1.9 % and +0.9 %. Cause: a dry face's zero velocity is advected as real momentum, not grid alignment. `design_note.md` carries the equations
    and the list of what this overturned, including `dx <= h/S` as a hard rule in decision 18.
21. **Flood outputs live in the engine and the plugin, not in scripts** (his instruction, 2026-11-01: "the plugin is what other people
    will use: a feature that is not in the plugin is not done"; he rejected the last maps as "pixel pixel"). After a run the engine makes depth,
    speed and depth x speed at the DEM pixel over the saved maps, on the GPU with a CPU path from one source, and the classes H1 to H6 by the rule in
    the schema. Two cells share a water surface when both levels stand above their shared face, or the higher does and their depths are alike; this
    replaces the fixed 2 m jump, which switched the slope off on steep channels. Each cell is then filled to its own mean depth, so a thin sheet
    reads its own depth, not a wedge. Rasters are the numbers of record; polygons and the depth drawing only show them. Detail: `W9 pixel outputs/README.md`.
20. **Validation without gauges** (his statement, 2026-11-01: Block 2 has no hydrometric station with matching rainfall and hydrographs for one event, so
    HMS is not the thing to validate the outputs). Consequences. HMS replication stays as a **code check**: it proves our hydrology does what HMS does, not
    that either is right. Mode (c) against HMS is a **disagreement between two uncalibrated models**, not a failure of (c), and not a pass for HMS. Hand check
    [Likely, flow lengths from Hack's law, not measured]: the HMS lags imply a mean velocity of 1.2 to 1.5 m/s over 8 to 18 km, which is slow for a 100-yr
    flood in a steep rock wadi; the 2D response is about 2 to 3 x faster, in line with Manning at flood depth. That is an argument, not evidence. **Corrected by `W11` 2026-11-02: Block 2 has two ministry gauges below it, with annual peaks and no event with rain and flow together; Lihban, on another basin, has both.** Evidence
    that does not need a gauge, in order of cost: HEC-RAS rain-on-grid on the same catchment (**done on Bidah 2026-11-01, rule fixed before the run:**
    622.0 against 621.9 m3/s at 10 m, 1.72 x HMS in RAS alone, so the gap is a method difference and not a Wadi2D defect; `validation/ras_rain_on_grid.md`;
    one catchment, no crests, and two solvers agreeing does not make either right about a real flood); the regional envelope of unit peaks; flood marks with a
    slope-area estimate from a known event (Shaheen 2021); satellite flood extent with satellite rain; a gauged neighbouring wadi, calibrated there and
    transferred. Until then design flows stay on mode (b), the method reviewers know, and mode (c) is for maps and for sensitivity.

23. **Shaped terrain objects** (his requirement, 2026-11-01: the options HEC-RAS has, plus "the channel with dykes", which HEC-RAS cannot do when a channel mixes burn and dykes, with profiles for bed and top and side slopes each side). Built in
    `W8 terrain tools`. Embankment, channel and channel_dyke are one object: the new ground is the old ground clamped between a cut surface and a fill surface, so each pixel settles itself and a bank turns from dyke to cut where the ground passes its top, with no step. Stretches standing above the ground also run as crest faces, one line per stretch and bank. Three things the code must keep: **object pixels are float32**, as a DEM is, or still water gains a false head at every face; **crest faces of shaped objects carry a negative coefficient**, which reads the energy head in both kernels, because the plain limit read Q down to 0.78 of critical on a resolved crest, and positive coefficients run the old path, so crest lines, spillways and natural crests did not move; **a spillway on a raised part takes the fill out of its pixels**, since a face is closed up to the higher of crest and ground. The eased coefficient is fitted to a sweep at 0.6 m head, not a law: within 5 % up to crest / dx 0.5, -13 % to +8 % above that, depending on where the line falls in the cell. See `W8 terrain tools/README.md`.

22. **The mesh and local time stepping** (2026-11-01, `W10 mesher`, merged to `main` off by default; **accepted for `main`, off by default**, the gate's failure on record). Built after all
    though deferred by decision 17, on his word. Block-uniform quadtree, 32 x 32 cells per tile, 2:1, no lists inside a tile; tiles step powers of two of the
    smallest step; both off by default, and the uniform path gives `main`'s numbers to the last digit. **Local stepping saves no time on a uniform grid**: 2 M cells,
    161.98 s uniform, 190.73 s at buffer 1.0, 160.25 s at buffer 0.5, though tile-steps halve; that fails the stage's gate, and stays recorded as a failure. **The gain
    is on the mesh at scale**: Block 2 at 10 m, 4.8 M cells against 8.1 M, clean, 603 s against 977 s at buffer 0.5, 1.6 x, five dams within 2.4 %, one ring -5.8 %; the 2.9 x first recorded had the uniform run on a shared card. On Bidah's 90 tiles the mesh is slower than
    uniform, launches swamp the kernels, so below about 1 M cells it saves memory, not time [Likely]. Buffer 1.0 stays the default: 0.5 misses a dry front by 3.7 %.

## Engineering rules for the code (his instruction, 2026-10-29)

His words: code in a standard way, so that changing one part never destroys the rest or forces a rewrite of hundreds or thousands of
lines; a parameter used in several places is set once, in one central location, and fed to wherever it is needed; look ahead so future
modifications are fast and painless. Binding for every stage; the design note lays out the module map.

1. **Small modules, one job each, a declared interface.** The solver kernels, the table builder, the hydrology engine, the ARF
   orchestration, the file readers and the QGIS plugin are separate packages that talk through data structures, never through each
   other's internals. No source file beyond a few hundred lines; a change touches one module and its tests.
2. **One source of truth for every parameter.** Physical constants, numerical settings (CFL, limiter, depth thresholds, tile size),
   units, defaults and file layouts live in one typed, versioned configuration schema in one file, validated at load and passed down
   explicitly; no literal repeated in a kernel or a dialog. Every run writes its full resolved configuration next to its results, so any
   figure can be reproduced from the folder alone.
3. **Stable data contracts.** The engine's inputs and outputs (grid and tables, rainfall, hydrographs, structures, results) are
   versioned files with a schema; the plugin, a later standalone UI and a later job runner speak only that contract, so either side
   changes alone. This is also decision 16's door and the test harness's entry point.
4. **Extension points named in advance.** The tile is the unit of the grid (quadtree levels and domain splitting attach there); the
   compute backend is behind one interface (CUDA first, CPU or Kokkos later); rainfall sources, loss methods, transform methods, routing
   methods and structures are each a registry of implementations behind one interface, so adding one is a new file, not an edit of the
   core.
5. **Tests before the next stage.** Unit tests for the table builder (against the HEC-RAS tables) and for every hydrology method
   (against HMS numbers); the analytic cases as regression tests for the solver; a Block 2 run as the end-to-end check. Nothing is done
   without its test, and a change that breaks one is not merged.
6. **Standard tooling, not house style.** The language's own formatter and linter (clang-format and clang-tidy for C++ and CUDA, ruff
   and black for Python), type hints and docstrings, a build that runs from a clean checkout with one command, continuous integration
   running the tests once there is a remote.
7. **Version control hygiene** (his standing rule): one logical change per commit, a branch for anything larger than a fix, releases
   tagged; W# folders for the engineering iterations as before.

## Version 1 scope (decided 2026-10-29)

His instruction: ship as fast as possible; before any research, name the bottlenecks and what to drop. The two schedule bottlenecks were
the **mesh generator** and the **standalone Windows UI**; both leave version 1. What remains on the critical path: the crest-aware faces
inside an explicit well-balanced scheme (handled by building the solver on the analytic tests before any real terrain) and the toolchain
(the check that precedes the research). Time [Guessing]: version 1 as cut, 3-4 months of focused work; the full list, 9-12 months.

| Item | Version 1 | Why |
|---|---|---|
| GPU solver: full SWE, sub-grid cells, crest-aware faces | Keep | The product; highest technical risk; the validation ladder controls it |
| Mesh generator (quadtree or unstructured) | Version 2; uniform grid with sub-grid instead | Bottleneck one. A uniform 10-20 m grid with sub-grid tables handles the plain; the hills go lumped in mode (b) |
| Lumped hydrology read from HMS files | Keep | Mode (a) validation and the reviewer argument; the HMS reader gives every parameter free |
| In-app delineation and Muskingum-Cunge sections from terrain | Version 2 | Users have HMS or GIS for this; weeks of work for no version-1 value |
| Rain-on-grid with CN losses | Keep | Cheap; the plain needs it |
| ARF multi-run and composite map | Keep | Cheap orchestration; the differentiator |
| Frequency storm and uniform hyetograph | Keep | His daily case |
| Gridded rainfall: netCDF, GRIB2, DSS grids, radar, satellite | Version 2; GeoTIFF stacks only | Only validation events need them; each format is about a week |
| Terrain objects: crest line, spillway, burn line, wall | Keep; channel templates version 2 | Dam work needs the first three |
| Standalone Windows UI | Version 2; QGIS plugin instead | Bottleneck two. Open source re-admits it; canvas, layers, drawing, GDAL and processing come free; TUFLOW ships this way [Likely] |
| Live view | Keep, minimal | A raster layer refreshed in QGIS every few hundred steps |
| HEC-RAS HDF reader | Keep, cheap | The oracle for the sub-grid tables and the head-to-head |
| Local time stepping | Version 2 | A speed-up of two at best, with numerical risk |
| Hardware portability (Kokkos, CPU fallback) | Decided by the benchmark, never allowed to block | If Kokkos fights MSVC and CUDA on Windows, version 1 is CUDA-only |
| Multi-PC and after-hours runs (decision 16) | Version 2; engine as a separate process from day one | Office PCs have no GPU; see decision 16 c |
| Validation ladder | Keep, except the observed event | Acceptance; the observed event waits for data |
| Installer, docs, licence audit | Minimal | A GitHub release, one tutorial, a licence file |

**The mesh in version 1** (his question, answered 2026-10-29; detail in decisions 2 and 4): "no mesh generator" means no refinement, not no
mesh. Version 1 builds its own uniform grid in-app (domain polygon, cell size, aligned to the DEM) and its own sub-grid tables from the 0.5 m
DEM; crest lines are rasterised onto the face lattice as a staircase of blocked faces with a length factor for overtopping; the solver works
on 32 x 32 tiles from day one so the quadtree (version 2) and domain splitting extend it without a rewrite. HEC-RAS supplies its geometry-HDF
tables as the oracle and its results for the head-to-head, never the mesh: importing RAS meshes would force an unstructured solver and
recreate the RAS Mapper dependency HMS 2D has. **Build order for version 1**: square-grid solver with sub-grid and crest faces on the
analytic tests, the HMS readers and the lumped engine (mode a), rain-on-grid and the hybrid (mode b), the QGIS plugin, the ARF orchestration,
the Block 2 comparison and the HEC-RAS head-to-head.

## Product requirements (added 2026-10-29)

His words: the UI "must be very easy to use"; he is "not a UI/UX specialist, but a fan of simplicity, applicability and effectivity"; there
are "many git repos that help with proper wiring of backend and UI"; the software "should be saleable and scalable", "others on other PCs
should be able to use them seamlessly", and "it should align with the capabilities of each PC".

What that implies (my reading, each point open for the design note):

1. **Hardware-adaptive execution.** Detect the machine and pick the backend: NVIDIA GPU fast path, a CPU build on every PC, AMD and Intel
   GPUs later if the market asks; domain size bounded by memory, with tiling where it is not enough. This is in tension with "fastest
   possible". Candidates: CUDA plus a separate CPU code (TUFLOW's model: GPU on NVIDIA, CPU for everyone else); a single-source
   performance-portable layer (Kokkos or alpaka; SERGHEI is built on Kokkos [Likely]) giving CUDA, HIP, SYCL and OpenMP from one code at
   near-native speed [Likely]; a portable GPU API (Vulkan compute, wgpu/WGSL) reaching every GPU including integrated ones, but WGSL has no
   float64 and the tooling is weaker [Likely]. Decided by the benchmark, not by argument.
2. **Engine and UI split from day one.** The solver is a library with a stable API behind a local service; the UI is a client. The same
   UI then drives a local engine on a laptop, a workstation GPU or a remote machine, and with a job queue several machines at once
   (decision 16, version 2). That is what "scalable" buys and what it costs. In version 1 the engine is a separate process driven by
   files and a pipe, the same split at no cost.
3. **UI.** One workflow in order (terrain, mesh, hydrology, storm, run, results), defaults that work, live feedback, few dialogs. Candidate
   stacks: a web front end in a desktop shell (Tauri or Electron) with a mapping library (MapLibre, deck.gl, OpenLayers), or PySide6/QML.
   Existing templates and repos for the backend-UI wiring are to be surveyed and one adopted, not invented. Open source (decision 15)
   puts a QGIS plugin and PyQt back among the candidates; every dependency is still audited against the chosen licence. **Chosen for
   version 1 (decision 17): the QGIS plugin.** The standalone UI is version 2.
4. **Product work** that a prototype never needed: installer and code signing, versioning and updates, documentation, support, QA,
   crash reports, an audit of every third-party licence against the chosen open-source licence, a product name, and the services that
   are sold (decision 15). Reviewer acceptance becomes a market question, not only a Block 2 one.

## Honest expectations (said to him, keep saying it)

- "Seconds" holds for one wadi or a short event. The full Block 2 catchment (599 km², 48 h, ~1-1.5 M cells with stream refinement)
  is **minutes** [Guessing: 4-8 min on the RTX 5080; local time stepping may halve it]. HEC-RAS on the CPU is hours. **Version 1**
  (uniform grid): the same minutes at 20 m over the full catchment, 30-60 min at 10 m, the plain alone at 10 m in mode (b) about 10 min
  [Guessing]; the 0.5 m terrain is inside the tables at every cell size.
- Not better than HEC-RAS or TUFLOW on 1D networks, culverts and bridges, or acceptance. Better on one thing: fast full-catchment
  wadi modelling with the hydrology and ARF inside, on his own machine.
- A months-long prototype. Each stage must work before the next starts. **Order revised 2026-10-29 (decision 17)**: square-grid solver
  with sub-grid and crest faces, the HMS readers and the lumped engine, rain-on-grid, the QGIS plugin, the ARF orchestration; the mesher
  and the standalone UI are version 2.
- Version 1 as cut: 3-4 months of focused work [Guessing]; the full list, 9-12 months. Full-catchment maps in version 1 are on the
  uniform grid; the fine-wadi map is version 2.
- **Measured 2026-11-01**, RTX 5080: Block 2 at 20 m, 2.03 M cells, 48 h, 8.9 min; at 10 m, 8.1 M cells, 36 h, 42 min; one ARF study of 13 storms and 5
  areas, 7.2 h; a 3 x 3 km fan at 10 m against HEC-RAS 6.6, 13.5 s against 8:42, 39 x. Steps cost 0.6 ns per cell.
- A saleable product is a different scale of work from a prototype: QA, installer, licence audit, documentation, support, and validation
  evidence that reviewers accept. Months becomes years. The prototype must be built so none of it is thrown away: the engine as a library
  with a stable API from the first stage, the UI as a separate client.

## Open questions for the design note

- Numerical scheme (Roe vs HLLC, MUSCL limiter, friction treatment with sub-grid, well-balancing with wet/dry), precision strategy,
  local time stepping. Steep cells (decision 18): the dx <= h/S rule and whether a sloped sub-grid free surface lifts it; the thin-cell
  velocity treatment and the depth threshold for the CFL search.
- Quadtree vs unstructured mesh and sub-grid at refinement interfaces (version 2); how a face carries a crest profile together with
  sub-grid tables. **Version 1**: tile size and layout (32 x 32 proposed), the crest-line staircase and its length factor, the HEC-RAS
  table oracle, and the engine's file-and-pipe protocol that the QGIS plugin and a later job runner share.
- The lumped-to-2D handoff when wadi-mouth cells are coarse (spread the inflow over the sub-grid channel width?).
- ARF option and its presentation to reviewers (decision 9).
- Stack micro-benchmark (CUDA C++ vs alternatives), UI toolkit; file formats to read (HMS, HEC-RAS HDF terrain and geometry for
  comparisons) and write.
- A name for the method in reports; the forbidden-terms habit applies to any client product made with it.
- Backend portability (CUDA plus CPU code, Kokkos-style single source, or a portable GPU API) and how the engine detects and uses each PC.
- UI architecture and stack (desktop shell with a web front end, or Qt), the mapping component, the live view, and which existing
  backend-UI template to adopt (version 2). **Version 1**: the QGIS plugin's structure, how it drives the engine process, long-running
  tasks, the live raster refresh.
- The open-source licence (GPL-3.0, Apache-2.0 or AGPL-3.0) and what is sold around the code; licences of every dependency; installer;
  competitor pricing (TUFLOW, ICM, MIKE) as the reference for the services.
- Distributed execution: the node service and job queue, discovery and security on a LAN, scheduling across unequal PCs (version 2); the
  tile and halo design that keeps domain splitting possible (version 1).

## Work order after version 0.1.1 (his decisions, side chat of 2026-11-02)

His rules for all of it: each item its own branch, tests, and a `W#` folder where it is an engineering iteration; **a feature is done only when it is in the plugin and tested through the real dock**; the [PRESERVE-CHECK] and [BROAD] rule applies; never push or publish without his word. In this order:

1. **D2, see the mesh.** After every run, the real cell grid as a vector layer in Model setup. **Done, `W17 cell grid layer`.**
2. **D8, boundaries.** One line layer holds all boundaries. The dock lists each line in a table with kind and value editable, defaults filled by kind, no fields needed in the layer. The kind and value field route stays. **Done, `W18 boundary table`.**
3. **D1, time slider.** The engine exports the saved frames as one CF NetCDF file; one dock button loads it as a QGIS mesh layer with depth, speed and hazard datasets, working with the Temporal Controller. Cell frames first; per-frame pixel maps only for small areas, if at all. **Checked: QGIS 3.44.8 reads it with its time axis. Done, `W19 time slider`.**
4. **D5, rainfall.** A Storm section: hyetograph table, hypothetical design patterns with ARF, gridded rain and DSS first, plus NetCDF; radar and satellite later. The rain feeds rain-on-grid and lumped alike. **Done, `W20 storm section`.**
5. **D9, result lines, HEC-RAS style.** Two kinds, labelled in the plot. Upfront lines and points stay, computed during the run: the numbers of record. After the run the user draws a temporary line or picks one from a layer, and the plugin rapidly shows the hydrograph, depth, and the water surface with the terrain along the line, all changing as the time slider moves. These read saved frames, so state their limit: the map interval, flow estimated from depth and speed. Depends on D1. **Done, `W21 result lines`; flow from frames read 0.6 to 1.0 of the upfront lines until `W30 face frames`, which saves the face discharges with every map: a line after the run is now of record at the frame interval.**
6. **D7, profile editor.** A dedicated graphical editor per structure, as in HEC-RAS: drag points, type a table, undo, for bed, tops and elevations. **Done, `W22 profile editor`; no human hand has dragged a point yet.**
7. **D3, mesh controls.** A table of lines: near cell size, number of rows, far cell size, as in HEC-RAS. The quadtree only doubles sizes, so round to the ladder and say so. **Done, `W23 mesh controls`; a band alone fails its 5 % rule, with the stream rules it passes.**
8. **D4, automatic breaklines in the Mesh section.** A Suggest breaklines button makes an editable layer to accept or delete. Streams in mountains and defined wadis by bank lines, never on the thalweg; none in plains with no defined wadi; one bank where one exists; lines at slope changes such as roads and dams. Follows the rules under Next steps and the `W5` results. Refinement by slope change alone lost 18 % of a wadi peak, so test it. **Done, `W26 suggested breaklines`; banks go to the Mesh table, not to Structures.**
9. **D6, HMS-style model inside.** The model generates its own subbasins, reaches, junctions and reservoir routing from the DEM. **First piece done, `W24 basin model`: `wadi2d basin` writes `basin.json` and `basin.gpkg`, and the lumped engine runs on them. The hand-back and transmission loss are in, `W25 hand-back and transmission loss`; the job wiring and the dock in `W27 basin wiring`. Done. His lag decision, 2026-11-02: Kirpich as he writes it in HMS, the default; NRCS stays an option. His routing decision: HMS-faithful stays, `conserving` added, `W29`.**
   - The 2D flow area is always the full area.
   - A subbasin is lumped by default. Parameters complete: it runs lumped. Not complete: a warning before the run names what is missing, and it runs as rain-on-grid unless the user adds them.
   - Scenarios on the same basin model can switch each subbasin between lumped and rain-on-grid.
   - Lumped means no rain on the cells beneath it; otherwise rain-on-grid. A cell never gets two rainfalls, and a check stops the run if one does.
   - Where a reach is defined, route HMS style. Where none is, the junction flow enters the 2D grid and runs over the dry ground to the next junction.
   - Flow double-count check: a reach-routed hydrograph stays out of the 2D grid until the end of its reach. The dock shows each junction's route.
   - Hand-back: where 2D flow reaches a junction with a lumped reach below, it leaves the grid at a defined line and enters the reach. This link does not exist today; prove its mass balance first.
   - Dry-bed transmission loss on 2D routing cells: an option, off by default.

**Productivity ideas, his answer of 2026-11-02: keep them, later, after the important parts; scenarios with compare first (missing from the HEC products, present in ICM and Bentley), then a batch run; the rest are good too:** scenarios with compare, check before run, run queue, templates, dock tabs, click-the-map results, warnings on the map.

## Next steps (for the next session)

Waiting on him:

1. Evidence for Manning n on the hills (field or photographs). 0.05 to 0.1 moves the Bidah peak by 25 %, the solver by 4 % at most.
2. The datum: confirm GGC sits 2.39 m above NSA for Block 2 W2, and on which datum the dam levels are to be used.
3. Confirm my edits to the dam shapefiles (gaps joined, spillways centred on the thalweg, `validation/block2_full.md` section 5).
4. Whether a neighbouring gauged wadi, flood marks or dam level records exist for Batinah. **Partly answered 2026-11-02: the gauges and Shaheen at Lihban are on W:, listed in `W11 validation round two`.** Still wanted: which of the 100-yr storm, the CN grid or the gauges he trusts, and whether transmission loss belongs in the design.
5. Permission to download the UK EA 2D benchmark data; the GPL section 7 permission for the NVIDIA libraries; whether the public repo may keep the
   project data it carries (dam levels, job files with local paths, the datum finding).
6. Deleting the generated caches under `validation/block2_full/` (`cache`, 3.9 GB; `cache_3f32ca6`, 6.5 GB), which the session's safety check refused.

Waiting on him, W9: the two things added beyond the brief, each cell filled to its own mean depth and the lift of depth x speed to the run's peak (H1 grows 12 % on the full extent from the first). Both are in `main`; `outputs.pixels.edge_passes` 0 and the fill stay as named settings so either can be undone.

Terrain found on the way, 2026-11-01: a straight step of about 0.75 m in the Bidah DEM at about 438,890 / 2,727,425, a seam on his reading, not confirmed; a hole in the blended full-extent DEM at 508,137 / 2,579,657, 30 m wide and 700 m deep, which makes the reported deepest pixel, 709 m, meaningless.

Decided 2026-11-01, his agreement: hazard is pixel depth x interpolated velocity on 5-minute frames, as HEC-RAS Mapper and his Majlas script do; no split of a face by conveyance until a case can validate it. Rerun `runs/full_30m_200yr_5min` holds those frames.

Version 2, his question of 2026-11-01 (cells aligned with the ground so steep slopes need no finer mesh): keep the tile quadtree, add faces snapped to breaklines, and test a sloped water surface inside a cell. Long cells along the flow fix diagonal channels; they do not by themselves lift the limit on steep ground, and thin cells shorten the explicit step. An unstructured mesh is the alternative, at 2 to 4 x the cost per cell (decision 4).

Automatic breaklines, his rules of 2026-11-01: streams from his Watershed-Scripts create_streams.py find the channel, smoothed; a row of cells runs along the thalweg with bank lines either side, never a breakline on the thalweg, because flow concentrates on a breakline. On a plain with no defined wadi there is no stream breakline at all: the faces stay as they are and the flow finds its way. One bank only where one bank exists. Roads, dams, ponds and stockpiles come from surveyed layers first, then DEM detection, reviewed in QGIS. Queued after the rerun: plan_min 0.05 against the Bidah HEC-RAS case; automatic lines against Bathinah Highway CL only, the coastal road is not fully built.

Results of 2026-11-01. Aligned faces (`W3 breakline faces test`): a 9-line advection fix takes the 45-degree error to -0.8 to +3.2 %, 0.16 over the 3 % pass mark, on a stand-alone CPU port, not yet on the GPU; snapped faces rejected, they oscillate to +29 % on banks; cell vectors pass, about 25 % of the kernels; triangles pass at equal faces, a whole new engine. Refinement by change of slope alone lost 18 % of a wadi peak. `plan_min` 0.05 (`W4 plan_min test`): accuracy passes, the speed gain is unproven. Automatic lines (`W5 automatic breaklines test`): suggestions for review only. Pixel hazard done (`W2 full extent run`).

Branch `fix/dry-face-advection`, not merged: the dry-face fix (`W6 dry face fix test`, on the GPU 45-degree 3-cell mean +6.4 to +1.1 %, worst +4.2 %, Bidah unchanged) and the plugin's engine default. Plugin tested through the real dock, 32 of 32 (`W7 plugin test`). Hazard film and pixel hazard with a guarded sloped water surface done (`W2 full extent run`); the fixed 2 m guard switches the slope off near 7 % at 30 m, so it needs to scale with the local slope.

From the terrain tools: merged and pushed on his word to push as the work goes. A `normal` boundary draws the level down near itself, 0.88 x normal depth at 120 m from it, and its width does not matter; the 2.5 x reported first was a filling transient. Overtopping at heads of 0.3 to 1.2 m is done (`W8 terrain tools`); submerged crests, flow round a bend in a channel, and shaped crests against HEC-RAS are untested.

**Boundaries, fixed 2026-11-01 (`7f4338d`):** a line more than one cell off the active cells used to lose those samples without a word: a 36.6 km sea line opened 0.2 km at 15 m and the balance closed all the same. It now opens the nearest cells within `snap_m` (150 m) and warns if it still opens under `min_share` (0.6) of its length. Lines within a cell of the domain keep their cells; W2 and the plugin hybrid were never affected. The W11 test 4 sets `t` and `b` were throttled and do not count.

Then, in no order: the full-extent run is done (`W2 full extent run`); frames every 5 to 10 min and a rerun are what his hazard video needs, the AIDR H1 to H6 script is in the Majlas dam break project;
why cells over 10 m relief hold 2 to 2.6 x more water in RAS than here (hillslope total matches, section
peak unaffected, may matter for a short storm); Wadi2D's 16.5 cm high in the gorge at 20 m, halving at 10 m, so design points run at 10 m; `plan_min` 0.05 (9 % faster, peaks within 0.3 %, needs a proper test); the composite ARF maps have been written but not looked at; the
plugin has no field for `initial_levels` yet, job.json only, and no ARF study, command line only; a full-domain run with the dams in place; research topics N04, N06, N07, N08, N10, H05, S01 to S05
were never run; reviewer acceptance is untested.

## Iterations

- `W2 full extent run` (live): the actual project boundary at 30 m on NSA 5 m blended with Copernicus 30 m, Block 2's 200-yr storm. Its `README.md` holds inputs and results.
- `W14 cell edge steps` (live, merged): why depth maps drew as cell-sized blocks, the edge blend.
- `W13 time step test` (done): a quarter of the step moves Bidah's peak 0.23 %.
- `W12 full extent rerun` (live): W2's job on the merged engine, the rule, the five dams, why the peaks rose, maps with the edge fix. Quote this and not W2 for current numbers.
- `W32 combinations test` (done, testing only): the CPU twin through the new sections, a generated basin with a gridded storm, with the mesh, with a resume, on the full extent, and the hand-back at a dam through crest faces; 4 of 6. **Open: the CPU twin and the GPU diverge deterministically on the Block 2 hybrid at 80 m (101,421 against 101,432 steps, Faydh 01 493.7 against 506.6 m3/s, a ring -23 %) while Bidah matches step for step to six digits, each backend repeating itself; a resumed run re-phases its series clock by one interval at the checkpoint, so it passes W25's 1e-3 and not the last digit.** Also found: the generated reservoir starts at its spillway crest while the grid pool starts dry, 3.6 Mm3 of dead storage on Bidah; the full-extent guard counts the bounding box; the dock has no backend choice.
- `W30 face frames` (done on QGIS 3.44.8): `outputs.face_discharge`, on by default, saves the signed x- and y-face discharges with every map, GPU and CPU from one source, in `NOT_WATER` so old hashes and checkpoints hold; `wadi2d lines` and the Result lines panel read the staircase faces a line crosses as an upfront line does, and fall back to the W21 estimate with the old words on a run without them. Bidah 20 m: across, oblique, axis and bent lines 1.001 of the record, worst 0.28 % over the running frames, the estimate 0.939; mesh 1.000. Disk 31.8 against 20.1 MB, 1.58 x per map; full extent about 24.6 GB in place of 15.4 [Likely]. 42 of 42 through the dock. Not tested: full extent, GPU resume.
- `W29 conserving routing` (done on QGIS 3.44.8): `hydrology.reach_routing`, `hms` (unchanged, to the last digit) or `conserving`, Todini's mass-conservative, storage-consistent variable-parameter Muskingum-Cunge on HMS's own cells and sub-steps, a `Reach routing` combo in the dock. Block 2's eight reaches at 100 yr: HMS path out/in 0.9992 to 1.0002, conserving 1.000000, peaks within 0.14 %; short 20-min floods, HMS path 0.84 to 1.91 x, conserving 1.000000; hand-back `routing_defect` 5e-6 m3 against -218.5. **Two guards are the agent's, not Todini's: D* >= 1 - C* and a parcel-speed floor of 0.1 m/s, needed on HMS's grid (a -97 m3/s dip and a tail that never drained without them) [Likely the right form]; on a short flood the two schemes are different models.** 29 of 29 through the dock. Not run: on a generated basin through the dock, an ARF study, a resume.
- `W28 final merge test` (done): every dock scenario of the work order rerun on the merged `main`, 497 of 497.
- `W27 basin wiring` (done on QGIS 3.44.8): D6b, a basin generated from the DEM runs from the dock, lumped by default, any subbasin switched to rain-on-grid, an incomplete element refused into rain-on-grid by name with a `parameters` override in the job to complete it; reaches route HMS style, junctions without one feed the grid, hand-back lines are built from the routes with the books closed; a cell never gets two rainfalls, overlap over 1 % stops the run; the lumped network's series are written for every element. Bidah 52 of 52 and Block 2 26 of 26 through the real dock; old jobs to the last digit. **Five dams through the dock at one storm area, generated against HMS: NRCS lag 1.05 to 1.59 x, HMS-style lag 0.88 to 1.26 x; the lag and the stream threshold are his switches, no gauge decides.** Found: `W24`'s polygons overlapped along shared edges and would have double-counted rain silently; now pixel-exact. Not run on a generated basin: a gridded storm, a mesh, a resume, the full extent; the hand-back at a dam is placed, not validated through the crest faces.
- `W26 suggested breaklines` (done on QGIS 3.44.8): D4, a Suggest breaklines button makes an editable layer: banks either side of defined wadis one cell clear of the thalweg, never on it, none on a plain with no defined wadi, one bank where one exists; top-hat crests for roads, dams and dykes on ground under 15 % slope; 32 of 32 through the real dock. **Bank lines used as crest lines cost the peak: Bidah -9.7 % at 10 m and -21.7 % at 20 m, Faydh 01 -30.1 % and -35.5 %, with 1.6 to 3.3 x the steps; the same lines a metre below the ground still cost 7.8 %, so three quarters is the crest face itself, its critical-flow cap and its step on every face a gorge flood crosses obliquely [Likely]. So banks are refinement lines for the Mesh table, which the layer's `near_dx`, `rows` and `far_dx` fields fill, and crests are for roads, dams and dykes; a face that carries the ground along a line without the weir law is the missing engine piece.** Highway on W5's ground: 74 % found with 211 km elsewhere. Not tested: banks as refinement lines through a flood.
- `W25 hand-back and transmission loss` (done, engine only): D6c, a line hands 2D flow to a lumped reach during the run and the reach's outflow comes back one lumped step late, held flat over the step; the books close to 4e-8 with the network's storage measured by draining it, resume keeps the line series, and old jobs match `main` in 311 of 311 items. On Block 2, R1 lumped against the same 26 km on the grid: 1,923 against 1,832 m3/s, 5.0 % higher and 35 min later, a difference of method. D6d, dry-bed transmission loss as HMS's percolation channel loss over the wetted share of each cell, rates from Lane's table in NEH 630 chapter 19, off by default; a dry channel loses the hand-computed volume within 3 %. **Found on the way: the HMS-faithful Muskingum-Cunge does not conserve volume, 0.22 % on R1 and up to 1.9 x out/in on short floods, booked on its own line as `routing_defect`; his call whether to keep it HMS-faithful or add a conserving variant. Fizh: bed loss at 150 mm/h on every channel cell still leaves 2.2 x Q100, so bed loss alone does not close the factor.** Not wired: `basin.json` networks, dock rows, a map of the loss.
- `W23 mesh controls` (done on QGIS 3.44.8): D3, refinement lines in the Mesh section, a table of near, rows and far with the actual size on the ladder shown before a run, 67 of 67 through the real dock; six existing jobs give every number unchanged. **An 8-row band on the main wadi alone reads 6.8 % low at Bidah's dam and 7.8 % at a wadi section, failing the 5 % rule set before the run; with the stream rules on, 4.1 % at worst. Far changes nothing up to 32 rows, a tile's width, and the dock says so.** The 18 % loss by slope change alone is in `W3` section 8, not `W5`.
- `W24 basin model` (done, engine only): D6a, subbasins, reaches, junctions and reservoirs from the DEM. On Block 2 the dam areas match HMS within 0.2 % (Bidah -4.2 %, the polygon past the axis), lengths and slopes within about 1 %; peaks 1.05 to 1.58 x HMS, all of it the lag. **Finding: HMS's 18 lags are not NRCS lags; each is 0.474 x Kirpich on the longest flow length and the 10-85 slope, spread 0.473 to 0.476. With HMS's lag and reaches the generated model gives 0.96 to 1.01 of HMS. Which lag the product uses is his call.** The NRCS lags sit on the 2D model's response instead; two methods agreeing is not a gauge.
- `W22 profile editor` (done on QGIS 3.44.8): D7, a graphical editor per structure beside the map, drag, type or paste, undo, with the engine's own preview under the plot; 120 of 120 through the real dock; an edited bed point moved the solver's ground from 120.65 to 118.50 m. A saved profile is a CSV section table per line that outranks fields and tables; crest lines and spillways take it as Z per vertex. Files are named by feature id, so packing a shapefile can misplace one.
- `W21 result lines` (done on QGIS 3.44.8): D9, a Result lines panel, upfront lines and points beside temporary lines drawn or picked after the run, all on the time slider, 73 of 73 through the real dock. Flow read from saved frames is an estimate at 0.6 to 1.0 of the upfront lines across the flow, lowest on 30 m cells, 7.5 x too high along the flow; the plot says so. Saving face discharge with each frame would fix it, about 5/3 of a frame, not built: his call.
- `W20 storm section` (done on QGIS 3.44.8): D5, steady, hyetograph, design storm and gridded rain from NetCDF, DSS and GeoTIFF folders, 41 of 41 through the real dock. Lumped and 2D take the same rain: the Block 2 hybrid on the HMS storm and on the same rain as frames, steady lines within 0.34 %. **Found there: `S5_ring` and `S11_ring` flicker at 40 m, about 107 m3/s a minute; S5 reads 480 m3/s raw and 325 as a 15-minute mean, in any run, so a raw peak near a lumped inflow can read high.**
- `W19 time slider` (done on QGIS 3.44.8): D1, the saved frames as a mesh layer on the Temporal Controller, 31 of 31 through the real dock.
- `W18 boundary table` (done): D8, one line layer, a table of kinds and values, 34 of 34 through the real dock.
- `W17 cell grid layer` (done): D2, the real cell grid in Model setup after every run, 21 of 21 through the real dock.
- `W16 release package` (live): the Windows package and installer, tested from a fresh environment on this PC; another PC not yet.
- `W15 final plugin test` (done): the five dock checks on merged `main`, 207 of 207, small areas, throwaway QGIS profiles.
- `W11 validation round two` (done): crest lines against RAS, a second catchment, the envelope, the extent F, the Fizh gauge, Shaheen at Lihban. The headline numbers were recomputed from the raw series on 2026-11-02; the rest are the agent's.
- `W10 mesher` (live, merged, off by default): quadtree, local time stepping, the mesher, the Mesh section; decision 22.
- `W9 pixel outputs` (live): pixel depth and hazard in the engine, sloped surface, smooth maps, Make map. The map scripts of `W2` and `W7` are superseded by it.
- `W8 terrain tools` (live, merged): shaped terrain objects, the crest sweep, the dock check.
- `W1 research and design note` (live): toolchain gate, Block 2 inventory, research, benchmarks, prototypes, design note. The software itself lives at
  the repository root. Convention: `W<n> <short description>`, never overwritten; superseded iterations stay and are marked in `README.md`.
