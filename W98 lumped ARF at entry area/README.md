# W98 lumped ARF at entry area

Branch `feature/arf-entry-area` off `feature/fast-products` (`0cfc332`), not merged, nothing pushed. Engine only, CPU.

Two tasks:

1. His rule of 2026-11-15 for `storm.area_reduction` (W95): the lumped part's form decides. A coefficient applies to
   every lumped subbasin (1 = no ARF); a fixed area gives one factor from the curve; a **curve reads each lumped
   subbasin at the total upstream area of the element where its water enters the 2D grid**, found from the network,
   never refused. In a lumped-only run the curve keeps HMS depth-area practice (every element at its own area).
2. W95 typed the NRCS Type I, IA, II and III 24-hour curves from memory: check every ordinate against a primary source
   and correct what is wrong.

## 1. The curve at the entry element's area

What changed (`wadi2d/engine/entry_area.py`, new; `run._lumped_rain`, `run._network`, `NetworkSeries`):

- Each lumped subbasin's entry element is the inflow's element (dam, junction) or the end of a hand-back's route it lies
  above, on links the grid does not carry (a generated basin's routes cut the rest); a subbasin entering at its own
  outlet enters at itself. Above two entries the nearer (smaller drainage area) wins. The area is
  `Basin.drainage_area`, HMS's total upstream area through `Downstream` links. Before, a subbasin with no storm area
  read the curve at its own area.
- A subbasin's own `storm_area_km2` still wins. One whose water reaches no entry (a table inflow of its name) reads its
  own area.
- The grid takes the hydrographs of that run. Every written element **above** its entry with a different drainage area
  (the upstream dam of a dam in series, the subbasins, reaches and junctions above a dam) is rerun lumped at its own
  drainage area (the network above it, `cut` links respected, the same storm and own storm areas); that rerun is its
  **series of record** (`series/network_<element>.csv`, `series/network/<element>`), and what the grid took is kept
  beside it as `series/entry_area_<element>.csv` and `series/entry_area/<element>`. The prefix `entry_area_` is not one
  the workbook dialog lists. `lumped_entry_areas.json` in the run folder lists every subbasin (entry, area, factor,
  where the area came from) and every rerun element (own and entry area and factor, which series is of record). The
  network layers read the series of record. A `lumped_entry_areas` event and a warning go on the run's record.
- Elements a hand-back runs live are not rerun (their water is the grid's).
- A lumped-only run is unchanged: it already reads every element at its own drainage area (`run_lumped`, `_by_element`).
- The words of the lumped curve in `arf_tags` and the warnings now say both cases; the schema's description of
  `form: curve` says it too (`tests/plugin/schema_sample.json` follows).

Not touched: jobs without a lumped curve (old `storm.arf` + `storm_area_km2`, fixed area, coefficient, no reduction)
take no branch of the new code; `test_jobs_without_a_lumped_curve_hash_and_read_as_before` holds the hash and the rain.

### Tests (`tests/engine/test_entry_area.py`, 6)

Network: A 0.01 and B 0.02 km2 into junction J (entry); C 0.03 into dam D1, reach Rd, dam D2 (entry) where E 0.04
joins. Curve 1 at 0 km2 to 0.5 at 0.1 km2, so factor = 1 - 5 x area, by hand: J 0.85, D2 0.65.

- A, B read 0.85, C, E read 0.65 (to 1e-12); E with its own 0.01 km2 reads 0.95; a fixed area 0.05 km2 gives 0.75 to
  all; a coefficient 1 gives no reduction.
- What enters at J and D2 is area x entry factor x depth (CN 100) to 1e-3; the own-area reruns are exactly
  {A, B, C, E, D1, Rd}; D1's own-area inflow volume is 0.03 x 0.85 x 50 mm, its grid run 0.03 x 0.65.
- Every rerun element and both entries equal a lumped-only run with the same curve to 1e-12 (HMS depth-area).
- A full run writes `lumped_entry_areas.json`, `entry_area_D1.csv` beside `network_D1.csv`, no `entry_area_D2.csv`.
- A generated basin (the W27 valley): all three subbasins enter at the outlet, read at the total area; the arms and
  the fork are rerun at their own areas.
- Old jobs: same hash, same rain, no reruns.

Also passed, one file at a time: `test_rain_sources_split_arf` 10, `test_lumped_network` 8, `test_subbasin_storm_area`
5, `test_network_series` 1, `test_rain_preview` 7, `test_handback` 33, `tests/plugin/test_contract` 97, and the
generated-basin, left-out and design-line files (see the commit). The full suite was not run (one runs on the main
checkout).

### Block 2 dry check (`scripts/dry_check_block2.py`, `results/`)

W79 `jobs/rerun2_run3_hybrid_aligned.json` (Hybrid Lumped, HMS Basin 3) with its storm moved to
`storm.area_reduction`: the lumped part a curve (his ARF FM table), the 2D part at 100 km2, every hand-typed
`storm_area_km2` taken out. No 2D solver.

| Entry element | Area km2 | Factor | Subbasins |
|---|---|---|---|
| Bidah 03 Reservoir | 20.971 | 0.9749 | S13 |
| Faydh 01 Reservoir | 74.304 | 0.9310 | S11, S12 |
| R5A Reservoir | 117.105 | 0.9046 | S14 to S18 |
| R2A Reservoir | 175.867 | 0.8758 | S5 to S10 |
| Z4C Reservoir | 211.085 | 0.8607 | S1 to S4 |
| HAT-J4 | 260.966 | 0.8461 | HAT-S1 to HAT-S8 |

- All 26 lumped subbasins found their entry; every area equals the one W79 typed by hand to its two decimals (largest
  difference 0.005 km2). No dam of Basin 3 lies above another, so the dam-in-series case does not arise on Block 2.
- The network the run would route, with the reruns: 0.3 s. Entry peaks, inflow / outflow m3/s: Bidah 03 454.6 / 0,
  Faydh 01 1,240.1 / 0, R5A 1,143.5 / 753.8, R2A 1,735.9 / 818.4, Z4C 2,101.1 / 2,025.0, HAT-J4 2,472.0: W79 rerun2
  run 3's numbers (Faydh 1,240.2 there; its hand area 74.30 against 74.304).
- 48 elements above the entries are now reported at their own area, peaks 1 to 17 % above what the grid's run gave
  them (S1 710 to 783 m3/s, J2 2,050 to 2,071, HAT-S5 447 to 522); listed in `results/block2_dry_check.json`.

## 2. The NRCS 24-hour curves

Source: HEC-HMS 4.12's own tables, read from `C:\Program Files\HEC\HEC-HMS\4.12\hms.jar`, class
`hms/model/met/e/aT` (the same arrays in `aV`), by `scripts/java_arrays.py` (reads the class file, runs nothing):
1441 ordinates a minute per type. Every sixth (0.1 h) is a number of four decimals, the NRCS tabular 0.1-hour
distribution; HMS's minutes between lie on a natural cubic spline through those knots to 5e-5 (HMS holds them to four
significant figures). Types told apart by I 0.035 at 2 h, IA 0.425 at 8 h, II 0.663 and III 0.500 at 12 h. NEH 630
chapter 4 itself was not read; HMS's tables were the brief's first choice.

W95's 23 ordinates against HMS (`results/scs_w95_against_hms.csv`):

| Type | Largest difference | Where | Ordinates off by more than 0.0005 |
|---|---|---|---|
| I | -0.0060 (0.926 against 0.932) | 20 h | 11 of 23 |
| IA | -0.0066 (0.906 against 0.9126) | 20 h | 2 of 23 |
| II | -0.0285 (0.357 against 0.3855) | 11.75 h | 3 of 23 |
| III | -0.0169 (0.339 against 0.3559) | 11.75 h | 9 of 23 |

Corrected: `wadi2d/storm/scs_tables.py` holds HMS's 241 knots of each type (written by `scripts/scs_check.py --write`);
`patterns.scs_curve` carries them to every minute on a natural cubic spline, knots kept exactly, and the storm reads
the minutes linearly: HMS's every minute to 5e-5 (`results/scs_new_against_hms.json`). Linear between the 0.1-hour
knots alone would be up to 0.0104 off HMS (Type II near noon). `tests/storm/test_scs_tables.py` (8) checks 16 of HMS's
minutes between knots per type to 6e-5, the knots, the NRCS anchors and that W95's worst ordinate is gone;
`tests/storm/test_rain_sources.py` reads the new table.

Effect: a W95 job with `storm.pattern.kind: scs` (new since W95; no job file in the W folders names one) changes its rain in time; its
depth total does not change.

## Not done

- The full suite (left to the merge); no real 2D run of Block 2 with the curve.
- The dock: nothing shows the entry areas or the `entry_area_` series yet; the workbook reads the series of record.
- The depth-area study (`wadi2d arf`) turns a lumped curve into a fixed area per run (`at_study_area`), as before; it
  takes no entry areas.
- NEH 630 chapter 4 not read against HMS's table.
