# W41 hybrid design lines

**Status (2026-11-07): fixed on his "Yes", branch `fix/hybrid-design-lines`, 23 of 24 through the real dock. A lumped
subbasin from an HMS project now enters at the wadi outlet of its own polygon, up the wadi and clear of every line. A
design line on a generated basin whose junction drains down a reach now reads the network's water too: Bidah 03 reads
410.4 m3/s, against 0.69 before. The one failure is Faydh 01's raw peak at 80 m, 0.957 of W1's placement, while its
15-minute peak agrees to the digit; see "Through the real dock".**

**The finding, as first written. The water is not lost: the books close to 2e-8 in every run. A hybrid's design line
reads only the grid, and the lumped water is put on the grid below the line, or carried past it inside a lumped reach.
The cause is not specific to Bidah 03. In every dock hybrid built from an HMS project, at all five Block 2 dams, the
local subbasin's hydrograph enters 0.4 to 87 m on the downstream side of the dam line. W1's validated mode (b) put it
80 to 460 m upstream. Measured on Block 2 at 80 m with the dock's entry points, the dam lines read 0.57 (Faydh 01),
0.003 (Bidah 03), 0.86 (R5A), 0.81 (R2A) and 1.00 (Z4C) of the same run with W1's. With W1's entry points every dam
line reads the lumped network within 2.2 %.**

His words (2026-11-07, on W39's question 5): "i don't know exactly what's the issues, but if the upsteam network is
generating 410 m3/s and the line shows and read 0.69 as flow going to downstream grid, it is a big issue and very
important to solve."

## What happens, in two routes

| Route | Where lumped water reaches the grid | What the design line sees |
|---|---|---|
| **Generated basin** (`wadi2d basin`, W24 to W27) | The design line becomes a junction, `Bidah 03`. Its route is *reach R1 to J1*, so the water travels inside the lumped reach and enters the grid at J1, 2.29 km below the line (`wadi2d/basin/job.py`, `_plan`) | Only the rain-on-grid around it: 0.69 m3/s against 410.2 in the network |
| **HMS route** (the dock's Hydrology section with an HMS folder, `wadi2d hms-import`) | Each subbasin enters at the icon of the element it drains to (`wadi2d/engine/hms_import.py`, `_outlet`). A dam's local subbasin drains to the dam junction, and that icon sits on the dam line or just below it | Nothing of that subbasin when its entry cell falls below the line's staircase, all of it when the cell falls above. W39 run 5: 24.4 m3/s against S13's 1,443.8 |

Both follow rules that were written down. D6 says a defined reach routes HMS-style, and HMS gives icons. Neither rule
ties the lumped water to the design line it drains to. W1's validated mode (b) did tie it, by hand: "hydrographs at the
wadi outlet of each polygon", the largest accumulation inside the polygon eroded 80 m. That rule is
`lumped_outlets` in `validation/block2_full/scripts/common.py`, and S13 was moved further up by hand "because the
accumulation rule placed it on the axis itself". When the HMS route went into the dock (W20), it took the icons
instead. Nothing has compared the dock's mode (b) at the dams with W1's since.

## Evidence

### Where each dam's local hydrograph enters (`inflow_sides.py`, `inflow_sides.json`)

Signed distance to the dam line. Negative is the subbasin's side (upstream).

| Dam | Local subbasin | Dock (HMS icon of the dam junction) | W1 validated outlet |
|---|---|---|---|
| Bidah 03 | S13 | **+87.3 m** | -420.7 m |
| Faydh 01 | S12 | **+0.4 m** | -94.8 m |
| R5A | S16, S17, S18 | **+12.1 m** | -85.1, -301.3, -82.5 m |
| R2A | S9, S10 | **+7.6 m** | -462.3, -85.1 m |
| Z4C | S4 | **+6.7 m** | -80.7 m |

### The test that confirms it: W39 run 5 with S13 entering upstream

The same resolved job (PMP, HMS route, S13 lumped, the other 17 subbasins rain-on-grid, 30 m), with only S13's outlet
moved to W1's point, 421 m above the line. Engine CLI, GPU, mass error 2.3e-8.

| S13 enters | Bidah 03 line peak | Line volume | S13 network |
|---|---|---|---|
| HMS icon, 87 m below (W39 run 5) | 24.4 m3/s, 13.69 h | 0.405 Mm3 | 1,443.8 m3/s, 23.722 Mm3 |
| W1's outlet, 421 m above | **1,463.8 m3/s**, 12.89 h | **24.122 Mm3** | 1,443.8 m3/s, 23.722 Mm3 |

The line volume equals S13's volume plus the rain-on-grid it read before: 23.722 + 0.405 = 24.127 against 24.122 Mm3.
The peak comes 4 min after the network's, the time it takes to travel 421 m.

### The generated basin (W39 run 3, from its saved series)

`network_Bidah_03.csv` has an outflow peak of 410.155 m3/s at 12.67 h and 2.340 Mm3. The grid line has 0.688 m3/s and
0.011 Mm3. Grid plus network at the line's times gives a peak of 409.5 m3/s: the network series is 5-minutely and the
line's minutely. Reach R1 delivers 408.7 m3/s to J1, and J1 takes 473.7 m3/s onto the grid with S1.

### Block 2 at the five dams, both placements (`jobs/w1_outlets.json`, `jobs/dock_icons.json`, `block2_entry.json`)

The setup is W1's mode (b) job, `arf_b20_n100.json`:
- all 18 subbasins lumped, the reaches and the plain in 2D;
- the HMS 100-yr storm at a 300 km2 storm area;
- Manning 0.1 on the reaches.

The cell is 80 m in place of 20 m, the run lasts 36 h, and it ran on the engine CLI and the GPU at `2068c93`. The two
jobs differ only in each subbasin's `outlet`. One uses W1's point. The other uses the icon the dock's `hms-import`
writes, through its own `_outlet`. Mass error is 5e-9 and 3e-9. The lumped network is the HMS method from the same run,
`series/network_<dam>.csv`.

| Dam | W1's entry: line peak, m3/s (h), volume Mm3 | Dock's entry: line peak (h), volume | Dock / W1, peak / volume | Lumped network, peak / volume |
|---|---|---|---|---|
| Faydh 01 | 875.1 (13.28), 10.69 | 498.2 (13.46), 6.00 | **0.569 / 0.561** | 877.9 / 10.67 |
| Bidah 03 | 299.1 (12.82), 2.84 | 1.0 (13.12), 0.02 | **0.003 / 0.009** | 302.3 / 2.83 |
| R5A | 791.1 (14.89), 16.33 | 677.3 (14.96), 11.54 | **0.856 / 0.707** | 801.1 / 16.46 |
| R2A | 1,305.0 (14.19), 24.49 | 1,055.4 (14.57), 19.81 | **0.809 / 0.809** | 1,277.3 / 24.58 |
| Z4C | 1,586.8 (15.74), 29.52 | 1,584.9 (15.72), 29.53 | 0.999 / 1.000 | 1,605.7 / 29.89 |

- [Certain] With the dock's entry points, four of the five dam lines read low at 80 m. Faydh 01 reads 0.57. Bidah 03
  reads nothing. R5A reads 0.86 on the peak and 0.71 on the volume, R2A 0.81. Z4C's S4 entry cell fell on the upstream
  side of the line's staircase, so it reads all of it. Whether a cell falls above or below depends on the
  rasterisation, so other cell sizes will differ dam by dam.
- [Certain] With W1's entry points, every dam line reads the lumped network within 2.2 % on peak and 1.3 % on volume.
- [Likely] **Every dock hybrid built from an HMS project since W20 reads its dam lines this way:** W20's Block 2
  hybrid, W33, W38, and W39 run 5. W37's open question (a dam line reading 42.6 m3/s against its junction's 308.5) has
  the same cause on the generated route. Comparisons inside one placement (W20's storm forms, W33's backends) are not
  affected. W1's mode (b) record is not affected: it used W1's own outlets.

## The fix (his "Yes", 2026-11-07; branch `fix/hybrid-design-lines`)

[PRESERVE-CHECK] [BROAD], as agreed:
- KEEP:
  - Every job that gives explicit outlets or inflow points runs to the last digit (W1's validation jobs, every test job).
  - The lumped engine, the hand-back, and his D6 routing rules: a defined reach still routes HMS-style.
  - The grid's own `line_<name>.csv`.
  - The W38 warning.
- CHANGE:
  1. A subbasin with `entry: wadi` enters at the wadi outlet of its polygon on the run's grid, W1's rule: the largest
     drainage area inside the polygon eroded `hydrology.entry_erode_m` (80 m). From there the entry walks up the wadi
     until the injection's cells and one more are clear of every result and hand-back line. `hms-import` writes
     `wadi`, so every dock HMS-route job takes it. A subbasin with no polygon walks up from its outlet.
  2. On a generated basin, a junction built on a design line gets an `entry: wadi` inflow, so it enters above the line.
     Where a reach carries that junction's water past the line instead, the line's record adds the junction's network
     outflow, less the 2D water a hand-back below the line took back.
  3. A record per such line, `series/design_<line>.csv` (grid, network, total). The run's peak for the line is the
     total's, so the depth-area study reads it. The Result lines panel draws the total as the number of record, with the
     grid alone in grey.
  4. `entries.json` in the run folder: where each entry was asked for, where it entered, and why.
- FILES: `wadi2d/config/schema.py` (`entry`, `entry_erode_m`); new `wadi2d/engine/entries.py`; new
  `wadi2d/engine/design_lines.py`; `wadi2d/run.py` (placement before the forcing, the records after the line series,
  the job hash dropping `point` entries so old checkpoints keep); `wadi2d/engine/hms_import.py`;
  `wadi2d/basin/job.py`; `wadi2d/engine/line_checks.py` (its cell helper made public); `wadi2d/products/result_lines.py`;
  `plugin/wadi2d_qgis/line_view.py`. Tests: new `tests/engine/test_entries.py` and `tests/engine/test_design_lines.py`;
  amended `tests/engine/test_basin_run.py` (a resolved inflow now carries `entry`), `tests/engine/test_block2.py`
  (the import asks for `wadi`), `tests/plugin/test_line_view.py`, `tests/plugin/schema_sample.json`.
- The coverage check per line, also in the proposal, is not built. The line-to-network mapping is exact on a generated
  basin, and on the HMS route the entries now lie above the lines, so the check would only re-measure what the runs
  already show.

### The fix on the CLI, the same jobs as above (`jobs/`)

The dock's own entry points (the HMS icons), now with `entry: wadi`:

| Dam | Line peak, m3/s | Volume, Mm3 | Against W1's outlets, peak / volume | Lumped network |
|---|---|---|---|---|
| Faydh 01 | 877.6 | 10.69 | 1.003 / 1.000 | 877.9 |
| Bidah 03 | 301.6 | 2.84 | 1.009 / 1.000 | 302.3 |
| R5A | 789.4 | 16.33 | 0.998 / 1.000 | 801.1 |
| R2A | 1,304.4 | 24.48 | 1.000 / 1.000 | 1,277.3 |
| Z4C | 1,582.3 | 29.51 | 0.997 / 1.000 | 1,605.7 |

All 18 entries are clear of every line, dam lines and rings alike. They moved 128 to 944 m from the icons. W38's
warning fires 0 times, against 15 with the icons and 1 with W1's hand-placed outlets.
The rings round the lumped subbasins in the same three 80 m runs, against each subbasin's own network outflow:

| Ring | HMS icons | W1's outlets | `entry: wadi` | Network | `wadi` / network |
|---|---|---|---|---|---|
| S1 | 18.6 | 549.7 | 549.3 | 549.2 | 1.000 |
| S2 | 15.5 | 439.8 | 439.9 | 441.6 | 0.996 |
| S5 | 41.1 | 653.4 | 659.9 | 629.5 | 1.048 |
| S6 | 2.0 | 326.5 | 326.5 | 326.9 | 0.999 |
| S11 | 52.6 | 508.3 | 507.0 | 492.7 | 1.029 |
| S14 | 451.4 | 455.2 | 453.7 | 447.9 | 1.013 |

[Likely] W31's finding that "a ring on a lumped subbasin's edge passes about half its hydrograph" (S5 0.50, S11 0.48,
S14 0.00, at 40 m on W20's dock job) is this same cause. That job took the HMS icons, which sit on the rings. The surge
itself, a pond where a hydrograph enters with no momentum, is a separate finding and still stands, now up the wadi from
the rings. S5's +4.8 % at 80 m may be its trace [Guessing].

W39's PMP run 5 with `entry: wadi` on S13: the Bidah 03 line reads 1,463.9 m3/s (S13 moved 186 m up the wadi), against
24.4 with the icon and 1,463.8 with W1's point.

### Through the real dock (`dock_design_lines.py`, `log_dock_design_lines.txt`): 23 of 24

QGIS 3.44.8, throwaway profile, the plugin and engine of this branch. The rules were fixed before the runs.

| Case | Result | |
|---|---|---|
| 1. W39's generated hybrid, Bidah 03, 30 m, RP200 NetCDF | The record's peak is 410.4 m3/s: the grid alone gives 0.69 and the network 410.2. The record equals grid plus network within 0.5 %, and holds W39's 410.16 within 1 %. The panel draws the record as the number of record, the grid alone in grey, and says why | PASS |
| 2. W39's PMP through the HMS route, S13 lumped | The import asks for `wadi` entries. S13 moved 186 m up the wadi, clear of the lines. The Bidah 03 line reads 1,463.9 m3/s against the 1,463.8 the CLI found with W1's point (24.4 before) | PASS |
| 3. Block 2 hybrid at 80 m, HMS 100-yr storm, dock Manning 0.035, 48 h | No dam line is warned of an inflow's cells. Against the same dock job on W1's outlets: Bidah 03 1.002, R5A 0.992, R2A 0.995, Z4C 0.997 | PASS 4 of 5 |
| | **Faydh 01 reads 0.957 on the raw peak, 895.6 against 936.1 m3/s** | **FAIL** |

**The failure, with its evidence.** At Faydh 01 the 15-minute peaks agree to the digit, 889.9 against 890.0 m3/s, and
the volumes within 0.11 %. The raw peak of the W1 placement is a spike 5 % above its own 15-minute peak. W33 measured
the same thing at Faydh 01: its raw peak moved 1.9 % under a Courant number nudged by 1e-6, while its 15-minute peak
moved 0.05 %. So the rule failed on the raw peak, which near a lumped inflow carries the pond's surge (W31), and not on
the flow. The rule stays as it was written, and the case is recorded as a fail. On the CLI job (Manning 0.1) the same
dam reads 1.003 of W1's.

| Dam | Raw peak, dock / W1's outlets | 15-minute peak | Volume |
|---|---|---|---|
| Faydh 01 | 895.6 / 936.1 = **0.957** | 889.9 / 890.0 = 1.000 | 0.9989 |
| Bidah 03 | 302.6 / 302.0 = 1.002 | 1.001 | 1.0000 |
| R5A | 994.0 / 1,002.5 = 0.992 | 0.996 | 1.0000 |
| R2A | 1,435.3 / 1,442.4 = 0.995 | 0.998 | 0.9999 |
| Z4C | 1,669.8 / 1,674.1 = 0.997 | 0.998 | 1.0000 |

The entries sit 4 to 433 m from W1's hand-placed points (S11 117 m, S12 106 m at Faydh 01). W1 read HMS's own 5 m
accumulation; the engine reads its own D8 drainage on the run's cells.

## Rerun

```
.venv\Scripts\python "W41 hybrid design lines\inflow_sides.py" "W41 hybrid design lines\inflow_sides.json"
.venv\Scripts\wadi2d run "W41 hybrid design lines\jobs\w1_outlets.json" --out <folder>
.venv\Scripts\wadi2d run "W41 hybrid design lines\jobs\dock_icons.json" --out <folder>
.venv\Scripts\wadi2d run "W41 hybrid design lines\jobs\pmp_hybrid_s13_above.json" --out <folder>
```

Each job names a cache folder in the session's scratch space; set `grid.cache_dir` to a folder of your own first. The
S13 job reads its inputs from W39's throwaway run folder, which the next clean-up removes. To rerun it after that,
regenerate the job with W39's scenario.
