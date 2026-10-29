# Wadi2D - profile and live state (read first; then `README.md`)

**State line (2026-10-29): project decided and recorded, nothing researched or coded yet. Next: the deep research (multi-agent
workflow) into GPU shallow-water solvers, sub-grid, meshing and the HMS methods, then a design note for his approval, then the
build. First iteration folder to create: `W1 research and design note`.**

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
heads, culverts) and **full-catchment flood maps**.

Why: today he runs HEC-HMS (hydrology, ARF through depth-area analyses) and exports hydrographs into HEC-RAS 2D (plains, braided
wadis, fans with several outfalls). HEC-RAS is CPU-only and slow, has no ARF (rain falls uniformly), and no hydrology of its own.
HEC-HMS 4.1x has a 2D subbasin, but the mesh must be built in HEC-RAS and it runs only the diffusion wave. He wants one model, fast.

## Owner, repo, machine, rules

- Owner: Mojtaba (personal project). Data may go on GitHub (files of 100 MB and more stay out, listed). No deadline.
- Repo: `https://github.com/mojikone/Wadi2D.git` (remote `origin` set on 2026-10-29; the initial commit was made locally; **nothing
  pushed**, pushing needs his explicit word, every time).
- Folder: `D:\Mojtaba\Renardet\Wadi2D` (outside the Batinah block folders). Working folders carry a short description in the name:
  `W<n> <what it holds>` (his instruction of 2026-10-29, now rule 15 of his global CLAUDE.md).
- Stack: his words, "whatever yields the fastest 2D solver possible". My pick, not yet benchmarked or approved: CUDA C++ core as a
  DLL, Python/Qt UI on top (his PyQGIS habits carry over). To be decided in the design note with a micro-benchmark.
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

1. **Solver**: full shallow-water equations, finite volume, explicit, CUDA; second order (MUSCL-type), well-balanced (still water
   stays still on steep ground), robust wet/dry, supercritical flow and jumps; adaptive global time step on CFL; local time stepping
   to be evaluated (the steep fine cells set the step for everyone).
2. **Sub-grid**: per cell a volume-vs-level table, per face a wet-width / conveyance-vs-level table, built from the 0.5 m DEM. Faces
   snap to breaklines and carry the crest profile, so **high ground blocks the flow until the level passes the crest**. This is the
   feature he asked for first ("edges aware of topography").
3. **Store depth, not water level.** [Certain, arithmetic] Float32 at 1,500 m elevation resolves ~0.12 mm; a 2 s step of 100 mm/h
   rain adds 0.056 mm; a level-based float32 solver loses the rain in the hills. Depth storage or mixed precision; FP64 on a GeForce is
   ~64x slower, so avoid it in the main loop.
4. **Mesh generator**: built in-app from the DEM, breaklines and refinement zones; quadtree (TUFLOW-HPC-like) is the first candidate,
   unstructured the alternative; refinement bands along the delineated streams so the mountains keep the wadis at full resolution
   (his requirement for full-catchment flood maps); coarse cells elsewhere in the hills.
5. **Hydrology inside, hybrid by design.** Subbasins are first-class objects; each is either *lumped* (HMS methods: SCS CN losses,
   SCS lag or Clark unit hydrograph, Muskingum-Cunge reaches) or *2D* (rain-on-grid with CN or Green-Ampt losses, depth-varying
   Manning n). A lumped subbasin polygon **masks the rain on every 2D cell beneath it** (no double rainfall; his point). Its hydrograph
   enters at its delineated outlet, into the wadi cells at the mountain front, not smeared along a boundary line. Same concept as the
   HMS 2D subbasin and ICM subcatchments draining to 2D zones, which is what he intended from the start.
6. **Three modes, compared on Block 2 at the five dam sites against the W1 HMS peaks**: (a) all lumped, which must reproduce HMS within
   a few per cent and validates the hydrology engine; (b) hybrid, lumped hills and 2D plain; (c) full 2D with coarse sub-grid hills and
   refined streams. Expectation [Guessing]: (b) for design flows (reviewers know the methods; fastest, the steep cells leave the 2D
   domain), (c) for full-catchment flood maps. Rain-on-grid and SCS-lag peaks will not coincide; the comparison is to know why before
   anyone else asks. If (c) matches HMS, his stated preference is the single full-2D model.
7. **Delineation is preprocessing, not run-time load.** Flow direction and accumulation on the 2 m or 5 m raster (599 km² at 5 m =
   24 M cells, seconds), once per terrain, cached on disk. **Catchment area at any point is one lookup in the accumulation grid**;
   catchment polygons only on demand (display). Wall and burn objects shared with terrain modification, as HMS does.
8. **Muskingum-Cunge parameters from terrain**: reach length and slope from the stream profile on the (burned) DEM; cross-sections
   sampled perpendicular to the stream every ~100 m and reduced to a representative **8-point section** (HMS supports it) or a fitted
   trapezoid (bottom width, side slope) when he wants the HMS look; Manning n from land use. Valid in confined hill wadis; fans and
   braided reaches are 2D anyway. [Likely]
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
   design note**, including how it is presented to MAFWWR reviewers.
10. **Terrain modification as vector objects**, applied when the sub-grid tables are built, **the DEM file never changes**: dam crest
    line with an elevation profile (a wall face; overtopping automatic), spillway structure at a face (Q = C L H^1.5, C ~ 2.1 for his
    dams), channel template on an alignment (burned), wall, burn line. The reservoir is the DEM behind the crest, so routing comes
    free (no EAV curve, no Modified Puls); a direct cross-check for Block 2 W2 when the dam data (FSL, crest, spillway length) arrives.
    The same objects feed delineation (HMS wall and burn layers).
11. **Rainfall inputs**: uniform hyetograph; the HMS frequency storm (point depths, 24 h specified pattern, storm area, ARF table);
    gridded time series: netCDF (CF conventions), GRIB2 (NOAA, ECMWF), GeoTIFF stacks, HEC-DSS grids, weather-radar products (GCC
    meteorological services run radars now; Oman DGMAN), satellite (GPM IMERG). Observed events become validation cases; candidate:
    Cyclone Shaheen, October 2021, over Al Batinah [Likely data exist; not checked].
12. **Validation ladder**: analytic cases (still water on steep ground, Stoker/Ritter dam-break, Thacker oscillation), the UK
    Environment Agency 2D benchmark tests, HMS replication on Block 2, one Block 2 wadi head to head with HEC-RAS on the same terrain
    (depth, extent, run time), an observed event. Acceptance by reviewers is unknown; the benchmarks and the HMS replication are the
    argument.
13. **Outputs**: max depth, velocity and hazard GeoTIFFs; hydrographs and levels at design points; per-storm-area and composite maps;
    live view of the flow on the GPU during the run.
14. **UI (Windows)**: load DEM and rasters, draw breaklines, boundaries, structures and subbasins (or import shapefiles), mesh, set the
    storm, run, watch, export. Reads the HMS project files (`.basin`, `.met`, `.control`, `.pdata`, DSS) so test (a) is apples to apples.

## Honest expectations (said to him, keep saying it)

- "Seconds" holds for one wadi or a short event. The full Block 2 catchment (599 km², 48 h, ~1-1.5 M cells with stream refinement)
  is **minutes** [Guessing: 4-8 min on the RTX 5080; local time stepping may halve it]. HEC-RAS on the CPU is hours.
- Not better than HEC-RAS or TUFLOW on 1D networks, culverts and bridges, or acceptance. Better on one thing: fast full-catchment
  wadi modelling with the hydrology and ARF inside, on his own machine.
- A months-long prototype. Each stage must work before the next starts: square-grid solver with sub-grid, then the mesher, then the
  hydrology, then the UI.

## Open questions for the design note

- Numerical scheme (Roe vs HLLC, MUSCL limiter, friction treatment with sub-grid, well-balancing with wet/dry), precision strategy,
  local time stepping.
- Quadtree vs unstructured mesh; how a face carries a crest profile together with sub-grid tables; sub-grid at refinement interfaces.
- The lumped-to-2D handoff when wadi-mouth cells are coarse (spread the inflow over the sub-grid channel width?).
- ARF option and its presentation to reviewers (decision 9).
- Stack micro-benchmark (CUDA C++ vs alternatives), UI toolkit; file formats to read (HMS, HEC-RAS HDF terrain and geometry for
  comparisons) and write.
- A name for the method in reports; the forbidden-terms habit applies to any client product made with it.

## Next steps (for the next session)

1. Create `W1 research and design note\` with its own `README.md`.
2. Deep research (Workflow, multi-agent, several phases): TUFLOW HPC and SGS papers; HEC-RAS sub-grid (Casulli 2009 and the RAS 2D
   reference manual); 3Di; Iber+; LISFLOOD-FP DG2; TRITON, HiPIMS, SERGHEI; GPU SWE kernels and memory layouts; quadtree meshers;
   local time stepping; well-balanced wet/dry schemes; mixed precision; the EA 2D benchmark report; HMS technical reference (SCS CN,
   lag, Clark, Muskingum-Cunge 8-point, depth-area analysis, frequency storm); ARF guidance (ARR 2019 Book 2, HMS, NOAA); rain-on-grid
   vs lumped comparisons; gridded rainfall formats and GCC radar products.
3. Design note for his approval before any code; then the build in the stated order, each stage verified.

## Iterations

- none yet. Convention: `W<n> <short description>`, never overwritten; superseded iterations stay and are marked in `README.md`.
