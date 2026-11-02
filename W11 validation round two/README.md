# W11 validation round two

**Status (2026-11-01): in progress. Engine frozen at `f976c23`. Results are added below; the rules in this section were written before any run; the one amendment, the primary of test 1, is marked where it was made.**

Read-only against the code: nothing under `wadi2d/`, `plugin/` or `tests/` is edited, nothing is committed or pushed, the Block files are only read. Every Wadi2D run uses the snapshot `engine_f976c23\`, made with `git archive f976c23`. The GPU is shared: no timing claim is made from any run here.

## Decision rules, fixed before the runs

**Rule 1, crest line against HEC-RAS 6.6.** Same terrain, same inflow or excess; a 2D Connection in RAS, a crest line in Wadi2D. Within 10 % on peak overtopping discharge AND within 0.15 m on peak stage upstream: **agree**. Otherwise: **diagnose, do not tune**. Time is compared and reported; it carries no threshold. The primary configuration is named below before its run. Any other configuration is a sensitivity and cannot change the verdict of the primary.

**Rule 2, second catchment rain-on-grid.** Same method as `W1 research and design note/validation/ras_rain_on_grid.md`: 10 m, n 0.05, SWE-EM, same excess in both, peak read over the same lattice faces. Wadi2D / RAS peak within +/-10 %: **agree**. Outside: **diagnose**. The catchment is named below before its run.

**Rule 3, regional envelope.** Bidah at 21 km2, 100 yr: 2D about 30 m3/s/km2, HMS 17. A source counts only if it covers arid mountain wadis of Oman or the Arabian Peninsula and an area within a factor of about 3 of 21 km2 (7 to 60 km2), or gives a relation that can be read there.
- **"Supports 30"** needs a regional quantile near 100 yr, or gauged floods of known return period, reading 24 or more at that size.
- **"Supports 17"** needs the same reading between 12 and 23.
- A world envelope, or an all-time maximum of unknown return period, can rule a value out only if it lies below it. It cannot support either value by lying above both.
- Otherwise: **cannot say**.

**Rule 4, extent F 0.40 against his 200-yr layer.** Named as the main cause only a difference that, changed or removed by itself, raises F by 0.10 or more, or accounts for at least half of the misses (his-only plus Wadi2D-only area). **Excluded** a candidate that moves F by under 0.03. Anything between is **partial**. F = both / (both + his only + Wadi2D only), same depth threshold on both, stated with each number.

### Test 1 configuration, fixed before its RAS runs

- **Primary, the one the rule judges: `z94_10`.** Domain, 0.5 m terrain, excess, n 0.05 and outlets of `ras_rain_on_grid`, Bidah, 10 m, SWE-EM. One constant crest at 94.0 m on the GGC terrain along the extended Bidah dam axis, the three legs of `case.AXIS`, 1,101.5 m, about 650 m of it below the crest. Where the ground is higher the ground is the crest in both models. Natural terrain otherwise: no fill, no toe, a line.
- **RAS:** a 2D Connection inside the mesh, weir equation, broad crested, C = 1.7046 m^0.5/s, which is Wadi2D's critical-flow coefficient, weir width 6 m, the default submergence limit 0.98. The mesh stays the lattice. RAS walks the staircase of faces and spreads the true line over them, 14 m of station on a 20 m face (grammar run, no rain).
- **Wadi2D:** a `crest_line` with `z_constant` 94.0; its own staircase and length factor.
- **Overtopping discharge:** RAS `2D Hyd Conn/Embankment` Structure Variables, Total Flow; Wadi2D the design line drawn on the same coordinates.
- **Stage upstream:** maximum water surface in the lattice cell holding each of two points on the normal to the middle leg at station 450 from the south-east end: `pool150`, 150 m upstream, is the one the rule judges; `pool400`, 400 m upstream, is reported.
- **Sensitivities:** the same at 20 m; crest 96.0 m, 10 m and 20 m, where the pool attenuates the peak; RAS overflow by the 2D equations in place of the weir equation, 10 m and 20 m. None can change the verdict of the primary.
- **What informed the crest level:** Wadi2D alone at 20 m, `probe20_z92`, `z94`, `z96`: peak over the crest 594, 506 and 190 m3/s against 602 with no crest. 94 was picked for a large overtopping flow with the pool still acting. No RAS result existed. The same probe with no crest reproduces the 601.6 of `ras_rain_on_grid` at 20 m, so `f976c23` has not moved that number.

### Test 2 configuration, fixed before its RAS runs

- **Catchment: Faydh 01, S11 + S12, 74.3 km2 against Bidah's 21.** Two subbasins and a reach in HMS, HMS peak 993 m3/s at 13.25 h, a single wadi leaving by one gorge. Compactness 0.28 and 0.20 for the two parts; mountain relief to about 1,500 m.
- **Domain:** both polygons as they stand, no buffer, plus a box on the wadi below the axis, 430,986 to 432,306 E, 2,732,940 to 2,733,860 N, 75.51 km2, 188,768 cells at 20 m, 755,072 at 10 m, on a 20 m staircase anchored at DEM pixel corners. East edge of the box open, normal depth S 0.015, surface slope 1.55 % in the Wadi2D-only domain test below. All other edges walls.
- **Forcing:** the 100-yr Block 2 storm, 205.4 mm, ARF at 74.304 km2, 191.22 mm, through S11's and S12's SCS losses, 163.49 and 162.57 mm. RAS's table is one depth for the mesh, so both models take the area-weighted mean, **163.08 mm**, uniform, no loss method. HMS holds the two apart; a 0.6 % difference.
- **Solver:** RAS 6.6 SWE-EM, n 0.05, Courant control as `ras_rain_on_grid`, 8 cores, 30 h. Wadi2D `f976c23` defaults, `tables.rows` 16.
- **Peak read** over the same lattice faces in both, on two sections: `axis`, the lower legs of the dam axis, which the rule judges, and `box_mid`, 431,605 E. RAS output every 2 min, not 1 min, to hold the file size; Wadi2D series every 2 min. The 20 m pair is run too and reported; the 10 m pair is the one the rule judges.
- **What informed the domain:** a Wadi2D-only run at 20 m, 1,835 m3/s at 12.21 h at the axis. No RAS number.
- **Added before the 10 m RAS run, rule unchanged:** that run stops at 16 h, not 30 h, and both models are read to the same hour. The rule reads the peak at about 12.2 h. At the rate of the 20 m run, 30 h at 10 m would take over a day. The 20 m pair keeps 30 h.

### Extra, not one of the four: an observed flood, fixed before its run

The search for test 3 found gauged rain and gauged flow for Cyclone Shaheen at Bani Umar near Lihban (DB839224AD, 197.5 km2): 2,540 m3/s at 04:00 on 4 October 2021, 29.8 Mm3, one 1-minute rain gauge near the outlet, 459 mm. A rain-on-grid run costs minutes, so it is run, as a check outside the four tests. It proves or disproves nothing about Block 2 by itself.

- **Method:** Wadi2D `f976c23`, 20 m, n 0.05, the project's blended terrain, the gauge's rain applied uniformly with a loss set so the excess volume equals the observed volume exactly, in two forms that bracket the timing: constant phi and constant fraction. No calibration of n.
- **Rule:** peak within +/-25 % of 2,540 m3/s and time of first peak within 45 min, in at least one of the two loss forms: **2D response consistent with the flood**. Peak over 1.25 x observed in both: **2D too fast or too high**. Under 0.75 x in both: **too slow or too low**. Otherwise: **cannot say**. A single rain gauge at the outlet of a 197 km2 basin limits what any answer means.

### Test 1, **amended** after the 20 m run: the limits stand, the primary moved

**This is an amendment, not "rule unchanged" as first written here.** The rule's limits did not move, but the run they judge did: the fixed primary `z94_10` could not be run, so `a94_10` took its place. File times show the order: Wadi2D's 10 m run 17:17, RAS `z94_20` 19:07, RAS `z94_10` crashed 19:09, aligned runs after. The 20 m pair (0.924, with the 28 % volume error) had been read by then. No 10 m pair could have been, because the RAS side did not exist, so the move could not follow from the 10 m result.

The first RAS run with the connection (`z94_20`) closed with a **28.1 % volume error**: 1.0 Mm3 of water that no rain supplied, against 0.016 % with no structure. `t1_crest\diag3.py`: the gain starts with the run and grows at about 12 m3/s from hour 3, long before the pool fills, so it is a spurious source in RAS and not the flood. The mesh was left as the lattice, with RAS walking a staircase of faces; the HEC-RAS manual expects a breakline on the structure. The rule, the crest and the primary `z94_10` stay as fixed above. **A reference with that error cannot decide alone**, so one more configuration is added before its run:

- `a94_10`, `a94_20`, `a96_20`: the same, with the mesh's faces aligned on the line: seeds mirrored across each leg, as a breakline does, lattice elsewhere. The same rule judges `a94_10`. The verdict states both, and if they differ, says which reference closed its volume.
- `d6_*`: 6 h runs to find the source: aligned mesh, and overflow by the 2D equations. Diagnosis only.

- **The primary as fixed cannot be run:** RAS `z94_10`, lattice mesh with the weir equation, went unstable at hour 3.15 with a volume error of 2.4e8 %, before any flood. The 6 h diagnostics locate the source: the weir equation on an unaligned lattice. With faces aligned (`d6_aligned`), or with overflow by the 2D equations on the lattice (`d6_lattice2d`), stored water plus outflow equals rain to 0.001 Mm3 in the first 6 h. So **`a94_10` is the configuration the rule judges**; the rule itself is unchanged. `z94_20_2d` was stopped at its start to free the cores. The lattice weir run `z96_20` is dropped.

- **Added before their runs:** `a94_20_2d` and `a94_10_2d`, aligned mesh with overflow by RAS's 2D equations in place of the weir equation. The weir runs give RAS Wadi2D's own coefficient, so they cannot fail on the coefficient. These runs carry no coefficient. Sensitivities, reported under the same two limits, with no effect on the verdict.

### Test 4 runs that are not valid

**Sets `t0` to `t5` and `b_t0` to `b_t5` in `t4_extent` are throttled and no F from them counts for rule 4.** His Sea line lies up to 140 m off the domain, and `cells_along` at `f976c23` looks one cell around each sample and drops the rest without a word. Real boundary cells on the engine's grid (`s13_boundary_check.py`, `boundary_check.json`): `t0` 48 cells, 0.039 x length/dx; `t4_dx15` 13 cells, 0.005; `b_t0` 516, 0.42; `b_t4_dx15` 592, 0.24. The 15 m run kept half the rain on land and the engine gave no warning. `b_t1` was stopped part way. The folders stay as the record. The valid set is `c_t0` to `c_t5`: the domain edge inset by 2 cells, clipped to the Sea stretch, gated at 0.7 x length/dx before any run. W2's own run is not affected, so the decomposition from W2 stands. The jobs of tests 1 and 2, Fizh and Lihban pass the same gate at 1.0 x.

## Results

### Test 1, crest line against a 2D Connection: **agree, with RAS given Wadi2D's own weir coefficient**

**Rule 1 verdict on `a94_10`:** peak overtopping Q 536.6 against 534.0 m3/s, **1.005**, limit 10 %; stage at `pool150` 94.616 against 94.614 m, **+0.002 m**, limit 0.15 m. **Agree.** RAS closed its volume to 0.017 %.

| Bidah axis, crest level, 2D Connection overflow by | Peak RAS | Peak Wadi2D | Ratio | Time, W - R, min | Volume ratio | Stage, W - R, m | RAS volume error, % |
|---|---|---|---|---|---|---|---|
| **94 m, 10 m, weir equation, aligned, the judged run** | **534.0** | **536.6** | **1.005** | +0.5 | 1.013 | **+0.002** | 0.017 |
| 94 m, 20 m, weir equation, aligned | 522.4 | 506.5 | 0.969 | +2.5 | 1.004 | -0.019 | 0.004 |
| 96 m, 20 m, weir equation, aligned, the pool attenuates | 184.8 | 190.3 | 1.030 | +3.5 | 1.049 | +0.001 | 0.027 |
| 94 m, 20 m, **2D equations**, aligned, no coefficient | **627.3** | 506.5 | **0.807** | +9.5 | 1.004 | **+0.337** | 0.008 |
| 94 m, 10 m, **2D equations**, aligned, no coefficient | **638.8** | 536.6 | **0.840** | +7.5 | 1.011 | **+0.411** | 0.002 |
| 94 m, 20 m, weir equation, **lattice** | 548.2 | 506.5 | 0.924 | +4.5 | 0.930 | +0.049 | **28.1** |
| 94 m, 10 m, weir equation, lattice, the primary as first fixed | unstable at 3.15 h | | | | | | 2.4e8 |

Wadi2D at `pool400` and at a tail point 100 m below the crest stands within 0.003 m of RAS at 10 m. RAS's weir submergence stayed about 0.001. Over 800 m of pool upstream, deep cells differ by -3.9 cm mean, 39 cm rms at 10 m, mostly on the steep margin, because the RAS mesh there is not the lattice [Likely].

**Read the agreement for what it is.**

- **The coefficient was shared.** RAS's weir equation was given 1.7046, Wadi2D's critical-flow value, so this pair cannot fail on the coefficient. It tests the pool, the staircase's length factor, timing and mass, and those pass. Back-calculated from the peaks on 651 m of crest, RAS reads C 1.71 and Wadi2D 1.71 at 10 m.
- **A real embankment's coefficient is a separate question.** Broad crest over a rough road is often taken lower than 1.7 [Guessing without a source here]. The result scales with it in both models.
- **The one test with no coefficient does not pass, and RAS is the one that looks wrong.** With overflow by the 2D equations RAS passes 627 m3/s at 20 m with the pool 0.25 m over the crest, and 639 at 10 m with it 0.20 m over: C 7.8 and 10.6, 4.6 and 6.2 x critical flow [Certain, arithmetic]. It moves away from critical as the mesh refines, and it stands at the natural peak of 622 to 628 as if the crest were not there. A pool level cannot pass 4.6 x critical flow over a crest, so I read this as RAS's face equations carrying no critical control across a thin raised face [Likely]. **It is outside the rule, it does not change the verdict, and it needs saying: on the only coefficient-free pair the two models differ by 16 % and 0.41 m at 10 m, so no independent check of crest discharge exists yet.** Wadi2D sits on critical flow, 0.996 of it in the analytic test.
- **Not tested:** submerged overtopping (submergence 0.001 here), a crest profile that varies, the shaped embankments of `W8 terrain tools`, a spillway beside a crest. This is a constant thin line on one site.

**RAS's connection on a lattice is a trap, for anyone copying this pipeline.** With the mesh not aligned to the connection, the weir equation made water from the first rain: 12 m3/s steady on the 20 m run, a 28 % volume error, and instability at 10 m. Nothing in RAS flagged the 20 m run, which reported `Unsteady Finished Successfully`. Aligned seeds cured it with no other change. The 20 m peak of 548 was 5 % off the clean 522 and looked plausible. The volume error is what gave it away.

### Test 2, second catchment

To follow.

### Test 3, regional envelope: **cannot say at 21 km2; the record leans to 17, and near Block 2 it sits under both**

**The find first: Block 2 does have gauges.** Two ministry stations lie below Block 2 catchments, and the project holds decades of neighbouring annual peaks, gauged event hydrographs and a national flood-frequency report. Decision 20's "no gauges" holds only in the narrow sense: no event with rain and flow together inside Block 2. Gauge basins from project 2331 laid over the HMS subbasins (`t3_envelope\gauge_basin_overlap.json`) [Certain]:

| Gauge | Basin km2 | Holds of Block 2 | Peaks on record | Largest, year, return period | Q100, report |
|---|---|---|---|---|---|
| **DC417300AD Fizh near Sabakh** | 262 | **S1, S2, S3, S4: all 210.7 km2 of Z4C** | 28 | 475, 1981, 39 yr | 770 |
| **DC434816AD Hatta near Shinas** | 653 | **S11, S12: all 74.2 km2 of Faydh 01** | 27 | 638, 1988, 55 yr | 837 |
| DC237976AD Hatta near Ajib | 478 | 0.9 km2; the mountain station beside Faydh | 26, plus 5 event hydrographs, no rain | 1,200, 1976, 44 yr | 1,710 |

`Francou-Rodier.xlsx` gives other areas (121 km2 for Hatta near Shinas); the polygons are used here. Hatta near Ajib reads 1,710 and Shinas downstream reads 837: the peak halves across the plain, the warning that goes with every plain gauge below.

**What is on W: and where** [Certain, opened]:

| Holds | Where |
|---|---|
| Annual instantaneous peaks 1971 to 2022, 36 stations; frequency fits; Francou-Rodier K | `2224...\06-WORKING\03-Hydrology\WadiGaugeDataAnalyses_MT\` |
| Ministry raw files, 10 stations, Fizh near Sabakh and Hatta near Shinas among them | `2224...\09-RECEIVED\13 SharePoint Data 06.06.2023\General\02_Data\00_Received\01_MAFWWR\27122022_MAFWWR\Wadi Data\` |
| **Shaheen 2021: 6-min flow at Lihban, 1-min rain, the project's HMS calibration** | `2224...\06-WORKING\03-Hydrology\calibration\` |
| **Rain and flow together, 4 events at Lihban; hydrographs at 4 more stations** | `2331...\0.13 REPORTS\Hydrology Final Report- Flood Data Analysis\Data for model calibration- hydrograph\` |
| **National report: Q by return period at 103 stations, K maps, Tc from hydrographs, return period of each largest flood** | same folder, `Report\Final Report\` |

**Readings at 21 km2, 100 yr, m3/s/km2.** HMS 17, 2D 30; the rule's bands are 12 to 23 and 24 or more.

| Source | Reading | Note |
|---|---|---|
| Report's K map for 100 yr at Block 2, K 4.5 to 4.9 [read off its Figure 49 by eye] | 10 to 19 | The method the report prescribes for a location in northern Oman |
| Six nearest gauges, K 4.06 to 4.80 | 5 to 16 | Mostly plain or fan head, low by construction |
| MRMEWR synthetic method, Qmaf = 2.1 A^0.76 S^0.16 NM^-0.142, x 5.9 [JICA] | 7 to 11 | Mountain form; S 15 to 50 m/km, NM 1 to 5 |
| Five northern gauges of 38 to 59 km2, each at its own K | 10, 20, 24, 30, 30 | Kid, Lansab, Misfah, Jifar, Saal; all about 190 to 240 km away |
| All 72 northern stations, u = 220 A^-0.70 | 26 | Scatter x/÷ 1.8 |
| The 37 northern stations of 300 km2 or less, u = 191 A^-0.68 | 24 | Scatter x/÷ 1.6 |
| Musandam regional table, 20 km2 [report Table 69] | 26 | Another governorate |

**Verdict by the rule: cannot say.** Readings fall in both bands and the rule names no winner. It leans to 17: the location-specific methods read 5 to 19; the readings of 24 or more pool all of northern Oman, and the report itself says one table cannot serve there. [Likely] 30 is not ruled out at 21 km2.

**Envelopes rule out nothing.** Saudi regional maximum Q = 251 A^0.45 gives 47 at 21 km2 (Ewea et al. 2018, K 5.5, recurrence 1,000 to 100,000 yr). Shaheen at Lihban, K 5.44, read down to 21 km2 gives 43. Both lie above 17 and 30, so by the rule they support neither. No published Creager or Francou-Rodier set for Oman surfaced on the web beyond project 2331. Wadi Dayqah in Gonu, about 10,000 m3/s estimated on about 1,700 km2, is an estimate at 80 x Bidah's area and is not used.

**At Block 2's own scale no extrapolation is needed, and the record reads lower than the question asked.** K at 100 yr; the same formula, Q0 1e6, A0 1e8:

| | km2 | HMS | 2D, mode c, 20 m |
|---|---|---|---|
| Bidah | 21 | 4.85 | 5.20 |
| Faydh 01 | 74 | 5.10 | 5.52 |
| R5A | 117 | 4.85 | 5.35 |
| R2A | 176 | 5.02 | 5.57 |
| Z4C | 211 | 5.10 | 5.36 |

The six gauges within 30 km read 4.06 to 4.80. Northern Oman, 72 stations: median 4.72, p90 5.29. 2D sits above p90 at four of five dams; HMS above the median at all five.

**A run at a real gauge** (extra; no rule set, reported as a measurement). `t3_envelope\s14_fizh_job.py`: rain-on-grid over the Fizh basin, 100-yr storm at 262 km2, project CN, n 0.05, 20 m.

| At or above the gauge | m3/s |
|---|---|
| Gauge, largest of 28 years | 475 |
| Gauge, Q100 of the report | 770 |
| HMS at Z4C, 7 km upstream, 211 km2 | 1,666 |
| Wadi2D at Z4C | 2,380 |
| **Wadi2D at the gauge** | **2,582, 3.4 x Q100** |

In the model 96 % of the flow passes in two adjoining threads beside the gauge, so the many-channels excuse for plain gauges does not apply here. No transmission loss is in the model. [Likely] A plain gauge reads low, the rating above bank is an extrapolation, and 28 years is short. None of these obviously closes a factor of 3.4, or 2.2 for HMS. **Either the 100-yr storm with these losses is too large for this ground, or 28 years have missed what it describes.**

**Sources.** Project 2331, *Hydrology Final Report - Flood Data Analysis*, 2025 (internal, read on W:). JICA Oman road study, chapter 11, [11784287_04.pdf](https://openjicareport.jica.go.jp/pdf/11784287_04.pdf), quoting the MRMEWR method and growth factors. Ewea, Al-Amri, Dawoud, Elfeki, Natural Hazards 94(2), 2018, [doi 10.1007/s11069-018-3421-x](https://ideas.repec.org/a/spr/nathaz/v94y2018i2d10.1007_s11069-018-3421-x.html). Dayqah: [Water Power Magazine](https://www.waterpowermagazine.com/analysis/the-day-wadi-dayqah-roared/). Al-Rawas and Valeo 2010, 12 Omani basins of 64 to 1,730 km2: [listing](https://squ.elsevierpure.com/ar/publications/relationship-between-wadi-drainage-characteristics-and-peak-flood), not read in full. Searches found no public peak discharge for Shaheen in Al Batinah; the project's gauge is the source.

### Extra: Shaheen at Lihban, an observed flood: **2D response consistent with the flood, in one of two loss forms**

Rule above, fixed before the run. Bani Umar near Lihban, 197.5 km2, 2,540 m3/s, 29.8 Mm3 (an older project table says 35.45; the 5-min record integrates to 29.76 and the 2331 sheet says 29.72), 459 mm at one gauge near the outlet; the two upstream gauges did not record. The sheet's Time column runs on from the start of the record and its Day column flips between 656 and 658, so minute 657 is midnight: main rain 00:00 to 05:40 on the 4th, as the project's HMS run has it [Likely]. Uncalibrated: n 0.05, nothing tuned. Figure: `t3_envelope\fig_lihban.png`.

| At the gauge | Peak, m3/s | / observed | First crest, h | Second flood, h | NSE |
|---|---|---|---|---|---|
| Observed | 2,540 at 4.0 h | 1 | 3.1 (2,160) | 6.0 | |
| **Wadi2D, phi loss** | **2,428** | **0.96** | 3.1 | 6.5 | 0.75 |
| Wadi2D, constant fraction | 1,486 | 0.59 | 3.1 | 6.6 | 0.70 |
| SCS lag 140 min (project HMS), same volume | 1,559 phi, 1,125 fraction | 0.61, 0.44 | | | |
| Project calibration, CN 92, lag 140 | 2,557 | 1.01, with **1.95 x the volume** | | | |

- **Rise and first crest match to about 15 min with nothing tuned.** The model has one broad crest where the gauge has two, so its highest point falls 54 min before the gauge's. The rule reads the first crest.
- **The first set-up run was invalid and is not a result:** the box below the gauge touched the basin at a pinch and 1 % of the water left. The box was widened; nothing else changed.
- **Best-fit SCS lag at Lihban, gauged rain, volume held** (`s11_lag_fit.py`, `s15_lag_events.py`): Shaheen 44 to 86 min; 2013, 72; 2019, 86; 2007, 114 at NSE 0.39. Centroid to centroid 81 to 147 min. Project lag 140. [Likely] The real lag is 0.3 to 0.8 of the project's on this basin, overlapping 2D's 0.3 to 0.6 of HMS. One basin, rain from at most three gauges.
- **The national report points the same way, and warns:** Tc from index hydrographs is a median 0.45 of Kirpich on 33 stations, but it says rising limbs may be under-recorded and the implied velocities look high.
- **Runoff was 33 % of the gauge's rain, against about 70 % in the 100-yr run on the Fizh basin (38.9 Mm3 of excess on 205 mm over about 270 km2; the 81 to 85 % first written here is a flat CN 88, not the project grid).** 151 of 459 mm. Implied CN 34 at the gauge's rain, 51 at 330 mm, 69 at 250 mm over the basin; the basin mean is not known. Earlier events 14 to 27 %.

**What the two extras say together** [Likely]: HMS at Block 2 carries two errors of opposite sign, a lag too slow and an excess too large; that is why the calibration needed 1.95 x the volume to reach the peak. 2D corrects the first and keeps the second, so it stands furthest from the gauges. 17 may lie nearer the record than 30 for the wrong reason.

### Test 4, extent F 0.40: **main cause named: the comparison counted ground his model never covered**

**Rule 4 verdict.** His layer stops at his model's perimeter, 1,083 km2, and is blank across the rest of its 2,068 km2 rectangle (the 1,730 km2 in `W2 full extent run/README.md` is wrong). Wadi2D had 119 km2 over 0.3 m in that blank ground, each of it counted as a miss. Restricting both to his perimeter takes F from **0.407 to 0.598, +0.19**, and removes 54 % of the misses. Both tests of the rule pass. **The run was not as far from his map as 0.40 said.**

**How his layer was made** [Certain for the plans read; Likely for the 200-yr plan, whose files were not found]. It is plan `Block2_FM_200Yr(F)` of the model at `W:\2512-1 Liwa- Fizah Road\06-WORKING\03-Hydrology\07. HECRAS\Block02.p06\`, an October 2025 refinement of the Workshop model `2224...\10 Workshops with stakeholders\Hydraulic Models\Block2\Block02`. The rasmap names the plan, and the raster grid sits on the same pixel corners. The plans, geometry and rain table of the sibling plans were read; `Block02.p10` itself and its results are not on W:.

| Input | His layer | W2 | Tested here |
|---|---|---|---|
| Domain | 1,083 km2 perimeter, Sea line the only outlet, S 0.0065 | 15,398 km2, coast S 0.003 | Yes |
| Rain | FM pattern, 10 min steps, uniform, table of the 50-yr plan 153.0 mm = 168.1 x 0.91, so **228 mm** at 200 yr [Likely] | 251 x ARF at 300 km2 = **209 mm** | Yes |
| Losses | SCS CN layer on the cells | Project CN grid | Not separately |
| Terrain | `HDSM_DTM_NSA`, 3 m raster on the GGC pixel corners | NSA 5 m + Copernicus | Yes, GGC 5 m stands in |
| n | 0.06 uniform [Likely, base value, `LCMann Table=0`] | 0.05 | Yes |
| Cells | 476,943 unstructured, about 23 m mean, 4,714 breaklines, 60 m base, 25 m along breaklines | 30 m uniform | 15 m only; breaklines cannot be tested here |
| Equations | SWE-ELM, Courant 0.85, 10 s, 24 h | Full SWE, 36 h | No |
| Roads, channels, dams | In the DTM as surveyed; **no 2D connections, so no culverts**; `g02` has no channels and no dams | Same natural ground, no structures | |

**Layers on one metric.** Depth over 30 m with dry as dry, 0.3 m, the metric of the 0.40; `t4_extent\s05_decompose.py`, `s08_score.py`. Changes from A, one at a time:

| Change | F | Move | Rule |
|---|---|---|---|
| A. As reported: W2 cell mean, his rectangle | 0.407 | | |
| **B. Inside his perimeter** | **0.598** | **+0.191** | **Main cause** |
| C. Pixel depth averaged to 30 m, not cell mean | 0.413 | +0.006 | Excluded |
| E. 5 m pixels, inside his perimeter, against B | 0.612 | +0.014 | Excluded |
| Whole-map shift, best of +/-40 m in 10 m steps, plain | 0.659 at 0, 0 | 0 | Excluded |
| Shift tile by tile, 2 km, 199 tiles, +/-60 m | median best shift 0 m, 1 % over 30 m | 0 | Excluded: no channel sits elsewhere |

**Runs on his perimeter, one input moved, against the base `c_t0`.** All with the gated outlet of the section above: 172 of 189 Mm3 leaves, 9 % on land at 30 h.

| Run | Rain Mm3 | F | Move | Rule |
|---|---|---|---|---|
| `c_t0` base, W2 inputs | 189 | 0.598 | | |
| `c_t1` rain 228 mm | 209 | 0.606 | +0.008 | Excluded |
| `c_t2` n 0.06 | 189 | 0.606 | +0.008 | Excluded |
| `c_t4` cell 15 m | 189 | 0.611 | +0.013 | Excluded |
| `c_t3` GGC 5 m terrain | 189 | 0.631 | +0.033 | **Partial** |
| `c_t5` all four | 209 | 0.662 | +0.064 | Below the 0.10 of a main cause |

**The rest, F 0.60 to 0.66, is not explained and is not noise.** Yardstick: his own 100- and 200-yr layers score 0.90 on the same metric.

| 5 m pixels, 0.3 m, inside his perimeter | Both | His only | W2 only | F |
|---|---|---|---|---|
| Hills, 599 km2 | 28.8 | 26.9 | 4.6 | 0.48 |
| Plain, 484 km2 | 112.7 | 31.3 | 27.1 | 0.66 |

- **The misses are thin.** 54 of his-only's 58 km2 sit in patches under 60 m wide, so they are gully edges, not a different flood path. The same network lights up in both (`t4_extent\fig_extent_w2.png`).
- **Water depth agrees better than edges.** Median Wadi2D less his -0.11 m where both exceed 0.5 m, as W2 reported.
- **Candidates left, not testable on this grid:** his 25 m breakline cells along the gullies, SWE-ELM, Mapper's depth rendering against a mean depth [Guessing which].

**The hybrid (W7) is a separate case.** F 0.14 inside his perimeter, because its 2D area is only 226 km2: hills lumped, plain cut at 443,500 E. Inside its own 2D area F is 0.53, against 0.61 for W2 on the same ground. That job also ran n 0.04, and the map used 15 min frames.

**What this does not settle.** Neither map is observed. Both carry 200-yr rain through CN losses that test 3 found high by a wide margin, so agreement between them says nothing about a real 200-yr flood.
