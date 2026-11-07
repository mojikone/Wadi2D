# W41 hybrid design lines

**Status (2026-11-07): root cause found and confirmed by test runs. No engine or plugin code has changed. The fix is
[BROAD] and waits for his go-ahead. The water is not lost: the books close to 2e-8 in every run. A hybrid's design line
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

## The fix, proposed (waits for his go-ahead)

See the [PRESERVE-CHECK] in the chat of 2026-11-07, repeated here once agreed.

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
