# W79 Block 2 four ways

**Live: the rerun of 2026-11-15 (`jobs/rerun_*.json`, `runs/rerun_*`). The first attempt (jobs without the `rerun_`
prefix, `runs/run1_*`, `runs/run2_hms_lumped`) is superseded: it read the ARF at 1,370.77 km2 and ran at 1 m pixels.**
All four runs are done. Runs 3 and 4 rained on a 40 m rim round the outline (6.2 km2, 0.6 % of the water: Findings);
the jobs without it are written (`jobs/rerun2_*`, `inputs/domain_no_rim.geojson`) and not run. The pixel rasters of the three aligned 2D runs are not made: the products
step fails in the strip's pixel stage at 0.5 m (below), an engine fault the pixel-maps work is fixing; the cell maps,
the series and the time-slider files are made. `Block2_four_ways_interim_cells.qgz` holds what exists ("interim, cell
maps"); `Block2_four_ways.qgz` waits for the pixel rasters. `Block2_four_ways_interim.qgz` is not ours: written at
05:36 by someone else, it holds his Block 06 project, and is left as it is. Nothing below is a design figure: no gauge
says which method is right.

## The rerun (2026-11-15)

Common to all four: FM_200yr.met (251 mm, 24 h, FM 10-1000yr pattern), his ARF FM table, 48 h, 5-min lumped step,
dams empty at the start, the W79 domain to the sea (1,406 km2) with the sea, four side outlets and the north line at
Wadi HAT as `normal` lines, CN 88 where his CN raster has none, the aligned centre mesh at 20 m (401 lines,
2,941,116 cells, 189,406 on the lines) with the ground read at the 0.5 m pixel (`pixel_stride` 1), GPU, maps every
15 min, W1's dam lines and a line round each pool.

The ARF, his decisions of 2026-11-15 (dam areas from Basin 3: Bidah 03 20.97, Faydh 01 74.30, R5A 117.10, R2A 175.87,
Z4C 211.09 km2):

| Run | Job | ARF |
|---|---|---|
| 1 Full 2D | `rerun_run1_full_2d_aligned` | one storm area of 100 km2 for all rain: 0.913, 229.2 mm |
| 2 Full HMS way | `rerun_run2_hms_lumped` (`scripts/s03_lumped.py`) | every element at its own total upstream area, HMS's depth-area analysis: the sub-network above each element rerun at its area (281 elements, 1.2 s) |
| 3 Hybrid | `rerun_run3_hybrid_aligned` | S1 to S18 (above the dams) at their dam's area, so each reservoir's outflow entering the grid is the dam's at its own area; the 86 plain subbasins and the grid rain at 100 km2 |
| 4 Hybrid, routing and dams in 2D | `rerun_run4_hybrid_2d_routing_aligned` | S1 to S18 at their dam's area, entering at their wadi outlets; the plain subbasins and the grid rain at 100 km2 |

Runs 3 and 4 needed an engine option: `hydrology.subbasins[].storm_area_km2`, a lumped subbasin's own storm area
(commit `38dc74e`, its own commit with its tests; refused on a 2D subbasin, without `storm.arf`, beside
`storm.arf_factor`, and by a depth-area study; a job without it keeps its hash). Check: run 3's five reservoirs equal
run 2's to 0.1 m3/s.

### Dam peaks (`dam_peaks.csv`, m3/s; times from the storm's start, h)

| Dam | ARF run 1 / 2-4 | Run 1 in / out | Run 2 in / out | Run 3 in / out | Run 4 in / out | Inflow time to peak, runs 1 / 2 / 4 |
|---|---|---|---|---|---|---|
| Bidah 03 | 0.913 / 0.975 | 581 / 0 | 455 / 0 | 455 / 0 | 446 / 0 | 12.5 / 12.8 / 13.3 |
| Faydh 01 | 0.913 / 0.931 | 2,321 / 0 | 1,240 / 0 | 1,240 / 0 | 1,221 / 0 | 12.3 / 13.2 / 13.8 |
| R5A | 0.913 / 0.905 | 2,075 / 604 | 1,144 / 754 | 1,144 / 754 | 1,136 / 668 | 12.8 / 14.7 / 15.0 |
| R2A | 0.913 / 0.876 | 3,949 / 1,134 | 1,736 / 818 | 1,736 / 818 | 1,515 / 844 | 12.8 / 14.2 / 14.0 |
| Z4C | 0.913 / 0.861 | 3,249 / 3,458 | 2,101 / 2,025 | 2,101 / 2,025 | 2,078 / 2,019 | 13.8 / 15.4 / 16.0 |

Inflow volumes, Mm3 (runs 1 / 2 / 4): Bidah 03 3.8 / 4.3 / 4.3; Faydh 01 14.9 / 15.2 / 15.2; R5A 22.8 / 22.9 / 22.8; R2A 34.3 / 32.9 / 32.8; Z4C 41.7 / 39.2 / 39.1.

How each is read: runs 2 and 3, the lumped reservoir's inflow and outflow (5-min step). Runs 1 and 4: the outflow on
the dam line (60 s series); the inflow by the pool's own balance, the change of the water in the pool polygon between
two saved maps plus the dam-line outflow in between (`scripts/s04_check.py`). Its volume is exact; its peak is a 15-min
mean, so a few per cent under an instantaneous one (Z4C in run 1 reads 3,249 in against 3,458 out for that reason). In
run 1 it holds the rain on the pool. The first table of this rerun read the inflow on a line round each pool; that
line over-reads where it crosses a wadi more than once, and is kept only as the `ring_inflow_*` columns.

Findings:
- [Certain] The full-2D inflow peaks are 1.3 to 2.3 times HMS's (run 1 against run 2), 0.3 to 1.9 h earlier, as on
  Block 2 since W1. Part of the gap here is the ARF: run 1 reads 0.913 everywhere, while run 2 reads 0.861 to 0.975.
  Bidah 03 is the reverse: 0.913 against 0.975. Most of the gap is the method, as before.
- [Certain] Runs 2 and 3 agree at the five dams: the grid below a dam does not touch its lumped hydrograph.
- Bidah 03 and Faydh 01 do not spill in any run: their pools hold the whole 200-yr inflow from empty.
- [Certain] Run 4 against run 2 (the same lumped hydrographs, routed in 2D instead of Muskingum-Cunge and Modified
  Puls): inflow volumes within 0.3 % at all five dams (4.33, 15.22, 22.82, 32.83, 39.13 Mm3 against 4.33, 15.23,
  22.85, 32.93, 39.18). Inflow peaks are 0.7 to 1.8 % lower at Bidah 03, Faydh 01, R5A and Z4C, and 12.7 % lower at
  R2A (1,515 against 1,736 m3/s; [Guessing] its six subbasins meet on two branches, at other times than the reaches give). Outflow peaks: R5A -11 %, R2A +3 %, Z4C
  -0.3 %. The +28 % and +8 % inflow first reported at R5A and R2A were the ring line over-reading (R5A +3.6 Mm3, R2A
  +2.9, Faydh 01 +0.5), not water: the pool's balance closes on the lumped hydrographs.
- [Certain] **Runs 3 and 4 rained on a 40 m rim round the outline** (his finding on the max depth maps, 2026-11-15).
  The domain is Basin 3's polygons + 40 m (`s01_inputs.py`), and rain falls on every active cell whose centre lies
  outside every lumped polygon. With all 104 subbasins lumped that left a band 2 cells wide: 14,250 squares and 1,139
  aligned cells, 6.18 km2, 1.42 Mm3 of rain and about 1.2 Mm3 of excess (0.6 % of the water in each run; identical in
  runs 3 and 4, whose rain books agree to 9 digits at 6.43 Mm3, the rest being the coast strip's 26.6 km2). Where the
  rim drains inward it makes the fans he saw at the west and south-west edge; where it drains outward it stands
  against the closed edge, which is the 740 small edge pools of the checks. The masks do what the engine says (aligned
  cells are masked by position like squares: 25 of 542,980 differ at polygon edges; 3 squares lie in gaps between
  polygons), so this is the job's fault, not the engine's. Effect on the dams: Bidah 03, Faydh 01 and R5A have no rim
  on their catchments; R2A has 0.02 km2; Z4C has 1.40 km2 (0.27 Mm3 of excess, under 0.7 % of its inflow). Run 3 is
  dry above Bidah 03, Faydh 01 and R5A; above Z4C 2.75 km2 was wet with 0.15 Mm3 at most, and its dam line reads no
  net flow. At the sea it is at most 1.2 Mm3 of 214. Fixed for the next run: `inputs/domain_no_rim.geojson`
  (`scripts/s16_domain_no_rim.py`: 13 cells left outside every polygon away from the coast strip, against 17,420) and
  the `rerun2_*` jobs on it (`W79_SET=rerun2`). Not run yet. On that outline the edge check opens three side lines
  (Wadi HAT's north line, Wadi Fizh's branch, the 1 km2 north stream), not five: the two 2 km2 streams at the south
  end near the sea no longer leave through it.
- The wet hill wadis outside the five dam catchments in runs 3 and 4 are the job as written, not the rim: the 86
  subbasins that drain to no dam are lumped and each enters at its own wadi outlet, 147.9 Mm3 in all, and the grid
  routes it from there. Twelve of them enter west of easting 436 km, in the hills (67.9 Mm3; Wadi HAT's eight, up to 835 m3/s), so
  Wadi HAT and its branches run on the grid from the hills down. If run 3 is to keep the hills dry, those subbasins
  must be routed by HMS's reaches to the mountain front and enter there: his decision.
- Engine, a record fault only: `entries.json` lists a wadi-outlet point, "enters at the wadi outlet of its polygon",
  for every lumped subbasin with `entry: wadi`, also for one with no outlet that is carried by an inflow below it
  (run 3's S1 to S18). No water enters there (`entries.py`, `_wanted` takes them all; `with_entries` places only real
  flows). The smallest case: one lumped subbasin with `entry: wadi`, `outlet: null`, and an inflow from the element
  below it.
- [Certain] The aligned cells' maximum speed has spikes in all three 2D runs: 1,513 to 4,846 aligned cells over 10 m/s,
  93 to 165 over 100 m/s, and a largest value of 1e7 to 7.6e8 m/s, mostly on the 'triangle' transition cells. The
  squares have 47 to 78 cells over 10 m/s. The depths and the water balance are not affected (mass errors 9e-10 to
  7e-8). The aligned cells' max speed and hazard are not usable until this is found (`maps/strip_maxima.json` per run).

### Checks

| Run | Finished | Mass error | Streams of 1 km2 or more leaving a closed edge | Edge pools over 0.01 km2 |
|---|---|---|---|---|
| 1 | yes | 9.4e-10 | none (under 1 km2: 5, the largest 0.64) | 6, the largest 0.69 km2 |
| 2 | yes (lumped, 1.2 s) | - | - | - |
| 3 | yes | 1.8e-08 | none (under 1 km2: 5, the largest 0.64) | 5, the largest 0.63 km2 |
| 4 | yes | 6.6e-08 | none (under 1 km2: 5, the largest 0.64) | 5, the largest 0.63 km2 |

The edge pools: the largest, 0.6 to 0.7 km2 and 4.7 to 4.9 m deep at (444440, 2740955), lies 1 km inside the sea line's
north end, where a 0.59 km2 stream leaves (under the 1 km2 rule; the first attempt had it too). A 0.065 km2 pool 5 to
5.7 m deep lies at (432840, 2740735), 420 m east of the north line at Wadi HAT. The rest, 740 cells, are pools of
0.001 to 0.003 km2 against the hill edges, 6 m median depth in steep cells: the rain on the 40 m rim that drains
outward (Findings). None changes a dam figure.

### Times

| Stage | Run 1 | Run 3 | Run 4 |
|---|---|---|---|
| Tables (0.5 m, built on the CPU before the run, `scripts/s08_tables.py`; peak memory) | 1,135 s, 14.6 GB | 1,018 s, 14.4 GB | shares run 1's (6.6 s) |
| Tables in the run (from the cache) | 6.0 s | 10.6 s | 5.8 s |
| Solver loop, 48 h | 2,767 s, 653,498 steps | 1,648 s, 386,196 steps | 1,843 s, 427,196 steps |
| Cell maps and series | in the loop | in the loop | in the loop |
| Pixel products, lattice ground | about 1 min | 22 s | stopped |
| Pixel products, lattice maps (193 frames) | 92 frames in 15 min, then failed: out of RAM, swapping under another worker's 325 GB pytest | about 2.5 min | stopped |
| Pixel products, strip (`strip_pixel_maxima`) | not reached | failed after about 25 min | stopped |
| Time-slider file (`wadi2d frames`, CPU) | 91 s, 2.1 GB commit | 38 s, 2.3 GB | 34 s, 2.3 GB |

The strip pixel stage (`wadi2d/strips/pixels.py`, `strip_pixel_maxima`): on run 3 `strip_ground` ran about 25 min on one
core, with no progress ticks, and the process commit rose from 128 to 240 GB. Then `StripMaxima.__init__` asked the GPU
for one 57.75 GB array (`ground.incidence`), and the step failed. Detail is in `runs/rerun_run3_hybrid_aligned.stage_times.txt`.
So the aligned mesh's pixel rasters at 0.5 m cannot be made on this machine until that stage is rebuilt. Run 4's
products were stopped on purpose (a stop file at the first products event) so that it would not repeat this. The remake
of runs 1, 3 and 4 is `scripts/s10_products.py <n> products`, which times each stage and samples the memory.

GPU: one job at a time (`scripts/s09_run.py` waits for any other engine run and for W82's driver). The wait for W82's
three jobs was 59 min (03:09 to 04:08).

### What there is to look at

- `Block2_four_ways_interim_cells.qgz` (`scripts/s11_interim_qgis.py`), in the plugin's group pattern:
  - a common group: the 5 m hillshade, the domain, the outflow lines, the dams, the HMS subbasins, the aligned cells,
    run 2's reservoir rows and `dam_peaks.csv`;
  - run 2's network, labelled with peak, time to peak and ARF;
  - per 2D run: the cell maps and, on top of them, the aligned cells' max depth, speed and hazard as polygons
    (`maps/strip_maxima.gpkg`, `scripts/s13_strip_maxima.py`); the dam lines' series; the edge checks; and the time
    sliders, all off by default.
  The light slider (`frames_light.nc`, `scripts/s14_light_slider.py`): hourly, only cells whose max mean depth reached
  0.1 m, aligned cells included; 107 to 258 MB. Headless, it loads in 1 to 3 s and draws a frame in 0.1 to 0.4 s
  (`scripts/s15_slider_render_test.py`). The full `frames.nc`: 2.3 GB, 2.9 M square cells and no aligned cells; it
  loads in 26 s and takes 0.9 s a frame. It is in a subgroup marked heavy, because turning it on hung QGIS on his PC.
- Engine products with no aligned cells (squares only, blank along the aligned wadis): the cell-map rasters
  (`maps/*.tif`), `frames.nc`, the W51 on-demand pixel layer, and the pixel rasters, which fail. `maps/strip_mesh.gpkg`
  holds max depth, level and mean depth per aligned cell, but not speed or hazard.
- Run 2 without the plugin: `run2_dam_workbook.xlsx` (`wadi2d workbook`: 200-year sheet, summaries, one sheet per dam)
  and `run2_charts/` (`scripts/s12_run2_charts.py`): the plugin's element chart drawn headless for the five reservoirs,
  FAY-J5, RIJ-J21, S13, S3 and HAT-S8.
- `Block2_four_ways.qgz` (`scripts/s06_qgis_project.py`, the final project) waits for the pixel rasters.

## The first attempt (superseded)

## The four runs of the first attempt (`jobs/` without `rerun_`, superseded)

Common to all: the 200-yr storm of his `FM_200yr.met` (251 mm, FM 10-1000yr pattern, 24 h); his ARF FM table read at
the whole block's area, Basin 3's 1,370.77 km2, which gives 0.661 and 166 mm (his met file names 300 km2, and his
depth-area analyses read each point's own area); 48 h and the 5-minute lumped step of `Control_1`. Dams start empty:
Basin 3's reservoirs at the bottom of their tables, the grid pools dry.

| Run | Job | What it is |
|---|---|---|
| 1 | `run1_full_2d_aligned.json` | Rain on every cell, no lumped element; five dams as crest lines and spillways on the grid |
| 2 | `run2_hms_lumped.json` | Basin 3 on the lumped engine alone (`scripts/s03_lumped.py`): 104 subbasins, the Muskingum-Cunge reaches, the five reservoirs. No 2D run, because with every element lumped no water reaches the grid. Series of every element as `series/network_<element>.csv` |
| 3 | `run3_hybrid_aligned.json` | S1 to S18 lumped with their reaches and the five reservoirs. Each reservoir's outflow enters 200 m below its dam. The 86 plain subbasins are lumped, each entering at its own wadi outlet. Rain on the grid only outside every polygon |
| 4 | `run4_hybrid_2d_routing_aligned.json` | All 104 subbasins lumped and entering at their wadi outlets. No reach or reservoir is routed; the five dams are 2D pools, as in run 1 |

2D runs: the aligned centre mesh at 20 m (`strips.generator: centres`, his decision of 2026-11-14). The guide lines
are the 1 km2 thalwegs of this domain's own Suggest breaklines file. The plain is n 0.04 and the hill subbasins off the
wadis are n 0.1 (W1's rule). His CN raster, with CN 88 (W1's value) on the 0.4 % of cells where it holds no data, mostly
in the coast strip. Maps every 15 min. Lines: W1's five dam lines, plus a line round each pool's upstream edge for
the inflow. Pixel maps on; polygons and the depth drawing off.

## Inputs (`inputs/`, `scripts/s01_inputs.py`)

- **Domain to the sea, 1,406.1 km2** (`inputs/domain.geojson`). No existing Block 2 job reaches the coast: W1, W41
  and W49 stop at a box 5 to 13 km short of it. This domain is Basin 3's 104 polygons + 40 m. Those polygons stop 0.1
  to 2.6 km short of W12's coastline, so the 26.7 km2 strip up to that coastline is added.
- **Boundaries:**
  - The sea: W12's coastline, 26.8 km, `normal` 0.003.
  - Four side outlets where the engine's edge check (W78) found a stream of 1 km2 or more leaving through a side, each
    `normal` 0.005 [Guessing: the fan slope]. The largest is Wadi Fizh's southern branch, 274.7 km2, leaving 2 km
    inland through Basin 3's south-east edge.
  - The north edge at (432446, 2740899), his decision: a `normal` line at 0.0057, the ground's slope along HAT-R4. This
    is Wadi HAT's main stem, 276.65 km2, where Basin 3's outline runs on a 107 to 110 m terrace beside the bed and the
    HDSM ends just outside it. In the squares run the edge there held a pool 5.1 m deep (0.092 km2) at (432881,
    2740716). With the line, the aligned run 1 has none.
  - The pre-run check on the final jobs reports no stream of 1 km2 or more leaving.
- **Dams on the GGC terrain** (`inputs/dams.geojson`, `inputs/dam_check.json`):
  - Bidah 03 and Faydh 01: W1's crest lines, dikes and spillways, with the dam team's NSA levels moved +2.39 m.
  - R5A, R2A and Z4C: the axes of `Det_Design_DAMS.shp`, with the levels that Basin 3's tables imply, not moved (their
    tables were cut from the HDSM). Spillway crest / dam crest: R5A 143 / 146, R2A 162 / 165, Z4C 167 / 170 m.
    Spillways: R2A 75.3 + 84.7 m and R5A 141.5 + 108.5 m on two wadi branches each [Guessing: which chute is on which
    branch], Z4C one of 220 m.
  - [Certain] The DEM pool at the spillway crest, behind these lines, holds 0.99 to 1.012 of Basin 3's table volume at
    all five dams. That confirms both the datum shift and the geometry.

## Results of the first attempt (superseded)

**Run 2, full HMS way** (Basin 3 on the lumped engine, 0.3 s; levels on each table's own datum, NSA for Bidah 03 and
Faydh 01):

| Dam | Inflow peak m3/s | at h | Inflow Mm3 | Outflow peak m3/s | at h | Outflow Mm3 | Highest pool m |
|---|---|---|---|---|---|---|---|
| Bidah 03 | 291 | 12.75 | 2.72 | 0 | - | 0.00 | 95.88 |
| Faydh 01 | 846 | 13.25 | 10.28 | 0 | - | 0.00 | 222.11 |
| R5A | 767 | 14.92 | 15.84 | 286 | 17.58 | 6.44 | 143.66 |
| R2A | 1,226 | 14.33 | 23.65 | 310 | 18.42 | 8.60 | 162.96 |
| Z4C | 1,546 | 15.67 | 28.81 | 1,458 | 16.08 | 24.24 | 169.18 |

**Run 1 on plain 20 m squares, superseded** (`runs/run1_full_2d`, 3,509,086 cells, 0.5 m sub-grid, solver 1,956 s,
mass error 1.0e-8). It was replaced on his decision of 2026-11-14 by the aligned centre mesh. It also had no line at the
north edge. Its pixel maps were stopped. Inflow is read on the line round each pool, without the rain that falls inside
that line; outflow is read on the dam line.

| Dam | Inflow peak m3/s | at h | Inflow Mm3 | Outflow peak m3/s | at h | Outflow Mm3 |
|---|---|---|---|---|---|---|
| Bidah 03 | 404 | 12.39 | 2.40 | 0 | - | 0.00 |
| Faydh 01 | 1,435 | 12.18 | 9.97 | 0 | - | 0.00 |
| R5A | 1,376 | 12.76 | 15.13 | 242 | 13.41 | 6.08 |
| R2A | 2,402 | 12.81 | 22.97 | 261 | 16.77 | 8.33 |
| Z4C | 2,085 | 13.96 | 28.34 | 1,910 | 14.34 | 23.92 |

As on Block 2 since W1, the full-2D inflow peaks are 1.35 to 1.96 times HMS's and come 0.4 to 2.2 h earlier, with the
volumes 2 to 12 % lower.

**Run 1 on the aligned mesh, stopped after the solver** (`runs/run1_full_2d_aligned`, `pixel_stride` 2 = 1 m):
2,941,116 cells, 401 lines with aligned cells, 189,406 cells on them; tables 1,493 s, solver 2,711 s, mass error
7.5e-9. Inflow / outflow peaks, m3/s: Bidah 03 416 / 0, Faydh 01 1,573 / 0, R5A 1,295 / 302, R2A 2,523 / 273,
Z4C 2,348 / 2,147. To be rerun at 0.5 m, so these are not for use.

## What failed and was stopped, in order

1. Run 1, first try (`runs/try1_run1_refused_cn`): refused because his CN raster gives no CN on 14,561 cells. The fix
   is CN 88 where it has none. The same try's edge check found Wadi Fizh's branch leaving the south-east side, which
   is why the side outlets were added.
2. Run 1 on squares (`runs/run1_full_2d`): finished, then superseded by the aligned mesh. Before its end, the
   coordinator asked for a line at the north edge. I held off, reading the bed (103 to 105 m, inside the outline) as
   not dammed. The squares run showed 0.56 m on the outline at the crossing itself, but a 5.1 m pool 450 m along the
   edge. So the line he decided on was needed.
3. Run 1 aligned at 0.5 m (`runs/try3_run1_aligned_memory`): exit 7. The strip's table builder reads the DEM over the
   bounding box of every aligned cell at once in float64: 91,457 x 97,537 pixels, 66.5 GiB. At `pixel_stride` 2 it
   ran.
4. Run 1 aligned, pixel maps: the products step stopped with "shape mismatch (…,5) against (…,4)". The strip's pixel
   ground padded every cell to 4 nodes, and the centre mesh has 5- to 9-sided cells. Fixed and committed separately
   (`bdbb7f5`, with a test of a pentagon cell; the strip pixel and product tests 33 of 33). The remake was stopped on
   his word at 60 % (all 193 maps done) and is not finished. The time-slider file was not made.
5. The edge-pool check after the aligned run lists 338 places more than 40 m from the real outline, 43 of them over
   0.01 km2. Among them are the dam pools against the crest lines' aligned cells. [Likely] the check counts the squares
   next to the strip's cells as a closed edge. On the real outline the aligned run has 4 pools over 0.01 km2 (the
   squares run had 5); the largest is 4.5 m deep, 0.59 km2, at (444441, 2740956), 1 km inside the sea line's north end,
   where a 0.59 km2 stream (under the 1 km2 rule) leaves.

## Scripts

`s01_inputs.py` builds the domain, boundaries, Manning raster and dams. `s02_jobs.py` builds the rerun's four jobs
(`jobs/rerun_*`, the ARF rules above), the side and north outlets, and the Suggest file; the first attempt's jobs were
made by its earlier version (git history). `s03_lumped.py` is run 2, each element at its own area. `s04_check.py <n>`
checks a run: finished, mass, warnings, the edge check's streams leaving, setup (storm areas included), dam inflow and
outflow. `s05_dam_peaks.py` writes `dam_peaks.csv` with the ARF area and factor of each dam. `s06_qgis_project.py`
builds the final headless QGIS project in the plugin's group pattern (it needs the pixel rasters);
`s11_interim_qgis.py` builds the interim one from what exists. `s07_tree.py` prints a project's tree. `s08_tables.py <n>`
builds a job's grid tables into the cache on the CPU, timed. `s09_run.py <n>` runs a job on the GPU once no other
engine run holds it, then checks it. `s10_products.py <n> [products|frames|both]` remakes products or the time-slider
file, timing each stage and sampling memory. `s12` to `s15` are the run 2 charts, the aligned-cell maxima, the light
slider and its timing test. `s16_domain_no_rim.py` writes the domain without the rim; every script works on the set
named by `W79_SET` (`rerun`, the default, or `rerun2`). Run outputs are in `runs/` (out of git).
