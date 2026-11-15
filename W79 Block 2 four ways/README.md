# W79 Block 2 four ways

**Interim, stopped on his decision of 2026-11-15 01:50.** Of the four runs, run 2 (full HMS way) is done. Run 1 (full
2D) ran twice: on plain 20 m squares (finished, now superseded) and on the aligned centre mesh at 20 m (the solver
finished; the pixel maps and time-slider file were stopped). Runs 3 and 4 have not been run. The engine is being fixed
for the aligned mesh on this domain (the strip's whole-window DEM reads, the strip mesh cache, the products' ground
read, the edge check on strip joins). After that merge, runs 1, 3 and 4 are rerun on the aligned mesh at the full
0.5 m pixel (`pixel_stride` 1). Nothing quoted below is a design figure. `dam_peaks.csv` and `Block2_four_ways.qgz` are
not made yet: they wait for the reruns.

## The four runs (`jobs/`, written by `scripts/s02_jobs.py`)

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

## Results so far

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

`s01_inputs.py` builds the domain, boundaries, Manning raster and dams. `s02_jobs.py` builds the four jobs, the side
and north outlets, and the Suggest file. `s03_lumped.py` is run 2. `s04_check.py <n>` checks a run: finished, mass,
warnings, setup, dam inflow and outflow. `s05_dam_peaks.py` writes `dam_peaks.csv`. `s06_qgis_project.py` builds the
headless QGIS project in the plugin's group pattern, with the aligned cells shown. `s07_tree.py` prints a project's tree.
A test pass of s06 on the squares run gave 35 layers, none invalid. Run outputs are in `runs/` (out of git): the squares
run 13 GB, the aligned run 1 11 GB, the grid cache 3.7 GB.
