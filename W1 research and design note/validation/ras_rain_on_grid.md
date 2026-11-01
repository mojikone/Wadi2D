# HEC-RAS 6.6 rain-on-grid head-to-head, Bidah 03 (2026-11-01)

**Branch 1 of the decision rule, within +/-10 %: at 10 m, SWE-EM, n 0.05, the Bidah section peaks at 622.0 m3/s in Wadi2D and 621.9 m3/s in RAS, ratio 1.000. The two 2D solvers agree, so the gap to HMS is a method difference and not a Wadi2D defect. RAS on its own gives 1.72 x the HMS-equivalent peak, 0.43 h earlier, from the same excess.**

The rule was fixed before any result existed and was not changed. **Checked independently of the run:** see the end of this page. RAS peak over HMS-equivalent is 1.716, so the suspected-defect branch would not have applied at any ratio. Every number is read from a run or a results file in `validation\ras_rain_on_grid\` and is [Certain] unless tagged. Figures name HEC-RAS 6.6 (September 2024) and the Wadi2D engine frozen at `609462d`.

| Primary, Bidah section, 10 m SWE-EM n 0.05 | RAS | Wadi2D | HMS-equivalent |
|---|---|---|---|
| Peak, m3/s | 621.9 | 622.0 | 362.4 |
| Time of peak, h | 12.32 | 12.33 | 12.75 |
| Ratio to HMS-equivalent | 1.716 | 1.717 | 1 |
| Volume through the section, Mm3 | 3.246 | 3.260 | 3.413, whole of S13 |
| Hydrograph NSE, RAS as reference | | 0.999 | |

**Read 1.000 as "within about 4 %", not as 0.02 %.** [Likely] The exact match is partly luck: RAS falls 1.0 % from 20 m to 10 m while Wadi2D rises 3.4 %, so the two lines cross near 10 m. At 20 m the gap is 4.2 %, and RAS's own SWE-ELM sits 3.4 % below its SWE-EM.

## What this does not prove

- **Two solvers agreeing does not make either right about a real flood.** Both solve the same equations on the same terrain with the same assumed n, the same uniform excess and no losses on the way down. A shared error stays invisible. Block 2 still has no gauge, and this test does not say HMS is wrong: it says the difference is in the method, not in Wadi2D.
- **The number is not a design flow.** Peak depends on n far more than on the solver: 0.05 to 0.1 cuts it by about 25 % in both models, against about 4 % at most between them. No field evidence fixes n here.
- **Excess is applied directly to the surface.** No transmission loss on the fan or in the wadi bed, no infiltration of water running across dry ground, no spatial storm. All of these would lower a real peak; none is in either model.
- **The sub-grid sampling rules differ.** Wadi2D takes the higher of two pixels along a face; RAS reads bilinearly at half-pixel spacing and rounds terrain to 1/32 m (`ras_head_to_head.md`). They were not made equal. RAS's mesh also carries its default laminar depth of 0.06 m.
- **One catchment, one storm, four configurations.** Neither model was run at 5 m. Wadi2D's 10 to 5 m move on the older Bidah job was +0.5 %; RAS's is unknown.
- **Out of scope:** crest lines, dams, spillways, spatial rain, and any observed event. Natural ground only.

## Results by run

Bidah section, the dam axis extended to high ground, read over the same lattice faces in both models. Wadi2D's output step and RAS's are both 1 min.

| | 20 m n 0.05 EM | **10 m n 0.05 EM** | 20 m n 0.1 EM | 20 m n 0.05 ELM |
|---|---|---|---|---|
| Peak RAS, m3/s | 628.0 | **621.9** | 467.5 | 606.5 |
| Peak Wadi2D, m3/s | 601.6 | **622.0** | 451.2 | 601.6 |
| **Wadi2D / RAS** | 0.958 | **1.000** | 0.965 | 0.992 |
| RAS / HMS-equivalent | 1.733 | 1.716 | 1.290 | 1.674 |
| Wadi2D / HMS-equivalent | 1.660 | 1.717 | 1.245 | 1.660 |
| Time of peak RAS, h | 12.30 | 12.32 | 12.68 | 12.32 |
| Time of peak Wadi2D, h | 12.34 | 12.33 | 12.74 | 12.34 |
| Volume RAS, Mm3 | 3.234 | 3.246 | 3.204 | 3.233 |
| Volume Wadi2D, Mm3 | 3.264 | 3.260 | 3.241 | 3.264 |
| NSE, RAS as reference | 0.983 | 0.999 | 0.986 | 0.993 |
| Lag RAS, min (HMS 53.3) | 28 | 30 | 50 | 29 |
| Lag Wadi2D, min (HMS 53.3) | 32 | 30 | 55 | 32 |
| Lag that reproduces the S13 edge peak, RAS / Wadi2D, min | 17.5 / 19.5 | 17.9 / 17.9 | 33.1 / 35.6 | 18.9 / 19.5 |
| Wadi, deep cells, level W-R, mean (rms), cm | +14.6 (31.8) | +6.9 (14.2) | +12.6 (31.7) | +14.0 (31.4) |
| of which gorge | +16.5 (34.1) | +8.0 (15.4) | +14.1 (33.9) | +15.7 (33.7) |
| of which fan | +2.1 (5.0) | +1.1 (4.1) | +2.5 (3.6) | +3.3 (5.4) |
| Shallow hillslope, level W-R, mean (rms), cm | -0.3 (8.7) | -1.1 (8.2) | 0.0 (8.3) | -0.2 (8.8) |
| F on extent, 0.5 m pixels >= 0.3 m, whole domain | 0.775 | 0.834 | 0.797 | 0.779 |
| F on extent, same, fan only | 0.870 | 0.934 | 0.895 | 0.871 |
| F on extent, 0.5 m pixels >= 0.1 m, whole domain | 0.782 | 0.813 | 0.797 | 0.784 |
| F on extent, same, fan only | 0.841 | 0.879 | 0.859 | 0.841 |
| RAS wall, 8 cores | 12:04 | **1:56:37** | 8:37 | 11:31 |
| Wadi2D wall, RTX 5080, warm cache | 14.3 s | **48.2 s** | 14.7 s | same run as EM |
| RAS volume error, % | 0.016 | 0.011 | 0.018 | 0.033 |
| Rain, Wadi2D / RAS | 1.00004 | 1.00004 | 1.00005 | 1.00004 |

- **Lag** is the method of `block2_full/scripts/s26_equiv_lag.py`: S13's excess, S13's area, 5 min steps, least squares on the lag in whole minutes. The S13 edge section gives the same values within 1 min.
- **Wadi** cells drain at least 1 km2, or lie within 40 m of one that does, by the HMS accumulation raster, so neither model sets the class. "Deep" is 0.5 m or more over the cell's low point in both. **Hillslope** is everything else; "shallow" is 2 cm to 0.5 m in both. The gorge lies west of 437,300 E, the fan east of it.
- **Extent:** cell-based F is left out of the table. On steep ground depth over a cell's low pixel measures relief as much as water, and at 10 m it gives 0.54 for 0.3 m. The fan-only pixel F of 0.934 is the one comparable with the 0.936 of the fan window in `ras_head_to_head.md`.
- **A second section,** the S13 edge, which holds all of S13's area: 633.8 against 633.8 m3/s at 10 m, 641.5 against 613.9 at 20 m, 1.749 x HMS-equivalent in both at 10 m.
- **Repeatability:** three Wadi2D jobs run twice gave identical hydrographs, difference 0.0 m3/s.

Figures: `ras_rain_on_grid\fig_10m_n050_em.png` and the same for each run; thalweg profile in `fig_jump_10m_n050_em.png`.

### Checked before believing the match

- **Raw series round the peak, 10 m:** RAS 612.95, 619.38, 621.93, 620.57, 615.30 m3/s at 12.283 to 12.350 h; Wadi2D 606.64, 615.90, 620.73, 621.15, 617.38. They differ, as independent runs should.
- **The section read is sound:** the same RAS code path gave a 4 % gap at 20 m, and RAS's outlet series closes on its own accounting: 3,544,534 against 3,544,602 m3 at 10 m.
- **Same cells:** RAS holds 219,744 cells at 10 m and 54,936 at 20 m, the lattice exactly, centres within 1e-8 m. Interior faces are the full cell width less at most 4 cm. The 477 tiny faces at each size are all on the wall. RAS Manning reads 0.05 and 0.1 on every cell.

### HMS-equivalent

The excess is the 100-yr Block 2 storm, 205.4 mm, x ARF 0.9749 at 20.971 km2 = 200.25 mm, less SCS losses at CN 87.6, Ia 7.2 mm = **162.74 mm**, first excess at 3.25 h, peak step 15.59 mm in the 5 min ending 11.83 h. Through S13's SCS unit hydrograph at lag 53.3 min on 5 min steps this gives 362.37 m3/s at 12.75 h, 3.413 Mm3: **identical to HMS's 362.371 m3/s**, since S13 alone feeds Bidah 03. That peak covers all of S13. The axis drains about 95 % of it, 19.9 to 20.0 km2 by volume, so the S13 edge is the strict like-for-like, at 1.75 x. The 1.72 at the axis is the conservative figure.

## What the HMS gap now means

- **The 2D response is faster than S13's lag in two independent solvers** at the same n: best-fit lag 29 to 30 min against 53.3.
- **The best-fit lag understates the gap, because the SCS shape is too broad here.** [Certain for the numbers] At lag 30 min it reaches only 502 m3/s against the 622 it is fitting. To reach the 634 at the S13 edge, the like-for-like section, the lag must fall to 18 min, a third of HMS's. So the 30 to 60 % in `block2_full.md` is a fit to the shape, not to the peak.
- **At n 0.1 everywhere the 2D lag matches HMS and the peak still does not:** lags 50 and 55 against 53.3, peaks 1.29 and 1.25 x. The peak difference there is shape, not timing. That is in line with the `n 0.1 everywhere` row for Bidah in `block2_full.md`, 1.23, read there at a different storm area.
- [Likely] The gap sits in the transform, hillslope to outlet, and only partly in the choice of n. Evidence for which is right must come from outside these models (decision 20).

## Where the two solvers do differ

The agreement is at the section. Inside the catchment:

| Thin-flow reading, hillslope max mean depth, cm, RAS / Wadi2D | 20 m | 10 m |
|---|---|---|
| Whole hillslope | 5.51 / 5.42 | 5.56 / 5.50 |
| Cells with 0 to 2 m relief inside | 12.98 / 14.01 | 11.81 / 12.73 |
| 2 to 5 m | 5.45 / 6.37 | 2.71 / 2.46 |
| 5 to 10 m | 3.14 / 3.03 | 1.60 / 0.78 |
| Over 10 m | 2.17 / 1.06 | 1.41 / 0.55 |
| Water left at the end of the run, m3 | 46,680 / 16,047 | 31,821 / 19,020 |

- **Cells with over 10 m of relief hold 2 to 2.6 x the water in RAS.** The total over the hillslope still matches, because Wadi2D holds more on gentle cells. [Likely] The cause is the thin-sheet reading against RAS's flat level per cell; I did not isolate it. Which one is closer to a real sheet on rock is not shown here. It is 0.9 % against 0.5 % of the rain at the end, which is about the volume difference at the section.
- **Max level on the hillslope is not comparable between the two in steep cells:** -8.2 cm mean, 19.3 cm rms at 10 m over all hillslope cells, against -1.1 (8.2) in the shallow class. Level over a cell's low pixel on a steep cell reflects how each code reads a sloping surface. The figure map shows this as blue over the western hills.
- **The thin-sheet option matters and helps.** Wadi2D with `sheet_flow` off, set in the job with no code change:

| Bidah section | Sheet flow on | Off | RAS |
|---|---|---|---|
| 20 m peak, time, NSE | 601.6, 12.34, 0.983 | 677.7, 12.23, 0.958 | 628.0, 12.30 |
| 10 m peak, time, NSE | 622.0, 12.33, 0.999 | 657.4, 12.28, 0.977 | 621.9, 12.32 |

  Thin-sheet treatment moves the peak by 6 to 13 %, and at 10 m it takes the ratio from 1.057 to 1.000. So it was not the source of a false excess over HMS: with it off, Wadi2D would stand further from HMS, not closer.

- **Cell size is Wadi2D's main remaining sensitivity on this ground.** At 20 m Wadi2D is 4.2 % low, 2.5 min late, and stands 16.5 cm high in the gorge (rms 34 cm), while the fan stays at +2.1 cm. RAS's EM to ELM spread in wadi level at 20 m is 8.4 cm rms, so Wadi2D's 31.6 cm rms from RAS on the same wadi cells at 20 m is 3.8 x that yardstick and is not solver-choice noise. It halves at 10 m. [Likely] It comes from the faces in a narrow steep channel at 20 m; I have not tested that.

## The jump at the fan head

**Neither model shows a hydraulic jump at the fan head.** Read at the section peak along a 6.4 km thalweg, from the 5 km2 point to the outlet, using cell speed and mean depth, 100 m running mean:

- **At 10 m both models give the same profile:** level difference -0.6 cm mean, 3.4 cm rms over the whole path. Froude peaks at 1.14 and 1.10, and both cross down through 1 for the last time 10 m apart along the path, at about 435,190 E, 2,726,795 N, with the bed at 2 %.
- **From there to the outlet Froude stays below 1 in both,** 0.5 to 1.0, and the water surface never rises: its 100 m slope stays between 0.6 and 2.8 % in RAS.
- **The nearest thing to a jump is a smooth transition where the gorge opens,** about 437,050 to 437,080 E, 2,726,600 to 2,726,490 N, and the two models place it alike. Over 125 m Froude falls from 0.90 to 0.57 (0.59 in Wadi2D) and depth over the low point doubles, 1.05 to 2.0 m, but level keeps falling, 109.64 to 108.25 m in RAS and 109.62 to 108.21 m in Wadi2D. The low point falls faster than the water, 1.9 % against 1.1 %, which is why depth grows with no rise in level. Below it the bed flattens from about 2 % to 1.2 %.
- **At 20 m** RAS hovers at 1.0 further down to 436,660 E; Wadi2D's last crossing is at the same 435,200 E. Froude near 1 makes that location weak.
- **Caveat** [Likely]: cell-mean depth over a sub-grid channel hides local supercritical threads, and Wadi2D's map is from the nearest 5 min output, 12.34 h against RAS's 12.32 h. So this rules out a clear jump at cell scale, not a local one inside a cell.

## Case

- **Domain.** S13's polygon as it stands, no buffer, plus a fan box out to 439,045.99 E and 2,727,980.39 N, as a staircase on a 20 m lattice anchored at DEM pixel corners; 21.97 km2. The same ring serves 10 m. Both use the same 0.5 m clip of `GGC_2_MERGE_HDSM.tif`, natural ground, no dam.
- **Outlet.** The east and north edges of the box are open, normal depth at S 0.01, measured 0.7 to 1.0 % on the thalweg. In RAS the boundary lines lie on the perimeter. Wadi2D's boundary cells are one extra row outside it, so the rained cells are the same cells. 99.8 % of the RAS outflow leaves by the east edge.
- **Forcing.** The excess above, on 5 min steps, spatially uniform, no loss method in either. RAS takes a precipitation table with no infiltration layer; Wadi2D takes a hypothetical storm with no ARF and no CN. 30 h run.
- **RAS settings.** Courant control on, maximum 1.0, minimum 0.45, base step 10 s, 3 doublings and 5 halvings, 8 cores, otherwise the defaults of `ras_common`. Output every 1 min, which alone writes 2.2 to 9 GB, so these wall times are not RAS's best.
- **Wadi2D settings.** Defaults at `609462d`, `tables.rows` 16, `source_every_s` 30.
- **Before any RAS run** I tested the domain with Wadi2D alone. No RAS number informed the domain.

### Water against closed edges

**The outlets are clean and the walls hold no pond in either model.** The engine's warning fired in every Wadi2D run, 4.5 to 4.9 m at a rim cell, and RAS shows the same, 4.9 to 5.0 m. That is depth over one low pixel, not stacked water.

| Closed edge cells, away from the outlets | 20 m, RAS / Wadi2D | 10 m, RAS / Wadi2D |
|---|---|---|
| Largest max mean depth, m | 0.32 / 0.33 | 0.80 / 0.82 |
| Cells over 0.5 m mean depth | 0 / 0 | 5 / 5 |
| Volume at max, m3 | 7,194 / 2,753 | 5,663 / 3,987 |
| Share of the rain | 0.20 / 0.08 % | 0.16 / 0.11 % |

### Run time

**RAS takes 145 x as long as Wadi2D at 10 m, 51 x at 20 m,** wall to wall with a warm cache: 6,997 against 48.2 s, 724 against 14.3 s, GPU otherwise idle at 0 %. Cold tables add about 5 s. RAS's output load and the open QGIS sessions make its times upper bounds, and Wadi2D has 5 min maps against RAS's 1 min. It is not a like-for-like benchmark.

## Traps paid for here

- **Precipitation grammar, from the Majlas `.u` files and one test run.** A `Boundary Location` naming the 2D area with an empty BC line, then `Interval=5MIN` and `Precipitation Hydrograph= N`, 8-character columns, 10 per line, then the usual `DSS Path` block. `Precipitation Mode` stays `Disable`. Ras.exe carries a message against turning precipitation on in both places; I did not test that.
- **Reading of that table, measured** with `Cell Cumulative Precipitation Depth` on a closed 500 m square (`grammar_test.py`): millimetres per interval; element k is the depth of the interval ending at k x dt, so element 0 is a dummy; the rate is constant inside the interval. That is HMS's period-ending convention.
- **A concave lattice corner kills RAS's mesh generator.** Seeds on a lattice with a staircase perimeter give "Some cells have negative area" or "Index was out of range", on even an L shape, because the corner lands on a four-way Voronoi vertex. **Pulling the perimeter in by 2 cm cures it** (`mesh_test.py`). Cost: rim cells lose up to 0.4 % of area, 0.003 % over the domain.
- **Reference lines are not used.** Sections are summed from `Face Flow` over Wadi2D's own staircase, so both read the same faces.
- **`maps\*.tif` and `results.h5` start at the run's own domain,** not at the lattice; the comparison pastes them onto it.

## What looks wrong, or waits on the owner

1. **Whether HMS's lag or the 2D response is right is still open, and it is now the whole question.** A solver defect is ruled out as the explanation for this catchment. The next evidence is outside the models: decision 20's regional envelope, flood marks from Shaheen 2021, a gauged neighbour.
2. **n matters 6 x more than the solver.** 0.05 to 0.1 moves the peak by 25 %. Field or photographic evidence for n on these hills would do more than any further solver work.
3. **Whole-catchment 20 m numbers in `block2_full.md` read low.** At Bidah, 20 m is 3.3 % under 10 m. That report already gives 3 to 6 %; this test shows the 10 m value is the one RAS supports. For a design point, run 10 m.
4. **Steep-cell storage differs by 2 to 2.6 x and was not explained.** It did not move the section peak here. It may matter more for a short storm, where hillslope storage is a larger share.
5. **Not tested here and still open:** crest lines against RAS, RAS at 5 m (about a day [Guessing, from 1:57 at 10 m]), one more catchment. A second catchment is the cheapest guard against 1.000 being luck.
6. **Disk.** The RAS folders hold 15 GB and `wadi_runs` 3.4 GB, kept for rerunning the comparison and ignored by git.

## Checked independently of the run

Second reading with none of the scripts above: the section rebuilt as a cut of RAS's own cell links (155 faces at 10 m), the sign from RAS's face normals.

- **Primary peak:** RAS 621.90 m3/s at 12.32 h, Wadi2D 622.03 at 12.33 h, ratio 1.0002, NSE 0.999. S13 edge 633.86 against 633.84. All four runs agree with the table within 0.15 m3/s at both sections.
- **RAS plan:** SWE-EM and SWE-ELM read from the plan HDF, one Manning value on every cell, Courant control as stated.
- **Forcing:** RAS's table and Wadi2D's curve total 162.74 mm, peak step 15.588 mm ending at 710 min in both, largest cumulative gap 5e-6 mm.
- **Engine:** all 99 files of the snapshot equal `609462d`, line endings aside.
- **Lag claims:** a separate SCS unit hydrograph gives 361.4 m3/s at lag 53.3 min (HMS 362.4), 501 at lag 30, 634 at lag 17.9.
- **Gorge level, partly:** the class means above are in `results_*.json`. A cruder split, cells over 2 m deep in both models, gives +9.0 cm at 10 m and +12.3 cm at 20 m in the gorge, +2.3 and +1.9 in the fan: same sign and order, not the same cells. The steep-cell storage table was not recomputed.

## Provenance and rerun

`frozen_commit.txt` holds `609462d0e8372ce04739fa95c992b8411f341d95`; the jobs ran from the snapshot `engine_609462d\` with the project venv. Nothing under `wadi2d/`, `plugin/` or `tests/` changed. Block 2 files were only read. No DSS file was touched. Nothing was downloaded or installed.

From `validation\ras_rain_on_grid\`, with `PYTHONPATH=engine_609462d`:

`s01_domain.py --terrain`, `s02_excess.py`, `queue_ras.sh 20m_n050_em 10m_n050_em 20m_n100_em 20m_n050_elm`, `run_wadi.py NAME`, `compare.py NAME`, `jump.py NAME`, `check_primary.py`, `peak_lag.py`, `yardsticks.py`, `collect.py`. All inputs are in `case.py`. `compare.py`, `jump.py`, `check_primary.py`, `peak_lag.py` and `yardsticks.py` need the project venv; the RAS queue does not.
