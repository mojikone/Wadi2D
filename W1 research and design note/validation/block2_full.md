# Block 2 whole-catchment validation (2026-11-01)

**Verdict: reach routing and dams pass, rain-on-grid does not reproduce HMS. Mode (b) matches the HMS peaks within 3 % when it uses HMS's own reach Manning 0.1. Both dams route within 1.6 % of Modified Puls. Mode (c) carries the right volume but peaks at 1.4 to 2.1 x HMS, 0.2 to 2.0 h early, and no defensible Manning closes that gap. Which of the two is right cannot be decided without an observed flood.**

The engine was frozen at commit `3f32ca6` for every number below, because the code tree was being edited during this work. Key cases rerun on `63d580c` moved by 0.3 % or less (section 6). No change was made to `wadi2d/`. Everything is in `validation\block2_full\`: jobs in `jobs\`, runs in `runs\`, scripts in `scripts\`.

## 1. Modes at the five dam sites, 100-yr

Each site is read from the run at its own storm area, through the extended dam axis. Each cell gives peak m3/s, time h, volume Mm3, then peak ratio / volume ratio to HMS. Runs last 36 h, HMS volumes 48 h. Mode (c) has wadis at n 0.04, hills at n 0.1. Storm 205.4 mm, per-cell CN from the project raster. Domain 811 km2, 2,025,556 cells at 20 m. [Certain, read from the run folders]

| Site, storm area km2 | HMS | (b) wadi n 0.04 | (b) n 0.1, HMS's reach value | (c) rain-on-grid, 20 m |
|---|---|---|---|---|
| Faydh 01, 74.3 | 993, 13.25, 12.12 | 1009, 13.21, 12.14: 1.02 / 1.002 | 992, 13.24, 12.13: 1.00 / 1.001 | 1803, 12.28, 12.08: **1.81** / 0.997 |
| Bidah 03, 21.0 | 362, 12.75, 3.41 | 361, 12.76, 3.42: 1.00 / 1.002 | 359, 12.82, 3.42: 0.99 / 1.001 | 528, 12.51, 3.26: **1.46** / 0.956 |
| R5A, 117.1 | 887, 14.75, 18.10 | 1119, 13.91, 18.08: 1.26 / 0.999 | 903, 14.68, 18.02: 1.02 / 0.995 | 1736, 12.78, 17.76: **1.96** / 0.981 |
| R2A, 175.9 | 1356, 14.25, 26.04 | 1496, 13.72, 26.02: 1.10 / 0.999 | 1395, 14.26, 25.97: 1.03 / 0.997 | 2820, 12.89, 25.73: **2.08** / 0.988 |
| Z4C, 211.1 | 1666, 15.58, 31.04 | 1733, 14.91, 30.97: 1.04 / 0.998 | 1653, 15.66, 30.79: 0.99 / 0.992 | 2316, 13.91, 30.62: **1.39** / 0.987 |

Mode (b) here means all 18 subbasins lumped, hydrographs at the wadi outlet of each polygon, reaches and plain in 2D. Bidah has no reach above the dam, so its row only tests the injection. S13's outlet was moved up to the wadi above the axis, because the accumulation rule placed it on the axis itself.

A closed ring around each catchment agrees with the axis within 0.1 % on peak at Faydh, R5A, R2A and Z4C, so no flow escapes those polygons. At Bidah the ring reads 1.49 / 0.997: about 4 % of S13 lies past the axis and never crosses it [Likely].

### Sensitivity, one storm area (74.3 km2), peak ratio to the lumped engine at that area

The lumped engine stands in for HMS here; it matches HMS within 0.002 %. These runs are sensitivity only, not calibration.

| Run | Faydh | Bidah | R5A | R2A | Z4C | Time of peak, h |
|---|---|---|---|---|---|---|
| Lumped, m3/s | 993 | 344 | 922 | 1464 | 1826 | 13.25, 12.75, 14.75, 14.25, 15.50 |
| n 0.04 everywhere | 1.96 | 1.77 | 2.15 | 2.15 | 1.53 | 12.18, 12.28, 12.51, 12.59, 13.39 |
| Hills 0.05, wadis 0.04 | 1.93 | 1.70 | 2.12 | 2.14 | 1.51 | 12.19, 12.32, 12.56, 12.62, 13.46 |
| Hills 0.1, wadis 0.04 | 1.81 | 1.44 | 1.95 | 2.08 | 1.40 | 12.28, 12.53, 12.78, 12.88, 13.86 |
| Hills 0.2, wadis 0.04 | 1.66 | 1.13 | 1.69 | 1.93 | 1.24 | 12.41, 12.82, 13.12, 13.24, 14.56 |
| n 0.1 everywhere | 1.51 | 1.23 | 1.51 | 1.73 | 1.22 | 12.47, 12.76, 13.18, 13.26, 14.43 |
| Hills 0.1, 10 m grid | 1.90 | 1.52 | 2.04 | 2.18 | 1.44 | 12.24, 12.49, 12.72, 12.82, 13.81 |

SCS lag that best reproduces the 2D hydrograph of a headwater subbasin (same excess as HMS, least squares), minutes:

| Subbasin | HMS lag | Hills 0.05 | Hills 0.1 | Hills 0.2 | n 0.1 everywhere |
|---|---|---|---|---|---|
| S1 | 112 | 45 | 51 | 60 | 65 |
| S2 | 102 | 44 | 49 | 56 | 61 |
| S5 | 127 | 40 | 44 | 51 | 57 |
| S6 | 65.5 | 21 | 25 | 31 | 37 |
| S11 | 78.2 | 27 | 30 | 36 | 41 |
| S14 | 93.5 | 41 | 45 | 51 | 57 |

### Why they differ

- **Volume is not the cause.** [Certain] Per-cell CN against composite CN differs by 0.06 % or less at every site. The CN range inside a subbasin is narrow and the rain is large. The remaining 1 to 2 % shortfall in mode (c) is water standing in depressions or still draining at 36 h [Likely].
- **The subbasin lag is the cause.** [Likely] The 2D response equals an SCS lag of 30 to 60 % of the HMS value. Even with HMS's own n 0.1 on every cell, peaks stay 1.2 to 1.7 x HMS, so the gap sits in the hillslope-to-wadi transform and not in the reaches.
- **The storm makes it worse.** [Certain] The pattern puts 34.9 mm in one 10 min step at 11.83 h, 65 mm in the peak hour. The peak is therefore very sensitive to lag.
- **Cell size pushes the wrong way.** [Certain] 10 m raises the peaks by 3 to 6 %. Going finer moves further from HMS.
- **Mode (b) reach routing.** [Likely] At n 0.04 the 2D reaches attenuate less and arrive earlier than Muskingum-Cunge at n 0.1 (R5A +26 %, 0.8 h early). HMS's n 0.1 reproduces its own routing, which shows the two routing methods agree. It does not show that 0.1 is right for these wadis.

### Which Manning is defensible

[Likely] n 0.05 to 0.1 for bare rocky hillslopes in sheet flow. 0.2 is above what bare rock and gravel support [Guessing on the upper bound; no field data here]. No single value fits: 0.2 brings Bidah to 1.13 and leaves R2A at 1.93. Nothing was tuned to hit HMS. The n 0.1 in mode (b) is HMS's value, used unchanged.

## 2. Speed

| Run | Cells | Device memory | Steps | Mean dt, min dt | Wall time | Tables |
|---|---|---|---|---|---|---|
| (c) 20 m, 48 h, GPU otherwise idle | 2.03 M | 1.3 GB | 416,884 | 0.414, 0.105 s | **533 s = 8.9 min** | 190 s cold, 3 s cached |
| (c) 10 m, 36 h, not 48 h | 8.10 M | 4.3 GB | 522,143 | 0.248, 0.037 s | **2,510 s = 42 min** | 197 s cold |
| (b) 20 m, 36 h, GPU shared | 2.03 M | | 259,000 to 309,000 | 0.42 to 0.50 s | 365 to 808 s | shared |

- **Cost per step:** 1.28 ms, or 1.58 G cell-steps/s at 20 m; 4.8 ms at 10 m. Rain refresh and recording are included.
- **Against CLAUDE.md:** the 4 to 8 min expectation was for 1 to 1.5 M cells. This domain has 2.03 M including the plain; scaled to 1.5 M it is 6.6 min [arithmetic]. The 10 m full catchment is 42 min for 36 h, inside the 30 to 60 min guess. The 48 h equivalent would be about 56 min [arithmetic].
- **Real ARF study:** `wadi2d arf` works end to end: five storm areas, design points and composite maps. The composite maps were written but not inspected. 13 storms x 5 areas x 6.7 min (36 h run) = **7.2 h** on one GPU; 48 h runs would take 9.6 h. [arithmetic on the measured run]
- **Mode (b) saved no time** [Certain, though timed on a shared GPU]. Rain on the plain keeps about 1,500 of 2,118 tiles active and dt is unchanged. Decision 6's expectation that (b) is fastest needs a smaller 2D domain to hold.
- **`--dry-run` estimated 119 s against 533 s**, 4.5 x low, the same bias as the first run.
- **What sets dt** [Certain, probed]: 0.41 s holds to the end of the run, 36 h after the peak, with almost no flow left. The storage term of the step rule, floored by `plan_min` 0.02, gives 19 to 22 m/s in near-dry cells, and 47,945 wet cells sit below the floor. `plan_min` 0.05 saved 9 % of the wall time and moved peaks by 0.3 % or less. Worth a proper test.

## 3. Dams

**Read this first. [Certain] `GGC_2_MERGE_HDSM` lies 2.39 m above `NSA_Batinah` (std 0.02 to 0.09 m in both reservoirs).** The EAV curves come from the NSA terrain: 5.63 and 16.84 Mm3 from NSA 2 m against 5.67 and 17.15 in the EAV. The dam levels are on that datum, as is everything in the dam data. HMS and Wadi2D run on GGC. FSL taken at face value on GGC gives 3.8 Mm3 at Bidah (0.67 of EAV) and 14.6 at Faydh (0.85).

(a) Volume in the pool, model tables against EAV. Bidah's crest row at 20 m is blank because the level reaches the escape path of item 4 below.

| Terrain, cell size | Bidah at FSL 100 | Bidah at crest 105 | Faydh at FSL 230 | Faydh at crest 235 |
|---|---|---|---|---|
| NSA 2 m, 20 m | 0.994 | n/a | 0.994 | 0.996 |
| NSA 2 m, 10 m | 0.988 | 0.992 | 0.995 | 0.997 |
| GGC 0.5 m + 2.39 m, 20 m | 0.994 | n/a | 0.992 | 0.996 |
| GGC 0.5 m + 2.39 m, 10 m | 0.984 | 0.988 | 0.991 | 0.994 |

(b) Routing on NSA 2 m, reservoir starting at FSL, Modified Puls on the EAV with Q = 2.1 L H^1.5. Levels are read at a pool point upstream of the dam.

| Case | Inflow m3/s | Puls peak out, level | 2D 20 m | 2D 10 m |
|---|---|---|---|---|
| Bidah 100-yr | 362 | 220, 101.28 | 222, 101.29 | 222, 101.29 |
| Bidah PMP | 1688 | 1530, 104.68 | 1527, 104.71 | 1526, 104.73 |
| Faydh 100-yr | 993 | 908, 231.63 | 893, 231.78 | 896, 231.75 |
| Faydh PMP | 4860 | 4797, 234.96 | 4820, 235.28 | 4818, 235.24 |

- **Times of peak** agree within 0.13 h. Volume through the axis equals boundary outflow within 0.1 % on the PMP runs, so nothing passed around the dams there. The 100-yr runs close within 0.4 %, except Bidah at 20 m: 0.06 Mm3 or 1.8 % left through the boundary without crossing the axis line, unexplained, and absent at 10 m.
- **Bidah crest:** held at PMP, zero flow on the crest lines at 20 m and 10 m. [Certain]
- **Faydh crest:** overtopped at PMP. Peaks on the crest either side of the spillway are 139 + 16 m3/s at 10 m and 180 + 112 at 20 m, 3 to 6 % of the outflow. The 2D pool stands 0.28 to 0.33 m above Puls, 0.24 to 0.28 m over the crest, while Puls stays 0.04 m under it. [Certain for the numbers] The higher level is the water slope through the reservoir at 4,800 m3/s, which a level pool cannot have [Likely].
- **PMP inflows equal the QPMF in the dam sheet** (1688, 4860), and Hmax 5 m is simply that flow on the spillway with no attenuation.
- **Assumptions:** the spillway position is not in the data; I centred it on the thalweg. The engine has no initial level, so each reservoir was prefilled by a constant inflow for 10 h, then rested 2 h.

## 4. Grid convergence, Bidah wadi, natural ground

Same storm, area 21.0 km2, n 0.05, 30 h. Levels are maxima in m. The fourth wadi point was a duplicate cell and is left out.

| Grid | Cells | Wall s | Peak at axis | Peak at ring | Vol Mm3 | 5 km2 point | 10 km2 point | 19 km2 point | Fan point | Extent km2 | F vs 5 m |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 40 m | 17,976 | 31 | 560 | 570 | 3.386 | 179.66 | 108.18 | 90.29 | 68.72 | 2.04 | 0.68 |
| 20 m | 71,934 | 53 | 606 | 617 | 3.401 | 179.39 | 108.38 | 90.61 | 68.72 | 2.13 | 0.73 |
| 10 m | 287,578 | 111 | 625 | 635 | 3.399 | 179.25 | 108.42 | 90.64 | 68.86 | 2.10 | 0.81 |
| 5 m | 1,151,413 | 726 | 628 | 638 | 3.400 | 179.32 | 108.49 | 90.75 | 68.84 | 2.07 | 1.00 |
| 20 m, stride 2 | 71,934 | 64 | 605 | 616 | 3.401 | 179.41 | 108.38 | 90.61 | 68.72 | 2.13 | 0.73 |
| 20 m, stride 4 | 71,934 | 103 | 602 | 613 | 3.400 | 179.41 | 108.38 | 90.61 | 68.72 | 2.15 | 0.73 |

[Certain] Peak converges monotonically: 20 m is 3.4 % under 5 m, 10 m is 0.5 % under. Levels agree within 0.41 m across all grids, 0.14 m between 20 m and 5 m. Extent is judged on one 2 m raster, and total area holds within 5 % while the overlap reaches only 0.73 at 20 m, so location is less certain than area. `pixel_stride` 2 changes the peak by 0.15 %, stride 4 by 0.7 %. Wall times here were on a shared GPU.

## 5. What looks wrong

1. **Mode (c) against HMS (section 1).** Not a defect found in the solver, but design flows from rain-on-grid would be nearly double those of the accepted model. It must not be used for design flows without an observed event to settle the lag. HMS's lags were not checked here. Mode (b) stays the design mode; the expectation in decision 6 stands, on quality rather than speed.
2. **The 2.39 m datum gap (section 3).** Any Block 2 reservoir model on GGC with these levels has about a third less storage at Bidah. This affects the W2 dam routing directly.
3. **Dam shapefiles.** The Faydh axis has a doubled-back leg 1-2, so the first run's Faydh line (413 m3/s) was not a valid section. The dike polylines jump between pieces. Pieces do not join: a 42 m gap at Faydh leaked at 234.0 m, under the 235 m crest, until I joined it. Open ends were carried on to high ground. Both edits are mine and need confirming.
4. **A 20 m face takes its lowest pixel.** Near Bidah's western dike the pool has a static escape path at 104.4 m at 20 m, 0.6 m under the crest, gone at 10 m (design note section 8, ridge inside a cell). The PMP run reached 104.71 m and closed without a visible leak, but that margin is not guaranteed.
5. **The grid cache hashes no engine version** [Certain, read at both commits]. Tables from older code are reused silently after a table-builder change. That is why this work has its own cache folders.
6. **A spillway's faces are not the staircase of its own line.** A line drawn on the spillway read 4 to 25 % under the true flow, because the spillway takes crest faces within one cell. Read the whole axis.
7. **My own domain error, caught and fixed.** A one-cell slit between two domain polygons walled the Faydh gorge and stood 53 m of water behind it, with a clean water balance. The engine gives no warning of a domain gap. A wall at the west edge of the plain box also ponds about 18 m against it, away from every dam line. No domain-check tool exists; a report of the deepest cells per run would have caught both.

## 6. Engine versions and leftovers

- **Later engine.** On `63d580c`, Bidah 100-yr, both PMP runs and the 20 m mode (c) run moved peaks by 0.3 % or less and levels not at all. Steps fell by about 10 % on the mode (c) run. The first attempts at some runs used the live tree; those were discarded and rerun. The pre-fix `x_` run gave identical numbers to `3f32ca6`.
- **For you to delete:** `validation\block2_full\cache\` (3.9 GB). It holds tables built while the terrain code was being edited, and no reported number uses it. The session's safety check refused the removal, so it stays until you remove it. Also `runs\x_c20_A74_n040_domain_slit_at_Faydh\`, which is the invalid slit run, kept for the record of item 7.
- **Not done:** an observed event, a full-domain run with the dams in place, inspection of the composite maps, and any check of how HMS's lags were derived.

## 7. Added after review, same day

- **Later test.** HEC-RAS rain-on-grid on Bidah, same terrain and same excess, gives the same peak as Wadi2D at 10 m and 1.72 x HMS on its own: `ras_rain_on_grid.md`. The gap to HMS in this report is a method difference there, not a solver defect.
- **Checked independently of this report.** Two runs repeated from clean tables on the final engine: Bidah axis 606.4 m3/s and Bidah PMP 1,527.1 m3/s, equal to the figures above, water balance 2e-8. GGC minus NSA resampled at 18,415 random points: median 2.35 m, 2.08 to 2.39 m by elevation band, so the gap is a datum shift and not noise.
- **Block 2 has no gauges** (his statement). HMS is therefore not a reference for section 1: read "mode (c) against HMS" as a disagreement between two uncalibrated models. The HMS lags imply a mean velocity of 1.2 to 1.5 m/s over 8 to 18 km [Likely, lengths from Hack's law, not measured], slow for a 100-yr flood in a steep rock wadi. Item 1 of section 5 is restated in decision 20 of `CLAUDE.md`.
- **The domains here are not clean.** The new edge warning, replayed on these maps, finds 20.5 m of water against the west edge of the plain box in every whole-catchment run (1,694 of 5,098 edge cells above 3 m) and 14.6 m at the end of the Bidah wadi domain. No dam reading is downstream of those points, so section 1 stands; a flood map of the plain from these runs would be wrong there. The two dam domains are clean.
- **`--dry-run`.** The 119 s above did not reproduce: on an idle GPU the old constants gave 728 s against 533 s. Recalibrated, 524 s against 533 s at 20 m and 25 % high at 10 m.
- **Now in the engine:** `initial_levels` replaces the 10 h prefill of section 3; the grid cache hashes the source of the table builder (item 5 of section 5); the edge warning covers item 7.
