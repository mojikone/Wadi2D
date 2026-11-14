# W55 HMS PMF against gridded PMP with ARF

**Live.** Branch `feature/hms-pmf-compare` off `feature/fast-products` at `1c2922d`; not merged, nothing pushed.

His words: "Update the test. Dams reservoir are added. You can test the reservoir routing. Currently HMS does not apply
ARF on dss grid. I need you to compare PMF from HMS with the runs with DSS grid with ARF applied." Refined the same day
into two tests: test 1, Wadi2D with exactly HMS's PMF rain against HMS everywhere it can be read; test 2, per dam, HMS
with one lumped PMP depth and pattern taken from the DSS PMP grid and ARF as HMS applies it, against Wadi2D on the
distributed DSS grid with ARF at the same dam's drainage area.

**The headline.** Test 1 is settled: Wadi2D reproduces HMS's PMF and 100-yr runs of Basin 3 to round-off at every
subbasin, reach, junction and reservoir but two short reaches, whose 0.01 to 1.9 % is HMS giving them a grid its own rule
does not give (proved, the trigger narrowed below). Test 2: on these five catchments the lumped-depth-with-ARF practice
and the distributed grid with ARF give the same dam floods within 0.3 % (peak) and 3 mm (pool), because the PMP grid
is almost uniform over each catchment. **What separates the HMS PMF from the grid runs is the rain itself: HMS's PMF
storm puts 1,013 to 1,370 mm on the dam catchments, the DSS PMP grid 435 to 493 mm after the same ARF, a factor of 2.3
to 2.8; the dam inflow peaks are 49 to 63 % lower on the grid.** ARF on the grid removes 2.5 to 13.9 % of the rain,
2.6 to 14.5 % of the inflow peak and 10 to 19 % of the outflow peak.

## What changed in his HMS project (2026-11-11)

[Certain, read from the files] The project `HEC_HMS_Block_02` now holds three basin models, each with its own 13
depth-area analyses on the FM storms (`FM_<T>.met`, specified 24 h patterns, ARF FM, storm area set to each point's
drainage area):

| Analyses | Basin model | What it is (his descriptions) | Points |
|---|---|---|---|
| `DA <T> B1` | Basin 1 | the 18 dam-catchment subbasins and 8 reaches, unchanged | 40 |
| `DA <T> B2` | Basin 2 | "Basin 1 dam catchments + Block 2 channel network (W12 flow points)": 104 subbasins, 71 reaches, 101 junctions | 91 |
| `DA <T> B3` | Basin 3 | "Basin 2 + the five dam reservoirs (empty at the start; spillway + dam overtopping)" | 97, the five reservoirs among them |

The reservoirs are `Modified Puls` on `Elevation-Area-Outflow` tables (`Elev-Area <dam>`, `Elev-Dis <dam>` in the
project's paired data), elevation-area primary, `Initial Elevation` at the bottom of each table: empty, as Wadi2D
starts a dam by default since W34; the comparison uses HMS's own setting. Results: `DA_<T>_B2.dss`, `DA_<T>_B3.dss`,
`results\DAA_DA_<T>_B<n>.results`; the `FM_<T>.dss` simulation runs still run Basin 1. The PMF of the project is
`DA PMP B3` (or `B1`/`B2` at the dam junctions, identical upstream): `FM_PMP.met` is a Precipitation-Frequency Grid
storm on the raster `Clip_PMP_823mm_21c_27032024.tif`, the depth averaged over each point's catchment, the FM PMP
pattern, ARF FM at the point's area. It is not the DSS PMP grid of `Hydrology\Grid\DSS`.

The old test failed for one reason in the engine: ten Basin 2 and 3 subbasins of 0.35 to 1.35 km2 hold no centre of the
958 m PMP raster, and three analysis points have nothing else above them. HMS logged for each the depth of the cell
nearest the centroid of their polygons (BID-J17 1,521.262 mm, BID-J19 and BID-J45 1,515.828 mm, to 0.001 mm);
BID-J45's two polygons read one cell, not one each, and where any centre lies in the polygons an empty one adds
nothing (the other 94 points). That rule is now in `DepthGrid` [Likely: fitted on three points, all consistent].

## How the tests now check it

- `tests/hydrology/test_block2_replication.py`: all 39 analyses, 2,964 points, peaks within 2 % (whole basin) and 1 %
  (dam sites), every peak within one step, the PMP depth HMS logged at every point of each basin model's PMP analysis
  to 0.001 mm (40, 91, 97 points), and the five reservoirs' outflow of record at 100 yr and PMP to 0.01 m3/s and the
  same step. Tolerances unchanged. The report `W1 .../validation/hms_replication.md` is rewritten by it.
- `tests/hydrology/test_block2_reservoirs.py` (new): every pool starts at the bottom of its table; HMS's own inflow
  routed through each reservoir gives HMS's outflow, storage and level at PMP and 100 yr to 1e-6.
- `tests/hms/test_hms_block2.py`: the readers on the new project (counts, Basin 3's reservoirs read with nothing
  unknown).
- `tests/hydrology/test_replication_rules.py`: the test that a polygon holding no cell centre raises became the rule
  above; a centroid more than a cell spacing from every wet centre (off the grid, or a raster in another coordinate
  system, Majlas's failure) still raises, and both tests say so.

## Test 1: identical rain, Basin 3

Wadi2D reran `DA PMP B3` and `DA 100yr B3` point by point, each point's sub-network under HMS's storm at that point's
area, and every element above every point was compared with HMS's DSS record for that point (`scripts/series_check.py`):
926 outflow series per storm (371 subbasin, 332 junction, 200 reach, 23 reservoir), plus the reservoirs' inflow, storage
and level.

| Storm | Series | Worst series difference, share of its peak | Worst peak | Volume | Peak time |
|---|---|---|---|---|---|
| PMP | 918 outflows outside the two reaches below | 3.2e-5 | -0.0001 % | 3e-6 | same step |
| 100 yr | 918 outflows outside the two reaches | 3.7e-5 | +0.0007 % | 4e-6 | same step |
| PMP | 23 reservoir inflows, storages, levels | 4.9e-7, 2.8e-7, 4.1e-6 | 0.0000 % | | same step |
| 100 yr | 23 reservoir inflows, storages, levels | 3.8e-6, 1.1e-6, 3.2e-6 | 0.0000 % | | same step |
| PMP | RIJ-R11, RIJ-J21 | 5.1e-3 | -0.013 % | 2e-5 | same step |
| 100 yr | RIJ-R17 and the three below it | 6.9e-3 | +0.055 % | 2e-6 | same step |

(The storage and level "time of peak" of Bidah 03 and Faydh 01 at 100 yr differs by up to 16 steps only because the
pool holds flat at its maximum with no spill; the values agree to 1e-6.)

**The one difference beyond round-off, traced.** On `RIJ-R11` (227.9 m) and `RIJ-R17` (400.1 m) HMS logged two cells
and twice the sub-steps (75 s, 113.95 m; 150 s, 200.05 m), where the rule Wadi2D carries, `N = ceil(L / (c dt))` and
`k = round(N c dt / L)`, gives one cell (150 s; 300 s), and where the same rule agrees with HMS on the other 69 reaches
of Basin 3 (and 8,390 reach runs of Blocks 2, 4, 6 and Majlas, W1). Routed on HMS's logged grid, the two reaches match
HMS to 5e-4 m3/s, and all 26 Basin 2 and 3 analyses then match to 0.004 % at every point with no step slip
(`scripts/logged_grid_replication.py`, `results/logged_grid_replication.json`); with the rule they read up to +1.93 %
at RIJ-J20 on the 5-yr flood, the worst point of the whole replication, inside the 2 % gate. What makes HMS double the
grid was hunted in HMS itself on a copy of the project (below); it is not in the slope, the width, Manning's n or the
reach below, but in the length.

In HMS 4.12 itself (headless, as in test 2), on variants of Basin 3 (`scripts/probe_reach_grid.py`,
`results/probe_reach_grid.json`): RIJ-R17 keeps two cells with its slope at 0.01, its width at 20 m, its n at 0.04, or
the reach below it lengthened; it drops to the rule's one cell at 300 m; RIJ-R11 keeps two with its width or slope
changed; BID-R24, one cell at its own 237.4 m, takes two at 400.1 m. A sweep of BID-R24's length alone
(`scripts/sweep_reach_length.py`, `results/sweep_reach_length.json`, 41 lengths from 60 to 1,000.1 m) follows the rule
at every length but three: **227.9, 239.9 and 400.1 m give two cells and twice the sub-steps, where 227.8, 228.0,
240.0, 240.1, 399.9, 400.0, 400.2, 400.5 and 400.9 m give the rule's grid.** [Likely] So it is not a hydraulic
criterion but a round-off artefact inside HMS's choice of grid at isolated lengths; nothing in its inputs predicts it
short of reproducing HMS's floating-point arithmetic, which is not known. (HMS also logs WARNING 41084, "applying the
diffusivity criteria ... would have increased spatial steps from 2 to 4" on RIJ-R11 and the like on many reaches; it
says "would have" and is not applied, and the base count it quotes, 2, is already the doubled one.) Wadi2D keeps its
rule; the effect is at most 0.064 % on any peak from 10 yr to PMP, and 1.2 and 1.9 % on the 2- and 5-yr peaks at
RIJ-J20, a channel point below the dams (no dam site is affected).

## Reservoir routing, Basin 3 against HMS

HMS's own numbers (`DA_PMP_B3.dss`, `DA_100yr_B3.dss` at each reservoir's own analysis point); Wadi2D's whole chain
(rain, losses, unit hydrographs, reaches, reservoir) gives them to the last columns' differences, and the reservoir alone
on HMS's inflow to 1e-11 m3/s and 1e-13 m (`scripts/reservoirs.py`, `results/reservoirs.json`). Every pool starts
empty at the bottom of its table.

| Run | Dam | Peak inflow | Peak outflow | Attenuation % | Peaks at, h (in / out) | Volume in / out, Mm3 | Max pool, m | Wadi2D chain: max outflow diff, m3/s | max level diff, m |
|---|---|---|---|---|---|---|---|---|---|
| DA PMP B3 | Bidah 03 | 1,688.4 | 1,477.2 | 12.5 | 12.83 / 13.50 | 27.85 / 22.27 | 104.570 | 1e-12 | 3e-14 |
| DA PMP B3 | Faydh 01 | 4,859.6 | 4,830.4 | 0.6 | 13.33 / 13.50 | 87.25 / 70.76 | 234.902 | 1e-04 | 2e-06 |
| DA PMP B3 | R2A | 9,107.1 | 9,091.1 | 0.2 | 13.92 / 14.00 | 190.15 / 175.10 | 166.277 | 2e-03 | 1e-05 |
| DA PMP B3 | R5A | 6,572.3 | 6,558.8 | 0.2 | 13.92 / 14.08 | 132.72 / 123.33 | 146.784 | 4e-04 | 6e-06 |
| DA PMP B3 | Z4C | 9,500.0 | 9,490.6 | 0.1 | 15.00 / 15.08 | 206.88 / 202.31 | 172.256 | 1e-03 | 1e-05 |
| DA 100yr B3 | Bidah 03 | 362.4 | 0.0 | 100.0 | 12.75 / - | 3.41 / 0.00 | 97.038 | 0 | 1e-14 |
| DA 100yr B3 | Faydh 01 | 993.5 | 0.0 | 100.0 | 13.25 / - | 12.12 / 0.00 | 224.632 | 0 | 6e-06 |
| DA 100yr B3 | R2A | 1,356.1 | 433.8 | 68.0 | 14.25 / 17.67 | 26.04 / 10.99 | 163.193 | 6e-04 | 4e-04 |
| DA 100yr B3 | R5A | 887.1 | 428.9 | 51.6 | 14.75 / 16.83 | 18.10 / 8.71 | 143.874 | 6e-04 | 8e-05 |
| DA 100yr B3 | Z4C | 1,666.4 | 1,583.2 | 5.0 | 15.58 / 16.00 | 31.04 / 26.47 | 169.303 | 3e-03 | 9e-05 |

Read: at 100 yr Bidah 03 and Faydh 01 hold the whole flood inside the 48 h window and spill nothing; at PMP every dam is
full and passes almost the whole peak (0.1 to 0.6 % attenuation), Bidah 03 alone 12.5 %. Nothing in the reader or the
routing needed a fix. Added: `ReservoirOutflowCurve.pool`, the storage and level of a routed series, from the step's own
mass balance.

## Test 2: lumped PMP depth with ARF in HMS against the distributed grid with ARF in Wadi2D

**How HMS was run.** HEC-HMS 4.12 (`C:\Program Files\HEC\HEC-HMS\4.12`) headless, no window: its own Jython entry
point `hms.Hms -s <script>` started with the java, class path and library path of its `HEC-HMS.cmd`
(`scripts/run_hms.ps1`; the `.cmd` itself would not start from this shell), the script calling
`OpenProject("HEC HMS Block 02", <copy>)` and `ComputeRun(<run>)` of `hms.model.JythonHms`. On a copy of his project
inside this folder (`_work/hms_project`, outside git): `Basin_3.basin` and `.sqlite`, `Control_1.control`, the pdata and
project DSS, and five new met models and runs written by `scripts/build_hms_runs.py`. Each is set up as his depth-area
runs set up a point: Hypothetical Storm, Point Depth = the mean depth of the DSS PMP grid over the dam's catchment,
Specified Pattern = that catchment's own cumulative pattern from the same DSS (a 145-ordinate Percent Graph, the form of
his FM PMP pattern), 24 h, Storm Area = the dam's drainage area, User-Specified ARF FM, Uniform Depth Yes, Basin 3 with
its reservoirs, Control 1. HMS logged, for Faydh 01, "Hypothetical storm depth ... 489.937 MM; Area-reduced
hypothetical storm depth: 456.125 mm", the depth and factor computed here. His folder was not touched. The two "could not
load grid" messages of each session are the PMP raster and CN grid named in the project's `.grid` file and not copied;
no run uses them.

**The rain.** From `Precipitation_PMP_10min.dss` (144 frames of 10 min, read by Wadi2D's DSS reader): each subbasin's
pixel mean, every pixel weighted by the area it shares with the subbasin's polygon (the engine's lumped reading), and the
catchment's series as the polygon-area-weighted mean of its subbasins'. Wadi2D's side keeps each subbasin's own series
(distributed) and multiplies every frame by ARF FM at the dam's drainage area (W53's gridded ARF).

| Dam | Area, km2 | ARF FM | Grid over the catchment, mm | after ARF, mm | Subbasins' own grid depth, mm | Wettest 1 h / 6 h, share of the day |
|---|---|---|---|---|---|---|
| Bidah 03 | 20.97 | 0.9749 | 505.8 | 493.1 | 505.8 (one subbasin) | 0.378 / 0.679 |
| Faydh 01 | 74.30 | 0.9310 | 489.9 | 456.1 | 489.2 to 490.8 | 0.385 / 0.685 |
| R2A | 175.87 | 0.8758 | 508.3 | 445.2 | 502.6 to 538.4 | 0.377 / 0.678 |
| R5A | 117.10 | 0.9046 | 502.2 | 454.3 | 494.7 to 529.0 | 0.380 / 0.680 |
| Z4C | 211.09 | 0.8607 | 505.6 | 435.2 | 493.9 to 530.0 | 0.378 / 0.679 |

The ARF removes 12.7 mm (2.5 %) of Bidah 03's rain, 33.8 mm (6.9 %) of Faydh 01's, 63.1 mm (12.4 %) of R2A's, 47.9 mm
(9.5 %) of R5A's and 70.4 mm (13.9 %) of Z4C's.

**The comparison at each dam** (`scripts/pmf_compare.py`, `results/pmf_compare.json`):

| Dam | HMS lumped + ARF: peak in / out, m3/s | Wadi2D distributed + ARF: peak in / out | Difference in / out, % | Pool, m | Peak times in / out, h | Volume in / out, Mm3 (both) |
|---|---|---|---|---|---|---|
| Bidah 03 | 865.5 / 187.5 | 865.5 / 187.5 | 0.00 / 0.00 | 101.154 / 101.154 | 12.92 / 14.83, same | 9.49 / 3.90 |
| Faydh 01 | 2,325.8 / 1,214.6 | 2,325.9 / 1,214.7 | +0.00 / +0.01 | 231.977 / 231.977 | 13.33 / 14.58, same | 31.67 / 15.18 |
| R2A | 3,599.3 / 3,398.2 | 3,597.4 / 3,398.1 | -0.05 / -0.01 | 165.437 / 165.437 | 14.00 / 14.50, same | 72.23 / 57.18 |
| R5A | 2,417.6 / 2,216.8 | 2,410.1 / 2,213.1 | -0.31 / -0.17 | 145.650 / 145.647 | 14.42 / 14.92, same | 49.26 / 39.87 |
| Z4C | 4,150.0 / 4,131.0 | 4,140.6 / 4,121.8 | -0.23 / -0.22 | 170.766 / 170.763 | 15.25 / 15.42, same | 85.08 / 80.51 |

The code check of the set-up: Wadi2D run with HMS's lumped storm reproduces each HMS run to 3e-3 m3/s and 3e-4 m.
So the columns differ only by lumping the grid: on these catchments the grid varies by at most 7 % between subbasins
and its pattern is the same everywhere, so spreading one mean depth and one mean pattern over the catchment changes the
peaks by under 0.3 % and the pools by 3 mm (why the distributed run is the lower one on three catchments was not
looked at). For these dams and this grid the HMS practice loses nothing; [Likely] on a storm with real spatial
structure it would.

## The PMF at the five dams, (a) to (d)

| Dam | Case | Rain, mm | Peak inflow, m3/s | at, h | Peak outflow, m3/s | at, h | Volume in / out, Mm3 | Max pool, m |
|---|---|---|---|---|---|---|---|---|
| Bidah 03 | (a) HMS PMF (DA PMP B3) = (b) Wadi2D on it | 1,370.4 | 1,688.4 | 12.83 | 1,477.2 | 13.50 | 27.85 / 22.27 | 104.570 |
| | (c) Wadi2D, DSS grid + ARF | 493.1 | 865.5 | 12.92 | 187.5 | 14.83 | 9.49 / 3.90 | 101.154 |
| | (d) Wadi2D, DSS grid, no ARF | 505.8 | 888.6 | 12.92 | 208.3 | 14.75 | 9.75 / 4.17 | 101.238 |
| Faydh 01 | (a) = (b) | 1,205.0 | 4,859.6 | 13.33 | 4,830.4 | 13.50 | 87.25 / 70.76 | 234.902 |
| | (c) | 456.1 | 2,325.9 | 13.33 | 1,214.7 | 14.58 | 31.67 / 15.18 | 231.977 |
| | (d) | 489.9 | 2,504.5 | 13.33 | 1,495.5 | 14.33 | 34.17 / 17.69 | 232.278 |
| R2A | (a) = (b) | 1,117.0 | 9,107.1 | 13.92 | 9,091.1 | 14.00 | 190.15 / 175.10 | 166.277 |
| | (c) | 445.2 | 3,597.4 | 14.00 | 3,398.1 | 14.50 | 72.23 / 57.18 | 165.437 |
| | (d) | 508.3 | 4,165.2 | 13.92 | 4,089.1 | 14.25 | 83.28 / 68.23 | 165.570 |
| R5A | (a) = (b) | 1,168.2 | 6,572.3 | 13.92 | 6,558.8 | 14.08 | 132.72 / 123.33 | 146.784 |
| | (c) | 454.3 | 2,410.1 | 14.42 | 2,213.1 | 14.92 | 49.26 / 39.87 | 145.647 |
| | (d) | 502.2 | 2,702.7 | 14.42 | 2,508.6 | 14.83 | 54.85 / 45.45 | 145.879 |
| Z4C | (a) = (b) | 1,013.3 | 9,500.0 | 15.00 | 9,490.6 | 15.08 | 206.88 / 202.31 | 172.256 |
| | (c) | 435.2 | 4,140.6 | 15.25 | 4,121.8 | 15.42 | 85.08 / 80.51 | 170.763 |
| | (d) | 505.6 | 4,843.6 | 15.25 | 4,826.9 | 15.33 | 99.88 / 95.31 | 171.009 |

(a) is HMS's result of record; (b) equals it to round-off (test 1). (a) and (c) use the same ARF at the same area, so
ARF is not what separates them. The hybrid and full 2D runs of (c) were not made (below).

## What explains the differences

1. **The rain, almost all of it.** HMS's PMF reads the PMP raster `Clip_PMP_823mm...`: 1,177 to 1,406 mm over these
   catchments before ARF (W39 found 1,405 mm over S13; the "823 mm" is only the file's name). The DSS PMP grid holds
   490 to 508 mm (W53: 1.5 x its RP10000 grid, capped at 1,500 mm). Same ARF, so after it 1,013 to 1,370 mm against
   435 to 493 mm, 2.3 to 2.8 times. The inflow volume follows at 2.4 to 2.9 times (the SCS losses take a larger share
   of the smaller rain) and the inflow peak at 1.9 to 2.7 times.
2. **The time pattern, secondary and the other way.** The grid puts 38 % of its day in the wettest hour and 68 % in
   the wettest six; the FM PMP pattern 23 % and 80 %. The grid's depth on the FM PMP pattern (the "split" rows of
   `results/pmf_compare.json`) gives inflow peaks 31 % lower than (c) at Bidah 03 and 22 % at Faydh 01, 3 and 4 % at
   R2A and Z4C, the same at R5A: the grid's sharp hour matters on the small fast catchments. So the 49 to 63 % drop of
   the inflow peak from (a) to (c) is the depth, partly offset by the pattern on the small catchments.
3. **ARF, (c) against (d).** The same table both ways; on the grid it removes 2.5 to 13.9 % of the rain, 2.6 to
   14.5 % of the inflow peak, 2.7 to 14.8 % of the inflow volume, 10.0 to 18.8 % of the outflow peak (the pool
   magnifies the cut most at Faydh 01 and R2A) and 0.08 to 0.30 m of the pool. That is what running the grid in HMS
   without ARF overstates, on this grid.
4. **The method, lumped against distributed:** under 0.3 % (test 2).

## Not done, and for his decision

- **Which PMP is the design PMP**: the raster HMS's PMF reads (about 1,200 to 1,400 mm over these catchments) or the
  DSS PMP grid (about 500 mm). They differ by 2.3 to 2.8 times; nothing here decides between them.
- The hybrid and full 2D runs of (c) on Basin 3: not made. The GPU was not used in this work.
- The trigger of HMS's doubled reach grid (above): Wadi2D keeps its rule; carrying an exception for two reaches
  without the rule behind it would be a guess.
- No full suite run (the coordinator's). `tests/hms tests/hydrology tests/storm tests/engine`, 898 tests collected,
  pass on the last commit (exit 0, no failure); on the way they caught the three tests of the old refusal, now changed
  as above.

## Files

`scripts/`: `series_check.py` (test 1, every series), `reservoirs.py`, `logged_grid_replication.py`,
`reach_grid_check.py` and `reach_features.py` (the reach grid against the logs), `probe_reach_grid.py` and
`sweep_reach_length.py` (HMS itself on variants), `pmf_wadi2d.py` (the grid's catchment rain, the Wadi2D side and the HMS
inputs), `build_hms_runs.py`, `run_hms.ps1`, `pmf_compare.py`, `rain_shape.py`, `tables.py`. Numbers in `results/`.
`_work/` holds the copies of his DSS results and the HMS project copy with its runs (outside git).
